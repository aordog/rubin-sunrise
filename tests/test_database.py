"""Tests for lsst module
Note: _get_obs_flags and _is_valid_date not currently tested, since the
user-defined flag feature is broken (Aug 13 2026). Will implement tests
for these when that feature is fixed.
"""

import pytest
import numpy as np
import pandas as pd
import rubin_sunrise.collector.database as database
import tempfile
import os
from unittest.mock import Mock, call
#BANDS = ('u', 'g', 'r', 'i', 'z', 'y')


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

@pytest.fixture
def basic_grid():
    """Fixture providing a simple 3-point grid for testing."""
    ra_grid = np.array([0.0, 1.0, 2.0])
    dec_grid = np.array([0.0, 1.0, 2.0])
    return ra_grid, dec_grid

@pytest.fixture
def mock_camera():
    """Fixture providing a mock camera footprint."""
    return Mock()

@pytest.fixture
def test_date():
    """Fixture providing a standard test date."""
    return "2026-08-13"

@pytest.fixture
def test_member_id():
    """Fixture providing a standard test member ID."""
    return 42

@pytest.fixture
def test_group_id():
    """Fixture providing a standard test group ID."""
    return 5

@pytest.fixture
def test_visits():
    """Fixture providing a standard test visits dictionary."""
    return {
        'uvisits': 5.0, 
        'gvisits': 3.0, 
        'rvisits': 7.0, 
        'ivisits': 2.0, 
        'zvisits': 1.0, 
        'yvisits': 0.0
    }

@pytest.fixture
def test_masks():
    """Fixture providing a standard test masks dictionary."""
    return {
        'umask': np.array([1, 2, 3], dtype=np.int16),
        'gmask': np.array([4, 5, 6], dtype=np.int16),
        'rmask': np.array([7, 8, 9], dtype=np.int16),
        'imask': np.array([10, 11, 12], dtype=np.int16),
        'zmask': np.array([13, 14, 15], dtype=np.int16),
        'ymask': np.array([16, 17, 18], dtype=np.int16),
    }

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

@pytest.mark.parametrize(
    "ra_list, dec_list, nside, expected_groups, expected_name_gr",
    [
        (np.array([256.5, 257.0, 257.4, 256.5, 257.0, 257.4]),
         np.array([-60.4, -60.4, -60.4, -61.1, -61.1, -61.1]),
         16,1,['nside16_2880']),

        (np.array([256.5, 257.0, 257.4, 256.5, 257.0, 257.4]),
         np.array([-60.4, -60.4, -60.4, -61.1, -61.1, -61.1]),
         8,1,['nside8_722']),

        (np.array([29.0, 100.0, 137.0, 139.0, 142.0, 143.0]),
         np.array([61.0,   0.0, -19.5, -19.5, -19.5, -19.5]),
         8,3,['nside8_41','nside8_376', 'nside8_508']),

        (np.array([29.0, 100.0, 137.0, 139.0, 142.0, 143.0]),
         np.array([61.0,   0.0, -19.5, -19.5, -19.5, -19.5]),
         16,4,['nside16_183','nside16_1521', 'nside16_2040', 'nside16_2041']),
    ],
    ids=["nside16_1grp","nside8_1grp","nside8_3grp","nside16_4grp"]
)
def test_group_targets(ra_list, dec_list, nside,expected_groups,expected_name_gr):
    """Test that _group_targets correctly groups targets on healpix grid."""

    groups_test = database._group_targets(ra_list, dec_list, nside)

    actual_name_gr = []
    for i in range(0,len(groups_test)):
        actual_name_gr.append(groups_test[i]['name_gr'])

    assert len(groups_test) == expected_groups, \
        f"Expected {expected_groups} groups, got {len(groups_test)}"
    assert actual_name_gr == expected_name_gr, \
        f"Expected group names: {expected_name_gr}, got {actual_name_gr}"

@pytest.mark.parametrize(
    "pointing_ra, pointing_dec, expected_size, expected_dRA",
    [
        (180.0, 0.0, 116281, 5.66), # equator
        (180.0, 45.0, 116281, 8.0), # mid declination
        (180.0, 87.0, 116281, 108.2), # high declination
        (180.0, 90.0, 116281, 360.0), # celestial pole
    ],
    ids=["equator", "mid_dec", "near_pole", "pole"]
)
def test_add_mask_grid(pointing_ra, pointing_dec, expected_size, expected_dRA):
    """Test that _add_mask_grid correctly produces grids for displaying 2D maps."""

    ra_grid_actual, dec_grid_actual = database._add_mask_grid(pointing_ra, 
                                                              pointing_dec)
    actual_dRA = np.nanmax(ra_grid_actual) - np.nanmin(ra_grid_actual)

    assert ra_grid_actual.shape[0] == expected_size,\
        f"Expected RA grid length: {expected_size}, got {len(ra_grid_actual)}"
    assert dec_grid_actual.shape[0] == expected_size,\
        f"Expected dec grid length:{expected_size}, got {len(dec_grid_actual)}"
    assert np.isclose(actual_dRA, expected_dRA, atol=0.5),\
        f"Expected RA extent:{expected_dRA}, got {actual_dRA}"

