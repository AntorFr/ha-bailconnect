"""BaillConnect API client.

Authenticates via the Laravel web UI, then extracts regulation data from the
inline JSON blob (window.assets.regulation) and sends commands via the
/api-client endpoints.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

import aiohttp
from bs4 import BeautifulSoup

try:
    from .const import BASE_URL, LOGIN_URL
except ImportError:
    # Allow standalone usage (e.g. scripts/test_login.py)
    BASE_URL = "https://www.baillconnect.com"
    LOGIN_URL = "/client/connexion"

_LOGGER = logging.getLogger(__name__)

# Regex to extract the JSON blob from the inline <script> tag
_REGULATION_RE = re.compile(
    r"assets\.regulation\s*=\s*(\{.+?\});\s*assets\.", re.DOTALL
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BaillConnectError(Exception):
    """Base exception for BaillConnect errors."""


class AuthenticationError(BaillConnectError):
    """Raised when authentication fails (bad credentials or expired session)."""


class CannotConnect(BaillConnectError):
    """Raised when the server is unreachable."""


class ParsingError(BaillConnectError):
    """Raised when the page structure is unexpected."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ThermostatData:
    """Represents a single thermostat (one per room)."""

    thermostat_id: int
    key: str  # e.g. "th1"
    name: str
    current_temperature: float | None = None
    setpoint_hot_t1: float | None = None
    setpoint_hot_t2: float | None = None
    setpoint_cool_t1: float | None = None
    setpoint_cool_t2: float | None = None
    t1_t2: int = 1  # 1=comfort (T1), 2=eco (T2)
    zone: int = 1
    is_on: bool = True
    is_connected: bool = True
    is_battery_low: bool = False
    motor_state: int = 0
    raw: dict = field(default_factory=dict)


@dataclass
class RegulationData:
    """Represents the full regulation system state."""

    regulation_id: int
    uc_mode: int  # 0=stop, 1=heat, 2=cool, 3=dehumidify (TBC)
    ui_on: bool
    ui_sp: float  # Global setpoint
    is_connected: bool
    uc_cool_mode: bool
    uc_hot_min: float
    uc_hot_max: float
    uc_cold_min: float
    uc_cold_max: float
    thermostats: list[ThermostatData] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

