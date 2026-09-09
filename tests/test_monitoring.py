"""Tests for monitoring module.

Tests for resource monitoring, logging, and plotting functionality.
Note: Commented-out stress_test functions are excluded per user request.
"""

import pytest
import logging
import tempfile
import os
from io import StringIO
from unittest.mock import Mock, MagicMock, patch, call, mock_open
from datetime import datetime
import threading

from rubin_sunrise import monitoring


class TestReadLog:
    """Tests for _read_log function."""

    def test_read_log_with_matching_lines(self):
        """Extract timestamps from lines matching search string."""
        log_content = "[2026-09-02 10:30:45] Updated data for cycle 1\n[2026-09-02 10:30:50] Other log\n[2026-09-02 10:31:00] Updated data for cycle 2\n"
        
        with patch("builtins.open", mock_open(read_data=log_content)):
            result = monitoring._read_log("logs", "test_time", "Updated data")
        
        assert len(result) == 2
        assert result[0] == "2026-09-02 10:30:45"
        assert result[1] == "2026-09-02 10:31:00"

    def test_read_log_no_matching_lines(self):
        """Return empty list when no lines match search string."""
        log_content = "[2026-09-02 10:30:45] Some log\n[2026-09-02 10:30:50] Other log\n"
        
        with patch("builtins.open", mock_open(read_data=log_content)):
            result = monitoring._read_log("logs", "test_time", "NOTFOUND")
        
        assert result == []

    def test_read_log_empty_file(self):
        """Return empty list for empty log file."""
        with patch("builtins.open", mock_open(read_data="")):
            result = monitoring._read_log("logs", "test_time", "search")
        
        assert result == []

    def test_read_log_single_match(self):
        """Extract single timestamp from log file."""
        log_content = "[2026-09-02 15:45:30] Map type clicked\n"
        
        with patch("builtins.open", mock_open(read_data=log_content)):
            result = monitoring._read_log("logs", "2026-09-02-15-45", "Map type")
        
        assert result == ["2026-09-02 15:45:30"]

    def test_read_log_file_path_construction(self):
        """Verify correct file path is constructed."""
        with patch("builtins.open", mock_open(read_data="")) as mock_file:
            monitoring._read_log("my_logs", "2026-09-02-12-00", "search_term")
            mock_file.assert_called_once_with("my_logs/log_2026-09-02-12-00.txt", 'r')


class TestWrite:
    """Tests for _write function."""

    def test_write_single_line_at_line_start(self):
        """Write single line with timestamp when at line start."""
        dest1 = StringIO()
        dest2 = StringIO()
        destinations = (dest1, dest2)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2026-09-02 10:30:00"
            result = monitoring._write(destinations, "Test message", at_line_start=True)
        
        expected = "[2026-09-02 10:30:00] Test message"
        assert dest1.getvalue() == expected
        assert dest2.getvalue() == expected
        assert result is False  # Not at line start anymore

    def test_write_multiple_lines(self):
        """Write message with multiple lines."""
        dest1 = StringIO()
        dest2 = StringIO()
        destinations = (dest1, dest2)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = ["2026-09-02 10:30:00", "2026-09-02 10:30:01"]
            result = monitoring._write(destinations, "Line 1\nLine 2", at_line_start=True)
        
        dest_content = dest1.getvalue()
        assert "[2026-09-02 10:30:00] Line 1\n" in dest_content
        assert "[2026-09-02 10:30:01] Line 2" in dest_content
        assert result is False

    def test_write_continuation_line(self):
        """Write continuation of line (not at line start)."""
        dest1 = StringIO()
        destinations = (dest1,)
        
        result = monitoring._write(destinations, " continuation", at_line_start=False)
        
        assert dest1.getvalue() == " continuation"
        assert result is False

    def test_write_empty_message(self):
        """Handle empty message."""
        dest1 = StringIO()
        destinations = (dest1,)
        
        result = monitoring._write(destinations, "", at_line_start=True)
        
        assert dest1.getvalue() == ""
        assert result is True  # Still at line start

    def test_write_message_with_empty_lines(self):
        """Write message with empty lines between content."""
        dest1 = StringIO()
        destinations = (dest1,)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = ["2026-09-02 10:30:00", "2026-09-02 10:30:01"]
            result = monitoring._write(destinations, "Start\n\nEnd", at_line_start=True)
        
        dest_content = dest1.getvalue()
        assert "[2026-09-02 10:30:00] Start\n" in dest_content
        assert "[2026-09-02 10:30:01] End" in dest_content
        assert result is False  # Message ends without newline, so not at line start

    def test_write_destination_flush_called(self):
        """Verify flush is called on all destinations."""
        mock_dest1 = MagicMock()
        mock_dest2 = MagicMock()
        destinations = (mock_dest1, mock_dest2)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2026-09-02 10:30:00"
            monitoring._write(destinations, "Test", at_line_start=True)
        
        mock_dest1.flush.assert_called_once()
        mock_dest2.flush.assert_called_once()


