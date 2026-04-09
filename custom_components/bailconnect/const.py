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

# BaillConnect uc_mode integer values → HA HVACMode strings
# uc_mode=0 observed with ui_on=False (system off)
# uc_mode=1 observed with heat mode
UC_MODE_TO_HVAC: dict[int, str] = {
    0: "off",
    1: "heat",
    2: "cool",
    3: "dry",  # dehumidification
}

HVAC_TO_UC_MODE: dict[str, int] = {v: k for k, v in UC_MODE_TO_HVAC.items()}
