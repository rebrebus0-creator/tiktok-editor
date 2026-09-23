"""Pixabay: видео и фото. Бесплатный ключ, лицензия Pixabay Content License."""

from __future__ import annotations

from ..errors import MissingCredentials
from ..models import MediaAsset, MediaKind, Orientation, SearchQuery
from .base import Provider

VIDEO_URL = "https://pixabay.com/api/videos/"
PHOTO_URL = "https://pixabay.com/api/"

_ORIENTATION = {
    Orientation.PORTRAIT: "vertical",
    Orientation.LANDSCAPE: "horizontal",
}


class PixabayProvider(Provider):
    name = "pixabay"

    def search(self, query: SearchQuery) -> list[MediaAsset]:
        if not self.settings.pixabay_api_key:
            raise MissingCredentials("PIXABAY_API_KEY не задан")

        params: dict = {
            "key": self.settings.pixabay_api_key,
            "q": query.text,
            "per_page": max(3, min(query.limit, 200)),
            "safesearch": "true",
        }
        orientation = _ORIENTATION.get(query.orientation)
        if orientation:
            params["orientation"] = orientation

        if query.kind is MediaKind.VIDEO:
            data = self._get_json(VIDEO_URL, params=params)
            return [a for a in map(self._parse_video, data.get("hits", [])) if a]

        params["image_type"] = "photo"
        data = self._get_json(PHOTO_URL, params=params)
        return [a for a in map(self._parse_photo, data.get("hits", [])) if a]

    def _parse_video(self, item: dict) -> MediaAsset | None:
        streams = [s for s in (item.get("videos") or {}).values() if s.get("url")]
        if not streams:
            return None
        best = max(streams, key=lambda s: (s.get("width") or 0) * (s.get("height") or 0))
        return MediaAsset(
            provider=self.name,
            provider_id=str(item["id"]),
            kind=MediaKind.VIDEO,
            url=best["url"],
            preview_url=best.get("thumbnail"),
            width=best.get("width", 0),
            height=best.get("height", 0),
            duration=item.get("duration"),
            author=item.get("user"),
            source_page=item.get("pageURL"),
            license="Pixabay Content License",
            tags=_split_tags(item.get("tags")),
        )

    def _parse_photo(self, item: dict) -> MediaAsset | None:
        url = item.get("largeImageURL") or item.get("webformatURL")
        if not url:
            return None
        return MediaAsset(
            provider=self.name,
            provider_id=str(item["id"]),
            kind=MediaKind.PHOTO,
            url=url,
            preview_url=item.get("previewURL"),
            width=item.get("imageWidth", 0),
            height=item.get("imageHeight", 0),
            author=item.get("user"),
            source_page=item.get("pageURL"),
            license="Pixabay Content License",
            tags=_split_tags(item.get("tags")),
        )


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]
