"""
observability.py: Calculate target observability and elevation tracking.

This module computes when astronomical targets are observable from the Vera
C. Rubin Observatory given their celestial coordinates. Observability is
determined by source elevation angle and night/day constraints. Functions 
provide both summary statistics (hours observable per night) and zoomed-in 
time series (elevation vs. time) for target visualization and forecasting.

Public API
----------
- ``get_az_el`` - Calculate azimuth and elevation arrays for targets.
- ``daily_observability`` - Calculate hours source is observable per night.
- ``el_vs_time`` - Calculate elevation versus time series for visualization.

**Author:** Anna Ordog, for CanDIAPL
"""
from astropy.time import Time
from astropy import coordinates as coord
from astropy import units as u
import numpy as np
import ephem

from rubin_sunrise.config import LOC, DT

def _get_sunrise_sunset(obs, day):
    """Calculate sunset and sunrise times for a given day.

    Computes the sunset and sunrise times for a specified date at Rubin
    location defined by the observer object. Sunset is computed from the 
    previous day to ensure it occurs before sunrise on the current day.

    Parameters
    ----------
    obs : ephem.Observer
        Observatory location and observer object from pyephem.
    day : str or datetime
        Query date (ISO format string or datetime object).

    Returns
    -------
    tuple of (datetime, datetime)
        (sunset, sunrise) where:
        - sunset : Datetime of the sunset before the given day
        - sunrise : Datetime of the sunrise on the given day
    """

    start_date = Time(day).iso
    
    # Get sunset on previous day to ensure sunset is before sunrise:
    obs.date = str(Time(start_date, format="iso", scale="utc") - 1*u.day)
    sunset  = obs.next_setting(ephem.Sun()).datetime()

    # Get sunrise on this day:
    obs.date = str(start_date)
    sunrise = obs.next_rising(ephem.Sun()).datetime()

    return sunset, sunrise

def get_az_el(ra_arr, dec_arr, day):
    """Calculate azimuth and elevation for targets over a night.

    Computes azimuth and altitude (elevation) angles for one or more targets
    as a function of time throughout a night. Uses 5-minute time sampling to
    generate accurate trajectories. Results are suitable for passing directly
    to daily_observability() for hours calculation.

    Parameters
    ----------
    ra_arr : float or np.ndarray
        Target right ascension(s) in degrees. Can be scalar or array.
    dec_arr : float or np.ndarray
        Target declination(s) in degrees. Can be scalar or array.
    day : str or datetime
        Query date (ISO format string or datetime object).

    Returns
    -------
    tuple of (np.ndarray, np.ndarray, astropy.time.Time)
        (az, el, t_utc) where:
        - az : Azimuth angles (degrees)
        - el : Elevation angles (degrees)
        - t_utc : astropy.time.Time array for corresponding times

    Notes
    -----
    - Time sampling interval is 5 minutes
    - Results are broadcast for vectorized computation: shape (N targets, M times)
    - Observatory location is defined by LOC in config.py
    """

    start_date = Time(day).iso

    # Set up time array:
    dmjd_arr = np.arange(-1, 1+DT/24., DT/24.) * u.day
    t_utc = Time(start_date, format="iso", scale="utc") + dmjd_arr

    c = coord.SkyCoord(ra_arr, dec_arr, frame='icrs', unit='deg')

    # Broadcast: coords shape (N, 1), times shape (1, M)  -> result shape (N, M)
    altaz_frame = coord.AltAz(obstime=t_utc[np.newaxis, :], location=LOC)
    result = c[:, np.newaxis].transform_to(altaz_frame)

    return result.az.deg, result.alt.deg, t_utc

