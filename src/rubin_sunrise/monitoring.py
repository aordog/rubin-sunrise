"""
monitoring.py: Monitor CPU, memory, and user interactions for dashboard 
performance.

This module provides resource monitoring, interactive stress testing for
performance evaluation, and multi-destination logging utilities.

Public API
----------
- ``QuietFilter`` - Suppress verbose Flask endpoint logging.
- ``Logger`` - Multi-destination logger with timestamp prefixing.
- ``monitor_resources`` - Log CPU and memory usage to file.
- ``monitoring_plots`` - Plot the results from `monitor_resources`
- ``stress_test`` - Perform automated clicks on dashboard for back-end testing.

**Author:** Anna Ordog, for CanDIAPL
"""

import time
from astropy.time import Time
from astropy.visualization import time_support
from datetime import datetime
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import random
import logging
from typing import TYPE_CHECKING
import requests
import os, psutil
import numpy as np
import pandas as pd

from rubin_sunrise.config import PORT, STRESS_TEST_CLICK_INTERVAL, DB_NAME

if TYPE_CHECKING:
    from rubin_sunrise.state import SharedState


def _fetch_valid_rows(cur) -> list[dict]:
    """Query database to get all valid row state tuples.

    Fetches group and member IDs from database, replicating the exact
    group/member ordering logic used by displays.populate_table() to
    ensure row indices (index, gn, mn) match the table rows.

    Parameters
    ----------
    cur : psycopg2.cursor
        Database cursor with DictCursor factory.

    Returns
    -------
    list[dict]
        List of dicts with keys 'index' (row number), 'gn' (group ID),
        'mn' (member index within group).
    """
    cur.execute("""
        SELECT g.group_id, m.member_id
        FROM members m
        JOIN groups g ON g.group_id = m.group_id
        ORDER BY g.group_id, m.member_id
    """)
    db_rows = cur.fetchall()
    
    rows = []
    prev_gid = None
    mem_idx = 0
    for n, r in enumerate(db_rows):
        if r[0] != prev_gid:  # r[0] is group_id
            prev_gid = r[0]
            mem_idx = 0
        else:
            mem_idx += 1
        rows.append({
            "index": n,
            "gn": r[0],
            "mn": mem_idx,
        })
    return rows

def _get_click_action(cycle: int) -> str:
    """Determine click action for a given cycle number.

    Maps cycle numbers to actions in a repeating 4-cycle pattern:
    - cycles 1, 3 mod 4: no clicks
    - cycle 2 mod 4: row clicks
    - cycle 4 mod 4: maptype clicks
    TO DO: might implement other test sequences later

    Parameters
    ----------
    cycle : int
        Cycle number (1-indexed).

    Returns
    -------
    str
        Action string: one of 'no clicks', 'row clicks', 'map-type clicks'.
    """
    cycle_mod = ((cycle - 1) % 4) + 1
    if cycle_mod == 1:
        return "no clicks"
    elif cycle_mod == 2:
        return "row clicks"
    elif cycle_mod == 3:
        return "no clicks"
    elif cycle_mod == 4:
        return "map-type clicks"

def _perform_row_click(base_url: str, row: dict) -> None:
    """Send HTTP POST request for row click to dashboard server.

    Sends a row_clicked request with the specified row's index, group,
    and member index.

    Parameters
    ----------
    base_url : str
        Base URL of the dashboard server.
    row : dict
        Row state dict from _fetch_valid_rows() with keys 'index', 'gn', 'mn'.
    """
    try:
        payload = {
            "index": row["index"],
            "maptype": "daily",
            "gn": str(row["gn"]),
            "mn": str(row["mn"])
        }
        response = requests.post(f"{base_url}/row_clicked", json=payload, timeout=5)
    except Exception as e:
        print(f"Row click error: {e}")

