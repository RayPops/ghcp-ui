"""Minimal IFS PSO HTTP client.

Scope
-----
* Holds credentials (never a long-lived bearer token from the operator).
* Calls ``/scheduling/session`` to mint a short-lived ``SessionToken`` and
  caches it in memory together with the timestamp it was issued at.
* Automatically refreshes the token before it expires (proactive) and again
  if the server replies ``401``/``403`` on a data call (reactive). The
  reactive path retries the request exactly once — never loops.
* Posts XML payloads to the ``/api/v1/scheduling/data`` endpoint.

Credentials are read from environment variables. They must never be logged.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


# Observed in the IFS demo cluster: session tokens are valid for ~20 minutes.
# We bias slightly low (1100s) so a single demo step does not race the server.
_DEFAULT_TOKEN_TTL_SECONDS = 1100
# How early to pre-emptively refresh before the cached token expires.
_DEFAULT_REFRESH_LEAD_SECONDS = 60


@dataclass(frozen=True)
class PsoConfig:
    """Connection details for the PSO instance.

    ``base_url`` is the full origin including scheme, e.g.
    ``https://sm-pso6-pso-1.ifsdemoworld.com/IFSSchedulingRESTfulGateway``.

    ``token_ttl_seconds`` controls when the in-memory session token is
    considered stale and proactively refreshed. The PSO server does not
    return an ``expires_in`` field in the session payload, so we have to
    track it ourselves.
    """

    base_url: str
    user: str
    password: str
    account_id: str = "smfsm6e1fsm19"
    dataset_id: str = "CC_LIVE"
    timeout_seconds: float = 30.0
    token_ttl_seconds: int = _DEFAULT_TOKEN_TTL_SECONDS
    token_refresh_lead_seconds: int = _DEFAULT_REFRESH_LEAD_SECONDS

    @classmethod
    def from_env(cls) -> "PsoConfig":
        """Load configuration from ``PSO_*`` environment variables.

        Required: ``PSO_URL``, ``PSO_USER``, ``PSO_PWD``.
        Optional: ``PSO_ACCOUNT_ID``, ``PSO_DATASET_ID``, ``PSO_TIMEOUT_SECONDS``,
        ``PSO_TOKEN_TTL_SECONDS``, ``PSO_TOKEN_REFRESH_LEAD_SECONDS``.
        """
        try:
            base_url = os.environ["PSO_URL"]
            user = os.environ["PSO_USER"]
            password = os.environ["PSO_PWD"]
        except KeyError as exc:
            missing = exc.args[0]
            raise RuntimeError(
                f"Missing PSO env var: {missing}. "
                "Set PSO_URL, PSO_USER, PSO_PWD before calling PsoClient."
            ) from None

        return cls(
            base_url=base_url.rstrip("/"),
            user=user,
            password=password,
            account_id=os.environ.get("PSO_ACCOUNT_ID", "smfsm6e1fsm19"),
            dataset_id=os.environ.get("PSO_DATASET_ID", "CC_LIVE"),
            timeout_seconds=float(os.environ.get("PSO_TIMEOUT_SECONDS", "30")),
            token_ttl_seconds=int(
                os.environ.get("PSO_TOKEN_TTL_SECONDS", str(_DEFAULT_TOKEN_TTL_SECONDS))
            ),
            token_refresh_lead_seconds=int(
                os.environ.get(
                    "PSO_TOKEN_REFRESH_LEAD_SECONDS", str(_DEFAULT_REFRESH_LEAD_SECONDS)
                )
            ),
        )


# --------------------------------------------------------------------------- #
# Response wrapper
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PsoHttpResponse:
    """Lightweight view of an HTTP response from PSO."""

    status_code: int
    body: str


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


_SESSION_PATH = "/api/v1/scheduling/session"
_DATA_PATH = "/api/v1/scheduling/data"

_DATA_QUERY = {
    "dataType": "SCHEDULE",
    "waitForCompletion": "true",
    "includeOutput": "true",
    "compressed": "false",
    "submitCompressed": "false",
}


class PsoClient:
    """Minimal sync client for the PSO REST gateway.

    The HTTP transport is injectable so tests can use ``httpx.MockTransport``.
    A ``clock`` callable (default :func:`time.monotonic`) is also injectable
    so tests can drive the token expiry deterministically without sleeping.
    """

    def __init__(
        self,
        config: PsoConfig,
        *,
        http: Optional[httpx.Client] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._token: Optional[str] = None
        self._token_issued_at: Optional[float] = None
        self._clock = clock
        self._http = http or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

    # ---------------- internal helpers ---------------- #

    def _login(self, *, reason: str) -> str:
        """POST credentials to ``/session`` and cache the returned token.

        ``reason`` is logged at INFO so demo viewers can see whether a refresh
        was the first call, a proactive pre-expiry refresh, or a reactive
        post-401 retry.
        """
        params = {
            "accountId": self._config.account_id,
            "userName": self._config.user,
            "password": self._config.password,
        }
        logger.info(
            "PSO login (%s): account=%s user=%s",
            reason,
            self._config.account_id,
            self._config.user,
        )
        response = self._http.post(_SESSION_PATH, params=params)
        response.raise_for_status()

        payload = response.json()
        token = payload.get("SessionToken")
        if not token:
            raise RuntimeError("PSO login response did not contain SessionToken")

        self._token = token
        self._token_issued_at = self._clock()
        # Never log the token itself, only its length.
        logger.info("PSO login successful (token length=%d)", len(token))
        return token

    def _token_is_stale(self) -> bool:
        """True if there is no token, or the cached one is at/near expiry."""
        if self._token is None or self._token_issued_at is None:
            return True
        age = self._clock() - self._token_issued_at
        ttl = self._config.token_ttl_seconds
        lead = self._config.token_refresh_lead_seconds
        return age + lead >= ttl

    def get_valid_token(self) -> str:
        """Return a token that is fresh enough to use for the next call.

        Triggers a proactive ``/session`` POST if the cached token is missing
        or within ``token_refresh_lead_seconds`` of expiry. This is the single
        entry point everything calling PSO should go through; the client never
        passes raw tokens between methods.
        """
        if self._token_is_stale():
            reason = "initial login" if self._token is None else "proactive refresh"
            return self._login(reason=reason)
        # mypy: at this point self._token is not None.
        return self._token  # type: ignore[return-value]

    def _invalidate_token(self) -> None:
        """Drop the cached token so the next ``get_valid_token`` re-logs in."""
        self._token = None
        self._token_issued_at = None

    # ---------------- public API ---------------- #

    def add_tasks(self, xml_body: str) -> PsoHttpResponse:
        """Post an ``<dsScheduleData>`` XML body to the ``/data`` endpoint.

        Always pre-validates the token via :meth:`get_valid_token`. If the
        server still replies ``401`` or ``403`` (e.g. the token was revoked
        out-of-band), the client refreshes once and retries the request once.
        A second auth failure is surfaced to the caller — no retry loop.
        """
        token = self.get_valid_token()
        response = self._post_data(xml_body, token)

        if response.status_code in (401, 403):
            logger.info(
                "PSO data POST returned %s; refreshing token and retrying once",
                response.status_code,
            )
            self._invalidate_token()
            retry_token = self._login(reason=f"reactive refresh after {response.status_code}")
            response = self._post_data(xml_body, retry_token)
            if response.status_code in (401, 403):
                logger.error(
                    "PSO data POST still %s after token refresh; not retrying again",
                    response.status_code,
                )

        # Log status and body length only; the body may contain customer notes.
        logger.info(
            "PSO add_tasks response: status=%s body_length=%d",
            response.status_code,
            len(response.text or ""),
        )
        response.raise_for_status()
        return PsoHttpResponse(status_code=response.status_code, body=response.text)

    def _post_data(self, xml_body: str, token: str) -> httpx.Response:
        """POST the XML body using the supplied token. No retry logic here."""
        headers = {
            "Content-Type": "application/xml",
            "apikey": token,
        }
        logger.info("PSO add_tasks: posting %d byte XML payload", len(xml_body))
        return self._http.post(
            _DATA_PATH,
            params=_DATA_QUERY,
            headers=headers,
            content=xml_body,
        )
