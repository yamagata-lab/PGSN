"""A command that fails says so with its exit status.

`pgsn doc`, `pgsn render` and `pgsn compile` report a failure as `Error: ...`
on stderr, and a script or a CI job that runs them can only tell a document
that failed from one that succeeded if the status is not 0 as well.
"""

import pytest
from click.testing import CliRunner

from pgsn.cli import _message, cli

_UNBOUND = "<PGSN><Goal><var name='nope'/><undeveloped/></Goal></PGSN>"
_MALFORMED = "<PGSN><Goal>"


@pytest.mark.parametrize("command", [["doc", "-o", "-"], ["render", "-o", "-"]])
def test_a_document_that_does_not_evaluate(tmp_path, command):
    source = tmp_path / "doc.xml"
    source.write_text(_UNBOUND)
    result = CliRunner().invoke(cli, [*command, str(source)])
    assert result.exit_code == 1
    assert "Error: " in result.output
    assert "name 'nope' is not defined" in result.output


@pytest.mark.parametrize("command", [["doc", "-o", "-"], ["render", "-o", "-"], ["compile"]])
def test_a_document_that_does_not_compile(tmp_path, command):
    source = tmp_path / "doc.xml"
    source.write_text(_MALFORMED)
    result = CliRunner().invoke(cli, [*command, str(source)])
    assert result.exit_code == 1
    assert "Error: " in result.output


def test_a_document_that_succeeds(tmp_path):
    source = tmp_path / "doc.xml"
    source.write_text("<PGSN><Goal>g<undeveloped/></Goal></PGSN>")
    result = CliRunner().invoke(cli, ["doc", str(source), "-o", "-"])
    assert result.exit_code == 0
    assert "Goal: g" in result.output


def test_doc_needs_an_output(tmp_path):
    source = tmp_path / "doc.xml"
    source.write_text("<PGSN><Goal>g<undeveloped/></Goal></PGSN>")
    result = CliRunner().invoke(cli, ["doc", str(source)])
    assert result.exit_code == 2
    assert "Missing option '--output'" in result.output


def test_doc_writes_a_file(tmp_path):
    source = tmp_path / "doc.xml"
    source.write_text("<PGSN><Goal>g<undeveloped/></Goal></PGSN>")
    target = tmp_path / "out.txt"
    result = CliRunner().invoke(cli, ["doc", str(source), "-o", str(target)])
    assert result.exit_code == 0
    assert "Goal: g" in target.read_text()


def test_an_error_without_a_message_names_its_kind():
    assert _message(AssertionError()) == "AssertionError"
    assert _message(ValueError("bad")) == "bad"
