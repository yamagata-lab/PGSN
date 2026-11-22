"""A command that fails says so with its exit status.

`pgsn doc`, `pgsn render` and `pgsn compile` report a failure as `Error: ...`
on stderr, and a script or a CI job that runs them can only tell a document
that failed from one that succeeded if the status is not 0 as well.
"""

import pytest
from click.testing import CliRunner

from pgsn.cli import cli

_UNBOUND = "<PGSN><Goal><var name='nope'/><undeveloped/></Goal></PGSN>"
_MALFORMED = "<PGSN><Goal>"


@pytest.mark.parametrize("command", [["doc"], ["render", "-o", "-"]])
def test_a_document_that_does_not_evaluate(tmp_path, command):
    source = tmp_path / "doc.xml"
    source.write_text(_UNBOUND)
    result = CliRunner().invoke(cli, [*command, str(source)])
    assert result.exit_code == 1
    assert "Error: " in result.output
    assert "name 'nope' is not defined" in result.output


@pytest.mark.parametrize("command", [["doc"], ["render", "-o", "-"], ["compile"]])
def test_a_document_that_does_not_compile(tmp_path, command):
    source = tmp_path / "doc.xml"
    source.write_text(_MALFORMED)
    result = CliRunner().invoke(cli, [*command, str(source)])
    assert result.exit_code == 1
    assert "Error: " in result.output


def test_a_document_that_succeeds(tmp_path):
    source = tmp_path / "doc.xml"
    source.write_text("<PGSN><Goal>g<undeveloped/></Goal></PGSN>")
    result = CliRunner().invoke(cli, ["doc", str(source)])
    assert result.exit_code == 0
    assert "Goal: g" in result.output
