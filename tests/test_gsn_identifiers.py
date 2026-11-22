"""A drawing heads every GSN element with an identifier, as GSN v3 requires.

1:2.1.2 of the standard gives each element an identifier, unique within the
argument module. `gsn_dot` numbers the elements of each kind in document
order, with the prefixes the standard's own figures use: G, S, Sn, C and A,
and CG for a defeater, which the dialectic figures draw as a goal that
challenges. The identifiers are for reading the drawing; a document cannot
refer to them. The same drawing gives an assumption the letter A at its right
and Challenges an open arrowhead, as Tables 1:2-1 and 1:6-2 do.
"""

import re

import pgsn

_DOCUMENT = """<PGSN>
  <Goal>safe
    <Context>in the plant</Context>
    <Assumption>trained</Assumption>
    <Defeater>H4 is unmitigated
      <Defeater>H4 was removed<Solution>change log</Solution></Defeater>
    </Defeater>
    <Strategy>over each hazard
      <Goal>H1 is mitigated<Solution>test report</Solution></Goal>
      <Goal>H2 is mitigated<undeveloped/></Goal>
    </Strategy>
  </Goal>
</PGSN>"""


def _source() -> str:
    return pgsn.gsn_dot(pgsn.load_xml_string(_DOCUMENT)).source


def _headings(source: str) -> dict[str, str]:
    """Each description, keyed to the heading the drawing gives it."""
    return {m.group(2): m.group(1)
            for m in re.finditer(r'label="([^"\n]+)\n([^"\n]+)', source)}


def test_each_kind_is_numbered_in_document_order():
    assert _headings(_source()) == {
        "safe": "G1", "in the plant": "C1", "trained": "A1",
        "H4 is unmitigated": "CG1", "H4 was removed": "CG2",
        "change log": "Sn1", "over each hazard": "S1",
        "H1 is mitigated": "G2", "test report": "Sn2",
        "H2 is mitigated": "G3",
    }


def test_an_assumption_carries_the_letter_at_its_right():
    # \r sets the line before it flush right; the label's other breaks are
    # real newlines, which graphviz centres.
    assert 'label="A1\ntrained\nA\\r"' in _source()


def test_nothing_else_carries_the_letter():
    assert _source().count("A\\r") == 1


def test_a_challenge_has_an_open_arrowhead():
    challenges = [line for line in _source().splitlines()
                  if "->" in line and "style=dashed" in line]
    assert len(challenges) == 2
    assert all("arrowtail=vee" in line for line in challenges)
