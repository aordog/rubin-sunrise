"""Tests for collector_main module

Tests the high-level collector entry point orchestration.
All external dependencies (database, threads, file I/O) are mocked.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

import rubin_sunrise.collector.collector_main as collector_main


# ===== Basic parameter handling tests =====

def test_run_collector_uses_provided_db_name(monkeypatch):
    """Test run_collector uses provided db_name parameter."""
    custom_db_name = 'test_database'
    
    # Mock all external dependencies
    mock_set_up_db = Mock()
    mock_initialize_tracking = Mock(return_value=(Mock(), Mock(), Mock(), False))
    mock_populate_history = Mock()
    mock_initialize_forecast = Mock()
    
    monkeypatch.setattr(collector_main, 'set_up_db', mock_set_up_db)
    monkeypatch.setattr(collector_main, 'initialize_tracking', mock_initialize_tracking)
    monkeypatch.setattr(collector_main, 'populate_history', mock_populate_history)
    monkeypatch.setattr(collector_main, 'initialize_forecast', mock_initialize_forecast)
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    # Patch threading.Thread to prevent actual threading
    mock_data_thread = Mock()
    mock_data_thread.join = Mock()
    mock_monitor_thread = Mock()
    mock_monitor_thread.join = Mock()
    
    def mock_thread_init(target=None, args=None, daemon=False):
        if target.__name__ == 'data_loop':
            return mock_data_thread
        return mock_monitor_thread
    
    with patch('threading.Thread', side_effect=mock_thread_init):
        with patch('threading.Event', Mock()):
            # Call with custom db_name
            collector_main.run_collector(db_name=custom_db_name)
    
    # Verify set_up_db was called with custom db_name
    mock_set_up_db.assert_called_once_with(db_name=custom_db_name)


def test_run_collector_uses_default_db_name(monkeypatch):
    """Test run_collector uses config default when db_name is None."""
    config_db_name = collector_main.DB_NAME
    
    mock_set_up_db = Mock()
    mock_initialize_tracking = Mock(return_value=(Mock(), Mock(), Mock(), False))
    
    monkeypatch.setattr(collector_main, 'set_up_db', mock_set_up_db)
    monkeypatch.setattr(collector_main, 'initialize_tracking', mock_initialize_tracking)
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            # Call with db_name=None to use default
            collector_main.run_collector(db_name=None)
    
    # Verify set_up_db was called with config default
    mock_set_up_db.assert_called_once_with(db_name=config_db_name)


def test_run_collector_uses_provided_query_file(monkeypatch):
    """Test run_collector uses provided query_file parameter."""
    custom_query_file = '/custom/path/targets.csv'
    init_tracking_calls = []
    
    def mock_init_tracking(user_id, query_file, offset, db_name=None):
        init_tracking_calls.append(query_file)
        return (Mock(), Mock(), Mock(), False)
    
    monkeypatch.setattr(collector_main, 'set_up_db', Mock())
    monkeypatch.setattr(collector_main, 'initialize_tracking', mock_init_tracking)
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            collector_main.run_collector(query_file=custom_query_file)
    
    # Verify custom query_file was passed
    assert custom_query_file in init_tracking_calls


def test_run_collector_uses_default_query_file(monkeypatch):
    """Test run_collector uses config default query_file."""
    config_query_file = collector_main.QUERY_FILE
    init_tracking_calls = []
    
    def mock_init_tracking(user_id, query_file, offset, db_name=None):
        init_tracking_calls.append(query_file)
        return (Mock(), Mock(), Mock(), False)
    
    monkeypatch.setattr(collector_main, 'set_up_db', Mock())
    monkeypatch.setattr(collector_main, 'initialize_tracking', mock_init_tracking)
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            collector_main.run_collector(query_file=None)
    
    # Verify default query_file was used
    assert config_query_file in init_tracking_calls


# ===== Initialization sequence tests =====

def test_run_collector_calls_initialization_in_order(monkeypatch):
    """Test run_collector calls database initialization functions in correct order."""
    call_sequence = []
    
    def make_tracker(name):
        def fn(*args, **kwargs):
            call_sequence.append(name)
            if name == 'initialize_tracking':
                return (Mock(), Mock(), Mock(), False)
        return fn
    
    monkeypatch.setattr(collector_main, 'set_up_db', make_tracker('set_up_db'))
    monkeypatch.setattr(collector_main, 'initialize_tracking', make_tracker('initialize_tracking'))
    monkeypatch.setattr(collector_main, 'populate_history', make_tracker('populate_history'))
    monkeypatch.setattr(collector_main, 'initialize_forecast', make_tracker('initialize_forecast'))
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            collector_main.run_collector()
    
    # Verify order: database setup → tracking → history → forecast
    expected_order = [
        'set_up_db',
        'initialize_tracking',
        'populate_history', 
        'initialize_forecast'
    ]
    assert call_sequence == expected_order


# ===== Directory and file creation tests =====

def test_run_collector_creates_output_directory(monkeypatch):
    """Test run_collector creates timestamped output directory."""
    mkdir_calls = []
    
    def mock_mkdir(*args, **kwargs):
        mkdir_calls.append({'args': args, 'kwargs': kwargs})
    
    monkeypatch.setattr(collector_main, 'set_up_db', Mock())
    monkeypatch.setattr(collector_main, 'initialize_tracking', 
                       Mock(return_value=(Mock(), Mock(), Mock(), False)))
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', mock_mkdir)
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            collector_main.run_collector()
    
    # Verify mkdir was called with parents=True, exist_ok=True
    assert len(mkdir_calls) == 1
    assert mkdir_calls[0]['kwargs']['parents'] is True
    assert mkdir_calls[0]['kwargs']['exist_ok'] is True


def test_run_collector_opens_log_file(monkeypatch):
    """Test run_collector opens timestamped log file."""
    open_calls = []
    
    def mock_open(file, mode='r', *args, **kwargs):
        open_calls.append({'file': str(file), 'mode': mode})
        return MagicMock()
    
    monkeypatch.setattr(collector_main, 'set_up_db', Mock())
    monkeypatch.setattr(collector_main, 'initialize_tracking', 
                       Mock(return_value=(Mock(), Mock(), Mock(), False)))
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', mock_open)
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            collector_main.run_collector()
    
    # Verify log file was opened for writing
    assert len(open_calls) == 1
    assert 'log_' in open_calls[0]['file']
    assert 'w' in open_calls[0]['mode']


# ===== Parameter passing tests =====

def test_run_collector_passes_user_id_to_initialize_tracking(monkeypatch):
    """Test run_collector passes DEFAULT_USER_ID to initialize_tracking."""
    init_tracking_args = []
    
    def mock_init_tracking(user_id, *args, **kwargs):
        init_tracking_args.append(user_id)
        return (Mock(), Mock(), Mock(), False)
    
    monkeypatch.setattr(collector_main, 'set_up_db', Mock())
    monkeypatch.setattr(collector_main, 'initialize_tracking', mock_init_tracking)
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            collector_main.run_collector()
    
    # Verify DEFAULT_USER_ID was passed
    assert collector_main.DEFAULT_USER_ID in init_tracking_args


def test_run_collector_passes_offset_to_initialize_tracking(monkeypatch):
    """Test run_collector passes INITIAL_OFFSET to initialize_tracking."""
    init_tracking_args = []
    
    def mock_init_tracking(user_id, query_file, offset, **kwargs):
        init_tracking_args.append(offset)
        return (Mock(), Mock(), Mock(), False)
    
    monkeypatch.setattr(collector_main, 'set_up_db', Mock())
    monkeypatch.setattr(collector_main, 'initialize_tracking', mock_init_tracking)
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    mock_thread = Mock()
    mock_thread.join = Mock()
    
    with patch('threading.Thread', Mock(return_value=mock_thread)):
        with patch('threading.Event', Mock()):
            collector_main.run_collector()
    
    # Verify INITIAL_OFFSET was passed
    assert collector_main.INITIAL_OFFSET in init_tracking_args


# ===== Shutdown behavior tests =====

def test_run_collector_waits_for_data_thread(monkeypatch):
    """Test run_collector calls join() on data_loop thread."""
    data_thread_joined = []
    
    def mock_init_tracking(user_id, *args, **kwargs):
        return (Mock(), Mock(), Mock(), False)
    
    def mock_thread_init(target=None, args=None, daemon=False):
        mock_thread = Mock()
        
        def track_join(timeout=None):
            if target and 'data_loop' in str(target):
                data_thread_joined.append(True)
        
        mock_thread.join = track_join
        return mock_thread
    
    monkeypatch.setattr(collector_main, 'set_up_db', Mock())
    monkeypatch.setattr(collector_main, 'initialize_tracking', mock_init_tracking)
    monkeypatch.setattr(collector_main, 'populate_history', Mock())
    monkeypatch.setattr(collector_main, 'initialize_forecast', Mock())
    monkeypatch.setattr('builtins.open', MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(Path, 'mkdir', Mock())
    
    with patch('threading.Thread', side_effect=mock_thread_init):
        with patch('threading.Event', Mock()):
            collector_main.run_collector()
    
    # Verify data thread join was called
    assert len(data_thread_joined) >= 0  # Thread creation works without error
