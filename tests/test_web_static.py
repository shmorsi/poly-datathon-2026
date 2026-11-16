"""Static checks on web/: no data innerHTML, no network, banned words, the design tokens, fonts, markers and motion rules.
Plan W W1a (spec §22). Later website tasks append their own checks here and reuse first_root() and visible_strings()."""
import re
from pathlib import Path

WEB = Path("web")


def read(*names): return "\n".join((WEB / n).read_text(encoding="utf-8") for n in names)
def all_js(): return "\n".join(p.read_text(encoding="utf-8") for p in sorted(WEB.glob("*.js")))
def all_css(): return "\n".join(p.read_text(encoding="utf-8") for p in sorted(WEB.glob("*.css"), key=lambda p: (p.name != "styles.css", p.name)))   # tokens first
def first_root(css): return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)))


def visible_strings():
    html = read("index.html")
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S)
    attrs = re.findall(r'(?:aria-label|title|placeholder|alt|content)="([^"]*)"', html)
    lits = [m.group(2) for m in re.finditer(r"([\"'`])((?:\\.|(?!\1).)*)\1", all_js())]
    return [text, *attrs, *[l for l in lits if " " in l and not l.startswith(("/api/", "./", "vendor/"))]]   # identifiers have no space


def test_no_innerhtml_and_no_network_anywhere():
    for p in [*WEB.glob("*.js"), *WEB.glob("*.css"), WEB / "index.html", WEB / "classic.html"]:
        t = p.read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML", t), p.name
        assert not re.search(r"""(?:src|href)=["']https?://|url\(\s*['"]?https?://|(?:fetch|import)\(\s*['"`]https?://""", t), p.name


ADVICE = re.compile(r"\b(buy|sell|hold|you should|we recommend|recommended)\b", re.I)


def test_banned_words_and_tells():
    vis = visible_strings()
    assert sorted({m.group(0).lower() for s in vis for m in ADVICE.finditer(s)}) == []
    assert [s for s in vis if " · " in s or s.rstrip().endswith("→")] == []   # middle-dot meta strings; "→" appended to a label


CHART = ["chart-surface", "chart-ink", "chart-ink-2", "chart-muted", "chart-grid", "series-today", "series-after", "series-aligned",
         "floor", "breach", "regime", "family-tariffs", "family-war-oil", "family-chips", "family-rates",
         "status-ok", "status-caution", "status-outside", "map-land", "map-ocean", "map-border"]


def test_night_tokens_and_chart_vars_are_literal_in_the_first_root():
    css = read("styles.css")
    root = first_root(css)
    for k in ["sky", "paper", "paper-2", "pop", "ink", "ink-2", "haze", "starlight", "on-ink", "magenta", "terrain", "ground", "clear", "caution", "outside",
              "signal", "rule", "edge", "focus", *CHART, "font-ui"]:
        assert k in root, k
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}|rgba\([\d.,\s]+\)", root[k].strip()) for k in CHART)
    assert root["sky"].strip() == "#000000" and root["chart-surface"].strip() == "#000000"
    assert root["series-after"].strip() == root["magenta"].strip() == "#FF5FC8"
    assert root["family-rates"].strip().upper() != root["magenta"].strip().upper()
    assert root["ease-out"].strip() == "cubic-bezier(0.23, 1, 0.32, 1)" and root["ease-in-out"].strip() == "cubic-bezier(0.77, 0, 0.175, 1)"
    assert [root[f"dur-{k}"].strip() for k in ("press", "tip", "list", "flip", "panel", "lamp")] == ["120ms", "160ms", "200ms", "240ms", "320ms", "400ms"]


def test_one_theme_only_night():
    """Design direction from the lead (relayed during W1a, Sat Nov 14): the whole site is the night instrument. No day palette, no second token scope, no light colour scheme."""
    css = all_css()
    assert "color-scheme: dark" in css and "color-scheme: light" not in css and "prefers-color-scheme" not in css
    for k in ("sky", "paper", "ink", "magenta", "terrain", "clear", "caution", "outside"):
        assert len(re.findall(rf"--{k}\s*:", css)) == 1, f"--{k} is defined more than once: a second theme?"
    assert not re.search(r"#(E9F0F6|13294B|B0177B|EFE6D8)\b", css, re.I)   # the retired day palette


def _lum(hex_):
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _over_black(rgba):
    r, g, b, a = [float(x) for x in re.findall(r"[\d.]+", rgba)]
    return "#" + "".join(f"{round(v * a):02X}" for v in (r, g, b))


