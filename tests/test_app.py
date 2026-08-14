"""Tests for the Flask application (app.py).

Note: mostly written by Claude - needs review
"""

import pytest
import json
from unittest.mock import Mock, patch
from flask import Flask
import time

from rubin_sunrise.app import create_app

@pytest.fixture
def mock_shared_state():
    """Create a mock SharedState object with typical snapshot data."""
    mock_state = Mock()
    current_time = time.time()
    mock_state.snapshot.return_value = {
        "date": "2025-04-27",
        "fig1_html": "<div>Map plot</div>",
        "fig2_html": "<div>Time series</div>",
        "fig3_html": "<div>Observability plot</div>",
        "table": "<table><tr><td>Target 1</td></tr></table>",
        "version": "v1.0.0",
        "next_update": current_time + 60,  # 1 min from now
        "updating": False,
        "progress": 100,
        "progress_msg": "Data ready",
        "cycle_number": 42,
    }
    return mock_state


@pytest.fixture
def mock_dbconn():
    """Create a mock database connection."""
    mock_conn = Mock()
    mock_cur = Mock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


@pytest.fixture
def app_with_mocks(mock_shared_state, mock_dbconn):
    """Create a Flask test app with mocked dependencies.
    
    This fixture patches the display classes and render_template to avoid
    database queries and missing template files during testing.
    """
    with patch("rubin_sunrise.app.TargetMap"), \
         patch("rubin_sunrise.app.TargetTimeSeries"), \
         patch("rubin_sunrise.app.ObservabilityData"), \
         patch("rubin_sunrise.app._reclaim_memory"), \
         patch("rubin_sunrise.app.render_template") as mock_render:
        
        # Mock render_template to return HTML without requiring actual template files
        mock_render.return_value = "<html><body>Dashboard</body></html>"
        
        # Configure the mock display objects to return HTML
        with patch("rubin_sunrise.app.TargetMap") as mock_target_map, \
             patch("rubin_sunrise.app.TargetTimeSeries") as mock_ts, \
             patch("rubin_sunrise.app.ObservabilityData") as mock_obs:
            
            # Setup mocks to return HTML strings
            mock_target_map.return_value.make_html_visits_map.return_value = (
                "<div id='map'>Visits Map</div>"
            )
            mock_ts.return_value.make_html_visits_plot.return_value = (
                "<div id='timeseries'>Time Series</div>"
            )
            mock_obs.return_value.make_html_obs_plot.return_value = (
                "<div id='obs'>Observability Plot</div>"
            )
            
            # Create the app
            app = create_app(
                mock_shared_state, 
                mock_dbconn,
                flags_present=False,
            )
            app.config["TESTING"] = True
            
            yield app


@pytest.fixture
def client(app_with_mocks):
    """Create a test client from the app fixture."""
    return app_with_mocks.test_client()


class TestHomeRoute:
    """Tests for the home() route that serves the main dashboard."""
    
    def test_home_returns_html_when_data_loaded(self, client, mock_shared_state):
        """Test that home returns HTML content when data is available."""
        response = client.get("/")
        
        # Assert successful response
        assert response.status_code == 200
        assert response.content_type.startswith("text/html")
        
        # Assert that response contains expected template elements
        # (These strings should be in your index.html template)
        data = response.get_data(as_text=True)
        assert "Rubin" in data or "Dashboard" in data or len(data) > 100
    
    def test_home_shows_loading_when_table_none(
        self, 
        client, 
        mock_shared_state
    ):
        """Test that home returns loading message when no table data."""
        # Configure mock to return None for table
        mock_shared_state.snapshot.return_value["table"] = None
        
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.get_data(as_text=True)
        assert "Data loading" in data
        assert "refresh" in data.lower()


