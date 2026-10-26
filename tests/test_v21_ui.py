from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'static/app.js').read_text()
HTML=(ROOT/'static/index.html').read_text()

def test_mission_picker_is_buttons_with_hidden_form_value():
    assert 'data-pick-mission' in APP
    assert 'type="hidden" id="home-mission" name="mission"' in APP
    assert "id('home-mission').value=String(selectedHomeMission)" in APP
    assert '<select id="home-mission"' not in APP

def test_chip_history_is_public_feedback_only():
    assert 'e.to===p.index' in APP
    assert "e.reaction==='positive'||e.reaction==='negative'" in APP
    assert 'USED CHIPS' in APP
    assert 'chipHistory' in APP

def test_cache_version_updated():
    assert 'layout-v21.css?v=22' in HTML
