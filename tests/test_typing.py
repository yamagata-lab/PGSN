"""Every GSN constructor satisfies the type of its own class.

From the issue that removed `is_instance`: that predicate answered False for
any class whose defaults hold a term still to be reduced, and which classes
those were was not visible from outside — `evidence_class` passed while
`goal_class`, the one most likely to be checked, failed. The cause was
confirmed on the old code: the class reached through an evaluated object had
`support` reduced to a PGSNObject, while the standalone `goal_class` still
held the unreduced application, and the two compared unequal.

`is_subtype` compares declared labels and never looks at a default, so the
answer cannot depend on that again. Asserting it for every constructor and
its class is what the issue asked for, so that the claim stays honest.
"""

import pytest
import pgsn


def satisfies(node, cls) -> bool:
    return pgsn.is_subtype(pgsn.type_of(node))(cls).fully_eval().value


# (name, node, the class the constructor builds)
CONSTRUCTORS = [
    ("evidence", pgsn.evidence(description="e"), pgsn.evidence_class),
    ("strategy", pgsn.strategy(description="s", sub_goals=pgsn.empty),
     pgsn.strategy_class),
    ("goal", pgsn.goal(description="g", support=pgsn.undeveloped),
     pgsn.goal_class),
    ("assumption", pgsn.assumption(description="a"), pgsn.assumption_class),
    ("context", pgsn.context(description="c"), pgsn.context_class),
    ("defeater", pgsn.defeater(description="d"), pgsn.defeater_class),
    ("undeveloped", pgsn.undeveloped, pgsn.undeveloped_class),
    ("immediate", pgsn.immediate(pgsn.empty), pgsn.strategy_class),
    ("evidence_as_goal",
     pgsn.evidence_as_goal(pgsn.evidence(description="e")), pgsn.goal_class),
]

IDS = [name for name, _, _ in CONSTRUCTORS]


@pytest.mark.parametrize("name, node, cls", CONSTRUCTORS, ids=IDS)
def test_constructor_satisfies_its_own_class(name, node, cls):
    assert satisfies(node, cls)


@pytest.mark.parametrize("name, node, cls", CONSTRUCTORS, ids=IDS)
def test_every_node_satisfies_gsn_node(name, node, cls):
    """`description` and `defeaters` are what a GSN node declares, and every
    constructor produces something carrying both."""
    assert satisfies(node, pgsn.gsn_class)


def test_the_three_cases_from_the_issue():
    """The two that worked, and the one that did not."""
    assert satisfies(pgsn.evidence(description="e"), pgsn.evidence_class)
    assert satisfies(pgsn.context(description="c"), pgsn.context_class)
    assert satisfies(pgsn.goal(description="g", support=pgsn.undeveloped),
                     pgsn.goal_class)


def test_a_type_is_not_satisfied_by_a_node_missing_its_labels():
    """Evidence declares no `support`, so it does not satisfy Goal. The
    converse holds, since a goal declares everything evidence does and more —
    that is structural typing, not a mistake."""
    assert not satisfies(pgsn.evidence(description="e"), pgsn.goal_class)
    assert satisfies(pgsn.goal(description="g", support=pgsn.undeveloped),
                     pgsn.evidence_class)
