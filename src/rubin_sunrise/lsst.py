"""
lsst.py: Access LSST Schedule Viewer and camera footprint data.

This module provides an interface to real (Rubin Schedule Viewer; RSV service)
or simulated (SIM_LSST_DB) databases, and LSST camera geometry data. It 
enables queries for completed visits at specific sky coordinates and provides 
camera footprint for 2D visits maps.

Public API
----------
- ``rsv_service`` - Query Rubin Schedule Viewer for observations.
- ``sim_service`` - Query simulated LSST database for observations.
- ``sim_service_range`` - Bulk query for observation range from simulated DB.
- ``get_visit_metadata`` - Extract visit metadata for a target position.
- ``get_camera`` - Load LSST camera footprint geometry.

**Author:** Anna Ordog, for CanDIAPL
"""

import numpy as np
import pandas as pd
import requests
import sqlite3

from rubin_sunrise.config import SIM_LSST_DB


def _target_visits_idxs(ra_t: float,
                        dec_t: float,
                        r_ang: float,
                        ra: np.ndarray,
                        dec: np.ndarray,
                        status: np.ndarray) -> np.ndarray:
    """Find visit indices within angular distance of target.

    Computes angular distance from a target position to all visits,
    accounting for declination effects on RA distance. Returns indices
    of visits that are within the search radius and have been performed.

    Parameters
    ----------
    ra_t : float
        Target right ascension in degrees.
    dec_t : float
        Target declination in degrees.
    r_ang : float
        Search radius in degrees.
    ra : np.ndarray
        Array of visit right ascensions in degrees.
    dec : np.ndarray
        Array of visit declinations in degrees.
    status : np.ndarray
        Array of visit execution status strings.

    Returns
    -------
    np.ndarray
        Indices of visits within r_ang of target with status=='Performed'.

    """
    dist = np.sqrt(
        ((ra_t - ra) * np.cos(dec_t * np.pi / 180.))** 2 +
        (dec_t - dec ) ** 2
    )
    return np.array(
        np.where((dist < r_ang) & (status == 'Performed'))[0]
    )

def _em_min_max_to_band(em_min, em_max):
    """
    Convert the wavelength minimum and maximum to band name.
    From RSP tutorial: Commissioning/102_Rubin_Schedule_Viewer.ipynb

    Parameters
    ----------
    em_min: float
        Wavelength minimum, in m.
    em_max: float
        Wavelength maximum, in m.

    Returns
    -------
    band: string
        Band (filter) name.
    """

    band = None
    band_dict = {'u': (2.95e-7, 4.05e-7), 'g': (4.00e-7, 5.55e-7),
                 'r': (5.50e-7, 6.92e-7), 'i': (6.90e-7, 8.20e-7),
                 'z': (8.15e-7, 9.25e-7), 'y': (9.20e-7, 11.1e-7)}
    for b in band_dict.keys():
        if em_min > band_dict[b][0] and em_max < band_dict[b][1]:
            band = b
    #if band is None:
    #    print(em_min, em_max, ' no band found')

    return band

def rsv_service(date: str) -> pd.DataFrame:
    """Query Rubin Schedule Viewer for observation visits.

    Retrieves scheduled observation data from the Rubin Schedule Viewer (RSV) 
    service for a specified date. The service returns visit information 
    including sky coordinates, execution status and bands for visits.

    Parameters
    ----------
    date : str
        Query date in ISO format expected by RSV service.

    Returns
    -------
    pd.DataFrame
        Observation visit data with columns: s_ra, s_dec, execution_status, 
        obs_id, and others from RSV. Also includes derived variable, 'band'

    Raises
    ------
    AssertionError
        If the HTTP request to RSV service fails (status != 200).

    Notes
    -----
    The RSV service is hosted at SLAC's Data Facility. Requires internet 
    connectivity to the USDF service endpoint.

    """
    # Define search parameters from inputs
    params = {"time": "24", "start": date}

    # Define the ObsLocTAP URL of the service:
    obsloctap_url = "https://usdf-rsp.slac.stanford.edu/obsloctap"

    # Define the schedule URL and connect to it using requests package:
    schedule_url = obsloctap_url + "/schedule"
    response = requests.get(schedule_url, params=params)

    # Assert that the service is alive:
    assert response.status_code == 200, (
        f"request failed with status {response.status_code}"
    )
    print(f"Rubin Schedule Forecast at {response.url} is alive.")
    print(response.url)

    # Calculate bands using RSP function and add this to dataframe:
    visits = pd.DataFrame(response.json())
    bands = []
    for i in range(0,len(visits)):
        bands.append(_em_min_max_to_band(visits['em_min'][i], 
                                         visits['em_max'][i]))
    visits['band'] = bands

    return visits

def sim_service(nightnum):
    """Query simulated LSST database for observation visits on a night.

    Retrieves observation data for a single night from the simulated LSST
    database (SIM_LSST_DB). Returns visit information including sky
    coordinates, rotation angles, and filter bands.

    Parameters
    ----------
    nightnum : int
        Night number identifying the observation night in the database.

    Returns
    -------
    pd.DataFrame
        Observation visit data with columns: s_ra, s_dec, rot, band, obs_id,
        execution_status. Returns empty DataFrame if no observations found.

    Notes
    -----
    Designed for querying individual nights. For bulk queries of multiple
    nights, use sim_service_range() for better efficiency.
    """
    visits = {}

    conn_sim = sqlite3.connect(SIM_LSST_DB)
    cursor = conn_sim.cursor()
    cursor.execute("""
                   SELECT fieldRA, fieldDec, rotSkyPos, filter, observationID FROM observations WHERE night = ?
                   """, (nightnum,))
    rows = cursor.fetchall()

    if len(rows) > 0:

        ra, dec, rot, band, obs_id = [np.array(x) for x in zip(*rows)]

        visits["s_ra"]              = ra
        visits["s_dec"]             = dec
        visits["rubin_rot_sky_pos"] = rot
        visits["band"]              = band
        visits["obs_id"]            = obs_id
        visits["execution_status"]  = ['Performed']*len(ra)
    
    return pd.DataFrame(visits)

