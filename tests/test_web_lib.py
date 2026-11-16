"""The pure helpers of the page run under node (web/lib.js: request body, debrief sections, block order, tokens; and every
lane's tests/web_*_test.cjs / tests/web_*_test.mjs, INTERFACES.md), plus static guards on the page's scripts: the Replay's
web/app.js, web/state.js and web/data.js (lane U0), and the frozen classic page web/classic.js (today's page before the Replay,
kept until the integrated page passes review)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE_TESTS = sorted(p.name for pat in ("web_*_test.cjs", "web_*_test.mjs") for p in (ROOT / "tests").glob(pat))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_web_lib_helpers_under_node():
    subprocess.run(["node", "tests/web_lib_test.cjs"], check=True, cwd=ROOT)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("script", [n for n in NODE_TESTS if n != "web_lib_test.cjs"])
def test_every_lane_node_test(script):
    """INTERFACES.md: every lane's pure-helper tests run under node from here (a non-zero exit fails)."""
    done = subprocess.run(["node", f"tests/{script}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, (done.stdout[-2000:], done.stderr[-2000:])


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_result_without_a_move_is_drawable(tmp_path):
    """C1: the real pipeline sends series.after, baseline and tipping_point as null for a question that changes nothing;
    the page's helper gives it a second path so no chart dereferences null."""
    import json
    import sys

    sys.path.insert(0, str(ROOT / "tests"))
    import pipeline
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine

    def no_move(*a, **k):
        return {**fake_engine().keyword_fallback(*a, **k), "type": "shock", "change": None, "portfolio": None}

    r = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine(keyword_fallback=no_move), use_bedrock=False)
    assert r["series"]["after"] is None and r["baseline"] is None and r["tipping_point"] is None
    path = tmp_path / "no_change.json"
    path.write_text(json.dumps(pipeline.jsonable(r)), encoding="utf-8")
    subprocess.run(["node", "tests/web_lib_test.cjs", str(path)], check=True, cwd=ROOT)


# ---- static guards on the classic page's script (web/classic.js, the page before the Replay, frozen): the structure that keeps
# one judge and plain errors (the behaviour is run in a browser) ----
import re

APP = (ROOT / "web" / "classic.js").read_text(encoding="utf-8")


def _body(name: str) -> str:
    """The text of `function name(...) { ... }` (braces counted; template `${}` pairs balance)."""
    start = APP.index(f"function {name}(")
    depth, i = 0, APP.index("{", start)
    for j in range(i, len(APP)):
        depth += {"{": 1, "}": -1}.get(APP[j], 0)
        if depth == 0:
            return APP[start:j + 1]
    raise AssertionError(f"function {name} is not closed")


def test_the_browser_never_judges():
    """Red gate 2 / ledger l.58: governance.verdict is the one judge. W-S1 removed the fake-mode copies of the tier logic
    (applyStormCheck, verdictOf, recheckLocal): no page code computes a check, a status or a verdict, in any mode. The verdict
    enum appears only in lib.js's word maps; app.js never names it; no status literal is ever assigned."""
    lib = (ROOT / "web" / "lib.js").read_text(encoding="utf-8")
    for name in ("applyStormCheck", "verdictOf", "recheckLocal", "curveVerdict"):
        assert name + "(" not in APP and name + "(" not in lib, name
    assert not re.search(r"\b(Compatible|Tension|Incompatible)\b", APP)
    hits = [ln.strip() for ln in lib.splitlines() if re.search(r"\b(Compatible|Tension|Incompatible)\b", ln)]
    assert hits and all("word:" in ln or ln.startswith("const HERO") or ln.startswith(("/*", "//", "*")) for ln in hits), hits
    assert not re.search(r"""status\s*[:=]\s*["'](pass|fail|warn)["']""", APP + lib)


def test_a_failed_run_gives_the_focus_back_to_run():
    """D Task 5 re-review r1 (3): one failure path; after it the focus is back on Run."""
    run = _body("startRun")
    assert 'const btn = $("#run")' in run and "btn.focus()" in run[run.index("const fail = "):run.index("const done = ")]


def test_no_label_reads_page_state():
    """D Task 5 re-review r1 (5): no label next to a server number reads page state (the old plan.asked); the shock family
    comes from the Result's scenario.families (PF.view(r).shockFamily, node-tested)."""
    assert not re.search(r"\.asked\b|\basked\s*[:=]", APP)        # no page-state field named after the old plan.asked


def test_no_exception_text_reaches_the_user():
    """I4: a caught exception's message is never shown; only tagged plain sentences are (PF.failureLine)."""
    allowed = ("window.__errors.push(String(e.message))",)         # the hidden error log, never rendered
    hits = [ln.strip() for ln in APP.splitlines() if re.search(r"\b(e|e2|err|ex|exc|error)\.message\b", ln) and not any(a in ln for a in allowed)]
    assert hits == [], hits
    assert "String(e.message)" not in APP.replace(allowed[0], "")
    assert "PF.failureLine(err)" in APP and "PF.failureLine(r)" in APP


def test_a_failed_run_keeps_the_last_result():
    """I3: an error Result and a render failure both go through fail(), which restores this investor's last good Result."""
    run = _body("startRun")
    assert 'r.status === "error"' in run and "fail(PF.failureLine(r))" in run
    assert "const last = PF.lastGood(S.last, S.pid);" in run and re.search(r"if \(last\) \{ try \{ S\.r = last;", run)
    assert "S.r = bridge(r)" in run and "catch (e) { console.error(e); fail(PF.failureLine(e)); }" in run


def test_no_move_labels_are_conditional():
    """C1: every 'with the move' text goes through withMove(r) / moveOf(r), so a question without a move never says it."""
    for line in APP.splitlines():
        if "with the move" in line and "withMove" not in line and "moveOf" not in line and "mv" not in line:
            assert re.search(r"^\s*(/\*|//)|\* ", line) or "Built by code" in line or "Worst drop with the move" in line, line.strip()[:140]


def test_the_browser_never_prices_a_dollar_or_decides_a_breach():
    """W-S1 fix round 1, I1 (ruling R18; board resolution 9, one value per fact; pitfall 5): every dollar the page prints is a
    Result key (PF.view reads kpis.*.loss_dollars, breaches[].loss_dollars, limits.capacity_dollars; node-tested). The page code
    never multiplies by the amount (one exception: the five questions turn a percent answer into the capacity they send),
    the fall chart prints no computed dollar (its readout is in percent) and the hatch is the Result's below_floor."""
    lib = (ROOT / "web" / "lib.js").read_text(encoding="utf-8")
    hits = [ln.strip() for ln in lib.splitlines() if re.search(r"\bamount\s*\*|\*\s*amount\b", ln)]
    assert hits == ['const capacity = a.unit === "%" ? (isNum(amount) ? Math.round(amount * loss) / 100 : NaN) : loss;'], hits
    assert not re.search(r"\bamount\s*\*|\*\s*amount\b", APP)
    assert "fmt.money(" not in APP                            # no dollar formatted from a page value
    fall = APP[APP.index("function drawFall("):APP.index("function renderThesis(")]   # drawFall + finishFall
    assert "P.hatch" in fall and not re.search(r"<\s*P\.floor\b|P\.floor\s*>", fall)
    assert "PF.fmt.pct(val)" in fall and "v.floor.label" in fall
    assert set(re.findall(r"\b\w+\.dollarsText\b", fall)) == {"side.dollarsText", "b.dollarsText"}   # the Result's own dollars


def test_a_failed_run_never_shows_another_investors_answer():
    """W-S1 fix round 1, I2: S.last is kept per investor and only the tab's own comes back (PF.lastGood, node-tested); the
    question box is written on a tab change, at load and by the hero's replay, never after a run (a blocked, clarify or
    failed answer keeps the typed words)."""
    assert "last: {}," in APP and not re.search(r"S\.last\s*=[^=]", APP)       # never one global Result
    assert set(re.findall(r"S\.last(\[\w+(?:\.\w+)?\]|\.\w+)\s*=[^=]", APP)) == {"[S.pid]", "[pid]", ".robert"}
    writes = [ln.strip() for ln in APP.splitlines() if re.search(r"#q\"\)\.value\s*=|\bq\.value\s*=", ln)]
    assert writes == ['$("#q").value = (src && src.question) || "";'], writes
    calls = [ln.strip() for ln in APP.splitlines() if "fillQuestion(" in ln and "function fillQuestion" not in ln]
    assert len(calls) == 3 and "fillQuestion(pid);" in calls[0], calls      # select, the hero's replay, init
    assert "fillQuestion" not in _body("renderCard") and "fillQuestion" not in _body("startRun")


def test_a_static_replay_keeps_its_runs_commit():
    """W-S1 fix round 1, I3: the replayed copy of a saved run keeps the commit runs/index.json names for it (the COMMIT map
    is keyed by the object; structuredClone made a new one, so the label fell back to the page's commit)."""
    run = _body("startRun")
    assert "COMMIT.set(replay, COMMIT.get(saved))" in run and "done(replay)" in run and "done(structuredClone(" not in run


def test_fix_round_1_minors():
    """W-S1 review minors 4, 8, 10: no clip at rest on the swept paths; a shock's line only for a fall (a rise never reads as
    one); APG tabs (Home, End); the run log's state in words; the card reads the run of your own answers' limits."""
    css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    globe = (ROOT / "web" / "classic-globe.js").read_text(encoding="utf-8")       # the classic page's globe (web/globe.js is U1's)
    assert not re.search(r"^\.reveal\s*\{", css, re.M)
    assert "e.trough < 0" in globe and "e.trough < 0" in _body("drawRings")
    assert "Home: 0, End: tabs.length - 1" in APP
    assert 'ic.setAttribute("aria-label", LOG_WORD[st])' in _body("onProgress")
    assert "r === S.custom.result" in _body("investorSource") and "S.custom.result = S.r" in _body("startRun")


# ---- the Replay's foundation (lane U0; INTERFACES.md, design doc §4): web/app.js, web/state.js, web/data.js, web/index.html ----
NEW = {n: (ROOT / "web" / n).read_text(encoding="utf-8") for n in ("app.js", "state.js", "data.js")}
SECTIONS = ["bar", "hero", "replay", "why", "testai", "money", "checklist", "investors", "how", "deep", "scenario", "record", "footer"]


def test_the_replay_foundation_never_judges_and_never_writes_html():
    """Red gate 2 (one judge: the server): the Replay's boot, store and data layer name no verdict word, decide no status and
    write no HTML; they talk only to the page's own API and its saved runs (no remote host), never to the FAKE sample files."""
    src = "\n".join(NEW.values())
    assert not re.search(r"\b(Compatible|Tension|Incompatible)\b", src)
    assert not re.search(r"""status\s*[:=]\s*["'](pass|fail|warn)["']""", src)
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", src)
    assert not re.search(r"https?://", src)
    assert not re.search(r"fake_(result|extras)|story-data", src)
    assert not re.search(r"\bamount\s*\*|\*\s*amount\b", src)                  # no dollar is priced in the browser


def test_the_store_and_the_data_layer_keep_the_interfaces():
    """INTERFACES.md: store.get/set/on; loadRun, runLive, recompute; the static build's runs/<id>.json, the live server's
    /api/demo-run, /api/run (NDJSON) and /api/recompute {run_id, id}; the mode from the static meta or GET /api/health."""
    s, d = NEW["state.js"], NEW["data.js"]
    assert "export const store" in s and all(f"  {m}(" in s for m in ("get", "set", "on"))
    for name in ("loadRun", "runLive", "recompute", "detectMode", "land", "peekRun"):
        assert re.search(rf"export (async )?function {name}\(", d), name
    for needle in ("site(`runs/${encodeURIComponent(investor)}.json`)", 'site("runs/index.json")', "import.meta.url", "/api/demo-run?pilot=", '"/api/run"',
                   '"/api/recompute"', '"/api/health"', 'meta("mode") === "static"', "run_id: runId, id"):
        assert needle in d, needle
    code = re.sub(r"/\*.*?\*/|(?<![:\\])//[^\n]*", "", d, flags=re.S)
    assert code.count("store.set(") == 1 and "store.set({ ...(extra || {}), result: result || null, view: viewOf(result)" in code   # one writer


def test_sections_mount_in_try_catch_and_the_page_never_blanks():
    """Brief U0 item 3: every web/sections/<name>.js named by index.html is imported and mounted in try/catch; a missing or
    throwing one is logged and skipped; errors are kept in window.__errors; window.__epi = {store, ready()}."""
    app = NEW["app.js"]
    assert "import(`./sections/${name}.js`)" in app and 'querySelectorAll("[data-module]")' in app
    body = app[app.index("function mountOne("):app.index("const wait =")]
    assert "try {" in body and "mount(el, store)" in body and "catch (e)" in body and "failed(e)" in body
    assert "window.__errors" in app and "console.error = " in app and '"unhandledrejection"' in app
    assert "window.__epi = {" in app and "ready: () => readyPromise" in app
    assert 'store.on("investor"' in app and "EPI_MOTION" in app


def test_index_has_every_section_in_the_design_doc_order():
    """Design doc §2 + R5 (#deep after #money) + R6 (#record after #how): one mount point per section, in page order, lib.js as a
    classic deferred script before app.js (a module), the marker sprite, the disclaimer, no inline script."""
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert re.findall(r'data-module="(\w+)"', html) == SECTIONS[:3] + ["agentlog"] + SECTIONS[3:]   # R42's log rides in the stage
    assert re.findall(r'<(?:section|header|footer)[^>]*\bid="(\w+)"', html) == SECTIONS
    assert html.index('<script src="lib.js" defer></script>') < html.index('<script type="module" src="app.js"></script>')
    assert all(f'<symbol id="{s}"' in html for s in ("m-fact", "m-assumption", "m-fiction", "i-in", "i-warn", "i-out"))
    assert "Educational simulation. This is not financial advice." in html
    assert "classic" not in html                                                   # nothing links to the classic page


def test_the_web_fixtures_are_public_cuts():
    """Ruling R17: lanes pin values on tests/fixtures/web/<investor>.json (scripts/web_fixtures.py), the public cut of the four
    saved real runs through the static build's own function: present, the right investor, leak-free, already cut (idempotent)."""
    import json
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import record_demo

    for name in ("robert", "mateo", "amira", "canadian"):
        r = json.loads((ROOT / "tests" / "fixtures" / "web" / f"{name}.json").read_text(encoding="utf-8"))
        assert r["pilot"] == name and r["status"] == "ok" and "figures" not in r
        assert record_demo.find_leaks(r) == [], name
        assert record_demo.public_result(r) == r, name
    loader = (ROOT / "tests" / "web_fixtures.mjs").read_text(encoding="utf-8")
    assert "export function load(name)" in loader and "fixtures/web/" in loader


def test_presenter_keys():
    """Ruling R19e: 1-9 jump to the beats in the page's order, R replays the stage (store.replay), Esc ends the motion until the next
    replay; ignored while typing or with a modifier; the reminder only with ?presenter=1; documented in the README."""
    app = NEW["app.js"]
    assert 'const BEATS = ["hero", "replay", "why", "money", "investors", "how", "deep", "scenario", "record"];' in app
    body = app[app.index("function onPresenterKey("):app.index("function presenterHint(")]
    assert "typing(e.target)" in body and "e.ctrlKey" in body and "e.metaKey" in body and "e.defaultPrevented" in body
    assert "store.set({ replay: Date.now() })" in body and "window.EPI_MOTION = false" in body and "smooth" not in body
    assert 'params.get("presenter") === "1"' in app and 'addEventListener("keydown", onPresenterKey)' in app
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "**Presenter keys**" in readme and "?presenter=1" in readme


def test_every_saved_result_says_when_it_was_recorded():
    """R15 ("recorded on <date>", for U6 and U7b): the recording step stamps result.recorded_at (ISO, Eastern time) before
    pipeline.save_run, the static build gives an older saved file its own saved_at in Eastern time, and the public cut keeps it."""
    import json
    import re as _re
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import record_demo

    assert record_demo.recorded_at("2026-11-15T20:02:11+00:00") == "2026-11-15T15:02:11-05:00"     # EST in November
    assert _re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-0[45]:00", record_demo.recorded_at())
    src = (ROOT / "scripts" / "record_demo.py").read_text(encoding="utf-8")
    one = src[src.index("def _record_one("):src.index("def _copy_default(")]
    assert one.index('ready["recorded_at"] = recorded_at()') < one.index("pipeline.save_run(ready")
    fixture = json.loads((ROOT / "tests" / "fixtures" / "web" / "robert.json").read_text(encoding="utf-8"))
    saved = {"key": "0123456789abcdef", "saved_at": "2026-11-15T20:02:11+00:00", "result": dict(fixture), "_analysis": None,
             "question": fixture["question"], "as_of": fixture["as_of"]}
    assert record_demo._replayed(saved)["recorded_at"] == "2026-11-15T15:02:11-05:00"
    kept = {**fixture, "recorded_at": "2026-11-15T15:00:00-05:00"}
    saved = {**saved, "result": dict(kept)}
    assert record_demo._replayed(saved)["recorded_at"] == "2026-11-15T15:00:00-05:00"             # its own stamp wins
    assert record_demo.public_result(kept)["recorded_at"] == "2026-11-15T15:00:00-05:00"


def test_the_pages_publisher_builds_the_public_cut_from_saved_results(tmp_path, monkeypatch):
    """scripts/publish_pages.py (the GitHub Pages demo): --runs wraps saved real Results as saved runs in a temporary folder,
    the static build makes runs/<investor>.json from them (replays, public cut), and publishing is a plain push of a commit on
    top of gh-pages (never a force push)."""
    import json
    import shutil
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import pipeline
    import publish_pages
    import record_demo

    runs = tmp_path / "runs"
    runs.mkdir()
    for name in ("robert", "mateo", "amira", "canadian"):
        shutil.copyfile(ROOT / "tests" / "fixtures" / "web" / f"{name}.json", runs / f"{name}.json")
    demo = tmp_path / "demo"
    publish_pages.wrap_runs(runs, demo)
    saved = [json.loads(p.read_text()) for p in sorted(demo.glob("*.json"))]
    assert len(saved) == 4 and all(s["data"] == "REAL" and len(s["commit"]) == 40 and len(s["key"]) == 16 for s in saved)
    assert {s["key"][:12] for s in saved} == {s["result"]["run_id"] for s in saved}          # the replay keeps each run's id
    monkeypatch.setattr(pipeline, "DEMO_DIR", demo)
    site = record_demo.build_static(tmp_path / "site")
    for name in ("robert", "mateo", "amira", "canadian"):
        r = json.loads((site / "runs" / f"{name}.json").read_text())
        assert r["pilot"] == name and r["mode"] == "demo_replay" and r["recorded_at"].endswith(("-05:00", "-04:00"))
    src = (ROOT / "scripts" / "publish_pages.py").read_text(encoding="utf-8")
    assert '"push", "-q", "origin", f"HEAD:{BRANCH}"' in src and "--force" not in src and "-f\"" not in src


def test_the_scenario_section_is_time_boxed_behind_its_flag():
    """Ruling R21: #scenario ("Build your own shock") sits after #deep (before #record in the 14:30 order), mounts only while window.EPI_SCENARIO is not false
    (?scenario=0 or SCENARIO_ON = false ships it off), and its stylesheet is linked only then: off means no request at all."""
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '<section id="scenario" data-module="scenario" data-flag="EPI_SCENARIO" data-css="css/scenario.css"' in html
    assert html.index('id="deep"') < html.index('id="scenario"') < html.index('id="record"')          # the 14:30 order
    assert 'href="css/scenario.css"' not in html and 'sections/scenario.js' not in html          # never fetched while off
    app = NEW["app.js"]
    assert "const SCENARIO_ON = true;" in app and 'params.get("scenario") === "0"' in app
    starts = app[app.index("function startImports("):app.index("async function mountAll(")]
    assert "flaggedOff(el)" in starts and 'el.dataset.mount = "off"' in starts and "sectionCss(el)" in starts


def test_r22_simple_detailed_switch_and_the_tour():
    """Ruling R22 (lane U0's page-level pieces): store.depth ("simple" default | "detailed", ?depth=detailed) set by one switch in
    the bar; "Take the tour" after the hero's command bar and on key T: it presses Replay, follows the stage to its end
    frame, glides the sections with ONE caption line (no meta dots), stops on any key, wheel, touch or click, and under reduced
    or paused motion shows the captions without auto-scrolling."""
    depth = (ROOT / "web" / "depth.js").read_text(encoding="utf-8")
    tour = (ROOT / "web" / "tour.js").read_text(encoding="utf-8")
    state = (ROOT / "web" / "state.js").read_text(encoding="utf-8")
    app = NEW["app.js"]
    assert 'depth: "simple",' in state and 'params.get("depth") === "detailed"' in depth and "store.set({ depth: value })" in depth
    assert 'querySelector("#bar .bar-end")' in depth and "mountDepth(store)" in app and "initialDepth(params)" in app
    assert 'store.set({ replay: Date.now() })' in tour and 'phaseIs("landed")' in tour
    assert all(t in tour for t in ('"keydown"', '"wheel"', '"touchmove"', '"pointerdown"'))
    assert "if (!motionOn()) return Promise.resolve();" in tour                      # reduced or paused: captions only
    ids = re.findall(r'\{ id: "(\w+)"', tour)
    assert ids == ["replay", "replay", "why", "money", "investors", "how", "deep", "scenario", "record"]
    assert " · " not in tour and 'e.key === "t" || e.key === "T"' in app and "tour.start()" in app


def test_the_public_demo_url_is_one_constant_on_window():
    """The footer's QR and share links read window.EPI_PUBLIC_URL; app.js sets it from lane U7b's PUBLIC_URL (lib/how.js), the
    GitHub Pages demo, never a live endpoint (R8)."""
    how = (ROOT / "web" / "lib" / "how.js").read_text(encoding="utf-8")
    assert 'export const PUBLIC_URL = "https://shmorsi.github.io/poly-datathon-2026/";' in how
    assert 'import { PUBLIC_URL } from "./lib/how.js";' in NEW["app.js"] and "window.EPI_PUBLIC_URL = PUBLIC_URL;" in NEW["app.js"]


def test_the_step_rail_and_the_answer_chip():
    """The direction research and the cold usability test (Sun 15 Nov): the bar names the workshop's method plus our check
    (Observe, Understand, Compare, Explain, Verify) and More; the stage is Understand while it reads and Compare once the race
    starts; the answer chip appears only after a replay has landed, in the stage's own words (lib/replay.js pillOf: a what-if
    size is never a verdict and never green, R20), and a press goes back to the stage."""
    rail = (ROOT / "web" / "rail.js").read_text(encoding="utf-8")
    labels = re.findall(r'\{ key: "(\w+)", label: "(\w+)", target: "(\w+)" \}', rail)
    assert labels == [("observe", "Observe", "hero"), ("understand", "Understand", "replay"), ("compare", "Compare", "money"),
                      ("explain", "Explain", "why"), ("verify", "Verify", "how")]
    assert re.findall(r'target: "(\w+)" \}', rail[rail.index("export const MORE"):rail.index("export const STEP_OF")]) == ["investors", "deep", "scenario"]
    assert 'import { pillOf } from "./lib/replay.js";' in rail and 'if (st.phase === "landed") landedOnce = true;' in rail
    assert 'setAttribute("aria-current", "step")' in rail and '["flying", "racing", "landed"].includes(phase) ? "compare" : "understand"' in rail
    assert " · " not in rail and "mountRail(store)" in NEW["app.js"]


def test_the_extra_recordings_ship_only_with_their_meta(tmp_path, monkeypatch):
    """publish_pages.add_extras: data/demo_runs/{moves,tests}.json, when present, go to runs/ in the public cut (a Result inside
    is cut like a saved run), checked for leaks and credentials, each with <meta name="epicentre-<name>"> so the page fetches it
    only when it is there; without the files nothing is added (no 404). #testai is mounted right after #why behind EPI_TESTAI."""
    import json
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import pipeline
    import publish_pages
    import record_demo

    demo = tmp_path / "demo"
    demo.mkdir()
    monkeypatch.setattr(pipeline, "DEMO_DIR", demo)
    monkeypatch.setattr(publish_pages, "ROOT", tmp_path)                       # no repo files leak into the test
    site = tmp_path / "site"
    (site / "runs").mkdir(parents=True)
    (site / "index.html").write_text("<html><head><title>x</title></head><body></body></html>", encoding="utf-8")
    assert publish_pages.add_extras(site) == [] and "epicentre-moves" not in (site / "index.html").read_text()
    fixture = json.loads((ROOT / "tests" / "fixtures" / "web" / "robert.json").read_text(encoding="utf-8"))
    (demo / "moves.json").write_text(json.dumps({"moves": [{"label": "NVIDIA to 20 %", "result": fixture}]}), encoding="utf-8")
    (demo / "tests.json").write_text(json.dumps({"tests": [{"id": "fr01", "text": "Et si", "ok": True}]}), encoding="utf-8")
    assert publish_pages.add_extras(site) == [("moves", "runs/moves.json"), ("tests", "runs/tests.json")]
    page = (site / "index.html").read_text()
    assert '<meta name="epicentre-moves" content="runs/moves.json">' in page and '<meta name="epicentre-tests" content="runs/tests.json">' in page
    moved = json.loads((site / "runs" / "moves.json").read_text())["moves"][0]["result"]
    assert moved == record_demo.public_result(fixture) and record_demo.find_leaks(moved) == []
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert html.index('id="why"') < html.index('id="testai"') < html.index('id="money"') and 'data-flag="EPI_TESTAI"' in html


def test_every_verdict_carries_the_standing_line_and_inside_is_no_approval_green():
    """The regulation flaw hunter (CRITICAL, Sun 15 Nov): one standing line under every verdict (lib/status.js standingLine: the
    stage, the answer chip's tooltip, #checklist's recheck, #record, the investors cards, the money ladder), and Inside in a calm
    blue-grey token, never an approval green (contrast is pinned by tests/test_web_static.py)."""
    status = (ROOT / "web" / "lib" / "status.js").read_text(encoding="utf-8")
    assert 'export const STANDING_LINE = "This compares what the move already did with the limits shown here. It does not say whether to make it.";' in status
    for f in ("sections/replay.js", "sections/record.js", "sections/investors.js", "sections/checklist.js", "sections/money.js", "rail.js"):
        src = (ROOT / "web" / f).read_text(encoding="utf-8")
        assert "standingLine" in src and "lib/status.js" in src, f
    css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    root = dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)))
    assert root["clear"].strip() == root["status-ok"].strip() == "#8FA9C4"
    r, g, b = (int(root["clear"].strip()[i:i + 2], 16) for i in (1, 3, 5))
    assert b > g > r                                                            # blue-grey: no green dominance


def test_a_sealed_record_keeps_each_limits_real_source():
    """limits-QA (Sun 18:00): a "You" record (or any run that is not one of the four personas) keeps each limit's real source:
    typed by you when edited, from your words when the profile reader read it, assumed otherwise; personas stay assumed."""
    rec = (ROOT / "web" / "lib" / "record.js").read_text(encoding="utf-8")
    assert 'export const FROM_WORDS = "from your words";' in rec
    assert '["robert", "mateo", "amira", "canadian"].includes(str(r.pilot))' in rec
    assert "edited.includes(k) ? TYPED : words.includes(k) ? FROM_WORDS : persona ? ASSUMED : ASSUMED_DEFAULT" in rec
