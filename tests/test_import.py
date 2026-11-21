"""How `<from>` translates, and what the translation costs.

A module is compiled, applied to its arguments, and its exports projected off
the result. The applied module is bound once and each import reads a field
from that binding, so the compiled term holds one copy of the module however
many names are taken from it.
"""

import attrs
import pytest

import pgsn
from pgsn.pgsn_term import Term
from pgsn.pgsn_xml import PGSNError, compile_pgsn


MODULE = """<PGSNModule>
    <param name="prefix"/>
    <def name="a"><expr>f"{prefix} a"</expr></def>
    <def name="b"><expr>f"{prefix} b"</expr></def>
    <def name="c"><expr>f"{prefix} c"</expr></def>
</PGSNModule>"""


def nodes(term: Term) -> int:
    """Positions the term occupies in the tree."""
    total = 1
    for field in attrs.fields(type(term)):
        value = object.__getattribute__(term, field.name)
        if isinstance(value, Term):
            total += nodes(value)
        elif isinstance(value, (tuple, list)):
            total += sum(nodes(t) for t in value if isinstance(t, Term))
        elif isinstance(value, dict):
            total += sum(nodes(t) for t in value.values() if isinstance(t, Term))
    return total


@pytest.fixture
def project(tmp_path):
    """A directory holding the module, plus a way to write documents into it."""
    (tmp_path / "lib.xml").write_text(MODULE)

    def write(body: str):
        path = tmp_path / "main.xml"
        path.write_text(f"<PGSN>{body}</PGSN>")
        return path

    return write


def test_importing_more_names_does_not_embed_the_module_again(project):
    """The point of the binding: the compiled term must not grow with the
    number of names taken from a module (issue #15)."""
    one = compile_pgsn(project(
        '<from file="lib.xml"><import name="a"/><arg name="prefix">p</arg>'
        '</from><var name="a"/>'))
    three = compile_pgsn(project(
        '<from file="lib.xml"><import name="a"/><import name="b"/>'
        '<import name="c"/><arg name="prefix">p</arg></from>'
        '<ol><li><var name="a"/></li><li><var name="b"/></li>'
        '<li><var name="c"/></li></ol>'))

    # Each further import adds a projection and a list entry, nothing like a
    # second copy of the module — which on its own is an order of magnitude
    # larger than the whole one-import document.
    assert nodes(three) - nodes(one) < nodes(one) // 2


def test_several_imported_names_all_arrive(project):
    result = pgsn.python_value(pgsn.load_xml(project(
        '<from file="lib.xml"><import name="a"/><import name="c" as="z"/>'
        '<arg name="prefix">p</arg></from>'
        '<ol><li><var name="a"/></li><li><var name="z"/></li></ol>')))
    assert result == ["p a", "p c"]


def test_two_modules_in_one_block_do_not_interfere(project, tmp_path):
    """Each `<from>` rebinds the same reserved name, so a projection has to
    read the binding nearest to it rather than the last one."""
    (tmp_path / "other.xml").write_text(
        '<PGSNModule><def name="a">from other</def></PGSNModule>')
    result = pgsn.python_value(pgsn.load_xml(project(
        '<from file="lib.xml"><import name="a"/>'
        '<arg name="prefix">p</arg></from>'
        '<from file="other.xml"><import name="a" as="other_a"/></from>'
        '<ol><li><var name="a"/></li><li><var name="other_a"/></li></ol>')))
    assert result == ["p a", "from other"]


def test_the_module_binding_is_not_reachable_from_the_document(project):
    """It uses a reserved name, so a document can neither read it nor
    interfere with it."""
    with pytest.raises(PGSNError, match="not a valid name"):
        pgsn.load_xml(project(
            '<from file="lib.xml"><import name="a"/>'
            '<arg name="prefix">p</arg></from><var name="_module"/>'))


def test_a_from_in_a_binding_position_needs_an_import(project):
    """Without one it binds nothing, which used to be accepted in silence."""
    with pytest.raises(PGSNError, match="needs an 'import'"):
        pgsn.load_xml(project(
            '<from file="lib.xml"><arg name="prefix">p</arg></from>'
            '<str>done</str>'))


# ------------------------------------------------------------------ #
# A module is a value
# ------------------------------------------------------------------ #

def test_a_from_in_a_value_position_is_the_module_record(project):
    result = pgsn.python_value(pgsn.load_xml(project(
        '<from file="lib.xml"><arg name="prefix">p</arg></from>')))
    assert result == {"a": "p a", "b": "p b", "c": "p c"}


def test_a_module_can_be_bound_and_selected_from(project):
    result = pgsn.python_value(pgsn.load_xml(project(
        '<def name="lib"><from file="lib.xml">'
        '<arg name="prefix">p</arg></from></def>'
        '<get key="b" of="lib"/>')))
    assert result == "p b"


