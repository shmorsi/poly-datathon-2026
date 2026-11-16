"""EPICENTRE API (plan D Task 4): serves web/, validates the flight plan, streams a run as NDJSON.

A thin, stateless layer: every number comes from pipeline.py (tools and the explainer), this file only
frames, validates and routes. Results are kept in memory by run_id (LRU, 50); inputs are never logged or
written to disk (red gate 6); errors cross the API as {"status": "error", "message": "<one sentence>"} and
never carry an exception text or a stack trace. Binds to 127.0.0.1 by default (`uvicorn server:app`).
Optional password: set the environment variable EPICENTRE_PASSWORD and every route except /api/health asks
for HTTP Basic credentials (any user name); unset or empty means open. There is no default password.
Deploy hardening (ledger section 30): with EPICENTRE_REQUIRE_PASSWORD=1 (the runbook's docker run) create_app()
raises at start-up on an empty or unset password, so the app never starts open by accident. When
EPICENTRE_ORIGIN_SECRET is set, every request except /api/health must carry the same value in X-Origin-Verify
(CloudFront adds it) or it gets 403, before the password is asked; the secret is never logged or returned.
"""
import base64
import binascii
import hmac
import json
import logging
import math
import os
import queue
import re
import secrets
import threading
import time
from collections import OrderedDict
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Callable, Iterator, Literal

import boto3
from fastapi import APIRouter, FastAPI
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

import config
from order_review import ExplainRequest, ReviewRequest, build_review, explain_review
import pipeline        # functions are looked up at request time (pipeline.recheck(...)) so tests can replace them
import record_store    # ruling R6: the sealed decision record vault (POST /api/record)

log = logging.getLogger("epicentre.server")

WEB_DIR = Path(__file__).resolve().parent / "web"
STARTER_PRICES = config.STARTER_DIR / "prices_daily.csv"
PERSONAS_PATH = config.DATA_DIR / "personas.json"
WIRE_PATH = config.CACHE_DIR / "wire.json"
PASSWORD_ENV = "EPICENTRE_PASSWORD"
REQUIRE_PASSWORD_ENV = "EPICENTRE_REQUIRE_PASSWORD"      # "1" (the runbook's docker run): never start without a password
ORIGIN_SECRET_ENV = "EPICENTRE_ORIGIN_SECRET"            # when it exists, requests must carry it in ORIGIN_HEADER
ORIGIN_HEADER = b"x-origin-verify"                       # the name CloudFront sends (ASGI header names are lower case)
NO_BEDROCK_ENV = "EPICENTRE_NO_BEDROCK"
DATA_START = date(2021, 11, 12)
MAX_TEXT = 2000
MAX_BODY_BYTES = 64 * 1024     # the largest legitimate body is a few KB; anything bigger is refused unread
RECORD_MAX_BODY_BYTES = 128 * 1024   # POST /api/record only: a sealed decision record is 15-50 KB (the lead, Sun 15 Nov)
HEALTH_TTL = 30.0              # seconds /api/health keeps its answer (the credential probe can take 1-2 s)

# the 31 tickers of spec section 9 (starter universe)
UNIVERSE_TICKERS = (
    "RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO",
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM",
    "XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO", "ZST.TO", "AGG", "TLT", "GLD",
    "BTC-USD", "ETH-USD",
)

MSG_EXPIRED = "This check has expired. Run it again."
MSG_GENERIC = "Something went wrong on the server. Try again in a moment; if it repeats, restart the server."
MSG_DATE = "Pick a date between 12 Nov 2021 and 12 Nov 2026."
MSG_PASSWORD = "Enter the password to open EPICENTRE."
MSG_FORBIDDEN = "This server only answers requests that come through its public address."
MSG_NO_PASSWORD = ("EPICENTRE_REQUIRE_PASSWORD is set but EPICENTRE_PASSWORD is empty or not set, so the server will "
                   "not start. Set a password, or leave EPICENTRE_REQUIRE_PASSWORD unset for local use.")
MSG_NO_RUNS = "There are no saved runs yet."
MSG_NO_INVESTOR_RUN = "There is no saved run for that investor."
MSG_NO_PILOTS = "The pilots file is not ready yet."
MSG_TOO_LARGE = "That request is too large."