def make_visits_use(ra=None, dec=None, band=None, rot=None):
    """Helper to easily construct visits_use dictionaries."""
    if ra is None:
        ra = []
    if dec is None:
        dec = []
    if band is None:
        band = []
    if rot is None:
        rot = []
    
    return {'ra': ra, 'dec': dec, 'band': band, 'rot': rot}

@pytest.mark.parametrize(
    "visits_ra, visits_dec, visits_band, camera_indices, expected_mask_results",
    [
        # Single visit covering all grid points
        ([0.5], [0.5], ['r'], 
         np.array([0, 1, 2]), 
         {'rmask': [1.0, 1.0, 1.0]}),
        
        # Two visits same location same band - accumulation
        ([0.5, 0.5], [0.5, 0.5], ['r', 'r'],
         [np.array([0]), np.array([0])],
         {'rmask': [2.0, 0.0, 0.0]}),
        
        # Band filtering - different bands
        ([0.5, 0.5], [0.5, 0.5], ['g', 'i'],
         np.array([0]),
         {'gmask': [1.0, 0.0, 0.0], 'imask': [1.0, 0.0, 0.0]}),
        
        # Empty visits
        ([], [], [],
         np.array([], dtype=int),
         {'rmask': [0.0, 0.0, 0.0], 'gmask': [0.0, 0.0, 0.0]}),
        
        # Multiple visits different locations
        ([0.5, 1.5], [0.5, 1.5], ['r', 'r'],
         [np.array([0]), np.array([1])],
         {'rmask': [1.0, 1.0, 0.0]}),
    ],
    ids=["single_visit_all_points", "accumulation", "band_filtering", 
         "empty_visits", "multiple_locations"]
)
def test_compute_daily_masks(basic_grid, mock_camera, visits_ra, visits_dec, 
                             visits_band, camera_indices, expected_mask_results):
    """Test _compute_daily_masks with various input scenarios."""
    ra_grid, dec_grid = basic_grid
    
    # Setup mock camera
    if isinstance(camera_indices, list):
        mock_camera.side_effect = camera_indices
    else:
        mock_camera.return_value = camera_indices
    
    # Build visits_use dict (rot is irrelevant when mocking camera)
    visits_use = {'ra': visits_ra, 
                  'dec': visits_dec, 
                  'band': visits_band, 
                  'rot': [0.0] * len(visits_ra)}
    
    actual_result = database._compute_daily_masks(visits_use, mock_camera, 
                                                  ra_grid, dec_grid)
    
    for mask_name, expected_values in expected_mask_results.items():
        assert actual_result[mask_name].tolist() == expected_values, \
            f"Expected {mask_name}={expected_values}, got {actual_result[mask_name].tolist()}"
    
    for mask_name in database.MASK_COLS:
        if mask_name not in expected_mask_results:
            assert (actual_result[mask_name] == 0.0).all(), \
                f"Expected {mask_name} to be all zeros, got {actual_result[mask_name]}"

def test_compute_daily_masks_camera_call(basic_grid, mock_camera):
    """Verify camera receives correct parameters."""
    ra_grid, dec_grid = basic_grid
    visit_ra, visit_dec, visit_rot = 10.0, -20.0, 45.0
    mock_camera.return_value = np.array([], dtype=int)
    
    visits_use = {'ra': [visit_ra], 'dec': [visit_dec], 
                  'band': ['r'], 'rot': [visit_rot]}
    database._compute_daily_masks(visits_use, mock_camera, ra_grid, dec_grid)
    
    mock_camera.assert_called_once_with(ra_grid, dec_grid, 
                                        visit_ra, visit_dec, visit_rot)


