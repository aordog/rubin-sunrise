"""
sim_clock.py: Simulated clock for testing with accelerated time.

Provides a centralized simulated clock that runs faster than real time,
advancing simulated dates at a configurable speedup factor. The clock state
is persisted to a PostgreSQL database so that multiple instances of the
application can access the same simulated time.

**Author:** Anna Ordog, for CanDIAPL
"""

import threading
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import extras
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root for schema file location
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class SimulatedClock:
    """Thread-safe simulated clock that advances faster than real time.
    
    Maintains the current simulated time, advancing it by a configured
    speedup factor. Provides methods to query the current time, check if
    simulation is complete, and interface with persistent storage.
    
    Parameters
    ----------
    sim_start : datetime
        Starting simulated date/time
    sim_end : datetime
        Ending simulated date/time (simulation stops when time >= sim_end)
    speedup_factor : float
        How much faster than real time to advance the clock.
        E.g., speedup_factor=720 means 1 real second = 720 simulated seconds
              (0.2 simulated hours per real second, or 5 simulated days per real minute)
    
    Attributes
    ----------
    _current_time : datetime
        Current simulated time
    _lock : threading.Lock
        Lock for thread-safe access to _current_time
    _sim_start : datetime
        Starting simulated time
    _sim_end : datetime
        Ending simulated time
    _speedup_factor : float
        Speedup multiplier
    """
    
    def __init__(self, sim_start: datetime, sim_end: datetime, speedup_factor: float):
        """Initialize the simulated clock."""
        self._current_time = sim_start
        self._sim_start = sim_start
        self._sim_end = sim_end
        self._speedup_factor = speedup_factor
        self._lock = threading.Lock()
        self._started_at: datetime | None = None  # Real time when clock started advancing
    
    def get_current_time(self) -> datetime:
        """Get the current simulated time.
        
        Returns
        -------
        datetime
            Current simulated time
        """
        with self._lock:
            return self._current_time
    
    def advance(self, real_seconds: float) -> None:
        """Advance the simulated clock by the given real time interval.
        
        Parameters
        ----------
        real_seconds : float
            Number of real seconds that have elapsed.
            Simulated time advances by: real_seconds * speedup_factor
        """
        sim_seconds = real_seconds * self._speedup_factor
        sim_delta = timedelta(seconds=sim_seconds)
        
        with self._lock:
            self._current_time += sim_delta
    
    def is_ended(self) -> bool:
        """Check if the simulation has reached the end time.
        
        Returns
        -------
        bool
            True if current_time >= sim_end, False otherwise
        """
        with self._lock:
            return self._current_time >= self._sim_end
    
    def save_to_db(self, db_name: str) -> None:
        """Persist the clock state to the database.
        
        Updates the sim_clock table with the current simulated time,
        started_at timestamp, and last_updated timestamp.
        
        Parameters
        ----------
        db_name : str
            Database name to connect to
        
        Raises
        ------
        psycopg2.Error
            If database connection or update fails
        """
        try:
            conn = psycopg2.connect(dbname=db_name)
            with conn.cursor() as cur:
                with self._lock:
                    if self._started_at is None:
                        self._started_at = datetime.now()
                    
                    cur.execute("""
                        UPDATE sim_clock
                        SET sim_time = %s,
                            last_updated = NOW()
                        WHERE id = 1
                    """, (self._current_time,))
                
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Database error saving clock state: {e}")
            raise
        finally:
            conn.close()
    
    def load_from_db(self, db_name: str) -> None:
        """Load the clock state from the database.
        
        Restores the current simulated time from the sim_clock table.
        This allows the clock to resume from where it left off.
        
        Parameters
        ----------
        db_name : str
            Database name to connect to
        
        Raises
        ------
        psycopg2.Error
            If database connection fails
        """
        try:
            conn = psycopg2.connect(dbname=db_name)
            with conn.cursor(cursor_factory=extras.DictCursor) as cur:
                cur.execute("SELECT sim_time, started_at FROM sim_clock WHERE id = 1")
                row = cur.fetchone()
                
                if row:
                    with self._lock:
                        self._current_time = row['sim_time']
                        self._started_at = row['started_at']
                        logger.info(
                            f"Loaded clock state from DB: "
                            f"sim_time={self._current_time}, "
                            f"started_at={self._started_at}"
                        )
                else:
                    logger.warning("No clock state found in database; using initial time")
        except psycopg2.Error as e:
            logger.error(f"Database error loading clock state: {e}")
            raise
        finally:
            conn.close()
    
    @classmethod
    def setup_clock_database(cls, db_name: str, sim_start: datetime) -> None:
        """Create and initialize the clock database from scratch.
        
        Drops any existing clock database, creates a new one,
        and loads the schema from schema_clock.sql.
        
        This is destructive and should only be called at clock process startup.
        
        Parameters
        ----------
        db_name : str
            Database name to create
        sim_start : datetime
            Initial simulated time to set
        
        Raises
        ------
        subprocess.CalledProcessError
            If database commands fail
        """
        try:
            subprocess.run(["dropdb", db_name], capture_output=True)
        except subprocess.CalledProcessError:
            logger.info(f"Clock database {db_name} did not exist (normal on first run)")
        
        try:
            subprocess.run(["createdb", db_name], check=True)
            schema_file = _PROJECT_ROOT / "schema_clock.sql"
            subprocess.run(["psql", "-d", db_name, "-f", str(schema_file)], check=True)
            logger.info(f"Created clock database {db_name} with schema")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create clock database: {e}")
            raise
        
        # Now initialize the sim_clock table entry
        cls.initialize_db(db_name, sim_start)
    
    @classmethod
    def initialize_db(cls, db_name: str, sim_start: datetime) -> None:
        """Initialize the sim_clock table in the database.
        
        Creates or resets the sim_clock table with the given start time.
        Called during database schema setup.
        
        Parameters
        ----------
        db_name : str
            Database name to connect to
        sim_start : datetime
            Initial simulated time to set
        
        Raises
        ------
        psycopg2.Error
            If database operations fail
        """
        try:
            conn = psycopg2.connect(dbname=db_name)
            with conn.cursor() as cur:
                # Check if table exists; if not, create it
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sim_clock (
                        id INT PRIMARY KEY,
                        sim_time TIMESTAMP NOT NULL,
                        started_at TIMESTAMP,
                        last_updated TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Delete existing row and insert new one
                cur.execute("DELETE FROM sim_clock WHERE id = 1")
                cur.execute("""
                    INSERT INTO sim_clock (id, sim_time, started_at, last_updated)
                    VALUES (1, %s, NULL, NOW())
                """, (sim_start,))
                
                conn.commit()
                logger.info(f"Initialized sim_clock table with start time: {sim_start}")
        except psycopg2.Error as e:
            logger.error(f"Database error initializing sim_clock: {e}")
            raise
        finally:
            conn.close()


def get_sim_time(db_name: str) -> datetime:
    """Query the current simulated time from the database.
    
    Provides the primary access point for all application components
    that need to know the current simulated time. This function queries
    the persistent sim_clock table in the database.
    
    Parameters
    ----------
    db_name : str
        Database name to query
    
    Returns
    -------
    datetime
        Current simulated time
    
    Raises
    ------
    psycopg2.Error
        If database connection or query fails
    """
    try:
        conn = psycopg2.connect(dbname=db_name)
        with conn.cursor(cursor_factory=extras.DictCursor) as cur:
            cur.execute("SELECT sim_time FROM sim_clock WHERE id = 1")
            row = cur.fetchone()
            
            if row:
                return row['sim_time']
            else:
                logger.warning("No clock state found in database")
                raise ValueError("sim_clock table is empty or not initialized")
    except psycopg2.Error as e:
        logger.error(f"Database error reading sim_time: {e}")
        raise
    finally:
        conn.close()
