"""Tests for pgsn_xml: compile + fully_eval + python_value inspection."""

import pytest
from pathlib import Path
import pgsn
from pgsn.dsl import python_value
from pgsn.pgsn_term import LambdaInterpreterError
from pgsn.pgsn_xml import compile_pgsn, PGSNError, load_xml_string
from pgsn.gsn import gsn_tree


def run(xml: str, tmp_path: Path):
    """Write XML to a temp file, compile, fully_eval, and return python_value."""
    p = tmp_path / "test.pgsn"
    p.write_text(xml)
    return python_value(compile_pgsn(p).fully_eval(), with_inherit_chain=True)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def gsn_type(result: dict) -> str:
    """Return the GSN class name from the __ClassName__ marker key.

    Uses the dunder class-name key (e.g. '__Goal__') which is present at
    every nesting level, unlike '__parent_classes__' which to_python only
    attaches to the top-level term.
    """
    gsn = {"Goal", "Strategy", "Evidence", "Context", "Assumption", "Undeveloped"}
    for k in result:
        if k.startswith("__") and k.endswith("__"):
            name = k.strip("_")
            if name in gsn:
                return name
    return None


# ------------------------------------------------------------------ #
# Bare string value
# ------------------------------------------------------------------ #

def test_bare_string(tmp_path):
    result = run("<PGSN>hello</PGSN>", tmp_path)
    assert result == "hello"


# ------------------------------------------------------------------ #
# def and var
# ------------------------------------------------------------------ #

def test_def_and_var(tmp_path):
    result = run("""
    <PGSN>
        <def name="x">hello</def>
        <var name="x"/>
    </PGSN>""", tmp_path)
    assert result == "hello"


def test_def_chain(tmp_path):
    # Later def can depend on earlier def
    result = run("""
    <PGSN>
        <def name="x">hello</def>
        <def name="y"><var name="x"/></def>
        <var name="y"/>
    </PGSN>""", tmp_path)
    assert result == "hello"


# ------------------------------------------------------------------ #
# div (local scope)
# ------------------------------------------------------------------ #

def test_div_local_scope(tmp_path):
    result = run("""
    <PGSN>
        <div>
            <def name="x">inner</def>
            <var name="x"/>
        </div>
    </PGSN>""", tmp_path)
    assert result == "inner"


# ------------------------------------------------------------------ #
# ul / ol / dl
# ------------------------------------------------------------------ #

def test_ol(tmp_path):
    result = run("""
    <PGSN>
        <ol>
            <li>a</li>
            <li>b</li>
        </ol>
    </PGSN>""", tmp_path)
    assert result == ["a", "b"]


def test_ol(tmp_path):
    result = run("""
    <PGSN>
        <ol>
            <li>x</li>
            <li>y</li>
        </ol>
    </PGSN>""", tmp_path)
    assert result == ["x", "y"]


def test_dl(tmp_path):
    result = run("""
    <PGSN>
        <dl>
            <dt key="name"/><dd>Alice</dd>
            <dt key="role"/><dd>Admin</dd>
        </dl>
    </PGSN>""", tmp_path)
    assert result["name"] == "Alice"
    assert result["role"] == "Admin"


# ------------------------------------------------------------------ #
# template + apply
# ------------------------------------------------------------------ #

