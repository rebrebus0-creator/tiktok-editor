"""CLI и оркестратор пайплайна.

    python -m src.main check              проверить окружение (FFmpeg, зависимости, шрифт)
    python -m src.main init <имя>         создать структуру нового проекта
    python -m src.main info <проект>      что лежит в проекте и как он разберётся
    python -m src.main build <проект>     собрать ролик
    python -m src.main batch <папка>      собрать все проекты внутри папки

Порядок этапов сборки (собираем поэтапно, см. README):
    1. транскрипция + авторез
    2. караоке-субтитры
    3. парсер тегов + выравнивание сценария с речью
    4. композитинг: [ЭКРАН] / [ВСТАВКА] / [ЗВУК] / [МУЗЫКА]
    5. финал: [ЗУМ], нормализация, экспорт 1080x1920, batch
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from . import __version__, ffmpeg_utils
from .config import FONTS_DIR, PROJECTS_DIR, Config
from .errors import EditorError, FFmpegNotFound, StagePending
from .logging_setup import collect_warnings, heading, setup_logging
from .models import KeepSegment
from .project import Project, discover_projects

log = logging.getLogger("main")

OK = "OK "
WARN = "!  "
FAIL = "x  "

STAGES: list[tuple[int, str]] = [
    (1, "Транскрипция + авторез"),
    (2, "Караоке-субтитры"),
    (3, "Парсер + выравнивание"),
    (4, "Композитинг"),
    (5, "Финал: зум, нормализация, экспорт"),
]

# Этапы, которые уже собраны. Обновляется по мере готовности.
DONE_STAGES: set[int] = {1}


# --------------------------------------------------------------------------- #
# check — проверка окружения
# --------------------------------------------------------------------------- #


def cmd_check(args: argparse.Namespace) -> int:
    cfg = Config.load()
    problems = 0
    warnings = 0

    heading("Окружение")
    py = sys.version_info
    if (py.major, py.minor) >= (3, 11):
        print(f"{OK}Python {py.major}.{py.minor}.{py.micro}")
    else:
        print(f"{FAIL}Python {py.major}.{py.minor} — нужен 3.11+ (используется tomllib)")
        problems += 1

    ffmpeg_path, ffprobe_path = ffmpeg_utils.find_ffmpeg()
    if ffmpeg_path and ffprobe_path:
        print(f"{OK}ffmpeg {ffmpeg_utils.version()} — {ffmpeg_path}")
        print(f"{OK}ffprobe — {ffprobe_path}")
    else:
        for name, path in (("ffmpeg", ffmpeg_path), ("ffprobe", ffprobe_path)):
            if path:
                print(f"{OK}{name} — {path}")
            else:
                print(f"{FAIL}{name} не найден. Установка на Mac: brew install ffmpeg")
                problems += 1

    if ffmpeg_path:
        heading("Фильтры FFmpeg")
        missing = [name for name in ffmpeg_utils.REQUIRED_FILTERS if not ffmpeg_utils.has_filter(name)]
        if missing:
            for name in missing:
                print(f"{FAIL}фильтр {name} отсутствует в этой сборке FFmpeg")
            problems += len(missing)
            print("   Поставь полную сборку: brew install ffmpeg")
        else:
            print(f"{OK}все нужные фильтры на месте ({len(ffmpeg_utils.REQUIRED_FILTERS)} шт.)")

        encoders = ffmpeg_utils.available_encoders()
        for encoder in (cfg.video.video_codec, cfg.video.audio_codec):
            if encoder in encoders:
                print(f"{OK}кодек {encoder}")
            else:
                print(f"{FAIL}кодек {encoder} недоступен")
                problems += 1

    heading("Python-зависимости")
    try:
        import faster_whisper  # noqa: F401

        fw_version = getattr(faster_whisper, "__version__", "?")
        print(f"{OK}faster-whisper {fw_version}")
    except ImportError:
        print(f"{FAIL}faster-whisper не установлен: pip install -r requirements.txt")
        problems += 1

    heading("Ресурсы")
    font = cfg.font_path()
    if font:
        print(f"{OK}шрифт субтитров: {font.name}")
    elif cfg.subtitles.font_file:
        print(
            f"{WARN}нет файла шрифта {cfg.subtitles.font_file} в {FONTS_DIR} — "
            f"субтитры возьмут системный шрифт «{cfg.subtitles.font_name}»"
        )
        warnings += 1
    else:
        print(f"{OK}шрифт субтитров: системный «{cfg.subtitles.font_name}»")

    if PROJECTS_DIR.is_dir():
        projects = discover_projects(PROJECTS_DIR)
        print(f"{OK}папка проектов: {PROJECTS_DIR} (проектов: {len(projects)})")
    else:
        print(f"{WARN}нет папки {PROJECTS_DIR} — создай проект: python -m src.main init <имя>")
        warnings += 1

    if cfg.sources:
        for source in cfg.sources:
            print(f"{OK}конфиг: {source}")
    else:
        print(f"{OK}конфиг: значения по умолчанию (config.toml не найден — это нормально)")

    print()
    if problems:
        print(f"Проблем: {problems}. Собрать ролик пока нельзя.")
        return 1
    if warnings:
        print(f"Всё готово к работе. Предупреждений: {warnings}.")
        return 0
    print("Всё готово к работе.")
    return 0


# --------------------------------------------------------------------------- #
# init — создание проекта
# --------------------------------------------------------------------------- #


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.name)
    if not target.is_absolute() and target.parent == Path("."):
        target = PROJECTS_DIR / target.name

    existed = target.exists()
    project = Project.create(target, with_example_script=not args.no_example)

    heading(f"Проект {project.name}")
    print(("Обновлён: " if existed else "Создан: ") + str(project.path))
    for name in ("raw", "screencasts", "inserts", "sounds", "music", "output"):
        print(f"   {name}/")
    print(f"   script.txt {'(пример сценария)' if not args.no_example else ''}")
    print()
    print("Дальше:")
    print(f"   1. положи исходное видео в {project.raw_dir}")
    print(f"   2. напиши сценарий с тегами в {project.script_path}")
    print(f"   3. собери ролик: python -m src.main build {project.path}")
    return 0


# --------------------------------------------------------------------------- #
# info — что в проекте
# --------------------------------------------------------------------------- #

TAG_RE = re.compile(r"\[([^\]\n]{1,120})\]")


def _preview_tags(text: str, cfg: Config) -> tuple[dict[str, int], list[str]]:
    """Грубый подсчёт тегов без выравнивания — чтобы глазами проверить разметку.

    Полный разбор (аргументы, якоря, таймкоды) появится на этапе 3.
    """
    aliases = cfg.tags.alias_map()
    counts: dict[str, int] = {}
    unknown: list[str] = []
    for match in TAG_RE.finditer(text):
        body = match.group(1).strip()
        head = body.split(":", 1)[0].strip().upper()
        head = " ".join(head.split())
        kind = aliases.get(head)
        if kind is None:
            unknown.append(match.group(0))
        else:
            counts[kind] = counts.get(kind, 0) + 1
    return counts, unknown


def cmd_info(args: argparse.Namespace) -> int:
    project = Project.load(Path(args.project))
    cfg = Config.load(project.path)

    heading(f"Проект {project.name}")
    print(f"Папка: {project.path}")

    try:
        raw = project.raw_video()
        try:
            info = ffmpeg_utils.media_info(raw)
            note = "" if info.is_vertical else "  (горизонтальное — будет вписано в 1080x1920)"
            print(f"{OK}raw/{raw.name}: {info.summary()}{note}")
            if not info.has_audio:
                print(f"{WARN}в исходнике нет звуковой дорожки — распознавать нечего")
        except FFmpegNotFound:
            print(f"{WARN}raw/{raw.name} (ffprobe недоступен, параметры не прочитаны)")
    except EditorError as exc:
        print(f"{FAIL}{exc}")

    for kind, title in (
        ("screen", "screencasts"),
        ("insert", "inserts"),
        ("sound", "sounds"),
        ("music", "music"),
    ):
        files = project.assets(kind)
        if files:
            print(f"{OK}{title}/: " + ", ".join(item.name for item in files))
        else:
            print(f"   {title}/: пусто")

    heading("Сценарий")
    try:
        text = project.script_text()
    except EditorError as exc:
        print(f"{FAIL}{exc}")
        return 1

    words = len(re.sub(TAG_RE, " ", text).split())
    # ~2.6 слова в секунду — типичный темп динамичной речи для коротких роликов.
    print(f"{OK}{project.script_path.name}: {words} слов (~{words / 2.6:.0f}с речи)")

    counts, unknown = _preview_tags(text, cfg)
    if counts:
        titles = {
            "screen": "[ЭКРАН]",
            "screen_stop": "[ЭКРАН СТОП]",
            "insert": "[ВСТАВКА]",
            "sound": "[ЗВУК]",
            "music": "[МУЗЫКА]",
            "music_stop": "[МУЗЫКА СТОП]",
            "pause": "[ПАУЗА]",
            "zoom": "[ЗУМ]",
        }
        for kind, count in sorted(counts.items()):
            print(f"{OK}{titles.get(kind, kind)}: {count}")
    else:
        print(f"{WARN}тегов не найдено — соберётся просто нарезка с субтитрами")

    for raw_tag in unknown:
        print(f"{WARN}неизвестный тег {raw_tag} — будет пропущен (имена тегов: config.tags.names)")

    heading("Настройки")
    print(f"   формат: {cfg.video.resolution} @ {cfg.video.fps}fps")
    print(f"   модель распознавания: {cfg.transcribe.model} ({cfg.transcribe.compute_type}, {cfg.transcribe.language})")
    print(f"   авторез: {'вкл' if cfg.autocut.enabled else 'выкл'}, "
          f"порог {cfg.autocut.silence_db}dB, пауза от {cfg.autocut.min_silence}с")
    print(f"   субтитры: {'вкл' if cfg.subtitles.enabled else 'выкл'}, "
          f"{cfg.subtitles.font_name} {cfg.subtitles.font_size}pt, "
          f"подсветка {cfg.subtitles.highlight_color}")
    if cfg.sources:
        print(f"   конфиг: {', '.join(str(path) for path in cfg.sources)}")
    return 0


# --------------------------------------------------------------------------- #
# cut — этап 1 отдельной командой: транскрипт + авторез + отчёт
# --------------------------------------------------------------------------- #


def _apply_overrides(cfg: Config, args: argparse.Namespace) -> None:
    """Разовые переопределения порогов из командной строки (подбор настроек)."""
    if getattr(args, "silence_db", None) is not None:
        cfg.autocut.silence_db = float(args.silence_db)
        log.info("порог тишины переопределён: %s dB", cfg.autocut.silence_db)
    if getattr(args, "min_silence", None) is not None:
        cfg.autocut.min_silence = float(args.min_silence)
        log.info("минимальная пауза переопределена: %s с", cfg.autocut.min_silence)


def run_autocut(project: Project, cfg: Config, args: argparse.Namespace) -> dict:
    """Этап 1 целиком: звук -> транскрипт -> нарезка -> видео без пауз.

    Возвращает отчёт: по нему настраиваются пороги, не пересматривая ролик
    покадрово. Используется и командой `cut`, и сборкой `build`.
    """
    from . import autocut, transcribe
    from .timeline import TimeMap

    project.cache_dir.mkdir(parents=True, exist_ok=True)
    project.output_dir.mkdir(parents=True, exist_ok=True)

    raw = Path(args.raw).expanduser().resolve() if getattr(args, "raw", None) else project.raw_video()
    info = ffmpeg_utils.media_info(raw)
    log.info("исходник: %s — %s", raw.name, info.summary())
    if not info.has_audio:
        raise EditorError(f"в {raw.name} нет звуковой дорожки — распознавать нечего")

    heading("Звук и транскрипция")
    audio = ffmpeg_utils.extract_audio(
        raw, project.cache_dir / "audio.wav", sample_rate=transcribe.WHISPER_SAMPLE_RATE
    )
    levels = ffmpeg_utils.volume_stats(audio)
    log.info(
        "громкость дорожки: средняя %s dB, пик %s dB",
        levels["mean_volume_db"],
        levels["max_volume_db"],
    )
    mean = levels["mean_volume_db"]
    if mean is not None and cfg.autocut.silence_db > mean:
        log.warning(
            "порог тишины (%s dB) громче средней громкости речи (%.1f dB) — "
            "авторез срежет саму речь; ставь порог примерно на 10-15 dB ниже средней",
            cfg.autocut.silence_db,
            mean,
        )

    transcript = transcribe.transcribe(
        raw,
        cfg,
        cache_path=project.cache_dir / "transcript.json",
        force=getattr(args, "no_cache", False),
        audio_path=audio,
    )

    heading("Авторез пауз")
    total = info.duration or transcript.duration
    silences = autocut.detect_silence(audio, cfg, total_duration=total)
    segments = autocut.plan_keep_segments(silences, total, cfg)
    time_map = TimeMap(segments)

    out_path = project.output_dir / f"{project.name}_cut.mp4"
    autocut.render_cut(raw, segments, out_path, cfg)
    log.info("видео без пауз: %s (%.1f с)", out_path, time_map.total or total)

    report = {
        "project": project.name,
        "source": {
            "file": raw.name,
            "duration": round(info.duration, 2),
            "resolution": f"{info.width}x{info.height}" if info.width else None,
            "fps": round(info.fps, 3) if info.fps else None,
            "audio_codec": info.audio_codec,
            "sample_rate": info.sample_rate,
        },
        "audio_levels": levels,
        "config": {
            "silence_db": cfg.autocut.silence_db,
            "min_silence": cfg.autocut.min_silence,
            "pad_before": cfg.autocut.pad_before,
            "pad_after": cfg.autocut.pad_after,
            "min_segment": cfg.autocut.min_segment,
            "merge_gap": cfg.autocut.merge_gap,
        },
        "transcribe": {
            "model": transcript.model,
            "language": transcript.language,
            "words": len(transcript.words),
            "segments": len(transcript.segments),
            "avg_probability": round(
                sum(word.probability for word in transcript.words) / len(transcript.words), 3
            )
            if transcript.words
            else 0.0,
        },
        "result": autocut.stats(segments, silences, total),
        "speech_check": _speech_check(transcript, segments, time_map),
        "segments": [
            {"start": round(s.start, 2), "end": round(s.end, 2), "protected": s.protected}
            for s in segments
        ],
        "silences": [{"start": round(s, 2), "end": round(e, 2)} for s, e in silences],
        "output": str(out_path),
    }

    if not getattr(args, "no_calibrate", False):
        heading("Калибровка порогов")
        report["calibration"] = autocut.calibrate(audio, cfg, total)
        _print_calibration(report["calibration"], cfg)

    return report


def _speech_check(transcript, segments, time_map) -> dict:
    """Главная проверка качества автореза: не порезало ли речь.

    Слово считается потерянным, если его середина попала в вырезанный кусок,
    и «на грани», если оно начинается или заканчивается вплотную к склейке.
    """
    edge = 0.06  # 60 мс — на слух это уже съеденный слог
    lost: list[dict] = []
    risky: list[dict] = []

    for word in transcript.words:
        middle = (word.start + word.end) / 2
        if not time_map.covers(middle):
            lost.append({"word": word.text, "start": round(word.start, 2)})
            continue
        for segment in segments:
            if segment.start <= middle <= segment.end:
                if word.start - segment.start < edge and segment.start > 0.01:
                    risky.append(
                        {"word": word.text, "start": round(word.start, 2), "where": "начало куска"}
                    )
                elif segment.end - word.end < edge:
                    risky.append(
                        {"word": word.text, "start": round(word.start, 2), "where": "конец куска"}
                    )
                break

    return {
        "words_total": len(transcript.words),
        "words_lost": len(lost),
        "words_at_edge": len(risky),
        "lost_examples": lost[:20],
        "edge_examples": risky[:20],
    }


def _print_calibration(calibration: dict, cfg: Config) -> None:
    print()
    print("  Порог тишины (min_silence = %.2f с):" % cfg.autocut.min_silence)
    print("    порог dB   пауз   кусков   вырезано")
    for row in calibration.get("silence_db", []):
        current = " <- сейчас" if row["silence_db"] == cfg.autocut.silence_db else ""
        print(
            f"    {row['silence_db']:>8}   {row['silences']:>4}   {row['segments']:>6}"
            f"   {row['removed_percent']:>5}%{current}"
        )
    print()
    print("  Минимальная пауза (порог = %.1f dB):" % cfg.autocut.silence_db)
    print("    длина с    пауз   кусков   вырезано")
    for row in calibration.get("min_silence", []):
        current = " <- сейчас" if row["min_silence"] == cfg.autocut.min_silence else ""
        print(
            f"    {row['min_silence']:>8}   {row['silences']:>4}   {row['segments']:>6}"
            f"   {row['removed_percent']:>5}%{current}"
        )


def _print_cut_summary(project: Project, report: dict) -> None:
    result = report["result"]
    check = report["speech_check"]
    heading("Итог этапа 1")
    print(f"  исходник:        {report['source']['file']}, {result['total_seconds']} с")
    print(
        f"  после автореза:  {result['kept_seconds']} с "
        f"(вырезано {result['removed_seconds']} с, {result['removed_percent']}%)"
    )
    print(f"  склеек:          {result['cuts']} (кусков речи: {result['segments']})")
    print(
        f"  распознано:      {report['transcribe']['words']} слов, "
        f"уверенность {report['transcribe']['avg_probability']}"
    )
    if check["words_lost"]:
        print(f"  ПОТЕРЯНО СЛОВ:   {check['words_lost']} — речь порезана, пороги надо править")
        for item in check["lost_examples"][:5]:
            print(f"       «{item['word']}» на {item['start']} с")
    else:
        print("  потеряно слов:   0")
    print(f"  слов у склейки:  {check['words_at_edge']} (проверь на слух, не съеден ли слог)")
    print()
    print(f"  видео:           {report['output']}")
    print(f"  отчёт:           {project.output_dir / 'autocut-report.json'}")
    print(f"  транскрипт:      {project.cache_dir / 'transcript.json'}")
    print(f"  лог:             {project.log_path}")


def cmd_cut(args: argparse.Namespace) -> int:
    project = Project.load(Path(args.project))
    if not args.no_log_file:
        setup_logging(verbose=args.verbose, log_file=project.log_path)

    cfg = Config.load(project.path)
    _apply_overrides(cfg, args)
    ffmpeg_utils.require_ffmpeg()

    heading(f"Этап 1: {project.name}")
    with collect_warnings() as warnings:
        report = run_autocut(project, cfg, args)
        report["warnings"] = list(warnings)

    report_path = project.output_dir / "autocut-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_cut_summary(project, report)
    return 0


# --------------------------------------------------------------------------- #
# build — сборка ролика
# --------------------------------------------------------------------------- #


def build_project(project: Project, args: argparse.Namespace) -> int:
    """Полный прогон пайплайна по одному проекту."""
    cfg = Config.load(project.path)
    project.output_dir.mkdir(parents=True, exist_ok=True)
    project.cache_dir.mkdir(parents=True, exist_ok=True)

    heading(f"Сборка: {project.name}")
    ffmpeg_utils.require_ffmpeg()

    log.info("сценарий: %s", project.script_path)
    log.info("результат: %s", project.output_video())
    raw = Path(args.raw).expanduser().resolve() if getattr(args, "raw", None) else project.raw_video()

    try:
        return _run_pipeline(project, cfg, raw, args)
    except StagePending as pending:
        log.warning("%s", pending)
        _print_roadmap(pending.stage)
        return 3


def _run_pipeline(project: Project, cfg: Config, raw: Path, args: argparse.Namespace) -> int:
    """Этапы пайплайна. По мере готовности каждый этап включается здесь."""
    from . import aligner, compositor, parser, subtitles, timeline, transcribe
    from .models import Transcript

    # --- Этап 1: транскрипция + авторез -----------------------------------
    heading("Этап 1: транскрипция + авторез")
    report = run_autocut(project, cfg, args)
    cut_video = Path(report["output"])
    transcript = Transcript.load(project.cache_dir / "transcript.json")
    segments = [
        KeepSegment(item["start"], item["end"], item["protected"]) for item in report["segments"]
    ]
    time_map = timeline.TimeMap(segments)

    # --- Этап 3: сценарий -> события таймлайна ----------------------------
    heading("Этап 3: сценарий и выравнивание")
    doc = parser.parse_script(project.script_text(), cfg)
    tags = aligner.align(doc, transcript, cfg)
    events = timeline.build_events(tags, time_map, cfg, project)

    # --- Этап 2: субтитры --------------------------------------------------
    heading("Этап 2: субтитры")
    ass_path = None
    if cfg.subtitles.enabled:
        final_words = time_map.map_words(transcript.words)
        ass_path = subtitles.build_ass(final_words, project.cache_dir / "subs.ass", cfg)

    # --- Этапы 4-5: композитинг и экспорт ---------------------------------
    heading("Этапы 4-5: композитинг и экспорт")
    out = compositor.compose(cut_video, events, project.output_video(), cfg, ass_path=ass_path)
    log.info("готово: %s", out)
    return 0


def _print_roadmap(current_stage: int) -> None:
    print()
    print("Собираем по шагам:")
    for number, title in STAGES:
        if number in DONE_STAGES:
            mark = "ok"
        elif number == current_stage:
            mark = "->"
        else:
            mark = "  "
        print(f"   {mark} этап {number}. {title}")


def cmd_build(args: argparse.Namespace) -> int:
    project = Project.load(Path(args.project))
    if not args.no_log_file:
        setup_logging(verbose=args.verbose, log_file=project.log_path)
    return build_project(project, args)


def cmd_batch(args: argparse.Namespace) -> int:
    root = Path(args.directory)
    projects = discover_projects(root)
    if not projects:
        log.error("в %s нет проектов (папка с script.txt внутри)", root)
        return 1

    log.info("проектов к сборке: %d", len(projects))
    failed: list[str] = []
    for project in projects:
        try:
            code = build_project(Project.load(project.path), args)
            if code != 0:
                failed.append(project.name)
        except EditorError as exc:
            # batch не должен вставать из-за одного кривого проекта
            log.error("%s: %s", project.name, exc)
            failed.append(project.name)

    heading("Итог batch")
    print(f"Собрано: {len(projects) - len(failed)} из {len(projects)}")
    if failed:
        print("Не собрались: " + ", ".join(failed))
        return 1
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tiktok-editor",
        description="Монтаж вертикальных роликов по размеченному сценарию.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  python -m src.main check\n"
            "  python -m src.main init my-video\n"
            "  python -m src.main info projects/my-video\n"
            "  python -m src.main build projects/my-video\n"
            "  python -m src.main batch projects\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"tiktok-editor {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="подробный лог (команды FFmpeg)")

    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="проверить окружение: FFmpeg, зависимости, шрифт")
    check.set_defaults(func=cmd_check)

    init = sub.add_parser("init", help="создать структуру нового проекта")
    init.add_argument("name", help="имя проекта (или путь к папке)")
    init.add_argument("--no-example", action="store_true", help="не создавать пример script.txt")
    init.set_defaults(func=cmd_init)

    info = sub.add_parser("info", help="показать содержимое проекта и разметку сценария")
    info.add_argument("project", help="папка проекта")
    info.set_defaults(func=cmd_info)

    cut = sub.add_parser(
        "cut",
        help="этап 1: транскрипт + авторез пауз + диагностический отчёт",
        description=(
            "Распознаёт речь, вырезает паузы и складывает результат в output/:\n"
            "  <проект>_cut.mp4      видео без пауз\n"
            "  autocut-report.json   отчёт для подбора порогов\n"
            "  build.log             полный лог прогона\n"
            "Транскрипт кэшируется, поэтому повторный подбор порогов идёт быстро."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cut.add_argument("project", help="папка проекта")
    cut.add_argument("--raw", help="конкретный исходник вместо автопоиска в raw/")
    cut.add_argument("--silence-db", type=float, help="порог тишины, dB (перебить конфиг)")
    cut.add_argument("--min-silence", type=float, help="минимальная пауза, с (перебить конфиг)")
    cut.add_argument("--no-cache", action="store_true", help="распознать речь заново")
    cut.add_argument("--no-calibrate", action="store_true", help="без калибровочной таблицы")
    cut.add_argument("--no-log-file", action="store_true", help="не писать output/build.log")
    cut.set_defaults(func=cmd_cut)

    build = sub.add_parser("build", help="собрать ролик")
    build.add_argument("project", help="папка проекта")
    build.add_argument("--raw", help="конкретный исходник вместо автопоиска в raw/")
    build.add_argument("--no-cache", action="store_true", help="не использовать кэш транскрипта")
    build.add_argument(
        "--calibrate",
        dest="no_calibrate",
        action="store_false",
        help="добавить калибровочную таблицу порогов (по умолчанию только в cut)",
    )
    build.add_argument("--no-log-file", action="store_true", help="не писать output/build.log")
    build.set_defaults(func=cmd_build, no_calibrate=True)

    batch = sub.add_parser("batch", help="собрать все проекты внутри папки")
    batch.add_argument("directory", nargs="?", default=str(PROJECTS_DIR), help="папка с проектами")
    batch.add_argument("--no-cache", action="store_true", help="не использовать кэш транскрипта")
    batch.add_argument("--no-log-file", action="store_true", help="не писать output/build.log")
    batch.set_defaults(func=cmd_batch, raw=None, no_calibrate=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(verbose=args.verbose)
    try:
        return int(args.func(args))
    except EditorError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        log.warning("прервано пользователем")
        return 130


if __name__ == "__main__":
    sys.exit(main())
