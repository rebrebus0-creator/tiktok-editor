import pytest

from stock_media.config import Settings
from stock_media.models import MediaAsset, MediaKind, Orientation, SearchQuery


@pytest.fixture
def settings(tmp_path):
    return Settings(
        pexels_api_key="test-pexels",
        pixabay_api_key="test-pixabay",
        anthropic_api_key=None,
        cache_dir=tmp_path / "cache",
        enable_youtube=False,
    )


@pytest.fixture
def video_query():
    return SearchQuery(text="city morning run", kind=MediaKind.VIDEO, limit=5)


def make_asset(**kwargs) -> MediaAsset:
    defaults = dict(
        provider="pexels",
        provider_id="1",
        kind=MediaKind.VIDEO,
        url="https://example.com/a.mp4",
        width=1080,
        height=1920,
        duration=10.0,
    )
    defaults.update(kwargs)
    return MediaAsset(**defaults)
