from stock_media.models import MediaKind, Orientation, SearchQuery
from stock_media.ranking import rank, score_asset

from .conftest import make_asset


def test_portrait_beats_landscape(video_query):
    portrait = make_asset(provider_id="p", width=1080, height=1920)
    landscape = make_asset(provider_id="l", width=1920, height=1080)
    assert score_asset(portrait, video_query) > score_asset(landscape, video_query)


def test_higher_resolution_wins(video_query):
    hd = make_asset(provider_id="hd", width=1080, height=1920)
    uhd = make_asset(provider_id="uhd", width=2160, height=3840)
    assert score_asset(uhd, video_query) > score_asset(hd, video_query)


def test_too_short_clip_is_rejected():
    query = SearchQuery(text="run", kind=MediaKind.VIDEO, min_duration=5.0)
    short = make_asset(duration=1.0)
    long = make_asset(duration=8.0)
    assert score_asset(long, query) > score_asset(short, query)


def test_rank_sorts_desc_and_sets_score(video_query):
    assets = [
        make_asset(provider_id="l", width=1920, height=1080),
        make_asset(provider_id="p", width=2160, height=3840),
    ]
    ranked = rank(assets, video_query)
    assert [a.provider_id for a in ranked] == ["p", "l"]
    assert all(a.score > 0 for a in ranked)


def test_any_orientation_does_not_penalize():
    query = SearchQuery(text="run", kind=MediaKind.VIDEO, orientation=Orientation.ANY)
    landscape = make_asset(width=1920, height=1080)
    portrait = make_asset(width=1080, height=1920)
    assert score_asset(landscape, query) == score_asset(portrait, query)
