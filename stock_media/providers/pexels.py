"""Pexels: видео и фото. Бесплатный ключ, лицензия Pexels License."""

from __future__ import annotations

from ..errors import MissingCredentials
from ..models import MediaAsset, MediaKind, Orientation, SearchQuery
from .base import Provider

VIDEO_URL = "https://api.pexels.com/videos/search"
PHOTO_URL = "https://api.pexels.com/v1/search"


class PexelsProvider(Provider):
    name = "pexels"

    def search(self, query: SearchQuery) -> list[MediaAsset]:
        if not self.settings.pexels_api_key:
            raise MissingCredentials("PEXELS_API_KEY не задан")

        headers = {"Authorization": self.settings.pexels_api_key}
        params: dict = {"query": query.text, "per_page": min(query.limit, 80)}
        if query.orientation is not Orientation.ANY:
            params["orientation"] = query.orientation.value

        if query.kind is MediaKind.VIDEO:
            data = self._get_json(VIDEO_URL, params=params, headers=headers)
            return [a for a in map(self._parse_video, data.get("videos", [])) if a]

        data = self._get_json(PHOTO_URL, params=params, headers=headers)
        return [a for a in map(self._parse_photo, data.get("photos", [])) if a]

    def _parse_video(self, item: dict) -> MediaAsset | None:
        # Pexels отдаёт несколько рендеров одного ролика — берём самый крупный.
        files = [f for f in item.get("video_files", []) if f.get("link")]
        if not files:
            return None
        best = max(files, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
        return MediaAsset(
            provider=self.name,
            provider_id=str(item["id"]),
            kind=MediaKind.VIDEO,
            url=best["link"],
            preview_url=item.get("image"),
            width=best.get("width") or item.get("width", 0),
            height=best.get("height") or item.get("height", 0),
            duration=item.get("duration"),
            author=(item.get("user") or {}).get("name"),
            source_page=item.get("url"),
            license="Pexels License",
        )

    def _parse_photo(self, item: dict) -> MediaAsset | None:
        src = item.get("src") or {}
        url = src.get("original") or src.get("large2x") or src.get("large")
        if not url:
            return None
        return MediaAsset(
            provider=self.name,
            provider_id=str(item["id"]),
            kind=MediaKind.PHOTO,
            url=url,
            preview_url=src.get("medium"),
            width=item.get("width", 0),
            height=item.get("height", 0),
            author=item.get("photographer"),
            source_page=item.get("url"),
            license="Pexels License",
            tags=[item["alt"]] if item.get("alt") else [],
        )
