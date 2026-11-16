"""Render the two PDF deliverables from the FILLED docs (lane pdf, Sun 15 Nov).

    python scripts/render_pdfs.py [--technical FILE] [--onepager FILE] [--out DIR] [--cdp FILE] [--port N] [--html-only]

Reads the filled docs (docs/technical.md and docs/one_pager.md, written by scripts/fill_docs.py from docs/templates/), converts
each to HTML with the print stylesheet docs/print/print.css, and prints it with headless Chrome (Page.printToPDF) through
the lane driver (--cdp, default /tmp/epi_lanes/cdp.mjs), holding the machine's one-Chrome lock (mkdir
/tmp/epi_chrome.lock, always released). Writes EPICENTRE_doc_tech.pdf and EPICENTRE_onepager.pdf to --out
(default ~/Desktop/EPICENTRE_deliverables; renamed to the team number at submission).

A render fails, writing nothing, when a slot or any angle-bracket placeholder is left in a filled copy, when the
one-pager shows more than six figures (ruling R22) or prints on more than one page. Pure standard library: a small
converter for the Markdown the two docs use (headings, paragraphs, lists, tables, fenced code, images, links, bold,
italic, code spans, rules, comments). Raw HTML is escaped, never passed through. Relative links become links into the
repository on GitHub, so every reference in the PDF opens; #anchors stay inside the PDF.
"""
import argparse
import html as _html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REPO = "https://github.com/shmorsi/poly-datathon-2026"
PRINT_CSS = DOCS / "print" / "print.css"
DEFAULT_OUT = Path.home() / "Desktop" / "EPICENTRE_deliverables"
DEFAULT_CDP = Path("/tmp/epi_lanes/cdp.mjs")
LOCK = Path("/tmp/epi_chrome.lock")
OUTPUTS = {"technical": "EPICENTRE_doc_tech.pdf", "onepager": "EPICENTRE_onepager.pdf"}
MAX_FIGURES = 6                                     # ruling R22 on the one-pager
SLOT = re.compile(r"⟨(run|eval):([^⟩|]+?)(?:\|([a-z0-9]+))?⟩")      # the grammar of scripts/fill_docs.py
NUMERIC_FORMATS = {"pct", "pct0", "spct", "usd", "usd2", "usd4", "int", "x1", "x2", "len"}
COMMENT = re.compile(r"<!--.*?-->", re.S)


class RenderError(Exception):
    """A render that must not ship; the message says which file and why."""


@dataclass
class Heading:
    level: int
    text: str
    id: str


@dataclass
class Doc:
    html: str
    headings: list = field(default_factory=list)
    figures: list = field(default_factory=list)          # ids of the figures (images) in reading order


def esc(s):
    return _html.escape(s, quote=True)


def strip_comments(md):
    return COMMENT.sub("", md)


# ---- inline -------------------------------------------------------------------------------------------------------

CODE_SPAN = re.compile(r"`([^`\n]+)`")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
ITALIC = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")
TOKEN = re.compile(r"\x00(\d+)\x00")


def link_target(href):
    """A doc's relative link, as a link that opens from the PDF: into the repository on GitHub; #anchors stay."""
    if href.startswith(("#", "http://", "https://", "mailto:")):
        return href
    path, _, anchor = href.partition("#")
    resolved = (DOCS / path).resolve()
    try:
        rel = resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return href
    kind = "tree" if path.endswith("/") or (resolved.is_dir()) else "blob"
    return f"{REPO}/{kind}/main/{rel}{'/' if path.endswith('/') else ''}{'#' + anchor if anchor else ''}"


