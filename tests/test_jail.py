"""Tests for jail-confined XML imports, the public API, and the CLI options."""

import os
import sys

import pytest
from click.testing import CliRunner

import pgsn
from pgsn.cli import cli, parse_jails
from pgsn.config import Config
from pgsn.dsl import python_value
from pgsn.jail import JailError, Jails
from pgsn.pgsn_xml import PGSNError, compile_pgsn, load_xml, load_xml_string


MODULE = """<PGSNModule>
    <def name="greeting">hello from the module</def>
</PGSNModule>"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def importer(file_attr, name="greeting"):
    return f"""<PGSN>
        <from file="{file_attr}" import="{name}"/>
        <var name="{name}"/>
    </PGSN>"""


# ------------------------------------------------------------------ #
# Jails: construction and validation
# ------------------------------------------------------------------ #

def test_jails_empty():
    jails = Jails()
    assert len(jails) == 0
    assert not jails
    assert jails.names == ()


def test_jails_resolves_root_to_real_path(tmp_path):
    (tmp_path / "lib").mkdir()
    jails = Jails({"lib": str(tmp_path / "lib")})
    assert jails.root_of("lib") == (tmp_path / "lib").resolve()
    assert "lib" in jails


@pytest.mark.parametrize("name", ["", "..", ".", "a/b", "a.b", "a b", "/lib"])
def test_jails_rejects_bad_names(tmp_path, name):
    with pytest.raises(JailError, match="Invalid jail name"):
        Jails({name: str(tmp_path)})


def test_jails_rejects_missing_root(tmp_path):
    with pytest.raises(JailError, match="no such directory"):
        Jails({"lib": str(tmp_path / "nope")})


def test_jails_rejects_file_as_root(tmp_path):
    f = write(tmp_path / "a.xml", "<PGSNModule/>")
    with pytest.raises(JailError, match="not a directory"):
        Jails({"lib": str(f)})


def test_jails_unknown_name_lists_registered(tmp_path):
    (tmp_path / "lib").mkdir()
    jails = Jails({"lib": str(tmp_path / "lib")})
    with pytest.raises(JailError, match="Unknown jail 'other'.*lib"):
        jails.resolve("/other/a.xml")


def test_jails_containing_root_picks_innermost(tmp_path):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    jails = Jails({"outer": str(outer), "inner": str(inner)})
    assert jails.containing_root(inner / "a.xml") == inner.resolve()
    assert jails.containing_root(outer / "a.xml") == outer.resolve()
    assert jails.containing_root(tmp_path / "a.xml") is None


# ------------------------------------------------------------------ #
# Jailed imports
# ------------------------------------------------------------------ #

def test_import_through_jail(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", MODULE)
    src = write(tmp_path / "work" / "main.xml",
                importer("/lib/mod.xml"))
    cfg = Config(jails={"lib": str(lib)})
    result = python_value(load_xml(src, config=cfg))
    assert result == "hello from the module"


def test_import_through_jail_subdirectory(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "sub" / "deep" / "mod.xml", MODULE)
    src = write(tmp_path / "main.xml", importer("/lib/sub/deep/mod.xml"))
    cfg = Config(jails={"lib": str(lib)})
    assert python_value(load_xml(src, config=cfg)) == "hello from the module"


def test_jailed_import_without_any_jail_fails(tmp_path):
    src = write(tmp_path / "main.xml", importer("/lib/mod.xml"))
    with pytest.raises(PGSNError, match="Unknown jail"):
        compile_pgsn(src)


def test_unknown_jail_name(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", MODULE)
    src = write(tmp_path / "main.xml", importer("/other/mod.xml"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="Unknown jail"):
        compile_pgsn(src, config=cfg)


def test_jail_name_alone_is_rejected(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    src = write(tmp_path / "main.xml", importer("/lib"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="Unsafe file path"):
        compile_pgsn(src, config=cfg)


def test_missing_file_in_jail(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    src = write(tmp_path / "main.xml", importer("/lib/nope.xml"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="No such file in jail"):
        compile_pgsn(src, config=cfg)


# ------------------------------------------------------------------ #
# Escape attempts
# ------------------------------------------------------------------ #

def test_dotdot_inside_jailed_path_rejected(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    write(tmp_path / "secret.xml", MODULE)
    src = write(tmp_path / "main.xml", importer("/lib/../secret.xml"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="Unsafe file path"):
        compile_pgsn(src, config=cfg)


def test_absolute_path_is_not_a_jail(tmp_path):
    """A real absolute path only works if its first component names a jail."""
    outside = write(tmp_path / "outside" / "mod.xml", MODULE)
    src = write(tmp_path / "work" / "main.xml", importer(str(outside)))
    with pytest.raises(PGSNError, match="Unknown jail"):
        compile_pgsn(src)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="symlink creation needs privileges on Windows")
def test_symlink_out_of_jail_rejected(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    write(tmp_path / "secret.xml", MODULE)
    os.symlink(tmp_path / "secret.xml", lib / "link.xml")
    src = write(tmp_path / "main.xml", importer("/lib/link.xml"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="escapes jail"):
        compile_pgsn(src, config=cfg)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="symlink creation needs privileges on Windows")
def test_symlinked_directory_out_of_jail_rejected(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    write(tmp_path / "elsewhere" / "mod.xml", MODULE)
    os.symlink(tmp_path / "elsewhere", lib / "sub")
    src = write(tmp_path / "main.xml", importer("/lib/sub/mod.xml"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="escapes jail"):
        compile_pgsn(src, config=cfg)


def test_backslash_rejected(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    src = write(tmp_path / "main.xml", importer("/lib\\mod.xml"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="backslashes"):
        compile_pgsn(src, config=cfg)


# ------------------------------------------------------------------ #
# Relative imports and the confinement root
# ------------------------------------------------------------------ #

def test_relative_import_below_entry_directory(tmp_path):
    write(tmp_path / "sub" / "mod.xml", MODULE)
    src = write(tmp_path / "main.xml", importer("sub/mod.xml"))
    assert python_value(load_xml(src)) == "hello from the module"


def test_dotdot_returning_inside_root_is_allowed(tmp_path):
    """'..' is fine as long as the result stays under the confinement root."""
    write(tmp_path / "b" / "mod.xml", MODULE)
    src = write(tmp_path / "a" / "main.xml", importer("../b/mod.xml"))
    cfg = Config(jails={"proj": str(tmp_path)})
    # The entry file lives inside jail 'proj', so the jail is its boundary.
    assert python_value(load_xml(src, config=cfg)) == "hello from the module"


def test_dotdot_escaping_entry_directory_rejected(tmp_path):
    """Without a surrounding jail, the entry file's directory is the boundary."""
    write(tmp_path / "b" / "mod.xml", MODULE)
    src = write(tmp_path / "a" / "main.xml", importer("../b/mod.xml"))
    with pytest.raises(PGSNError, match="Unsafe file path"):
        compile_pgsn(src)


