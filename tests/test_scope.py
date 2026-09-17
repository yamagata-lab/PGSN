"""Scope rules: rebinding, and the scope the builtins live in.

Two rules, and they are the same rule seen twice. A block's bindings are
threaded into nested lets, so a later binding shadows an earlier one and a
binding's value is compiled in the scope *before* it. The builtins are the
outermost such scope, which is why a document may rebind one of their names —
and why `<expr>` reaches them through reserved aliases instead.
"""

import pytest

import pgsn
from pgsn.pgsn_xml import PGSNError


def run(source: str):
    return pgsn.python_value(pgsn.load_xml_string(f"<PGSN>{source}</PGSN>"))


# ------------------------------------------------------------------ #
# Rebinding within a block
# ------------------------------------------------------------------ #

def test_a_later_binding_shadows_an_earlier_one():
    assert run('<def name="x">first</def>'
               '<def name="x">second</def>'
               '<var name="x"/>') == "second"


def test_a_binding_is_evaluated_before_itself():
    """`<def name="x"><var name="x"/></def>` refers to the outer x, not to
    itself. Self-reference is what `recursive="true"` is for."""
    assert run('<def name="x">outer</def>'
               '<def name="x"><var name="x"/></def>'
               '<var name="x"/>') == "outer"


def test_the_earlier_binding_is_still_visible_to_what_precedes_it():
    assert run('<def name="x">first</def>'
               '<def name="seen"><var name="x"/></def>'
               '<def name="x">second</def>'
               '<ul><li><var name="seen"/></li><li><var name="x"/></li></ul>'
               ) == ["first", "second"]


def test_rebinding_inside_a_div_does_not_escape():
    assert run('<def name="x">outer</def>'
               '<ul><li><div><def name="x">inner</def>'
               '<var name="x"/></div></li>'
               '<li><var name="x"/></li></ul>') == ["inner", "outer"]


def test_rebinding_inside_a_template_does_not_escape():
    """A parameterless <template> is just its body, so `t` is the value."""
    assert run('<def name="x">outer</def>'
               '<def name="t" as="template"><def name="x">inner</def>'
               '<var name="x"/></def>'
               '<ul><li><var name="t"/></li>'
               '<li><var name="x"/></li></ul>') == ["inner", "outer"]


def test_a_parameter_shadows_an_outer_binding():
    assert run('<def name="x">outer</def>'
               '<def name="t" as="template">'
               '<param name="x" positional="true"/><var name="x"/></def>'
               '<apply><var name="t"/><arg>inner</arg></apply>') == "inner"


# ------------------------------------------------------------------ #
# Builtins are ordinary bindings
# ------------------------------------------------------------------ #

def test_an_unbound_builtin_name_denotes_the_builtin():
    assert run('<apply><var name="head"/>'
               '<arg><ul><li>a</li><li>b</li></ul></arg></apply>') == "a"


def test_a_document_may_rebind_a_builtin_name():
    """Previously the name was substituted at compile time, so the definition
    was silently discarded (issue #14)."""
    assert run('<def name="head">my own head</def>'
               '<var name="head"/>') == "my own head"


def test_a_parameter_may_be_named_after_a_builtin():
    """`context`, `index`, `head` and `tail` are all plausible parameter
    names, which is the likeliest way to meet the old defect."""
    assert run('<def name="t" as="template">'
               '<param name="context" positional="true"/>'
               '<var name="context"/></def>'
               '<apply><var name="t"/><arg>the deployed system</arg></apply>'
               ) == "the deployed system"


def test_rebinding_a_builtin_does_not_leak_out_of_its_block():
    assert run('<div><def name="head">mine</def><var name="head"/></div>'
               ) == "mine"
    assert run('<apply><var name="head"/>'
               '<arg><ul><li>a</li></ul></arg></apply>') == "a"


def test_a_gsn_constructor_name_may_be_rebound_too():
    assert run('<def name="goal">not a goal</def>'
               '<var name="goal"/>') == "not a goal"