def inline(text):
    """One line or cell of Markdown as HTML: code spans first (literal), then images, links, bold, italic."""
    spans = []

    def keep(fragment):
        spans.append(fragment)
        return f"\x00{len(spans) - 1}\x00"

    def attr(s):
        return esc(_html.unescape(s))

    text = CODE_SPAN.sub(lambda m: keep(f"<code>{_html.escape(m.group(1), quote=False)}</code>"), text)
    text = _html.escape(text, quote=False)
    text = IMAGE.sub(lambda m: keep(f'<img src="{attr(asset_url(_html.unescape(m.group(2))))}" '
                                    f'alt="{attr(m.group(1))}">'), text)
    text = LINK.sub(lambda m: keep(f'<a href="{attr(link_target(_html.unescape(m.group(2))))}">'
                                   f'{emphasis(m.group(1))}</a>'), text)
    text = emphasis(typography(text))
    while TOKEN.search(text):                             # a link may hold a code span: restore until none is left
        text = TOKEN.sub(lambda m: spans[int(m.group(1))], text)
    return text


def emphasis(text):
    return ITALIC.sub(r"<em>\1</em>", BOLD.sub(r"<strong>\1</strong>", text))


def typography(text):
    """Printer's quotes in running text (never in code): Robert's -> Robert’s, "a" -> “a”."""
    text = re.sub(r"(?<=\w)'", "’", text)                      # Robert's, the organizers'
    text = re.sub(r"(^|[\s(\[—–-])'(?=\S)", "\\1‘", text)
    text = text.replace("'", "’")
    text = re.sub(r'(^|[\s(\[—–-])"(?=\S)', "\\1“", text)
    return text.replace('"', "”")


def plain(text):
    """The words of a heading without its marks, as GitHub reads them for the id."""
    text = CODE_SPAN.sub(r"\1", text)
    text = LINK.sub(r"\1", text)
    return re.sub(r"\*\*|(?<!\w)\*|\*(?!\w)", "", text).strip()


def slugify(text, seen):
    """GitHub's heading id: lower case, punctuation dropped, spaces to hyphens, a repeat gets -1, -2."""
    base = re.sub(r"[^\w\- ]", "", plain(text).lower()).replace(" ", "-")
    slug, n = base, 0
    while slug in seen:
        n += 1
        slug = f"{base}-{n}"
    seen.add(slug)
    return slug


def asset_url(src):
    """A local image as a file:// URL (Chrome prints from disk); a web address stays as written."""
    if src.startswith(("http://", "https://", "data:", "file:")):
        return src
    p = Path(src)
    return (p if p.is_absolute() else (DOCS / src)).resolve().as_uri()


# ---- blocks -------------------------------------------------------------------------------------------------------