@pytest.mark.parametrize(
    "ra, dec, expected_visits",
    [
        (180.0, -20.0, 
         {'uvisits':1,'gvisits':0,'rvisits':1,
          'ivisits':0,'zvisits':1,'yvisits':0,}),
        (181.0, -19.0, 
         {'uvisits':1,'gvisits':0,'rvisits':0,
          'ivisits':1,'zvisits':1,'yvisits':0,}), 

    ],
    ids=["test1","test2"]
)
def test_compute_visits(ra, dec, expected_visits):

    ra_grid  = np.array([180.0, 181.0, 180.0, 181.0])
    dec_grid = np.array([-20.0, -20.0, -19.0, -19.0])
    mask = {'umask':[1,1,1,1],
            'gmask':[0,0,0,0],
            'rmask':[1,0,0,0],
            'imask':[0,0,0,1],
            'zmask':[1,1,1,1],
            'ymask':[0,0,0,0]
            }
    actual_visits = database._compute_visits(ra, dec, ra_grid, dec_grid, mask)

    for visits_name in database.VISIT_COLS:
        assert (actual_visits[visits_name] == expected_visits[visits_name]), \
            f"Expected {expected_visits[visits_name]}, got {actual_visits[visits_name]}"


# Tests for database insert and upsert functions using mocked cursor

def test_insert_daily_visits(test_date, test_member_id, test_visits):
    """Verify _insert_daily_visits executes correct SQL with proper parameters."""
    mock_cur = Mock()
    
    database._insert_daily_visits(mock_cur, test_date, test_member_id, test_visits)
    
    # Verify execute was called once
    assert mock_cur.execute.call_count == 1
    
    # Extract the SQL and parameters
    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]
    
    # Verify SQL structure
    assert "INSERT INTO member_daily_visits" in sql
    assert "time, member_id" in sql
    assert "umask" not in sql  # Verify it's using VISIT_COLS not MASK_COLS
    
    # Verify parameters in correct order
    assert params[0] == test_date
    assert params[1] == test_member_id
    assert params[2:] == (5.0, 3.0, 7.0, 2.0, 1.0, 0.0)


def test_insert_member_totals(test_date, test_visits):
    """Verify _insert_member_totals executes correct SQL with proper parameters."""
    mock_cur = Mock()
    member_id = 99
    
    database._insert_member_totals(mock_cur, test_date, member_id, test_visits)
    
    # Verify execute was called once
    assert mock_cur.execute.call_count == 1
    
    # Extract the SQL and parameters
    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]
    
    # Verify SQL structure
    assert "INSERT INTO member_totals" in sql
    assert "time, member_id" in sql
    
    # Verify parameters in correct order
    assert params[0] == test_date
    assert params[1] == member_id
    assert params[2:] == (5.0, 3.0, 7.0, 2.0, 1.0, 0.0)


def test_upsert_masks(test_group_id, test_masks):
    """Verify _upsert_masks executes correct upsert SQL."""
    mock_cur = Mock()
    mask_type = "latest"
    
    database._upsert_masks(mock_cur, test_group_id, mask_type, test_masks)
    
    # Verify execute was called once
    assert mock_cur.execute.call_count == 1
    
    # Extract the SQL and parameters
    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]
    
    # Verify SQL structure for upsert
    assert "INSERT INTO group_masks" in sql
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET" in sql
    
    # Verify first parameters are gid and mask_type
    assert params[0] == test_group_id
    assert params[1] == mask_type
    
    # Verify mask data is binary-encoded (psycopg2.Binary)
    assert len(params) == 8  # gid, mask_type, plus 6 mask columns


def test_insert_observability(test_date, test_member_id):
    """Verify _insert_observability executes correct SQL with proper parameters."""
    mock_cur = Mock()
    hrs = 8.5
    
    database._insert_observability(mock_cur, test_date, test_member_id, hrs)
    
    # Verify execute was called once
    assert mock_cur.execute.call_count == 1
    
    # Extract the SQL and parameters
    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]
    
    # Verify SQL structure
    assert "INSERT INTO member_observability" in sql
    assert "time, member_id, hrs_obs" in sql
    
    # Verify parameters in correct order
    assert params[0] == test_date
    assert params[1] == test_member_id  # Converted to Python int
    assert params[2] == 8.5  # Converted to Python float


def test_insert_observability_with_numpy_types(test_date):
    """Verify _insert_observability handles numpy types correctly."""
    mock_cur = Mock()
    member_id = np.int64(42)
    hrs = np.float64(7.25)
    
    database._insert_observability(mock_cur, test_date, member_id, hrs)
    
    # Extract parameters
    call_args = mock_cur.execute.call_args
    params = call_args[0][1]
    
    # Verify numpy types are converted to native Python types
    assert isinstance(params[1], int) and params[1] == 42
    assert isinstance(params[2], float) and params[2] == 7.25