def _perform_maptype_click(base_url: str, maptype: str, gn: str,
                           mn: str) -> None:
    """Send HTTP POST request for maptype click to dashboard server.

    Sends a maptype_clicked request to toggle between 'daily' and 'total'
    visualizations for a specified group and member.

    Parameters
    ----------
    base_url : str
        Base URL of the dashboard server.
    maptype : str
        Map type selection: 'daily' or 'total'.
    gn : str
        Group ID as string.
    mn : str
        Member index as string.
    """
    try:
        payload = {
            "index": 0,
            "maptype": maptype,
            "gn": gn,
            "mn": mn
        }
        response = requests.post(f"{base_url}/maptype_clicked", json=payload, timeout=5)
    except Exception as e:
        print(f"Maptype click error: {e}")

def _read_log(dir_files, file_time, search_string):
    """Extract timestamps from log file matching search string.

    Parses a log file and returns a list of timestamps extracted from
    lines containing the specified search string.

    Parameters
    ----------
    dir_files : str
        Base directory containing the log file subdirectory.
    file_time : str
        Subdirectory and filename prefix for the log file.
    search_string : str
        String to search for in log lines.

    Returns
    -------
    list[str]
        List of timestamp strings extracted from matching lines.
    """
    ts = []
    with open(f"{dir_files}/log_{file_time}.txt", 'r') as file:
        for line in file:
            if search_string in line:
                ts.append(line.strip().split()[0][1::]+" "+line.strip().split()[1][0:-1])

    return ts

def _write(destinations, msg, at_line_start):
    """Write message to multiple destinations with timestamp prefixing.

    Splits message by newlines and writes each line to all destinations.
    Prepends timestamps to lines that start at the beginning of a new line.

    Parameters
    ----------
    destinations : tuple
        File-like objects to write to (e.g., sys.stdout, open files).
    msg : str
        Message to write.
    at_line_start : bool
        Whether output position is at the start of a new line.

    Returns
    -------
    bool
        Updated at_line_start flag indicating final output position.
    """
    lines = msg.split("\n")

    for i, line in enumerate(lines):
        if i > 0:
            for dest in destinations:
                dest.write("\n")
            at_line_start = True

        if line:
            if at_line_start:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                line = f"[{timestamp}] {line}"
                at_line_start = False
            for dest in destinations:
                dest.write(line)
                dest.flush()

    return at_line_start


class QuietFilter(logging.Filter):
    """Logging filter to suppress verbose Flask endpoint messages.
    
    Filters out logging records from endpoints that generate high-cadence
    messages not useful for debugging or monitoring to keep log files and 
    terminal output readable.
    
    Attributes
    ----------
    NOISY : set
        Collection of endpoint paths whose log messages should be suppressed.
    """

    NOISY = {'/check_update', '/next_update'}

    def filter(self, record):
        """Check if a log record should be allowed through the filter.

        Suppresses logging output for noisy endpoints that generate
        high-cadence messages (e.g., frequent polling requests). This keeps
        log files and terminal output readable during normal operation.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to filter.

        Returns
        -------
        bool
            False if the record contains a message from a noisy endpoint
            (endpoint paths in NOISY set), True otherwise (record allowed).
        """
        return not any(path in record.getMessage() for path in self.NOISY)

class Logger:
    """Multi-destination logging handler with timestamp prefixing.
    
    Writes log messages to multiple output streams (terminal, file) with
    timestamps. Compatible with sys.stdout/sys.stderr redirection.
    
    Parameters
    ----------
    *destinations : file-like
        Variable number of output streams to write to (e.g., sys.stdout,
        open file objects).
    
    Attributes
    ----------
    destinations : tuple
        Collection of output streams.
    at_line_start : bool
        Flag tracking start of new line (for timestamp insertion).
    """
    
    def __init__(self, *destinations):
        self.destinations = destinations
        self.at_line_start = True

    def write(self, msg):
        """Write message to multiple destinations with timestamp prefixing.

        Splits message by newlines and writes each line to all destinations.
        Prepends timestamps to lines that start at the beginning of a new line.
        Updates internal state tracking to know when the next write starts on
        a new line.

        Parameters
        ----------
        msg : str
            Message to write.
        """
        self.at_line_start = _write(self.destinations, msg,
                                    self.at_line_start)

    def flush(self):
        """Flush all output streams.

        Ensures all buffered data in each destination stream is written out
        immediately. Called after each write operation for real-time logging.
        """
        for dest in self.destinations:
            dest.flush()

