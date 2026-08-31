"""
Utility functions for prototyping and development.

Provides helper functions for the prototyping phase of the dashboard,
including fake data generation (target list and date ranges)
and coordinate transformations. TO DO: determine where these should
ultimately go instead of generic 'utilities'

**Author:** Anna Ordog
"""

import numpy as np
import healpy as hp
from datetime import datetime, timedelta
from astropy.time import Time
import sqlite3

BANDS = ('u', 'g', 'r', 'i', 'z', 'y')
MASK_COLS = [f'{b}mask' for b in BANDS]
VISIT_COLS = [f'{b}visits' for b in BANDS]


def remove_high_dec(ra_in, dec_in, dec_lim):
    """Filter out sources above a declination limit.

    Removes coordinates from input arrays where declination exceeds the
    specified limit. Used to exclude sources in the far north from example
    source catalogs to roughly match Rubin Observatory's observing footprint.

    Parameters
    ----------
    ra_in : array-like
        Right ascension values in degrees.
    dec_in : array-like
        Declination values in degrees.
    dec_lim : float
        Declination limit in degrees. Sources with dec >= dec_lim are removed.

    Returns
    -------
    tuple[ndarray, ndarray]
        Filtered (ra, dec) arrays containing only sources with dec < dec_lim.
    """
    return ra_in[dec_in<dec_lim], dec_in[dec_in<dec_lim]

def make_fake_src_list(nside, declim):
    """Generate fake source catalog using HEALPix tessellation.

    Creates a uniform source catalog by placing one source at each HEALPix
    pixel center at a given resolution level. Sources above the declination
    limit are removed to match the Rubin Observatory observing footprint.
    Used for prototyping the dashboard with uniform sky coverage of targets.

    Parameters
    ----------
    nside : int
        HEALPix resolution parameter (must be power of 2). Higher values
        create denser source catalogs.
    declim : float
        Declination limit in degrees. Sources with dec >= declim are excluded.

    Returns
    -------
    tuple[ndarray, ndarray]
        (RA, Dec) coordinates in degrees for all HEALPix pixels below declim.
    """
    idx_list = np.arange(0,hp.nside2npix(nside))

    ra, dec = hp.pix2ang(nside, idx_list, lonlat=True)

    return remove_high_dec(ra.astype(float), 
                           dec.astype(float), declim)

def simulation_dates(sim_start: datetime, sim_end: datetime) -> list[str]:
    """Generate list of simulated survey dates.

    Creates a complete date range from start to end (inclusive) as
    ISO formatted strings. Used for iterating through simulated
    observing nights during the prototyping phase.

    Parameters
    ----------
    sim_start : datetime
        Start date of simulation window.
    sim_end : datetime
        End date of simulation window (inclusive).

    Returns
    -------
    list[str]
        List of YYYY-MM-DD date strings from sim_start to sim_end.
    """
    n_days = (sim_end - sim_start).days + 1
    return [
        (sim_start + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(n_days)
    ]

def date_to_nightnum(date, base_mjd):
    """Convert ISO date string to Rubin night number.

    Converts a date string to Modified Julian Date (MJD) and computes the
    night number relative to the base MJD provided. Night numbering matches
    the convention used by the simulated LSST database.

    Parameters
    ----------
    date : str
        ISO format date string (YYYY-MM-DD).
    base_mjd : float
        Reference MJD for night 0 in the simulation.

    Returns
    -------
    int
        Night number relative to base_mjd (integer part of MJD - base_mjd).
    """
    t = Time(date, scale='utc')
    mjd = t.mjd

    return int(mjd - base_mjd)

def get_base_mjd(sim_lsst_db):
    """Retrieve the base MJD from the simulated LSST database.

    Queries the simulated LSST database to find the minimum observation start
    MJD, which serves as the reference point (night 0) for night numbering.
    This base MJD is used in date_to_nightnum() to convert dates to night
    numbers consistent with the database.

    Parameters
    ----------
    sim_lsst_db : str
        Path to the simulated LSST SQLite database file.

    Returns
    -------
    float
        The minimum observationStartMJD value from the observations table,
        representing the base MJD (night 0).
    """
    conn = sqlite3.connect(sim_lsst_db)
    cursor = conn.cursor()

    # Get the base MJD (minimum value from night 0)
    cursor.execute("SELECT MIN(observationStartMJD) FROM observations")

    return cursor.fetchone()[0]
