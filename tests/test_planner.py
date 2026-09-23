from stock_media.models import MediaKind, Orientation
from stock_media.planner import HeuristicPlanner


def test_splits_brief_into_queries():
    planner = HeuristicPlanner()
    queries = planner.plan("Девушка бежит по городу. Потом пьёт кофе в кафе.")
    assert len(queries) == 2
    assert all(q.kind is MediaKind.VIDEO for q in queries)
    assert queries[0].scene_hint == "Девушка бежит по городу"


def test_stopwords_are_dropped():
    queries = HeuristicPlanner().plan("Это в городе и на улице")
    assert "и" not in queries[0].text.split()
    assert "в" not in queries[0].text.split()


def test_respects_max_queries():
    brief = ". ".join(f"сцена номер {i}" for i in range(20))
    assert len(HeuristicPlanner().plan(brief, max_queries=3)) == 3


def test_empty_brief_yields_nothing():
    assert HeuristicPlanner().plan("...  \n ") == []


def test_orientation_propagates():
    queries = HeuristicPlanner().plan("бег по городу", orientation=Orientation.LANDSCAPE)
    assert queries[0].orientation is Orientation.LANDSCAPE