def monitor_resources(log_path, interval=5, stop_event=None):
    """Log CPU and memory usage at regular intervals.

    Monitors the current process and writes CPU percentage and memory
    usage (in MB) to a CSV file at specified intervals until stop_event
    is set. Used for performance profiling during dashboard operation.

    Parameters
    ----------
    log_path : str
        Path to output CSV file for resource data.
    interval : float, optional
        Sampling interval in seconds. Default is 5.
    stop_event : threading.Event
        Event object to signal monitoring to stop. When stop_event.is_set()
        returns True, monitoring terminates. Required (not optional).
    """
    process = psutil.Process(os.getpid())

    with open(log_path, "w") as f:
        f.write("timestamp,cpu_percent,memory_mb\n")

        while not stop_event.is_set():
            cpu = process.cpu_percent(interval=interval)
            mem = process.memory_info().rss / (1024 * 1024)  # bytes → MB
            ts  = time.strftime("%Y-%m-%d %H:%M:%S")

            f.write(f"{ts},{cpu:.1f},{mem:.1f}\n")
            f.flush()

def log_table_size(cur, log_path):
    """Log total database size in bytes with timestamp.

    Records the total on-disk size in bytes of the lsst_database along with 
    the current timestamp. Designed to be called once per iteration of the 
    main data loop in pipeline.py.

    Parameters
    ----------
    cur : psycopg2.cursor
        Database cursor for executing size query.
    log_path : str
        Path to output CSV file for table size data.
    """
    file_exists = os.path.isfile(log_path)

    cur.execute("SELECT pg_database_size(%s)", (DB_NAME,))
    total_size = cur.fetchone()[0]
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    with open(log_path, "a") as f:
        if not file_exists:
            f.write("timestamp,total_size_bytes\n")
        f.write(f"{ts},{total_size}\n")
        f.flush()

def stress_test(shared_state: "SharedState", cur) -> None:
    """Perform automated dashboard interactions for backend performance 
    testing.

    Monitors cycle number and performs automated clicks based on a repeating 
    4-cycle pattern. Different click types test different interaction modes:
    - Cycles 1, 3 mod 4: No clicks
    - Cycle 2 mod 4: Random row clicks (tests row selection)
    - Cycle 4 mod 4: Maptype clicks (tests daily/total map toggle)

    Clicks are spaced by STRESS_TEST_CLICK_INTERVAL seconds during their
    active cycle.

    Parameters
    ----------
    shared_state : SharedState
        Shared state containing current cycle_number.
    cur : psycopg2.cursor
        Database cursor to fetch valid row states for clicking.
    """
    # Fetch valid rows once at startup
    valid_rows = _fetch_valid_rows(cur)
    if not valid_rows:
        print("Warning: No valid rows available for stress testing")
        return
    
    base_url = f"http://localhost:{PORT}"
    last_cycle = 0
    current_maptype = "daily"
    fixed_row = valid_rows[0]  # Use first row for maptype clicks
    last_click_time = 0
    active_cycle = 0  # Track which cycle we're performing clicks for
    
    while True:
        snap = shared_state.snapshot()
        current_cycle = snap.get("cycle_number", 0)
        now = time.time()
        
        # When cycle changes, print the action and reset timing
        if current_cycle != last_cycle and current_cycle > 0:
            action = _get_click_action(current_cycle)
            print(f"stress test for cycle {current_cycle}: {action}")
            last_cycle = current_cycle
            active_cycle = current_cycle
            last_click_time = now
        
        # Only perform clicks if we're still in the active cycle
        cycle_mod = ((active_cycle - 1) % 4) + 1 if active_cycle > 0 else 0
        
        if active_cycle > 0 and current_cycle == active_cycle and (now - last_click_time) >= STRESS_TEST_CLICK_INTERVAL:
            if cycle_mod == 2:
                # Row clicks with random row each time
                row = random.choice(valid_rows)
                _perform_row_click(base_url, row)
            elif cycle_mod == 4:
                # Maptype clicks, alternating maptype but keeping same row
                current_maptype = "total" if current_maptype == "daily" else "daily"
                _perform_maptype_click(base_url, current_maptype,
                                      str(fixed_row["gn"]),
                                      str(fixed_row["mn"]))
            
            last_click_time = now
        
        time.sleep(0.1)

