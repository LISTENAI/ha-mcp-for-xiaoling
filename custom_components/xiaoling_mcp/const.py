"""Constants for the Xiaoling MCP integration."""

DOMAIN = "xiaoling_mcp"
INTEGRATION_VERSION = "0.2.0"

CONF_DEVICES = "devices"
CONF_PAIRING_CODE = "pairing_code"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_API_TOKEN = "api_token"
CONF_BINDING_ID = "binding_id"
CONF_CONNECTOR_ID = "connector_id"
CONF_PRODUCT_ID = "product_id"
CONF_MANIFEST_VERSION = "manifest_version"

XIAOLING_API_BASE = "https://staging-api.listenai.com"
EXCHANGE_PATH = "/external/mcp/auth/exchange"
CONNECTOR_WS_PATH = "/v1/mcp/connector"

PROTOCOL_VERSION = 1
CONNECTOR_TYPE = "home_assistant"
USER_AGENT = f"Xiaoling-HA/{INTEGRATION_VERSION} (Home Assistant)"
SERVER_NAME = "Home Assistant"
MAX_RECONNECT_DELAY = 30
HELLO_TIMEOUT = 15
DEFAULT_HEARTBEAT_SECONDS = 30
DEFAULT_MAX_FRAME_SIZE = 655360
DEFAULT_CALL_TIMEOUT = 30

MANUFACTURER = "Xiaoling"
MODEL = "MCP device"
