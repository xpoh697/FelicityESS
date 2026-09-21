"""Constants for the Felicity Solar ESS integration."""
from homeassistant.const import Platform

DOMAIN = "felicity_ess"

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PLANT_ID = "plant_id"
CONF_PLANT_NAME = "plant_name"
CONF_SCAN_INTERVAL = "scan_interval"

# Default intervals
DEFAULT_SCAN_INTERVAL = 30  # seconds
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 300
TOPOLOGY_UPDATE_INTERVAL_CYCLES = 60  # update device inventory every ~30 mins

# API Endpoints
API_BASE_URL = "https://shine-api.felicitysolar.com"
API_PATH_LOGIN = "/app/base/userlogin"
API_PATH_LIST_PLANT = "/app/plant/list_plant"
API_PATH_LIST_DEVICE = "/app/device/list_device"
API_PATH_PLANT_DETAILS_BATTERY = "/app/plant/plantDetails_Battery"
API_PATH_STORAGE_REALTIME = "/app/storageRealtimeData/pv_power_storage_realtimeData"

# App Identity
SOURCE_ANDROID = "ANDROID"
APP_VERSION = "4.0.9"

# RSA Public Key for password encryption (2048-bit DER X.509 in Base64)
RSA_PUBLIC_KEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9FZugJXC6bBSluTW6mJttOLOal"
    "jrdErVnM5DNN+YFzpB9pAysTErjY1bnSVuEwQSwptnqUji7Ch2qMj2n+0eCp8p6vtSh7/tFr2ul8nDRtkoswLAN"
    "AIwtUk/G85ipMpmY1W642LImnEJmGkkddlbjbjxJTZWR5hc/d9cPWb+AR77LxFFrMik3c+44v1kQlIPFP6EjIbO"
    "vt/Lv7fHWD9JI/YzN4y1gK7C/VQdNGuikQyNg+5W3rg9ecYf9I5uLAQwY/hxeI3lbNsErebqKe2EbJ8AwcNIC0l"
    "DBz53Sq0ML89QapEuy3fB+upuctxLULVDCbNwIDAQAB"
)

# Device Types from Fsolar protocol
DEVICE_TYPE_BATTERY = "BP"
DEVICE_TYPE_HYBRID = "HY"
DEVICE_TYPE_INVERTER = "IV"

MANUFACTURER = "Felicity Solar"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]
