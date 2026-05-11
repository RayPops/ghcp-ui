"""Tests for the minimal PSO HTTP client."""

from __future__ import annotations

import json

import httpx

from app.integrations.pso.client import PsoClient, PsoConfig


_FAKE_TOKEN = "fake-session-token-abc123"


def _make_client(call_log: list[str]) -> PsoClient:
    """Build a PsoClient backed by an httpx.MockTransport.

    The transport records every requested URL path so the test can assert on
    call ordering and counts.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        call_log.append(request.url.path)
        if request.url.path.endswith("/scheduling/session"):
            return httpx.Response(200, json={"SessionToken": _FAKE_TOKEN})
        if request.url.path.endswith("/scheduling/data"):
            return httpx.Response(200, text="<ok/>")
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://pso.example.test")
    config = PsoConfig(
        base_url="https://pso.example.test",
        user="MSFT",
        password="hunter2",
    )
    return PsoClient(config, http=http)


def test_login_caches_token() -> None:
    """Two add_tasks calls should trigger one /session POST and two /data POSTs."""
    call_log: list[str] = []
    client = _make_client(call_log)

    first = client.add_tasks("<dsScheduleData/>")
    second = client.add_tasks("<dsScheduleData/>")

    assert first.status_code == 200
    assert second.status_code == 200

    session_calls = [p for p in call_log if p.endswith("/scheduling/session")]
    data_calls = [p for p in call_log if p.endswith("/scheduling/data")]

    assert len(session_calls) == 1, f"expected 1 /session call, got {len(session_calls)}: {call_log}"
    assert len(data_calls) == 2, f"expected 2 /data calls, got {len(data_calls)}: {call_log}"
    assert call_log[0].endswith("/scheduling/session"), "login must happen before first data call"