class TestQuietFilter:
    """Tests for QuietFilter logging filter."""

    def test_quiet_filter_blocks_check_update(self):
        """Block log records containing /check_update."""
        filter_obj = monitoring.QuietFilter()
        record = Mock()
        record.getMessage.return_value = "GET /check_update HTTP/1.1"
        
        assert filter_obj.filter(record) is False

    def test_quiet_filter_blocks_next_update(self):
        """Block log records containing /next_update."""
        filter_obj = monitoring.QuietFilter()
        record = Mock()
        record.getMessage.return_value = "POST /next_update with params"
        
        assert filter_obj.filter(record) is False

    def test_quiet_filter_allows_other_messages(self):
        """Allow log records not containing noisy endpoints."""
        filter_obj = monitoring.QuietFilter()
        record = Mock()
        record.getMessage.return_value = "GET /page HTTP/1.1"
        
        assert filter_obj.filter(record) is True

    def test_quiet_filter_allows_empty_message(self):
        """Allow empty log messages."""
        filter_obj = monitoring.QuietFilter()
        record = Mock()
        record.getMessage.return_value = ""
        
        assert filter_obj.filter(record) is True

    def test_quiet_filter_case_sensitive(self):
        """Filter checks are case-sensitive."""
        filter_obj = monitoring.QuietFilter()
        record = Mock()
        record.getMessage.return_value = "GET /CHECK_UPDATE HTTP/1.1"  # uppercase
        
        assert filter_obj.filter(record) is True  # Should allow (not exact match)

    def test_quiet_filter_noisy_set_contains_endpoints(self):
        """Verify NOISY set contains expected endpoints."""
        assert '/check_update' in monitoring.QuietFilter.NOISY
        assert '/next_update' in monitoring.QuietFilter.NOISY


class TestLogger:
    """Tests for Logger class."""

    def test_logger_init(self):
        """Initialize logger with multiple destinations."""
        dest1 = StringIO()
        dest2 = StringIO()
        logger = monitoring.Logger(dest1, dest2)
        
        assert logger.destinations == (dest1, dest2)
        assert logger.at_line_start is True

    def test_logger_write_single_message(self):
        """Write single message to logger."""
        dest1 = StringIO()
        logger = monitoring.Logger(dest1)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2026-09-02 10:30:00"
            logger.write("Test message")
        
        assert "[2026-09-02 10:30:00] Test message" in dest1.getvalue()

    def test_logger_write_multiple_times(self):
        """Write multiple times updates at_line_start state."""
        dest1 = StringIO()
        logger = monitoring.Logger(dest1)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = ["2026-09-02 10:30:00", "2026-09-02 10:30:01"]
            logger.write("Line 1\n")
            logger.write("Line 2")
        
        content = dest1.getvalue()
        assert "Line 1" in content
        assert "Line 2" in content

    def test_logger_flush(self):
        """Call flush on all destinations."""
        mock_dest1 = MagicMock()
        mock_dest2 = MagicMock()
        logger = monitoring.Logger(mock_dest1, mock_dest2)
        
        logger.flush()
        
        mock_dest1.flush.assert_called_once()
        mock_dest2.flush.assert_called_once()

    def test_logger_write_updates_line_start_state(self):
        """at_line_start state updated correctly after write."""
        dest1 = StringIO()
        logger = monitoring.Logger(dest1)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2026-09-02 10:30:00"
            logger.write("Message\n")
        
        assert logger.at_line_start is True

    def test_logger_maintains_state_across_writes(self):
        """Logger state persists correctly across multiple writes."""
        dest1 = StringIO()
        logger = monitoring.Logger(dest1)
        
        with patch("rubin_sunrise.monitoring.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = [
                "2026-09-02 10:30:00",
                "2026-09-02 10:30:01"
            ]
            logger.write("Start")
            logger.write(" middle")
            logger.write("\nEnd")
        
        content = dest1.getvalue()
        assert "[2026-09-02 10:30:00] Start" in content
        # Middle part should not have timestamp
        assert " middle" in content
        # After newline, next line gets timestamp
        assert "\n[2026-09-02 10:30:01] End" in content


