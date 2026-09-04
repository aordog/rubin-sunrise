"""Collector subsystem entry point.

Runs the data collection pipeline indefinitely, populating the database
with observation data from the LSST simulator or RSV.

Entry point: `python -m rubin_sunrise.collector.collector_main`

**Author:** Anna Ordog
"""

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

from rubin_sunrise.config import (
    DEFAULT_USER_ID,
    INITIAL_OFFSET,
    MEM_TEST_MODE,
    OUTPUT_BASE,
    QUERY_FILE,
    DB_NAME,
)
 
from rubin_sunrise.collector.database import (
    initialize_tracking, 
    set_up_db, 
    populate_history, 
    initialize_forecast,
)
from rubin_sunrise.collector.pipeline import data_loop

from rubin_sunrise.monitoring import (
    monitor_resources, 
    QuietFilter,
    Logger)

# Resolve project root (…/src/rubin_sunrise/__main__.py  →  …/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_collector(db_name: str | None = None, query_file: str | None = None) -> None:
    """Initialize and run the Rubin Dashboard application.

    Orchestrates the complete startup sequence for the dashboard:

    1. Sets up logging and output directory with timestamped files
    2. Initializes PostgreSQL database
    3. Loads user's target catalog and camera footprint
    4. Populates database with historical observation data
    5. Initializes daily observability forecast data
    6. Spawns background threads:
       - data_loop: periodic database updates with observation data
       - monitor_resources: CPU and memory profiling (writes CSV)
       - stress_test: automated interaction testing if MEM_TEST_MODE
         enabled
    7. On shutdown: saves monitoring plots and closes log file

    The dashboard runs as a multi-threaded application:
    - Background threads: data pipeline, resource monitoring, and
      optional stress testing

    Log output is simultaneously written to terminal and timestamped
    log file via Logger multi-destination handler.

    Parameters
    ----------
    db_name : str | None
        Database name. If None, uses default from config.
    query_file : str | None
        Query file path with target coordinates. If None, uses default from config.

    Configuration Parameters
    --------
    All parameters read from rubin_sunrise.config:
    - DEFAULT_USER_ID: Database user identifier
    - INITIAL_OFFSET: Declination limit for target filtering
    - QUERY_FILE: Path to target catalog
    - MEM_TEST_MODE: Enable/disable automated stress testing

    Raises
    ------
    Exception


    Notes
    -----
    Keyboard interrupt (Ctrl+C) triggers shutdown sequence.
    """
    # Use provided db_name or fall back to config default
    if db_name is None:
        db_name = DB_NAME
    
    # Use provided query_file or fall back to config default
    if query_file is None:
        query_file = QUERY_FILE

    # ── Output / logging ────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    run_dir = OUTPUT_BASE / 'logs' / 'data_logs' / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    log_file = open(run_dir / f"log_{timestamp}.txt", "w")
    sys.stdout = Logger(sys.stdout, log_file)
    sys.stderr = Logger(sys.stderr, log_file)

    # ── Database ────────────────────────────────────────────────
    set_up_db(db_name=db_name)
    logging.getLogger("werkzeug").addFilter(QuietFilter())

    camera, conn, cur, flags_present = initialize_tracking(
        DEFAULT_USER_ID, query_file, INITIAL_OFFSET, db_name=db_name
    )

    # ── Populate database with historical data ──────────────────
    populate_history(conn, cur, camera, DEFAULT_USER_ID)

    # ── Populate database with observabillity data ──────────────
    initialize_forecast(conn, cur, DEFAULT_USER_ID)

    # ── Background threads ──────────────────────────────────────
    stop_monitor = threading.Event()
    monitor_thread = threading.Thread(
        target=monitor_resources,
        args=(str(run_dir / f"resources_{timestamp}.csv"), 1, stop_monitor),
        daemon=False,
    )
    monitor_thread.start()

    data_thread = threading.Thread(
        target=data_loop,
        args=(conn, cur, camera, DEFAULT_USER_ID, flags_present,
                    run_dir, timestamp, db_name),
        daemon=False,
    )
    data_thread.start()

    #if MEM_TEST_MODE:
    #    stress_test_thread = threading.Thread(
    #        target=stress_test,
    #        args=(shared_state, cur),
    #        daemon=True,
    #    )
    #    stress_test_thread.start()

    # ── Serve ───────────────────────────────────────────────────
    try:
        print('Starting data collection loop (no web server)...')
        # Wait for data collection to complete all cycles
        data_thread.join()
        print('Data collection complete.')
    except KeyboardInterrupt:
        print('\nShutdown requested by user.')
    finally:
        # Signal monitor thread to stop and clean up
        stop_monitor.set()
        monitor_thread.join(timeout=10)
        log_file.close()


if __name__ == "__main__":
    run_collector()