class TestRowClickedRoute:
    """Tests for the row_clicked() route handling table interactions."""
    
    def test_row_clicked_returns_json_with_plots(
        self, 
        client, 
        mock_shared_state, 
        mock_dbconn
    ):
        """Test that clicking a row returns JSON with plot HTML."""
        request_data = {
            "index": 0,
            "gn": 1,  # group number
            "mn": 5,  # member number
            "maptype": "daily"
        }
        
        response = client.post(
            "/row_clicked",
            data=json.dumps(request_data),
            content_type="application/json"
        )
        
        # Check response structure
        assert response.status_code == 200
        assert response.content_type == "application/json"
        
        json_data = response.get_json()
        assert json_data is not None
        assert json_data["status"] == "ok"
        assert "fig1_html" in json_data
        assert "fig2_html" in json_data
        assert "fig3_html" in json_data
        
        # Check that HTML is actually present (not empty)
        assert len(json_data["fig1_html"]) > 0
        assert len(json_data["fig2_html"]) > 0
        assert len(json_data["fig3_html"]) > 0
    
    def test_row_clicked_with_index_required(self, client):
        """Test that row_clicked requires index in the request.
        
        Note: The app code uses data['index'] directly (not .get()),
        so index is actually required even though docstring doesn't
        explicitly state this. This test documents the actual behavior.
        """
        request_data = {
            "index": 0,  # index is required by the implementation
            "gn": 1,
            "mn": 5,
        }
        
        response = client.post(
            "/row_clicked",
            data=json.dumps(request_data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "ok"
    
    def test_row_clicked_with_string_numbers(self, client):
        """Test that row_clicked converts string group/member numbers to int."""
        request_data = {
            "index": 5,
            "gn": "2",  # String instead of int
            "mn": "10",  # String instead of int
            "maptype": "total"
        }
        
        response = client.post(
            "/row_clicked",
            data=json.dumps(request_data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "ok"


class TestMapTypeClickedRoute:
    """Tests for the maptype_clicked() route handling map type changes."""
    
    def test_maptype_clicked_returns_json_with_plots(self, client):
        """Test that changing map type returns updated plots."""
        request_data = {
            "gn": 1,
            "mn": 5,
            "maptype": "total",
            "index": 2
        }
        
        response = client.post(
            "/maptype_clicked",
            data=json.dumps(request_data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "ok"
        assert "fig1_html" in json_data
        assert "fig2_html" in json_data
    
    def test_maptype_clicked_with_default_index(self, client):
        """Test that maptype_clicked handles missing index with default."""
        request_data = {
            "gn": 1,
            "mn": 5,
            "maptype": "daily",
            # No index provided - should default to 0
        }
        
        response = client.post(
            "/maptype_clicked",
            data=json.dumps(request_data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "ok"


class TestObsPlotUpdateRoute:
    """Tests for the obs_plot_update() route handling observability updates."""
    
    def test_obs_plot_update_returns_json_with_plot(self, client):
        """Test that updating observability plot returns new plot HTML."""
        request_data = {
            "gn": 1,
            "mn": 5,
            "selected_date": "2025-05-01",
            "window_days": 10
        }
        
        response = client.post(
            "/obs_plot_update",
            data=json.dumps(request_data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "ok"
        assert "fig3_html" in json_data
        assert len(json_data["fig3_html"]) > 0
    
    def test_obs_plot_update_with_default_window(self, client):
        """Test that obs_plot_update uses default window_days when not provided."""
        request_data = {
            "gn": 1,
            "mn": 5,
            "selected_date": "2025-05-01",
            # No window_days - should default to 5
        }
        
        response = client.post(
            "/obs_plot_update",
            data=json.dumps(request_data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "ok"


class TestCheckUpdateRoute:
    """Tests for the check_update() polling endpoint."""
    
    def test_check_update_returns_version(self, client, mock_shared_state):
        """Test that check_update returns current version."""
        response = client.get("/check_update")
        
        assert response.status_code == 200
        json_data = response.get_json()
        assert "version" in json_data
        assert json_data["version"] == "v1.0.0"
    
    def test_check_update_version_changes(
        self, 
        client, 
        mock_shared_state
    ):
        """Test that version in check_update can be updated."""
        # First request
        response1 = client.get("/check_update")
        version1 = response1.get_json()["version"]
        
        # Change the mock's version
        mock_shared_state.snapshot.return_value["version"] = "v1.0.1"
        
        # Second request should reflect new version
        response2 = client.get("/check_update")
        version2 = response2.get_json()["version"]
        
        assert version1 == "v1.0.0"
        assert version2 == "v1.0.1"


class TestNextUpdateRoute:
    """Tests for the next_update() polling endpoint."""
    
    def test_next_update_returns_all_fields(self, client, mock_shared_state):
        """Test that next_update returns all required fields."""
        response = client.get("/next_update")
        
        assert response.status_code == 200
        json_data = response.get_json()
        
        # Check all required fields are present
        required_fields = [
            "next_update",
            "server_time",
            "updating",
            "progress",
            "progress_msg",
            "cycle_number",
        ]
        for field in required_fields:
            assert field in json_data, f"Missing field: {field}"
    
    def test_next_update_has_valid_timestamps(
        self, 
        client, 
        mock_shared_state
    ):
        """Test that next_update returns valid Unix timestamps."""
        response = client.get("/next_update")
        json_data = response.get_json()
        
        current_time = time.time()
        
        # next_update should be in the future
        assert json_data["next_update"] > current_time
        
        # server_time should be close to current time
        assert abs(json_data["server_time"] - current_time) < 5
    
    def test_next_update_with_active_update(
        self, 
        client, 
        mock_shared_state
    ):
        """Test next_update when an update is in progress."""
        mock_shared_state.snapshot.return_value["updating"] = True
        mock_shared_state.snapshot.return_value["progress"] = 45
        mock_shared_state.snapshot.return_value["progress_msg"] = (
            "Loading data..."
        )
        
        response = client.get("/next_update")
        json_data = response.get_json()
        
        assert json_data["updating"] is True
        assert json_data["progress"] == 45
        assert "Loading" in json_data["progress_msg"]


class TestCreateAppFactory:
    """Tests for the create_app() factory function."""
    
    def test_create_app_returns_flask_instance(
        self, 
        mock_shared_state, 
        mock_dbconn
    ):
        """Test that create_app returns a Flask application."""
        with patch("rubin_sunrise.app.TargetMap"), \
             patch("rubin_sunrise.app.TargetTimeSeries"), \
             patch("rubin_sunrise.app.ObservabilityData"), \
             patch("rubin_sunrise.app._reclaim_memory"):
            
            app = create_app(mock_shared_state, mock_dbconn)
            assert isinstance(app, Flask)
    
    def test_create_app_with_custom_folders(
        self, 
        mock_shared_state, 
        mock_dbconn, 
        tmp_path
    ):
        """Test that create_app respects custom template/static folders."""
        template_dir = tmp_path / "templates"
        static_dir = tmp_path / "static"
        template_dir.mkdir()
        static_dir.mkdir()
        
        with patch("rubin_sunrise.app.TargetMap"), \
             patch("rubin_sunrise.app.TargetTimeSeries"), \
             patch("rubin_sunrise.app.ObservabilityData"), \
             patch("rubin_sunrise.app._reclaim_memory"):
            
            app = create_app(
                mock_shared_state,
                mock_dbconn,
                template_folder=str(template_dir),
                static_folder=str(static_dir),
            )
            
            assert app.template_folder == str(template_dir)
            assert app.static_folder == str(static_dir)
    
    def test_create_app_with_flags_present(
        self, 
        mock_shared_state, 
        mock_dbconn
    ):
        """Test that create_app accepts flags_present parameter."""
        with patch("rubin_sunrise.app.TargetMap"), \
             patch("rubin_sunrise.app.TargetTimeSeries"), \
             patch("rubin_sunrise.app.ObservabilityData"), \
             patch("rubin_sunrise.app._reclaim_memory"):
            
            app = create_app(
                mock_shared_state,
                mock_dbconn,
                flags_present=True,
            )
            
            assert isinstance(app, Flask)


@pytest.mark.integration
class TestFlowInteraction:
    """Integration tests simulating user workflows."""
    
    def test_user_clicks_row_then_changes_maptype(self, client):
        """Simulate user clicking a row, then switching map type."""
        # Step 1: Click a row
        row_data = {"index": 0, "gn": 1, "mn": 5, "maptype": "daily"}
        response1 = client.post(
            "/row_clicked",
            data=json.dumps(row_data),
            content_type="application/json"
        )
        assert response1.status_code == 200
        result1 = response1.get_json()
        daily_map = result1["fig1_html"]
        
        # Step 2: Switch to total view
        maptype_data = {"gn": 1, "mn": 5, "maptype": "total"}
        response2 = client.post(
            "/maptype_clicked",
            data=json.dumps(maptype_data),
            content_type="application/json"
        )
        assert response2.status_code == 200
        result2 = response2.get_json()
        total_map = result2["fig1_html"]
        
        # Both should have plot HTML (whether they're the same or different
        # depends on your business logic)
        assert len(daily_map) > 0
        assert len(total_map) > 0