def test_insert_obs_flags(test_date, test_member_id):
    """Verify _insert_obs_flags executes correct SQL with proper parameters."""
    mock_cur = Mock()
    flag = 1
    
    database._insert_obs_flags(mock_cur, test_date, test_member_id, flag)
    
    # Verify execute was called once
    assert mock_cur.execute.call_count == 1
    
    # Extract the SQL and parameters
    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]
    
    # Verify SQL structure
    assert "INSERT INTO member_obs_flags" in sql
    assert "time, member_id, obs_flag" in sql
    
    # Verify parameters in correct order
    assert params[0] == test_date
    assert params[1] == test_member_id
    assert params[2] == 1

def test_read_grid_and_mask_first_day():
    """_read_grid_and_mask returns zeros on first observation."""
    mock_cur = Mock()
    
    # Mock the group query result
    ra_grid = np.array([0.0, 1.0, 2.0])
    dec_grid = np.array([0.5, 1.5, 2.5])
    mock_cur.fetchone.side_effect = [
        {'ra_gr': 100.0, 'dec_gr': -30.0, 
         'ra_grid': ra_grid.tobytes(), 
         'dec_grid': dec_grid.tobytes()},
        None  # No mask row on first day
    ]
    
    result_ra, result_dec, mask_row = database._read_grid_and_mask(1, mock_cur)
    
    assert np.array_equal(result_ra, ra_grid)
    assert np.array_equal(result_dec, dec_grid)
    assert mask_row is None

def test_read_grid_and_mask_with_existing_mask():
    """_read_grid_and_mask retrieves existing cumulative mask."""
    mock_cur = Mock()
    
    ra_grid = np.array([0.0, 1.0, 2.0])
    dec_grid = np.array([0.5, 1.5, 2.5])
    existing_mask = np.array([10, 15, 5], dtype=np.int16)
    
    mock_cur.fetchone.side_effect = [
        {'ra_gr': 100.0, 'dec_gr': -30.0, 
         'ra_grid': ra_grid.tobytes(), 
         'dec_grid': dec_grid.tobytes()},
        {'umask': existing_mask.tobytes(), 
         'gmask': existing_mask.tobytes(),
         # ... all other masks
        }
    ]
    
    result_ra, result_dec, mask_row = database._read_grid_and_mask(1, mock_cur)
    
    assert mask_row is not None
    assert float(mask_row['umask'][0]) > 0  # Has data


def test_process_group_first_day(test_date, test_group_id, basic_grid, mock_camera, 
                                  test_masks, test_visits, monkeypatch):
    """Verify _process_group on first day (no existing mask)."""
    ra_grid, dec_grid = basic_grid
    
    mock_cur = Mock()
    mock_conn = Mock()
    
    # Mock dependencies
    monkeypatch.setattr(database, '_read_grid_and_mask', 
                       lambda gid, cur: (ra_grid, dec_grid, None))
    monkeypatch.setattr(database, '_compute_daily_masks', 
                       lambda visits, camera, ra_g, dec_g: test_masks)
    monkeypatch.setattr(database, '_compute_visits', 
                       lambda ra, dec, ra_g, dec_g, mask: test_visits)
    
    # Setup member query
    member_data = [
        {'member_id': 101, 'ra_mem': 0.5, 'dec_mem': 0.5},
        {'member_id': 102, 'ra_mem': 1.5, 'dec_mem': 1.5},
    ]
    mock_cur.fetchall.return_value = member_data
    
    # Call _process_group
    visits = {'ra': [0.5], 'dec': [0.5], 'band': ['r'], 'rot': [0.0]}
    database._process_group(test_group_id, test_date, visits, mock_camera, 
                           mock_conn, mock_cur)
    
    # Verify: 2 upserts + 1 member query + (2 members × 2 inserts) = 7 calls
    assert mock_cur.execute.call_count == 7
    mock_conn.commit.assert_called_once()


def test_process_group_with_mask_accumulation(test_date, test_group_id, basic_grid, 
                                               mock_camera, test_masks, test_visits, monkeypatch):
    """Verify _process_group accumulates masks correctly on subsequent days."""
    ra_grid, dec_grid = basic_grid
    
    mock_cur = Mock()
    mock_conn = Mock()
    
    # Create mask_row with binary data
    mask_row = {f'{b}mask': test_masks[f'{b}mask'].tobytes() for b in database.BANDS}
    
    # Mock dependencies
    monkeypatch.setattr(database, '_read_grid_and_mask',
                       lambda gid, cur: (ra_grid, dec_grid, mask_row))
    monkeypatch.setattr(database, '_compute_daily_masks',
                       lambda visits, camera, ra_g, dec_g: test_masks)
    monkeypatch.setattr(database, '_compute_visits',
                       lambda ra, dec, ra_g, dec_g, mask: test_visits)
    
    # Single member
    mock_cur.fetchall.return_value = [{'member_id': 101, 'ra_mem': 0.5, 'dec_mem': 0.5}]
    
    visits = {'ra': [0.5], 'dec': [0.5], 'band': ['r'], 'rot': [0.0]}
    database._process_group(test_group_id, test_date, visits, mock_camera,
                           mock_conn, mock_cur)
    
    # Verify: 2 upserts + 1 query + 2 inserts = 5 calls
    assert mock_cur.execute.call_count == 5
    mock_conn.commit.assert_called_once()


