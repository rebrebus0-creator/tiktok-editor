"""stock_media — подбор стоковых видео и фото под текстовый запрос.

Модуль самодостаточный: зависит только от `requests` и `pydantic`
(нейросетевой планировщик и YouTube — опциональные extras). Подключается
к основному софту одним импортом `StockMediaClient`.
"""

from .api import StockMediaClient
from .config import Settings
from .errors import (
    DownloadError,
    MissingCredentials,
    ProviderError,
    StockMediaError,
)
from .models import MediaAsset, MediaKind, Orientation, SearchQuery

__version__ = "0.1.0"

__all__ = [
    "StockMediaClient",
    "Settings",
    "MediaAsset",
    "MediaKind",
    "Orientation",
    "SearchQuery",
    "StockMediaError",
    "ProviderError",
    "MissingCredentials",
    "DownloadError",
]
