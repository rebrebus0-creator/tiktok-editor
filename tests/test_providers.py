import responses

from stock_media.errors import MissingCredentials
from stock_media.models import MediaKind, SearchQuery
from stock_media.providers.pexels import PexelsProvider
from stock_media.providers.pixabay import PixabayProvider

PEXELS_VIDEO = {
    "videos": [
        {
            "id": 42,
            "url": "https://www.pexels.com/video/42/",
            "duration": 12,
            "image": "https://example.com/thumb.jpg",
            "user": {"name": "Аня"},
            "video_files": [
                {"link": "https://example.com/sd.mp4", "width": 640, "height": 360},
                {"link": "https://example.com/hd.mp4", "width": 1080, "height": 1920},
            ],
        }
    ]
}


@responses.activate
def test_pexels_picks_largest_render(settings, video_query):
    responses.add(responses.GET, "https://api.pexels.com/videos/search", json=PEXELS_VIDEO)
    assets = PexelsProvider(settings).search(video_query)
    assert len(assets) == 1
    assert str(assets[0].url) == "https://example.com/hd.mp4"
    assert assets[0].width == 1080
    assert assets[0].author == "Аня"


@responses.activate
def test_pexels_skips_entries_without_files(settings, video_query):
    responses.add(
        responses.GET,
        "https://api.pexels.com/videos/search",
        json={"videos": [{"id": 1, "video_files": []}]},
    )
    assert PexelsProvider(settings).search(video_query) == []


def test_pexels_requires_key(settings, video_query):
    settings.pexels_api_key = None
    try:
        PexelsProvider(settings).search(video_query)
    except MissingCredentials:
        return
    raise AssertionError("ожидали MissingCredentials")


@responses.activate
def test_pixabay_parses_photo(settings):
    responses.add(
        responses.GET,
        "https://pixabay.com/api/",
        json={
            "hits": [
                {
                    "id": 7,
                    "largeImageURL": "https://example.com/big.jpg",
                    "previewURL": "https://example.com/small.jpg",
                    "imageWidth": 1080,
                    "imageHeight": 1920,
                    "user": "Petya",
                    "pageURL": "https://pixabay.com/photos/7/",
                    "tags": "city, morning, run",
                }
            ]
        },
    )
    query = SearchQuery(text="city morning", kind=MediaKind.PHOTO)
    assets = PixabayProvider(settings).search(query)
    assert assets[0].tags == ["city", "morning", "run"]
    assert assets[0].kind is MediaKind.PHOTO