def daily_observability(el_t, day, t_utc):
    """Calculate hours a target is observable during a night.

    Computes the duration for which a target is above the minimum elevation
    threshold (15 degrees) during nighttime (between sunset and sunrise) on
    a given date. Uses 5-minute time sampling for accuracy.

    Parameters
    ----------
    el_t : float
        Target elevation in degrees.
    day : str or datetime
        Query date (ISO format string or datetime object).
    t_utc : array of time values for the day (from `get_az_el`)

    Returns
    -------
    float
        Observable hours during the night (decimal hours). Returns 0 if
        target never rises above 15 degrees during nighttime.

    Notes
    -----
    - Minimum elevation cutoff is fixed at 15 degrees
    - Nighttime is defined as time between sunset and next day sunrise
    - Observatory location is defined by LOC in config.py
    """

    # Set up observer object and populate:
    obs = ephem.Observer()
    obs.lon  = str(LOC.geodetic.lon.deg) #Note that lon should be string
    obs.lat  = str(LOC.geodetic.lat.deg) #Note that lat should be string
    obs.elev = LOC.geodetic.height.value

    # Get sunrise and sunset:
    sunset, sunrise = _get_sunrise_sunset(obs, day)

    # Determine when source is between sunset and sunrise and above min el:
    idx_count = np.where((Time(t_utc).mjd>Time(sunset).mjd) & 
                         (Time(t_utc).mjd<Time(sunrise).mjd) & 
                         (el_t>15))[0]
    if len(idx_count) > 0:
        hrs = len(idx_count)*DT
    else:
        hrs = 0.0

    return hrs

def el_vs_time(ra_t, dec_t, day):
    """Calculate elevation versus time for target visualization.

    Computes target elevation (altitude) as a function of time over a 5-day
    window, along with sunrise/sunset times for display of day/night regions.
    Useful for visualizing the sky positions giving rise to the observability
    hours reported by daily_observability.

    Parameters
    ----------
    ra_t : float
        Target right ascension in degrees.
    dec_t : float
        Target declination in degrees.
    day : str or datetime
        Reference date for start of observation window (ISO format string or
        datetime object).

    Returns
    -------
    tuple
        (t_utc, el, sunrise_list, sunset_list) where:
        - t_utc : astropy.time.Time array
            Times at which elevation is computed (5+ days, DT-min intervals).
        - el : np.ndarray
            Elevation angles (degrees) corresponding to t_utc times.
        - sunrise_list : list
            Sunrise times (datetime) for each day in the window.
        - sunset_list : list
            Sunset times (datetime) for each day in the window.

    Notes
    -----
    - Time sampling interval is DT from config.py
    - Window covers 5 days from the reference date
    - Observatory location is defined by LOC in config.py
    """
    ##### Constants - eventually convert to inputs ####
    Ndays = 5.0  # days

    start_date = Time(day).iso

    ##### 1) Data for tracking the target #####

    # Set up time array (expand 1 day beyond range):
    dmjd_arr = np.arange(0, Ndays+1+DT/24., DT/24.)*u.day
    t_utc = Time(start_date, format="iso", scale="utc") + dmjd_arr

    # Get alt/az coords of target vs time:
    c = coord.SkyCoord(ra_t, dec_t, frame='icrs', unit='deg')
    aa_frame = coord.AltAz(obstime = t_utc, location = LOC)
    c_altaz  = c.transform_to(aa_frame)
    az = c_altaz.az.deg.copy()
    az[az > 180.] = az[az > 180.] - 360.
    el  = c_altaz.alt.deg

    ##### 2) Data for tracking sunrise/sunset #####
    
    # Set up array of days (expand 1 day beyond range):
    days_mjd = np.arange(0, Ndays+1.0, 1.0)
    days_utc = Time(start_date, format="iso", scale="utc") + days_mjd*u.day

    # Set up observer object and populate:
    obs = ephem.Observer()
    obs.lon  = str(LOC.geodetic.lon.deg) #Note that lon should be string
    obs.lat  = str(LOC.geodetic.lat.deg) #Note that lat should be string
    obs.elev = LOC.geodetic.height.value

    # Loop through days to get sunrise and sunset times:
    sunrise_list = []
    sunset_list  = []

    for i in range(0,len(days_utc)):

        sunset, sunrise = _get_sunrise_sunset(obs, days_utc[i])
        sunrise_list.append(sunrise)
        sunset_list.append(sunset)

    return t_utc, el, sunrise_list, sunset_list
