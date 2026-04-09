#!/usr/bin/env python3
"""Test script to validate BaillConnect login and inspect regulation data.

Usage:
    1. Copy secrets.yaml.example to secrets.yaml and fill in your credentials.
    2. Run: python scripts/test_login.py
"""

import asyncio
import sys
from pathlib import Path

import aiohttp
import yaml

# Import api.py directly to avoid triggering __init__.py (which needs HA)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "custom_components" / "bailconnect"))

from api import (
    AuthenticationError,
    BaillConnectApiClient,
    CannotConnect,
    RegulationData,
    ThermostatData,
)

SECRETS_PATH = PROJECT_ROOT / "secrets.yaml"


def load_credentials() -> tuple[str, str]:
    """Load email and password from secrets.yaml."""
    if not SECRETS_PATH.exists():
        print(f"ERROR: {SECRETS_PATH} not found.")
        print("Copy secrets.yaml.example to secrets.yaml and fill in your credentials.")
        sys.exit(1)

    with open(SECRETS_PATH) as f:
        data = yaml.safe_load(f)

    bc = data.get("bailconnect", {})
    email = bc.get("email", "")
    password = bc.get("password", "")

    if not email or not password or "example" in email:
        print("ERROR: Please fill in real credentials in secrets.yaml")
        sys.exit(1)

    return email, password


def print_regulation(reg: RegulationData) -> None:
    """Pretty-print the regulation data."""
    print("\n" + "=" * 60)
    print("REGULATION DATA")
    print("=" * 60)
    print(f"  ID:            {reg.regulation_id}")
    print(f"  uc_mode:       {reg.uc_mode}")
    print(f"  ui_on:         {reg.ui_on}")
    print(f"  ui_sp:         {reg.ui_sp}°C")
    print(f"  is_connected:  {reg.is_connected}")
    print(f"  uc_cool_mode:  {reg.uc_cool_mode}")
    print(f"  Temp range:    hot={reg.uc_hot_min}-{reg.uc_hot_max}°C, "
          f"cold={reg.uc_cold_min}-{reg.uc_cold_max}°C")

    print(f"\nTHERMOSTATS ({len(reg.thermostats)}):")
    print("-" * 60)
    for th in reg.thermostats:
        print(f"  [{th.key}] {th.name}")
        print(f"    ID:          {th.thermostat_id}")
        print(f"    Temperature: {th.current_temperature}°C")
        print(f"    Setpoints:   hot T1={th.setpoint_hot_t1} T2={th.setpoint_hot_t2}, "
              f"cold T1={th.setpoint_cool_t1} T2={th.setpoint_cool_t2}")
        print(f"    T1/T2 mode:  {th.t1_t2} ({'comfort' if th.t1_t2 == 1 else 'eco'})")
        print(f"    Zone:        {th.zone}")
        print(f"    is_on:       {th.is_on}")
        print(f"    Connected:   {th.is_connected}")
        print(f"    Battery low: {th.is_battery_low}")
        print(f"    Motor state: {th.motor_state}")
        print()

    # Print raw zone data from the regulation
    zones = reg.raw.get("zones", [])
    print(f"ZONES ({len(zones)}):")
    print("-" * 60)
    for z in zones:
        print(f"  [{z['key']}] {z['name']} — mode={z['mode']}, id={z['id']}")

    print("\n" + "=" * 60)
    print("RAW JSON KEYS:", list(reg.raw.keys()))
    print("=" * 60)


async def main() -> None:
    """Run the login test and data inspection."""
    email, password = load_credentials()
    print(f"Authenticating as: {email}")

    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        client = BaillConnectApiClient(session, email, password)

        try:
            await client.authenticate()
            print(f"Login SUCCESSFUL! (regulation_id={client.regulation_id})")
        except AuthenticationError as err:
            print(f"Login FAILED: {err}")
            sys.exit(1)
        except CannotConnect as err:
            print(f"Connection FAILED: {err}")
            sys.exit(1)

        # Fetch and parse regulation data
        print("\nFetching regulation data...")
        reg = await client.get_regulation()
        print_regulation(reg)


if __name__ == "__main__":
    asyncio.run(main())
