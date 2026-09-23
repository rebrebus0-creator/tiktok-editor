"""CLI для ручной проверки модуля: `stock-media "бриф" --kind video`."""

from __future__ import annotations

import argparse
import logging
import sys

from .api import StockMediaClient
from .errors import StockMediaError
from .models import MediaKind, Orientation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Подбор стоковых видео и фото")
    parser.add_argument("brief", help="Сценарий или описание ролика")
    parser.add_argument("--kind", choices=[k.value for k in MediaKind], default="video")
    parser.add_argument(
        "--orientation", choices=[o.value for o in Orientation], default="portrait"
    )
    parser.add_argument("--max-queries", type=int, default=6)
    parser.add_argument("--per-query", type=int, default=2)
    parser.add_argument(
        "--dry-run", action="store_true", help="только показать план и найденное, не качать"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )

    client = StockMediaClient()
    print(f"провайдеры: {', '.join(p.name for p in client.providers) or 'нет (задай API-ключи)'}")

    kind = MediaKind(args.kind)
    orientation = Orientation(args.orientation)

    try:
        if args.dry_run:
            for query in client.plan(
                args.brief, kind=kind, orientation=orientation, max_queries=args.max_queries
            ):
                found = client.search(query, top=args.per_query)
                print(f"\n[{query.text}]  ({query.scene_hint or '—'})")
                for asset in found:
                    print(f"  {asset.score:.2f}  {asset.uid}  {asset.width}x{asset.height}")
            return 0

        for asset in client.collect(
            args.brief,
            kind=kind,
            orientation=orientation,
            max_queries=args.max_queries,
            per_query=args.per_query,
        ):
            print(f"{asset.score:.2f}  {asset.local_path}")
    except StockMediaError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