class BodyTooLarge(FastAPIHTTPException):
    """Raised from `receive` once a body passes its cap (_body_cap; FastAPI passes its own HTTPException through)."""

    def __init__(self):
        super().__init__(status_code=413)


class ApiError(Exception):
    """An expected failure with its HTTP status and the one plain sentence the page shows."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def error_response(status_code: int, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"status": "error", "message": message}, status_code=status_code, headers=headers)


def _log_failure(where: str, exc: BaseException) -> None:
    log.error("%s failed (%s)", where, type(exc).__name__)    # the type only: a message can carry the user's input


class RunStore:
    """Thread-safe LRU of Results by run_id; `get` refreshes recency."""

    def __init__(self, maxlen: int = 50):
        self.maxlen = maxlen
        self._data: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, result: Any) -> None:
        run_id = result.get("run_id") if isinstance(result, dict) else None
        if not run_id:
            return
        with self._lock:
            self._data[run_id] = result
            self._data.move_to_end(run_id)
            while len(self._data) > self.maxlen:
                self._data.popitem(last=False)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            result = self._data.get(run_id)
            if result is not None:
                self._data.move_to_end(run_id)
            return result

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


RUNS = RunStore()


def to_json(obj: Any) -> str:
    """Compact JSON the browser's JSON.parse accepts (no NaN); numpy and tuples cleaned by pipeline.jsonable."""
    return json.dumps(pipeline.jsonable(obj), allow_nan=False, separators=(",", ":"))


def _public(result: dict) -> dict:
    """The Result as the browser may see it: top-level keys starting with '_' are server-side only."""
    return pipeline.jsonable(result)


def _with_funds(shown: Any) -> Any:
    """Live only (lane funds; red gate 8): the largest companies inside each fund the investor holds, with the investor's
    dollars in each (result_extras.funds_private), added to THIS response when the licensed holdings file is on this
    machine. A new dict: the stored run is not changed. Never saved (pipeline.save_run cuts it) and never published
    (record_demo.find_leaks refuses the key, so the static build fails if it ever appears)."""
    if not isinstance(shown, dict) or shown.get("status") != "ok":
        return shown
    try:
        import result_extras
        private = result_extras.funds_private(shown)
    except Exception as exc:                      # the look-inside is an extra: the run is answered without it
        _log_failure("funds_private", exc)
        return shown
    return {**shown, "funds_private": private} if private else shown


# ---- request bodies: the typed fields of ledger section 15; the question is the only free text ----

Weight = Annotated[float, Field(ge=0, allow_inf_nan=False)]


def _finite_limits(value: dict | None) -> dict | None:
    if value is not None:
        inner = [v for x in value.values() if isinstance(x, dict) for v in x.values()]   # sector_caps {industry: share}
        if len(value) > 32 or len(inner) > 32:
            raise ValueError("too many limits")
        if any(isinstance(v, float) and not math.isfinite(v) for v in [*value.values(), *inner]):
            raise ValueError("limits must be finite numbers")
    return value


def _checked_caps(limits: dict | None) -> None:
    """Lane sector-limits: an industry limit the replay cannot read is refused in governance's own plain sentence (422)
    before anything runs ("“Crypto” is not an industry this replay knows; use one of: ...")."""
    if isinstance(limits, dict) and limits.get("sector_caps") is not None:
        import governance
        try:
            governance.validate_sector_caps(limits["sector_caps"])
        except ValueError as exc:
            raise ApiError(422, str(exc)) from None


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: Literal["growth", "balance", "preservation", "income"]
    horizon_years: Annotated[StrictInt, Field(ge=1, le=40)]
    esg: StrictBool
    crypto: StrictBool
    risk: Literal["low", "moderate", "high"] | None = None
    capacity: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    reaction_2022: Literal["sold", "held", "bought"] | None = None


class RunBody(BaseModel):
    portfolio: dict[str, Weight]
    amount: float = Field(allow_inf_nan=False)
    profile: Profile | None = None
    limits: dict[str, Any] | None = None
    question: str = ""
    as_of: str | None = None
    redteam: StrictBool = False
    pilot: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")] | None = None

    _limits_ok = field_validator("limits")(_finite_limits)