class TestMonitorResources:
    """Tests for monitor_resources function."""

    def test_monitor_resources_creates_csv_header(self):
        """Create CSV file with header on startup."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            stop_event = threading.Event()
            stop_event.set()  # Stop immediately
            
            with patch("rubin_sunrise.monitoring.psutil.Process"):
                monitoring.monitor_resources(temp_path, interval=0.1, stop_event=stop_event)
            
            with open(temp_path, 'r') as f:
                first_line = f.readline()
            
            assert first_line.strip() == "timestamp,cpu_percent,memory_mb"
        finally:
            os.unlink(temp_path)

    def test_monitor_resources_writes_data_rows(self):
        """Write data rows until stop_event is set."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            stop_event = threading.Event()
            
            mock_process = MagicMock()
            mock_process.cpu_percent.return_value = 25.5
            mock_process.memory_info.return_value.rss = 512 * 1024 * 1024  # 512 MB
            
            call_count = [0]
            def side_effect(interval):
                call_count[0] += 1
                if call_count[0] >= 2:
                    stop_event.set()
                return 25.5
            
            mock_process.cpu_percent.side_effect = side_effect
            
            with patch("rubin_sunrise.monitoring.psutil.Process", return_value=mock_process):
                with patch("rubin_sunrise.monitoring.time.strftime", return_value="2026-09-02 10:30:00"):
                    monitoring.monitor_resources(temp_path, interval=0.01, stop_event=stop_event)
            
            with open(temp_path, 'r') as f:
                lines = f.readlines()
            
            assert len(lines) >= 2  # Header + at least one data row
            assert "timestamp,cpu_percent,memory_mb" in lines[0]
            # Check data row format
            assert "2026-09-02 10:30:00,25.5,512.0" in lines[1]
        finally:
            os.unlink(temp_path)

    def test_monitor_resources_uses_custom_interval(self):
        """Use provided interval parameter."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            stop_event = threading.Event()
            
            mock_process = MagicMock()
            mock_process.cpu_percent.return_value = 50.0
            mock_process.memory_info.return_value.rss = 256 * 1024 * 1024
            
            call_count = [0]
            def side_effect(interval):
                call_count[0] += 1
                if call_count[0] >= 1:
                    stop_event.set()
                return 50.0
            
            mock_process.cpu_percent.side_effect = side_effect
            
            with patch("rubin_sunrise.monitoring.psutil.Process", return_value=mock_process):
                with patch("rubin_sunrise.monitoring.time.strftime", return_value="2026-09-02 10:30:00"):
                    monitoring.monitor_resources(temp_path, interval=10.0, stop_event=stop_event)
            
            # Verify cpu_percent was called with our interval
            mock_process.cpu_percent.assert_called_with(interval=10.0)
        finally:
            os.unlink(temp_path)


class TestLogTableSize:
    """Tests for log_table_size function."""

    def test_log_table_size_creates_header(self):
        """Create header when file doesn't exist."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        os.unlink(temp_path)  # Remove it to test file creation
        
        try:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = [1000000]  # 1 MB
            
            with patch("rubin_sunrise.monitoring.time.strftime", return_value="2026-09-02 10:30:00"):
                monitoring.log_table_size(mock_cur, temp_path, db_name="test_db")
            
            with open(temp_path, 'r') as f:
                first_line = f.readline()
            
            assert first_line.strip() == "timestamp,total_size_bytes"
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_log_table_size_appends_to_existing_file(self):
        """Append data row without header if file exists."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            f.write("timestamp,total_size_bytes\n")
            f.write("2026-09-02 10:29:00,900000\n")
            temp_path = f.name
        
        try:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = [950000]
            
            with patch("rubin_sunrise.monitoring.time.strftime", return_value="2026-09-02 10:30:00"):
                monitoring.log_table_size(mock_cur, temp_path, db_name="test_db")
            
            with open(temp_path, 'r') as f:
                lines = f.readlines()
            
            assert len(lines) == 3  # header + 2 data rows
            assert "2026-09-02 10:30:00,950000" in lines[2]
        finally:
            os.unlink(temp_path)

    def test_log_table_size_executes_correct_query(self):
        """Execute correct SQL query with db_name parameter."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = [5000000]
            
            with patch("rubin_sunrise.monitoring.time.strftime", return_value="2026-09-02 10:30:00"):
                monitoring.log_table_size(mock_cur, temp_path, db_name="custom_db")
            
            # Verify query was called with custom db_name
            mock_cur.execute.assert_called_once_with("SELECT pg_database_size(%s)", ("custom_db",))
        finally:
            os.unlink(temp_path)

    def test_log_table_size_uses_default_db_name(self):
        """Use default DB_NAME from config if not provided."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = [5000000]
            
            with patch("rubin_sunrise.monitoring.time.strftime", return_value="2026-09-02 10:30:00"):
                with patch("rubin_sunrise.monitoring.DB_NAME", "default_db"):
                    monitoring.log_table_size(mock_cur, temp_path, db_name=None)
            
            # Should use default
            mock_cur.execute.assert_called_once_with("SELECT pg_database_size(%s)", ("default_db",))
        finally:
            os.unlink(temp_path)


class TestMonitoringPlotsCollector:
    """Tests for monitoring_plots_collector function."""

    def test_monitoring_plots_collector_handles_empty_resource_file(self):
        """Skip plotting for empty resource CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resources_path = os.path.join(tmpdir, "resources_2026-09-02.csv")
            table_size_path = os.path.join(tmpdir, "table_size_2026-09-02.csv")
            
            with open(resources_path, 'w') as f:
                f.write("timestamp,cpu_percent,memory_mb\n")
            with open(table_size_path, 'w') as f:
                f.write("timestamp,total_size_bytes\n")
            
            with patch("builtins.print") as mock_print:
                monitoring.monitoring_plots_collector(tmpdir, "2026-09-02")
            
            # Should print warning
            assert any("WARNING" in str(call) for call in mock_print.call_args_list)

    def test_monitoring_plots_collector_handles_missing_files(self):
        """Function requires both CSV files to exist (doesn't gracefully handle missing)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create only one file (missing the other) - will raise FileNotFoundError
            resources_path = os.path.join(tmpdir, "resources_2026-09-02.csv")
            with open(resources_path, 'w') as f:
                f.write("timestamp,cpu_percent,memory_mb\n")
            
            # Missing table_size CSV will cause FileNotFoundError (not caught by code)
            with pytest.raises(FileNotFoundError):
                monitoring.monitoring_plots_collector(tmpdir, "2026-09-02")


class TestMonitoringPlotsDisplay:
    """Tests for monitoring_plots_display function."""

    def test_monitoring_plots_display_handles_empty_file(self):
        """Skip plotting for empty CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resources_path = os.path.join(tmpdir, "resources_2026-09-02.csv")
            
            with open(resources_path, 'w') as f:
                f.write("timestamp,cpu_percent,memory_mb\n")
            
            with patch("builtins.print") as mock_print:
                monitoring.monitoring_plots_display(tmpdir, "2026-09-02")
            
            assert any("WARNING" in str(call) for call in mock_print.call_args_list)

    def test_monitoring_plots_display_handles_missing_file(self):
        """Function requires CSV file to exist (doesn't gracefully handle missing)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Missing CSV file will cause FileNotFoundError (not caught by code)
            with pytest.raises(FileNotFoundError):
                monitoring.monitoring_plots_display(tmpdir, "2026-09-02")

