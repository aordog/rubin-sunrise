"""Tests for observability module"""

import pytest
import ephem
import numpy as np
from astropy.time import Time
from rubin_sunrise.config import LOC
from rubin_sunrise.observability import (get_az_el, 
                                        _get_sunrise_sunset, 
                                        daily_observability,
                                        el_vs_time)

@pytest.mark.parametrize(
    "ra, dec, day, expected_max_el, expected_min_el",
    [
        # Test 1: Observer's location should reach zenith (90°)
        # max_el = 90° - |lat - dec| = 90°
        # min_el = -29,51074
        (LOC.lon.deg, LOC.lat.deg, "2025-06-21", 90.0, -29.51074),
        
        # Test 2: Target far south (near south pole, always visible)
        # max_el = 90° - |(-30.24463) - (-80)| = 40.24463°
        # min_el = 20.24463
        (0.0, -80.0, "2025-06-21", 40.24463, 20.24463),
        
        # Test 3: Northern target 30° away in declination
        # max_el = 90° - |(-30.24463) - 0°| = 59.75537°
        # min_el = -59.75537
        (0.0, 0.0, "2025-06-21", 59.75537, -59.75537),
        
        # Test 4: Southern target also 30° away (equidistant from Rubin)
        # max_el = 90° - |(-30.24463) - (-60)| = 60.24463°
        # min_el = 0.24463
        (0.0, -60.0, "2025-06-21", 60.24463, 0.24463),
    ],
    ids=["zenith", "circumpolar", "northern_target", "southern_target"]
)
def test_get_az_el_minmax_elevation(ra, dec, day, expected_max_el, expected_min_el):
    """Test that maximum elevation matches astronomical principles."""
    
    # Ensure inputs are arrays (get_az_el expects array inputs)
    ra_arr = np.atleast_1d(ra)
    dec_arr = np.atleast_1d(dec)
    
    az, el, _ = get_az_el(ra_arr, dec_arr, day)
    actual_max_el = np.max(el)
    actual_min_el = np.min(el)
    
    assert np.isclose(actual_max_el, expected_max_el, atol=0.5), \
        f"Expected max elevation ~{expected_max_el}°, got {actual_max_el}°"
    assert np.isclose(actual_min_el, expected_min_el, atol=0.5), \
        f"Expected min elevation ~{expected_min_el}°, got {actual_min_el}°"

@pytest.mark.parametrize(
    "n_targets, day",
    [
        (1, "2025-06-21"),
        (2, "2025-06-21"),
        (4, "2025-06-21"),
        (10, "2025-06-21"),
    ],
    ids=["one", "two", "four", "ten"]
)
def test_get_az_el_shape(n_targets, day):
    """Test that output shapes are correct for different input sizes."""
    
    ra = np.linspace(0, 360, n_targets, endpoint=False)
    dec = np.full(n_targets, -30.0)
    
    az, el, t_utc = get_az_el(ra, dec, day)
    
    assert az.shape[0] == n_targets
    assert el.shape[0] == n_targets
    assert az.shape[1] == len(t_utc)
    assert el.shape[1] == len(t_utc)

@pytest.mark.parametrize(
    "day",
    [
        ("2025-06-21"),
        ("2025-12-21"),
    ],
    ids=["June","December"]
)
def test_get_sunrise_sunset(day):
    """Test that sunset occurs before sunrise"""
    obs = ephem.Observer()
    obs.lon  = str(LOC.geodetic.lon.deg) #Note that lon should be string
    obs.lat  = str(LOC.geodetic.lat.deg) #Note that lat should be string
    obs.elev = LOC.geodetic.height.value

    sunset, sunrise = _get_sunrise_sunset(obs, day)
    
    assert Time(sunset).mjd < Time(sunrise).mjd, \
        f"Sunset {sunset} later than sunrise {sunrise}"  

@pytest.mark.parametrize(
    "ra, dec, day, expected_hrs",
    [
        # Test 1: Target far south at equinox
        (0.0, -80.0, "2025-03-21", 12.0),
        
        # Test 2: High dec target always below horizon
        (0.0, 50.0, "2025-06-21", 0.0),
        
        # Test 3: Target far south at June solstice (more than 14 hrs)
        (0.0, -80.0, "2025-06-21", 14.0),

        # Test 4: Target far south at June solstice (less than 10 hrs)
        (0.0, -80.0, "2025-12-21", 10.0),
    ],
    ids=["equinox", "high_dec", "Jun_solstice", "Dec_solstice"]
)
def test_daily_observability(ra, dec, day, expected_hrs):
    """Test expected number of observable hours."""
    
    # Ensure inputs are arrays (get_az_el expects array inputs)
    ra_arr = np.atleast_1d(ra)
    dec_arr = np.atleast_1d(dec)

    az, el, t_utc = get_az_el(ra_arr, dec_arr, day)
    actual_hrs = daily_observability(el, day, t_utc)
    
    assert np.isclose(actual_hrs, expected_hrs, atol=0.5), \
        f"Expected hours ~{expected_hrs}, got {actual_hrs}"

@pytest.mark.parametrize(
    "day",
    [
        ("2025-06-21"),
        ("2025-12-21"),
    ],
    ids=["June","December"]
)
def test_el_vs_time_sunrise_sunset(day):
    """Test that sunset occurs before sunrise for all 5 days displayed"""

    t_utc, el, sunrise_list, sunset_list = el_vs_time(180.0, -20.0, day)

    for i in range(0,len(sunrise_list)):
        assert Time(sunset_list[i]).mjd < Time(sunrise_list[i]).mjd, \
            f"Sunset {sunset_list[i]} later than sunrise {sunrise_list[i]}"

@pytest.mark.parametrize(
    "ra, dec, day, expected_max_el, expected_min_el",
    [
        # Test 1: Observer's location should reach zenith (90°)
        # max_el = 90° - |lat - dec| = 90°
        # min_el = -29,51074
        (LOC.lon.deg, LOC.lat.deg, "2025-06-21", 90.0, -29.51074),
        
        # Test 2: Target far south (near south pole, always visible)
        # max_el = 90° - |(-30.24463) - (-80)| = 40.24463°
        # min_el = 20.24463
        (0.0, -80.0, "2025-06-21", 40.24463, 20.24463),
        
        # Test 3: Northern target 30° away in declination
        # max_el = 90° - |(-30.24463) - 0°| = 59.75537°
        # min_el = -59.75537
        (0.0, 0.0, "2025-06-21", 59.75537, -59.75537),
        
        # Test 4: Southern target also 30° away (equidistant from Rubin)
        # max_el = 90° - |(-30.24463) - (-60)| = 60.24463°
        # min_el = 0.24463
        (0.0, -60.0, "2025-06-21", 60.24463, 0.24463),
    ],
    ids=["zenith", "circumpolar", "northern_target", "southern_target"]
)
def test_el_vs_time_minmax_elevation(ra, dec, day, expected_max_el, expected_min_el):
    """Test that maximum elevation matches astronomical principles.
    Note: max el across 5 days should be similar - this test will fail if
    Ndays is much bigger than 5."""
    
    t_utc, el, sunrise_list, sunset_list = el_vs_time(ra, dec, day)
    actual_max_el = np.nanmax(el)
    actual_min_el = np.nanmin(el)
    
    assert np.isclose(actual_max_el, expected_max_el, atol=0.5), \
        f"Expected max elevation ~{expected_max_el}°, got {actual_max_el}°"
    assert np.isclose(actual_min_el, expected_min_el, atol=0.5), \
        f"Expected min elevation ~{expected_min_el}°, got {actual_min_el}°"