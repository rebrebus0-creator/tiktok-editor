"""YouTube: поиск роликов и вырезание отдельных фрагментов.

ВНИМАНИЕ. Провайдер выключен по умолчанию и включается флагом
`STOCK_MEDIA_ENABLE_YOUTUBE=1`. Скачивание видео с YouTube нарушает
Условия использования сервиса, а сам контент почти всегда защищён
авторским правом. Для личного монтажа это работает; для коммерческого
продукта риск несёт тот, кто включает флаг.

Требует extras `youtube` (yt-dlp) и установленный ffmpeg.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import ProviderError
from ..models import MediaAsset, MediaKind, SearchQuery
from .base import Provider

#: длина вырезаемого фрагмента по умолчанию, сек
DEFAULT_CLIP_SECONDS = 6.0
#: отступ от начала ролика — там обычно заставка и титры
DEFAULT_CLIP_OFFSET = 15.0


def _load_ytdlp():
    try:
        import yt_dlp  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise ProviderError(
            "youtube", "не установлен yt-dlp (pip install 'stock-media[youtube]')"
        ) from exc
    return yt_dlp


class YouTubeProvider(Provider):
    name = "youtube"
    supports = frozenset({"video"})

    def search(self, query: SearchQuery) -> list[MediaAsset]:
        if query.kind is not MediaKind.VIDEO:
            return []

        yt_dlp = _load_ytdlp()
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist"}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{query.limit}:{query.text}", download=False)
        except Exception as exc:  # yt-dlp бросает свою иерархию исключений
            raise ProviderError(self.name, str(exc)) from exc

        return [a for a in map(lambda e: self._parse(e, query), info.get("entries", [])) if a]

    def _parse(self, entry: dict, query: SearchQuery) -> MediaAsset | None:
        video_id = entry.get("id")
        if not video_id:
            return None

        total = float(entry.get("duration") or 0.0)
        clip_len = query.max_duration or DEFAULT_CLIP_SECONDS
        start, end = self._pick_clip(total, clip_len)

        return MediaAsset(
            provider=self.name,
            provider_id=video_id,
            kind=MediaKind.VIDEO,
            url=f"https://www.youtube.com/watch?v={video_id}",
            preview_url=entry.get("thumbnail"),
            width=entry.get("width") or 1920,
            height=entry.get("height") or 1080,
            duration=end - start,
            author=entry.get("uploader") or entry.get("channel"),
            source_page=f"https://www.youtube.com/watch?v={video_id}",
            license="YouTube Standard License (проверяй права вручную)",
            extra={"clip_start": start, "clip_end": end, "full_duration": total},
        )

    @staticmethod
    def _pick_clip(total: float, clip_len: float) -> tuple[float, float]:
        """Взять фрагмент, пропустив интро, но не выйдя за конец ролика."""
        if total <= clip_len:
            return 0.0, max(total, clip_len)
        start = min(DEFAULT_CLIP_OFFSET, max(0.0, total - clip_len))
        return start, start + clip_len

    def download(self, asset: MediaAsset, dest: Path) -> Path | None:
        yt_dlp = _load_ytdlp()
        start = asset.extra.get("clip_start", 0.0)
        end = asset.extra.get("clip_end", DEFAULT_CLIP_SECONDS)

        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(dest.with_suffix("")) + ".%(ext)s",
            "merge_output_format": "mp4",
            # Качаем только нужный диапазон, а не весь ролик целиком.
            "download_ranges": yt_dlp.utils.download_range_func(None, [(start, end)]),
            "force_keyframes_at_cuts": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([str(asset.url)])
        except Exception as exc:
            raise ProviderError(self.name, f"не удалось скачать фрагмент: {exc}") from exc

        produced = sorted(dest.parent.glob(dest.stem + ".*"))
        if not produced:
            raise ProviderError(self.name, "yt-dlp не создал файл")
        return produced[0]
