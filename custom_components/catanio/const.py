"""Constants for the CatanIO integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "catanio"
MANUFACTURER: Final = "Phoenix Contact"

# Fixed link-local addresses of the Catan C1: its own I/O and the backend
# that discovers the extension modules on the local bus.
C1_IO_HOST: Final = "169.254.253.1"
C1_BACKEND_HOST: Final = "169.254.253.2"

SCAN_INTERVAL: Final = timedelta(seconds=5)
DISCOVERY_INTERVAL: Final = timedelta(minutes=15)
IDENTIFY_DURATION_S: Final = 30
