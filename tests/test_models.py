from stock_media.models import Orientation

from .conftest import make_asset


def test_orientation_detection():
    assert make_asset(width=1080, height=1920).orientation is Orientation.PORTRAIT
    assert make_asset(width=1920, height=1080).orientation is Orientation.LANDSCAPE
    assert make_asset(width=1000, height=1000).orientation is Orientation.SQUARE


def test_uid_is_provider_scoped():
    a = make_asset(provider="pexels", provider_id="7")
    b = make_asset(provider="pixabay", provider_id="7")
    assert a.uid != b.uid
