"""Tests for pipeline module

Tests the data_loop orchestrator and memory management functions.
External dependencies (database, LSST services, time) are mocked.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, call
from datetime import datetime, timedelta

import rubin_sunrise.collector.pipeline as pipeline


@pytest.fixture
def mock_conn_cur():
    """Mock database connection and cursor."""
    mock_conn = Mock()
    mock_cur = Mock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn, mock_cur


@pytest.fixture
def mock_camera():
    """Mock camera footprint object."""
    return Mock()


@pytest.fixture
def test_visits_df():
    """Sample visits DataFrame for mocking service calls."""
    return pd.DataFrame({
        's_ra': np.array([100.0, 101.0]),
        's_dec': np.array([-30.0, -31.0]),
        'execution_status': np.array(['Performed', 'Performed']),
        'band': np.array(['g', 'r']),
        'rubin_rot_sky_pos': np.array([45.0, 90.0]),
        'obs_id': np.array([1, 2])
    })


# ===== Basic Orchestration Tests =====

def test_data_loop_sim_path_single_cycle(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop processes single SIM cycle correctly."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    # Setting up mocks for SIM path
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'SIM')
    monkeypatch.setattr(pipeline, 'SIM_LSST_DB', '/path/to/db')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)  # No delay for testing
    
    # Mock date sequence
    test_dates = [pd.Timestamp('2026-08-10')]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    # Mock conversions
    monkeypatch.setattr(pipeline, 'get_base_mjd', lambda db: 60000)
    monkeypatch.setattr(pipeline, 'date_to_nightnum', lambda date, mjd: 100)
    
    # Mock service and orchestration functions
    mock_sim_service = Mock(return_value=test_visits_df)
    monkeypatch.setattr(pipeline, 'sim_service', mock_sim_service)
    
    mock_populate_db = Mock()
    monkeypatch.setattr(pipeline, 'populate_database', mock_populate_db)
    
    mock_populate_forecast = Mock()
    monkeypatch.setattr(pipeline, 'populate_forecast', mock_populate_forecast)
    
    # Mock memory and logging
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    # Call data_loop
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify orchestration
    mock_sim_service.assert_called_once_with(100)
    mock_populate_db.assert_called_once()
    mock_populate_forecast.assert_called_once()


def test_data_loop_rsv_path_single_cycle(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop processes single RSV cycle correctly."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    test_dates = [pd.Timestamp('2026-08-10')]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    mock_rsv_service = Mock(return_value=test_visits_df)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    mock_populate_db = Mock()
    monkeypatch.setattr(pipeline, 'populate_database', mock_populate_db)
    
    mock_populate_forecast = Mock()
    monkeypatch.setattr(pipeline, 'populate_forecast', mock_populate_forecast)
    
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    # Call
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify RSV path was called with Timestamp object (not string)
    mock_rsv_service.assert_called_once_with(pd.Timestamp('2026-08-10'))
    mock_populate_db.assert_called_once()
    mock_populate_forecast.assert_called_once()


def test_data_loop_multiple_cycles(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop cycles through multiple dates."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-12'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    # Three dates
    test_dates = [
        pd.Timestamp('2026-08-10'),
        pd.Timestamp('2026-08-11'),
        pd.Timestamp('2026-08-12'),
    ]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    mock_rsv_service = Mock(return_value=test_visits_df)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    mock_populate_db = Mock()
    monkeypatch.setattr(pipeline, 'populate_database', mock_populate_db)
    
    mock_populate_forecast = Mock()
    monkeypatch.setattr(pipeline, 'populate_forecast', mock_populate_forecast)
    
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify 3 cycles
    assert mock_rsv_service.call_count == 3
    assert mock_populate_db.call_count == 3
    assert mock_populate_forecast.call_count == 3
    
    # Verify dates passed in order
    called_dates = [call_args[0][0] for call_args in mock_rsv_service.call_args_list]
    assert called_dates == test_dates


# ===== Data Handling Tests =====

def test_data_loop_handles_empty_visits(mock_conn_cur, mock_camera, monkeypatch):
    """Test data_loop skips populate_database when visits are empty."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    test_dates = [pd.Timestamp('2026-08-10')]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    # Empty DataFrame
    empty_visits = pd.DataFrame()
    mock_rsv_service = Mock(return_value=empty_visits)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    mock_populate_db = Mock()
    monkeypatch.setattr(pipeline, 'populate_database', mock_populate_db)
    
    mock_populate_forecast = Mock()
    monkeypatch.setattr(pipeline, 'populate_forecast', mock_populate_forecast)
    
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify populate_database was NOT called for empty data
    mock_populate_db.assert_not_called()
    mock_populate_forecast.assert_not_called()