def test_process_group_multiple_members(test_date, test_group_id, basic_grid, 
                                        mock_camera, test_masks, test_visits, monkeypatch):
    """Verify _process_group correctly processes multiple members and visits."""
    ra_grid, dec_grid = basic_grid
    
    mock_cur = Mock()
    mock_conn = Mock()
    
    # Mock dependencies
    monkeypatch.setattr(database, '_read_grid_and_mask',
                       lambda gid, cur: (ra_grid, dec_grid, None))
    monkeypatch.setattr(database, '_compute_daily_masks',
                       lambda visits, camera, ra_g, dec_g: test_masks)
    monkeypatch.setattr(database, '_compute_visits',
                       lambda ra, dec, ra_g, dec_g, mask: test_visits)
    
    # Multiple members
    member_data = [
        {'member_id': 101, 'ra_mem': 0.0, 'dec_mem': 0.0},
        {'member_id': 102, 'ra_mem': 1.0, 'dec_mem': 1.0},
        {'member_id': 103, 'ra_mem': 2.0, 'dec_mem': 2.0},
    ]
    mock_cur.fetchall.return_value = member_data
    
    visits = {'ra': [0.5, 1.5], 'dec': [0.5, 1.5], 'band': ['r', 'g'], 'rot': [0.0, 45.0]}
    database._process_group(test_group_id, test_date, visits, mock_camera,
                           mock_conn, mock_cur)
    
    # Verify: 2 upserts + 1 query + (3 members × 2 inserts) = 9 calls
    assert mock_cur.execute.call_count == 9
    mock_conn.commit.assert_called_once()


# Tests for populate_database

def test_populate_database_single_group(test_date, mock_camera, monkeypatch):
    """Verify populate_database processes a single group correctly."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    
    # Mock group query result
    group_data = [
        {'group_id': 1, 'ra_gr': 100.0, 'dec_gr': -30.0}
    ]
    mock_cur.fetchall.return_value = group_data
    
    # Mock get_visit_metadata
    mock_visits_use = {'ra': [100.5], 'dec': [-29.5], 'band': ['r'], 'rot': [0.0]}
    monkeypatch.setattr(database, 'get_visit_metadata',
                       lambda visits, ra, dec: mock_visits_use)
    
    # Mock _process_group
    mock_process_group = Mock()
    monkeypatch.setattr(database, '_process_group', mock_process_group)
    
    # Create mock visits DataFrame
    import pandas as pd
    visits = pd.DataFrame({'s_ra': [100.5], 's_dec': [-29.5]})
    
    database.populate_database(mock_conn, mock_cur, mock_camera, user_id, 
                               visits, test_date)
    
    # Verify group query was executed
    assert mock_cur.execute.called
    
    # Verify _process_group was called once with correct args
    mock_process_group.assert_called_once()
    call_args = mock_process_group.call_args
    assert call_args[0][0] == 1  # group_id
    assert call_args[0][1] == test_date


def test_populate_database_multiple_groups(test_date, mock_camera, monkeypatch):
    """Verify populate_database iterates through all groups."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    
    # Mock multiple groups
    group_data = [
        {'group_id': 1, 'ra_gr': 100.0, 'dec_gr': -30.0},
        {'group_id': 2, 'ra_gr': 150.0, 'dec_gr': -45.0},
        {'group_id': 3, 'ra_gr': 200.0, 'dec_gr': -60.0},
    ]
    mock_cur.fetchall.return_value = group_data
    
    # Mock get_visit_metadata to return empty dict (no visits for any group)
    monkeypatch.setattr(database, 'get_visit_metadata',
                       lambda visits, ra, dec: {'ra': [], 'dec': [], 'band': [], 'rot': []})
    
    # Mock _process_group
    mock_process_group = Mock()
    monkeypatch.setattr(database, '_process_group', mock_process_group)
    
    import pandas as pd
    visits = pd.DataFrame()
    
    database.populate_database(mock_conn, mock_cur, mock_camera, user_id, 
                               visits, test_date)
    
    # Verify _process_group was called once for each group
    assert mock_process_group.call_count == 3
    
    # Verify group_ids were processed in order
    call_group_ids = [call[0][0] for call in mock_process_group.call_args_list]
    assert call_group_ids == [1, 2, 3]


