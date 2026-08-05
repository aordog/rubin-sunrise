"""
app.py: Flask application factory and route definitions.

This module defines the Flask application factory and all HTTP endpoints.
It coordinates with the background data pipeline to display the data table and 
summary plots, allowing for updates based on user interactions.

**Thread Safety Note:** This module accesses a shared `SharedState` object 
managed by the background data loop. The `snapshot()` method provides 
thread-safe read access to the current dashboard state.

**Author:** Anna Ordog, for CanDIAPL
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
import psycopg2.extras
from flask import Flask, jsonify, render_template, request

from rubin_sunrise.pipeline import _reclaim_memory
from rubin_sunrise.displays import TargetMap, TargetTimeSeries, ObservabilityData
if TYPE_CHECKING:
    from rubin_sunrise.state import SharedState


def create_app(
    shared_state: SharedState,
    conn,
    *,
    flags_present: bool = False,
    template_folder: str | Path | None = None,
    static_folder: str | Path | None = None,
) -> Flask:
    """Build and return the configured Flask application.

    Initializes a Flask application with all routes for the dashboard. The app 
    provides endpoints for viewing data visualizations, interacting with the
    visualizations, and polling for updates from the background data pipeline.

    Parameters
    ----------
    shared_state : SharedState
        Thread-safe state shared with the background data loop. Provides access
        to current data snapshots, progress information, and update tracking.
    conn : psycopg2.extensions.connection
        PostgreSQL database connection, kept open for the lifetime of the 
        process. Used by route handlers to query the user-specific database.
    flags_present : bool, optional
        Whether user-defined observability flags are present in the database.
    template_folder : str | Path | None, optional
        Specify the Flask template search path.
    static_folder : str | Path | None, optional
        Specify the Flask static file search path.

    Returns
    -------
    Flask
        Configured Flask application with routes registered, ready to serve.
    """
    kwargs: dict = {}
    if template_folder is not None:
        kwargs["template_folder"] = str(template_folder)
    if static_folder is not None:
        kwargs["static_folder"] = str(static_folder)

    app = Flask(__name__, **kwargs)

    # helpers local to the app:
    def _render_plots(gn: int, mn: int, maptype: str, date) -> dict:
        """Generate visualization plots for a chosen target.

        Creates the interactive HTML visualizations:
        - 2D visits map for the region surrounding the target
        - Visits time series for the target
        - Future observability of the target

        Uses a short-lived cursor to minimize database connection overhead,
        then reclaims memory.

        Parameters
        ----------
        gn : int
            Group number (target group identifier).
        mn : int
            Member number (target member identifier within the group).
        maptype : str
            Type of visits map to generate ("daily" or "total").
        date : str
            Date string for calculating the future observability.

        Returns
        -------
        dict
            Flask JSON response containing:
            - "status": "ok"
            - "fig1_html": HTML rendering of the visits map
            - "fig2_html": HTML rendering of the visits time series
            - "fig3_html": HTML rendering of the observability plot
        """
        local_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            fig1_html=TargetMap(gn,local_cur).make_html_visits_map(mn,maptype)
            fig2_html=TargetTimeSeries(gn,mn,local_cur).make_html_visits_plot(mn,maptype)
            fig3_html=ObservabilityData(gn,mn,local_cur,date, flags_present).make_html_obs_plot()
            #fig3_html = ""  # DISABLED FOR TESTING
        finally:
            local_cur.close()
        result = jsonify({"status": "ok", "fig1_html": fig1_html, 
                                          "fig2_html": fig2_html, 
                                          "fig3_html": fig3_html})
        _reclaim_memory()
        return result

    # routes:
    @app.route("/")
    def home() -> str:
        """Serve the main dashboard page.

        Retrieves the current dashboard state and renders the templates/index 
        page with the latest visualizations, data table, and countdown to next 
        update. 

        Returns
        -------
        str
            HTML content of the rendered dashboard page.
        """
        snap = shared_state.snapshot()
        if snap["table"] is None:
            return (
                "<h2>Data loading…</h2>"
                "<meta http-equiv='refresh' content='2'>"
            )
        return render_template(
            "index.html",
            date=snap["date"],
            fig1_html=snap["fig1_html"],
            fig2_html=snap["fig2_html"],
            fig3_html=snap["fig3_html"],
            table_html=snap["table"],
            version=snap["version"],
            countdown_seconds=max(0, snap["next_update"] - time.time()),
            flags_present=flags_present,
        )

    @app.route("/row_clicked", methods=["POST"])
    def row_clicked() -> dict:
        """Handle row selection from the table of targets.

        Processes a user click on a row in the table and re-renders the
        visualization plots for the selected target. Extracts group and member
        identifiers from the request and generates fresh plots.

        Request JSON
        --------
        index : int
            Row index in the table (for logging purposes).
        gn : int or str
            Group number of the selected target.
        mn : int or str
            Member number of the selected target.
        maptype : str, optional
            Type of map to display (default: "daily").

        Returns
        -------
        dict
            JSON response with plot HTML from ``_render_plots()``.
        """
        data    = request.get_json()
        gn      = int(data["gn"])
        mn      = int(data["mn"])
        maptype = data.get("maptype", "daily")
        date    = shared_state.snapshot()["date"]
        print(
            f"Row {data['index']} clicked "
            f"(maptype={maptype}, group:{gn}, member:{mn})"
        )
        return _render_plots(gn, mn, maptype, date)

    @app.route("/maptype_clicked", methods=["POST"])
    def maptype_clicked() -> dict:
        """Handle map type selection from the visualization area.

        Processes a user toggling of the map type ("daily" or "total") and 
        re-renders the visits map and time series while keeping the same target 
        selected.

        Request JSON
        --------
        gn : int or str
            Group number of the target.
        mn : int or str
            Member number of the target.
        maptype : str
            New map type and time series to display ("daily" or "total").
        index : int, optional
            Row index (for logging, default: 0).

        Returns
        -------
        dict
            JSON response with plot HTML from ``_render_plots()``.
        """
        data    = request.get_json()
        gn      = int(data["gn"])
        mn      = int(data["mn"])
        maptype = data["maptype"]
        date    = shared_state.snapshot()["date"]
        print(
            f"Map type {maptype} clicked "
            f"(row={data.get('index', 0)}, group:{gn}, member:{mn})"
        )
        return _render_plots(gn, mn, maptype, date)

    @app.route("/obs_plot_update", methods=["POST"])
    def obs_plot_update() -> dict:
        """Handle observability plot updates based on user click.

        Processes a user click on the top panel of the observability plot and 
        regenerates the bottom panel zoomed to a time window starting on the
        selected date.

        Request JSON
        --------
        gn : int or str
            Group number of the target.
        mn : int or str
            Member number of the target.
        selected_date : str
            ISO format date string (e.g., '2025-04-27').
        window_days : int, optional
            Number of days to show after selected_date (default: 5).

        Returns
        -------
        dict
            JSON response with:
            - "status": "ok"
            - "fig3_html": HTML rendering of the updated observability plot
        """
        data = request.get_json()
        gn = int(data["gn"])
        mn = int(data["mn"])
        selected_date = data.get("selected_date")
        window_days = int(data.get("window_days", 5))
        date = shared_state.snapshot()["date"]
        
        local_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            fig3_html = ObservabilityData(gn, mn, local_cur, date, flags_present).make_html_obs_plot(
                selected_date=selected_date, 
                window_days=window_days
            )
        finally:
            local_cur.close()
        
        result = jsonify({"status": "ok", "fig3_html": fig3_html})
        _reclaim_memory()
        return result

    @app.route("/check_update")
    def check_update() -> dict:
        """Check for data updates.

        Polling endpoint for client-side scripts to detect when new data are
        available. Clients compare the returned version with their cached
        version to determine if a page refresh is needed.

        Current Implementation:
            Refresh happens every `REFRESH_INTERVAL` as defined in config.py.

        Future Version:
            Will poll for a new date to provide daily updates from the Rubin
            database.

        Returns
        -------
        dict
            JSON response with:
            - "version": Current dashboard data version identifier.
        """
        snap = shared_state.snapshot()
        return jsonify({"version": snap["version"]})

    @app.route("/next_update")
    def next_update() -> dict:
        """Provide update status and timing information.

        Polling endpoint that returns information about the next scheduled data
        update and the current state of any in-progress update. Used by the
        client to display progress information and update the countdown timer.

        Current Implementation:
            Timer counts down the `REFRESH_INTERVAL` defined in config.py.

        Future Version:
            Will countdown to the following date.

        Returns
        -------
        dict
            JSON response with:
            - "next_update": Unix timestamp of the next scheduled update.
            - "server_time": Current server time for synchronization.
            - "updating": Boolean indicating if an update is in progress.
            - "progress": Numeric progress value for update progress bar.
            - "progress_msg": Detailed progress message string.
            - "cycle_number": Current update cycle counter.
        """
        snap = shared_state.snapshot()
        return jsonify({
            "next_update":  snap["next_update"],
            "server_time":  time.time(),
            "updating":     snap["updating"],
            "progress":     snap["progress"],
            "progress_msg": snap["progress_msg"],
            "cycle_number": snap["cycle_number"],
        })

    return app