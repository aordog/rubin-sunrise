"""Tests for lsst module"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch
import rubin_sunrise.collector.lsst as lsst

@pytest.mark.parametrize(
    "ra_t, dec_t, r_ang, ra, dec, status, expected_indices",
    [
        # Same position: distance = 0
        (0.0, 0.0, 1.0, 
         np.array([0.0]), np.array([0.0]), np.array(['Performed']), 
         np.array([0])),
        
        # Pure RA difference at equator: 1 deg away (within 2 deg radius)
        (0.0, 0.0, 2.0, 
         np.array([1.0]), np.array([0.0]), np.array(['Performed']), 
         np.array([0])),
        
        # Pure RA difference at equator: 3 deg away (outside 2 deg radius)
        (0.0, 0.0, 2.0, 
         np.array([3.0]), np.array([0.0]), np.array(['Performed']), 
         np.array([])),
        
        # Check for not performed observations
        (0.0, 0.0, 2.0, 
         np.array([1.0]), np.array([0.0]), np.array(['Unperformed']), 
         np.array([])),
        
        # Multiple targets: mix of inside/outside and performed/not
        (0.0, 0.0, 1.5,
         np.array([0.5, 2.0, 0.8]), np.array([0.0, 0.0, 0.0]),
         np.array(['Performed', 'Performed', 'Not Performed']),
         np.array([0])),  # Only index 0 is within radius AND performed

        # High declination
        (0.0, 60.0, 2.0,
         np.array([3.0]), np.array([60.0]), np.array(['Performed']), 
         np.array([0])),
    ],
    ids=["same_position", "within_radius", "outside_radius", 
         "wrong_status", "mixed", "high_dec"]
)
def test_target_visits_idxs(ra_t, dec_t, r_ang, ra, dec, 
                            status, expected_indices):
    """Test that _target_visits_idxs returns correct indices."""

    result = lsst._target_visits_idxs(ra_t, dec_t, r_ang, ra, dec, status)

    assert np.array_equal(result, expected_indices), \
        f"Expected indices {expected_indices}, got {result}"

@pytest.mark.parametrize(
    "em_min, em_max, expected_band",
    [
        (3.0e-7, 4.0e-7, 'u'),
        (4.5e-7, 5.5e-7, 'g'),
        (6.0e-7, 6.7e-7, 'r'),
        (7.0e-7, 8.0e-7, 'i'),
        (8.5e-7, 9.0e-7, 'z'),
        (9.5e-7, 11.0e-7, 'y'),
        (2.0e-7, 2.1e-7, None), # outside bands   
    ],
    ids=["u", "g", "r", "i", "z", "y", "outside"]
)
def test_em_min_max_to_band(em_min, em_max, expected_band):
    """Test that _em_min_max_to_band returns correct bands."""

    band_actual = lsst._em_min_max_to_band(em_min, em_max)

    assert band_actual == expected_band, \
        f"Expected band {expected_band}, got {band_actual}"

@pytest.mark.parametrize(
    "ra_t, dec_t, visits_input, expected_count",
    [
        # All visits within 3 deg radius
        (0.0, 0.0, 
         {'s_ra': np.array([1.0, 2.0]), 'execution_status': np.array(['Performed', 'Performed']),
          's_dec': np.array([0.0, 0.0]), 'band': np.array(['g', 'i']), 
          'rubin_rot_sky_pos': np.array([45.0, 90.0]), 'obs_id': np.array([1, 2])},
         2),
        
        # One visit within, one outside 3 deg radius
        (0.0, 0.0,
         {'s_ra': np.array([1.0, 5.0]), 'execution_status': np.array(['Performed', 'Performed']),
          's_dec': np.array([0.0, 0.0]), 'band': np.array(['g', 'i']), 
          'rubin_rot_sky_pos': np.array([45.0, 90.0]), 'obs_id': np.array([1, 2])},
         1),
        
        # Filter by status (unperformed visits excluded)
        (0.0, 0.0,
         {'s_ra': np.array([1.0, 2.0]), 'execution_status': np.array(['Performed', 'Unperformed']),
          's_dec': np.array([0.0, 0.0]), 'band': np.array(['g', 'i']), 
          'rubin_rot_sky_pos': np.array([45.0, 90.0]), 'obs_id': np.array([1, 2])},
         1),
        
        # No visits in radius
        (0.0, 0.0,
         {'s_ra': np.array([10.0]), 'execution_status': np.array(['Performed']),
          's_dec': np.array([0.0]), 'band': np.array(['g']), 
          'rubin_rot_sky_pos': np.array([45.0]), 'obs_id': np.array([1])},
         0),
    ],
    ids=["all_within", "mixed", "filter_status", "none_in_radius"]
)
def test_get_visit_metadata(ra_t, dec_t, visits_input, expected_count):
    """Test that get_visit_metadata correctly filters and extracts visits."""
    
    result = lsst.get_visit_metadata(visits_input, ra_t, dec_t)
    
    assert len(result['ra']) == expected_count, \
        f"Expected {expected_count} visits, got {len(result['ra'])}"
    assert len(result['dec']) == expected_count, \
        f"Dec array length mismatch: expected {expected_count}, got {len(result['dec'])}"
    assert len(result['band']) == expected_count, \
        f"Band array length mismatch: expected {expected_count}, got {len(result['band'])}"
    assert len(result['rot']) == expected_count, \
        f"Rotation array length mismatch: expected {expected_count}, got {len(result['rot'])}"

def test_rsv_service_with_mocked_request(monkeypatch):
    """Test rsv_service correctly parses response and adds bands."""
    
    # Mock the requests.get response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.url = "https://test.url"
    mock_response.json.return_value = [
        {'em_min': 3.5e-7, 'em_max': 3.9e-7, 's_ra': 100.0, 's_dec': -30.0, 'obs_id': 1},
        {'em_min': 4.2e-7, 'em_max': 5.2e-7, 's_ra': 101.0, 's_dec': -30.5, 'obs_id': 2},
        {'em_min': 6.0e-7, 'em_max': 6.5e-7, 's_ra': 102.0, 's_dec': -31.0, 'obs_id': 3},
    ]
    
    mock_get = Mock(return_value=mock_response)
    monkeypatch.setattr('requests.get', mock_get)
    
    # Call rsv_service
    result = lsst.rsv_service('2026-05-16')
    
    # Verify requests.get was called with correct parameters
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert 'params' in call_args.kwargs
    assert call_args.kwargs['params']['start'] == '2026-05-16'
    
    # Verify result is a DataFrame with expected data
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 3
    assert 'band' in result.columns
    
    # Verify bands were correctly assigned
    assert result['band'].iloc[0] == 'u'  # em_min=3.5e-7, em_max=3.9e-7 -> 'u'
    assert result['band'].iloc[1] == 'g'  # em_min=4.2e-7, em_max=5.2e-7 -> 'g'
    assert result['band'].iloc[2] == 'r'  # em_min=6.0e-7, em_max=6.5e-7 -> 'r'


def test_rsv_service_request_failure(monkeypatch):
    """Test rsv_service raises AssertionError on failed HTTP request."""
    
    # Mock failed response
    mock_response = Mock()
    mock_response.status_code = 404
    
    mock_get = Mock(return_value=mock_response)
    monkeypatch.setattr('requests.get', mock_get)
    
    # Verify AssertionError is raised
    with pytest.raises(AssertionError, match="request failed with status 404"):
        lsst.rsv_service('2026-05-16')


def test_get_camera():
    """Test get_camera initializes LsstCameraFootprint with correct parameters."""
    
    # Mock the camera footprint class and import
    mock_camera = Mock()
    mock_camera_class = Mock(return_value=mock_camera)
    
    # Mock the rubin_scheduler import
    mock_rubin_scheduler = Mock()
    mock_rubin_scheduler.LsstCameraFootprint = mock_camera_class
    
    # Use patch to mock the import within the lsst module
    def mock_import_side_effect(name, *args, **kwargs):
        if 'rubin_scheduler' in name:
            return mock_rubin_scheduler
        return __import__(name, *args, **kwargs)
    
    with patch('builtins.__import__', side_effect=mock_import_side_effect):
        result = lsst.get_camera()
    
    # Verify LsstCameraFootprint was called with correct parameters
    mock_camera_class.assert_called_once_with(
        units='degrees',
        footprint_file='fov_map.npz'
    )
    
    # Verify it returns the camera object
    assert result == mock_camera

@pytest.mark.integration
def test_rsv_service_visits():
    """Test that RSV service returns expected data format.
    
    This is an integration test that verifies the external Rubin Schedule
    Viewer service is accessible and returns results matching a reference
    test file. It requires internet connectivity.
    """

    test_date = '2026-05-16'
    test_data = pd.read_csv(f'tests/test_rsv_{test_date}.csv')

    bands_expected = []
    for i in range(0,len(test_data)):
        bands_expected.append(lsst._em_min_max_to_band(test_data['em_min'][i], 
                                                       test_data['em_max'][i]))
    bands_expected = ['nan' if x is None else x for x in bands_expected]

    bands_actual =list(lsst.rsv_service(test_date)['band'])
    bands_actual_str = [str(element) for element in bands_actual]

    assert bands_actual_str == bands_expected, \
        f"Expected {bands_expected[0:5]}..., got {bands_actual_str[0:5]}..."

#@pytest.mark.parametrize(
#    "",
#    [
#        (),
#        (), 
#    ],
#    ids=[]
#)
#def test___():
#    """Test that ."""

#    band_actual = _em_min_max_to_band(em_min, em_max)

#    assert band_actual == expected_band, \
#        f"Expected band {expected_band}, got {band_actual}"