def test_a_bound_module_is_an_ordinary_value(project):
    """It can be held in a list and passed to a template like anything else."""
    result = pgsn.python_value(pgsn.load_xml(project(
        '<def name="lib"><from file="lib.xml">'
        '<arg name="prefix">p</arg></from></def>'
        '<def name="pick" as="template"><param name="m" positional="true"/>'
        '<get key="c" of="m"/></def>'
        '<ol><li><get key="a" of="lib"/></li>'
        '<li><apply><var name="pick"/><arg var="lib"/></apply></li></ol>')))
    assert result == ["p a", "p c"]


def test_selecting_from_a_module_needs_no_binding_at_all(project):
    result = pgsn.python_value(pgsn.load_xml(project(
        '<get key="a"><from file="lib.xml">'
        '<arg name="prefix">p</arg></from></get>')))
    assert result == "p a"


def test_a_module_used_as_a_value_takes_no_import(project):
    """The record is the whole module, so selecting at the same time would be
    two different things spelled as one."""
    with pytest.raises(PGSNError, match="takes no 'import'"):
        pgsn.load_xml(project(
            '<from file="lib.xml" import="a"><arg name="prefix">p</arg></from>'))
    with pytest.raises(PGSNError, match="takes no 'import'"):
        pgsn.load_xml(project(
            '<from file="lib.xml"><import name="a"/>'
            '<arg name="prefix">p</arg></from>'))


def test_as_without_an_import_is_rejected(project):
    """It renames an imported name, and there is none to rename."""
    with pytest.raises(PGSNError, match="'as' renames an imported name"):
        pgsn.load_xml(project(
            '<from file="lib.xml" as="lib"><arg name="prefix">p</arg></from>'))


def test_a_module_used_as_a_value_is_still_confined(project, tmp_path):
    """First-class or not, a module is reached through the same path rules."""
    with pytest.raises(PGSNError, match="escapes|No such file"):
        pgsn.load_xml(project('<from file="../outside.xml"/>'))


def test_the_single_import_form_still_works(project):
    result = pgsn.python_value(pgsn.load_xml(project(
        '<from file="lib.xml" import="b" as="renamed">'
        '<arg name="prefix">p</arg></from><var name="renamed"/>')))
    assert result == "p b"


# A module is closed: it receives values from its importer only through its
# parameters. A name it leaves free would be bound by whatever the importer
# has in scope where the module is embedded, so the same component would argue
# differently in different systems (issue-drafts 10).
OPEN_MODULE = '<PGSNModule><def name="leak"><var name="secret"/></def></PGSNModule>'


def test_a_module_with_a_free_name_is_rejected(project, tmp_path):
    (tmp_path / "open.xml").write_text(OPEN_MODULE)
    with pytest.raises(PGSNError, match=r"'open\.xml' uses 'secret'"):
        compile_pgsn(project(
            '<def name="secret">the importer\'s value</def>'
            '<from file="open.xml" import="leak"/><var name="leak"/>'))


def test_a_free_name_is_rejected_when_the_module_is_a_value(project, tmp_path):
    (tmp_path / "open.xml").write_text(OPEN_MODULE)
    with pytest.raises(PGSNError, match=r"'open\.xml' uses 'secret'"):
        compile_pgsn(project('<get key="leak"><from file="open.xml"/></get>'))


def test_a_free_name_is_rejected_however_deep_the_module(project, tmp_path):
    """The module in the middle binds the name, but it cannot lend it to the
    module it imports: that one is closed or rejected on its own."""
    (tmp_path / "open.xml").write_text(OPEN_MODULE)
    (tmp_path / "middle.xml").write_text(
        '<PGSNModule><def name="secret">the middle value</def>'
        '<from file="open.xml" import="leak"/></PGSNModule>')
    with pytest.raises(PGSNError, match=r"'open\.xml' uses 'secret'"):
        compile_pgsn(project('<from file="middle.xml" import="leak"/>'
                             '<var name="leak"/>'))


def test_a_module_may_pass_its_parameters_on(project, tmp_path):
    """Parameters, its own definitions, its imports and the builtins are what
    a closed module may use."""
    (tmp_path / "middle.xml").write_text(
        '<PGSNModule><param name="prefix"/>'
        '<from file="lib.xml" import="a"><arg name="prefix" var="prefix"/></from>'
        '<def name="both"><ol><li><var name="a"/></li>'
        '<li><apply template="plus"><arg><num>1</num></arg>'
        '<arg><num>2</num></arg></apply></li>'
        '</ol></def></PGSNModule>')
    result = pgsn.python_value(pgsn.load_xml(project(
        '<from file="middle.xml" import="both"><arg name="prefix">p</arg></from>'
        '<var name="both"/>')))
    assert result == ["p a", 3]
