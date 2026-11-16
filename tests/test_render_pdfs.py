"""scripts/render_pdfs.py (lane pdf): the small Markdown converter, the checks that gate a render (no slot left, one
page for the one-pager, at most six figures on it) and the repo's two print sources. No Chrome here: the PDF checks
read small hand-built PDF bytes."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts import render_pdfs as rp

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/shmorsi/poly-datathon-2026"


def html(md, **kw):
    return rp.md_to_html(md, **kw).html


# ---- the converter -------------------------------------------------------------------------------------------------

def test_headings_get_the_github_ids_the_docs_link_to():
    out = html("## 1. The overall logic\n\n## 3. Methods, models and technologies, and why\n\n## 1. The overall logic")
    assert '<h2 id="1-the-overall-logic">1. The overall logic</h2>' in out
    assert 'id="3-methods-models-and-technologies-and-why"' in out
    assert 'id="1-the-overall-logic-1"' in out                      # a repeated title gets GitHub's suffix


def test_inline_bold_italic_code_and_links_are_escaped_once():
    out = html("**Bold** and *italic*, `a<b> & c`, [the site](https://x.example/?a=1&b=2).")
    assert out == ('<p><strong>Bold</strong> and <em>italic</em>, <code>a&lt;b&gt; &amp; c</code>, '
                   '<a href="https://x.example/?a=1&amp;b=2">the site</a>.</p>')


def test_a_code_span_is_literal_and_a_link_may_wrap_one():
    assert html("`**not bold**`") == "<p><code>**not bold**</code></p>"
    out = html("[`runtime-policy.json`](iam/runtime-policy.json)")
    assert f'<a href="{REPO}/blob/main/docs/iam/runtime-policy.json"><code>runtime-policy.json</code></a>' in out


def test_relative_links_point_at_the_repository_and_anchors_stay_in_the_pdf():
    out = html("[AWS](aws.md) [R](../README.md) [one](#1-the-overall-logic) [cost](aws.md#cost) [IAM](iam/)")
    assert f'href="{REPO}/blob/main/docs/aws.md"' in out
    assert f'href="{REPO}/blob/main/README.md"' in out
    assert 'href="#1-the-overall-logic"' in out
    assert f'href="{REPO}/blob/main/docs/aws.md#cost"' in out
    assert f'href="{REPO}/tree/main/docs/iam/"' in out


def test_lists_unordered_and_ordered():
    assert html("- **One.** first\n- two") == "<ul>\n<li><strong>One.</strong> first</li>\n<li>two</li>\n</ul>"
    assert html("1. a\n2. b") == "<ol>\n<li>a</li>\n<li>b</li>\n</ol>"
    assert html("3. c\n4. d").startswith('<ol start="3">')
    assert html("- an item\n  that continues") == "<ul>\n<li>an item that continues</li>\n</ul>"


def test_a_table_keeps_its_header_alignment_and_inline_marks():
    out = html("| Step | Who |\n|---|:---:|\n| **OBSERVE** | `code` |\n| VERIFY | the receipt |")
    assert out.startswith("<table>\n<thead>\n<tr><th>Step</th><th style=\"text-align:center\">Who</th></tr>")
    assert "<tr><td><strong>OBSERVE</strong></td><td style=\"text-align:center\"><code>code</code></td></tr>" in out
    assert out.count("<tr>") == 3 and out.endswith("</tbody>\n</table>")


def test_a_fenced_block_is_escaped_and_tagged_with_its_language():
    out = html("```mermaid\nA --> B<br/>\n```")
    assert out == '<pre><code class="language-mermaid">A --&gt; B&lt;br/&gt;</code></pre>'


def test_comments_are_dropped_raw_html_is_escaped_and_a_rule_is_a_rule():
    out = html("<!--\nnote for authors\n-->\n# Title\n\n<b>x</b>\nnext line\n\n---\nEnd.")
    assert "note for authors" not in out
    assert '<h1 id="title">Title</h1>' in out
    assert "<p>&lt;b&gt;x&lt;/b&gt; next line</p>" in out
    assert "<hr>" in out and out.endswith("<p>End.</p>")


def test_a_lone_image_becomes_a_figure_and_a_local_svg_is_inlined(tmp_path):
    png = html("![Robert's end frame](img/replay-end-frame.png)")
    assert png.startswith('<figure class="fig" id="fig-replay-end-frame"><img src="file://') and "docs/img/replay-end-frame.png" in png
    assert 'alt="Robert&#x27;s end frame"' in png
    svg = tmp_path / "d.svg"
    svg.write_text('<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><title>T</title>'
                   '<rect width="10" height="10"/></svg>', encoding="utf-8")
    out = html(f"![The architecture]({svg})")
    assert "<?xml" not in out and out.count("<svg") == 1
    assert 'role="img"' in out and 'aria-label="The architecture"' in out


def test_sections_wrap_each_h2_with_what_follows():
    out = html("# T\n\nlead\n\n## A\n\none\n\n## B\n\ntwo", sections=True)
    assert out.count("<section") == 2 and out.count("</section>") == 2
    assert out.index('<section class="s" data-for="a">') < out.index("one") < out.index("</section>")


def test_headings_are_collected_for_the_contents_block():
    doc = rp.md_to_html("# Doc\n\n## 1. One\n\n### Sub\n\n## 2. Two **bold**")
    assert [(h.level, h.text, h.id) for h in doc.headings] == [
        (1, "Doc", "doc"), (2, "1. One", "1-one"), (3, "Sub", "sub"), (2, "2. Two bold", "2-two-bold")]


# ---- the checks that gate a render ---------------------------------------------------------------------------------

def test_a_slot_left_in_a_filled_copy_fails_the_render_naming_the_line():
    rp.require_filled("All filled: 34.5 %.\n", "ok.md")
    for text in ("Line one\nfell ⟨run:robert:kpis.max_drawdown.value|pct⟩\n", "evidence: ⟨to capture⟩\n",
                 "in a span `⟨eval:price⟩`\n", "a stray ⟩ bracket\n"):
        with pytest.raises(rp.RenderError, match=r"t\.md:\d"):
            rp.require_filled(text, "t.md")


def _pdf(pages):
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objs = [b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj",
            f"2 0 obj\n<</Type /Pages /Kids [{kids}] /Count {pages}>>\nendobj".encode()]
    objs += [f"{3 + i} 0 obj\n<</Type/Page /Parent 2 0 R /MediaBox [0 0 612 792]>>\nendobj".encode() for i in range(pages)]
    return b"%PDF-1.4\n" + b"\n".join(objs) + b"\n%%EOF"


def test_pages_are_counted_from_the_page_objects():
    assert rp.page_count(_pdf(1)) == 1 and rp.page_count(_pdf(11)) == 11
    with pytest.raises(rp.RenderError):
        rp.page_count(b"%PDF-1.4\nnot a document")


def test_the_one_pager_fails_past_one_page():
    rp.require_pages(_pdf(1), 1, "EPICENTRE_onepager.pdf")
    with pytest.raises(rp.RenderError, match="2 pages"):
        rp.require_pages(_pdf(2), 1, "EPICENTRE_onepager.pdf")


def test_figures_are_quantities_not_names_years_or_addresses():
    text = ("Robert put 40 % of his savings in it; the same fall is $207,146 against the $90,000 he set. It broke at "
            "9 %, in this 2021–26 replay (Nov 2021 to Nov 2026). Receipt: 14 of 14. Claude Sonnet 5.5, SHA-256, S3, "
            "EC2, PolyFinances Datathon 2026, https://github.com/shmorsi/poly-datathon-2026 and shmorsi.github.io.")
    assert rp.figures(text) == ["40 %", "$207,146", "$90,000", "9 %", "14", "14"]
    assert rp.figures("−34.5 % and 1,315 tokens, 0.7") == ["−34.5 %", "1,315", "0.7"]


# ---- the repo's print sources --------------------------------------------------------------------------------------

ONE_PAGER = ROOT / "docs" / "templates" / "one_pager.md"      # the template: its slots are the figures R22 counts
SIX = ("problem", "agentic", "original", "data", "explainab", "gain")    # the case §3.4 order


def test_the_one_pager_has_the_six_required_blocks_in_the_case_order():
    doc = rp.md_to_html(ONE_PAGER.read_text(encoding="utf-8"))
    blocks = [h.text.lower() for h in doc.headings if h.level == 2]
    assert len(blocks) == 6, blocks
    for word, title in zip(SIX, blocks):
        assert word in title, (word, title)


def test_the_one_pager_shows_at_most_six_figures_and_types_none():
    """R22: at most six figures on the page; docs rule: every number is a slot, never typed."""
    text = rp.strip_comments(ONE_PAGER.read_text(encoding="utf-8"))
    slots = rp.SLOT.findall(text)
    numeric = [s for s in slots if s[2] in rp.NUMERIC_FORMATS or s[1].endswith(("verified", "total"))]
    typed = rp.figures(rp.SLOT.sub("", text))
    assert typed == [], typed
    assert len(numeric) <= 6 and len(slots) == len(numeric) + sum(1 for s in slots if s[2] == "verdict"), slots


def test_the_one_pager_carries_the_lines_the_red_gates_need():
    text = ONE_PAGER.read_text(encoding="utf-8")
    for line in ("Crash-test your move before you make it.", "« Passez votre placement au crash-test avant d'agir. »",
                 "This already happened; it is not a forecast.", "Fictional illustration, not a recommendation.",
                 "Educational simulation. This is not financial advice.",
                 "https://shmorsi.github.io/poly-datathon-2026/", REPO):
        assert line in text, line
    assert text.count("![") == 1                                       # one hero image


ARCH = ROOT / "docs" / "img" / "architecture.svg"


def test_the_architecture_diagram_is_self_contained_svg():
    root = ET.parse(ARCH).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg" and root.get("viewBox")
    assert root.find("{http://www.w3.org/2000/svg}title") is not None
    raw = ARCH.read_text(encoding="utf-8")
    assert "<script" not in raw and "<image" not in raw and "@import" not in raw
    assert "http" not in raw.replace("http://www.w3.org/2000/svg", "").replace("http://www.w3.org/1999/xlink", "")
    for name in ("CloudFront", "EC2", "FastAPI", "Amazon Bedrock", "Guardrails", "Claude Sonnet 5.5", "Converse", "S3",
                 "Object Lock", "CloudWatch", "IAM", "GitHub Pages", "no AWS call"):
        assert name in raw, name


def test_the_technical_doc_shows_the_diagram_in_section_1():
    text = (ROOT / "docs" / "technical.md").read_text(encoding="utf-8")
    one = text.split("\n## 1. ", 1)[1].split("\n## 2. ", 1)[0]
    assert "](img/architecture.svg)" in one
    assert "```mermaid" not in text


def test_the_contents_block_names_every_section_and_the_diagram():
    doc = rp.md_to_html("# T\n\n## 1. Logic\n\n![Arch](img/architecture.svg)\n\n## 2. Data\n\n## 3. Limits")
    block = rp.contents_block(doc, pages={"1-logic": 1, "2-data": 3})
    assert block.count("<li") == 4
    assert 'href="#1-logic"' in block and 'href="#3-limits"' in block and 'href="#fig-architecture"' in block
    assert '<span class="pg">3</span>' in block


def test_running_text_gets_printers_quotes_but_code_does_not():
    assert html('Robert\'s "move" and `a "b" \'c\'`') == '<p>Robert’s “move” and <code>a "b" \'c\'</code></p>'


def _outlined_pdf():
    """Three pages in a nested page tree and an outline whose titles the print sheet set in capitals."""
    objs = [b"1 0 obj\n<</Type /Catalog /Pages 2 0 R /Outlines 9 0 R>>\nendobj",
            b"2 0 obj\n<</Type /Pages /Kids [3 0 R 6 0 R] /Count 3>>\nendobj",
            b"3 0 obj\n<</Type /Pages /Parent 2 0 R /Kids [4 0 R 5 0 R] /Count 2>>\nendobj",
            b"4 0 obj\n<</Type /Page /Parent 3 0 R>>\nendobj", b"5 0 obj\n<</Type /Page /Parent 3 0 R>>\nendobj",
            b"6 0 obj\n<</Type /Page /Parent 2 0 R>>\nendobj",
            b"9 0 obj\n<</Type /Outlines /First 10 0 R /Count 2>>\nendobj",
            b"10 0 obj\n<</Title (1. THE OVERALL LOGIC)\n/Dest [4 0 R /XYZ 51 351 0] /Next 11 0 R>>\nendobj",
            b"11 0 obj\n<</Title <FEFF0032002E00200044004100540041>\n/Dest [6 0 R /XYZ 51 700 0]>>\nendobj"]
    return b"%PDF-1.4\n" + b"\n".join(objs) + b"\n%%EOF"


def test_the_contents_pages_come_from_the_pdf_outline():
    pdf = _outlined_pdf()
    assert rp.outline_pages(pdf) == {"1. THE OVERALL LOGIC": 1, "2. DATA": 3}
    doc = rp.md_to_html("# T\n\n## 1. The overall logic\n\n## 2. Data\n\n## 3. Missing")
    assert rp.heading_pages(doc, pdf) == {"1-the-overall-logic": 1, "2-data": 3}
    assert rp.page_count(pdf) == 3


def test_the_figure_and_section_pages_come_from_the_named_destinations():
    pdf = _outlined_pdf().replace(b"/Outlines 9 0 R>>", b"/Outlines 9 0 R /Dests 12 0 R>>").replace(
        b"\n%%EOF", b"\n12 0 obj\n<</fig-architecture [5 0 R /XYZ 0 600 0]\n/2-data [6 0 R /XYZ 0 700 0]>>\nendobj\n%%EOF")
    assert rp.dest_pages(pdf) == {"fig-architecture": 2, "2-data": 3}
    doc = rp.md_to_html("# T\n\n## 1. The overall logic\n\n![A](img/architecture.svg)\n\n## 2. Data")
    pages = rp.heading_pages(doc, pdf)
    assert pages == {"1-the-overall-logic": 1, "2-data": 3, "fig-architecture": 2}
    assert '<span class="t">' + rp.ARCH_LINE + '</span><span class="pg">2</span>' in rp.contents_block(doc, pages)


@pytest.mark.parametrize("name", ["technical.md", "one_pager.md"])
def test_every_link_the_pdf_carries_opens_a_file_of_the_repository(name):
    """A relative link becomes a GitHub address in the PDF: the file it names must exist, so no link is a dead end."""
    doc = rp.md_to_html((ROOT / "docs" / name).read_text(encoding="utf-8"))
    ids = {h.id for h in doc.headings} | set(doc.figures)
    for href in re.findall(r'<a href="([^"]+)"', doc.html):
        if href.startswith("#"):
            assert href[1:] in ids, href
        elif href.startswith(REPO + "/"):
            path = href[len(REPO) + 1:].split("/", 2)[2].split("#")[0]
            assert (ROOT / path).exists(), href