class RecheckBody(BaseModel):
    run_id: str
    limits: dict[str, Any]

    _limits_ok = field_validator("limits")(_finite_limits)


class RecomputeBody(BaseModel):
    run_id: str
    id: str


class RecordBody(BaseModel):
    record: dict[str, Any]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class ScenarioReadBody(BaseModel):
    text: str = ""
    portfolio: dict[str, Weight] | None = None
    as_of: str | None = None


class ProfileReadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = ""


# ---- checks that run before any work ----

_DATE_RX = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _check_as_of(value: str) -> None:
    try:
        if not _DATE_RX.fullmatch(value):
            raise ValueError(value)
        day = date.fromisoformat(value)
    except ValueError:
        raise ApiError(422, MSG_DATE) from None
    if not DATA_START <= day <= date.fromisoformat(pipeline.DATASET_END):
        raise ApiError(422, MSG_DATE)


def _echo(text: str, limit: int = 24) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _checked_weights(body: RunBody) -> dict[str, float]:
    """The plan's plain-English refusals, in the plan's order; returns the weights normalized to sum 1."""
    for ticker in body.portfolio:
        if ticker not in UNIVERSE_TICKERS:
            raise ApiError(422, f"{_echo(ticker)} is not in the dataset. Pick one of the {len(UNIVERSE_TICKERS)} tickers.")
    total = sum(body.portfolio.values())
    if abs(total - 1) > 0.005:
        raise ApiError(422, f"Your weights add up to {total * 100:.0f} %; they must add up to 100 %.")
    if not body.amount > 0:
        raise ApiError(422, "Enter a fictional amount above $0.")
    if len(body.question) > MAX_TEXT:
        raise ApiError(422, "Keep the question under 2,000 characters.")
    if body.as_of is not None:
        _check_as_of(body.as_of)
    return {ticker: weight / total for ticker, weight in body.portfolio.items()}


def _stored(run_id: str) -> dict:
    result = RUNS.get(run_id)
    if result is None:
        raise ApiError(404, MSG_EXPIRED)
    return result


# ---- the NDJSON stream ----

_DONE = object()


def _line(event: Any) -> str | None:
    try:
        return to_json(event) + "\n"
    except Exception as exc:                      # an event the browser could not read: drop it, keep the run alive
        _log_failure("stream line", exc)
        if isinstance(event, dict) and event.get("type") == "result":
            return to_json({"type": "result", "result": {"status": "error", "message": MSG_GENERIC}}) + "\n"
        return None


def ndjson_lines(work: Callable[[Callable[[dict], None]], dict]) -> Iterator[str]:
    """Run `work(progress)` in a thread and yield one JSON line per progress event, then the result line."""
    events: queue.Queue = queue.Queue()

    def worker() -> None:
        shown = {"status": "error", "message": MSG_GENERIC}
        try:
            result = work(events.put)
            RUNS.put(result)
            shown = _with_funds(_public(result))
        except BaseException as exc:              # a cancellation or an exit request must not leave the stream open
            _log_failure("run", exc)
            if isinstance(exc, (SystemExit, KeyboardInterrupt)):
                raise                             # passed on, but only after the finally below has closed the stream
        finally:
            events.put({"type": "result", "result": shown})
            events.put(_DONE)

    threading.Thread(target=worker, daemon=True, name="epicentre-run").start()
    while True:
        event = events.get()
        if event is _DONE:
            return
        line = _line(event)
        if line is not None:
            yield line


# ---- the outer layer: optional password, security headers on every response, last-resort 500 ----

def _authorized(scope: dict) -> bool:
    password = os.environ.get(PASSWORD_ENV, "")
    if not password or scope.get("path") == "/api/health":
        return True
    supplied = None
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "basic":
                try:
                    user_and_password = base64.b64decode(token.strip(), validate=True).decode("utf-8")
                except (binascii.Error, UnicodeDecodeError):
                    return False
                _, colon, supplied = user_and_password.partition(":")
                if not colon:
                    return False
            break
    return supplied is not None and secrets.compare_digest(supplied.encode("utf-8"), password.encode("utf-8"))


