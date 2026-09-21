# Felicity Solar ESS Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/xpoh697/FelicityESS?include_prereleases&style=flat-square)](https://github.com/xpoh697/FelicityESS/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<p align="center">
  <img src="custom_components/felicity_ess/brand/icon.png" width="160" alt="Felicity ESS Icon" />
</p>

Custom integration for [Home Assistant](https://www.home-assistant.io/) to monitor **Felicity Solar** battery storage systems (ESS) and hybrid inverters via cloud telemetry.

Developed via reverse-engineering of the official **Fsolar Android application** (`com.felicity.solar`).

---

## 🌟 Key Features

- 🔋 **Full Battery Telemetry**:
  - State of Charge (SOC %) and State of Health (SOH %)
  - Pack Voltage (V), Current (A), and Power (W)
  - Nominal / Remaining Capacity (Ah)
  - Energy charged today (kWh) and Energy discharged today (kWh)
- 🛡️ **BMS Protection Limits & Diagnostics**:
  - BMS Charge Current Limit (`bmslccurr`) & Discharge Current Limit (`bmsldcurr`) (A)
  - BMS Charge Voltage Limit & Discharge Voltage Limit (V)
  - Maximum & Minimum Cell Voltage (V) with Cell identification numbers
  - Maximum & Minimum Cell Temperature (°C) with Cell identification numbers
  - BMS Alarm and Trouble binary sensors
- 🔬 **Cell-Level Telemetry (16S / 4T)**:
  - Individual Cell Voltages 1 through 16 (V)
  - Individual Cell Temperatures 1 through 4 (°C)
  - *Note:* To keep your Home Assistant database compact, individual cell sensors are provided and can be enabled in 1-click in the device entity registry.
- ☀️ **Solar Plant Telemetry**:
  - Real-time Solar PV Generation (W)
  - Grid Feed-in Power (W)
  - Home Load Consumption (W)
  - Daily Solar Generation and Consumption counters (kWh)
- 🔒 **Secure Authentication**:
  - Client-side RSA 2048-bit PKCS1v15 password encryption matching the official app protocol.
  - Automatic session token refresh with concurrency locking.
- ⚙️ **Config Flow & Options**:
  - Intuitive UI setup: enter login/password and select your plant.
  - Configurable polling interval (15 to 300 seconds).

---

## 📦 Installation

### Option 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Click the three dots in the top right corner and select **Custom repositories**.
4. Add repository:
   - **Repository**: `https://github.com/xpoh697/FelicityESS`
   - **Type**: `Integration`
5. Click **Add**, then find **Felicity Solar ESS** and click **Download**.
6. Restart Home Assistant.

### Option 2: Manual Installation

1. Download the latest release `.zip` or clone this repository.
2. Copy the `custom_components/felicity_ess` directory into your Home Assistant `<config_dir>/custom_components/` directory.
3. Restart Home Assistant.

---

## 🚀 Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Felicity Solar ESS**.
3. Enter your **Fsolar** account credentials (email/username and password).
4. Select your solar plant installation.
5. Done! Your devices and battery sensors will appear immediately.

---

## 📋 Available Entities

| Entity | Category | Description | Unit |
| :--- | :--- | :--- | :--- |
| `sensor.felicity_battery_soc` | Battery | Battery State of Charge | `%` |
| `sensor.felicity_battery_soh` | Diagnostic | Battery Health | `%` |
| `sensor.felicity_battery_voltage` | Measurement | Battery Pack Voltage | `V` |
| `sensor.felicity_battery_current` | Measurement | Battery Pack Current | `A` |
| `sensor.felicity_battery_power` | Measurement | Battery Power (Charge/Discharge) | `W` |
| `sensor.felicity_battery_capacity` | Diagnostic | Battery Capacity | `Ah` |
| `sensor.felicity_battery_bms_charge_current_limit` | Diagnostic | BMS Max Allowed Charge Current | `A` |
| `sensor.felicity_battery_bms_discharge_current_limit` | Diagnostic | BMS Max Allowed Discharge Current | `A` |
| `sensor.felicity_battery_energy_charged_today` | Energy | Cumulative Daily Charged Energy | `kWh` |
| `sensor.felicity_battery_energy_discharged_today` | Energy | Cumulative Daily Discharged Energy | `kWh` |
| `sensor.felicity_battery_max_cell_voltage` | Diagnostic | Highest cell voltage in pack | `V` |
| `sensor.felicity_battery_min_cell_voltage` | Diagnostic | Lowest cell voltage in pack | `V` |
| `sensor.felicity_battery_cell_voltage_1..16` | Diagnostic | Individual cell voltages (disabled by default) | `V` |
| `sensor.felicity_battery_cell_temp_1..4` | Diagnostic | Individual temperature probes (disabled by default) | `°C` |
| `sensor.felicity_plant_solar_pv_power` | Power | Real-time solar production | `W` |
| `sensor.felicity_plant_home_load_power` | Power | Real-time household consumption | `W` |
| `binary_sensor.felicity_battery_online` | Connectivity | Battery communication status | `on/off` |
| `binary_sensor.felicity_battery_alarm` | Problem | BMS fault or warning indicator | `on/off` |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
