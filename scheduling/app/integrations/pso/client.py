"""Minimal IFS PSO HTTP client.

Scope (deliberately small for the demo)
---------------------------------------
* Logs in once on first request, caches the ``SessionToken`` in memory.
* Posts XML payloads to the ``/api/v1/scheduling/data`` endpoint.

Out of scope for now (will be added once Federico confirms the auth shape):
* 401-triggered re-auth and retry.
* Custom exception types — ``httpx.HTTPStatusError`` is allowed to bubble.
* Persistent token storage.

Credentials are read from environment variables. They must never be logged.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PsoConfig:
    """Connection details for the PSO instance.

    ``base_url`` is the full origin including scheme, e.g.
    ``https://sm-pso6-pso-1.ifsdemoworld.com/IFSSchedulingRESTfulGateway``.
    """

    base_url: str
    user: str
    password: str
    account_id: str = "smfsm6e1fsm19"
    dataset_id: str = "CC_LIVE"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "PsoConfig":
        """Load configuration from ``PSO_*`` environment variables.

        Required: ``PSO_URL``, ``PSO_USER``, ``PSO_PWD``.
        Optional: ``PSO_ACCOUNT_ID``, ``PSO_DATASET_ID``, ``PSO_TIMEOUT_SECONDS``.
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
    """

    def __init__(
        self,
        config: PsoConfig,
        *,
        http: Optional[httpx.Client] = None,
    ) -> None:
        self._config = config
        self._token: Optional[str] = None
        self._http = http or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

    # ---------------- internal helpers ---------------- #

    def _login(self) -> str:
        """POST credentials to ``/session`` and cache the returned token."""
        params = {
            "accountId": self._config.account_id,
            "userName": self._config.user,
            "password": self._config.password,
        }
        logger.info("PSO login: account=%s user=%s", self._config.account_id, self._config.user)
        response = self._http.post(_SESSION_PATH, params=params)
        response.raise_for_status()

        payload = response.json()
        token = payload.get("SessionToken")
        if not token:
            raise RuntimeError("PSO login response did not contain SessionToken")

        self._token = token
        # Never log the token itself, only its length.
        logger.info("PSO login successful (token length=%d)", len(token))
        return token

    def _ensure_token(self) -> str:
        if self._token is None:
            return self._login()
        return self._token

    # ---------------- public API ---------------- #

    def add_tasks(self, xml_body: str) -> PsoHttpResponse:
        """Post an ``<dsScheduleData>`` XML body to the ``/data`` endpoint.

        Authenticates lazily on first use; reuses the cached session token
        on subsequent calls.
        """
        token = self._ensure_token()
        headers = {
            "Content-Type": "application/xml",
            "apikey": token,
        }
        logger.info("PSO add_tasks: posting %d byte XML payload", len(xml_body))
        response = self._http.post(
            _DATA_PATH,
            params=_DATA_QUERY,
            headers=headers,
            content=xml_body,
        )
        # Log status and body length only; the body may contain customer notes.
        logger.info(
            "PSO add_tasks response: status=%s body_length=%d",
            response.status_code,
            len(response.text or ""),
        )
        response.raise_for_status()
        return PsoHttpResponse(status_code=response.status_code, body=response.text)