def test_populate_database_with_shared_state(test_date, mock_camera, monkeypatch):
    """Verify populate_database updates shared_state progress correctly."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_shared_state = Mock()
    
    # Mock groups
    group_data = [
        {'group_id': 1, 'ra_gr': 100.0, 'dec_gr': -30.0},
        {'group_id': 2, 'ra_gr': 150.0, 'dec_gr': -45.0},
    ]
    mock_cur.fetchall.return_value = group_data
    
    monkeypatch.setattr(database, 'get_visit_metadata',
                       lambda visits, ra, dec: {'ra': [], 'dec': [], 'band': [], 'rot': []})
    
    mock_process_group = Mock()
    monkeypatch.setattr(database, '_process_group', mock_process_group)
    
    import pandas as pd
    visits = pd.DataFrame()
    
    database.populate_database(mock_conn, mock_cur, mock_camera, user_id, 
                               visits, test_date, shared_state=mock_shared_state)
    
    # Verify shared_state.write was called twice (once per group)
    assert mock_shared_state.write.call_count == 2
    
    # Verify progress updates
    calls = mock_shared_state.write.call_args_list
    
    # First group: 1/2 = 0.5 progress
    first_call_kwargs = calls[0][1]
    assert first_call_kwargs['progress'] == 0.5
    assert "1/2" in first_call_kwargs['progress_msg']
    
    # Second group: 2/2 = 1.0 progress
    second_call_kwargs = calls[1][1]
    assert second_call_kwargs['progress'] == 1.0
    assert "2/2" in second_call_kwargs['progress_msg']


def test_populate_database_no_groups(test_date, mock_camera, monkeypatch):
    """Verify populate_database handles case with no groups."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    
    # Mock empty group query result
    mock_cur.fetchall.return_value = []
    
    mock_process_group = Mock()
    monkeypatch.setattr(database, '_process_group', mock_process_group)
    
    import pandas as pd
    visits = pd.DataFrame()
    
    database.populate_database(mock_conn, mock_cur, mock_camera, user_id, 
                               visits, test_date)
    
    # Verify _process_group was not called
    mock_process_group.assert_not_called()


# Tests for populate_forecast

def test_populate_forecast_single_member(test_date, monkeypatch):
    """Verify populate_forecast processes single member correctly."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_insert_obs = Mock()
    
    # Mock member query
    member_data = [
        {'member_id': 101, 'ra_mem': 100.0, 'dec_mem': -30.0}
    ]
    mock_cur.fetchall.return_value = member_data
    
    # Mock external functions
    mock_az = np.array([180.0])
    mock_el = np.array([45.0])
    mock_t_utc = np.array([0.0])
    
    monkeypatch.setattr(database, 'get_az_el', 
                       lambda ra, dec, date: (mock_az, mock_el, mock_t_utc))
    monkeypatch.setattr(database, 'daily_observability',
                       lambda el, date, t_utc: 8.5)
    monkeypatch.setattr(database, '_insert_observability', mock_insert_obs)
    
    # Call populate_forecast
    database.populate_forecast(mock_conn, mock_cur, user_id, test_date)
    
    # Verify member query was executed
    assert mock_cur.execute.called
    call_args = mock_cur.execute.call_args_list[0]
    assert 'members' in call_args[0][0]
    assert call_args[0][1][0] == user_id
    
    # Verify _insert_observability was called once with correct member_id
    mock_insert_obs.assert_called_once()
    call_args = mock_insert_obs.call_args[0]
    assert call_args[1] == test_date
    assert call_args[2] == 101  # member_id
    assert call_args[3] == 8.5  # hours value
    
    mock_conn.commit.assert_called_once()


def test_populate_forecast_multiple_members(test_date, monkeypatch):
    """Verify populate_forecast processes multiple members."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_insert_obs = Mock()
    
    # Mock multiple members
    member_data = [
        {'member_id': 101, 'ra_mem': 100.0, 'dec_mem': -30.0},
        {'member_id': 102, 'ra_mem': 150.0, 'dec_mem': -45.0},
        {'member_id': 103, 'ra_mem': 200.0, 'dec_mem': -60.0},
    ]
    mock_cur.fetchall.return_value = member_data
    
    # Mock external functions to return arrays matching number of members
    mock_az = np.array([180.0, 190.0, 200.0])
    mock_el = np.array([45.0, 30.0, 15.0])
    mock_t_utc = np.array([0.0, 0.0, 0.0])
    
    monkeypatch.setattr(database, 'get_az_el',
                       lambda ra, dec, date: (mock_az, mock_el, mock_t_utc))
    monkeypatch.setattr(database, 'daily_observability',
                       lambda el, date, t_utc: 8.5)
    monkeypatch.setattr(database, '_insert_observability', mock_insert_obs)
    
    # Call populate_forecast
    database.populate_forecast(mock_conn, mock_cur, user_id, test_date)
    
    # Verify _insert_observability was called 3 times with correct member_ids
    assert mock_insert_obs.call_count == 3
    
    calls = mock_insert_obs.call_args_list
    member_ids = [call[0][2] for call in calls]  # member_id is 3rd arg
    assert member_ids == [101, 102, 103]
    
    mock_conn.commit.assert_called_once()


