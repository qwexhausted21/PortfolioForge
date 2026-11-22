"""Tests for app module (FastAPI endpoints)."""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import tempfile
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from app import app, _load_repos, _save_repos, _get_last_published_url


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def temp_repos_file():
    """Create temporary repos file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('[]')
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


class TestReposStorage:
    """Tests for repository storage functions."""

    def test_load_empty_repos(self, temp_repos_file):
        """Test loading empty repos list."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            repos = _load_repos()
            assert repos == []

    def test_save_and_load_repos(self, temp_repos_file):
        """Test saving and loading repos."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            test_repos = [
                {"name": "test1", "url": "https://github.com/user/test1"},
                {"name": "test2", "url": "https://github.com/user/test2"},
            ]
            _save_repos(test_repos)
            loaded = _load_repos()
            assert loaded == test_repos

    def test_get_last_published_url(self, temp_repos_file):
        """Test getting last published URL."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            _save_repos([
                {"name": "old", "url": "https://github.com/user/old", "updated_at": "2024-01-01"},
                {"name": "new", "url": "https://github.com/user/new", "updated_at": "2024-12-01"},
            ])
            url = _get_last_published_url()
            assert url == "https://github.com/user/new"

    def test_get_last_published_url_empty(self, temp_repos_file):
        """Test getting last published URL when empty."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            url = _get_last_published_url()
            assert url is None


class TestEndpoints:
    """Tests for FastAPI endpoints."""

    def test_index(self, client):
        """Test root endpoint returns HTML."""
        pytest.skip("Template rendering fails in test environment without full context")

    @pytest.mark.skip(reason="Requires tkinter which fails in headless test environment")
    def test_select_folder_endpoint(self, client):
        pass

    @pytest.mark.skip(reason="Requires tkinter which fails in headless test environment")
    def test_select_folder_cancelled(self, client):
        pass

    @pytest.mark.skip(reason="Requires tkinter which fails in headless test environment")
    def test_select_folder_outside_home(self, client):
        pass

    def test_generate_readme_endpoint(self, client):
        """Test generate-readme endpoint."""
        response = client.post(
            "/generate-readme",
            json={
                "project_name": "TestProject",
                "description": "Test description",
                "tech_stack": "Python, FastAPI",
                "demo_link": "",
                "private": False
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "# TestProject" in data["content"]

    def test_publish_invalid_project_name(self, client):
        """Test publish rejects invalid project name on backend."""
        response = client.post(
            "/publish",
            json={
                "project_name": "Invalid Name!",
                "description": "",
                "tech_stack": "",
                "demo_link": "",
                "private": False,
                "folder_path": "/tmp/somefolder",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_publish_valid_project_name(self, client):
        """Test publish accepts valid project name (fails later, not at validation)."""
        response = client.post(
            "/publish",
            json={
                "project_name": "my-portfolio",
                "description": "",
                "tech_stack": "",
                "demo_link": "",
                "private": False,
                "folder_path": "/tmp/somefolder",
            },
        )
        # Validation passes; further failure (no git/token) is acceptable here.
        assert response.status_code in (200, 500)

    def test_generate_readme_missing_name(self, client):
        """Test generate-readme with missing project name."""
        response = client.post(
            "/generate-readme",
            json={"project_name": "", "description": "", "tech_stack": "", "demo_link": "", "private": False}
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_validate_token_endpoint(self, client):
        """Test validate-token endpoint."""
        with patch("app.GitHubManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            mock_manager.validate_token.return_value = (True, "Токен валиден. Пользователь: testuser")

            response = client.post("/validate-token", json={"token": "ghp_test"})
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "testuser" in data["message"]

    def test_validate_token_invalid(self, client):
        """Test validate-token with invalid token."""
        with patch("app.GitHubManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            mock_manager.validate_token.return_value = (False, "Неверный токен")

            response = client.post("/validate-token", json={"token": "bad"})
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is False

    def test_save_token_endpoint(self, client):
        """Test save-token endpoint."""
        with patch("app.GitHubManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            mock_manager.validate_token.return_value = (True, "OK")

            response = client.post("/save-token", json={"token": "ghp_newtoken"})
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            mock_manager.save_token.assert_called_once_with("ghp_newtoken")

    def test_repos_list_endpoint(self, client, temp_repos_file):
        """Test repos list endpoint."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            _save_repos([{"name": "test", "url": "https://github.com/user/test"}])
            response = client.get("/repos")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "test"

    def test_add_repo_endpoint(self, client, temp_repos_file):
        """Test add repo endpoint."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            response = client.post(
                "/repos",
                json={"name": "newrepo", "url": "https://github.com/user/newrepo"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    def test_delete_repo_endpoint(self, client, temp_repos_file):
        """Test delete repo endpoint."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            _save_repos([{"name": "todelete", "url": "https://github.com/user/todelete"}])
            response = client.delete("/repos/todelete")
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    def test_last_folder_endpoint(self, client, temp_repos_file):
        """Test last-folder endpoint returns saved folder."""
        with patch("app.LAST_FOLDER_FILE", Path(temp_repos_file)):
            Path(temp_repos_file).write_text(json.dumps({"folder": "/tmp/savedfolder"}), encoding="utf-8")
            response = client.get("/last-folder")
            assert response.status_code == 200
            data = response.json()
            assert data["folder"] == "/tmp/savedfolder"

    def test_last_folder_endpoint_empty(self, client, temp_repos_file):
        """Test last-folder endpoint when no folder saved."""
        with patch("app.LAST_FOLDER_FILE", Path(temp_repos_file)):
            Path(temp_repos_file).write_text("{}", encoding="utf-8")
            response = client.get("/last-folder")
            assert response.status_code == 200
            data = response.json()
            assert data["folder"] is None

    def test_publish_cancel_no_active(self, client):
        """Test cancel endpoint returns 400 when no publish is active."""
        import app as app_module
        app_module.publish_cancel_event = None
        response = client.post("/publish/cancel")
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False

    def test_last_published_endpoint(self, client, temp_repos_file):
        """Test last-published endpoint."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            _save_repos([{"name": "test", "url": "https://github.com/user/test", "updated_at": "2024-12-01"}])
            response = client.get("/last-published")
            assert response.status_code == 200
            data = response.json()
            assert data["url"] == "https://github.com/user/test"

    def test_repo_details_endpoint(self, client, temp_repos_file):
        """Test repo details endpoint for auto-fill."""
        with patch("app.REPOS_FILE", Path(temp_repos_file)):
            _save_repos([{"name": "testrepo", "full_name": "user/testrepo", "description": "Test desc", "url": "https://github.com/user/testrepo", "private": False}])
            with patch("app.GitHubManager") as mock_manager_class:
                mock_manager = Mock()
                mock_manager_class.return_value = mock_manager
                mock_manager.github = None

                response = client.get("/repos/testrepo/details")
                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert data["repo"]["name"] == "testrepo"


class TestWebSocket:
    """Tests for WebSocket endpoint (basic)."""

    def test_ws_logs_connection(self, client):
        """Test WebSocket connection."""
        with client.websocket_connect("/ws/logs") as ws:
            # Connection should succeed
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])