"""Tests for backend/main.py admin API endpoints."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for _path in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import config  # noqa: E402
import main  # noqa: E402
import pytest  # noqa: E402


class StubAdminRequest:
    def __init__(self, state: SimpleNamespace, body=None, headers: dict | None = None, query_params: dict | None = None):
        self.app = SimpleNamespace(state=state)
        self._body = body
        self.headers = headers or {}
        self.query_params = query_params or {}

    async def json(self):
        return self._body if self._body is not None else {}


@pytest.fixture
def valid_headers():
    return {"X-Admin-Key": config.admin_api_key()}


@pytest.fixture
def ready_state():
    state = SimpleNamespace()
    state.firebase_ready = True
    state.settings = SimpleNamespace(llm_provider="mock")
    return state


async def test_admin_stats_unauthorized():
    req = StubAdminRequest(SimpleNamespace(firebase_ready=True), headers={})
    res = await main.admin_stats(req)
    assert res.status_code == 401


async def test_admin_stats_firebase_not_ready(valid_headers):
    req = StubAdminRequest(SimpleNamespace(firebase_ready=False), headers=valid_headers)
    res = await main.admin_stats(req)
    assert res.status_code == 503


async def test_admin_stats_success(valid_headers, ready_state):
    req = StubAdminRequest(ready_state, headers=valid_headers)
    mock_stats = {
        "total_groups": 2,
        "active_groups": 1,
        "claimed_groups": 1,
        "total_blocked": 42,
    }
    with patch("firebase_client.get_admin_stats", new_callable=AsyncMock) as m:
        m.return_value = mock_stats
        res = await main.admin_stats(req)
        assert res.status_code == 200
        assert json.loads(res.body) == mock_stats


async def test_admin_list_groups_success(valid_headers, ready_state):
    req = StubAdminRequest(ready_state, headers=valid_headers)
    mock_groups = [{"chat_id": -1001, "group_name": "Test Group"}]
    with patch("firebase_client.list_all_groups", new_callable=AsyncMock) as m:
        m.return_value = mock_groups
        res = await main.admin_list_groups(req)
        assert res.status_code == 200
        assert json.loads(res.body) == {"groups": mock_groups}


async def test_admin_create_group_success(valid_headers, ready_state):
    body = {"chat_id": -100999, "group_name": "New Alpha Group", "active": True}
    req = StubAdminRequest(ready_state, body=body, headers=valid_headers)
    created_doc = {"chat_id": -100999, "group_name": "New Alpha Group", "active": True}
    with patch("firebase_client.create_group_manual", new_callable=AsyncMock) as m:
        m.return_value = created_doc
        res = await main.admin_create_group(req)
        assert res.status_code == 201
        data = json.loads(res.body)
        assert data["ok"] is True
        assert data["group"]["chat_id"] == -100999


async def test_admin_update_group_success(valid_headers, ready_state):
    body = {"group_name": "Renamed Alpha", "active": False}
    req = StubAdminRequest(ready_state, body=body, headers=valid_headers)
    with patch("firebase_client.update_group", new_callable=AsyncMock) as m:
        m.return_value = {"chat_id": -1001, "group_name": "Renamed Alpha", "active": False}
        res = await main.admin_update_group(-1001, req)
        assert res.status_code == 200
        data = json.loads(res.body)
        assert data["ok"] is True
        assert data["group"]["group_name"] == "Renamed Alpha"


async def test_admin_delete_group_success(valid_headers, ready_state):
    req = StubAdminRequest(ready_state, headers=valid_headers)
    with patch("firebase_client.delete_group", new_callable=AsyncMock) as m:
        m.return_value = True
        res = await main.admin_delete_group(-1001, req)
        assert res.status_code == 200
        data = json.loads(res.body)
        assert data["ok"] is True
        assert data["chat_id"] == -1001


async def test_analytics_collect_success(ready_state):
    body = {
        "path": "/dashboard",
        "referrer": "https://t.co/abc",
        "visitor_id": "v_test123",
        "device": "mobile",
    }
    req = StubAdminRequest(ready_state, body=body)
    with patch("firebase_client.record_pageview", new_callable=AsyncMock) as m:
        m.return_value = {"ok": True}
        res = await main.collect_analytics(req)
        assert res.status_code == 200
        assert json.loads(res.body) == {"ok": True}
        m.assert_called_once_with(
            path="/dashboard",
            referrer="https://t.co/abc",
            visitor_id="v_test123",
            device="mobile",
        )


async def test_analytics_collect_skips_admin(ready_state):
    body = {"path": "/admin/settings"}
    req = StubAdminRequest(ready_state, body=body)
    with patch("firebase_client.record_pageview", new_callable=AsyncMock) as m:
        res = await main.collect_analytics(req)
        assert res.status_code == 200
        assert json.loads(res.body) == {"ok": True, "skipped": True}
        m.assert_not_called()


async def test_admin_analytics_success(valid_headers, ready_state):
    req = StubAdminRequest(ready_state, headers=valid_headers)
    mock_summary = {
        "total_pageviews": 100,
        "unique_visitors": 50,
        "today_pageviews": 20,
        "today_uniques": 10,
        "top_paths": [{"path": "/", "count": 80}],
        "top_referrers": [{"referrer": "X / Twitter", "count": 60}],
        "device_breakdown": {"desktop": 70, "mobile": 30},
        "daily_trend": [{"date": "2026-11-10", "pageviews": 20, "uniques": 10}],
        "recent_visits": [],
    }
    with patch("firebase_client.get_analytics_summary", new_callable=AsyncMock) as m:
        m.return_value = mock_summary
        res = await main.admin_analytics(req)
        assert res.status_code == 200
        assert json.loads(res.body) == mock_summary


