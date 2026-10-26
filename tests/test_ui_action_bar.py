from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
CSS = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')
HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


def test_ai_advance_is_only_in_dedicated_right_action_panel():
    assert 'function aiTurnActionPanel()' in APP
    assert 'class="btn primary journal-ai-button" type="button" data-do="advance_ai"' in APP
    assert 'class="journal-column">${missionCardPanel()}${aiTurnActionPanel()}${journalPanel()}' in APP
    assert 'class="btn primary dock-button ai-advance"' not in APP
    assert APP.count('data-do="advance_ai"') == 1


def test_ai_panel_only_appears_during_active_ai_turn():
    assert "state.phase!=='turn' || !state.ai_waiting || state.inspect!==null" in APP
    assert "if(!actor || !actor.bot) return ''" in APP


def test_sidebar_position_above_history_and_remains_visible():
    assert 'position:sticky;' in CSS
    assert '.game-main .journal-column .journal-panel' in CSS
    assert '.game-main .journal-ai-button' in CSS
    assert '.game-main .hand-dock{' in CSS


def test_cache_busting():
    assert 'style.css?v=22' in HTML
    assert 'app.js?v=22' in HTML
