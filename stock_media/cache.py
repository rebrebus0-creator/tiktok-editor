"""Скачивание и локальный кэш с дедупликацией по содержимому."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path

import requests

from .config import Settings
from .errors import DownloadError
from .models import MediaAsset, MediaKind
from .providers.base import Provider

_CHUNK = 1 << 16
_INDEX_NAME = "index.json"

_DEFAULT_SUFFIX = {MediaKind.VIDEO: ".mp4", MediaKind.PHOTO: ".jpg"}


class MediaCache:
    """Кладёт файлы в `cache_dir`, помнит, что уже скачано.

    Дедупликация двухуровневая: сначала по uid ассета (не ходим в сеть
    повторно), потом по sha256 содержимого (два провайдера могут отдать
    один и тот же файл).
    """

    def __init__(self, settings: Settings) -> None:
        self.dir = Path(settings.cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.timeout = settings.request_timeout
        self._index_path = self.dir / _INDEX_NAME
        self._index: dict[str, str] = self._load_index()

    def _load_index(self) -> dict[str, str]:
        if not self._index_path.exists():
            return {}
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Битый индекс — не повод падать: просто скачаем заново.
            return {}

    def _save_index(self) -> None:
        self._index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def fetch(self, asset: MediaAsset, provider: Provider | None = None) -> MediaAsset:
        """Скачать ассет (или взять из кэша) и заполнить `local_path`/`sha256`."""
        cached = self._index.get(asset.uid)
        if cached and (self.dir / cached).exists():
            asset.local_path = self.dir / cached
            asset.sha256 = Path(cached).stem
            return asset

        tmp = self.dir / f".tmp-{_safe_name(asset.uid)}{self._suffix(asset)}"
        try:
            produced = provider.download(asset, tmp) if provider else None
            if produced is None:
                produced = self._http_download(asset, tmp)

            digest = _sha256_file(produced)
            final = self.dir / f"{digest}{produced.suffix}"
            if final.exists():
                produced.unlink(missing_ok=True)  # такой файл уже есть
            else:
                produced.replace(final)
        except requests.RequestException as exc:
            tmp.unlink(missing_ok=True)
            raise DownloadError(f"{asset.uid}: {exc}") from exc

        self._index[asset.uid] = final.name
        self._save_index()

        asset.local_path = final
        asset.sha256 = digest
        return asset

    def _http_download(self, asset: MediaAsset, dest: Path) -> Path:
        with requests.get(str(asset.url), stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            suffix = self._suffix(asset, resp.headers.get("Content-Type"))
            dest = dest.with_suffix(suffix)
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(_CHUNK):
                    fh.write(chunk)
        return dest

    @staticmethod
    def _suffix(asset: MediaAsset, content_type: str | None = None) -> str:
        if content_type:
            guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if guessed:
                return ".jpg" if guessed == ".jpe" else guessed
        from_url = Path(str(asset.url).split("?")[0]).suffix
        if from_url and len(from_url) <= 5:
            return from_url
        return _DEFAULT_SUFFIX[asset.kind]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)
