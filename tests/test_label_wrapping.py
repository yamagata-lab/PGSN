"""Graphviz does not wrap a label, so a node is as wide as its longest line.

A generated case states a whole provision in a description -- the EU AI Act
example reaches 197 characters in one -- and the drawing then comes out several
times wider than it is tall, with edges running the width of the page. The
wrapping is what keeps a figure readable, so it is checked here: nothing else
would notice if it were lost.
"""

import re

import pgsn

_LONG = ("Identity Verification may deploy inference of emotions in the "
         "workplace or in education institutions, in which case Art. 5 "
         "forbids placing it on the market at all")


def _dot_source(label: str, **kwargs) -> str:
    term = pgsn.load_xml_string(
        f"<PGSN><Goal>{label}<undeveloped/></Goal></PGSN>")
    return pgsn.gsn_dot(term, **kwargs).source


def _longest_label_line(source: str) -> int:
    # A label is one quoted string, and graphviz writes its breaks as real
    # newlines, so the attribute has to be read across the lines of the source.
    labels = re.findall(r'label="(.*?)"', source, re.S)
    return max(len(part) for label in labels for part in label.split("\n"))


def test_a_long_description_is_wrapped():
    assert _longest_label_line(_dot_source(_LONG)) <= pgsn.LABEL_WIDTH


def test_the_width_can_be_chosen():
    assert _longest_label_line(_dot_source(_LONG, label_width=20)) <= 20


def test_zero_leaves_the_label_on_one_line():
    assert _longest_label_line(_dot_source(_LONG, label_width=0)) == len(_LONG)
