"""CLI для ручной проверки модуля: `stock-media "бриф" --kind video`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .api import StockMediaClient
from .config import DOTENV_PATH, Settings
from .errors import StockMediaError
from .models import MediaKind, Orientation
from .planner import HeuristicPlanner
from .providers.registry import PROVIDER_CLASSES

OK = "[ок]"
OFF = "[--]"


def doctor(settings: Settings) -> None:
    """Показать, что модуль видит: .env, ключи, провайдеры, планировщик.

    Отвечает на вопрос «почему ничего не нашлось» до того, как он возникнет.
    """
    print("Файл .env:")
    if DOTENV_PATH:
        print(f"  {OK} {DOTENV_PATH}")
    else:
        print(f"  {OFF} не найден — ключи возьмутся только из переменных окружения")
        print(f"       ожидался здесь: {Path.cwd() / '.env'}")

    print("\nПровайдеры:")
    for name, reason in settings.provider_status().items():
        kinds = ", ".join(sorted(PROVIDER_CLASSES[name].supports))
        if reason is None:
            print(f"  {OK} {name:10} {kinds}")
        else:
            print(f"  {OFF} {name:10} {kinds:12} {reason}")

    planner = "Claude" if settings.anthropic_api_key else "эвристика (нет ANTHROPIC_API_KEY)"
    print(f"\nПланировщик запросов: {planner}")
    print(f"Папка для файлов: {settings.cache_dir.resolve()}")


def _warn_if_no_provider_for(client: StockMediaClient, kind: MediaKind) -> None:
    capable = [p.name for p in client.providers if kind.value in p.supports]
    if capable:
        return
    print(
        f"\nВНИМАНИЕ: ни один включённый провайдер не умеет отдавать {kind.value}. "
        "Результатов не будет.\n"
        "Запусти `stock-media --check`, чтобы увидеть, чего не хватает.",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Подбор стоковых видео и фото")
    parser.add_argument("brief", nargs="?", help="Сценарий или описание ролика")
    parser.add_argument("--kind", choices=[k.value for k in MediaKind], default="video")
    parser.add_argument(
        "--orientation", choices=[o.value for o in Orientation], default="portrait"
    )
    parser.add_argument("--max-queries", type=int, default=6)
    parser.add_argument("--per-query", type=int, default=2)
    parser.add_argument(
        "--dry-run", action="store_true", help="только показать план и найденное, не качать"
    )
    parser.add_argument(
        "--check", action="store_true", help="проверить настройки и выйти (ничего не искать)"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )

    settings = Settings()
    if args.check:
        doctor(settings)
        return 0

    if not args.brief:
        parser.error("нужен текст брифа (или флаг --check)")

    client = StockMediaClient(settings)
    kind = MediaKind(args.kind)
    orientation = Orientation(args.orientation)

    active = ", ".join(p.name for p in client.providers)
    print(f"провайдеры: {active}")
    if isinstance(client.planner, HeuristicPlanner):
        print("планировщик: эвристика (задай ANTHROPIC_API_KEY, чтобы запросы придумывал Claude)")
    _warn_if_no_provider_for(client, kind)

    found_anything = False
    try:
        if args.dry_run:
            for query in client.plan(
                args.brief, kind=kind, orientation=orientation, max_queries=args.max_queries
            ):
                found = client.search(query, top=args.per_query)
                print(f"\n[{query.text}]  ({query.scene_hint or '—'})")
                if not found:
                    print("  ничего не найдено")
                    continue
                found_anything = True
                for asset in found:
                    print(f"  {asset.score:.2f}  {asset.uid}  {asset.width}x{asset.height}")
        else:
            for asset in client.collect(
                args.brief,
                kind=kind,
                orientation=orientation,
                max_queries=args.max_queries,
                per_query=args.per_query,
            ):
                found_anything = True
                print(f"{asset.score:.2f}  {asset.local_path}")
    except StockMediaError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 1

    if not found_anything:
        print(
            "\nНичего не найдено. Проверь настройки: stock-media --check",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
