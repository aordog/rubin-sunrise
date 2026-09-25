"""
config.py: Configuration parameters for the Rubin Dashboard.

Defines user inputs, server settings, simulation parameters, and stress
testing configuration. Constants are organized by category.

**Author:** Anna Ordog, for CanDIAPL
"""

from datetime import datetime
from pathlib import Path
import astropy.units as u
from astropy import coordinates as coord

########### USER INPUTS #########
QUERY_FILE     = "small_query.txt" # File with user-selected targets
INITIAL_OFFSET = 0.0               # declination limit to filter targets
OBS_FLAGS      = False            # Additional observability flags available
#################################

# Server-side info
PORT = 8000 # Server
DEFAULT_USER_ID: int  = 1  # User ID. TO DO: REVISIT WHEN ADDING USERS!
DB_NAME = "lsst_database"  # Name of user-specific database
CLOCK_DB_NAME = "rubin_clock"  # Name of shared clock database (independent of user DBs)
OUTPUT_BASE = Path(__file__).parent.parent.parent

# PostgreSQL connection settings
PG_HOST = "localhost"  # PostgreSQL server hostname (default: localhost for local development)
PG_PORT = 5432  # PostgreSQL server port (default: 5432)

# Optional custom storage location for databases (tablespace)
# Set PG_TABLESPACE_PATH to a valid directory path to store databases there instead of default location.
# Requires PostgreSQL superuser privileges to create tablespace.
# Example: PG_TABLESPACE_PATH = "/var/lib/postgresql/custom_tablespace"
# Leave as None to use PostgreSQL default data directory.
PG_TABLESPACE_PATH = "/var/lib/postgresql/custom_storage"  # Custom tablespace directory (optional)
PG_TABLESPACE_NAME = "rubin_tablespace"  # Name for custom tablespace (only used if PG_TABLESPACE_PATH is set)

DAYS_FORECAST = 20 # Number of days for which to calculate observability
DT = 5.0/60.0 # Time increment for observability plots (hours)
LOC = coord.EarthLocation.of_site('LSST') # Rubin location for obs. plots

# Simulated LSST survey (for testing)
QUERY_TYPE = 'RSV' # Options: RSV, SIM, Local
REFRESH_INTERVAL: int = 30 # refresh rate for simulated iterations
SIM_HIST  = datetime(2026, 6, 3) # simulated historical data (prior to query)
SIM_START = datetime(2026, 6, 4)  # simulated days start
SIM_END   = datetime(2026, 7, 20) # simulated days end
VERBOSE = False  # Show debug columns in table (gr_name, gr_num, mem_num)
SIM_LSST_DB = "baseline_v3.3_200day.db"
SIM_SPEEDUP_FACTOR: float = 720.0  # speedup multiplier: 1 real second = 720 simulated seconds
                                    # (2 real minutes = 1 simulated day)

# Stress testing
MEM_TEST_MODE = False  # Turn on memory stress testing (simulated clicks)
STRESS_TEST_CLICK_INTERVAL = 3  # Seconds between automated clicks
