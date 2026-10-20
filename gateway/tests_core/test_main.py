from unittest.mock import patch

from app.config import Settings
from app.main import run


def test_run_server(tmp_path) -> None:
    settings = Settings(gateway_data_dir=tmp_path / "gw")
    with patch("uvicorn.run") as mock_run, \
         patch("app.main.create_app") as mock_create_app, \
         patch("app.main.load_settings", return_value=settings):
        run()
        mock_create_app.assert_called_once_with(settings)
        mock_run.assert_called_once()
