#!/usr/bin/env python3
"""Probe script to discover the correct API payload format for BaillConnect.

Tries multiple payload formats and endpoints to find which one
actually changes the thermostat setpoint.
"""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import unquote

import aiohttp
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = PROJECT_ROOT / "secrets.yaml"

sys.path.insert(0, str(PROJECT_ROOT / "custom_components" / "bailconnect"))
from api import BaillConnectApiClient


def load_credentials() -> tuple[str, str]:
    with open(SECRETS_PATH) as f:
        data = yaml.safe_load(f)
    bc = data["bailconnect"]
    return bc["email"], bc["password"]


async def try_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    payload: dict,
    label: str,
    csrf_token: str | None = None,
) -> None:
    """Send a request and print the result."""
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    # Add XSRF token from cookie
    for cookie in session.cookie_jar:
        if cookie.key == "XSRF-TOKEN":
            headers["X-XSRF-TOKEN"] = unquote(cookie.value)
    if csrf_token:
        headers["X-CSRF-TOKEN"] = csrf_token

    print(f"\n--- {label} ---")
    print(f"  {method} {url}")
    print(f"  Payload: {json.dumps(payload)}")

    try:
        async with session.request(
            method, url, json=payload, headers=headers, allow_redirects=True
        ) as resp:
            status = resp.status
            body = await resp.text()
            print(f"  Status: {status}")
            if len(body) > 500:
                # Check if the setpoint changed in the response
                try:
                    data = json.loads(body)
                    # Look for our thermostat's setpoint in response
                    if "data" in data:
                        ths = data["data"].get("thermostats", [])
                    elif "thermostats" in data:
                        ths = data.get("thermostats", [])
                    else:
                        ths = []
                    for th in ths:
                        if th.get("id") == 6513:
                            print(f"  → th1 setpoint_hot_t1 = {th.get('setpoint_hot_t1')}")
                            break
                except json.JSONDecodeError:
                    print(f"  Body (first 200): {body[:200]}")
            else:
                print(f"  Body: {body}")
    except Exception as err:
        print(f"  Error: {err}")


async def main() -> None:
    email, password = load_credentials()
    base = "https://www.baillconnect.com"

    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        # Authenticate
        client = BaillConnectApiClient(session, email, password)
        await client.authenticate()
        print(f"Logged in (regulation_id={client.regulation_id})")

        # Get CSRF token from the dashboard page
        html = await client.fetch_page()
        import re
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        meta = soup.find("meta", {"name": "csrf-token"})
        csrf = meta["content"] if meta else None
        print(f"CSRF token: {csrf[:20]}..." if csrf else "No CSRF token found")

        reg_id = client.regulation_id
        th_id = 6513  # Chambre invitée
        test_value = 22.5

        # Format 1: Current format (key/value)
        await try_request(
            session, "POST",
            f"{base}/api-client/regulations/{reg_id}",
            {"key": f"thermostats.{th_id}.setpoint_hot_t1", "value": test_value},
            "Format 1: POST {key, value}",
            csrf,
        )

        # Format 2: Flat key as property name
        await try_request(
            session, "POST",
            f"{base}/api-client/regulations/{reg_id}",
            {f"thermostats.{th_id}.setpoint_hot_t1": test_value},
            "Format 2: POST flat key",
            csrf,
        )

        # Format 3: PUT instead of POST
        await try_request(
            session, "PUT",
            f"{base}/api-client/regulations/{reg_id}",
            {"key": f"thermostats.{th_id}.setpoint_hot_t1", "value": test_value},
            "Format 3: PUT {key, value}",
            csrf,
        )

        # Format 4: PATCH
        await try_request(
            session, "PATCH",
            f"{base}/api-client/regulations/{reg_id}",
            {"key": f"thermostats.{th_id}.setpoint_hot_t1", "value": test_value},
            "Format 4: PATCH {key, value}",
            csrf,
        )

        # Format 5: Per-thermostat endpoint
        await try_request(
            session, "POST",
            f"{base}/api-client/thermostats/{th_id}",
            {"setpoint_hot_t1": test_value},
            "Format 5: POST /thermostats/{id} direct",
            csrf,
        )

        # Format 6: Per-thermostat endpoint with PUT
        await try_request(
            session, "PUT",
            f"{base}/api-client/thermostats/{th_id}",
            {"setpoint_hot_t1": test_value},
            "Format 6: PUT /thermostats/{id} direct",
            csrf,
        )

        # Format 7: Nested under regulation with thermostat sub-path
        await try_request(
            session, "POST",
            f"{base}/api-client/regulations/{reg_id}/thermostats/{th_id}",
            {"setpoint_hot_t1": test_value},
            "Format 7: POST /regulations/{id}/thermostats/{id}",
            csrf,
        )

        # Format 8: form-encoded instead of JSON
        print(f"\n--- Format 8: POST form-encoded ---")
        print(f"  POST {base}/api-client/regulations/{reg_id}")
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }
        for cookie in session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                headers["X-XSRF-TOKEN"] = unquote(cookie.value)
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf
        async with session.post(
            f"{base}/api-client/regulations/{reg_id}",
            data={"key": f"thermostats.{th_id}.setpoint_hot_t1", "value": str(test_value)},
            headers=headers,
            allow_redirects=True,
        ) as resp:
            body = await resp.text()
            print(f"  Status: {resp.status}")
            try:
                data = json.loads(body)
                ths = data.get("data", {}).get("thermostats", [])
                for th in ths:
                    if th.get("id") == 6513:
                        print(f"  → th1 setpoint_hot_t1 = {th.get('setpoint_hot_t1')}")
            except:
                print(f"  Body (first 200): {body[:200]}")

        # Restore: read final state
        print("\n\n=== FINAL STATE CHECK ===")
        reg = await client.get_regulation()
        for th in reg.thermostats:
            if th.thermostat_id == 6513:
                print(f"  th1 setpoint_hot_t1 = {th.setpoint_hot_t1}")
                if th.setpoint_hot_t1 != 22:
                    print("  ⚠ Value was changed! Restoring to 22...")
                    # Try all successful formats to restore
                    await client.set_thermostat_setpoint(6513, "setpoint_hot_t1", 22)


if __name__ == "__main__":
    asyncio.run(main())
