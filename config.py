"""PREFLIGHT configuration: model ids and request fields, limits defaults, guardrail names, paths.

Constants plus a few tiny
readers of environment overrides, no other logic. UI design tokens live in web/styles.css, not here.
Sources: spec section 11 (models, boto3), section 7 (guardrail), section 5 (limits); plan B Task 1.
"""
import copy
import os
from pathlib import Path

from botocore.config import Config

# ---- region and models (spec section 11) ----
REGION = "us-east-1"
MODEL_ID = "us.anthropic.claude-sonnet-5-5"  # default for both language jobs
MODEL_ID_GLOBAL = "global.anthropic.claude-sonnet-5-5"  # only if the us. profile is refused
MODEL_ID_FALLBACK = "global.anthropic.claude-sonnet-5"  # Sonnet 5, verified 0.9 s
MODEL_ID_HAIKU = "us.anthropic.claude-haiku-5-5"  # eval-only (Task 11)
MODEL_ID_HAIKU_GLOBAL = "global.anthropic.claude-haiku-5-5"

# additionalModelRequestFields per model id. Never send temperature/topP or a forced toolChoice:
# both are HTTP 400 on Sonnet 5.5 (pitfall 3).
REQUEST_FIELDS: dict[str, dict] = {
    MODEL_ID: {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}},
    MODEL_ID_GLOBAL: {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}},
    MODEL_ID_FALLBACK: {"thinking": {"type": "disabled"}},
    MODEL_ID_HAIKU: {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}},
    MODEL_ID_HAIKU_GLOBAL: {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}},
}
MAX_TOKENS_SCENARIO = 1500  # the navigator; max_tokens counts thinking on Sonnet 5.5
MAX_TOKENS_EXPLAINER = 2000  # the debrief

# Anthropic list prices, USD per million tokens (input, output). Bedrock bills separately, so
# eval_results.md labels cost "estimate at list price".
PRICE_USD_PER_MTOK = {
    MODEL_ID: (2.00, 10.00),
    MODEL_ID_GLOBAL: (2.00, 10.00),
    MODEL_ID_FALLBACK: (2.00, 10.00),
    MODEL_ID_HAIKU: (0.10, 0.50),
    MODEL_ID_HAIKU_GLOBAL: (0.10, 0.50),
}
# The date and source of the price table above, for the Proof block's run cost (proofs.run_cost; no undated price claim).
# The table was entered on 2026-11-14 (commit 3a8074d) as the published list prices; the Amazon Bedrock on-demand
# pricing page, https://aws.amazon.com/bedrock/pricing/, read again on 2026-11-15, renders no per-token table in its
# text, so the cost stays labelled an estimate at list price (Bedrock bills separately).
PRICES_AS_OF = "2026-11-14"
PRICES_SOURCE = "List prices per million tokens, as entered on 2026-11-14 (aws.amazon.com/bedrock/pricing); an estimate"
CACHE_READ_MULT = 0.1  # a cache read costs 0.1 x the input price
CACHE_WRITE_MULT = 1.25  # a cache write costs 1.25 x the input price
# Smallest cacheable prompt prefix, in tokens (Anthropic caching table). Task 12's live canary is the
# proof before anyone claims caching.
MIN_CACHE_TOKENS = {
    MODEL_ID: 512,
    MODEL_ID_GLOBAL: 512,
    MODEL_ID_FALLBACK: 1024,
    MODEL_ID_HAIKU: 512,
    MODEL_ID_HAIKU_GLOBAL: 512,
}

# ---- navigator engine and budgets (spec sections 7 and 11) ----
SCENARIO_ENGINE = "converse"  # one Converse call over code-computed tool outputs (spec §24 res. 1); "strands" is not built
SCENARIO_MAX_TURNS = 4
SCENARIO_MAX_TOOL_CALLS = 4

# ---- environment variable names (identifiers, never secrets; nothing in git) ----
ENV_GUARDRAIL_ID = "EPICENTRE_GUARDRAIL_ID"
ENV_GUARDRAIL_VERSION = "EPICENTRE_GUARDRAIL_VERSION"
ENV_DEMO = "EPICENTRE_DEMO"
ENV_MODEL = "EPICENTRE_MODEL_ID"
_ENV_SCENARIO_ENGINE = "EPICENTRE_SCENARIO_ENGINE"  # strands | converse | loop
_ENV_JOB_MODEL = {"navigator": "EPICENTRE_NAVIGATOR_MODEL_ID", "debrief": "EPICENTRE_DEBRIEF_MODEL_ID"}


def request_fields(model_id: str) -> dict:
    """additionalModelRequestFields for a model id, as a deep copy (callers may change it freely)."""
    if model_id not in REQUEST_FIELDS:
        raise ValueError(f"No request fields for model id {model_id!r}; known ids: {sorted(REQUEST_FIELDS)}")
    return copy.deepcopy(REQUEST_FIELDS[model_id])


