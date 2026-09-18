"""The order of a list is part of what a document says.

Sub-goals, contexts, assumptions and defeaters are List terms, and PGSN takes
their order to be meaningful: `<ol>` is the only list element, and what a
document writes first is reported first. The implementation used to answer the
question twice. `python_value` reported document order, while every rendering
path went through a `treelib.Tree`, which sorts siblings by tag unless asked
not to -- so `pgsn doc`, `pgsn doc -d json` and `pgsn render` all reordered
what the Python API did not.

The sub-goals below are written in reverse alphabetical order so that sorting
by tag and keeping document order cannot agree by accident.
"""

import pgsn


SOURCE = """
<PGSN>
    <Goal>
        top
        <Strategy>
            over the sub-goals
            <subGoals>
                <ol>
                    <li><Goal>gamma<undeveloped/></Goal></li>
                    <li><Goal>beta<undeveloped/></Goal></li>
                    <li><Goal>alpha<undeveloped/></Goal></li>
                </ol>
            </subGoals>
        </Strategy>
    </Goal>
</PGSN>"""

WRITTEN = ["gamma", "beta", "alpha"]


def _term():
    return pgsn.load_xml_string(SOURCE)


def _order_in(text: str) -> list[str]:
    """The descriptions in the order the text mentions them."""
    return sorted(WRITTEN, key=text.index)


def test_python_value_reports_document_order():
    value = pgsn.python_value(_term())
    assert [g["description"]
            for g in value["support"]["sub_goals"]] == WRITTEN


def test_the_text_rendering_reports_document_order():
    tree = pgsn.gsn_tree(_term())
    assert _order_in(tree.show(stdout=False, sorting=False)) == WRITTEN


def test_the_json_rendering_reports_document_order():
    tree = pgsn.gsn_tree(_term())
    assert _order_in(tree.to_json(sort=False)) == WRITTEN


def test_the_drawing_reports_document_order():
    """`gsn_dot` walks the tree itself, and the order the nodes are emitted in
    is what graphviz lays the siblings out by."""
    assert _order_in(pgsn.gsn_dot(_term()).source) == WRITTEN


def test_the_renderings_agree_with_the_python_value():
    """The one answer the two used to disagree on."""
    tree = pgsn.gsn_tree(_term())
    value = pgsn.python_value(_term())
    written = [g["description"] for g in value["support"]["sub_goals"]]
    assert _order_in(tree.show(stdout=False, sorting=False)) == written
    assert _order_in(tree.to_json(sort=False)) == written
