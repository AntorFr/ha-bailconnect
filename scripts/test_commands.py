#!/usr/bin/env python3
"""Test script to validate BaillConnect API commands.

Tests write commands (setpoint, mode, on/off) against the live API.
Each command is followed by a read to verify the change took effect,
then the original value is restored.

Usage:
    python scripts/test_commands.py
"""

import asyncio
import sys
from pathlib import Path

import aiohttp
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "custom_components" / "bailconnect"))

from api import (
    AuthenticationError,
    BaillConnectApiClient,
    CannotConnect,
    RegulationData,
)

SECRETS_PATH = PROJECT_ROOT / "secrets.yaml"

# ANSI colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def load_credentials() -> tuple[str, str]:
    """Load email and password from secrets.yaml."""
    if not SECRETS_PATH.exists():
        print(f"ERROR: {SECRETS_PATH} not found.")
        sys.exit(1)
    with open(SECRETS_PATH) as f:
        data = yaml.safe_load(f)
    bc = data.get("bailconnect", {})
    return bc["email"], bc["password"]


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{RESET}")


def info(msg: str) -> None:
    print(f"  {YELLOW}→ {msg}{RESET}")


async def test_setpoint(
    client: BaillConnectApiClient, th_id: int, th_name: str
) -> bool:
    """Test changing a thermostat setpoint and restoring it."""
    print(f"\n--- Test: set_thermostat_setpoint (thermostat {th_id}: {th_name}) ---")

    # Read current state
    reg = await client.get_regulation()
    th = next(t for t in reg.thermostats if t.thermostat_id == th_id)
    original = th.setpoint_hot_t1
    test_value = original + 0.5 if original < 29 else original - 0.5

    info(f"Current setpoint_hot_t1 = {original}°C")
    info(f"Setting to {test_value}°C...")

    # Send command
    result = await client.set_thermostat_setpoint(th_id, "setpoint_hot_t1", test_value)
    print(f"  API response: {result}")

    # Wait a moment then re-read
    await asyncio.sleep(2)
    reg2 = await client.get_regulation()
    th2 = next(t for t in reg2.thermostats if t.thermostat_id == th_id)
    new_value = th2.setpoint_hot_t1

    if new_value == test_value:
        ok(f"Setpoint changed to {new_value}°C")
    else:
        fail(f"Expected {test_value}°C, got {new_value}°C")

    # Restore original value
    info(f"Restoring to {original}°C...")
    await client.set_thermostat_setpoint(th_id, "setpoint_hot_t1", original)
    await asyncio.sleep(2)

    reg3 = await client.get_regulation()
    th3 = next(t for t in reg3.thermostats if t.thermostat_id == th_id)
    if th3.setpoint_hot_t1 == original:
        ok(f"Restored to {original}°C")
    else:
        fail(f"Restore failed: got {th3.setpoint_hot_t1}°C")

    return new_value == test_value


async def test_thermostat_on_off(
    client: BaillConnectApiClient, th_id: int, th_name: str
) -> bool:
    """Test toggling a thermostat on/off and restoring it."""
    print(f"\n--- Test: set_thermostat_on/off (thermostat {th_id}: {th_name}) ---")

    reg = await client.get_regulation()
    th = next(t for t in reg.thermostats if t.thermostat_id == th_id)
    original = th.is_on
    target = not original

    info(f"Current is_on = {original}")
    info(f"Setting to {target}...")

    result = await client.set_thermostat_on(th_id, target)
    print(f"  API response: {result}")

    await asyncio.sleep(2)
    reg2 = await client.get_regulation()
    th2 = next(t for t in reg2.thermostats if t.thermostat_id == th_id)

    if th2.is_on == target:
        ok(f"is_on changed to {th2.is_on}")
    else:
        fail(f"Expected {target}, got {th2.is_on}")

    # Restore
    info(f"Restoring to {original}...")
    await client.set_thermostat_on(th_id, original)
    await asyncio.sleep(2)

    reg3 = await client.get_regulation()
    th3 = next(t for t in reg3.thermostats if t.thermostat_id == th_id)
    if th3.is_on == original:
        ok(f"Restored to {original}")
    else:
        fail(f"Restore failed: got {th3.is_on}")

    return th2.is_on == target


async def test_regulation_mode(client: BaillConnectApiClient) -> bool:
    """Test changing the global HVAC mode and restoring it."""
    print("\n--- Test: set_regulation_mode ---")

    reg = await client.get_regulation()
    original = reg.uc_mode
    # Pick a different mode to test
    test_mode = 2 if original != 2 else 1
    mode_names = {0: "off", 1: "heat", 2: "cool", 3: "dry"}

    info(f"Current uc_mode = {original} ({mode_names.get(original, '?')})")
    info(f"Setting to {test_mode} ({mode_names.get(test_mode, '?')})...")

    result = await client.set_regulation_mode(test_mode)
    print(f"  API response: {result}")

    await asyncio.sleep(2)
    reg2 = await client.get_regulation()

    if reg2.uc_mode == test_mode:
        ok(f"uc_mode changed to {reg2.uc_mode} ({mode_names.get(reg2.uc_mode, '?')})")
    else:
        fail(f"Expected {test_mode}, got {reg2.uc_mode}")

    # Restore
    info(f"Restoring to {original} ({mode_names.get(original, '?')})...")
    await client.set_regulation_mode(original)
    await asyncio.sleep(2)

    reg3 = await client.get_regulation()
    if reg3.uc_mode == original:
        ok(f"Restored to {original}")
    else:
        fail(f"Restore failed: got {reg3.uc_mode}")

    return reg2.uc_mode == test_mode


async def main() -> None:
    """Run all command tests."""
    email, password = load_credentials()
    print(f"Authenticating as: {email}")

    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        client = BaillConnectApiClient(session, email, password)

        try:
            await client.authenticate()
            ok(f"Login successful (regulation_id={client.regulation_id})")
        except (AuthenticationError, CannotConnect) as err:
            fail(f"Login failed: {err}")
            sys.exit(1)

        # Read initial state
        reg = await client.get_regulation()
        th = reg.thermostats[0]

        print(f"\nUsing thermostat [{th.key}] {th.name} (id={th.thermostat_id}) for tests")
        print("Each test will modify a value, verify, then restore the original.\n")

        if "--yes" not in sys.argv:
            try:
                confirm = input("Proceed with live tests? [y/N] ").strip().lower()
                if confirm != "y":
                    print("Aborted.")
                    sys.exit(0)
            except EOFError:
                print("Non-interactive mode. Use --yes to skip confirmation.")
                sys.exit(1)

        results = {}

        # Test 1: Setpoint change
        results["setpoint"] = await test_setpoint(
            client, th.thermostat_id, th.name
        )

        # Test 2: Thermostat on/off
        results["on_off"] = await test_thermostat_on_off(
            client, th.thermostat_id, th.name
        )

        # Test 3: Regulation mode
        results["mode"] = await test_regulation_mode(client)

        # Summary
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        all_passed = True
        for name, passed in results.items():
            status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
            print(f"  {name}: {status}")
            if not passed:
                all_passed = False

        if all_passed:
            print(f"\n{GREEN}All tests passed!{RESET}")
        else:
            print(f"\n{RED}Some tests failed.{RESET}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
