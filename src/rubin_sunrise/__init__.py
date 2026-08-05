"""
Rubin Dashboard - interactive survey-progress dashboard for Rubin LSST.

A Flask-based dashboard for tracking observation progress and target coverage 
during LSST survey observations (simulated for now). Displays visit counts, 
coverage, time series, and observability forecasts for user-selected targets.

To run the dashboard:
    python -m rubin_sunrise

Upon startup, the dashboard:
- Initializes a PostgreSQL database with user's target catalog
- Populates historical observation data
- Launches a background data processing pipeline
- Opens the web interface in your default browser

All configuration is defined in rubin_sunrise/config.py.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("rubin-sunrise")
except PackageNotFoundError:
    __version__ = "0.1.0.dev0"

__author__ = "Anna Ordog"

__all__ = ["__version__", "__author__"]