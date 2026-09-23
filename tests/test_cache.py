import responses

from stock_media.cache import MediaCache

from .conftest import make_asset


@responses.activate
def test_downloads_and_names_file_by_hash(settings):
    responses.add(
        responses.GET,
        "https://example.com/a.mp4",
        body=b"video-bytes",
        content_type="video/mp4",
    )
    asset = MediaCache(settings).fetch(make_asset())
    assert asset.local_path.exists()
    assert asset.local_path.stem == asset.sha256
    assert asset.local_path.read_bytes() == b"video-bytes"


@responses.activate
def test_second_fetch_hits_cache(settings):
    responses.add(responses.GET, "https://example.com/a.mp4", body=b"x", content_type="video/mp4")
    cache = MediaCache(settings)
    first = cache.fetch(make_asset())
    second = MediaCache(settings).fetch(make_asset())  # новый экземпляр читает индекс с диска
    assert first.local_path == second.local_path
    assert len(responses.calls) == 1


@responses.activate
def test_identical_content_from_two_providers_stored_once(settings):
    responses.add(responses.GET, "https://example.com/a.mp4", body=b"same", content_type="video/mp4")
    responses.add(responses.GET, "https://example.com/b.mp4", body=b"same", content_type="video/mp4")
    cache = MediaCache(settings)
    a = cache.fetch(make_asset(provider="pexels", provider_id="1"))
    b = cache.fetch(make_asset(provider="pixabay", provider_id="2", url="https://example.com/b.mp4"))
    assert a.local_path == b.local_path