def monitoring_plots(dir_files, file_time, ymax_mb=800):
    """Generate performance monitoring plots from resource data.

    Creates a plot showing memory usage, CPU usage, and annotated event
    timings (data updates, map toggle, row clicks) from logged monitoring
    data. Saves output as PDF and PNG files.

    Parameters
    ----------
    dir_files : str
        Base directory containing monitoring data subdirectories.
    file_time : str
        Subdirectory and filename prefix for data and output files.
    ymax_mb : float, optional
        Maximum memory axis limit in MB. Default is 800.
    """
    time_support()

    data  = pd.read_csv(f"{dir_files}/resources_{file_time}.csv")
    data2 = pd.read_csv(f"{dir_files}/table_size_{file_time}.csv")

    timestamp   = Time(data['timestamp'].tolist())
    cpu_percent = np.array(data['cpu_percent'])
    memory_mb   = np.array(data['memory_mb'])
    timestamp2  = Time(data2['timestamp'].tolist())
    filesize    = np.array(data2['total_size_bytes'])/1e6 # MB

    ts_update  = _read_log(dir_files, file_time, "Updated data for")
    ts_maptype = _read_log(dir_files, file_time, "Map type")
    ts_rowpick = _read_log(dir_files, file_time, "Row")

    fig, ax = plt.subplots(3,1, figsize=(10,8))
    plt.subplots_adjust(left=0.1,right=0.95,top=0.95,bottom=0.1,hspace=0.15)

    ax[0].plot(timestamp, memory_mb, color='k',linewidth=1)
    ax[0].set_ylim(0,ymax_mb)
    ax[0].set_ylabel('Memory (MB)')

    ax[1].plot(timestamp, cpu_percent, color='k',linewidth=1)
    ax[1].set_ylim(0,100)
    ax[1].set_ylabel('CPU (%)')

    ax[2].plot(timestamp2, filesize, color='k',linewidth=1)
    ax[2].set_ylim(0,)
    ax[2].set_ylabel('Table size (MB)')

    colors = ['grey', 'blue', 'green']
    labels = ['update', 'toggle map', 'click row']
    linestyles = ['dashed', 'dashed', 'dotted']
    ts = [ts_update, ts_maptype, ts_rowpick]
    for k in [0,1]:
        for j in range(0,3):
            for i in range(0,len(ts[j])):
                if i == 0:
                    ax[k].plot(Time([ts[j][i], ts[j][i]]),[0,1000], linestyle=linestyles[j], 
                        linewidth=0.5, color=colors[j], label=labels[j])
                else:
                    ax[k].plot(Time([ts[j][i], ts[j][i]]),[0,1000], linestyle=linestyles[j], 
                            linewidth=0.5, color=colors[j])

    for k in range(0,3):
        ax[k].set_xlim(timestamp[0],timestamp[-1])
        ax[k].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        if k < 1:
            ax[k].legend(framealpha=1, loc='lower left')
    ax[2].set_xlabel('Time')

    ax[0].set_title(f'{len(timestamp2)} simulated days', fontsize=18)

    plt.savefig(f"{dir_files}/{file_time}.pdf")
    plt.savefig(f"{dir_files}/{file_time}.png")

    return