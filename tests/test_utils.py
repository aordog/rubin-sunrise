"""Tests for utils module

Tests utility functions for date handling and database queries.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import rubin_sunrise.collector.utils as utils


# ===== simulation_dates tests =====

class TestSimulationDates:
    """Tests for simulation_dates() function."""
    
    def test_single_day(self):
        """Test simulation_dates with start == end."""
        start = pd.Timestamp('2026-08-10')
        end = pd.Timestamp('2026-08-10')
        
        result = utils.simulation_dates(start, end)
        
        assert len(result) == 1
        assert result[0] == '2026-08-10'
    
    def test_consecutive_days(self):
        """Test simulation_dates with 3 consecutive days."""
        start = pd.Timestamp('2026-08-10')
        end = pd.Timestamp('2026-08-12')
        
        result = utils.simulation_dates(start, end)
        
        assert len(result) == 3
        assert result[0] == '2026-08-10'
        assert result[1] == '2026-08-11'
        assert result[2] == '2026-08-12'
    
    def test_date_format(self):
        """Verify dates are in ISO format (YYYY-MM-DD)."""
        start = pd.Timestamp('2026-03-15')
        end = pd.Timestamp('2026-03-17')
        
        result = utils.simulation_dates(start, end)
        
        for date_str in result:
            # Verify format and that it can be parsed
            parts = date_str.split('-')
            assert len(parts) == 3
            assert len(parts[0]) == 4  # YYYY
            assert len(parts[1]) == 2  # MM
            assert len(parts[2]) == 2  # DD
    
    def test_leap_year(self):
        """Test simulation_dates crossing February 28/29 in a leap year."""
        # 2024 is a leap year, test Feb 28 - Mar 1
        start = pd.Timestamp('2024-02-28')
        end = pd.Timestamp('2024-03-01')
        
        result = utils.simulation_dates(start, end)
        
        # Should cross Feb 29 (leap day)
        assert len(result) == 3
        assert result[0] == '2024-02-28'
        assert result[1] == '2024-02-29'  # Leap day exists in 2024
        assert result[2] == '2024-03-01'
    
    def test_year_boundary(self):
        """Test simulation_dates crossing year boundary."""
        start = pd.Timestamp('2025-12-30')
        end = pd.Timestamp('2026-01-02')
        
        result = utils.simulation_dates(start, end)
        
        assert len(result) == 4
        assert result[0] == '2025-12-30'
        assert result[1] == '2025-12-31'
        assert result[2] == '2026-01-01'
        assert result[3] == '2026-01-02'
    
    def test_month_boundary(self):
        """Test simulation_dates crossing month boundary."""
        start = pd.Timestamp('2026-08-30')
        end = pd.Timestamp('2026-09-02')
        
        result = utils.simulation_dates(start, end)
        
        assert len(result) == 4
        assert '2026-08-30' in result
        assert '2026-08-31' in result
        assert '2026-09-01' in result
        assert '2026-09-02' in result
    
    def test_long_range(self):
        """Test simulation_dates with 30-day range."""
        start = pd.Timestamp('2026-08-01')
        end = pd.Timestamp('2026-08-31')
        
        result = utils.simulation_dates(start, end)
        
        assert len(result) == 31
        assert result[0] == '2026-08-01'
        assert result[-1] == '2026-08-31'


# ===== date_to_nightnum tests =====

class TestDateToNightnum:
    """Tests for date_to_nightnum() function."""
    
    def test_same_day_as_base(self):
        """Test nightnum is 0 when date equals base MJD."""
        # MJD 60000.0 corresponds to 2023-02-25
        base_mjd = 60000.0
        date = '2023-02-25'
        
        result = utils.date_to_nightnum(date, base_mjd)
        
        assert result == 0
    
    def test_one_day_later(self):
        """Test nightnum is 1 for date one day after base."""
        base_mjd = 60000.0
        date = '2023-02-26'
        
        result = utils.date_to_nightnum(date, base_mjd)
        
        assert result == 1
    
    def test_multiple_days_later(self):
        """Test nightnum with multiple days offset."""
        base_mjd = 60000.0
        date = '2023-03-07'  # 10 days after 2023-02-25
        
        result = utils.date_to_nightnum(date, base_mjd)
        
        assert result == 10
    
    def test_returns_integer(self):
        """Verify date_to_nightnum returns an integer."""
        base_mjd = 60000.5  # Fractional MJD
        date = '2023-02-26'
        
        result = utils.date_to_nightnum(date, base_mjd)
        
        assert isinstance(result, int)
    
    def test_midnight_utc_convention(self):
        """Test that date string is interpreted as UTC midnight."""
        # Two consecutive dates should differ by 1 night
        base_mjd = 60000.0
        date1 = '2023-02-25'
        date2 = '2023-02-26'
        
        night1 = utils.date_to_nightnum(date1, base_mjd)
        night2 = utils.date_to_nightnum(date2, base_mjd)
        
        assert night2 - night1 == 1
    
    def test_known_mjd_dates(self):
        """Test with consistent date and base MJD."""
        # Use same date as base - should give nightnum 0
        from astropy.time import Time
        test_date = '2026-08-15'
        t = Time(test_date, scale='utc')
        base_mjd = t.mjd
        
        result = utils.date_to_nightnum(test_date, base_mjd)
        
        assert result == 0
    
    def test_large_offset(self):
        """Test with large date offset."""
        base_mjd = 60000.0
        date = '2026-08-10'  # Far in future
        
        result = utils.date_to_nightnum(date, base_mjd)
        
        # Should be positive and large (>1000 days)
        assert result > 1000
        assert isinstance(result, int)


# ===== get_base_mjd tests =====

class TestGetBaseMjd:
    """Tests for get_base_mjd() function."""
    
    def test_get_base_mjd_returns_float(self):
        """Test that get_base_mjd returns a float MJD value."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (60000.5,)
        
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('sqlite3.connect', return_value=mock_conn):
            result = utils.get_base_mjd('/path/to/db.sqlite')
        
        assert isinstance(result, float)
        assert result == 60000.5
    
    def test_get_base_mjd_queries_correct_table(self):
        """Test that correct SQL query is executed."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (60000.0,)
        
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('sqlite3.connect', return_value=mock_conn):
            utils.get_base_mjd('/path/to/db.sqlite')
        
        # Verify SQL query was called
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0][0]
        
        # Check that query selects MIN(observationStartMJD) from observations
        assert 'MIN' in call_args
        assert 'observationStartMJD' in call_args
        assert 'observations' in call_args
    
    def test_get_base_mjd_connects_to_database(self):
        """Test that correct database path is used."""
        db_path = '/path/to/test_db.sqlite'
        
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (60000.0,)
        
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('sqlite3.connect', return_value=mock_conn) as mock_connect:
            utils.get_base_mjd(db_path)
        
        # Verify sqlite3.connect was called with correct path
        mock_connect.assert_called_once_with(db_path)
    
    def test_get_base_mjd_with_typical_value(self):
        """Test with typical MJD value."""
        mock_cursor = Mock()
        typical_mjd = 60102.0  # 2026-01-01
        mock_cursor.fetchone.return_value = (typical_mjd,)
        
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('sqlite3.connect', return_value=mock_conn):
            result = utils.get_base_mjd('/path/to/db.sqlite')
        
        assert result == typical_mjd
    
    def test_get_base_mjd_with_early_date(self):
        """Test with early MJD (historical date)."""
        mock_cursor = Mock()
        early_mjd = 59000.0  # Before 2020
        mock_cursor.fetchone.return_value = (early_mjd,)
        
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('sqlite3.connect', return_value=mock_conn):
            result = utils.get_base_mjd('/path/to/db.sqlite')
        
        assert result == early_mjd
    
    def test_get_base_mjd_with_late_date(self):
        """Test with future MJD."""
        mock_cursor = Mock()
        future_mjd = 65000.0  # Future date
        mock_cursor.fetchone.return_value = (future_mjd,)
        
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('sqlite3.connect', return_value=mock_conn):
            result = utils.get_base_mjd('/path/to/db.sqlite')
        
        assert result == future_mjd


# ===== Integration tests =====

class TestUtilsIntegration:
    """Integration tests across multiple utils functions."""
    
    def test_simulation_dates_with_date_to_nightnum(self):
        """Test using simulation_dates output with date_to_nightnum."""
        base_mjd = 60000.0
        start = pd.Timestamp('2023-02-25')
        end = pd.Timestamp('2023-02-27')
        
        # Generate dates
        dates = utils.simulation_dates(start, end)
        
        # Convert each to nightnum
        nightnums = [utils.date_to_nightnum(d, base_mjd) for d in dates]
        
        # Should be monotonically increasing
        assert nightnums == [0, 1, 2]
    
    def test_nightnum_sequence_from_dates(self):
        """Test that nightnum sequence matches date sequence."""
        base_mjd = 60100.0
        start = pd.Timestamp('2026-03-01')
        end = pd.Timestamp('2026-03-05')
        
        dates = utils.simulation_dates(start, end)
        nightnums = [utils.date_to_nightnum(d, base_mjd) for d in dates]
        
        # Verify nightnums increase by 1 each day
        for i in range(len(nightnums) - 1):
            assert nightnums[i+1] - nightnums[i] == 1