class BaillConnectApiClient:
    """Async client that authenticates and interacts with the BaillConnect web UI."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._base_url = base_url
        self._authenticated = False
        self._csrf_token: str | None = None
        self._regulation_id: int | None = None
        self._dashboard_url: str | None = None

    @property
    def regulation_id(self) -> int | None:
        """Return the regulation ID discovered at login."""
        return self._regulation_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Log in to BaillConnect.

        Raises AuthenticationError on bad credentials.
        Raises CannotConnect on network issues.
        """
        try:
            # Step 1 — GET login page to obtain CSRF tokens
            login_url = f"{self._base_url}{LOGIN_URL}"
            _LOGGER.debug("Fetching login page: %s", login_url)

            async with self._session.get(login_url) as resp:
                if resp.status != 200:
                    raise CannotConnect(
                        f"Login page returned HTTP {resp.status}"
                    )
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            token_input = soup.find("input", {"name": "_token"})
            if token_input is None:
                raise ParsingError("CSRF _token not found on login page")
            self._csrf_token = token_input.get("value", "")

            # Step 2 — POST credentials
            xsrf_value = self._get_xsrf_cookie_value()
            headers: dict[str, str] = {}
            if xsrf_value:
                headers["X-XSRF-TOKEN"] = xsrf_value

            payload = {
                "_token": self._csrf_token,
                "email": self._email,
                "password": self._password,
            }

            _LOGGER.debug("Posting credentials to %s", login_url)
            async with self._session.post(
                login_url,
                data=payload,
                headers=headers,
                allow_redirects=True,
            ) as resp:
                final_url = str(resp.url)
                _LOGGER.debug(
                    "Post-login redirect: %s (HTTP %s)", final_url, resp.status
                )

                if "connexion" in final_url:
                    raise AuthenticationError("Invalid email or password")

                self._authenticated = True
                self._dashboard_url = final_url

                # Extract regulation ID from URL: /client/regulations/{id}
                match = re.search(r"/regulations/(\d+)", final_url)
                if match:
                    self._regulation_id = int(match.group(1))

                _LOGGER.info(
                    "Authenticated (regulation_id=%s, dashboard=%s)",
                    self._regulation_id,
                    final_url,
                )
                return True

        except aiohttp.ClientError as err:
            raise CannotConnect(f"Network error: {err}") from err

    async def fetch_page(self, path: str | None = None) -> str:
        """Fetch an authenticated page and return its HTML.

        If *path* is None, fetches the dashboard URL discovered at login.
        Handles session expiry by re-authenticating once.
        """
        await self._ensure_authenticated()

        url = f"{self._base_url}{path}" if path else self._dashboard_url
        if url is None:
            raise BaillConnectError("No URL to fetch — authenticate first")

        try:
            async with self._session.get(url, allow_redirects=True) as resp:
                final_url = str(resp.url)

                if "connexion" in final_url:
                    _LOGGER.warning("Session expired, re-authenticating")
                    self._authenticated = False
                    await self.authenticate()
                    return await self.fetch_page(path)

                return await resp.text()

        except aiohttp.ClientError as err:
            raise CannotConnect(f"Network error fetching {url}: {err}") from err

    async def get_regulation(self) -> RegulationData:
        """Fetch the dashboard and parse the regulation JSON."""
        html = await self.fetch_page()
        return self._parse_regulation(html)

    async def api_post(self, path: str, data: dict) -> dict | None:
        """Send a POST request to the /api-client endpoint.

        Returns the JSON response body, or None if no JSON body.
        """
        await self._ensure_authenticated()

        url = f"{self._base_url}/api-client{path}"
        headers = self._api_headers()

        _LOGGER.debug("API POST %s — %s", url, data)
        try:
            async with self._session.post(
                url, json=data, headers=headers, allow_redirects=True
            ) as resp:
                final_url = str(resp.url)
                if "connexion" in final_url:
                    _LOGGER.warning("Session expired during API call")
                    self._authenticated = False
                    await self.authenticate()
                    return await self.api_post(path, data)

                _LOGGER.debug("API response: HTTP %s", resp.status)
                if resp.content_type and "json" in resp.content_type:
                    return await resp.json()
                return None
        except aiohttp.ClientError as err:
            raise CannotConnect(f"API error: {err}") from err

    async def set_thermostat_setpoint(
        self, thermostat_id: int, key: str, value: float
    ) -> dict | None:
        """Update a thermostat setpoint.

        *key* is one of: setpoint_hot_t1, setpoint_hot_t2,
        setpoint_cool_t1, setpoint_cool_t2.
        """
        return await self.api_post(
            f"/regulations/{self._regulation_id}",
            {"key": f"thermostats.{thermostat_id}.{key}", "value": value},
        )

    async def set_thermostat_on(
        self, thermostat_id: int, is_on: bool
    ) -> dict | None:
        """Turn a thermostat on or off."""
        return await self.api_post(
            f"/regulations/{self._regulation_id}",
            {"key": f"thermostats.{thermostat_id}.is_on", "value": is_on},
        )

    async def set_regulation_mode(self, mode: int) -> dict | None:
        """Set the global HVAC mode (uc_mode).

        Known values (to be confirmed):
            0 = stop/off
            1 = heat
            2 = cool
            3 = dehumidify
        """
        return await self.api_post(
            f"/regulations/{self._regulation_id}",
            {"key": "uc_mode", "value": mode},
        )

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self._session.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _ensure_authenticated(self) -> None:
        if not self._authenticated:
            await self.authenticate()

    def _get_xsrf_cookie_value(self) -> str | None:
        """Extract and URL-decode the XSRF-TOKEN cookie value."""
        for cookie in self._session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                return unquote(cookie.value)
        return None

    def _get_csrf_meta_token(self, html: str) -> str | None:
        """Extract the CSRF token from the <meta name='csrf-token'> tag."""
        soup = BeautifulSoup(html, "html.parser")
        meta = soup.find("meta", {"name": "csrf-token"})
        if meta:
            return meta.get("content")
        return None

    def _api_headers(self) -> dict[str, str]:
        """Build headers for /api-client requests."""
        headers: dict[str, str] = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }
        xsrf = self._get_xsrf_cookie_value()
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        if self._csrf_token:
            headers["X-CSRF-TOKEN"] = self._csrf_token
        return headers

    @staticmethod
    def _parse_regulation(html: str) -> RegulationData:
        """Extract the regulation JSON from the inline script tag."""
        match = _REGULATION_RE.search(html)
        if not match:
            # Fallback: try to find the JSON blob with a broader pattern
            alt = re.search(
                r"assets\.regulation\s*=\s*(\{.+?\});", html, re.DOTALL
            )
            if not alt:
                raise ParsingError(
                    "Could not find assets.regulation JSON in page"
                )
            raw_json = alt.group(1)
        else:
            raw_json = match.group(1)

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as err:
            raise ParsingError(f"Invalid JSON in assets.regulation: {err}") from err

        thermostats = []
        for th in data.get("thermostats", []):
            thermostats.append(
                ThermostatData(
                    thermostat_id=th["id"],
                    key=th["key"],
                    name=th.get("name", th["key"]).strip(),
                    current_temperature=th.get("temperature"),
                    setpoint_hot_t1=th.get("setpoint_hot_t1"),
                    setpoint_hot_t2=th.get("setpoint_hot_t2"),
                    setpoint_cool_t1=th.get("setpoint_cool_t1"),
                    setpoint_cool_t2=th.get("setpoint_cool_t2"),
                    t1_t2=th.get("t1_t2", 1),
                    zone=th.get("zone", 1),
                    is_on=th.get("is_on", True),
                    is_connected=th.get("is_connected", False),
                    is_battery_low=th.get("is_battery_low", False),
                    motor_state=th.get("motor_state", 0),
                    raw=th,
                )
            )

        return RegulationData(
            regulation_id=data["id"],
            uc_mode=data.get("uc_mode", 0),
            ui_on=data.get("ui_on", False),
            ui_sp=data.get("ui_sp", 20),
            is_connected=data.get("is_connected", False),
            uc_cool_mode=data.get("uc_cool_mode", False),
            uc_hot_min=data.get("uc_hot_min", 16),
            uc_hot_max=data.get("uc_hot_max", 30),
            uc_cold_min=data.get("uc_cold_min", 16),
            uc_cold_max=data.get("uc_cold_max", 30),
            thermostats=thermostats,
            raw=data,
        )
