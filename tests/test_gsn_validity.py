"""An evaluated structure is checked against the rules of GSN v3.

The language lets a document put any value anywhere, so a structure can
evaluate and still not be one GSN allows. `gsn_violations` reports where, and
`pgsn doc` and `pgsn render` print the reports as warnings, or stop on them
under --strict. One test per rule, each with a document that breaks it.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

import pgsn
from pgsn.cli import cli

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _violations(body: str) -> list[str]:
    term = pgsn.load_xml_string(f"<PGSN>{body}</PGSN>")
    return [str(v) for v in pgsn.gsn_violations(term)]


def _violations_of(term) -> list[str]:
    return [str(v) for v in pgsn.gsn_violations(term.fully_eval())]


def test_a_goal_supported_by_text():
    assert _violations("<Goal>g<supportedBy>just text</supportedBy></Goal>") == [
        "G1 at <root>: a goal is supported by a strategy, a solution or "
        "sub-goals, not by text"]


def test_a_strategy_supported_by_something_other_than_goals():
    term = pgsn.goal(description="g", support=pgsn.strategy(
        description="s", sub_goals=pgsn.list_term((pgsn.string("x"),))))
    assert _violations_of(term) == [
        "S1 at <root>.support.sub_goals[0]: a strategy is supported by "
        "goals, not by text"]


def test_a_context_that_is_not_a_context():
    term = pgsn.goal(description="g", support=pgsn.undeveloped,
                     contexts=pgsn.list_term((pgsn.string("plant"),)))
    assert _violations_of(term) == [
        "G1 at <root>.contexts[0]: the contexts of a goal are contexts, "
        "not text"]


def test_an_empty_strategy():
    assert _violations(
        '<def name="none"><ol/></def>'
        '<Goal>g<Strategy>s<subGoals var="none"/></Strategy></Goal>') == [
        "S1 at <root>.support: a strategy relates a goal to supporting "
        "goals, but this one has none"]


def test_a_strategy_written_without_sub_goals():
    """Not a compile error: written or computed, an empty strategy is
    reported by the check."""
    assert _violations("<Goal>g<Strategy>s</Strategy></Goal>") == [
        "S1 at <root>.support: a strategy relates a goal to supporting goals, "
        "but this one has none"]


def test_a_goal_where_a_defeater_belongs():
    term = pgsn.goal(description="g", support=pgsn.undeveloped,
                     defeaters=pgsn.list_term((pgsn.goal(
                         description="h", support=pgsn.undeveloped),)))
    violations = _violations_of(term)
    assert ("G1 at <root>.defeaters[0]: what challenges an element is a "
            "defeater, not Goal") in violations


@pytest.mark.parametrize("body, description", [
    ("<Goal><undeveloped/></Goal>", "''"),
    ("<Goal><description/><undeveloped/></Goal>", "''"),
    ("<Goal><description>  </description><undeveloped/></Goal>", "''"),
    ("<Goal>g<Context><description/></Context><undeveloped/></Goal>", "''"),
])
def test_an_element_that_states_nothing(body, description):
    # An empty description compiles; the check is what reports it.
    violations = _violations(body)
    assert len(violations) == 1
    assert violations[0].endswith(
        f"must state something in its description, which is {description}")


@pytest.mark.parametrize("body", [
    "<Goal>g<Context><ol><li>a</li></ol></Context><undeveloped/></Goal>",
    '<Goal>g<Context><dl><dt>url</dt><dd>https://example.com</dd></dl></Context>'
    "<undeveloped/></Goal>",
    "<Goal><num>3</num><undeveloped/></Goal>",
], ids=["a list", "a record", "a number"])
def test_a_description_that_is_not_text_is_no_breach(body):
    """A context may be a reference to an artefact rather than a statement,
    and the language lets any value stand for a description."""
    assert _violations(body) == []


def test_a_structure_not_headed_by_a_goal():
    assert _violations("<Strategy>s<Goal>g<undeveloped/></Goal></Strategy>") == [
        "<root>: the structure is not headed by a goal"]


def test_identifiers_are_the_ones_the_drawing_shows():
    body = ('<def name="none"><ol/></def>'
            "<Goal>g<Context>c</Context>"
            "<Strategy>s<Goal>a<Strategy>t<subGoals var=\"none\"/></Strategy>"
            "</Goal></Strategy></Goal>")
    term = pgsn.load_xml_string(f"<PGSN>{body}</PGSN>")
    [violation] = pgsn.gsn_violations(term)
    assert violation.identifier == "S2"
    assert 'label="S2\nt"' in pgsn.gsn_dot(term).source


@pytest.mark.parametrize(
    "path",
    [p for p in sorted(EXAMPLES.rglob("*.xml"))
     if "<PGSNModule" not in p.read_text()],
    ids=lambda p: str(p.relative_to(EXAMPLES)))
def test_the_examples_keep_the_rules(path):
    assert pgsn.gsn_violations(pgsn.load_xml(str(path))) == []


_EMPTY_STRATEGY = ('<PGSN><def name="none"><ol/></def>'
                   '<Goal>g<Strategy>s<subGoals var="none"/></Strategy></Goal>'
                   '</PGSN>')


def test_doc_warns_and_writes_the_document(tmp_path):
    source = tmp_path / "doc.xml"
    source.write_text(_EMPTY_STRATEGY)
    result = CliRunner().invoke(cli, ["doc", str(source), "-o", "-"])
    assert result.exit_code == 0
    assert "Warning: S1 at <root>.support" in result.output
    assert "Goal: g" in result.output


def test_strict_stops_without_writing(tmp_path):
    source = tmp_path / "doc.xml"
    source.write_text(_EMPTY_STRATEGY)
    result = CliRunner().invoke(cli, ["doc", str(source), "-o", "-", "--strict"])
    assert result.exit_code == 1
    assert "Error: S1 at <root>.support" in result.output
    assert "Goal: g" not in result.output
