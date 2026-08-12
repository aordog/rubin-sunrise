"""
Dashboard application entry point and orchestration.

Entry point for ``python -m rubin_sunrise``. Orchestrates full startup
of the dashboard application including database initialization, Flask
app creation, background data processing pipeline, resource monitoring,
and optional stress testing. Manages all background threads and cleanup.

**Author:** Anna Ordog
"""

import logging
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from rubin_sunrise.config import (
    DEFAULT_USER_ID,
    INITIAL_OFFSET,
    MEM_TEST_MODE,
    OUTPUT_BASE,
    PORT,
    QUERY_FILE,
)
 
from rubin_sunrise.database import (
    initialize_tracking, set_up_db, populate_history, initialize_forecast,
)
from rubin_sunrise.state import SharedState
from rubin_sunrise.pipeline import data_loop
from rubin_sunrise.app import create_app
from rubin_sunrise.monitoring import (stress_test, 
                                    monitor_resources, 
                                    monitoring_plots,
                                    QuietFilter,
                                    Logger)

# Resolve project root (…/src/rubin_sunrise/__main__.py  →  …/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    """Initialize and run the Rubin Dashboard application.

    Orchestrates the complete startup sequence for the dashboard:

    1. Sets up logging and output directory with timestamped files
    2. Initializes PostgreSQL database
    3. Loads user's target catalog and camera footprint
    4. Populates database with historical observation data
    5. Initializes daily observability forecast data
    6. Creates Flask application with shared state management
    7. Spawns background threads:
       - data_loop: periodic database updates with observation data
       - monitor_resources: CPU and memory profiling (writes CSV)
       - stress_test: automated interaction testing if MEM_TEST_MODE
         enabled
    8. Opens web browser to dashboard URL
    9. Runs Flask server (blocking)
    10. On shutdown: saves monitoring plots and closes log file

    The dashboard runs as a multi-threaded application:
    - Main thread: Flask web server
    - Background threads: data pipeline, resource monitoring, and
      optional stress testing

    Log output is simultaneously written to terminal and timestamped
    log file via Logger multi-destination handler.

    Configuration Parameters
    --------
    All parameters read from rubin_sunrise.config:
    - PORT: Flask server port
    - DEFAULT_USER_ID: Database user identifier
    - INITIAL_OFFSET: Declination limit for target filtering
    - QUERY_FILE: Path to target catalog
    - MEM_TEST_MODE: Enable/disable automated stress testing

    Raises
    ------
    Exception
        Any errors during database setup or Flask initialization will
        propagate. Resource monitoring thread is cleaned up in the
        finally block.

    Notes
    -----
    This function blocks indefinitely while Flask server is running.
    Keyboard interrupt (Ctrl+C) triggers shutdown sequence.
    """
    # ── Output / logging ────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    run_dir = OUTPUT_BASE / 'logs'
    run_dir.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT_BASE / 'logs' / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    log_file = open(run_dir / f"log_{timestamp}.txt", "w")
    sys.stdout = Logger(sys.stdout, log_file)
    sys.stderr = Logger(sys.stderr, log_file)

    # ── Database ────────────────────────────────────────────────
    set_up_db()
    logging.getLogger("werkzeug").addFilter(QuietFilter())

    camera, conn, cur, flags_present = initialize_tracking(
        DEFAULT_USER_ID, QUERY_FILE, INITIAL_OFFSET,
    )

    # ── Populate database with historical data ──────────────────
    populate_history(conn, cur, camera, DEFAULT_USER_ID)

    # ── Populate database with observabillity data ──────────────
    initialize_forecast(conn, cur, DEFAULT_USER_ID)

    # ── Shared state & Flask app ────────────────────────────────
    shared_state = SharedState()
    app = create_app(
        shared_state,
        conn,
        flags_present=flags_present,
        template_folder=_PROJECT_ROOT / "templates",
        static_folder=_PROJECT_ROOT / "static",
    )

    # ── Background threads ──────────────────────────────────────
    stop_monitor = threading.Event()
    monitor_thread = threading.Thread(
        target=monitor_resources,
        args=(str(run_dir / f"resources_{timestamp}.csv"), 1, stop_monitor),
        daemon=True,
    )
    monitor_thread.start()

    data_thread = threading.Thread(
        target=data_loop,
        args=(shared_state, conn, cur, camera, DEFAULT_USER_ID, flags_present,
              run_dir, timestamp),
        daemon=True,
    )
    data_thread.start()

    if MEM_TEST_MODE:
        stress_test_thread = threading.Thread(
            target=stress_test,
            args=(shared_state, cur),
            daemon=True,
        )
        stress_test_thread.start()

    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    # ── Serve ───────────────────────────────────────────────────
    try:
        app.run(port=PORT)
    finally:
        stop_monitor.set()
        monitor_thread.join(timeout=10)
        monitoring_plots(run_dir, timestamp, ymax_mb=500)
        log_file.close()


if __name__ == "__main__":
    main()