FENCE = re.compile(r"^```\s*([\w-]*)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RULE = re.compile(r"^ {0,3}([-*_])( *\1){2,} *$")
BULLET = re.compile(r"^[-*+]\s+(.*)$")
NUMBERED = re.compile(r"^(\d+)[.)]\s+(.*)$")
TABLE_SEP = re.compile(r"^\|? *:?-{3,}:? *(\| *:?-{3,}:? *)*\|? *$")
QUOTE = re.compile(r"^>\s?(.*)$")
LONE_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")


def _starts_block(line):
    return bool(FENCE.match(line) or HEADING.match(line) or RULE.match(line) or BULLET.match(line)
                or NUMBERED.match(line) or line.startswith("|") or QUOTE.match(line))


def _cells(line):
    """The cells of a table row; a | inside a code span does not split."""
    spans = []
    s = CODE_SPAN.sub(lambda m: spans.append(m.group(0)) or f"\x01{len(spans) - 1}\x01", line.strip())
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    return [re.sub(r"\x01(\d+)\x01", lambda m: spans[int(m.group(1))], c).strip() for c in s.split("|")]


def _align(sep):
    out = []
    for c in _cells(sep):
        left, right = c.startswith(":"), c.endswith(":")
        out.append("center" if left and right else "right" if right else "left" if left else None)
    return out


def _table(lines, i):
    head, aligns, rows, i = _cells(lines[i]), _align(lines[i + 1]), [], i + 2
    while i < len(lines) and lines[i].strip().startswith("|"):
        rows.append(_cells(lines[i]))
        i += 1

    def row(cells, tag):
        tds = []
        for n, c in enumerate(cells):
            a = aligns[n] if n < len(aligns) else None
            style = f' style="text-align:{a}"' if a else ""
            tds.append(f"<{tag}{style}>{inline(c)}</{tag}>")
        return "<tr>" + "".join(tds) + "</tr>"

    body = "\n".join(row(r, "td") for r in rows)
    return f"<table>\n<thead>\n{row(head, 'th')}\n</thead>\n<tbody>\n{body}\n</tbody>\n</table>", i


def _list(lines, i):
    first = NUMBERED.match(lines[i])
    pattern, items = (NUMBERED if first else BULLET), []
    while i < len(lines):
        m = pattern.match(lines[i])
        if m:
            items.append([m.group(m.lastindex)])
        elif lines[i].strip() and items and (lines[i][:1] in " \t" or not _starts_block(lines[i])):
            items[-1].append(lines[i].strip())                          # an indented or lazy continuation
        else:
            break
        i += 1
    tag = "ol" if first else "ul"
    start = f' start="{first.group(1)}"' if first and first.group(1) != "1" else ""
    body = "\n".join(f"<li>{inline(' '.join(item))}</li>" for item in items)
    return f"<{tag}{start}>\n{body}\n</{tag}>", i


def _figure(alt, src, figures):
    path = Path(src) if Path(src).is_absolute() else DOCS / src
    fid = "fig-" + re.sub(r"[^\w-]", "-", path.stem.lower())
    figures.append(fid)
    if path.suffix.lower() == ".svg" and path.is_file():          # inline: the diagram's words use the page's font
        svg = re.sub(r"^\s*(<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|\s)*", "", path.read_text(encoding="utf-8"))
        body = svg.replace("<svg", f'<svg role="img" aria-label="{esc(alt)}"', 1)
    else:
        body = f'<img src="{esc(asset_url(src))}" alt="{esc(alt)}">'
    return f'<figure class="fig" id="{fid}">{body}</figure>'


def md_to_html(md, sections=False):
    """Doc(html, headings, figures). With sections=True each h2 opens a <section> that runs to the next h2 or to a
    rule (---), and the run of sections sits in one <div class="sections">."""
    lines = strip_comments(md).split("\n")
    out, headings, figures, seen = [], [], [], set()
    state = {"section": False, "group": False}

    def close(group_too):
        if state["section"]:
            out.append("</section>")
            state["section"] = False
        if group_too and state["group"]:
            out.append("</div>")
            state["group"] = False

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if m := FENCE.match(line):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            lang = f' class="language-{m.group(1)}"' if m.group(1) else ""
            out.append(f"<pre><code{lang}>{_html.escape(chr(10).join(lines[i + 1:j]), quote=False)}</code></pre>")
            i = j + 1
            continue
        if m := HEADING.match(line):
            level, text = len(m.group(1)), m.group(2)
            hid = slugify(text, seen)
            headings.append(Heading(level, plain(text), hid))
            if sections and level == 2:
                close(False)
                if not state["group"]:
                    out.append('<div class="sections">')
                    state["group"] = True
                out.append(f'<section class="s" data-for="{hid}">')
                state["section"] = True
            out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
            i += 1
            continue
        if RULE.match(line):
            close(True)
            out.append("<hr>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and TABLE_SEP.match(lines[i + 1]):
            block, i = _table(lines, i)
            out.append(block)
            continue
        if BULLET.match(line) or NUMBERED.match(line):
            block, i = _list(lines, i)
            out.append(block)
            continue
        j, para = i, []
        quote = bool(QUOTE.match(line))
        while j < len(lines) and lines[j].strip() and (j == i or not _starts_block(lines[j])
                                                        or (quote and QUOTE.match(lines[j]))):
            para.append(QUOTE.match(lines[j]).group(1) if quote and QUOTE.match(lines[j]) else lines[j].strip())
            j += 1
        text = " ".join(p.strip() for p in para)
        if m := LONE_IMAGE.match(text):
            out.append(_figure(m.group(1), m.group(2), figures))
        elif quote:
            out.append(f"<blockquote><p>{inline(text)}</p></blockquote>")
        else:
            out.append(f"<p>{inline(text)}</p>")
        i = j
    close(True)
    return Doc("\n".join(out), headings, figures)


# ---- the checks that gate a render ---------------------------------------------------------------------------------

def require_filled(text, name):
    """Every slot filled: no angle-bracket placeholder anywhere in the copy, code spans included."""
    bad = [f"{name}:{n}: {line.strip()[:100]}" for n, line in enumerate(text.split("\n"), 1) if re.search("[⟨⟩]", line)]
    if bad:
        raise RenderError("a slot or placeholder is left (fill the docs with scripts/fill_docs.py --final first):\n  "
                          + "\n  ".join(bad))


def page_count(pdf):
    n = len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", pdf))
    if not n:
        raise RenderError("no page found in the PDF")
    return n


def require_pages(pdf, most, name):
    n = page_count(pdf)
    if n > most:
        raise RenderError(f"{name}: {n} pages, at most {most} allowed")
    return n


URL = re.compile(r"(?:https?://|www\.)\S+|[\w.-]+\.(?:github\.io|com|ca|org|net)(?:/\S*)?")
NAMES = re.compile(r"\b(?:Sonnet|Haiku|Opus)\s\d+(?:\.\d+)?|\bDatathon\s\d{4}")
DATES = re.compile(r"\b\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b")
YEARS = re.compile(r"(?<![\w$.,−-])(?:19|20)\d\d(?:\s?[–-]\s?\d\d(?:\d\d)?)?(?![\w%,.]\d|\s?%)")
FIGURE = re.compile(r"(?<![\w.,−-])[−-]?\$?\d+(?:,\d{3})*(?:\.\d+)?(?:\s?%)?(?![\w-])")


def figures(text):
    """The figures a reader sees: amounts, rates and counts; not years or date labels, names with a version
    (Sonnet 5.5, SHA-256, S3) or web addresses."""
    for pattern in (URL, NAMES, DATES, YEARS):
        text = pattern.sub(" ", text)
    return [re.sub(r"\s+", " ", f) for f in FIGURE.findall(text)]


def visible_text(page_html):
    body = re.sub(r"<(style|script)\b.*?</\1>", " ", page_html, flags=re.S)
    return _html.unescape(re.sub(r"<[^>]+>", " ", body))


# ---- the pages -----------------------------------------------------------------------------------------------------

ARCH_LINE = "Architecture: components, data flows, AWS services, cost"


def contents_block(doc, pages=None):
    """The contents: every h2 with its page, and the architecture figure under the section that holds it."""
    pages = pages or {}
    items, fig_after = [], None
    if "fig-architecture" in doc.figures:
        html_before = doc.html.split('id="fig-architecture"', 1)[0]
        owners = [h for h in doc.headings if h.level == 2 and f'id="{h.id}"' in html_before]
        fig_after = owners[-1].id if owners else None
    for h in (h for h in doc.headings if h.level == 2):
        num, _, title = h.text.partition(". ") if re.match(r"^\d+\. ", h.text) else ("", "", h.text)
        items.append(f'<li><a href="#{h.id}"><span class="n">{esc(num)}</span><span class="t">{esc(title)}</span>'
                     f'<span class="pg">{pages.get(h.id, "")}</span></a></li>')
        if h.id == fig_after:
            items.append(f'<li class="sub"><a href="#fig-architecture"><span class="n"></span>'
                         f'<span class="t">{ARCH_LINE}</span><span class="pg">'
                         f'{pages.get("fig-architecture", pages.get(h.id, ""))}</span></a></li>')
    return ('<nav class="contents" aria-label="Contents"><p class="contents-h">Contents</p><ol>'
            + "".join(items) + "</ol></nav>")


def page(kind, title, body):
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>{esc(title)}</title>\n'
            f'<link rel="stylesheet" href="{PRINT_CSS.as_uri()}">\n</head>\n<body class="{kind}">\n{body}\n</body>\n</html>\n')


def technical_page(md, pages=None):
    """The technical doc: the title block, then the contents beside the one-paragraph summary, then the rest."""
    doc = md_to_html(md, sections=True)
    blocks = doc.html.split("\n")
    lead = next((n for n, b in enumerate(blocks) if b.startswith("<p><strong>In one paragraph")), None)
    nav = contents_block(doc, pages)
    if lead is None:
        at = next((n for n, b in enumerate(blocks) if b.startswith("<h1")), -1) + 1
        blocks.insert(at, nav)
    else:
        blocks[lead] = f'<div class="front">{blocks[lead]}{nav}</div>'
    title = next((h.text for h in doc.headings if h.level == 1), "EPICENTRE: technical documentation")
    return page("doc tech", title, "\n".join(blocks)), doc


def onepager_page(md):
    """The spec sheet: the title and pitch beside the hero image (its caption under it), then the six blocks."""
    doc = md_to_html(md, sections=True)
    blocks = doc.html.split("\n")
    fig = next((n for n, b in enumerate(blocks) if b.startswith("<figure")), None)
    if fig is not None and blocks[0].startswith("<h1") and fig + 1 < len(blocks) and blocks[fig + 1].startswith("<p>"):
        blocks = (blocks[:1] + ['<div class="pitch">' + "".join(blocks[1:fig]) + "</div>",
                                '<div class="hero">' + blocks[fig] + blocks[fig + 1] + "</div>"] + blocks[fig + 2:])
    html_text = page("doc onepager", "EPICENTRE: one-pager", "\n".join(blocks))
    found = figures(visible_text(html_text))
    if len(found) > MAX_FIGURES:
        raise RenderError(f"the one-pager shows {len(found)} figures, at most {MAX_FIGURES} (R22): {', '.join(found)}")
    return html_text, doc


# ---- the outline: which page each heading landed on ----------------------------------------------------------------

OBJ = re.compile(rb"(\d+) 0 obj\s*(<<.*?)(?:stream\r?\n|endobj)", re.S)


def _pdf_string(raw):
    """A PDF text string (literal or hex, PDFDocEncoding or UTF-16BE) as str."""
    if raw.startswith(b"<"):
        data = bytes.fromhex(raw[1:-1].decode("ascii"))
    else:
        body, data, k = raw[1:-1], bytearray(), 0
        while k < len(body):
            c = body[k:k + 1]
            if c == b"\\" and k + 1 < len(body):
                nxt = body[k + 1:k + 2]
                octal = re.match(rb"[0-7]{1,3}", body[k + 1:k + 4])
                if octal:
                    data.append(int(octal.group(0), 8) & 0xFF)
                    k += 1 + len(octal.group(0))
                    continue
                data += {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(nxt, nxt)
                k += 2
                continue
            data += c
            k += 1
        data = bytes(data)
    return data[2:].decode("utf-16-be") if data[:2] == b"\xfe\xff" else data.decode("latin-1")


def outline_pages(pdf):
    """{bookmark title: page number} from the outline Chrome writes (generateDocumentOutline); {} if none is found."""
    objs = {int(m.group(1)): m.group(2) for m in OBJ.finditer(pdf)}
    root = next((b for b in objs.values() if re.search(rb"/Type\s*/Pages\b", b) and b"/Parent" not in b), None)
    order = []

    def walk(body):
        kids = re.search(rb"/Kids\s*\[([^\]]*)\]", body)
        for ref in re.findall(rb"(\d+) 0 R", kids.group(1) if kids else b""):
            kid = objs.get(int(ref), b"")
            if re.search(rb"/Type\s*/Pages\b", kid):
                walk(kid)
            else:
                order.append(int(ref))

    if root is None:
        return {}
    walk(root)
    index = {ref: n + 1 for n, ref in enumerate(order)}
    out = {}
    for body in objs.values():
        title = re.search(rb"/Title\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", body, re.S)
        dest = re.search(rb"/(?:Dest|D)\s*\[\s*(\d+) 0 R", body)
        if title and dest and int(dest.group(1)) in index:
            out.setdefault(re.sub(r"\s+", " ", _pdf_string(title.group(1))).strip(), index[int(dest.group(1))])
    return out


def dest_pages(pdf):
    """{anchor id: page} from the named destinations Chrome writes for every #link target (the catalog's /Dests)."""
    objs = {int(m.group(1)): m.group(2) for m in OBJ.finditer(pdf)}
    order = []

    def walk(body):
        kids = re.search(rb"/Kids\s*\[([^\]]*)\]", body)
        for ref in re.findall(rb"(\d+) 0 R", kids.group(1) if kids else b""):
            kid = objs.get(int(ref), b"")
            walk(kid) if re.search(rb"/Type\s*/Pages\b", kid) else order.append(int(ref))

    catalog = next((b for b in objs.values() if re.search(rb"/Type\s*/Catalog\b", b)), b"")
    root, dests = re.search(rb"/Pages\s+(\d+) 0 R", catalog), re.search(rb"/Dests\s+(\d+) 0 R", catalog)
    if not (root and dests):
        return {}
    walk(objs.get(int(root.group(1)), b""))
    index = {ref: n + 1 for n, ref in enumerate(order)}
    names = re.findall(rb"/([^\s/\[\]()<>{}%]+)\s*\[\s*(\d+) 0 R", objs.get(int(dests.group(1)), b""))
    return {re.sub(r"#([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), n.decode("latin-1")): index[int(r)]
            for n, r in names if int(r) in index}


def heading_pages(doc, pdf):
    """{id: page} for the h2 headings and the figures: the named destinations first, else the bookmarks' titles."""
    def key(s):                                          # the print sheet sets h2 in capitals; the outline keeps them
        return re.sub(r"\W+", "", s.casefold())

    marks = {key(t): n for t, n in outline_pages(pdf).items()}
    found = {h.id: marks[key(h.text)] for h in doc.headings if h.level == 2 and key(h.text) in marks}
    wanted = {h.id for h in doc.headings if h.level == 2} | set(doc.figures)
    return {**found, **{k: v for k, v in dest_pages(pdf).items() if k in wanted}}


# ---- Chrome -------------------------------------------------------------------------------------------------------

NODE_PRINT = """
import { launch } from %s;
import { writeFileSync } from 'node:fs';
const jobs = JSON.parse(process.env.EPI_PDF_JOBS);
const b = await launch({ port: Number(process.env.EPI_PDF_PORT), W: 1275, H: 1650, dsf: 1, maxMs: 170000 });
let code = 0;
try {
  for (const j of jobs) {
    await b.goto(j.url);
    await b.waitFor('document.fonts.status === "loaded" && [...document.images].every((i) => i.complete)', 20000);
    const fonts = await b.evaluate('document.fonts.ready.then(() => [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family + " " + f.weight).join(", "))');
    const r = await b.send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false,
      generateTaggedPDF: true, generateDocumentOutline: true });
    writeFileSync(j.pdf, Buffer.from(r.data, 'base64'));
    console.log(JSON.stringify({ pdf: j.pdf, fonts }));
  }
  const bad = b.logs.filter((l) => l.startsWith('EXC') || l.startsWith('error'));
  if (bad.length) { console.error(bad.join('\\n')); code = 2; }
} catch (e) { console.error(String(e)); code = 1; } finally { await b.close(); }
process.exit(code);
"""


def chrome_print(jobs, cdp, port):
    """Print [(html_path, pdf_path)] in one headless Chrome, under the machine's one-Chrome lock (always released)."""
    if not Path(cdp).is_file():
        raise RenderError(f"the Chrome driver {cdp} is missing (pass --cdp)")
    t0 = time.time()
    while True:
        try:
            LOCK.mkdir()
            break
        except FileExistsError:
            if time.time() - t0 > 900:
                raise RenderError("the Chrome lock stayed taken for 15 minutes") from None
            time.sleep(3)
    try:
        env = dict(os.environ, EPI_PDF_PORT=str(port),
                   EPI_PDF_JOBS=json.dumps([{"url": Path(h).resolve().as_uri(), "pdf": str(p)} for h, p in jobs]))
        r = subprocess.run(["node", "--input-type=module", "-e", NODE_PRINT % json.dumps(Path(cdp).resolve().as_uri())],
                           env=env, capture_output=True, text=True, timeout=200)
    finally:
        LOCK.rmdir()
    if r.returncode:
        raise RenderError(f"Chrome could not print (exit {r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]


# ---- main ---------------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the technical doc and the one-pager to PDF from the filled docs.")
    ap.add_argument("--technical", type=Path, default=DOCS / "technical.md", help="the filled technical doc")
    ap.add_argument("--onepager", type=Path, default=DOCS / "one_pager.md", help="the filled one-pager")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where the two PDFs go")
    ap.add_argument("--cdp", type=Path, default=DEFAULT_CDP, help="the headless-Chrome driver (cdp.mjs)")
    ap.add_argument("--port", type=int, default=9590, help="Chrome's debugging port")
    ap.add_argument("--html-only", action="store_true", help="write the two HTML pages to --out, print nothing")
    args = ap.parse_args(argv)
    try:
        sources = {"technical": args.technical.read_text(encoding="utf-8"),
                   "onepager": args.onepager.read_text(encoding="utf-8")}
        for kind, text in sources.items():
            require_filled(text, {"technical": args.technical, "onepager": args.onepager}[kind].name)
        tech_html, tech_doc = technical_page(sources["technical"])
        one_html, _ = onepager_page(sources["onepager"])
        args.out.mkdir(parents=True, exist_ok=True)
        work = args.out if args.html_only else Path(tempfile.mkdtemp(prefix="epi_pdf_"))
        html_paths = {"technical": work / "EPICENTRE_doc_tech.html", "onepager": work / "EPICENTRE_onepager.html"}
        html_paths["technical"].write_text(tech_html, encoding="utf-8")
        html_paths["onepager"].write_text(one_html, encoding="utf-8")
        if args.html_only:
            print(f"render_pdfs: HTML written to {work}")
            return 0
        drafts = {k: work / OUTPUTS[k] for k in OUTPUTS}
        info = chrome_print([(html_paths[k], drafts[k]) for k in OUTPUTS], args.cdp, args.port)
        pages = heading_pages(tech_doc, drafts["technical"].read_bytes())
        if pages:                                            # second pass: the contents with the pages just found
            html_paths["technical"].write_text(technical_page(sources["technical"], pages)[0], encoding="utf-8")
            chrome_print([(html_paths["technical"], drafts["technical"])], args.cdp, args.port)
            moved = {k: v for k, v in heading_pages(tech_doc, drafts["technical"].read_bytes()).items() if pages.get(k) != v}
            if moved:
                raise RenderError(f"the contents' page numbers moved on the second pass: {moved}")
        n_one = require_pages(drafts["onepager"].read_bytes(), 1, OUTPUTS["onepager"])
        n_tech = page_count(drafts["technical"].read_bytes())
        for k in OUTPUTS:
            (args.out / OUTPUTS[k]).write_bytes(drafts[k].read_bytes())
    except RenderError as exc:
        print(f"render_pdfs: {exc}", file=sys.stderr)
        return 1
    print(f"render_pdfs: {OUTPUTS['technical']} {n_tech} pages (contents pages: {'found' if pages else 'none'}), "
          f"{OUTPUTS['onepager']} {n_one} page, in {args.out}; fonts: {info[0].get('fonts') if info else '?'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
