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

    `is_instance` is not used here: it answers False for any class whose
    defaults hold an unevaluated term, which covers `goal_class` and
    `defeater_class` alike. That defect predates this branch.
    """
    return pgsn.python_value(node.fully_eval(),
                             with_inherit_chain=True)["__parent_classes__"]


def test_defeater_kinds_are_distinguishable():
    assert ancestry(pgsn.rebuttal(description="d")) == [
        "Rebuttal", "Defeater", "GSN_Node", "BaseClass"]
    assert ancestry(pgsn.undercutter(description="d")) == [
        "Undercutter", "Defeater", "GSN_Node", "BaseClass"]
    assert ancestry(pgsn.defeater(description="d")) == [
        "Defeater", "GSN_Node", "BaseClass"]


def test_a_rebuttal_is_not_an_undercutter():
    assert "Undercutter" not in ancestry(pgsn.rebuttal(description="d"))


def test_defeater_support_defaults_to_undeveloped():
    node = pgsn.python_value(pgsn.undercutter(description="d").fully_eval())
    assert class_marker(node["support"]) == "__Undeveloped__"


def test_defeaters_attach_to_a_goal():
    g = pgsn.goal(
        description="safe",
        defeaters=[pgsn.rebuttal(description="hazard H4 is unmitigated")],
        support=pgsn.evidence(description="test report"))
    value = pgsn.python_value(g.fully_eval())
    assert [d["description"] for d in value["defeaters"]] == [
        "hazard H4 is unmitigated"]


def test_defeaters_attach_to_strategies_and_evidence():
    """A defeater challenges strategies and solutions, not only goals."""
    s = pgsn.strategy(description="argue over hazards",
                      sub_goals=pgsn.list_term(()),
                      defeaters=[pgsn.undercutter(description="list is stale")])
    e = pgsn.evidence(description="report",
                      defeaters=[pgsn.undercutter(description="report is old")])
    assert pgsn.python_value(s.fully_eval())["defeaters"][0]["description"] \
        == "list is stale"
    assert pgsn.python_value(e.fully_eval())["defeaters"][0]["description"] \
        == "report is old"


def test_a_defeater_can_itself_be_challenged():
    """Defeaters are GSN nodes, so the dialectic nests without extra machinery."""
    node = pgsn.rebuttal(
        description="H4 is unmitigated",
        defeaters=[pgsn.undercutter(description="H4 was withdrawn")])
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

def test_defeater_tags_in_xml():
    result = run("""<Goal>the system is safe
        <Rebuttal>hazard H4 is unmitigated</Rebuttal>
        <Undercutter>the test suite is out of date</Undercutter>
        <Evidence>test report</Evidence>
    </Goal>""")
    kinds = [class_marker(d) for d in result["defeaters"]]
    assert kinds == ["__Rebuttal__", "__Undercutter__"]
    assert [d["description"] for d in result["defeaters"]] == [
        "hazard H4 is unmitigated", "the test suite is out of date"]


def test_a_defeater_carries_its_own_support():
    result = run("""<Goal>the system is safe
        <Rebuttal>hazard H4 is unmitigated
            <Evidence>incident report 2026-03</Evidence>
        </Rebuttal>
        <Evidence>test report</Evidence>
    </Goal>""")
    rebuttal = result["defeaters"][0]
    assert rebuttal["support"]["description"] == "incident report 2026-03"


def test_defeaters_nest_in_xml():
    result = run("""<Goal>the system is safe
        <Rebuttal>hazard H4 is unmitigated
            <Undercutter>H4 was withdrawn in revision 7</Undercutter>
        </Rebuttal>
        <Evidence>test report</Evidence>
    </Goal>""")
    inner = result["defeaters"][0]["defeaters"][0]
    assert inner["description"] == "H4 was withdrawn in revision 7"
    assert class_marker(inner) == "__Undercutter__"


def test_defeater_on_a_strategy_in_xml():
    result = run("""<Goal>the system is safe
        <Strategy>argue over each hazard
            <Undercutter>the hazard list is incomplete</Undercutter>
            <Goal>H1 is mitigated<Evidence>report H1</Evidence></Goal>
        </Strategy>
    </Goal>""")
    strategy = result["support"]
    assert strategy["defeaters"][0]["description"] == "the hazard list is incomplete"


def test_defeater_description_may_be_computed():
    result = run("""<def name="i"><num>4</num></def>
        <Goal>the system is safe
            <Rebuttal><description><expr>f"hazard H{i} is unmitigated"</expr>
                </description></Rebuttal>
            <Evidence>test report</Evidence>
        </Goal>""")
    assert result["defeaters"][0]["description"] == "hazard H4 is unmitigated"


def test_defeater_as_a_standalone_value():
    """`<Rebuttal>` is an expression, so it can be bound and reused."""
    result = run("""<def name="doubt"><Rebuttal>H4 is unmitigated</Rebuttal></def>
        <var name="doubt"/>""")
    assert class_marker(result) == "__Rebuttal__"


# ------------------------------------------------------------------ #
# Rendering
# ------------------------------------------------------------------ #

def test_tree_names_the_kind_of_defeater():
    text = tree("""<Goal>safe
        <Rebuttal>H4 unmitigated</Rebuttal>
        <Undercutter>tests are stale</Undercutter>
        <Evidence>report</Evidence>
    </Goal>""")
    assert "Rebuttal: H4 unmitigated" in text
    assert "Undercutter: tests are stale" in text


def test_dot_draws_defeaters_as_dashed_hexagons():
    term = pgsn.load_xml_string(
        "<PGSN><Goal>safe<Rebuttal>H4</Rebuttal>"
        "<Evidence>report</Evidence></Goal></PGSN>")
    source = pgsn.gsn_dot(term).source
    hexagons = [line for line in source.splitlines() if "hexagon" in line]
    assert len(hexagons) == 1
    assert "style=dashed" in hexagons[0]


def test_dot_draws_the_challenge_edge_differently():
    """A challenge must not read as SupportedBy."""
    term = pgsn.load_xml_string(
        "<PGSN><Goal>safe<Rebuttal>H4</Rebuttal>"
        "<Evidence>report</Evidence></Goal></PGSN>")
    edges = [line for line in pgsn.gsn_dot(term).source.splitlines()
             if "->" in line]
    challenge = [e for e in edges if "dashed" in e]
    assert len(challenge) == 1
    assert "dir=back" in challenge[0]
