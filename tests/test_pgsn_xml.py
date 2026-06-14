"""Tests for pgsn_xml: compile + fully_eval + python_value inspection."""

import pytest
from pathlib import Path
from pgsn.dsl import python_value
from pgsn.pgsn_xml import compile_pgsn, PGSNError, load_string
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

def test_ul(tmp_path):
    result = run("""
    <PGSN>
        <ul>
            <li>a</li>
            <li>b</li>
        </ul>
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
        <get label="label" of="obj"/>
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
        <get label="y" of="obj"/>
    </PGSN>""", tmp_path)
    assert result == "py"


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


def test_context_with_value(tmp_path):
    # Context carrying an arbitrary expression as payload
    result = run("""
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
    ctx = result["contexts"][0]
    assert ctx["description"] == "software version"
    assert ctx["value"] == "v1.2"


def test_assumption_with_value(tmp_path):
    # Assumption carrying an arbitrary expression as payload
    result = run("""
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
    assm = result["assumptions"][0]
    assert assm["description"] == "threat assumption"
    assert assm["value"] == "no insider threat"


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
        load_string(xml) -> fully-evaluated Term
        pgsn.gsn.gsn_tree(term) -> GSN tree (where a leftover App used to surface
                                   the "does not normalize a Python value" error)
    """

    def _to_tree(self, xml: str):
        """Compile + fully_eval, then build the GSN tree. Errors propagate."""
        term = load_string(xml)
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
            load_string(xml)

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
            load_string(xml)


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
            <ul>
                <li><Goal>G1<undeveloped/></Goal></li>
                <li><Goal>G2<undeveloped/></Goal></li>
            </ul>
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
                <get label="greeting" of="self"/>
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
                <get label="greeting" of="self"/>
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
                <get label="val" of="self"/>
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
# Integer literals
# ------------------------------------------------------------------ #

def test_integer_literal_in_arg(tmp_path):
    # Plain numeric text is parsed as Integer, not String
    result = run("""
    <PGSN>
        <apply template="plus">
            <arg>3</arg>
            <arg>5</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == 8


def test_integer_literal_in_def(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">42</def>
        <var name="n"/>
    </PGSN>""", tmp_path)
    assert result == 42


def test_string_not_confused_with_integer(tmp_path):
    # Text that isn't purely numeric stays a String
    result = run("""
    <PGSN>
        <def name="s">hello</def>
        <var name="s"/>
    </PGSN>""", tmp_path)
    assert result == "hello"


def test_integer_arithmetic(tmp_path):
    result = run("""
    <PGSN>
        <def name="x">3</def>
        <def name="y">4</def>
        <apply template="plus"><arg var="x"/><arg var="y"/></apply>
    </PGSN>""", tmp_path)
    assert result == 7


# ------------------------------------------------------------------ #
# {expr} inline expression expansion
# ------------------------------------------------------------------ #

def test_text_expr_simple_var(tmp_path):
    # {name} still works as before
    result = run("""
    <PGSN>
        <def name="f" as="template">
            <param name="name" positional="true"/>
            <Evidence>Hello {name}</Evidence>
        </def>
        <apply template="f"><arg>world</arg></apply>
    </PGSN>""", tmp_path)
    assert result["description"] == "Hello world"


def test_text_expr_arithmetic(tmp_path):
    # {x + 1} expands to plus(var(x), integer(1))
    result = run("""
    <PGSN>
        <def name="f" as="template">
            <param name="n" positional="true"/>
            <Evidence>Count: {n + 1}</Evidence>
        </def>
        <apply template="f"><arg>4</arg></apply>
    </PGSN>""", tmp_path)
    assert result["description"] == "Count: 5"


def test_text_expr_multiply(tmp_path):
    result = run("""
    <PGSN>
        <def name="f" as="template">
            <param name="n" positional="true"/>
            <Evidence>{n * 2} items</Evidence>
        </def>
        <apply template="f"><arg>3</arg></apply>
    </PGSN>""", tmp_path)
    assert result["description"] == "6 items"


def test_text_expr_two_vars(tmp_path):
    result = run("""
    <PGSN>
        <def name="f" as="template">
            <param name="a" positional="true"/>
            <param name="b" positional="true"/>
            <Evidence>{a + b} total</Evidence>
        </def>
        <apply template="f"><arg>10</arg><arg>5</arg></apply>
    </PGSN>""", tmp_path)
    assert result["description"] == "15 total"


def test_text_expr_equality_stringifies(tmp_path):
    # {x == y} is interpolated as a STRING (format_string semantics), not a
    # raw Boolean. To get a raw Boolean for use as a condition, use <expr>
    # instead of {...} — see test_expr_element_equality.
    result = run("""
    <PGSN>
        <def name="x">1</def>
        <Evidence>Result: {x == 1}</Evidence>
    </PGSN>""", tmp_path)
    assert result["description"] == "Result: True"


# ------------------------------------------------------------------ #
# <expr> element
# ------------------------------------------------------------------ #

def test_expr_element_arithmetic(tmp_path):
    result = run("""
    <PGSN>
        <def name="x">10</def>
        <def name="y">3</def>
        <expr>x + y</expr>
    </PGSN>""", tmp_path)
    assert result == 13


def test_expr_element_equality(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">5</def>
        <apply template="if_then_else">
            <arg><expr>n == 5</expr></arg>
            <arg>match</arg>
            <arg>no match</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "match"


def test_expr_element_complex(tmp_path):
    result = run("""
    <PGSN>
        <def name="a">3</def>
        <def name="b">4</def>
        <expr>a * a + b * b</expr>
    </PGSN>""", tmp_path)
    assert result == 25


def test_expr_element_unary_minus(tmp_path):
    result = run("""
    <PGSN>
        <def name="x">5</def>
        <expr>x + -3</expr>
    </PGSN>""", tmp_path)
    assert result == 2


# ------------------------------------------------------------------ #
# New builtins: repeat, fold, list_all, integer_sum
# ------------------------------------------------------------------ #

def test_builtin_repeat(tmp_path):
    # repeat(f, acc, n) applies f to acc n times
    result = run("""
    <PGSN>
        <def name="addOne" as="template">
            <param name="x" positional="true"/>
            <expr>x + 1</expr>
        </def>
        <apply template="repeat">
            <arg var="addOne"/>
            <arg>0</arg>
            <arg>5</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == 5


def test_builtin_fold(tmp_path):
    result = run("""
    <PGSN>
        <apply template="fold">
            <arg var="plus"/>
            <arg>0</arg>
            <arg><ol><li>1</li><li>2</li><li>3</li></ol></arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == 6


def test_builtin_integer_sum(tmp_path):
    result = run("""
    <PGSN>
        <apply template="integer_sum">
            <arg><ol><li>10</li><li>20</li><li>12</li></ol></arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == 42


def test_builtin_list_all(tmp_path):
    result = run("""
    <PGSN>
        <def name="isPos" as="template">
            <param name="x" positional="true"/>
            <apply template="equal"><arg><expr>x == x</expr></arg><arg var="true"/></apply>
        </def>
        <apply template="list_all">
            <arg var="isPos"/>
            <arg><ol><li>1</li><li>2</li><li>3</li></ol></arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result is True


# ------------------------------------------------------------------ #
# Comparison operators
# ------------------------------------------------------------------ #

def test_less_than(tmp_path):
    result = run("""
    <PGSN>
        <apply template="if_then_else">
            <arg><expr>3 &lt; 5</expr></arg>
            <arg>yes</arg>
            <arg>no</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "yes"


def test_greater_than(tmp_path):
    result = run("""
    <PGSN>
        <apply template="if_then_else">
            <arg><expr>10 > 5</expr></arg>
            <arg>yes</arg>
            <arg>no</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "yes"


def test_less_eq(tmp_path):
    result = run("""
    <PGSN>
        <apply template="if_then_else">
            <arg><expr>5 &lt;= 5</expr></arg>
            <arg>yes</arg>
            <arg>no</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "yes"


def test_greater_eq(tmp_path):
    result = run("""
    <PGSN>
        <apply template="if_then_else">
            <arg><expr>6 >= 5</expr></arg>
            <arg>yes</arg>
            <arg>no</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "yes"


def test_comparison_with_var(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">3</def>
        <apply template="if_then_else">
            <arg><expr>n &lt; 5</expr></arg>
            <arg>small</arg>
            <arg>large</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "small"


def test_comparison_builtin_direct(tmp_path):
    # less_than as a direct builtin call
    result = run("""
    <PGSN>
        <apply template="less_than">
            <arg>3</arg>
            <arg>5</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result is True


# ------------------------------------------------------------------ #
# Boolean operators: xor, implies, and/or/not in <expr>
# ------------------------------------------------------------------ #

def test_boolean_xor_builtin(tmp_path):
    result = run("""
    <PGSN>
        <apply template="boolean_xor">
            <arg var="true"/>
            <arg var="false"/>
        </apply>
    </PGSN>""", tmp_path)
    assert result is True


def test_boolean_xor_both_true(tmp_path):
    result = run("""
    <PGSN>
        <apply template="boolean_xor">
            <arg var="true"/>
            <arg var="true"/>
        </apply>
    </PGSN>""", tmp_path)
    assert result is False


def test_implies_builtin(tmp_path):
    # false implies anything -> true
    result = run("""
    <PGSN>
        <apply template="implies">
            <arg var="false"/>
            <arg var="false"/>
        </apply>
    </PGSN>""", tmp_path)
    assert result is True


def test_implies_true_false(tmp_path):
    # true implies false -> false
    result = run("""
    <PGSN>
        <apply template="implies">
            <arg var="true"/>
            <arg var="false"/>
        </apply>
    </PGSN>""", tmp_path)
    assert result is False


def test_expr_and(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">3</def>
        <apply template="if_then_else">
            <arg><expr>n > 0 and n &lt; 10</expr></arg>
            <arg>in range</arg>
            <arg>out of range</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "in range"


def test_expr_or(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">0</def>
        <apply template="if_then_else">
            <arg><expr>n &lt; 0 or n == 0</expr></arg>
            <arg>non-positive</arg>
            <arg>positive</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "non-positive"


def test_expr_not(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">5</def>
        <apply template="if_then_else">
            <arg><expr>not (n == 0)</expr></arg>
            <arg>nonzero</arg>
            <arg>zero</arg>
        </apply>
    </PGSN>""", tmp_path)
    assert result == "nonzero"


# ------------------------------------------------------------------ #
# <if cond="..."> shorthand for if_then_else
# ------------------------------------------------------------------ #

def test_if_cond_with_else(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">0</def>
        <if cond="n == 0">
            <then>base case</then>
            <else>recursive case</else>
        </if>
    </PGSN>""", tmp_path)
    assert result == "base case"


def test_if_cond_else_branch(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">5</def>
        <if cond="n == 0">
            <then>base case</then>
            <else>recursive case</else>
        </if>
    </PGSN>""", tmp_path)
    assert result == "recursive case"


def test_if_cond_without_else(tmp_path):
    # missing <else> uses undefined; the then-branch is taken when cond holds
    result = run("""
    <PGSN>
        <def name="ready" var="true"/>
        <if cond="ready">
            <then>done</then>
        </if>
    </PGSN>""", tmp_path)
    assert result == "done"


def test_if_cond_with_arithmetic(tmp_path):
    result = run("""
    <PGSN>
        <def name="x">3</def>
        <if cond="x &gt; 0 and x &lt; 10">
            <then>in range</then>
            <else>out of range</else>
        </if>
    </PGSN>""", tmp_path)
    assert result == "in range"


def test_if_cond_with_gsn_branches(tmp_path):
    # A general expression (here: if_then_else) used as a Goal's support
    # must be wrapped in <supportedBy>, per PGSN.rng's goal_pat: a bare
    # <if> is not a direct alternative of <Goal>'s choice. <undeveloped/>
    # is part of GSNNode, so it can be used as a general expression too
    # (e.g. as an <if>/<else> branch), not just as <Goal>'s direct child.
    result = run("""
    <PGSN>
        <def name="hasEvidence">1</def>
        <Goal>
            System is secure
            <supportedBy>
                <if cond="hasEvidence == 1">
                    <then><Evidence>Audit passed</Evidence></then>
                    <else><undeveloped/></else>
                </if>
            </supportedBy>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert gsn_type(result["support"]) == "Evidence"


def test_if_cond_simple_var(tmp_path):
    # cond can be a plain variable name, not just an expression
    result = run("""
    <PGSN>
        <def name="flag" var="false"/>
        <if cond="flag">
            <then>yes</then>
            <else>no</else>
        </if>
    </PGSN>""", tmp_path)
    assert result == "no"


# ------------------------------------------------------------------ #
# <if><cond>...</cond>...</if> child-element form
# ------------------------------------------------------------------ #

def test_if_cond_child_element_var_shorthand(tmp_path):
    # <cond var="x"/> as an alternative to cond="x"
    result = run("""
    <PGSN>
        <def name="flag" var="true"/>
        <if>
            <cond var="flag"/>
            <then>yes</then>
            <else>no</else>
        </if>
    </PGSN>""", tmp_path)
    assert result == "yes"


def test_if_cond_child_element_complex_expr(tmp_path):
    # <cond> can hold any expression, e.g. an <apply>
    result = run("""
    <PGSN>
        <def name="x">5</def>
        <if>
            <cond><apply template="greater_than"><arg var="x"/><arg>3</arg></apply></cond>
            <then>big</then>
            <else>small</else>
        </if>
    </PGSN>""", tmp_path)
    assert result == "big"


def test_if_missing_cond_error(tmp_path):
    # <if> without cond= and without <cond> child is an error
    p = tmp_path / "bad.pgsn"
    p.write_text("""
    <PGSN>
        <if><then>a</then><else>b</else></if>
    </PGSN>""")
    with pytest.raises(PGSNError):
        compile_pgsn(p)


# ------------------------------------------------------------------ #
# <cases>/<case>/<else>: a flat cascade of conditions
# ------------------------------------------------------------------ #

def test_cases_first_branch(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">0</def>
        <cases>
            <case cond="n == 0">zero</case>
            <case cond="n == 1">one</case>
            <case cond="n == 2">two</case>
            <else>many</else>
        </cases>
    </PGSN>""", tmp_path)
    assert result == "zero"


def test_cases_middle_branch(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">1</def>
        <cases>
            <case cond="n == 0">zero</case>
            <case cond="n == 1">one</case>
            <case cond="n == 2">two</case>
            <else>many</else>
        </cases>
    </PGSN>""", tmp_path)
    assert result == "one"


def test_cases_last_case_branch(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">2</def>
        <cases>
            <case cond="n == 0">zero</case>
            <case cond="n == 1">one</case>
            <case cond="n == 2">two</case>
            <else>many</else>
        </cases>
    </PGSN>""", tmp_path)
    assert result == "two"


def test_cases_falls_through_to_else(tmp_path):
    result = run("""
    <PGSN>
        <def name="n">99</def>
        <cases>
            <case cond="n == 0">zero</case>
            <case cond="n == 1">one</case>
            <case cond="n == 2">two</case>
            <else>many</else>
        </cases>
    </PGSN>""", tmp_path)
    assert result == "many"


def test_cases_without_final_else(tmp_path):
    # no <else>: falls through to undefined if nothing matches.
    # Here the second case matches, so undefined is never evaluated.
    result = run("""
    <PGSN>
        <def name="n">1</def>
        <cases>
            <case cond="n == 0">zero</case>
            <case cond="n == 1">one</case>
        </cases>
    </PGSN>""", tmp_path)
    assert result == "one"


def test_cases_cond_child_element(tmp_path):
    # <case> with a <cond> child element (var= shorthand), body is the
    # case's remaining content directly — no <then> wrapper.
    result = run("""
    <PGSN>
        <def name="flag" var="true"/>
        <cases>
            <case cond="false">first</case>
            <case><cond var="flag"/>second</case>
            <else>third</else>
        </cases>
    </PGSN>""", tmp_path)
    assert result == "second"


def test_cases_cond_child_complex_expr(tmp_path):
    # <cond> child can hold an arbitrary expression, e.g. <apply>
    result = run("""
    <PGSN>
        <def name="x">5</def>
        <cases>
            <case><cond><apply template="greater_than"><arg var="x"/><arg>10</arg></apply></cond>big</case>
            <case><cond><apply template="greater_than"><arg var="x"/><arg>0</arg></apply></cond>positive</case>
            <else>non-positive</else>
        </cases>
    </PGSN>""", tmp_path)
    assert result == "positive"


def test_cases_with_gsn_branches(tmp_path):
    # Same reasoning as test_if_cond_with_gsn_branches: a <cases> expression
    # used as support must be wrapped in <supportedBy>. <undeveloped/> is
    # part of GSNNode, so the fallback can use it directly as a branch value.
    result = run("""
    <PGSN>
        <def name="level">2</def>
        <Goal>
            System is secure
            <supportedBy>
                <cases>
                    <case cond="level == 1"><Evidence>Level 1 audit</Evidence></case>
                    <case cond="level == 2"><Evidence>Level 2 audit</Evidence></case>
                    <else><undeveloped/></else>
                </cases>
            </supportedBy>
        </Goal>
    </PGSN>""", tmp_path)
    assert gsn_type(result) == "Goal"
    assert gsn_type(result["support"]) == "Evidence"
    assert result["support"]["description"] == "Level 2 audit"


def test_cases_requires_at_least_one_case(tmp_path):
    p = tmp_path / "bad.pgsn"
    p.write_text("""
    <PGSN>
        <cases><else>fallback</else></cases>
    </PGSN>""")
    with pytest.raises(PGSNError):
        compile_pgsn(p)