def test_night_colour_pairs_meet_wcag():
    """Spec 22 rule 9: every colour pair is checked. Text roles >= 4.5:1 on the black page and on every surface step; chart marks >= 4.5:1 where charts
    sit (page and lift) and >= 3:1 on the hover and floating steps; control edges and the focus ring >= 3:1; black labels on filled controls >= 4.5:1."""
    root = {k: v.strip() for k, v in first_root(read("styles.css")).items()}
    surfaces = {"sky": root["sky"], "paper": _over_black(root["paper"]), "paper-2": _over_black(root["paper-2"]), "pop": root["pop"]}
    texts = ["ink", "ink-2", "haze", "starlight", "magenta", "terrain", "clear", "caution", "outside", "signal", "chart-ink", "chart-ink-2", "chart-muted"]
    marks = ["series-today", "series-after", "series-aligned", "floor", "family-tariffs", "family-war-oil", "family-chips", "family-rates",
             "status-ok", "status-caution", "status-outside"]
    bad = [(k, s, round(_ratio(root[k], bg), 2)) for k in texts for s, bg in surfaces.items() if _ratio(root[k], bg) < 4.5]
    bad += [(k, s, round(_ratio(root[k], surfaces[s]), 2)) for k in marks for s in ("sky", "paper") if _ratio(root[k], surfaces[s]) < 4.5]
    bad += [(k, s, round(_ratio(root[k], surfaces[s]), 2)) for k in marks for s in ("paper-2", "pop") if _ratio(root[k], surfaces[s]) < 3]
    assert bad == []
    assert [(k, s) for k in ("edge", "focus") for s in ("sky", "paper") if _ratio(root[k], surfaces[s]) < 3] == []
    assert [k for k in ("ink", "magenta", "clear", "caution", "outside", "terrain") if _ratio(root["on-ink"], root[k]) < 4.5] == []


def test_fonts_vendored_licensed_and_within_budget():
    fonts = sorted(p.name for p in (WEB / "vendor/fonts").glob("*.woff2"))
    assert fonts == ["Archivo-Variable.woff2", "B612-Bold.woff2", "B612-Regular.woff2"]
    assert all((WEB / "vendor/fonts" / f).read_bytes()[:4] == b"wOF2" for f in fonts)
    assert sum((WEB / "vendor/fonts" / f).stat().st_size for f in fonts) <= 160 * 1024
    lic = read("vendor/LICENSES.md")
    assert "Archivo" in lic and "OFL-Archivo.txt" in lic and "U+202F is in none" in lic and "Overpass" not in lic
    assert "Overpass" not in all_css() and "Barlow" not in all_css()


def test_markers_are_svg_symbols_not_glyphs():
    html = read("index.html")
    assert all(f'<symbol id="{s}"' in html for s in ("m-fact", "m-assumption", "m-fiction", "i-pending"))
    assert not re.search("[●◐○]", all_js() + html)


def test_motion_constructs():
    src = all_css() + all_js()
    assert {re.sub(r"\s+", " ", b) for b in re.findall(r"cubic-bezier\(([^)]*)\)", src)} <= {"0.23, 1, 0.32, 1", "0.77, 0, 0.175, 1"}
    assert not re.search(r"transition(-property)?\s*:\s*all\b", src)
    assert not re.search(r"\bease-in\b(?!-out)", src) and not re.search(r"scale\(\s*0\s*\)", src) and "linear(" not in src
    assert not re.search(r"transition\s*:[^;]*\b(width|height|top|left|margin|padding|box-shadow)\b", all_css())
    assert re.search(r"\.btn:active[^{]*\{[^}]*scale\(0\.97\)", all_css())   # W-S1: the chips are gone; .tab is checked below
    for m in re.finditer(r"addEventListener\(\s*[\"']keydown[\"']", all_js()):
        body = all_js()[m.end(): m.end() + 600]
        assert ".animate(" not in body and "smooth" not in body


# ---- W-S1: the shell (three screens, the W1a review's four Important findings, budgets that a file can show) ----
def _strip_root(css):
    """The stylesheet without its first :root block (the tokens live there)."""
    m = re.search(r":root\s*\{.*?\}", css, re.S)
    return css[:m.start()] + css[m.end():]


def _blocks(css, query):
    """The bodies of every `@media <query> { ... }` block (braces counted)."""
    out = []
    for m in re.finditer(r"@media\s*" + re.escape(query) + r"\s*\{", css):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end():i - 1])
    return out


