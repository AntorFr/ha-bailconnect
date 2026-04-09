"""Constants for the BaillConnect integration."""

from datetime import timedelta

DOMAIN = "bailconnect"
BASE_URL = "https://www.baillconnect.com"
LOGIN_URL = "/client/connexion"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

CONF_SCAN_INTERVAL = "scan_interval"

# Temperature bounds (Celsius) — matches uc_hot_min/max and uc_cold_min/max
MIN_TEMP = 16
MAX_TEMP = 30
TEMP_STEP = 0.5

# BaillConnect uc_mode integer values → HA mode strings
# Confirmed from client.min.js: value:1=snowflake(cool), value:2=flame(heat)
UC_MODE_TO_HVAC: dict[int, str] = {
    0: "off",
    1: "cool",
    2: "heat",
    3: "dry",
    4: "fan",
}

HVAC_TO_UC_MODE: dict[str, int] = {v: k for k, v in UC_MODE_TO_HVAC.items()}

# uc_mode value for cool mode (used to pick cool vs hot setpoints)
UC_MODE_COOL = 1