# Tests for populate_obs_flags

def test_populate_obs_flags_single_member(test_date, monkeypatch):
    """Verify populate_obs_flags processes single member."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_insert_obs_flags = Mock()
    
    # Mock member query
    member_data = [
        {'member_id': 101, 'ra_mem': 100.0, 'dec_mem': -30.0}
    ]
    mock_cur.fetchall.return_value = member_data
    
    # Mock _insert_obs_flags since it's already tested separately
    monkeypatch.setattr(database, '_insert_obs_flags', mock_insert_obs_flags)
    
    # Create flags array matching number of members
    flags = np.array([1])
    
    # Call populate_obs_flags
    database.populate_obs_flags(mock_conn, mock_cur, user_id, test_date, flags)
    
    # Verify member query
    assert mock_cur.execute.called
    call_args = mock_cur.execute.call_args_list[0]
    assert 'members' in call_args[0][0]
    
    # Verify _insert_obs_flags was called once with correct member_id and flag
    mock_insert_obs_flags.assert_called_once()
    call_args = mock_insert_obs_flags.call_args[0]
    assert call_args[1] == test_date
    assert call_args[2] == 101  # member_id
    assert call_args[3] == 1    # flag
    
    mock_conn.commit.assert_called_once()


def test_populate_obs_flags_multiple_members(test_date, monkeypatch):
    """Verify populate_obs_flags processes multiple members with different flags."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_insert_obs_flags = Mock()
    
    # Mock multiple members
    member_data = [
        {'member_id': 101, 'ra_mem': 100.0, 'dec_mem': -30.0},
        {'member_id': 102, 'ra_mem': 150.0, 'dec_mem': -45.0},
    ]
    mock_cur.fetchall.return_value = member_data
    
    # Mock _insert_obs_flags
    monkeypatch.setattr(database, '_insert_obs_flags', mock_insert_obs_flags)
    
    # Flags array
    flags = np.array([1, 0])
    
    database.populate_obs_flags(mock_conn, mock_cur, user_id, test_date, flags)
    
    # Verify _insert_obs_flags was called twice with correct member_ids and flags
    assert mock_insert_obs_flags.call_count == 2
    
    calls = mock_insert_obs_flags.call_args_list
    assert calls[0][0][2] == 101  # first member_id
    assert calls[0][0][3] == 1    # first flag
    assert calls[1][0][2] == 102  # second member_id
    assert calls[1][0][3] == 0    # second flag
    
    mock_conn.commit.assert_called_once()


# Tests for populate_history

