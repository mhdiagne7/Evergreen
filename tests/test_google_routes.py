from core.google_routes import directions_url


def test_walking_link_without_key():
    link = directions_url("MRT", "FTX")
    assert link.startswith("https://www.google.com/maps/dir/?")
    assert "travelmode=walking" in link
    assert "key=" not in link
    assert directions_url("UNKNOWN", "MRT") is None
