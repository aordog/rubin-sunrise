"""
state.py: Thread-safe shared state linking data pipeline and web layer.

This module provides the `SharedState` class, which synchronizes data
between the background data-processing loop running in a daemon thread and
the Flask web application serving request handlers. Thread safety is
enforced via a lock, ensuring that concurrent reads and writes do not
produce inconsistent state.

**Author:** Anna Ordog, for CanDIAPL
"""

from __future__ import annotations
import threading

class SharedState:
    """Thread-safe container for shared dashboard state.

    This class wraps a dictionary of dashboard state and provides 
    lock-protected access methods. It facilitates communication between the 
    background data pipeline (running in a daemon thread) and the Flask request 
    handlers (running in the main thread).

    The state dictionary tracks:
    - Visualization data (HTML figures and table)
    - Update timing and progress
    - Data versioning for cache invalidation (avoid using stale figures)

    All state modifications must go through the `write()` method or the
    `snapshot()` method for reads to ensure thread safety.
    """

    def __init__(self) -> None:
        """Initialize shared state with default values.

        Creates a thread lock and initializes the internal state dictionary 
        with empty or default values for all dashboard elements.
        """
        self._lock = threading.Lock()
        self._data: dict = {
            "date":         None,
            "fig1_html":    "",
            "fig2_html":    "",
            "fig3_html":    "",
            "table":        None,
            "version":      0,
            "updating":     False,
            "progress":     0.0,
            "progress_msg": "",
            "next_update":  0.0,
            "cycle_number": 0,
        }

    # -- Public methods --

    def snapshot(self) -> dict:
        """Return a thread-safe shallow copy of the state.

        Creates an atomic read of the entire state dictionary. Useful for 
        request handlers that need a consistent view of multiple state fields 
        without holding the lock.

        Returns
        -------
        dict
            A shallow copy of the internal state dictionary, read atomically 
            under the lock.
        """
        with self._lock:
            return dict(self._data)

    def write(self, **kwargs) -> None:
        """Atomically update one or more state fields.

        Updates the internal state dictionary with the provided
        keyword arguments. The entire update is performed atomically
        under the lock, ensuring that other threads observing the
        state will either see the old values or all new values, never
        a partial update.

        Parameters
        ----------
        **kwargs
            Key-value pairs to update in the state dictionary.
            Typical keys include: date, fig1_html, fig2_html,
            fig3_html, table, version, updating, progress,
            progress_msg, next_update, cycle_number.
        """
        with self._lock:
            self._data.update(kwargs)