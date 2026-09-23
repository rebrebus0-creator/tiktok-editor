"""Исключения модуля."""


class StockMediaError(Exception):
    """Базовая ошибка модуля."""


class ProviderError(StockMediaError):
    """Провайдер вернул ошибку или недоступен."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider


class MissingCredentials(StockMediaError):
    """Не задан API-ключ для провайдера."""


class DownloadError(StockMediaError):
    """Не удалось скачать файл."""
