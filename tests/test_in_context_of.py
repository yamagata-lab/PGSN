"""InContextOf is drawn as GSN v3 draws it.

Table 1:2-2 of the standard renders InContextOf as a line with a hollow
arrowhead, running from a goal or a strategy to a context or an assumption,
with the arrow pointing at the target. `gsn_dot` used to reverse the edge, so
a solid arrowhead pointed at the goal.
"""

import re

import pgsn


def _edges_into(source: str, node_type: str) -> list[str]:
    ids = re.findall(rf'\t"([^"]+)" \[label="{node_type}\n', source)
    return [line for line in source.splitlines()
            if "->" in line and any(f'-> "{i}"' in line for i in ids)]


def _source(body: str) -> str:
    return pgsn.gsn_dot(pgsn.load_xml_string(f"<PGSN>{body}</PGSN>")).source


def test_a_context_is_pointed_at_with_a_hollow_arrowhead():
    [edge] = _edges_into(
        _source("<Goal>safe<Context>in the plant</Context><undeveloped/></Goal>"),
        "Context")
    assert "arrowhead=empty" in edge
    assert "dir=back" not in edge


def test_an_assumption_is_pointed_at_with_a_hollow_arrowhead():
    [edge] = _edges_into(
        _source("<Goal>safe<Assumption>trained</Assumption><undeveloped/></Goal>"),
        "Assumption")
    assert "arrowhead=empty" in edge
    assert "dir=back" not in edge


def test_a_strategy_takes_context_the_same_way():
    [edge] = _edges_into(_source(
        "<Goal>safe<Strategy>over hazards<Context>hazard log</Context>"
        "<Goal>H1<undeveloped/></Goal></Strategy></Goal>"), "Context")
    assert "arrowhead=empty" in edge


def test_supported_by_keeps_its_solid_arrowhead():
    source = _source("<Goal>safe<Solution>report</Solution></Goal>")
    [edge] = _edges_into(source, "Solution")
    assert "arrowhead" not in edge
