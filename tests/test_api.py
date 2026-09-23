import pytest

from stock_media.api import StockMediaClient
from stock_media.errors import ProviderError
from stock_media.models import MediaAsset, SearchQuery
from stock_media.planner import HeuristicPlanner
from stock_media.providers.base import Provider

from .conftest import make_asset


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, settings, assets):
        super().__init__(settings)
        self._assets = assets

    def search(self, query: SearchQuery) -> list[MediaAsset]:
        return [a.model_copy(deep=True) for a in self._assets]


class BrokenProvider(Provider):
    name = "broken"

    def search(self, query):
        raise ProviderError(self.name, "упал")


@pytest.fixture
def client(settings):
    assets = [
        make_asset(provider="fake", provider_id="hd", width=2160, height=3840),
        make_asset(provider="fake", provider_id="sd", width=640, height=360),
    ]
    return StockMediaClient(
        settings,
        providers=[FakeProvider(settings, assets), BrokenProvider(settings)],
        planner=HeuristicPlanner(),
    )


def test_search_ranks_and_trims(client, video_query):
    found = client.search(video_query, top=1)
    assert [a.provider_id for a in found] == ["hd"]


def test_broken_provider_does_not_break_search(client, video_query):
    assert len(client.search(video_query)) == 2


def test_search_attaches_query(client, video_query):
    assert client.search(video_query)[0].query.text == video_query.text


def test_dedupe_across_queries(client):
    plan = client.plan("бег по городу. кофе в кафе", max_queries=2)
    collected = []
    for query in plan:
        collected.extend(client.search(query, top=2))
    uids = [a.uid for a in collected]
    assert len(uids) != len(set(uids))  # дубли до дедупликации есть
