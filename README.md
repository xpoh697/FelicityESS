# Felicity Solar ESS Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/xpoh697/FelicityESS?include_prereleases&style=flat-square)](https://github.com/xpoh697/FelicityESS/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<p align="center">
  <img src="custom_components/felicity_ess/brand/icon.png" width="160" alt="Felicity ESS Icon" />
</p>

Custom integration for [Home Assistant](https://www.home-assistant.io/) to monitor **Felicity Solar** battery energy storage systems (ESS) and hybrid systems.

Supports two connection modes:
1. 🏠 **Direct Local Network (WiFi / LAN) — Recommended**: Communicates directly with the battery over your local network via plain TCP (port `53970`). **Zero cloud dependency**, no internet required, fast updates, 100% private and resilient.
2. ☁️ **Felicity Cloud (Fsolar REST API)**: Telemetry via the official cloud API with client-side RSA 2048-bit encryption for remote systems.

---

## 🌟 Key Features

### 🔌 Direct Local WiFi/LAN Mode
- **Zero Cloud**: Direct TCP stream to port `53970` on the battery's internal Wi-Fi controller.
- **Fast & Responsive**: Real-time polling every 5–15 seconds without rate limits or cloud downtime.
- **Verified Battery Profiles**:
  - `FLB48314TG1-H` (48V 16S, 2×2 temperature matrix)
  - `FLA24100` (24V 8S, `BtemList` temperature mapping)
  - `FLA48300` (48V 16S, cycle count `BmsCnt`)
  - `Generic Felicity Solar Battery` fallback for other models
- **Microcontroller Protection**: Serialized persistent TCP connection with `asyncio.Lock`, OS-level `SO_KEEPALIVE`, and buffer flushing to ensure stability on embedded ESP/lwIP chipsets.
- **Data Integrity**: Outlier/sentinel filtering (`65535`, `32767`, `-1`) and boot-snapshot rejection (avoids false 0V / 0% spikes).
- **Invert Current Option**: User-configurable current sign convention to match Home Assistant standards (negative = charging, positive = discharging).

### 🔋 Complete Telemetry
- State of Charge (SOC %) & State of Health (SOH %)
- Pack Voltage (V), Current (A), and Power (W)
- Operating State (`charging`, `discharging`, `standby`)
- Remaining Capacity (Ah) and Charge Cycle Count (`BmsCnt`)
- Maximum & Minimum Cell Voltage (V) with Cell Number identification
- Maximum & Minimum Cell Temperatures (°C)
- BMS Charge & Discharge Voltage / Current Limits
- 16 Individual Cell Voltages (V) *(disabled by default to protect Recorder database)*
- 4 Individual Cell Temperature probes (°C)
- Binary sensors for connectivity and BMS alarm/problem states

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

1. In Home Assistant, navigate to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Felicity Solar ESS**.
3. Choose your preferred connection mode:
   - **Direct Local Network (WiFi/LAN)**:
     - Enter the **IP address** of your Felicity battery in your home network.
     - Port defaults to `53970`.
     - Toggle current inversion if preferred.
   - **Felicity Solar Cloud**:
     - Enter your **Fsolar** account credentials (email, registered phone number, or username).
     - Select your solar plant installation.
4. Click **Submit**. Your battery sensors and diagnostics will appear immediately!

---

## 📋 Available Entities (Local Mode)

| Entity | Category | Description | Unit |
| :--- | :--- | :--- | :--- |
| `sensor.felicity_battery_voltage` | Measurement | Battery Pack Voltage | `V` |
| `sensor.felicity_battery_current` | Measurement | Battery Pack Current | `A` |
| `sensor.felicity_battery_power` | Measurement | Real-time Battery Power | `W` |
| `sensor.felicity_battery_charging_state` | State | Operation mode (`charging`, `discharging`, `standby`) | — |
| `sensor.felicity_battery_soc` | Battery | Battery State of Charge | `%` |
| `sensor.felicity_battery_soh` | Diagnostic | Battery State of Health | `%` |
| `sensor.felicity_battery_capacity` | Diagnostic | Usable Battery Capacity | `Ah` |
| `sensor.felicity_battery_cycle_count` | Diagnostic | Charge/discharge cycle counter | — |
| `sensor.felicity_battery_max_cell_voltage` | Diagnostic | Highest individual cell voltage | `V` |
| `sensor.felicity_battery_min_cell_voltage` | Diagnostic | Lowest individual cell voltage | `V` |
| `sensor.felicity_battery_max_cell_number` | Diagnostic | Cell index with maximum voltage | — |
| `sensor.felicity_battery_min_cell_number` | Diagnostic | Cell index with minimum voltage | — |
| `sensor.felicity_battery_max_cell_temperature` | Diagnostic | Highest cell temperature probe | `°C` |
| `sensor.felicity_battery_min_cell_temperature` | Diagnostic | Lowest cell temperature probe | `°C` |
| `sensor.felicity_battery_cell_1..16_voltage` | Diagnostic | Voltages for cells 1–16 (1-click enable in entity registry) | `V` |
| `sensor.felicity_battery_temperature_1..4` | Diagnostic | Cell temperature probes 1–4 | `°C` |
| `sensor.felicity_battery_charge_voltage_limit` | Diagnostic | BMS Max Allowed Charge Voltage | `V` |
| `sensor.felicity_battery_discharge_voltage_limit` | Diagnostic | BMS Min Allowed Discharge Voltage | `V` |
| `sensor.felicity_battery_charge_current_limit` | Diagnostic | BMS Max Allowed Charge Current | `A` |
| `sensor.felicity_battery_discharge_current_limit` | Diagnostic | BMS Max Allowed Discharge Current | `A` |
| `binary_sensor.felicity_battery_online` | Connectivity | Local TCP connection status | `on/off` |
| `binary_sensor.felicity_battery_alarm` | Problem | BMS fault / warning active | `on/off` |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