def test_template_apply(tmp_path):
    result = run("""
    <PGSN>
        <def name="f">
            <template>
                <param name="x"/>
                <var name="x"/>
            </template>
        </def>
        <apply>
            <var name="f"/>
            <arg name="x">result</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "result"



# ------------------------------------------------------------------ #
# recursive def
# ------------------------------------------------------------------ #

def test_positional_args(tmp_path):
    # if_then_else is a positional-argument builtin
    result = run("""
    <PGSN>
        <apply>
            <var name="if_then_else"/>
            <arg><var name="true"/></arg>
            <arg>yes</arg>
            <arg>no</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "yes"


def test_recursive_def(tmp_path):
    # A recursive template that immediately returns via its base case.
    # Verifies that fix-wrapping and self-reference compile and evaluate.
    result = run("""
    <PGSN>
        <def name="pick" recursive="true">
            <template>
                <param name="cond"/>
                <apply>
                    <var name="if_then_else"/>
                    <arg><var name="cond"/></arg>
                    <arg>stop</arg>
                    <arg>
                        <apply>
                            <var name="pick"/>
                            <arg name="cond"><var name="true"/></arg>
                        </apply>
                    </arg>
                </apply>
            </template>
        </def>
        <apply>
            <var name="pick"/>
            <arg name="cond"><var name="false"/></arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "stop"


# ------------------------------------------------------------------ #
# class + object + get
# ------------------------------------------------------------------ #

def test_class_object_get(tmp_path):
    result = run("""
    <PGSN>
        <def name="MyClass">
            <class>
                <attribute name="label"/>
            </class>
        </def>
        <def name="obj">
            <object>
                <instanceOf var="MyClass"/>
                <attribute name="label">test_label</attribute>
            </object>
        </def>
        <get key="label" of="obj"/>
    </PGSN>""", tmp_path)
    assert result == "test_label"


def test_class_inheritance(tmp_path):
    result = run("""
    <PGSN>
        <def name="Base">
            <class>
                <attribute name="x"/>
            </class>
        </def>
        <def name="Child">
            <class>
                <inherit><var name="Base"/></inherit>
                <attribute name="y"/>
            </class>
        </def>
        <def name="obj">
            <object>
                <instanceOf var="Child"/>
                <attribute name="x">px</attribute>
                <attribute name="y">py</attribute>
            </object>
        </def>
        <get key="y" of="obj"/>
    </PGSN>""", tmp_path)
    assert result == "py"


# ------------------------------------------------------------------ #
# typeOf
# ------------------------------------------------------------------ #

def test_type_of_admits_a_goal(tmp_path):
    """The check that used to stall. `goal_class` defaults `support` to an
    application, and the predicate behind the old `instanceOf` compared
    classes structurally, so it answered False for every goal.
    """
    result = run("""
    <PGSN>
        <def name="g" typeOf="Goal">
            <Goal>
                <description>system is safe</description>
                <undeveloped/>
            </Goal>
        </def>
        <var name="g"/>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert result["description"] == "system is safe"


def test_type_of_is_structural(tmp_path):
    """A class of one's own satisfies Evidence by carrying its labels. Nothing
    connects MyNode to the GSN classes.
    """
    result = run("""
    <PGSN>
        <def name="MyNode" as="class">
            <attribute name="description"/>
            <attribute name="defeaters"/>
            <attribute name="owner"/>
        </def>
        <def name="n" typeOf="Evidence">
            <object>
                <instanceOf var="MyNode"/>
                <attribute name="description">an audit</attribute>
                <attribute name="defeaters"><ol/></attribute>
                <attribute name="owner">QA</attribute>
            </object>
        </def>
        <get key="owner" of="n"/>
    </PGSN>""", tmp_path)
    assert result == "QA"


def test_type_of_stalls_when_a_label_is_missing(tmp_path):
    """An evidence node carries no `support`, so it does not satisfy Goal. A
    failed check leaves the document unreduced, and the readback says where.
    """
    with pytest.raises(ValueError, match="unexpected term type"):
        run("""
        <PGSN>
            <def name="e" typeOf="Goal">
                <Evidence><description>a report</description></Evidence>
            </def>
            <var name="e"/>
        </PGSN>""", tmp_path)


def test_type_of_on_a_var_reference(tmp_path):
    result = run("""
    <PGSN>
        <def name="g">
            <Goal>
                <description>system is safe</description>
                <undeveloped/>
            </Goal>
        </def>
        <var name="g" typeOf="Goal"/>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"


@pytest.mark.parametrize("source", [
    '<ol><li><ul><li>a</li></ul></li></ol>',
    '<def name="xs" as="ul"><li>a</li></def><var name="xs"/>',
])
def test_there_is_no_ul_element(source, tmp_path):
    """There is one list and it is ordered, so `ul` is not an element."""
    with pytest.raises(PGSNError, match="Unknown expression"):
        run(f"<PGSN>{source}</PGSN>", tmp_path)


# ------------------------------------------------------------------ #
# GSN: Evidence
# ------------------------------------------------------------------ #

def test_evidence(tmp_path):
    result = run("""
    <PGSN>
        <Evidence>
            <description>test report passed</description>
        </Evidence>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Evidence"
    assert result["description"] == "test report passed"


# ------------------------------------------------------------------ #
# GSN: Goal with undeveloped
# ------------------------------------------------------------------ #

def test_goal_undeveloped(tmp_path):
    result = run("""
    <PGSN>
        <Goal>
            <description>system is safe</description>
            <undeveloped/>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert result["description"] == "system is safe"


# ------------------------------------------------------------------ #
# GSN: Goal → Strategy → Evidence
# ------------------------------------------------------------------ #

def test_goal_strategy_evidence(tmp_path):
    result = run("""
    <PGSN>
        <Goal>
            <description>system is secure</description>
            <Strategy>
                argument text
                <Goal>
                    <description>input validated</description>
                    <Evidence>
                        <description>static analysis passed</description>
                    </Evidence>
                </Goal>
            </Strategy>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert result["description"] == "system is secure"
    support = result["support"]
    assert gsn_type(support) == "Strategy"


# ------------------------------------------------------------------ #
# GSN: Context and Assumption (documentation only, same structure)
# ------------------------------------------------------------------ #

def test_context_text(tmp_path):
    result = run("""
    <PGSN>
        <Goal>
            <description>G1</description>
            <Context>certified under IEC 61508</Context>
            <undeveloped/>
        </Goal>
    </PGSN>""", tmp_path)
    ctx = result["contexts"][0]
    assert gsn_type(ctx) == "Context"
    assert ctx["description"] == "certified under IEC 61508"


def test_assumption_text(tmp_path):
    result = run("""
    <PGSN>
        <Goal>
            <description>G1</description>
            <Assumption>no zero-day attacks</Assumption>
            <undeveloped/>
        </Goal>
    </PGSN>""", tmp_path)
    assm = result["assumptions"][0]
    assert gsn_type(assm) == "Assumption"
    assert assm["description"] == "no zero-day attacks"


def test_context_description_from_variable(tmp_path):
    # `var=` expands to a <var> child, and for a documentation node that
    # child is the statement itself: the string lands in `description`.
    result = run("""
    <PGSN>
        <def name="version">certified under IEC 61508</def>
        <Goal>
            <description>G1</description>
            <Context var="version"/>
            <undeveloped/>
        </Goal>
    </PGSN>""", tmp_path)
    ctx = result["contexts"][0]
    assert gsn_type(ctx) == "Context"
    assert ctx["description"] == "certified under IEC 61508"


def test_assumption_description_from_variable(tmp_path):
    result = run("""
    <PGSN>
        <def name="threat_model">no insider threat</def>
        <Goal>
            <description>G1</description>
            <Assumption var="threat_model"/>
            <undeveloped/>
        </Goal>
    </PGSN>""", tmp_path)
    assm = result["assumptions"][0]
    assert gsn_type(assm) == "Assumption"
    assert assm["description"] == "no insider threat"


def test_context_description_from_expression_child(tmp_path):
    # The expanded spelling means the same thing as the attribute shorthand.
    result = run("""
    <PGSN>
        <def name="version">v1.2</def>
        <Goal>
            <description>G1</description>
            <Context><var name="version"/></Context>
            <undeveloped/>
        </Goal>
    </PGSN>""", tmp_path)
    assert result["contexts"][0]["description"] == "v1.2"


def test_context_rejects_description_and_expression(tmp_path):
    # A documentation node holds one statement, so writing both a
    # <description> and an expression is rejected rather than silently
    # dropping one of them.
    with pytest.raises(PGSNError, match="single statement"):
        run("""
        <PGSN>
            <def name="version">v1.2</def>
            <Goal>
                <description>G1</description>
                <Context>
                    <description>software version</description>
                    <var name="version"/>
                </Context>
                <undeveloped/>
            </Goal>
        </PGSN>""", tmp_path)


def test_assumption_rejects_description_and_expression(tmp_path):
    with pytest.raises(PGSNError, match="single statement"):
        run("""
        <PGSN>
            <def name="threat_model">no insider threat</def>
            <Goal>
                <description>G1</description>
                <Assumption>
                    <description>threat assumption</description>
                    <var name="threat_model"/>
                </Assumption>
                <undeveloped/>
            </Goal>
        </PGSN>""", tmp_path)


def test_context_rejects_two_expressions(tmp_path):
    with pytest.raises(PGSNError, match="single statement"):
        run("""
        <PGSN>
            <def name="a">one</def>
            <def name="b">two</def>
            <Goal>
                <description>G1</description>
                <Context><var name="a"/><var name="b"/></Context>
                <undeveloped/>
            </Goal>
        </PGSN>""", tmp_path)


def test_context_and_assumption_on_a_strategy(tmp_path):
    # A strategy carries contexts and assumptions of its own: GSN allows
    # InContextOf from a strategy, and the constructor once bound them and
    # dropped them without a word. Written on a strategy they have to reach
    # the term, the same way they do on a goal.
    result = run("""
    <PGSN>
        <Strategy>
            <description>argue over each identified hazard</description>
            <Context>hazard log rev 3</Context>
            <Assumption>all hazards have been identified</Assumption>
            <Goal>
                <description>H1 is mitigated</description>
                <undeveloped/>
            </Goal>
        </Strategy>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Strategy"
    ctx = result["contexts"][0]
    assert gsn_type(ctx) == "Context"
    assert ctx["description"] == "hazard log rev 3"
    assm = result["assumptions"][0]
    assert gsn_type(assm) == "Assumption"
    assert assm["description"] == "all hazards have been identified"


# ------------------------------------------------------------------ #
# GSN: supportedBy variable reference
# ------------------------------------------------------------------ #

def test_supported_by_var(tmp_path):
    result = run("""
    <PGSN>
        <def name="ev">
            <Evidence>
                <description>audit log</description>
            </Evidence>
        </def>
        <Goal>
            <description>system logged</description>
            <supportedBy><var name="ev"/></supportedBy>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert gsn_type(result["support"]) == "Evidence"


# ------------------------------------------------------------------ #
# Error cases
# ------------------------------------------------------------------ #

def test_unsafe_path(tmp_path):
    p = tmp_path / "test.pgsn"
    p.write_text('<PGSN><from file="../evil.pgsn" import="x"/><var name="x"/></PGSN>')
    with pytest.raises(PGSNError, match="Unsafe"):
        compile_pgsn(p)


def test_missing_value(tmp_path):
    p = tmp_path / "test.pgsn"
    p.write_text("<PGSN></PGSN>")
    with pytest.raises(PGSNError):
        compile_pgsn(p)


def test_unknown_expression(tmp_path):
    p = tmp_path / "test.pgsn"
    p.write_text("<PGSN><bogus/></PGSN>")
    with pytest.raises(PGSNError, match="Unknown expression"):
        compile_pgsn(p)


def test_wrong_root(tmp_path):
    p = tmp_path / "test.pgsn"
    p.write_text("<PGSNModule><def name='x'>y</def></PGSNModule>")
    with pytest.raises(PGSNError, match="Expected <PGSN>"):
        compile_pgsn(p)


# ------------------------------------------------------------------ #
# Positional template parameters
# ------------------------------------------------------------------ #

class TestPositionalParams:
    """Regression tests for positional vs keyword <template> parameters.

    Background
    ----------
    `<template>` parameters are split into a positional group (marked
    ``positional="true"``) and a keyword group (the default). Following Python's
    convention, positional params must precede keyword params. The compiler emits a
    two-layer lambda: an outer ``lambda_abs_vars`` for the positional params and an
    inner ``lambda_abs_keywords`` for the keyword params. This matches
    ``Term.__call__``, which applies positional args as ``f a b ...`` and passes
    keyword args as one trailing Record.

    Pipeline under test (mirrors examples/map_term.py):
        load_xml_string(xml) -> fully-evaluated Term
        pgsn.gsn.gsn_tree(term) -> GSN tree (where a leftover App used to surface
                                   the "does not normalize a Python value" error)
    """

    def _to_tree(self, xml: str):
        """Compile + fully_eval, then build the GSN tree. Errors propagate."""
        term = load_xml_string(xml)
        tree = gsn_tree(term)
        tree.show()
        return tree

    def test_positional_via_map_term(self, capsys):
        xml = """
        <PGSN>
            <def name="goalTemplate" as="template">
                <param name="desc" positional="true"/>
                <Goal><description var="desc"/><Evidence><description var="desc"/></Evidence></Goal>
            </def>
            <def name="goals" as="apply">
                <var name="map_term"/>
                <arg var="goalTemplate"/>
                <arg><ol><li>Firewall enabled</li><li>Encrypted communication</li></ol></arg>
            </def>
            <Goal>
                Security requirements fulfilled
                <supportedBy><apply><var name="immediate"/><arg var="goals"/></apply></supportedBy>
            </Goal>
        </PGSN>
        """
        self._to_tree(xml)  # must not raise

    def test_keyword_application(self, capsys):
        xml = """
        <PGSN>
            <def name="mk" as="template">
                <param name="desc"/>
                <Goal><description var="desc"/><Evidence><description var="desc"/></Evidence></Goal>
            </def>
            <def name="g" as="apply"><var name="mk"/><arg name="desc">No hardcoded passwords</arg></def>
            <var name="g"/>
        </PGSN>
        """
        self._to_tree(xml)  # must not raise

    def test_mixed_positional_then_keyword(self, capsys):
        xml = """
        <PGSN>
            <def name="mk" as="template">
                <param name="desc" positional="true"/>
                <param name="ev"/>
                <Goal><description var="desc"/><Evidence><description var="ev"/></Evidence></Goal>
            </def>
            <def name="g" as="apply"><var name="mk"/><arg>System is secure</arg><arg name="ev">Audit passed</arg></def>
            <var name="g"/>
        </PGSN>
        """
        self._to_tree(xml)  # must not raise

    def test_keyword_before_positional_rejected(self):
        xml = """
        <PGSN>
            <def name="mk" as="template">
                <param name="kw"/>
                <param name="pos" positional="true"/>
                <var name="pos"/>
            </def>
            <var name="mk"/>
        </PGSN>
        """
        with pytest.raises(PGSNError):
            load_xml_string(xml)

    def test_positional_with_default_rejected(self):
        xml = """
        <PGSN>
            <def name="mk" as="template">
                <param name="pos" positional="true">some default</param>
                <var name="pos"/>
            </def>
            <var name="mk"/>
        </PGSN>
        """
        with pytest.raises(PGSNError):
            load_xml_string(xml)


# ------------------------------------------------------------------ #
# template with inner defs (no wrapping div needed)
# ------------------------------------------------------------------ #

def test_template_inner_defs(tmp_path):
    # <template> body can contain <def>s before the final value,
    # equivalent to wrapping them in a <div>.
    result = run("""
    <PGSN>
        <def name="f">
            <template>
                <param name="x"/>
                <def name="a"><var name="x"/></def>
                <def name="b"><var name="a"/></def>
                <var name="b"/>
            </template>
        </def>
        <apply><var name="f"/><arg name="x">hello</arg></apply>
    </PGSN>""", tmp_path)
    assert result == "hello"


def test_template_inner_defs_gsn(tmp_path):
    # Inner defs in a template that builds a GSN node.
    result = run("""
    <PGSN>
        <def name="makeGoal">
            <template>
                <param name="desc"/>
                <def name="ev"><Evidence><description var="desc"/></Evidence></def>
                <Goal>
                    <description var="desc"/>
                    <supportedBy var="ev"/>
                </Goal>
            </template>
        </def>
        <apply><var name="makeGoal"/><arg name="desc">system is safe</arg></apply>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert result["description"] == "system is safe"
    assert gsn_type(result["support"]) == "Evidence"


def test_template_inner_defs_equiv_div(tmp_path):
    # template with inner defs must produce the same result as wrapping in div.
    with_defs = run("""
    <PGSN>
        <def name="f">
            <template>
                <param name="x"/>
                <def name="y"><var name="x"/></def>
                <var name="y"/>
            </template>
        </def>
        <apply><var name="f"/><arg name="x">ok</arg></apply>
    </PGSN>""", tmp_path)

    with_div = run("""
    <PGSN>
        <def name="f">
            <template>
                <param name="x"/>
                <div>
                    <def name="y"><var name="x"/></def>
                    <var name="y"/>
                </div>
            </template>
        </def>
        <apply><var name="f"/><arg name="x">ok</arg></apply>
    </PGSN>""", tmp_path)

    assert with_defs == with_div


def test_template_inner_non_def_before_value_error(tmp_path):
    # A non-def element before the final value is an error.
    p = tmp_path / "bad.pgsn"
    p.write_text("""
    <PGSN>
        <def name="f">
            <template>
                <param name="x"/>
                <var name="x"/>
                <def name="y">oops</def>
                <var name="y"/>
            </template>
        </def>
        <apply><var name="f"/><arg name="x">v</arg></apply>
    </PGSN>""")
    with pytest.raises(PGSNError):
        compile_pgsn(p)


# ------------------------------------------------------------------ #
# GSN text lift: leading text -> <description>
# ------------------------------------------------------------------ #

def test_gsn_text_lift_goal(tmp_path):
    # Leading text in a Goal with sibling children is lifted to <description>.
    result = run("""
    <PGSN>
        <Goal>
            system is secure
            <Evidence>static analysis passed</Evidence>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert result["description"] == "system is secure"


def test_gsn_text_lift_strategy(tmp_path):
    result = run("""
    <PGSN>
        <Goal>
            top goal
            <Strategy>
                argument by decomposition
                <Goal>
                    sub goal
                    <undeveloped/>
                </Goal>
            </Strategy>
        </Goal>
    </PGSN>""", tmp_path)
    assert result["description"] == "top goal"
    assert result["support"]["description"] == "argument by decomposition"


# ------------------------------------------------------------------ #
# {var} inline text expansion
# ------------------------------------------------------------------ #

def test_text_expansion_in_description(tmp_path):
    result = run("""
    <PGSN>
        <def name="f">
            <template>
                <param name="name"/>
                <Goal>
                    System {name} is secure
                    <undeveloped/>
                </Goal>
            </template>
        </def>
        <apply><var name="f"/><arg name="name">Alpha</arg></apply>
    </PGSN>""", tmp_path)
    assert result["description"] == "System Alpha is secure"


def test_text_expansion_in_evidence(tmp_path):
    result = run("""
    <PGSN>
        <def name="f">
            <template>
                <param name="c"/>
                <Evidence>Test doc for {c}</Evidence>
            </template>
        </def>
        <apply><var name="f"/><arg name="c">C1</arg></apply>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Evidence"
    assert result["description"] == "Test doc for C1"


def test_text_expansion_multiple_fields(tmp_path):
    result = run("""
    <PGSN>
        <def name="f">
            <template>
                <param name="a"/>
                <param name="b"/>
                <Evidence>{a} and {b}</Evidence>
            </template>
        </def>
        <apply>
            <var name="f"/>
            <arg name="a">foo</arg>
            <arg name="b">bar</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result["description"] == "foo and bar"


def test_text_expansion_escaped_braces(tmp_path):
    # {{ and }} are Python str.format escapes for literal braces.
    result = run("""
    <PGSN>
        <Evidence>{{not a var}}</Evidence>
    </PGSN>""", tmp_path)
    assert result["description"] == "{not a var}"


def test_text_no_expansion_without_braces(tmp_path):
    # Plain text without {} must pass through unchanged.
    result = run("""
    <PGSN>
        <Evidence>plain text no braces</Evidence>
    </PGSN>""", tmp_path)
    assert result["description"] == "plain text no braces"


# ------------------------------------------------------------------ #
# var attribute shorthand
# ------------------------------------------------------------------ #

def test_var_attribute_on_arg(tmp_path):
    result = run("""
    <PGSN>
        <def name="x">hello</def>
        <def name="f">
            <template>
                <param name="v"/>
                <var name="v"/>
            </template>
        </def>
        <apply>
            <var name="f"/>
            <arg name="v" var="x"/>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "hello"


def test_var_attribute_on_supportedBy(tmp_path):
    result = run("""
    <PGSN>
        <def name="ev"><Evidence>audit passed</Evidence></def>
        <Goal>
            logged
            <supportedBy var="ev"/>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert gsn_type(result["support"]) == "Evidence"


def test_var_attribute_on_subGoals(tmp_path):
    result = run("""
    <PGSN>
        <def name="goals">
            <ol>
                <li><Goal>G1<undeveloped/></Goal></li>
                <li><Goal>G2<undeveloped/></Goal></li>
            </ol>
        </def>
        <Goal>
            top
            <Strategy>
                by decomposition
                <subGoals var="goals"/>
            </Strategy>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert gsn_type(result["support"]) == "Strategy"


def test_var_attribute_with_children_error(tmp_path):
    # var attribute + child elements is an error.
    p = tmp_path / "bad.pgsn"
    p.write_text("""
    <PGSN>
        <def name="x">hello</def>
        <arg var="x"><string>extra</string></arg>
    </PGSN>""")
    with pytest.raises(PGSNError):
        compile_pgsn(p)


# ------------------------------------------------------------------ #
# apply template= shorthand
# ------------------------------------------------------------------ #

def test_apply_template_attribute(tmp_path):
    # <apply template="f"> is shorthand for <apply><var name="f"/>...</apply>
    result = run("""
    <PGSN>
        <def name="greet">
            <template>
                <param name="name"/>
                <var name="name"/>
            </template>
        </def>
        <apply template="greet">
            <arg name="name">world</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "world"


def test_apply_template_positional(tmp_path):
    # template= with positional argument
    result = run("""
    <PGSN>
        <def name="wrap" as="template">
            <param name="x" positional="true"/>
            <Evidence>{x}</Evidence>
        </def>
        <apply template="wrap">
            <arg>component A</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Evidence"
    assert result["description"] == "component A"


def test_apply_template_equiv_var(tmp_path):
    # apply template= must produce the same result as explicit <var>
    with_attr = run("""
    <PGSN>
        <def name="f" as="template">
            <param name="x"/>
            <var name="x"/>
        </def>
        <apply template="f"><arg name="x">ok</arg></apply>
    </PGSN>""", tmp_path)

    with_var = run("""
    <PGSN>
        <def name="f" as="template">
            <param name="x"/>
            <var name="x"/>
        </def>
        <apply><var name="f"/><arg name="x">ok</arg></apply>
    </PGSN>""", tmp_path)

    assert with_attr == with_var


def test_apply_template_builtin(tmp_path):
    # template= also works with builtin names
    result = run("""
    <PGSN>
        <apply template="if_then_else">
            <arg var="true"/>
            <arg>yes</arg>
            <arg>no</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "yes"


# ------------------------------------------------------------------ #
# send method= / to= shorthand
# ------------------------------------------------------------------ #

def test_send_method_to(tmp_path):
    # <send method="m" to="obj"> shorthand: method call on a variable receiver.
    result = run("""
    <PGSN>
        <def name="Greeter" as="class">
            <attribute name="greeting"/>
            <method name="greet">
                <get key="greeting" of="self"/>
            </method>
        </def>
        <def name="g" as="object">
            <instanceOf var="Greeter"/>
            <attribute name="greeting">hello</attribute>
        </def>
        <send method="greet" to="g"/>
    </PGSN>""", tmp_path)
    assert result == "hello"


def test_send_method_without_to(tmp_path):
    # send method= without to= uses the first child element as receiver.
    result = run("""
    <PGSN>
        <def name="Greeter" as="class">
            <attribute name="greeting"/>
            <method name="greet">
                <get key="greeting" of="self"/>
            </method>
        </def>
        <def name="g" as="object">
            <instanceOf var="Greeter"/>
            <attribute name="greeting">hello</attribute>
        </def>
        <send method="greet">
            <var name="g"/>
        </send>
    </PGSN>""", tmp_path)
    assert result == "hello"


def test_send_method_to_equiv_without_to(tmp_path):
    # send method= to= must produce the same result as method= with explicit
    # child var element as receiver (the two ways of specifying the receiver).
    xml_base = """
    <PGSN>
        <def name="Wrapper" as="class">
            <attribute name="val"/>
            <method name="unwrap">
                <get key="val" of="self"/>
            </method>
        </def>
        <def name="w" as="object">
            <instanceOf var="Wrapper"/>
            <attribute name="val">abc</attribute>
        </def>
        {send_form}
    </PGSN>"""

    with_to = run(
        xml_base.format(send_form='<send method="unwrap" to="w"/>'),
        tmp_path)

    without_to = run(
        xml_base.format(send_form='<send method="unwrap"><var name="w"/></send>'),
        tmp_path)

    assert with_to == without_to

# ------------------------------------------------------------------ #
# A class carries its own name
# ------------------------------------------------------------------ #

def test_an_object_is_reported_under_its_class_name(tmp_path):
    """The name travels with the class, so an instance of it says what it is.
    It is not the binding: `<def>` names a value in a scope, `name=` names the
    class itself."""
    result = run("""
    <PGSN>
        <def name="Component">
            <class name="Component">
                <attribute name="part"/>
            </class>
        </def>
        <def name="c">
            <object>
                <instanceOf var="Component"/>
                <attribute name="part">sensor</attribute>
            </object>
        </def>
        <var name="c"/>
    </PGSN>""", tmp_path)
    assert result["part"] == "sensor"
    assert result["__Component__"] is True


def test_an_object_of_an_anonymous_class_cannot_be_reported(tmp_path):
    """There is nothing to report it as, so the conversion says so rather
    than producing a value with a hole in it."""
    with pytest.raises(ValueError, match="class has no name"):
        run("""
        <PGSN>
            <def name="Component">
                <class><attribute name="part"/></class>
            </def>
            <object>
                <instanceOf var="Component"/>
                <attribute name="part">sensor</attribute>
            </object>
        </PGSN>""", tmp_path)


# ------------------------------------------------------------------ #
# The evaluation budget
# ------------------------------------------------------------------ #

DOC = ('<PGSN><apply><var name="plus"/>'
       '<arg><num>1</num></arg><arg><num>2</num></arg></apply></PGSN>')


def test_a_budget_too_small_to_finish_is_reported():
    """The budget belongs to the caller, so the loaders have to take one.
    Without this a program could not evaluate what `pgsn doc` evaluates:
    the command allows ten times what `fully_eval` does by default."""
    with pytest.raises(LambdaInterpreterError):
        pgsn.load_xml_string(DOC, steps=1)


def test_a_budget_large_enough_finishes():
    assert python_value(pgsn.load_xml_string(DOC, steps=1000)) == 3


def test_the_file_loader_takes_a_budget_too(tmp_path):
    path = tmp_path / "budget.xml"
    path.write_text(DOC)
    with pytest.raises(LambdaInterpreterError):
        pgsn.load_xml(path, steps=1)
    assert python_value(pgsn.load_xml(path, steps=1000)) == 3
