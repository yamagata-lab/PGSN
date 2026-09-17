"""Every example validates against `PGSN.rng`.

The schema describes the surface syntax, which makes it documentation with a
validator attached — and documentation drifts unless something checks it. It
drifted before: when this test was written four of the twenty-six documents
under `examples/` validated, and the schema was still describing spellings the
language had dropped.

Validation is not evaluation, and the two catch different things. The compiler
ignores a child element it does not know, so a misspelled `<Defeater>` produces
a document with one defeater missing and no complaint; the schema rejects it.
That is the case the negative tests below are here for.

`xmllint` is used when it is available because it is quick, and `jing` — the
reference implementation — otherwise. On this corpus the two agree file for
file, as does `rnv` on the compact syntax `trang` converts the schema to.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "PGSN.rng"
EXAMPLES = ROOT / "examples"


def _validator():
    if shutil.which("xmllint"):
        return lambda path: subprocess.run(
            ["xmllint", "--noout", "--relaxng", str(SCHEMA), str(path)],
            capture_output=True, text=True)
    if shutil.which("jing"):
        return lambda path: subprocess.run(
            ["jing", str(SCHEMA), str(path)], capture_output=True, text=True)
    return None


VALIDATE = _validator()

pytestmark = pytest.mark.skipif(
    VALIDATE is None, reason="needs xmllint or jing to validate RELAX NG")


@pytest.mark.parametrize("path", sorted(EXAMPLES.rglob("*.xml")),
                         ids=lambda p: str(p.relative_to(EXAMPLES)))
def test_an_example_validates(path):
    result = VALIDATE(path)
    assert result.returncode == 0, result.stdout + result.stderr


REJECTED = {
    "an element the language does not have":
        "<PGSN><bogus/></PGSN>",
    "a misspelled Defeater, which the compiler would drop in silence":
        "<PGSN><Goal>g<Rebuttal>r</Rebuttal><Evidence>e</Evidence></Goal></PGSN>",
    "a <def> with nothing to bind":
        "<PGSN><def>x</def>v</PGSN>",
    "a <get> with no key":
        '<PGSN><get of="r"/></PGSN>',
    "a <send> with no method":
        '<PGSN><send to="r"/></PGSN>',
    "a <Context> on an <Evidence>, which cannot hold one":
        "<PGSN><Evidence>e<Context>c</Context></Evidence></PGSN>",
    "a <Strategy> with no sub-goals":
        "<PGSN><Strategy>s</Strategy></PGSN>",
    "an <if> with no <else>":
        "<PGSN><if><cond>c</cond><then>t</then></if></PGSN>",
    "a <dt> with no <dd>":
        '<PGSN><dl><dt key="k"/></dl></PGSN>',
    "a <param> on a <PGSN>, which takes none":
        '<PGSN><param name="p"/>v</PGSN>',
}


@pytest.mark.parametrize("source", REJECTED.values(), ids=list(REJECTED))
def test_the_schema_rejects(source, tmp_path):
    path = tmp_path / "doc.xml"
    path.write_text(source)
    assert VALIDATE(path).returncode != 0
