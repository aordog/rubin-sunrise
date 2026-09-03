"""
pipeline.py: Data-processing pipeline for rubin-sunrise.

This module manages the background data loop that periodically updates the
user-specific database and provides a frontend-agnostic API.

The module runs in a daemon thread...

Public API
----------
- ``data_loop`` - Background driver iterating simulated dates

**Author:** Anna Ordog, for CanDIAPL
"""

from __future__ import annotations

import ctypes
import ctypes.util
import gc
import time
from typing import TYPE_CHECKING
from astropy.time import Time
from datetime import timedelta

from rubin_sunrise.config import (
    REFRESH_INTERVAL, 
    SIM_START, 
    SIM_END,
    SIM_LSST_DB,
    QUERY_TYPE,
    DAYS_FORECAST,
)
from rubin_sunrise.collector.utils import (
    simulation_dates, 
    get_base_mjd,
    date_to_nightnum,
)
from rubin_sunrise.collector.database import (
    populate_database, 
    populate_forecast,
)

from rubin_sunrise.collector.lsst import (
    rsv_service, 
    sim_service,
)

from rubin_sunrise.monitoring import (
    log_table_size,
    monitoring_plots_collector,
)

print(f"DEBUG: Using pipeline from {__file__}")

# C-level memory reclamation (glibc-specific; unavailable on macOS/Windows):
_libc = None
_has_malloc_trim = False
try:
    _libc = ctypes.CDLL(ctypes.util.find_library("c"))
    # malloc_trim only exists in glibc; probe before relying on it.
    _libc.malloc_trim
    _has_malloc_trim = True
except (OSError, AttributeError):
    _has_malloc_trim = False

def _reclaim_memory() -> None:
    """Force garbage collection and return memory to the OS.

    This function triggers garbage collection and, where available calls 
    ``malloc_trim(0)`` to return freed memory pages to the OS. On platforms 
    without ``malloc_trim`` (e.g. macOS), only ``gc.collect()`` runs.
    """
    gc.collect()
    if _has_malloc_trim:
        _libc.malloc_trim(0)


# The main data loop:
def data_loop(
    conn,
    cur,
    camera,
    user_id: int,
    flags_present: bool = False,
    log_dir=None,
    timestamp=None,
) -> None:
    """Iterate over simulated dates, updating database and state.

    This function drives the background data pipeline. It runs in a daemon 
    thread, cycling through simulated dates. In the final version, this will
    be replaced with a loop through actual dates in real time. For each cycle:

    1. Queries the Rubin Schedule Viewer (RSV) service for visits data
    2. Updates PostgreSQL database with new visits data for the user's targets
    3. Repeats after REFRESH_INTERVAL seconds (will eventually be real days)

    Parameters
    ----------  
    conn : psycopg2.extensions.connection
        PostgreSQL database connection for reading/writing data.
    cur : psycopg2.extensions.cursor
        Database cursor object for query execution.
    camera : Camera
        Camera footprint metadata object for the observing instrument.
    user_id : int
        User identifier for filtering database queries (not relevant yet).
  
    Notes
    -----
    This function is designed to run as a daemon thread. The REFRESH_INTERVAL 
    is read from config.py and sets the duration between cycles. Memory is 
    explicitly reclaimed after each cycle via _reclaim_memory().
    """

    if QUERY_TYPE == 'SIM':
        base_mjd = get_base_mjd(SIM_LSST_DB)
        print(f"Querying simulated LSST data base: {SIM_LSST_DB}")
    if QUERY_TYPE == 'RSV':
        print(f"Querying Rubin Schedule Viewer")
    print('=====================================================')

    cycle_number = 0
    for date in simulation_dates(SIM_START, SIM_END):
        cycle_number += 1

        # Reading in data with simulated database option 
        if QUERY_TYPE == 'SIM':
            nightnum = date_to_nightnum(date, base_mjd)
            print(f"[CYCLE START #{cycle_number}] {date}, night #{nightnum}")
            visits = sim_service(nightnum)

        # Reading in data with RSV option    
        if QUERY_TYPE == 'RSV':
            print(f"[CYCLE START #{cycle_number}] {date}")
            visits = rsv_service(date)

        if visits.empty:
            print(f"DATA MISSING for {date}")
        else:     
            populate_database(
                    conn, cur, camera, user_id, visits, date, 
                    shared_state=None
                )
            populate_forecast(conn, cur, user_id, 
                              str(Time(date)+timedelta(days=DAYS_FORECAST)), 
                              shared_state=None)
            gc.collect()

            print("============================")
            print(f"Updated data for {date}")
            print("============================")

        if log_dir is not None and timestamp is not None:
            log_table_size(cur, str(log_dir / f"table_size_{timestamp}.csv"))
            monitoring_plots_collector(log_dir, timestamp)
        _reclaim_memory()
        time.sleep(REFRESH_INTERVAL)
        print(f"[CYCLE END #{cycle_number}]")