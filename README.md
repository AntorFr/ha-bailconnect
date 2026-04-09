# BaillConnect for Home Assistant

A custom Home Assistant integration to control your [BaillConnect](https://www.baillconnect.com) HVAC zoning system.

BaillConnect by Baillindustrie is a connected zoning system compatible with major HVAC brands (Daikin, Fujitsu, Mitsubishi Electric, Panasonic, Samsung, Toshiba, Carrier, LG, and more).

## Features

- **Per-room temperature monitoring** — current temperature from each thermostat
- **Per-room setpoint control** — adjust target temperature per thermostat
- **HVAC mode control** — Heat, Cool, Dry (dehumidification), Off
- **Comfort / Eco support** — respects T1 (comfort) and T2 (eco) setpoints
- **Per-thermostat on/off** — turn individual thermostats on or off
- **Auto-refresh** — polls BaillConnect every 60 seconds

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** > **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for **BaillConnect** and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/bailconnect/` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **BaillConnect**
3. Enter your BaillConnect account email and password
4. Your thermostats will appear as climate entities

No YAML configuration is needed. Credentials are stored securely in the Home Assistant config entry.

## Entities

Each thermostat in your BaillConnect system becomes a **Climate** entity with:

| Attribute | Description |
|---|---|
| Current temperature | Room temperature reported by the thermostat |
| Target temperature | Active setpoint (hot or cold, comfort or eco) |
| HVAC mode | Off / Heat / Cool / Dry |
| Min/Max temp | Dynamic bounds based on current mode (16-30°C) |

## Development

A standalone test script is included for development and debugging:

```bash
# Create a virtual environment
python3 -m venv venv
source venv/bin/activate
pip install aiohttp beautifulsoup4 pyyaml

# Configure credentials
cp secrets.yaml.example secrets.yaml
# Edit secrets.yaml with your BaillConnect credentials

# Run the test script
python scripts/test_login.py
```

The test script authenticates against BaillConnect and prints the full regulation data (thermostats, zones, modes, temperatures).

## How it works

BaillConnect does not expose a public API. This integration:

1. Authenticates via the web login form (handling Laravel CSRF tokens)
2. Extracts regulation data from the inline JSON blob on the dashboard page
3. Sends commands via the internal `/api-client` endpoints

## License

MIT