def current_model_id() -> str:
    """EPICENTRE_MODEL_ID when set and not empty, else MODEL_ID."""
    return os.environ.get(ENV_MODEL) or MODEL_ID


def model_for(job: str) -> str:
    """The model id for a job, "navigator" or "debrief": its own env override, else current_model_id()."""
    if job not in _ENV_JOB_MODEL:
        raise ValueError(f"Unknown job {job!r}; expected one of {sorted(_ENV_JOB_MODEL)}")
    return os.environ.get(_ENV_JOB_MODEL[job]) or current_model_id()


def scenario_engine() -> str:
    """EPICENTRE_SCENARIO_ENGINE when it is "strands", "converse" or "loop" (exact names), else SCENARIO_ENGINE."""
    value = os.environ.get(_ENV_SCENARIO_ENGINE)
    return value if value in ("strands", "converse", "loop") else SCENARIO_ENGINE


def boto_config() -> Config:
    """botocore client config of spec section 11: adaptive retries x3, connect 5 s, read 30 s, us-east-1."""
    return Config(region_name=REGION, retries={"mode": "adaptive", "max_attempts": 3},
                  connect_timeout=5, read_timeout=30)


# ---- guardrail (spec section 7) ----
GUARDRAIL_NAME = "epicentre-guardrail"
LEGACY_GUARDRAIL_NAMES = ("preflight-guardrail",)  # scripts/create_guardrail.py finds it and renames it in place
GUARDRAIL_PROFILE = "us.guardrail.v1:0"  # cross-Region profile (Standard tier)
GROUNDING_THRESHOLD = RELEVANCE_THRESHOLD = 0.7
QUERY_MAX_CHARS = 1000  # OUTPUT check: the `query` block is cut to this
GROUNDING_MAX_CHARS = 20000  # OUTPUT check: the `grounding_source` block (the facts JSON)
GUARD_CONTENT_MAX_CHARS = 5000  # OUTPUT check: the `guard_content` block (the debrief text)
INPUT_MAX_CHARS = 5000  # INPUT check: longer text is refused, not cut (the tail would go unchecked)

# ---- words the product uses ----
DISCLAIMER = "Educational simulation. This is not financial advice."
FAMILIES = ("tariffs", "war_oil", "chips", "rates")
FAMILY_LABELS = {"tariffs": "Tariff war", "war_oil": "War & oil", "chips": "Chip war", "rates": "Rate shock"}
VERDICT_WORDS = {
    "Compatible": "Inside your limits",
    "Tension": "Inside, with caveats",
    "Incompatible": "Outside your limits",
    None: "Limits missing",
}

# ---- rules and limits (spec section 5; ledger section 0). Limits are read through governance.load_limits,
# which takes data/personas.json first and falls back to these defaults key by key. ----
RULE_IDS = (
    "max_drawdown", "scenario_stress", "single_stock", "sector", "crypto", "esg_direct", "esg_indirect",
    "risk_concentration", "recovery", "short_horizon", "missing_data",
)
DEFAULT_LIMITS = {
    "high": {"max_drawdown": -0.45, "max_single_stock": 0.20, "max_sector": 0.40, "max_crypto": 0.10},
    "moderate": {"max_drawdown": -0.25, "max_single_stock": 0.10, "max_sector": 0.35, "max_crypto": 0.0},
    "low": {"max_drawdown": -0.15, "max_single_stock": 0.10, "max_sector": 0.30, "max_crypto": 0.0},
}
DEFAULT_THRESHOLDS = {
    "scenario_stress_fraction": 0.5,  # scenario stress limit = this x the drawdown floor
    "esg_indirect_warn": 0.01,  # warn when flagged names inside ETFs reach this share of the portfolio
    "rounding_pp": 0.1,  # compare after rounding to 0.1 percentage point
    "recovery_fraction_of_horizon": 0.3333,  # recovery limit = horizon x this x 365 calendar days
    "short_horizon_years": 3,  # warn when the money is needed in fewer years than this
    "risk_share_warn": 0.5,  # warn when one line carries more than this share of the portfolio's risk
}
REACTION_TO_RISK = {"sold": "low", "held": "moderate", "bought": "high"}  # "In 2022, when markets fell, you..."

# ---- paths ----
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STARTER_DIR = DATA_DIR / "starter"  # gitignored, licence
EVENTS_CSV = DATA_DIR / "events.csv"
PERSONAS_JSON = DATA_DIR / "personas.json"
ESG_FLAGS_CSV = DATA_DIR / "esg_flags.csv"
ETF_HOLDINGS_CSV = DATA_DIR / "etf_holdings.csv"  # local only, issuers forbid redistribution
WIRE_SOURCES_JSON = DATA_DIR / "wire_sources.json"
DEMO_RUNS_DIR = DATA_DIR / "demo_runs"
CACHE_DIR = DATA_DIR / "cache"  # gitignored
WIRE_CACHE = CACHE_DIR / "wire.json"
EVAL_RESULTS_MD = ROOT / "docs" / "eval_results.md"

COLORS = {}  # deprecated: UI tokens live in web/styles.css