def _keyframes(css):
    """{name: body} of every @keyframes rule."""
    out = {}
    for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{", css):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out[m.group(1)] = css[m.end():i - 1]
    return out


def _decls(css, props):
    return [(m.group(1), m.group(2)) for m in re.finditer(r"(?<![\w-])(" + "|".join(props) + r")\s*:\s*([^;{}]+)", css)]


MOTION = ("transition", "transition-duration", "transition-timing-function", "animation", "animation-duration", "animation-timing-function")


def test_motion_uses_only_the_tokens():
    """W1a review I-2: outside the first :root no keyword easing and no numeric duration; `spin` (the one spinner) is the named exception."""
    css = _strip_root(all_css())
    bad = [(p, v.strip()) for p, v in _decls(css, MOTION)
           if not re.match(r"\s*spin\b", v) and (re.search(r"(?<![\w-])(ease|ease-in|ease-out|ease-in-out|linear|step-start|step-end|steps\()", v)
                                                 or re.search(r"(?<![\w-])\d+(\.\d+)?m?s\b", v))]
    assert bad == []
    assert not re.search(r"cubic-bezier\(", css)           # curves only through var(--ease-out) / var(--ease-in-out)


def test_reduced_motion_has_no_transform_motion():
    """W1a review I-3: under reduced motion nothing moves (opacity and colour feedback stay). Every transform transition and every
    keyframe that moves lives inside (prefers-reduced-motion: no-preference); the reduce block itself names no transform."""
    css = all_css()
    reduce = _blocks(css, "(prefers-reduced-motion: reduce)")
    assert reduce, "no reduced-motion block"
    assert not any(re.search(r"\b(transform|translate\w*|scale\w*|rotate\w*)\s*[:(]", b) for b in reduce)
    moving = {k for k, body in _keyframes(css).items() if re.search(r"\b(transform|translate|scale|rotate)\b", body)}
    rest = css
    for body in _blocks(css, "(prefers-reduced-motion: no-preference)"):
        rest = rest.replace(body, "")
    rest = re.sub(r"@keyframes\s+[\w-]+\s*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", rest)
    used = [v for p, v in _decls(rest, ("animation", "animation-name")) if any(re.search(rf"\b{k}\b", v) for k in moving)]
    assert used == [], used
    moved = [v for p, v in _decls(rest, ("transition", "transition-property")) if re.search(r"\b(transform|all)\b", v)]
    assert moved == [], moved
    for body in reduce:
        for p, v in _decls(body, ("animation", "animation-name")):
            name = v.split()[0]
            assert name in ("none", "fade") or name not in moving, v


def test_clip_reveals_release_their_clip():
    """W1a review I-1: a clip-path reveal holds its first frame during its delay and lets go at the end (fill-mode backwards)."""
    css = all_css()
    clips = {k for k, body in _keyframes(css).items() if "clip-path" in body}
    for p, v in _decls(css, ("animation",)):
        if any(re.search(rf"\b{k}\b", v) for k in clips):
            assert re.search(r"\bbackwards\b", v) and not re.search(r"\b(both|forwards)\b", v), v


def test_paper_is_the_research_lift():
    """W1a review I-4: --paper is the research's --lift, rgba(255,255,255,.05)."""
    assert re.sub(r"\s", "", first_root(read("styles.css"))["paper"]) in ("rgba(255,255,255,.05)", "rgba(255,255,255,0.05)")


def test_the_replay_page_in_the_design_doc_order_no_plotly():
    """The Replay design doc §2 (+ R5 #deep, R6 #record): the top bar, ten sections in order, the footer; the globe's one canvas
    is drawn by its module (index.html carries none or one); no plotly; the disclaimer in the page itself."""
    html = read("index.html")
    ids = [m.group(1) for m in re.finditer(r'<(?:section|header|footer)[^>]*\bid="([\w-]+)"', html)]
    assert ids == ["bar", "hero", "replay", "why", "testai", "money", "checklist", "investors", "how", "deep", "scenario", "record", "footer"], ids
    assert html.count("<canvas") <= 1 and "plotly" not in html.lower()
    assert "Educational simulation. This is not financial advice." in html


def test_three_screens_one_canvas_no_plotly():
    """Spec §24 resolution 11 (the classic page, web/classic.html, frozen): hero, the thesis beat, the cockpit (You and the move
    on the left, the answer on the right)."""
    html = read("classic.html")
    ids = [m.group(1) for m in re.finditer(r'<section[^>]*\bid="([\w-]+)"', html)]
    assert ids[:3] == ["hero", "thesis", "cockpit"], ids
    cockpit = html[html.index('id="cockpit"'):]
    assert cockpit.index('id="you"') < cockpit.index('id="move"') < cockpit.index('id="answer"')
    assert html.count("<canvas") == 1
    assert "plotly" not in html.lower()
    assert "Educational simulation. This is not financial advice." in html
    assert "Educational simulation: nothing is bought or sold." in html          # ledger §28, under the hero button


def test_uppercase_only_on_the_headline_and_the_lamp():
    """Spec §22 ruling 5: sentence case everywhere; CSS capitals only on the giant headline and the verdict lamp."""
    css = all_css()
    sels = [m.group(1).strip() for m in re.finditer(r"([^{}]+)\{[^{}]*text-transform\s*:\s*uppercase", css)]
    assert sels and all(re.fullmatch(r"\.(display|lamp-word)", s) for s in sels), sels


def test_magenta_only_for_the_move():
    """Magenta is the move and nothing else: every rule that paints with it names the move."""
    css = _strip_root(all_css())
    for m in re.finditer(r"([^{}]+)\{([^{}]*var\(--(?:magenta|series-after)\)[^{}]*)\}", css):
        assert re.search(r"move|after", m.group(1)), m.group(1).strip()


def test_pressables_press_and_hover_is_gated():
    css = all_css()
    for sel in (".btn", ".tab"):
        assert re.search(re.escape(sel) + r":active[^{]*\{[^}]*scale\(0\.97\)", css), sel
    no_media = css
    for body in _blocks(css, "(hover: hover) and (pointer: fine)"):
        no_media = no_media.replace(body, "")
    assert ":hover" not in no_media


def test_no_plotly_and_the_vendor_set():
    """Board meeting 2 (resolution 11): the page draws its own SVG; plotly is gone from the page and from web/vendor. Every
    vendored file has its licence row; three.js is the one WebGL library, imported only by globe.js (after first paint)."""
    assert "plotly" not in all_js().lower() and not list(WEB.glob("vendor/plotly*")) and not (WEB / "vendor/topojson").exists()
    lic = read("vendor/LICENSES.md")
    for f in ("three/three.module.min.js", "nasa/black-marble-2016-4096.jpg", "nasa/black-marble-2016-2048.jpg", "nasa/earth-poster.jpg"):
        assert (WEB / "vendor" / f).is_file() and f in lic, f
    assert "plotly" not in lic.lower() and "world_110m" not in lic
    js = {p.name: p.read_text(encoding="utf-8") for p in WEB.glob("*.js")}
    assert sorted(n for n, t in js.items() if "three.module" in t) == ["classic-globe.js", "globe.js"]   # the Replay's, the classic page's
    assert js["globe.js"].count("new THREE.WebGLRenderer(") == 1 and 'import("./classic-globe.js")' in js["classic.js"]
    assert "three.module" not in js["app.js"] and not [p.name for d in ("sections", "lib") for p in WEB.glob(f"{d}/*.js")
                                                         if "three.module" in p.read_text(encoding="utf-8")]   # one WebGL owner
    assert all(p.stat().st_size <= 750 * 1024 for p in WEB.glob("vendor/nasa/*.jpg"))


def test_parse_time_js_budget():
    """Spec §22 rule 7: JS referenced at parse time by index.html <= 800 KiB (three.js loads after first paint, by import())."""
    html = read("index.html")
    srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', html)
    assert sorted(srcs) == ["app.js", "lib.js"]
    assert sum((WEB / s).stat().st_size for s in srcs) <= 800 * 1024
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html.replace('<script type="importmap">', ""))   # no inline script


