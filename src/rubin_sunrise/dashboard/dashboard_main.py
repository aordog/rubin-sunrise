"""Dashboard display subsystem entry point.

Runs the dashboard display updates.

Entry point: `python -m rubin_sunrise.dashboard.dashboard_main`

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
    DB_NAME,
    ENABLE_CONSOLE_OUTPUT,
)
 

from rubin_sunrise.dashboard.state import SharedState
from rubin_sunrise.dashboard.database_read import get_database
from rubin_sunrise.dashboard.runner import data_loop
from rubin_sunrise.dashboard.app import create_app
from rubin_sunrise.monitoring import ( 
                                    monitor_resources, 
                                    QuietFilter)

# Resolve project root (…/src/rubin_sunrise/__main__.py  →  …/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

logger = logging.getLogger(__name__)


def run_display(db_name: str | None = None) -> None:
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

    Parameters
    ----------
    db_name : str | None
        Database name. If None, uses default from config.

    Configuration Parameters
    --------
    All parameters read from rubin_sunrise.config:
    - PORT: Flask server port
    - DEFAULT_USER_ID: Database user identifier
    - INITIAL_OFFSET: Declination limit for target filtering
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
    # Use provided db_name or fall back to config default
    if db_name is None:
        db_name = DB_NAME

    # ── Output / logging ────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    run_dir = OUTPUT_BASE / 'logs' / 'display_logs' / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Configure unified logging for all rubin_sunrise modules
    # Custom formatter that strips the redundant 'rubin_sunrise.' prefix
    class CondensedFormatter(logging.Formatter):
        def format(self, record):
            # Remove 'rubin_sunrise.' prefix from logger name
            if record.name.startswith('rubin_sunrise.'):
                record.name = record.name[len('rubin_sunrise.'):]
            return super().format(record)
    
    # Unified format for both console and file (consistency)
    log_formatter = CondensedFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler - always write DEBUG and above
    file_handler = logging.FileHandler(run_dir / f"log_{timestamp}.txt")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_formatter)
    
    # Console handler - conditional based on ENABLE_CONSOLE_OUTPUT
    console_handler = None
    if ENABLE_CONSOLE_OUTPUT:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)  # Full DEBUG level for development
        console_handler.setFormatter(log_formatter)
    
    # Configure root logger to WARNING to suppress third-party debug spam
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    root_logger.addHandler(file_handler)
    if console_handler:
        root_logger.addHandler(console_handler)
    
    # Configure rubin_sunrise loggers to DEBUG level (only affects our code)
    rubin_logger = logging.getLogger('rubin_sunrise')
    rubin_logger.setLevel(logging.DEBUG)
    
    # Suppress third-party debug messages
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('astropy').setLevel(logging.WARNING)
    logging.getLogger('psycopg2').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').addFilter(QuietFilter())

    conn, cur, flags_present = get_database(db_name=db_name)

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
        daemon=False,
    )
    monitor_thread.start()

    data_thread = threading.Thread(
        target=data_loop,
        args=(shared_state, conn, cur, DEFAULT_USER_ID, flags_present, 
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

    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    # ── Serve ───────────────────────────────────────────────────
    try:
        logger.info('Starting display update...')
        # Wait for data collection to complete all cycles
        app.run(port=PORT)
        logger.info('Display update complete.')
    except KeyboardInterrupt:
        logger.info('Shutdown requested by user.')
    finally:
        # Signal monitor thread to stop and clean up
        stop_monitor.set()
        monitor_thread.join(timeout=10)


if __name__ == "__main__":
    run_display()