def _origin_ok(scope: dict) -> bool:
    """Ledger section 30 (b), the third gate: behind CloudFront every request carries `X-Origin-Verify: <secret>`.
    No variable means no check (local dev). A variable that exists but is empty can match nothing, so a deployment
    mistake closes the door instead of opening it. /api/health stays open (the container probe sends no header).
    Both sides are bytes and are compared in constant time; nothing here logs or returns either value."""
    secret = os.environ.get(ORIGIN_SECRET_ENV)
    if secret is None or scope.get("path") == "/api/health":
        return True
    if not secret:
        return False
    for name, value in scope.get("headers", []):
        if name == ORIGIN_HEADER:
            return hmac.compare_digest(value, secret.encode("utf-8", "surrogateescape"))
    return False


def _declared_length(scope: dict) -> int:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


def _body_cap(scope: dict) -> int:
    return RECORD_MAX_BODY_BYTES if scope.get("path") == "/api/record" else MAX_BODY_BYTES


class Guard:
    """Pure ASGI middleware (no buffering, so the NDJSON stream flows)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_with_headers(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
            await send(message)

        if not _origin_ok(scope):                         # first: a caller that skipped CloudFront learns nothing else
            await error_response(403, MSG_FORBIDDEN)(scope, receive, send_with_headers)
            return
        if not _authorized(scope):
            challenge = {"WWW-Authenticate": 'Basic realm="EPICENTRE", charset="UTF-8"'}
            await error_response(401, MSG_PASSWORD, challenge)(scope, receive, send_with_headers)
            return
        cap = _body_cap(scope)
        if _declared_length(scope) > cap:                 # refused unread
            await error_response(413, MSG_TOO_LARGE)(scope, receive, send_with_headers)
            return
        received = 0

        async def counted_receive():                      # also covers a chunked body that declares no length
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > cap:
                    raise BodyTooLarge()
            return message

        try:
            await self.app(scope, counted_receive, send_with_headers)
        except BodyTooLarge:
            if not started:
                await error_response(413, MSG_TOO_LARGE)(scope, receive, send_with_headers)
        except Exception as exc:                  # never re-raised: no stack trace, no exception text, no inputs
            _log_failure(f"{scope.get('method', '')} {scope.get('path', '')}", exc)
            if not started:
                await error_response(500, MSG_GENERIC)(scope, receive, send_with_headers)


# ---- handlers ----

async def on_api_error(request, exc: ApiError):
    return error_response(exc.status_code, exc.message)


async def on_validation_error(request, exc: RequestValidationError):
    errors = exc.errors()
    parts = [p for p in (errors[0]["loc"] if errors else ()) if p not in ("body", "query", "path", "header", "cookie")]
    field = ".".join(_echo(str(p), 40) for p in parts) if parts and not isinstance(parts[0], int) else "request body"
    return error_response(422, f"The request has a missing or invalid field: {field}.")


_HTTP_WORDS = {404: "That page or action was not found.", 405: "That action is not allowed here.", 413: MSG_TOO_LARGE}


async def on_http_error(request, exc: StarletteHTTPException):
    message = _HTTP_WORDS.get(exc.status_code, "The request could not be completed.")
    return error_response(exc.status_code, message, getattr(exc, "headers", None))


# ---- routes ----

router = APIRouter()


def _json(obj: Any, status_code: int = 200) -> Response:
    return Response(to_json(obj), status_code=status_code, media_type="application/json")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.post("/api/run")
def run(body: RunBody):
    weights = _checked_weights(body)
    _checked_caps(body.limits)
    plan = {"portfolio": weights, "amount": body.amount,
            "profile": body.profile.model_dump(exclude_unset=True) if body.profile else None,
            "limits": body.limits, "pilot": body.pilot}
    as_of = body.as_of or pipeline.DATASET_END
    use_bedrock = os.environ.get(NO_BEDROCK_ENV) != "1"

    def work(progress):
        return pipeline.run(plan, body.question, as_of, progress=progress, use_bedrock=use_bedrock,
                            redteam=body.redteam)

    return StreamingResponse(ndjson_lines(work), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# Review evidence is kept in memory under an unguessable ID. Raw inputs are not cached.

REVIEW_EVIDENCE = RunStore(maxlen=50)


@router.post("/api/review")
def review_order(body: ReviewRequest):
    try:
        result = build_review(body)
    except ValueError as exc:
        raise ApiError(422, str(exc)) from None
    except (FileNotFoundError, OSError):
        raise ApiError(503, "Market data is unavailable. Try a saved example.") from None
    review_id = secrets.token_hex(16)
    REVIEW_EVIDENCE.put({"run_id": review_id, "evidence": result["evidence"]})
    result["review_id"] = review_id
    if "before_evidence" in result:
        before_id = secrets.token_hex(16)
        REVIEW_EVIDENCE.put({"run_id": before_id, "evidence": result["before_evidence"]})
        result["before_review_id"] = before_id
    response = _json(result)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/api/review/explain")
def explain_order_review(body: ExplainRequest):
    cached = REVIEW_EVIDENCE.get(body.review_id)
    if cached is None:
        raise ApiError(404, "This review expired. Run the calculations again.") from None
    try:
        result = explain_review(cached["evidence"], body.goal.strip(),
                                use_bedrock=os.environ.get(NO_BEDROCK_ENV) != "1")
    except PermissionError as exc:
        raise ApiError(422, str(exc)) from None
    response = _json(result)
    response.headers["Cache-Control"] = "no-store"
    return response


def _signed_floor(limits: dict | None) -> dict | None:
    """Jury QA K3: a positive floor f is the drop −f, the way a person types "35 %" (0.35 reads −0.35)."""
    floor = limits.get("floor") if isinstance(limits, dict) else None
    if isinstance(floor, (int, float)) and not isinstance(floor, bool) and floor > 0:
        return {**limits, "floor": -floor}
    return limits


def _checked_limits(limits: dict | None, stored: dict) -> None:
    """Every limit the stored run would be judged with, read by governance before anything runs: one it refuses is 422
    in its own plain sentence ("The floor is a drop, so it must be between −100 % and 0 %."), never a 500."""
    _checked_caps(limits)
    raw = stored.get("profile")
    if not isinstance(raw, dict):
        return                                            # no answers: the recheck judges nothing
    import governance
    try:
        governance.load_limits({k: raw[k] for k in pipeline.PROFILE_KEYS if k in raw}, limits or None,
                               amount=stored.get("amount"))
    except ValueError as exc:
        raise ApiError(422, str(exc)) from None


@router.post("/api/recheck")
def recheck(body: RecheckBody):
    limits, stored = _signed_floor(body.limits), _stored(body.run_id)
    _checked_limits(limits, stored)
    return _json(pipeline.recheck(stored, limits))


@router.post("/api/recompute")
def recompute(body: RecomputeBody):
    """One number of a stored run computed again by its own tool (pipeline.recompute): the value, how it was computed
    and whether it equals the stored one. An unknown number is 404; tools or data missing on this machine, 503."""
    answer = pipeline.recompute(_stored(body.run_id), body.id)
    if isinstance(answer, dict) and answer.get("error"):
        raise ApiError(503 if answer.get("reason") == "unavailable" else 404, str(answer["error"]))
    return _json(answer)


class ScenarioBody(BaseModel):
    """POST /api/scenario (lane sc-b): the shocks stay raw JSON so tools.factors refuses a true or a "0.3" in plain words."""
    portfolio: dict[str, Weight]
    shocks: dict[str, Any]
    baseline: dict[str, Weight] | None = None
    limits: dict[str, Any] | None = None
    amount: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    as_of: str | None = None
    fill: StrictBool = True

    _limits_ok = field_validator("limits")(_finite_limits)


def _scenario_mix(weights: dict, name: str) -> dict[str, float]:
    for ticker in weights:
        if ticker not in UNIVERSE_TICKERS:
            raise ApiError(422, f"{_echo(ticker)} is not in the dataset. Pick one of the {len(UNIVERSE_TICKERS)} tickers.")
    total = sum(weights.values())
    if not weights or abs(total - 1) > 0.005:
        raise ApiError(422, f"The weights of the {name} add up to {total * 100:.0f} %; they must add up to 100 %.")
    return {ticker: weight / total for ticker, weight in weights.items()}


@router.post("/api/scenario")
def scenario(body: ScenarioBody):
    """Lane sc-b, "Build your own shock": what one made-up shock vector would do to the mix (tools.factors.custom).
    {portfolio (the mix the scenario is about), baseline (today's mix, optional), limits {floor}, amount, as_of,
    shocks {factor id: fraction; rates 0.01 = 1 point}, fill (the factors not given move with the given ones)} -> the
    shape of one result.scenarios preset. An unknown factor, a move past 3 times the factor's largest measured move or
    weights that do not add up is 422 in plain words; no starter data on this machine is 503."""
    from tools import factors                               # noqa: PLC0415 (loaded when the section first asks)
    after = _scenario_mix(body.portfolio, "portfolio")
    today = _scenario_mix(body.baseline, "baseline") if body.baseline is not None else None
    if body.as_of is not None:
        _check_as_of(body.as_of)
    floor = (body.limits or {}).get("floor")
    if floor is not None and (isinstance(floor, bool) or not isinstance(floor, (int, float)) or not -1 <= floor <= 0):
        raise ApiError(422, "The floor must be a fall between 0 % and −100 %, written as a fraction (−0.15).")
    try:
        answer = factors.custom(after, body.shocks, baseline=today, amount=body.amount, floor=floor, as_of=body.as_of,
                                fill_others=body.fill)
    except factors.ShockError as exc:
        raise ApiError(422, str(exc)) from None
    except (factors.FactorDataMissing, FileNotFoundError):
        raise ApiError(503, "The scenario engine needs the starter data on this machine.") from None
    return _json(answer)


@router.post("/api/record")
def store_record(body: RecordBody):
    """Ruling R6: one sealed decision record into the private, versioned vault (record_store.put_record), on the
    investor's own action. Storage off (no bucket, or EPICENTRE_DEMO=1) is 200 with status "off"; an AWS failure is
    502; a broken seal or an unusable record is 422. The body is capped like every body and is never logged."""
    try:
        answer = record_store.put_record(body.record, expected_sha256=body.sha256)
    except ValueError as exc:
        raise ApiError(422, str(exc)) from None
    return _json(answer, 502 if answer["status"] == "error" else 200)


@router.post("/api/scenario/read")
def scenario_read(body: ScenarioReadBody):
    """Lane sc-a: the investor's words about a made-up future -> explicit, editable factor shocks, each anchored to a
    measured precedent (agents/scenario_builder.read_scenario: the input guardrail, the advice gate, one Converse call
    whose picks code checks, the keyword reading on any failure). The words are never logged or stored."""
    from agents import scenario_builder                    # looked up per request: tests replace book_for
    if len(body.text) > MAX_TEXT:
        raise ApiError(422, "Keep the scenario under 2,000 characters.")
    for ticker in body.portfolio or {}:
        if ticker not in UNIVERSE_TICKERS:
            raise ApiError(422, f"{_echo(ticker)} is not in the dataset. Pick one of the {len(UNIVERSE_TICKERS)} tickers.")
    if body.as_of is not None:
        _check_as_of(body.as_of)
    try:
        book = scenario_builder.book_for(body.as_of or pipeline.DATASET_END)
    except scenario_builder.BookUnavailable as exc:
        raise ApiError(503, str(exc)) from None
    return _json(scenario_builder.read_scenario(body.text, body.portfolio, book=book,
                                                use_bedrock=os.environ.get(NO_BEDROCK_ENV) != "1"))


@router.post("/api/profile/read")
def profile_read(body: ProfileReadBody):
    """Lane profile-ai, the fifth profile "You": the investor's own words -> a checked fictional profile
    (agents/profile_reader.read_profile: code's real-account check, the input guardrail, the advice gate, one Converse
    call whose picks code checks, the keyword reading on any failure). Empty or too-long words are 422 in plain words.
    When Amazon Bedrock is off (EPICENTRE_NO_BEDROCK=1) or did not answer, the status is 503 and the body is still the
    whole answer, read by the keyword rules (ai "off" or "down"). The words are never logged or stored."""
    from agents import profile_reader                      # looked up per request, like the scenario reader
    try:
        answer = profile_reader.read_profile(body.text, use_bedrock=os.environ.get(NO_BEDROCK_ENV) != "1")
    except ValueError as exc:
        raise ApiError(422, str(exc)) from None
    return _json(answer, 503 if answer.get("ai") in ("off", "down") else 200)


@router.get("/api/pilots")
def pilots():
    data = _read_json(PERSONAS_PATH)
    if not (isinstance(data, dict) and isinstance(data.get("pilots"), dict) and isinstance(data.get("storm_cards"), dict)):
        raise ApiError(503, MSG_NO_PILOTS)
    return _json({"pilots": data["pilots"], "storm_cards": data["storm_cards"]})


@router.get("/api/wire")
def wire():
    items = _read_json(WIRE_PATH)
    return _json({"items": items[:8] if isinstance(items, list) else []})


_health_lock = threading.Lock()
_health_cache: dict[str, Any] = {}


def _now() -> float:
    return time.monotonic()


def clear_health_cache() -> None:
    with _health_lock:
        _health_cache.clear()


def _holdings_usable() -> bool:
    """The ETF holdings file can be looked through for this replay: tools.lookthrough's own rule decides (the mode is
    a property of the file, so one equity ETF of the universe asks it); a snapshot dated after the replay's last day,
    no file or no data is direct mode (red gate 3). The live page says so in one line when this is False."""
    try:
        from tools import lookthrough
        return lookthrough.look_through({"XIU.TO": 1.0})["mode"] == "lookthrough"
    except Exception:
        return False


def _deep_panel() -> bool:
    """The deep-history panel is where result_extras looks for it (data/cache/deep, or $EPICENTRE_DEEP_PANEL)."""
    try:
        import result_extras
        return (result_extras.deep_dir() / "panel.csv").is_file()
    except Exception:
        return False


def health_payload() -> dict:
    """Five booleans, recomputed at most every HEALTH_TTL seconds. /api/health stays open when a password is set and
    the credential lookup takes 1-2 s with no credentials anywhere, so a burst makes one probe, not many."""
    with _health_lock:
        now = _now()
        if _health_cache and now - _health_cache["at"] < HEALTH_TTL:
            return _health_cache["payload"]
        try:
            bedrock = boto3.Session().get_credentials() is not None    # resolves the credential chain; no AWS API call
        except Exception:
            bedrock = False
        payload = {"data": STARTER_PRICES.exists(), "bedrock": bedrock, "guardrail": config.ENV_GUARDRAIL_ID in os.environ,
                   "holdings": _holdings_usable(), "deep": _deep_panel()}
        _health_cache.update(at=now, payload=payload)
        return payload


@router.get("/api/health")
def health():
    return _json(health_payload())


@router.get("/api/demo-run")
def demo_run(pilot: str | None = None):
    loader = getattr(pipeline, "default_demo_run", None)
    result = (loader(pilot) if pilot else loader()) if loader else None      # no investor asked: the default one (Robert)
    if not isinstance(result, dict):
        raise ApiError(404, MSG_NO_INVESTOR_RUN if pilot else MSG_NO_RUNS)
    RUNS.put(result)                              # the page's first paint must be rechecked like any other run
    return _json(_with_funds(result))


def create_app(web_dir: Path | None = WEB_DIR) -> FastAPI:
    if os.environ.get(REQUIRE_PASSWORD_ENV) == "1" and not os.environ.get(PASSWORD_ENV, ""):
        raise RuntimeError(MSG_NO_PASSWORD)           # ledger section 30 (a): deploy mode never starts open
    app = FastAPI(title="EPICENTRE", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_exception_handler(ApiError, on_api_error)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(StarletteHTTPException, on_http_error)
    app.include_router(router)
    if web_dir is not None and Path(web_dir).is_dir():        # mounted last: the API routes win
        if os.environ.get("EPICENTRE_LANDING") == "review" and (Path(web_dir) / "review.html").is_file():
            app.add_api_route("/", _review_landing, methods=["GET", "HEAD"], include_in_schema=False)
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    app.add_middleware(Guard)
    return app


def _review_landing():
    return RedirectResponse("./review.html", status_code=307)


app = create_app()
