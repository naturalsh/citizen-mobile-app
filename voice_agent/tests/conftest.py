import pytest

from brain import budget, osm_index, places


@pytest.fixture(autouse=True)
def separate_budget(tmp_path, monkeypatch):
    """Tests never touch the real request counter or Pause AI switch in output/, and never notify."""
    monkeypatch.setenv("BRAIN_BUDGET_DIR", str(tmp_path / "budget"))
    monkeypatch.setenv("BRAIN_CONTROL_DIR", str(tmp_path / "control"))  # never the real Pause AI switch
    monkeypatch.setattr(budget, "NOTIFY", False)
    monkeypatch.setattr(places, "ENABLED", False)  # no OpenStreetMap requests from tests (test_places fakes it)
    monkeypatch.setattr(places, "STREET_LIST", False)  # nor Overpass street lists
    monkeypatch.setattr(osm_index, "ENABLED", False)  # nor the real local index (test_osm_index builds its own)
    monkeypatch.setenv("BRAIN_OUTPUT_DIR", str(tmp_path / "brain-output"))