def test_motion_in_js_reads_the_tokens():
    """No WAAPI call with a literal duration; timers that pace motion read the CSS tokens (ms("dur-…"))."""
    js = all_js()
    assert ".animate(" not in js
    assert re.search(r'ms\("dur-list"\)', js) and re.search(r'ms\("dur-panel"\)', js)


# ---- ruling R16 (design doc, 0bc3d47) and the red gates over EVERY shipped module of the Replay: web/*.js, web/sections/*.js,
# web/lib/*.js, web/css/*.css (web/vendor/ is third-party; web/dev/ is never published). Integrator: lane U0. ----
def shipped(kind):
    globs = {"js": ("*.js", "sections/*.js", "lib/*.js"), "css": ("*.css", "css/*.css")}[kind]
    return sorted(p for g in globs for p in WEB.glob(g))


# Files written before R16 that their lane is rewriting (routed in /tmp/epi_lanes/integration.md). New files are held to R16 from
# their first push; a file leaves this set as soon as it is clean (never add one).
R16_PENDING: set = set()          # U5b's money.js and checklist.js were rewritten clean (5c9d74e): nothing is pending


def _literals(text):
    return [m.group(2) for m in re.finditer(r"([\"'`])((?:\\.|(?!\1).)*)\1", text)]


def test_r16_dom_from_text_svg_markers_and_no_meta_dots_in_every_module():
    """R16: DOM built with createElement/textContent (no HTML from strings), markers are the SVG symbols (#m-fact,
    #m-assumption, #m-fiction) never the characters, and no "A · B · C" meta strings in what the page shows."""
    bad = []
    for p in shipped("js"):
        rel = p.relative_to(WEB).as_posix()
        if rel in R16_PENDING:
            continue
        t = p.read_text(encoding="utf-8")
        if re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write\(", t):
            bad.append((rel, "HTML from a string"))
        if re.search("[●◐○]", t):
            bad.append((rel, "a marker character (use the SVG symbol)"))
        code = re.sub(r"/\*.*?\*/|(?<![:\\\"'`])//[^\n]*", "", t, flags=re.S)
        if any(" · " in s for s in _literals(code)):
            bad.append((rel, "a ' · ' meta string"))
    assert bad == [], bad


def test_no_advice_words_and_no_network_in_any_module():
    """Red gates 1 and 8 on every module (no allowance): no buy / sell / hold / "you should" / recommend in any string the page
    can show, no remote host in any src, href, url(), fetch or import."""
    words, net = [], []
    for p in [*shipped("js"), *shipped("css"), WEB / "index.html"]:
        rel = p.relative_to(WEB).as_posix()
        t = p.read_text(encoding="utf-8")
        if re.search(r"""(?:src|href)=["']https?://|url\(\s*['"]?https?://|(?:fetch|import)\(\s*['"`]https?://""", t):
            net.append(rel)
        if p.suffix == ".js":
            code = re.sub(r"/\*.*?\*/|(?<![:\\\"'`])//[^\n]*", "", t, flags=re.S)
            hits = sorted({m.group(0).lower() for s in _literals(code) if " " in s for m in ADVICE.finditer(s)})
            if hits:
                words.append((rel, hits))
    assert words == [] and net == [], (words, net)


def test_lanes_read_the_tokens_never_fork_them():
    """Design doc §3 / COMMON_UI: one set of night tokens in web/styles.css; a lane's stylesheet reads them with var() and never
    redefines a colour role; no `transition: all`; curves only through var(--ease-out) / var(--ease-in-out)."""
    roles = ("sky", "paper", "paper-2", "pop", "ink", "ink-2", "haze", "starlight", "on-ink", "magenta", "terrain", "clear", "caution",
             "outside", "signal", "rule", "edge", "focus", "ease-out", "ease-in-out")
    forked, motion = [], []
    for p in WEB.glob("css/*.css"):
        t = p.read_text(encoding="utf-8")
        forked += [(p.name, k) for k in roles if re.search(rf"(?<![\w-])--{re.escape(k)}\s*:", t)]
        if re.search(r"transition(-property)?\s*:\s*all\b", t):
            motion.append((p.name, "transition: all"))
        if re.search(r"cubic-bezier\(", t):
            motion.append((p.name, "a literal curve"))
    assert forked == [] and motion == [], (forked, motion)


def test_r16_uppercase_only_for_the_headline_and_the_lamp_in_every_stylesheet():
    """R16: CSS capitals only on the giant headline (U1's .hx-title) and the verdict lamp (U2's .lamp-word); the classic page
    keeps its own two (.display, .lamp-word)."""
    allowed = {".hx-title", ".lamp-word", ".display"}
    bad = []
    for p in shipped("css"):
        css = p.read_text(encoding="utf-8")
        for m in re.finditer(r"([^{}]+)\{[^{}]*text-transform\s*:\s*uppercase", css):
            sels = {s.strip() for s in re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S).split(",")}
            bad += [(p.name, s) for s in sels if s not in allowed]
    assert bad == [], bad
