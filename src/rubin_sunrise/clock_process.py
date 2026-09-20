"""
clock_process.py: Standalone simulated clock process.

This module provides a standalone process that continuously advances
a simulated clock and persists the time to a PostgreSQL database.
All other application instances (collectors, dashboards) read the
current simulated time from this centralized clock.

Entry point: `python -m rubin_sunrise.clock_process`

**Author:** Anna Ordog, for CanDIAPL
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path

from rubin_sunrise.config import (
    SIM_START,
    SIM_END,
    CLOCK_DB_NAME,
    SIM_SPEEDUP_FACTOR,
)
from rubin_sunrise.sim_clock import SimulatedClock

# Resolve project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_clock(clock_db_name: str | None = None, refresh_interval: float = 1.0) -> None:
    """Run the standalone simulated clock process.
    
    Initializes the clock, loads any existing state from the database,
    then enters an infinite loop where it:
    1. Sleeps for refresh_interval real seconds
    2. Advances the simulated clock
    3. Persists the updated time to the database
    4. Checks if simulation is complete and exits if so
    
    Parameters
    ----------
    clock_db_name : str | None
        Name of shared clock database. If None, uses CLOCK_DB_NAME from config.
    refresh_interval : float
        Real-time sleep interval (seconds) between clock updates.
        Default: 1.0 second. Smaller values give finer time resolution
        but use more CPU; larger values are more efficient but less precise.
    
    Notes
    -----
    This process should be started before other application instances
    that depend on the clock. It will run indefinitely until the
    simulation reaches SIM_END, at which point it exits cleanly.
    
    On Ctrl+C (KeyboardInterrupt), logs a shutdown message and exits.
    """
    if clock_db_name is None:
        clock_db_name = CLOCK_DB_NAME
    
    logger.info("=" * 70)
    logger.info("Simulated Clock Process Starting")
    logger.info("=" * 70)
    logger.info(f"Clock Database: {clock_db_name}")
    logger.info(f"Sim Start: {SIM_START}")
    logger.info(f"Sim End: {SIM_END}")
    logger.info(f"Speedup Factor: {SIM_SPEEDUP_FACTOR}x")
    logger.info(f"Refresh Interval: {refresh_interval} real seconds")
    logger.info("=" * 70)
    
    # Set up (drop and recreate) the clock database
    try:
        SimulatedClock.setup_clock_database(clock_db_name, SIM_START)
    except Exception as e:
        logger.error(f"Failed to set up clock database: {e}")
        sys.exit(1)
    
    # Create clock instance
    clock = SimulatedClock(
        sim_start=SIM_START,
        sim_end=SIM_END,
        speedup_factor=SIM_SPEEDUP_FACTOR
    )
    
    # Load any previously saved state
    try:
        clock.load_from_db(clock_db_name)
    except Exception as e:
        logger.warning(f"Could not load previous clock state, starting fresh: {e}")
    
    logger.info(f"Starting simulation from: {clock.get_current_time()}")
    print(f"[CLOCK START] {clock.get_current_time()}")
    
    cycle_count = 0
    try:
        while not clock.is_ended():
            cycle_count += 1
            
            # Sleep for the refresh interval
            time.sleep(refresh_interval)
            
            # Advance the clock by the time that has passed
            clock.advance(refresh_interval)
            
            # Persist to database
            try:
                clock.save_to_db(clock_db_name)
            except Exception as e:
                logger.error(f"Failed to save clock state to database: {e}")
                # Don't exit on DB errors; try again next cycle
            
            # Log progress every 60 cycles (every ~60 seconds with default 1s refresh)
            if cycle_count % 60 == 0:
                current = clock.get_current_time()
                logger.info(f"[CYCLE #{cycle_count}] {current}")
                print(f"[CYCLE #{cycle_count}] {current}")
        
        # Simulation complete
        current = clock.get_current_time()
        logger.info("=" * 70)
        logger.info(f"[CLOCK END] Simulation complete at: {current}")
        logger.info("=" * 70)
        print(f"[CLOCK END] {current}")
        
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 70)
        logger.info("Clock process interrupted by user (Ctrl+C)")
        current = clock.get_current_time()
        logger.info(f"Final simulated time: {current}")
        logger.info("=" * 70)
        print(f"\n[CLOCK STOPPED] {current}")
    except Exception as e:
        logger.error(f"Unexpected error in clock process: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Allow optional command-line argument for clock database name
    clock_db_name = sys.argv[1] if len(sys.argv) > 1 else None
    run_clock(clock_db_name=clock_db_name)
