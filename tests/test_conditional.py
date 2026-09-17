"""Conditionals.

`<if>` and `<cases>` are shorthands: desugaring rewrites them into an
application of the `if_then_else` builtin, the same way it rewrites `<expr>`.
Nothing is reachable through them that `<apply>` could not reach.
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


# ------------------------------------------------------------------ #
# <if>
# ------------------------------------------------------------------ #

def test_if_takes_the_then_branch():
    assert run('<if><cond><expr>i == 2</expr></cond><then>two</then>'
               '<else>other</else></if>', TWO) == "two"


def test_if_takes_the_else_branch():
    assert run('<if><cond><expr>i == 9</expr></cond><then>nine</then>'
               '<else>other</else></if>', TWO) == "other"


def test_a_condition_may_be_written_any_way_a_value_can():
    """<cond> is a wrapper, so a child element and the `var` shorthand both
    work, and so does anything else that stands for a value."""
    forms = ['<cond><expr>i &gt; 1</expr></cond>',
             '<cond><var name="yes"/></cond>',
             '<cond var="yes"/>']
    for cond in forms:
        assert run(f'<if>{cond}<then>big</then><else>small</else></if>',
                   TWO + '<def name="yes"><expr>True</expr></def>') == "big"


def test_a_branch_may_be_any_expression():
    assert run('<if><cond><expr>i == 2</expr></cond>'
               '<then><apply><var name="plus"/><arg var="i"/>'
               '<arg><num>1</num></arg></apply></then>'
               '<else><num>0</num></else></if>', TWO) == 3


def test_the_branch_not_taken_is_not_evaluated():
    """Otherwise a conditional could not guard a recursion."""
    assert run('<if><cond><expr>True</expr></cond><then>ok</then>'
               '<else><apply><var name="spin"/><arg><num>1</num></arg>'
               '</apply></else></if>',
               '<def name="spin" recursive="true"><template>'
               '<param name="n" positional="true"/>'
               '<apply><var name="spin"/><arg var="n"/></apply>'
               '</template></def>') == "ok"


def test_a_conditional_is_a_value_like_any_other():
    result = run('<Goal>the system is safe<Evidence>'
                 '<if><cond><expr>i == 2</expr></cond><then>report A</then>'
                 '<else>report B</else></if></Evidence></Goal>', TWO)
    assert result["support"]["description"] == "report A"


def test_if_rejects_missing_and_unknown_parts():
    with pytest.raises(PGSNError, match="exactly one <else>"):
        run('<if><cond><expr>True</expr></cond><then>t</then></if>')
    with pytest.raises(PGSNError, match="exactly one <cond>"):
        run('<if><then>t</then><else>e</else></if>')
    with pytest.raises(PGSNError, match="found <otherwise>"):
        run('<if><cond><expr>True</expr></cond><then>t</then>'
            '<otherwise>e</otherwise></if>')


# ------------------------------------------------------------------ #
# <cases>
# ------------------------------------------------------------------ #

CASES = ('<cases>'
         '<case><cond><expr>i == 0</expr></cond><then>none</then></case>'
         '<case><cond><expr>i == 1</expr></cond><then>one</then></case>'
         '<case><cond><expr>i == 2</expr></cond><then>two</then></case>'
         '<else>many</else></cases>')


@pytest.mark.parametrize("value,expected", [
    (0, "none"), (1, "one"), (2, "two"), (7, "many"),
])
def test_cases_picks_the_first_matching_branch(value, expected):
    assert run(CASES, f'<def name="i"><num>{value}</num></def>') == expected


def test_cases_stops_at_the_first_match():
    """Two conditions hold; the earlier one wins."""
    assert run('<cases>'
               '<case><cond><expr>True</expr></cond><then>first</then></case>'
               '<case><cond><expr>True</expr></cond><then>second</then></case>'
               '<else>neither</else></cases>') == "first"


def test_cases_nest():
    assert run('<cases><case><cond><expr>i == 2</expr></cond><then>'
               '<cases><case><cond><expr>True</expr></cond><then>inner</then></case>'
               '<else>x</else></cases></then></case>'
               '<else>y</else></cases>', TWO) == "inner"


def test_cases_requires_an_else():
    """A conditional with nothing to fall back on would simply get stuck, so
    the omission is rejected rather than left to surface as a stuck term."""
    with pytest.raises(PGSNError, match="must end in an <else>"):
        run('<cases><case><cond><expr>True</expr></cond><then>t</then></case></cases>')


def test_cases_rejects_an_empty_body_and_unknown_parts():
    with pytest.raises(PGSNError, match="at least one <case>"):
        run('<cases><else>e</else></cases>')
    with pytest.raises(PGSNError, match="found <when>"):
        run('<cases><when><cond><expr>True</expr></cond><then>t</then></when>'
            '<else>e</else></cases>')
    with pytest.raises(PGSNError, match="<case> takes <cond> and <then>"):
        run('<cases><case><cond><expr>True</expr></cond><value>t</value></case>'
            '<else>e</else></cases>')


# ------------------------------------------------------------------ #
# The expansion
# ------------------------------------------------------------------ #

def test_if_expands_to_an_application_of_the_builtin():
    assert expanded('<if><cond var="c"/><then>t</then><else>e</else></if>') == (
        '<apply><var name="_if_then_else" />'
        '<arg><var name="c" /></arg><arg>t</arg><arg>e</arg></apply>')


def test_a_conditional_cannot_be_intercepted():
    """`<if>` reaches the builtin by a name no document can bind."""
    assert run('<def name="if_then_else">not a conditional</def>'
               '<if><cond><expr>True</expr></cond><then>ok</then>'
               '<else>no</else></if>') == "ok"
