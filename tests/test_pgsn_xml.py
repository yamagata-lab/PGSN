"""Tests for pgsn_xml: compile + fully_eval + python_value inspection."""

import pytest
from pathlib import Path
from pgsn.dsl import python_value
from pgsn.pgsn_xml import compile_pgsn, PGSNError


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
                <instanceOf><var name="MyClass"/></instanceOf>
                <attribute name="label">test_label</attribute>
            </object>
        </def>
        <get name="label"><var name="obj"/></get>
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
                <instanceOf><var name="Child"/></instanceOf>
                <attribute name="x">px</attribute>
                <attribute name="y">py</attribute>
            </object>
        </def>
        <get name="y"><var name="obj"/></get>
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