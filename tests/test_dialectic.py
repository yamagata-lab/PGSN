"""Tests for the dialectic extension: defeaters challenging GSN nodes."""

import pytest

import pgsn
from pgsn.pgsn_xml import PGSNError


def run(source: str):
    return pgsn.python_value(pgsn.load_xml_string(f"<PGSN>{source}</PGSN>"))


def tree(source: str) -> str:
    return pgsn.gsn_tree(
        pgsn.load_xml_string(f"<PGSN>{source}</PGSN>")).show(stdout=False)


def class_marker(node: dict) -> str:
    """The __ClassName__ key that says what a node is."""
    return next(k for k in node
                if k.startswith("__") and k.endswith("__")
                and k != "__parent_classes__")


# ------------------------------------------------------------------ #
# Building defeaters from Python
# ------------------------------------------------------------------ #

def ancestry(node) -> list[str]:
    """The class names a node descends from, nearest first.

    The names, not `is_subtype`: subtyping is structural, and a Defeater
    declares a subset of what a Goal declares, so every Goal satisfies the
    Defeater type. Telling the two apart is a question about where a class
    came from, which only the inheritance chain answers.
    """
    return pgsn.python_value(node.fully_eval(),
                             with_inherit_chain=True)["__parent_classes__"]


def test_a_defeater_is_a_gsn_node():
    """One class covers every challenge; rebutting and undercutting are read
    off the argument, not off the type."""
    assert ancestry(pgsn.defeater(description="d")) == [
        "Defeater", "GSN_Node", "BaseClass"]


def test_defeater_support_defaults_to_undeveloped():
    node = pgsn.python_value(pgsn.defeater(description="d").fully_eval())
    assert class_marker(node["support"]) == "__Undeveloped__"


def test_a_defeater_can_argue_its_case():
    """Filling in `support` is what distinguishes an argued counter-claim from
    a bare objection."""
    node = pgsn.defeater(
        description="hazard H4 is unmitigated",
        support=pgsn.evidence(description="incident report 2026-03"))
    value = pgsn.python_value(node.fully_eval())
    assert value["support"]["description"] == "incident report 2026-03"


def test_defeaters_attach_to_a_goal():
    g = pgsn.goal(
        description="safe",
        defeaters=[pgsn.defeater(description="hazard H4 is unmitigated")],
        support=pgsn.evidence(description="test report"))
    value = pgsn.python_value(g.fully_eval())
    assert [d["description"] for d in value["defeaters"]] == [
        "hazard H4 is unmitigated"]


def test_defeaters_attach_to_strategies_and_evidence():
    """A defeater challenges strategies and solutions, not only goals."""
    s = pgsn.strategy(description="argue over hazards",
                      sub_goals=pgsn.list_term(()),
                      defeaters=[pgsn.defeater(description="list is stale")])
    e = pgsn.evidence(description="report",
                      defeaters=[pgsn.defeater(description="report is old")])
    assert pgsn.python_value(s.fully_eval())["defeaters"][0]["description"] \
        == "list is stale"
    assert pgsn.python_value(e.fully_eval())["defeaters"][0]["description"] \
        == "report is old"


def test_a_defeater_can_itself_be_challenged():
    """Defeaters are GSN nodes, so the dialectic nests without extra machinery."""
    node = pgsn.defeater(
        description="H4 is unmitigated",
        defeaters=[pgsn.defeater(description="H4 was withdrawn")])
    value = pgsn.python_value(node.fully_eval())
    assert value["defeaters"][0]["description"] == "H4 was withdrawn"


def test_nodes_without_defeaters_are_unchanged():
    """Adding the attribute must not disturb documents that never use it."""
    g = pgsn.goal(description="safe", support=pgsn.undeveloped).fully_eval()
    assert pgsn.python_value(g)["defeaters"] == []
    assert "defeaters" not in pgsn.gsn_tree(g).show(stdout=False)


# ------------------------------------------------------------------ #
# XML syntax
# ------------------------------------------------------------------ #

def test_defeater_tag_in_xml():
    result = run("""<Goal>the system is safe
        <Defeater>hazard H4 is unmitigated</Defeater>
        <Defeater>the test suite is out of date</Defeater>
        <Evidence>test report</Evidence>
    </Goal>""")
    assert [class_marker(d) for d in result["defeaters"]] == [
        "__Defeater__", "__Defeater__"]
    assert [d["description"] for d in result["defeaters"]] == [
        "hazard H4 is unmitigated", "the test suite is out of date"]