def sim_service_range(min_night: int, max_night: int) -> dict:
    """Query all observations for a range of nights from SIM_LSST_DB.

    Efficiently retrieves observation data for all nights in a range in a 
    single database query, organizing results by night number. This is about a
    factor of 2 faster than calling sim_service() repeatedly for each night 
    when populating historical data.

    Parameters
    ----------
    min_night : int
        Minimum night number (inclusive).
    max_night : int
        Maximum night number (inclusive).

    Returns
    -------
    dict
        Dictionary keyed by night number, where each value is a pd.DataFrame
        containing observations for that night with columns: s_ra, s_dec, rot,
        band, obs_id, execution_status. Returns empty dict if no observations 
        found in range.

    Notes
    -----
    Opens database connection once for the entire range, which has been 
    observed to be a factor of 2 more efficient than repeated connections for 
    individual nights.
    """
    visits_by_night = {}

    conn_sim = sqlite3.connect(SIM_LSST_DB)
    cursor = conn_sim.cursor()
    cursor.execute("""
        SELECT night, fieldRA, fieldDec, rotSkyPos, filter, observationID 
        FROM observations 
        WHERE night >= ? AND night <= ?
        ORDER BY night
    """, (min_night, max_night))
    rows = cursor.fetchall()
    conn_sim.close()

    if len(rows) > 0:
        # Group rows by night number
        current_night = None
        night_data = {}
        
        for row in rows:
            night, ra, dec, rot, band, obs_id = row
            
            if night != current_night:
                # New night encountered
                if current_night is not None:
                    # Save the previous night's data
                    visits_by_night[current_night] = _create_visits_df(night_data)
                current_night = night
                night_data = {
                    'ra': [],
                    'dec': [],
                    'rot': [],
                    'band': [],
                    'obs_id': []
                }
            
            # Append to current night's data
            night_data['ra'].append(ra)
            night_data['dec'].append(dec)
            night_data['rot'].append(rot)
            night_data['band'].append(band)
            night_data['obs_id'].append(obs_id)
        
        # Don't forget the last night
        if current_night is not None:
            visits_by_night[current_night] = _create_visits_df(night_data)

    return visits_by_night

def _create_visits_df(night_data: dict) -> pd.DataFrame:
    """Helper function to create a visits DataFrame from night data.

    Parameters
    ----------
    night_data : dict
        Dictionary with keys 'ra', 'dec', 'rot', 'band', 'obs_id', 
        each containing lists of values.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: s_ra, s_dec, rot, band, obs_id, execution_status.

    """
    visits = {}
    visits["s_ra"]              = np.array(night_data['ra'])
    visits["s_dec"]             = np.array(night_data['dec'])
    visits["rubin_rot_sky_pos"] = np.array(night_data['rot'])
    visits["band"]              = np.array(night_data['band'])
    visits["obs_id"]            = np.array(night_data['obs_id'])
    visits["execution_status"]  = ['Performed'] * len(night_data['ra'])
    
    return pd.DataFrame(visits)

def get_visit_metadata(visits,
                     ra_t: float,
                     dec_t: float):
    """Extract visit metadata for a target position from an LSST database.

    Filters observation visits to find those within a 3-degree search radius
    of the target coordinates. Extracts RA, Dec, band, and rotation angle
    for matching visits.

    Parameters
    ----------
    visits : dict or pd.DataFrame
        Visit data from rsv_service(), sim_service(), or sim_service_range().
    ra_t : float
        Target right ascension in degrees.
    dec_t : float
        Target declination in degrees.

    Returns
    -------
    dict
        Dictionary with keys:
        - 'ra': float array of visit RA values for target
        - 'dec': float array of visit Dec values for target
        - 'band': array of camera filters
        - 'rot': array of camera rotation angles

    Notes
    -----
    Search radius is fixed at 3.0 degrees. Only visits with 
    execution_status == 'Performed' are included. Uses helper
    _target_visits_idxs to identify matching visits.

    """
    r = 3.0
    ra = np.array(visits["s_ra"])
    dec = np.array(visits["s_dec"])
    status = np.array(visits["execution_status"])
    obs_id = visits["obs_id"]

    idxs = _target_visits_idxs(ra_t, dec_t, r, ra, dec, status)

    visits_use = {}
    visits_use['ra']   = ra[idxs]
    visits_use['dec']  = dec[idxs]
    visits_use['band'] = np.array(visits["band"])[idxs]
    visits_use['rot']  = np.array(visits["rubin_rot_sky_pos"])[idxs]

    return visits_use

def get_camera():
    """Load LSST camera footprint geometry.

    Initializes and returns the LSST camera footprint object from
    rubin_scheduler. The footprint defines the instrument's field of
    view and detector geometry.

    Returns
    -------
    rubin_scheduler.utils.LsstCameraFootprint
        Camera footprint object with units='degrees'.

    Notes
    -----
    Requires rubin_scheduler package.

    """
    from rubin_scheduler.utils import (LsstCameraFootprint,
                                       _angular_separation)
    print('Getting camera')
    camera = LsstCameraFootprint(units='degrees',
                                 footprint_file='fov_map.npz')

    return camera