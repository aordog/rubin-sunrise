"""
config.py: Configuration parameters for the Rubin Dashboard.

Defines user inputs, server settings, simulation parameters, and stress
testing configuration. Constants are organized by category with inline
comments explaining their purpose.

**Author:** Anna Ordog, for CanDIAPL
"""

from datetime import datetime
from pathlib import Path
import astropy.units as u
from astropy import coordinates as coord

########### USER INPUTS #########
QUERY_FILE     = "moon_test.csv" # File with user-selected targets
INITIAL_OFFSET = 0.0               # declination limit to filter targets
OBS_FLAGS      = False            # Additional observability flags available
#################################

# Server-side info
PORT = 8000 # Server
DEFAULT_USER_ID: int  = 1  # User ID. TO DO: REVISIT WHEN ADDING USERS!
DB_NAME = "lsst_database"  # Name of user-specific database
#OUTPUT_BASE = Path("/home/aordog/Dropbox/candiapl/rubin-dash-out/")
OUTPUT_BASE = Path(__file__).parent.parent.parent
DAYS_FORECAST = 60 # Number of days for which to calculate observability
DT = 5.0/60.0 # Time increment for observability plots (hours)
LOC = coord.EarthLocation.of_site('LSST') # Rubin location for obs. plots

# Simulated LSST survey (for testing)
QUERY_TYPE = 'RSV' # Options: RSV, SIM
REFRESH_INTERVAL: int = 120 # refresh rate for simulated iterations
SIM_HIST  = datetime(2026, 6, 3) # simulated historical data (prior to query)
SIM_START = datetime(2026, 6, 4)  # simulated days start
SIM_END   = datetime(2026, 7, 20) # simulated days end
VERBOSE = False  # Show debug columns in table (gr_name, gr_num, mem_num)
SIM_LSST_DB = "baseline_v3.3_200day.db"

# Stress testing
MEM_TEST_MODE = False  # Turn on memory stress testing (simulated clicks)
STRESS_TEST_CLICK_INTERVAL = 3  # Seconds between automated clicks