# ------------------------------------------------------------------ #
# Reserved names
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("source", [
    '<def name="_x">v</def><var name="_x"/>',
    '<def name="t" as="template"><param name="_x"/>v</def><var name="t"/>',
    '<var name="_plus"/>',
    '<var name="x" typeOf="_c"/>',
    '<def name="x" typeOf="_c">v</def>',
    '<apply template="_f"><arg>a</arg></apply>',
    '<get key="a" of="_obj"/>',
    '<send method="m" to="_obj"/>',
    '<apply><var name="head"/><arg name="_k">v</arg></apply>',
    '<ul><li var="_x"/></ul>',
])
def test_reserved_names_are_rejected(source):
    with pytest.raises(PGSNError, match="not a valid name"):
        run(source)


def test_a_reserved_name_is_rejected_inside_expr_too():
    with pytest.raises(PGSNError, match="not a valid name"):
        run("<expr>_plus</expr>")


@pytest.mark.parametrize("name", ["my-goal", "2nd", "a b", "", "x.y"])
def test_a_name_must_be_an_identifier(name):
    """Names and <expr> have to agree on what a name is: an expression is
    parsed by Python's parser, so a name it could not spell would be
    unreachable from one."""
    with pytest.raises(PGSNError, match="not a valid name"):
        run(f'<def name="{name}">v</def>v')


def test_a_name_may_be_written_in_any_script():
    assert run('<def name="ゴール">安全である</def>'
               '<var name="ゴール"/>') == "安全である"


def test_record_labels_are_not_reserved():
    """Labels are a different namespace, so the restriction does not reach
    them. Only names that denote variables are affected."""
    assert run('<dl><dt key="_k"/><dd>v</dd></dl>') == {"_k": "v"}
    assert run('<get key="_k"><dl><dt key="_k"/><dd>v</dd></dl></get>') == "v"


# ------------------------------------------------------------------ #
# Modules
# ------------------------------------------------------------------ #

def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_a_module_may_rebind_a_builtin_without_affecting_its_importer(tmp_path):
    write(tmp_path, "lib.xml",
          '<PGSNModule><def name="head">module head</def></PGSNModule>')
    main = write(tmp_path, "main.xml",
                 '<PGSN><from file="lib.xml" import="head" as="theirs"/>'
                 '<ul><li><var name="theirs"/></li>'
                 '<li><apply><var name="head"/>'
                 '<arg><ul><li>a</li></ul></arg></apply></li></ul></PGSN>')
    assert pgsn.python_value(pgsn.load_xml(main)) == ["module head", "a"]


def test_a_module_gets_the_builtins_of_its_own(tmp_path):
    """A module is a separate lexical scope; the importer's cannot reach it."""
    write(tmp_path, "lib.xml",
          '<PGSNModule><def name="sum">'
          '<apply><var name="plus"/><arg><num>1</num></arg>'
          '<arg><num>2</num></arg></apply></def></PGSNModule>')
    main = write(tmp_path, "main.xml",
                 '<PGSN><def name="plus">not addition</def>'
                 '<from file="lib.xml" import="sum"/>'
                 '<var name="sum"/></PGSN>')
    assert pgsn.python_value(pgsn.load_xml(main)) == 3


def test_an_import_may_land_on_a_name_the_document_also_binds(tmp_path):
    write(tmp_path, "lib.xml",
          '<PGSNModule><def name="x">from module</def></PGSNModule>')
    main = write(tmp_path, "main.xml",
                 '<PGSN><def name="x">from document</def>'
                 '<from file="lib.xml" import="x"/>'
                 '<var name="x"/></PGSN>')
    assert pgsn.python_value(pgsn.load_xml(main)) == "from module"


def test_a_reserved_name_is_rejected_in_a_module_too(tmp_path):
    write(tmp_path, "lib.xml",
          '<PGSNModule><def name="_x">v</def></PGSNModule>')
    main = write(tmp_path, "main.xml",
                 '<PGSN><from file="lib.xml" import="_x"/>'
                 '<var name="x"/></PGSN>')
    with pytest.raises(PGSNError, match="not a valid name"):
        pgsn.load_xml(main)