def test_a_defeater_carries_its_own_support():
    result = run("""<Goal>the system is safe
        <Defeater>hazard H4 is unmitigated
            <Evidence>incident report 2026-03</Evidence>
        </Defeater>
        <Evidence>test report</Evidence>
    </Goal>""")
    challenge = result["defeaters"][0]
    assert challenge["support"]["description"] == "incident report 2026-03"


def test_a_defeater_without_support_is_undeveloped():
    result = run("""<Goal>the system is safe
        <Defeater>the test suite is out of date</Defeater>
        <Evidence>test report</Evidence>
    </Goal>""")
    assert class_marker(result["defeaters"][0]["support"]) == "__Undeveloped__"


def test_defeaters_nest_in_xml():
    result = run("""<Goal>the system is safe
        <Defeater>hazard H4 is unmitigated
            <Defeater>H4 was withdrawn in revision 7</Defeater>
        </Defeater>
        <Evidence>test report</Evidence>
    </Goal>""")
    inner = result["defeaters"][0]["defeaters"][0]
    assert inner["description"] == "H4 was withdrawn in revision 7"
    assert class_marker(inner) == "__Defeater__"


def test_defeater_on_a_strategy_in_xml():
    result = run("""<Goal>the system is safe
        <Strategy>argue over each hazard
            <Defeater>the hazard list is incomplete</Defeater>
            <Goal>H1 is mitigated<Evidence>report H1</Evidence></Goal>
        </Strategy>
    </Goal>""")
    strategy = result["support"]
    assert strategy["defeaters"][0]["description"] == "the hazard list is incomplete"


def test_defeater_description_may_be_computed():
    result = run("""<def name="i"><num>4</num></def>
        <Goal>the system is safe
            <Defeater><description><expr>f"hazard H{i} is unmitigated"</expr>
                </description></Defeater>
            <Evidence>test report</Evidence>
        </Goal>""")
    assert result["defeaters"][0]["description"] == "hazard H4 is unmitigated"


def test_defeater_as_a_standalone_value():
    """`<Defeater>` is an expression, so it can be bound and reused."""
    result = run("""<def name="doubt"><Defeater>H4 is unmitigated</Defeater></def>
        <var name="doubt"/>""")
    assert class_marker(result) == "__Defeater__"


def test_the_dropped_tags_are_not_recognised():
    """`<Rebuttal>` and `<Undercutter>` were considered and rejected: the
    distinction is not one the notation makes.

    Only the expression position is checked. Inside a GSN element an unknown
    child tag is silently ignored rather than rejected — a pre-existing defect
    of the compiler, not something this branch introduces.
    """
    for tag in ("Rebuttal", "Undercutter"):
        with pytest.raises(PGSNError):
            run(f"<{tag}>H4</{tag}>")


# ------------------------------------------------------------------ #
# Rendering
# ------------------------------------------------------------------ #

def test_tree_names_the_defeater():
    text = tree("""<Goal>safe
        <Defeater>H4 unmitigated</Defeater>
        <Evidence>report</Evidence>
    </Goal>""")
    assert "Defeater: H4 unmitigated" in text


def test_dot_draws_defeaters_as_dashed_hexagons():
    term = pgsn.load_xml_string(
        "<PGSN><Goal>safe<Defeater>H4</Defeater>"
        "<Evidence>report</Evidence></Goal></PGSN>")
    source = pgsn.gsn_dot(term).source
    hexagons = [line for line in source.splitlines() if "hexagon" in line]
    assert len(hexagons) == 1
    assert "style=dashed" in hexagons[0]


def test_dot_draws_the_challenge_edge_differently():
    """A challenge must not read as SupportedBy."""
    term = pgsn.load_xml_string(
        "<PGSN><Goal>safe<Defeater>H4</Defeater>"
        "<Evidence>report</Evidence></Goal></PGSN>")
    edges = [line for line in pgsn.gsn_dot(term).source.splitlines()
             if "->" in line]
    challenge = [e for e in edges if "dashed" in e]
    assert len(challenge) == 1
    assert "dir=back" in challenge[0]
