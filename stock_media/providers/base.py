"""Базовый класс провайдера.

Чтобы добавить новый источник, достаточно унаследоваться и реализовать
`search`. Регистрация — в `registry.py`.
"""

from __future__ import annotations

import abc
from pathlib import Path

import requests

from ..config import Settings
from ..errors import ProviderError
from ..models import MediaAsset, SearchQuery


class Provider(abc.ABC):
    name: str = "base"
    #: какие типы медиа умеет отдавать
    supports: frozenset[str] = frozenset({"video", "photo"})

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    @abc.abstractmethod
    def search(self, query: SearchQuery) -> list[MediaAsset]:
        """Вернуть найденные ассеты. Скачивание — не здесь."""

    def download(self, asset: MediaAsset, dest: "Path") -> "Path | None":
        """Своя логика скачивания, если прямого URL на файл недостаточно.

        Возврат None означает «качай обычным HTTP-GET по asset.url».
        """
        return None

    def _get_json(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> dict:
        try:
            resp = self.session.get(
                url, params=params, headers=headers, timeout=self.settings.request_timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise ProviderError(self.name, str(exc)) from exc
        except ValueError as exc:  # тело ответа не JSON
            raise ProviderError(self.name, f"некорректный JSON: {exc}") from exc
