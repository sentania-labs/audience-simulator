import concurrent.futures
import pytest
from app.control import Control, LimitReached
from app.config import Settings
from app.budget import Budget


def test_atomic_daily_reservations_and_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('DAILY_BUDGET_USD', '.10')
    c = Control(str(tmp_path/'db'))
    c.admit('one', 1)
    c.admit('two', 2)
    def spend(i):
        try:
            c.reserve('one' if i%2 else 'two', 'vision', .02)
            return True
        except LimitReached:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(spend, range(20))) == 5
    c2 = Control(c.path)
    assert c2.usage('one')['daily_usd'] == .10
    with pytest.raises(LimitReached):
        c2.admit('three', 1)


def test_meeting_limit_reconciliation_and_cancel_keeps_charge(tmp_path, monkeypatch):
    monkeypatch.setenv('MEETING_BUDGET_USD', '.05')
    c = Control(str(tmp_path/'db'))
    c.admit('one', 1)
    charge = c.reserve('one','dialogue',.04)
    with pytest.raises(LimitReached):
        c.reserve('one','tts',.02)
    assert c.usage('one')['meeting_usd'] == .04
    c.reconcile(charge, .01)
    c.reserve('one','tts',.02)
    assert c.usage('one')['meeting_usd'] == .03
    c.finish('one', 100, 'ended')
    with pytest.raises(LimitReached):
        c.reserve('one','dialogue',.001)


def test_admission_pause_concurrency_and_auth_roles(tmp_path, monkeypatch):
    monkeypatch.setenv('MEETING_PASSWORD','meeting-test-password')
    monkeypatch.setenv('ADMIN_PASSWORD','admin-test-password')
    monkeypatch.setenv('MAX_CONCURRENT_MEETINGS','1')
    c = Control(str(tmp_path/'db'))
    token = c.login('meeting','meeting-test-password')
    assert c.authorized(token,'meeting')
    assert not c.authorized(token,'admin')
    c.logout(token)
    assert not c.authorized(token,'meeting')
    c.admit('one',2)
    with pytest.raises(LimitReached):
        c.admit('two',1)
    c.finish('one',50,'ended')
    c.pause(True)
    with pytest.raises(LimitReached):
        c.admit('two',1)
    c.pause(False)
    c.admit('two',1)


def test_unknown_pricing_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv('PROVIDER_MODE','hosted')
    monkeypatch.delenv('COST_RATES_JSON', raising=False)
    c=Control(str(tmp_path/'db'))
    with pytest.raises(ValueError):
        Budget(c,'one',Settings(),lambda reason:None)


def test_daily_reset_uses_calendar_day(tmp_path, monkeypatch):
    import app.control as module
    monkeypatch.setattr(module,'day',lambda:'2026-10-08')
    c=Control(str(tmp_path/'db'))
    c.admit('one',1)
    c.reserve('one','vision',.1)
    monkeypatch.setattr(module,'day',lambda:'2026-10-09')
    assert c.usage('one') == dict(meeting_usd=.1,daily_usd=0,warning=False)
