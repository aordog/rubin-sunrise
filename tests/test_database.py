"""Tests for lsst module"""

import pytest
import numpy as np
import pandas as pd
import rubin_sunrise.database as database
import tempfile
import os

@pytest.fixture
def csv_with_comma():
    """Create a temporary CSV file with comma delimiter."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
        f.write("Object Name,RA,Dec,Type,Comment\n")
        f.write("Target1,10.5,-20.5,Galaxy,test\n")
        f.write("Target2,15.0,-50.0,Galaxy,test\n") 
        f.write("Target3,20.0,-5.0,Star,test\n")
        f.write("Target4,20.0,20.0,Star,test\n")
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)

@pytest.fixture
def csv_with_pipe():
    """Create a temporary CSV file with pipe delimiter."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, newline='') as f:
        f.write("Name|RA|Dec|Type|Comment\n")
        f.write("Target1|10.5|-20.5|Galaxy|test\n")
        f.write("Target2|15.0|-10.0|Galaxy|test\n")
        f.write("Target3|20.0|5.0|Star|test\n")
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)

@pytest.mark.parametrize(
    "fixture_name, declim, expected_count",
    [
        ("csv_with_comma", -10.0, 2),  # 2 targets within declim
        ("csv_with_comma",  0.0, 3),  # 3 target within declim
        ("csv_with_pipe", 0.0, 2),    # Different delimiter
    ],
    ids=["comma_declim_-10", "comma_declim_0", "pipe_delimiter"]
)
def test_read_csv_file(fixture_name, declim, expected_count, request):
    """Test that _read_csv_file correctly reads and filters targets."""
    file_path = request.getfixturevalue(fixture_name)
    
    ra_use, dec_use, all_flags = database._read_csv_file(file_path, declim)
    
    assert len(ra_use) == expected_count, \
        f"Expected {expected_count} targets, got {len(ra_use)}"
    assert len(ra_use) == len(dec_use), "RA and Dec arrays should have same length"
    assert all(dec < declim for dec in dec_use), \
        f"All Dec values should be < {declim}, got {dec_use}"