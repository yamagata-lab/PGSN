"""A label in a drawing is the document's text and nothing else.

`gsn_dot` writes each label into the DOT source, where several forms of text
mean something to graphviz. A label of the form <...> is an HTML label, which
the graphviz package writes out unquoted, so the text after its first closing
> becomes attributes of the node: `image="/etc/hosts"` makes graphviz open that
file, and an image file would be embedded in the drawing. A trailing backslash
escapes the closing quote, and the source no longer parses. \\N and \\G are
replaced by the names of the node and the graph. A document that `pgsn render`
draws may come from someone else, so none of this may reach graphviz.
"""

import html
import re
import shutil

import graphviz
import pytest

import pgsn

# The key ends the HTML label opened by its first <, then opens another for
# tooltip, which the value of the inner record closes. Both are folded into one
# box, so the label the node gets is <<b>x</b>> image="/etc/hosts" tooltip=<...>.
_HTML_KEY = """
<PGSN>
  <dl>
    <dt>&lt;&lt;b&gt;x&lt;/b&gt;&gt; image="/etc/hosts" tooltip=&lt;</dt>
    <dd><dl><dt>k</dt><dd>x&gt;</dd></dl></dd>
  </dl>
</PGSN>
"""


def test_html_like_text_is_quoted():
    source = pgsn.gsn_dot(pgsn.load_xml_string(_HTML_KEY), label_width=0).source
    assert "label=<" not in source
    assert 'image=\\"/etc/hosts\\"' in source


def _drawn_text(description: str) -> list[str]:
    term = pgsn.goal(description=description,
                     support=pgsn.undeveloped).fully_eval()
    svg = graphviz.Source(pgsn.gsn_dot(term).source).pipe(
        format="svg", quiet=True).decode()
    return [html.unescape(t) for t in re.findall(r"<text[^>]*>(.*?)</text>", svg)]


@pytest.mark.skipif(shutil.which("dot") is None,
                    reason="graphviz's dot is not installed")
@pytest.mark.parametrize("description", [
    r"node \N graph \G",
    "ends with \\",
    'a\\\\" image="/etc/hosts" k="',
])
def test_backslashes_and_quotes_are_drawn_as_written(description):
    assert _drawn_text(description) == ["Goal", description,
                                        pgsn.gsn.UNDEVELOPED_DECORATOR]
