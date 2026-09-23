"""Реестр провайдеров: имя -> класс."""

from __future__ import annotations

from ..config import Settings
from .base import Provider
from .openverse import OpenverseProvider
from .pexels import PexelsProvider
from .pixabay import PixabayProvider
from .youtube import YouTubeProvider

PROVIDER_CLASSES: dict[str, type[Provider]] = {
    PexelsProvider.name: PexelsProvider,
    PixabayProvider.name: PixabayProvider,
    OpenverseProvider.name: OpenverseProvider,
    YouTubeProvider.name: YouTubeProvider,
}


def build_providers(settings: Settings, names: list[str] | None = None) -> list[Provider]:
    """Создать экземпляры провайдеров.

    `names=None` — взять все, у кого есть ключи (см. `Settings.enabled_providers`).
    """
    selected = names if names is not None else settings.enabled_providers()
    unknown = [n for n in selected if n not in PROVIDER_CLASSES]
    if unknown:
        raise ValueError(f"неизвестные провайдеры: {', '.join(unknown)}")
    return [PROVIDER_CLASSES[n](settings) for n in selected]
