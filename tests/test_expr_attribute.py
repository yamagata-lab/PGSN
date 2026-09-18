"""The `expr` attribute: shorthand for an `<expr>` child.

The parallel is with `var`, which is shorthand for a `<var>` child. Neither is
tied to a particular element: wherever a value is expected, the attribute says
what the child would have said.
"""

import xml.etree.ElementTree as ET

import pytest

import pgsn
from pgsn.pgsn_xml import PGSNError, _desugar


def run(source: str, defs: str = ""):
    return pgsn.python_value(pgsn.load_xml_string(f"<PGSN>{defs}{source}</PGSN>"))


def expanded(source: str) -> str:
    root = ET.fromstring(f"<PGSN>{source}</PGSN>")
    _desugar(root)
    return ET.tostring(root[0], encoding="unicode")


TWO = '<def name="i"><num>2</num></def>'


def test_the_attribute_says_what_the_child_says():
    assert expanded('<arg expr="1 + 2"/>') == expanded(
        '<arg><expr>1 + 2</expr></arg>')


@pytest.mark.parametrize("source,expected", [
    ('<apply><var name="plus"/><arg expr="i"/><arg expr="i * 10"/></apply>', 22),
    ('<def name="n" expr="i + 1"/><var name="n"/>', 3),
    ('<ol><li expr="i * 2"/><li expr="i - 2"/></ol>', [4, 0]),
    ('<dl><dt key="k"/><dd expr="i + 1"/></dl>', {"k": 3}),
    ('<div><def name="m" expr="i * 3"/><var name="m"/></div>', 6),
])
def test_it_works_wherever_a_value_is_expected(source, expected):
    assert run(source, TWO) == expected


def test_it_works_in_a_gsn_node():
    result = run('<Goal><description expr=\'f"requirement {i} is met"\'/>'
                 '<Evidence expr=\'f"test report {i}"\'/></Goal>', TWO)
    assert result["description"] == "requirement 2 is met"
    assert result["support"]["description"] == "test report 2"


def test_it_works_in_a_condition():
    """The shorthand is what makes `<if>` read as a conditional rather than as
    a stack of wrappers."""
    assert run('<if><cond expr="i == 2"/><then>two</then>'
               '<else>other</else></if>', TWO) == "two"
    assert run('<cases><case><cond expr="i == 0"/><then>none</then></case>'
               '<case><cond expr="i == 2"/><then>two</then></case>'
               '<else>many</else></cases>', TWO) == "two"


def test_an_f_string_needs_the_attribute_quoted_with_apostrophes():
    assert run('<def name="s" expr=\'f"component {i}"\'/>'
               '<var name="s"/>', TWO) == "component 2"


def test_a_less_than_must_be_escaped():
    assert run('<def name="b" expr="i &lt; 3"/><var name="b"/>', TWO) is True


def test_the_attribute_conflicts_with_content_of_its_own():
    with pytest.raises(PGSNError, match="both an 'expr' attribute"):
        run('<apply><var name="head"/><arg expr="1 + 2">also text</arg></apply>')
    with pytest.raises(PGSNError, match="both an 'expr' attribute"):
        run('<ol><li expr="1"><num>2</num></li></ol>')


def test_the_expression_is_checked_like_any_other():
    """It goes through the same expansion, so the same rules apply."""
    with pytest.raises(PGSNError, match="Call is not allowed"):
        run('<ol><li expr="f(x)"/></ol>')
    with pytest.raises(PGSNError, match="not a valid name"):
        run('<ol><li expr="_plus"/></ol>')
