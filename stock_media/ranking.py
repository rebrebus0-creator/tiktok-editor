"""Ранжирование: из кучи найденного выбрать то, что реально пойдёт в монтаж.

Пока эвристика на метаданных — разрешение, ориентация, длительность,
совпадение тегов. CLIP-релевантность по превью логично добавить сюда же
отдельным слагаемым, когда дойдут руки.
"""

from __future__ import annotations

from .models import MediaAsset, Orientation, SearchQuery

#: вес каждого критерия в итоговом score (в сумме 1.0)
W_RESOLUTION = 0.35
W_ORIENTATION = 0.30
W_DURATION = 0.20
W_TAGS = 0.15

#: разрешение, выше которого перестаём давать бонус (4K по большей стороне)
_RESOLUTION_CEILING = 3840 * 2160


def score_asset(asset: MediaAsset, query: SearchQuery) -> float:
    total = (
        W_RESOLUTION * _resolution_score(asset)
        + W_ORIENTATION * _orientation_score(asset, query)
        + W_DURATION * _duration_score(asset, query)
        + W_TAGS * _tag_score(asset, query)
    )
    return round(total, 4)


def rank(assets: list[MediaAsset], query: SearchQuery) -> list[MediaAsset]:
    """Проставить score и отсортировать по убыванию."""
    for asset in assets:
        asset.score = score_asset(asset, query)
    return sorted(assets, key=lambda a: a.score, reverse=True)


def _resolution_score(asset: MediaAsset) -> float:
    pixels = asset.width * asset.height
    if pixels <= 0:
        return 0.0
    return min(1.0, pixels / _RESOLUTION_CEILING)


def _orientation_score(asset: MediaAsset, query: SearchQuery) -> float:
    if query.orientation is Orientation.ANY:
        return 1.0
    if asset.orientation is query.orientation:
        return 1.0
    # Квадрат кадрируется во что угодно почти без потерь, поэтому не ноль.
    return 0.5 if asset.orientation is Orientation.SQUARE else 0.0


def _duration_score(asset: MediaAsset, query: SearchQuery) -> float:
    if asset.duration is None:
        return 1.0  # фото — критерий неприменим, не штрафуем
    if query.min_duration is not None and asset.duration < query.min_duration:
        return 0.0
    if query.max_duration is not None and asset.duration > query.max_duration:
        # Длинный ролик не брак: лишнее просто обрежется на монтаже.
        return 0.6
    return 1.0


def _tag_score(asset: MediaAsset, query: SearchQuery) -> float:
    if not asset.tags:
        return 0.5  # нет данных — среднее, чтобы не наказывать провайдера
    words = {w for w in query.text.lower().split() if len(w) > 2}
    if not words:
        return 0.5
    tags = {t.lower() for t in asset.tags}
    hits = sum(1 for w in words if any(w in t for t in tags))
    return hits / len(words)
