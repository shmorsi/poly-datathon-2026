"""scripts/format_holdout_v2_results.py, the paired line of section 2a (ruling R37): the held-out v2 result stated as
paired counts with an exact McNemar test, not as two separate rates."""
import pytest

from scripts import format_holdout_v2_results as F


@pytest.mark.parametrize("b, c, p", [(13, 0, 2 / 2 ** 13), (0, 0, 1.0), (3, 3, 1.0), (5, 1, 0.21875)])
def test_mcnemar_exact_is_the_two_sided_binomial_test_of_the_discordant_pairs(b, c, p):
    assert F.mcnemar_exact(b, c) == pytest.approx(p)


def _rows(spec):
    return [{"id": f"q{i}", "group": g, "families_ok": f, "whole_ok": w} for i, (g, f, w) in enumerate(spec)]


def test_the_paired_line_counts_each_side_and_the_categories():
    nav = _rows([("french", True, True), ("paraphrase", True, True), ("headline", True, True),
                 ("no_precedent", True, True)])
    kw = _rows([("french", False, False), ("paraphrase", False, False), ("headline", True, True),
                ("no_precedent", True, False)])
    line = F.paired_line(nav, kw, 4)
    assert "2 questions only the AI reader (the navigator) got right, 0 the other way (exact McNemar p = 0.5000" in line
    assert "french 1, paraphrase 1; both right 2, both wrong 0" in line
    assert "Whole reading right: 3 only the AI reader, 0 the other way" in line and "the 1 more: no_precedent 1" in line


def test_the_committed_rows_give_thirteen_to_zero():
    first, second = F.load()
    line = F.paired_line(second["navigator"], second["keyword"], len(second["navigator"]))
    assert "13 questions only the AI reader (the navigator) got right, 0 the other way (exact McNemar p = 0.0002" in line
