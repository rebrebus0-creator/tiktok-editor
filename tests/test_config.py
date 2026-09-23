import os

from stock_media.config import Settings


def test_reads_keys_from_environment(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "abc")
    monkeypatch.setenv("PIXABAY_API_KEY", "def")
    settings = Settings()
    assert settings.pexels_api_key == "abc"
    assert settings.pixabay_api_key == "def"


def test_explicit_values_win_over_environment(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "from-env")
    assert Settings(pexels_api_key="explicit").pexels_api_key == "explicit"


def test_enabled_providers_follow_available_keys(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    # Openverse не требует ключа, поэтому доступен всегда.
    assert Settings(pexels_api_key=None, pixabay_api_key=None).enabled_providers() == ["openverse"]
    assert "pexels" in Settings(pexels_api_key="k").enabled_providers()


def test_youtube_is_opt_in(monkeypatch):
    monkeypatch.delenv("STOCK_MEDIA_ENABLE_YOUTUBE", raising=False)
    assert "youtube" not in Settings().enabled_providers()
    assert "youtube" in Settings(enable_youtube=True).enabled_providers()


def test_env_flag_parsing(monkeypatch):
    for raw, expected in [("1", True), ("true", True), ("ON", True), ("0", False), ("нет", False)]:
        monkeypatch.setenv("STOCK_MEDIA_ENABLE_YOUTUBE", raw)
        assert Settings().enable_youtube is expected
