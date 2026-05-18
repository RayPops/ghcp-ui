"""Tests for the minimal PSO HTTP client."""

from __future__ import annotations

import httpx

from app.integrations.pso.client import PsoClient, PsoConfig


_FAKE_TOKEN = "fake-session-token-abc123"


def _make_client(
    call_log: list[str],
    *,
    config: PsoConfig | None = None,
    token_factory=None,
    data_status_sequence: list[int] | None = None,
    clock=None,
) -> PsoClient:
    """Build a PsoClient backed by an httpx.MockTransport.

    Parameters
    ----------
    call_log:
        Mutable list the transport appends every requested URL path to.
    config:
        Optional :class:`PsoConfig`. Defaults to a permissive config with a
        long TTL so tests not exercising refresh behaviour see one login.
    token_factory:
        Optional ``Callable[[], str]`` returning the token for each login
        response. Lets tests detect that a refresh happened by checking that
        the token actually changed.
    data_status_sequence:
        Optional list of HTTP status codes to return from the ``/data``
        endpoint, one per call. When exhausted, falls back to ``200``.
    clock:
        Optional monotonic clock for the client. Lets tests fast-forward
        past the TTL without sleeping.
    """
    tokens = iter(token_factory()) if callable(token_factory) else iter([_FAKE_TOKEN] * 10)
    data_statuses = iter(data_status_sequence or [])

    def handler(request: httpx.Request) -> httpx.Response:
        call_log.append(request.url.path)
        if request.url.path.endswith("/scheduling/session"):
            return httpx.Response(200, json={"SessionToken": next(tokens)})
        if request.url.path.endswith("/scheduling/data"):
            status = next(data_statuses, 200)
            body = "<ok/>" if status < 400 else f"<error code='{status}'/>"
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://pso.example.test")
    cfg = config or PsoConfig(
        base_url="https://pso.example.test",
        user="MSFT",
        password="hunter2",
        token_ttl_seconds=10_000,  # effectively no expiry by default
        token_refresh_lead_seconds=60,
    )
    return PsoClient(cfg, http=http, clock=clock or (lambda: 0.0))


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


def test_proactive_refresh_before_token_ttl_expires() -> None:
    """A cached token within ``refresh_lead`` of expiry must be refreshed proactively.

    Clock starts at 0. TTL is 100s, lead is 10s. First call mints token at t=0.
    Advance to t=95 (within the 10s lead window) and the next add_tasks must
    re-login before posting data.
    """
    now = {"t": 0.0}
    clock = lambda: now["t"]  # noqa: E731 — tiny test helper
    call_log: list[str] = []
    tokens = iter(["token-A", "token-B"])

    config = PsoConfig(
        base_url="https://pso.example.test",
        user="MSFT",
        password="hunter2",
        token_ttl_seconds=100,
        token_refresh_lead_seconds=10,
    )
    client = _make_client(
        call_log,
        config=config,
        token_factory=lambda: tokens,
        clock=clock,
    )

    client.add_tasks("<dsScheduleData/>")
    assert client.get_valid_token() == "token-A"

    now["t"] = 95.0  # 5s before expiry, inside the 10s lead window
    client.add_tasks("<dsScheduleData/>")
    assert client.get_valid_token() == "token-B", "second call must use the refreshed token"

    session_calls = [p for p in call_log if p.endswith("/scheduling/session")]
    assert len(session_calls) == 2, f"expected 2 logins (initial + proactive), got {len(session_calls)}"


def test_401_triggers_single_refresh_and_retry() -> None:
    """A 401 from /data triggers exactly one re-login and one retry."""
    call_log: list[str] = []
    tokens = iter(["stale-token", "fresh-token"])
    client = _make_client(
        call_log,
        token_factory=lambda: tokens,
        data_status_sequence=[401, 200],
    )

    response = client.add_tasks("<dsScheduleData/>")

    assert response.status_code == 200
    session_calls = [p for p in call_log if p.endswith("/scheduling/session")]
    data_calls = [p for p in call_log if p.endswith("/scheduling/data")]

    assert len(session_calls) == 2, (
        f"expected 2 logins (initial + reactive refresh), got {len(session_calls)}: {call_log}"
    )
    assert len(data_calls) == 2, (
        f"expected 2 data POSTs (original + retry), got {len(data_calls)}: {call_log}"
    )
    # Cached token should be the fresh one after the retry.
    assert client.get_valid_token() == "fresh-token"


def test_second_401_after_refresh_surfaces_error_no_loop() -> None:
    """If the retried request also returns 401, raise — do not retry forever."""
    import pytest

    call_log: list[str] = []
    client = _make_client(
        call_log,
        data_status_sequence=[401, 401],
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.add_tasks("<dsScheduleData/>")

    assert exc_info.value.response.status_code == 401

    session_calls = [p for p in call_log if p.endswith("/scheduling/session")]
    data_calls = [p for p in call_log if p.endswith("/scheduling/data")]

    # Exactly: initial login + reactive refresh = 2. No third login attempt.
    assert len(session_calls) == 2, f"expected exactly 2 logins, got {len(session_calls)}"
    # Exactly: initial POST + one retry = 2. No further retries.
    assert len(data_calls) == 2, f"expected exactly 2 data POSTs, got {len(data_calls)}"


def test_403_also_triggers_refresh_and_retry() -> None:
    """403 must be treated the same as 401 — refresh once, retry once."""
    call_log: list[str] = []
    tokens = iter(["stale-token", "fresh-token"])
    client = _make_client(
        call_log,
        token_factory=lambda: tokens,
        data_status_sequence=[403, 200],
    )

    response = client.add_tasks("<dsScheduleData/>")

    assert response.status_code == 200
    session_calls = [p for p in call_log if p.endswith("/scheduling/session")]
    assert len(session_calls) == 2, f"expected 2 logins (initial + reactive refresh), got {len(session_calls)}"