def test_relative_import_inside_jail_stays_in_jail(tmp_path):
    """A module reached through a jail keeps that jail as its boundary."""
    lib = tmp_path / "lib"
    write(lib / "inner" / "leaf.xml", MODULE)
    write(lib / "mod.xml", """<PGSNModule>
        <from file="inner/leaf.xml" import="greeting"/>
        <def name="greeting"><var name="greeting"/></def>
    </PGSNModule>""")
    src = write(tmp_path / "main.xml", importer("/lib/mod.xml"))
    cfg = Config(jails={"lib": str(lib)})
    assert python_value(load_xml(src, config=cfg)) == "hello from the module"


def test_relative_import_cannot_climb_out_of_jail(tmp_path):
    """Once inside a jail, '..' cannot reach the importing document's tree."""
    lib = tmp_path / "lib"
    write(tmp_path / "secret.xml", MODULE)
    write(lib / "mod.xml", """<PGSNModule>
        <from file="../secret.xml" import="greeting"/>
        <def name="greeting"><var name="greeting"/></def>
    </PGSNModule>""")
    src = write(tmp_path / "main.xml", importer("/lib/mod.xml"))
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="Unsafe file path"):
        compile_pgsn(src, config=cfg)


def test_import_between_jails_needs_explicit_name(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(b / "leaf.xml", MODULE)
    write(a / "mod.xml", """<PGSNModule>
        <from file="/b/leaf.xml" import="greeting"/>
        <def name="greeting"><var name="greeting"/></def>
    </PGSNModule>""")
    src = write(tmp_path / "main.xml", importer("/a/mod.xml"))
    cfg = Config(jails={"a": str(a), "b": str(b)})
    assert python_value(load_xml(src, config=cfg)) == "hello from the module"


# ------------------------------------------------------------------ #
# Circular imports
# ------------------------------------------------------------------ #

def test_circular_import_across_jails(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a / "mod.xml", """<PGSNModule>
        <from file="/b/mod.xml" import="greeting"/>
        <def name="greeting"><var name="greeting"/></def>
    </PGSNModule>""")
    write(b / "mod.xml", """<PGSNModule>
        <from file="/a/mod.xml" import="greeting"/>
        <def name="greeting"><var name="greeting"/></def>
    </PGSNModule>""")
    src = write(tmp_path / "main.xml", importer("/a/mod.xml"))
    cfg = Config(jails={"a": str(a), "b": str(b)})
    with pytest.raises(PGSNError, match="Circular import"):
        compile_pgsn(src, config=cfg)


def test_same_module_imported_twice_is_allowed(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", MODULE)
    src = write(tmp_path / "main.xml", """<PGSN>
        <from file="/lib/mod.xml" import="greeting" as="a"/>
        <from file="/lib/mod.xml" import="greeting" as="b"/>
        <ul><li><var name="a"/></li><li><var name="b"/></li></ul>
    </PGSN>""")
    cfg = Config(jails={"lib": str(lib)})
    assert python_value(load_xml(src, config=cfg)) == \
        ["hello from the module", "hello from the module"]


# ------------------------------------------------------------------ #
# load_xml_string
# ------------------------------------------------------------------ #

def test_load_xml_string_with_jailed_import(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", MODULE)
    cfg = Config(jails={"lib": str(lib)})
    result = load_xml_string(importer("/lib/mod.xml"), config=cfg)
    assert python_value(result) == "hello from the module"


def test_load_xml_string_relative_needs_jail(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", MODULE)
    cfg = Config(jails={"lib": str(lib)})
    with pytest.raises(PGSNError, match="Relative imports are not allowed"):
        load_xml_string(importer("mod.xml"), config=cfg)
    result = load_xml_string(importer("mod.xml"), config=cfg, jail="lib")
    assert python_value(result) == "hello from the module"


def test_load_xml_string_unknown_jail(tmp_path):
    with pytest.raises(PGSNError, match="Unknown jail"):
        load_xml_string("<PGSN>hi</PGSN>", jail="nope")


# ------------------------------------------------------------------ #
# Config
# ------------------------------------------------------------------ #

def test_config_accepts_mapping_or_jails(tmp_path):
    (tmp_path / "lib").mkdir()
    a = Config(jails={"lib": str(tmp_path / "lib")})
    b = Config(jails=Jails({"lib": str(tmp_path / "lib")}))
    assert a == b
    assert a.jails.root_of("lib") == (tmp_path / "lib").resolve()


def test_config_replace(tmp_path):
    (tmp_path / "lib").mkdir()
    base = Config()
    derived = base.replace(jails={"lib": str(tmp_path / "lib")})
    assert not base.jails
    assert "lib" in derived.jails
    with pytest.raises(TypeError, match="Unknown configuration field"):
        base.replace(bogus=1)


def test_configure_sets_default(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", MODULE)
    src = write(tmp_path / "main.xml", importer("/lib/mod.xml"))
    previous = pgsn.get_config()
    try:
        pgsn.configure(jails={"lib": str(lib)})
        assert python_value(pgsn.load_xml(src)) == "hello from the module"
    finally:
        pgsn.configure(previous)
    with pytest.raises(PGSNError, match="Unknown jail"):
        compile_pgsn(src)


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def test_public_names_are_importable():
    missing = [name for name in pgsn.__all__ if not hasattr(pgsn, name)]
    assert missing == []


def test_internals_are_not_exported():
    for hidden in ("json_dumps", "json_loads", "compile_pgsn",
                   "compile_pgsn_string", "dsl", "gsn", "pgsn_term",
                   "pgsn_xml", "cli", "helpers", "dcom"):
        assert hidden not in pgsn.__all__


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #

def test_parse_jails_valid(tmp_path):
    (tmp_path / "lib").mkdir()
    jails = parse_jails((f"lib={tmp_path / 'lib'}",))
    assert jails.names == ("lib",)


@pytest.mark.parametrize("spec", ["lib", "=/tmp", "lib=", ""])
def test_parse_jails_malformed(spec):
    with pytest.raises(Exception, match="NAME=PATH"):
        parse_jails((spec,))


def test_parse_jails_duplicate(tmp_path):
    (tmp_path / "lib").mkdir()
    with pytest.raises(Exception, match="more than once"):
        parse_jails((f"lib={tmp_path / 'lib'}", f"lib={tmp_path / 'lib'}"))


def test_cli_doc_with_jail(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", """<PGSNModule>
        <def name="g"><Goal>imported goal</Goal></def>
    </PGSNModule>""")
    src = write(tmp_path / "main.xml", """<PGSN>
        <from file="/lib/mod.xml" import="g"/>
        <var name="g"/>
    </PGSN>""")
    result = CliRunner().invoke(
        cli, ["doc", str(src), "--jail", f"lib={lib}", "-o", "-"])
    assert result.exit_code == 0, result.output
    assert "imported goal" in result.output


def test_cli_doc_without_jail_fails(tmp_path):
    lib = tmp_path / "lib"
    write(lib / "mod.xml", """<PGSNModule>
        <def name="g"><Goal>imported goal</Goal></def>
    </PGSNModule>""")
    src = write(tmp_path / "main.xml", """<PGSN>
        <from file="/lib/mod.xml" import="g"/>
        <var name="g"/>
    </PGSN>""")
    result = CliRunner().invoke(cli, ["doc", str(src), "-o", "-"])
    assert "Unknown jail" in result.output


def test_cli_rejects_jail_for_python_input(tmp_path):
    src = write(tmp_path / "main.py", "main = 1\n")
    result = CliRunner().invoke(
        cli, ["doc", str(src), "--jail", f"lib={tmp_path}"])
    assert result.exit_code != 0
    assert "--jail applies to .xml input only" in result.output


def test_cli_rejects_jail_for_json_input(tmp_path):
    src = write(tmp_path / "main.json", '{"__type__": "String", "value": "x"}')
    result = CliRunner().invoke(
        cli, ["doc", str(src), "--jail", f"lib={tmp_path}"])
    assert result.exit_code != 0
    assert "--jail applies to .xml input only" in result.output


def test_cli_rejects_malformed_jail(tmp_path):
    src = write(tmp_path / "main.xml", "<PGSN>hi</PGSN>")
    result = CliRunner().invoke(cli, ["doc", str(src), "--jail", "lib"])
    assert result.exit_code != 0
    assert "NAME=PATH" in result.output
