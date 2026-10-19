import pytest
from unittest.mock import Mock, patch

from main import run


def test_run_server() -> None:
    """Test server startup (integration test)."""
    with patch("uvicorn.run") as mock_run:
        with patch("main.create_app") as mock_create_app:
            with patch("main.load_settings") as mock_load_settings:
                mock_settings = Mock()
                mock_app = Mock()
                mock_load_settings.return_value = mock_settings
                mock_create_app.return_value = mock_app
                
                run()
                
                mock_create_app.assert_called_once_with(mock_settings)
                mock_run.assert_called_once()