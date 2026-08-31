"""
database_read.py: Read user-specific database for displays.

**Author:** Anna Ordog, for CanDIAPL
"""

import pandas as pd
import healpy as hp
import numpy as np
import psycopg2
from psycopg2 import extras
from datetime import timedelta, datetime
from dateutil.parser import parse
import csv
from rubin_sunrise.collector.utils import (
    simulation_dates, 
    get_base_mjd,
    date_to_nightnum,
)
from rubin_sunrise.collector.lsst import (
    get_camera, 
    get_visit_metadata,
    rsv_service,
    sim_service_range,
)
from rubin_sunrise.observability import daily_observability, get_az_el

import subprocess
from rubin_sunrise.config import (
    DB_NAME, SIM_HIST, SIM_START, QUERY_TYPE, SIM_LSST_DB, DAYS_FORECAST, OBS_FLAGS,
)

BANDS = ('u', 'g', 'r', 'i', 'z', 'y')
MASK_COLS = [f'{b}mask' for b in BANDS]
VISIT_COLS = [f'{b}visits' for b in BANDS]


def get_database():
    """Initialize user-specific database and load targets for tracking.
    
    Performs one-time setup of the Rubin Dashboard application by:
    - Reading the target list from a file using _read_csv_file()
    - Grouping targets spatially using _group_targets()
    - Establishing database connection
    - Loading target data if not already present using _setup_targets()
    - Loading LSST camera footprint information
    
    Parameters
    ----------
    user_id : int
        User ID for database queries and tracking.
    
    Returns
    -------
    conn : psycopg2.connection
        Open database connection for lifetime of process.
    cur : psycopg2.cursor (DictCursor)
        Database cursor for queries.
    
    Raises
    ------
    psycopg2.OperationalError
        If database connection fails.
    FileNotFoundError
        If input file cannot be found.
    
    Notes
    -----
    - Targets are grouped using HEALPix nside=16
    - If targets are already loaded for this user, loading is skipped
    - LSST Camera footprint is loaded from rubin_sim_data environment
    """

    # Open a connection to database
    conn = psycopg2.connect(dbname="lsst_database")

    # Use a DictCursor to safely specify columns later
    cur = conn.cursor(cursor_factory=extras.DictCursor)

    # This will need to be updated to check for flags:
    flags_present = False

    return conn, cur, flags_present