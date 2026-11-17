"""Tests for the modular extension: a Module supporting a goal."""

import pytest

import pgsn
from pgsn.pgsn_xml import PGSNError

CASE = """
<Goal>System is safe
  <Strategy>Argue over functions
    <Goal>Function A is safe
      <Module identifier="fna">Safety argument for function A
        <Goal>Function A is safe
          <Evidence>Test report A</Evidence>
        </Goal>
      </Module>
    </Goal>
    <Goal>Function B is safe<undeveloped/></Goal>
  </Strategy>
</Goal>
"""


def load(source: str):
    return pgsn.load_xml_string(f"<PGSN>{source}</PGSN>").fully_eval()


def labels(dot) -> str:
    return "\n".join(dot.body)


def test_module_is_a_support_of_its_goal():
    goal = pgsn.python_value(load(CASE))["support"]["sub_goals"][0]
    module = goal["support"]
    assert "__Module__" in module
    assert module["identifier"] == "fna"
    assert module["description"] == "Safety argument for function A"
    assert module["argument"]["support"]["description"] == "Test report A"


def test_main_drawing_shows_the_module_but_not_its_argument():
    body = labels(pgsn.gsn_dot(load(CASE)))
    assert "shape=tab" in body
    assert "Safety argument for function A" in body
    assert "Test report A" not in body


def test_each_module_argument_is_drawn_on_its_own():
    dots = pgsn.gsn_module_dots(load(CASE))
    assert list(dots) == ["fna"]
    body = labels(dots["fna"])
    assert "Test report A" in body
    assert "System is safe" not in body


def test_nested_module_is_drawn_in_its_own_right():
    nested = """
    <Goal>Top
      <Module identifier="outer">
        <Goal>Outer
          <Module identifier="inner"><Goal>Inner<Evidence>E</Evidence></Goal></Module>
        </Goal>
      </Module>
    </Goal>
    """
    dots = pgsn.gsn_module_dots(load(nested))
    assert list(dots) == ["outer", "inner"]
    assert "Evidence\nE" not in labels(dots["outer"])
    assert "Evidence\nE" in labels(dots["inner"])


def test_module_needs_an_identifier():
    with pytest.raises(PGSNError, match="identifier"):
        load("<Goal>G<Module><Goal>A</Goal></Module></Goal>")


def test_module_identifier_is_safe_as_a_file_name():
    for bad in ("../up", "a/b", "a b", "a.b", "-a"):
        with pytest.raises(PGSNError, match="identifier"):
            load(f'<Goal>G<Module identifier="{bad}"><Goal>A</Goal></Module></Goal>')


def test_module_can_support_a_defeater():
    case = """
    <Goal>G
      <Defeater>D
        <Module identifier="m"><Goal>A<Evidence>E</Evidence></Goal></Module>
      </Defeater>
    </Goal>
    """
    gsn = load(case)
    assert list(pgsn.gsn_module_dots(gsn)) == ["m"]
    assert "Evidence\nE" not in labels(pgsn.gsn_dot(gsn))


def test_module_holds_exactly_one_goal():
    with pytest.raises(PGSNError, match="one <Goal>"):
        load('<Goal>G<Module identifier="m"><Goal>A</Goal><Goal>B</Goal></Module></Goal>')


def test_two_modules_cannot_share_an_identifier():
    twice = """
    <Goal>G
      <Strategy>S
        <Goal>A<Module identifier="m"><Goal>A</Goal></Module></Goal>
        <Goal>B<Module identifier="m"><Goal>B</Goal></Module></Goal>
      </Strategy>
    </Goal>
    """
    with pytest.raises(ValueError, match="'m'"):
        pgsn.gsn_module_dots(load(twice))


def test_save_gsn_writes_each_module_beside_the_main_drawing(tmp_path):
    out = tmp_path / "case"
    pgsn.save_gsn(load(CASE), str(out), image_format="svg")
    assert (tmp_path / "case.svg").exists()
    assert "Test report A" in (tmp_path / "case.fna.svg").read_text()
