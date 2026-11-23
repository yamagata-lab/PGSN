"""GSN v3 marks an undeveloped goal or strategy with a decorator.

Table 1:2-1 of the standard renders the undeveloped element decorator as a
hollow diamond at the bottom centre of the element it applies to, and lets it
apply to goals and strategies. `gsn_dot` used to draw it as a diamond-shaped
node of its own, joined to the element by a SupportedBy edge, which reads as
one more element of the argument.
"""

import pgsn
from pgsn.gsn import UNDEVELOPED_DECORATOR


def _labels(term) -> list[str]:
    source = pgsn.gsn_dot(term).source
    # A label is one quoted string, which may run over several lines.
    return [part.split('"', 1)[0]
            for part in source.split('label="')[1:]]


def _xml(body: str):
    return pgsn.load_xml_string(f"<PGSN>{body}</PGSN>")


def test_an_undeveloped_goal_carries_the_decorator():
    labels = _labels(_xml("<Goal>safe<undeveloped/></Goal>"))
    assert labels == [f"G1\nsafe\n{UNDEVELOPED_DECORATOR}"]


def test_no_element_of_its_own_is_drawn():
    source = pgsn.gsn_dot(_xml("<Goal>safe<undeveloped/></Goal>")).source
    assert "diamond" not in source
    assert "->" not in source


def test_a_developed_goal_has_no_decorator():
    labels = _labels(_xml("<Goal>safe<Solution>report</Solution></Goal>"))
    assert not any(UNDEVELOPED_DECORATOR in label for label in labels)


def test_an_undeveloped_strategy_carries_the_decorator():
    term = pgsn.goal(description="g", support=pgsn.strategy(
        description="s", sub_goals=pgsn.list_term((pgsn.undeveloped,))))
    assert f"S1\ns\n{UNDEVELOPED_DECORATOR}" in _labels(term.fully_eval())


def test_an_unsupported_defeater_has_neither():
    """The standard gives the decorator to goals and strategies only, and an
    objection put without grounds says so by having nothing beneath it."""
    labels = _labels(_xml(
        "<Goal>safe<Defeater>H4</Defeater><Solution>report</Solution></Goal>"))
    assert "CG1\nH4" in labels
    assert not any(UNDEVELOPED_DECORATOR in label for label in labels)


def test_a_strategy_is_left_undeveloped_in_xml():
    """An <undeveloped/> among the sub-goals is how a document says it."""
    labels = _labels(_xml("<Goal>g<Strategy>s<undeveloped/></Strategy></Goal>"))
    assert labels == ["G1\ng", f"S1\ns\n{UNDEVELOPED_DECORATOR}"]


def test_an_undeveloped_strategy_keeps_the_sub_goals_it_has():
    labels = _labels(_xml(
        "<Goal>g<Strategy>s<Goal>a<Solution>r</Solution></Goal>"
        "<undeveloped/></Strategy></Goal>"))
    assert f"S1\ns\n{UNDEVELOPED_DECORATOR}" in labels
    assert "G2\na" in labels
