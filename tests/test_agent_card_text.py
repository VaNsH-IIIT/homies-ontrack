"""Agent card: free text with dollar amounts must not be read as LaTeX (owner: P3, K24).

Streamlit renders `$...$` in markdown as maths: "the $10,538 stays unpaid ... (calls 3% at $2.40)" showed as
"the 10,538 ... at 2.40" with the text between in a maths font (28,113 open cases have two `$` in reason_1).
"""
import ast
import re
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "src" / "ontrack" / "app" / "pages" / "3_Agent_Card.py"
SOURCE = PAGE.read_text(encoding="utf-8")
# record fields that hold generated or customer text (and the two locals built from them)
FREE_TEXT = ("reason_", "counterfactual", "routing_reason", "text_evidence", "service_notes", "banner", "why")


def _md():
    tree = ast.parse(SOURCE)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "md")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(PAGE), "exec"), ns)
    return ns["md"]


def test_md_escapes_every_dollar_sign():
    md = _md()
    assert md("the $10,538 stays unpaid (calls 3% at $2.40)") == "the \\$10,538 stays unpaid (calls 3% at \\$2.40)"
    assert md("no amounts") == "no amounts"
    assert md(None) == "None" and md(12) == "12"


def test_every_free_text_render_goes_through_md():
    """Each st.markdown / st.error / st.warning / st.info / st.caption call that shows a free-text field wraps it in md()."""
    calls = re.findall(r"st\.(?:markdown|error|warning|info|caption)\((.*?)\)\s*$", SOURCE, flags=re.M)
    checked = 0
    for args in calls:
        for field in FREE_TEXT:
            for m in re.finditer(rf"\{{([^{{}}]*{field}[^{{}}]*)\}}", args):          # inside an f-string: {md(...)}
                assert m.group(1).lstrip().startswith("md("), f"not escaped: {m.group(0)!r} in st.*({args[:80]}...)"
                checked += 1
            for m in re.finditer(rf"\br\[\"{field}[^\"]*\"\]", args):                 # passed directly: md(r["..."])
                assert args[max(0, m.start() - 3):m.start()] == "md(", f"not escaped: {m.group(0)!r}"
                checked += 1
    for args in calls:                                   # the three reasons are shown in a loop: f"- {md(r[k])}"
        for m in re.finditer(r"\{([^{}]*\br\[k\][^{}]*)\}", args):
            assert m.group(1).lstrip().startswith("md("), f"not escaped: {m.group(0)!r}"
            checked += 1
    assert checked >= 7, checked   # banner, quote, review reasons, notes, the 3 reasons, counterfactual, blocked why
