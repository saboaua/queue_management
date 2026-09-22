"""Constants for the Queue Management integration."""

DOMAIN = "queue_management"

# Storage
STORAGE_KEY = f"{DOMAIN}.queues"
STORAGE_VERSION = 1

# Default queue
DEFAULT_QUEUE_ID = "main"
DEFAULT_QUEUE_NAME = "Main Queue"

# Attributes / keys
ATTR_QUEUE_ID = "queue_id"
ATTR_TICKET = "ticket"
ATTR_NAME = "name"
ATTR_PREFIX = "prefix"
ATTR_START_NUMBER = "start_number"

# Events
EVENT_TICKET_ISSUED = f"{DOMAIN}_ticket_issued"
EVENT_TICKET_CALLED = f"{DOMAIN}_ticket_called"
EVENT_QUEUE_RESET = f"{DOMAIN}_queue_reset"

# Platforms
PLATFORMS = ["sensor", "button"]

# Services
SERVICE_TAKE_TICKET = "take_ticket"
SERVICE_CALL_NEXT = "call_next"
SERVICE_CALL_TICKET = "call_ticket"
SERVICE_RESET_QUEUE = "reset_queue"
SERVICE_CREATE_QUEUE = "create_queue"
SERVICE_DELETE_QUEUE = "delete_queue"