def test_populate_history_sim_path_with_data(mock_camera, monkeypatch):
    """Verify populate_history processes SIM data correctly."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_populate_db = Mock()
    
    # Mock config
    monkeypatch.setattr(database, 'QUERY_TYPE', 'SIM')
    monkeypatch.setattr(database, 'SIM_HIST', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(database, 'SIM_START', pd.Timestamp('2026-08-13'))
    monkeypatch.setattr(database, 'SIM_LSST_DB', '/path/to/db')
    
    # Mock external functions
    monkeypatch.setattr(database, 'get_base_mjd', lambda db: 60000)
    monkeypatch.setattr(database, 'date_to_nightnum',
                       lambda date, mjd: 100)  # return constant
    
    # Mock sim_service_range to return visits for some nights
    mock_visits_sim = pd.DataFrame({'s_ra': [100.0, 101.0], 's_dec': [-30.0, -31.0]})
    monkeypatch.setattr(database, 'sim_service_range',
                       lambda min_night, max_night: {100: mock_visits_sim, 101: mock_visits_sim})
    
    # Mock simulation_dates to return 3 dates
    test_dates = [
        pd.Timestamp('2026-08-10'),
        pd.Timestamp('2026-08-11'),
        pd.Timestamp('2026-08-12'),
    ]
    monkeypatch.setattr(database, 'simulation_dates',
                       lambda start, end: test_dates)
    
    # Mock populate_database
    monkeypatch.setattr(database, 'populate_database', mock_populate_db)
    
    # Call populate_history
    database.populate_history(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify populate_database was called 3 times (once per date)
    assert mock_populate_db.call_count == 3
    
    # Verify correct date parameters
    dates_called = [call[0][5] for call in mock_populate_db.call_args_list]
    assert dates_called == test_dates


def test_populate_history_sim_path_missing_data(mock_camera, monkeypatch):
    """Verify populate_history handles missing data in SIM path."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_populate_db = Mock()
    
    monkeypatch.setattr(database, 'QUERY_TYPE', 'SIM')
    monkeypatch.setattr(database, 'SIM_HIST', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(database, 'SIM_START', pd.Timestamp('2026-08-13'))
    monkeypatch.setattr(database, 'SIM_LSST_DB', '/path/to/db')
    monkeypatch.setattr(database, 'get_base_mjd', lambda db: 60000)
    monkeypatch.setattr(database, 'date_to_nightnum',
                       lambda date, mjd: 100)
    
    # Empty visits_by_night dict (no data)
    monkeypatch.setattr(database, 'sim_service_range',
                       lambda min_night, max_night: {})
    
    test_dates = [
        pd.Timestamp('2026-08-10'),
        pd.Timestamp('2026-08-11'),
    ]
    monkeypatch.setattr(database, 'simulation_dates',
                       lambda start, end: test_dates)
    
    monkeypatch.setattr(database, 'populate_database', mock_populate_db)
    
    database.populate_history(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify populate_database was NOT called (no data available)
    mock_populate_db.assert_not_called()


def test_populate_history_rsv_path_with_data(mock_camera, monkeypatch):
    """Verify populate_history processes RSV data correctly."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_populate_db = Mock()
    mock_rsv_service = Mock()
    
    monkeypatch.setattr(database, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(database, 'SIM_HIST', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(database, 'SIM_START', pd.Timestamp('2026-08-12'))
    
    # Mock simulation_dates
    test_dates = [
        pd.Timestamp('2026-08-10'),
        pd.Timestamp('2026-08-11'),
    ]
    monkeypatch.setattr(database, 'simulation_dates',
                       lambda start, end: test_dates)
    
    # Mock rsv_service to return data
    mock_visits_rsv = pd.DataFrame({'s_ra': [100.0], 's_dec': [-30.0]})
    mock_rsv_service.return_value = mock_visits_rsv
    monkeypatch.setattr(database, 'rsv_service', mock_rsv_service)
    
    monkeypatch.setattr(database, 'populate_database', mock_populate_db)
    
    database.populate_history(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify rsv_service was called for each date
    assert mock_rsv_service.call_count == 2
    
    # Verify populate_database was called 2 times
    assert mock_populate_db.call_count == 2


def test_populate_history_rsv_path_missing_data(mock_camera, monkeypatch):
    """Verify populate_history handles missing RSV data gracefully."""
    user_id = 1
    
    mock_cur = Mock()
    mock_conn = Mock()
    mock_populate_db = Mock()
    mock_rsv_service = Mock()
    
    monkeypatch.setattr(database, 'QUERY_TYPE', 'RSV')
    monkeypatch.setattr(database, 'SIM_HIST', pd.Timestamp('2026-08-10'))
    monkeypatch.setattr(database, 'SIM_START', pd.Timestamp('2026-08-12'))
    
    test_dates = [
        pd.Timestamp('2026-08-10'),
        pd.Timestamp('2026-08-11'),
    ]
    monkeypatch.setattr(database, 'simulation_dates',
                       lambda start, end: test_dates)
    
    # rsv_service returns empty DataFrame (no data)
    mock_rsv_service.return_value = pd.DataFrame()
    monkeypatch.setattr(database, 'rsv_service', mock_rsv_service)
    
    monkeypatch.setattr(database, 'populate_database', mock_populate_db)
    
    database.populate_history(mock_conn, mock_cur, mock_camera, user_id)
    
    # Verify rsv_service was still called
    assert mock_rsv_service.call_count == 2
    
    # But populate_database should not be called (no data)
    mock_populate_db.assert_not_called()

#@pytest.mark.parametrize(
#    "",
#    [
#        (),

#        (),

#    ],
#    ids=["",""]
#)
#def test_add_mask_grid():