def test_data_loop_mixed_empty_and_data(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop handles mix of empty and populated dates."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-12'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    test_dates = [
        pd.Timestamp('2026-08-10'),  # Empty
        pd.Timestamp('2026-08-11'),  # Data
        pd.Timestamp('2026-08-12'),  # Empty
    ]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    # Alternate between empty and populated
    side_effects = [
        pd.DataFrame(),        # Empty for 2026-08-10
        test_visits_df,        # Data for 2026-08-11
        pd.DataFrame(),        # Empty for 2026-08-12
    ]
    mock_rsv_service = Mock(side_effect=side_effects)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    mock_populate_db = Mock()
    monkeypatch.setattr(pipeline, 'populate_database', mock_populate_db)
    
    mock_populate_forecast = Mock()
    monkeypatch.setattr(pipeline, 'populate_forecast', mock_populate_forecast)
    
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify populate was only called once (for the date with data)
    assert mock_populate_db.call_count == 1
    assert mock_populate_forecast.call_count == 1


# ===== Configuration Tests =====

def test_data_loop_uses_provided_db_name(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop uses db_name parameter when provided."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    custom_db_name = 'custom_database'
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    test_dates = [pd.Timestamp('2026-08-10')]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    mock_rsv_service = Mock(return_value=test_visits_df)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    mock_populate_db = Mock()
    monkeypatch.setattr(pipeline, 'populate_database', mock_populate_db)
    
    mock_populate_forecast = Mock()
    monkeypatch.setattr(pipeline, 'populate_forecast', mock_populate_forecast)
    
    mock_log_table = Mock()
    monkeypatch.setattr(pipeline, 'log_table_size', mock_log_table)
    
    mock_monitoring = Mock()
    monkeypatch.setattr(pipeline, 'monitoring_plots_collector', mock_monitoring)
    
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    # Call with log_dir and timestamp to exercise db_name usage
    from pathlib import Path
    log_dir = Path('/tmp/logs')
    
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id,
                      log_dir=log_dir, timestamp='2026-08-10-12-00-00',
                      db_name=custom_db_name)
    
    # Verify log_table_size was called with custom db_name
    mock_log_table.assert_called_once()
    call_kwargs = mock_log_table.call_args.kwargs
    assert call_kwargs['db_name'] == custom_db_name


# ===== Logging & Monitoring Tests =====

def test_data_loop_calls_monitoring_when_log_dir_provided(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop calls logging/monitoring functions when log_dir is set."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    test_dates = [pd.Timestamp('2026-08-10')]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    mock_rsv_service = Mock(return_value=test_visits_df)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    monkeypatch.setattr(pipeline, 'populate_database', Mock())
    monkeypatch.setattr(pipeline, 'populate_forecast', Mock())
    
    mock_log_table = Mock()
    monkeypatch.setattr(pipeline, 'log_table_size', mock_log_table)
    
    mock_monitoring = Mock()
    monkeypatch.setattr(pipeline, 'monitoring_plots_collector', mock_monitoring)
    
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    from pathlib import Path
    log_dir = Path('/tmp/logs')
    timestamp = '2026-08-10-12-00-00'
    
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id,
                      log_dir=log_dir, timestamp=timestamp)
    
    # Verify logging was called
    mock_log_table.assert_called_once()
    mock_monitoring.assert_called_once_with(log_dir, timestamp)


def test_data_loop_skips_monitoring_when_log_dir_none(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop skips logging when log_dir is None."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    test_dates = [pd.Timestamp('2026-08-10')]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    mock_rsv_service = Mock(return_value=test_visits_df)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    monkeypatch.setattr(pipeline, 'populate_database', Mock())
    monkeypatch.setattr(pipeline, 'populate_forecast', Mock())
    
    mock_log_table = Mock()
    monkeypatch.setattr(pipeline, 'log_table_size', mock_log_table)
    
    mock_monitoring = Mock()
    monkeypatch.setattr(pipeline, 'monitoring_plots_collector', mock_monitoring)
    
    monkeypatch.setattr(pipeline, '_reclaim_memory', Mock())
    
    # Call WITHOUT log_dir
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify logging was NOT called
    mock_log_table.assert_not_called()
    mock_monitoring.assert_not_called()


# ===== Memory Management Tests =====

def test_data_loop_calls_reclaim_memory(mock_conn_cur, mock_camera, test_visits_df, monkeypatch):
    """Test data_loop calls _reclaim_memory after each cycle."""
    mock_conn, mock_cur = mock_conn_cur
    user_id = 1
    
    monkeypatch.setattr(pipeline, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(pipeline, 'SIM_START', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(pipeline, 'SIM_END', pd.Timestamp('2026-08-12'))
    monkeypatch.setattr(pipeline, 'REFRESH_INTERVAL', 0)
    
    test_dates = [
        pd.Timestamp('2026-08-10'),
        pd.Timestamp('2026-08-11'),
    ]
    monkeypatch.setattr(pipeline, 'simulation_dates', 
                       lambda start, end: test_dates)
    
    mock_rsv_service = Mock(return_value=test_visits_df)
    monkeypatch.setattr(pipeline, 'rsv_service', mock_rsv_service)
    
    monkeypatch.setattr(pipeline, 'populate_database', Mock())
    monkeypatch.setattr(pipeline, 'populate_forecast', Mock())
    
    mock_reclaim = Mock()
    monkeypatch.setattr(pipeline, '_reclaim_memory', mock_reclaim)
    
    pipeline.data_loop(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify _reclaim_memory called once per cycle
    assert mock_reclaim.call_count == 2
