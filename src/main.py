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
import copy
import json
import logging
import re
import sys
import tempfile
from pathlib import Path

from . import __version__, ffmpeg_utils
from .config import FONTS_DIR, PROJECTS_DIR, Config
from .errors import EditorError, FFmpegNotFound
from .logging_setup import collect_warnings, heading, setup_logging
from .project import Project, discover_projects

log = logging.getLogger("main")

OK = "OK "
WARN = "!  "
FAIL = "x  "



# --------------------------------------------------------------------------- #
# check — проверка окружения
# --------------------------------------------------------------------------- #


def _smoke_test_cut(cfg: Config) -> str | None:
    """Прогоняет настоящую нарезку на секундном тестовом ролике.

    Возвращает описание проблемы или None, если всё сошлось.
    """
    from . import autocut
    from .models import KeepSegment

    fast = copy.deepcopy(cfg)
    fast.video.preset = "ultrafast"
    fast.video.crf = 32

    autocut_log = logging.getLogger("src.autocut")
    previous_level = autocut_log.level
    autocut_log.setLevel(logging.WARNING)
    try:
        with tempfile.TemporaryDirectory(prefix="tiktok-editor-check-") as tmp:
            source = Path(tmp) / "probe.mp4"
            ffmpeg_utils.run(
                [
                    "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(source),
                ],
                desc="тестовый ролик",
            )
            out = Path(tmp) / "cut.mp4"
            # Два куска по 0.5 с: в сумме ровно 1 с — по длительности и сверяем.
            autocut.render_cut(
                source,
                [KeepSegment(0.0, 0.5), KeepSegment(1.0, 1.5)],
                out,
                fast,
            )
            result = ffmpeg_utils.media_info(out)
            if abs(result.duration - 1.0) > 0.25:
                return f"длительность результата {result.duration:.2f} с вместо 1.00 с"
            if not result.has_audio:
                return "в результате пропала звуковая дорожка"
    except EditorError as exc:
        return str(exc).replace("\n", " ")[:300]
    finally:
        autocut_log.setLevel(previous_level)
    return None


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
        filters = ffmpeg_utils.available_filters()
        encoders = ffmpeg_utils.available_encoders()
        # Если разбор списка сломался на будущей версии FFmpeg — честно
        # говорим об этом, а не рапортуем, что отсутствуют все фильтры сразу.
        if len(filters) < 20:
            print(f"{WARN}не удалось прочитать список фильтров этой сборки — пропускаю проверку")
            warnings += 1
        else:
            missing = [name for name in ffmpeg_utils.REQUIRED_FILTERS if name not in filters]
            if missing:
                for name in missing:
                    print(f"{FAIL}фильтр {name} отсутствует в этой сборке FFmpeg")
                problems += len(missing)
                print("   Поставь полную сборку: brew install ffmpeg")
            else:
                print(f"{OK}все нужные фильтры на месте ({len(ffmpeg_utils.REQUIRED_FILTERS)} шт.)")

        if len(encoders) < 10:
            print(f"{WARN}не удалось прочитать список кодеков этой сборки — пропускаю проверку")
            warnings += 1
        else:
            for encoder in (cfg.video.video_codec, cfg.video.audio_codec):
                if encoder in encoders:
                    print(f"{OK}кодек {encoder}")
                else:
                    print(f"{FAIL}кодек {encoder} недоступен")
                    problems += 1

    if ffmpeg_path:
        heading("Проверка склейки")
        # Самая версиезависимая операция проекта — режем и склеиваем тестовый
        # ролик тем же кодом, что и настоящий. Дешевле, чем узнать на материале.
        problem = _smoke_test_cut(cfg)
        if problem:
            print(f"{FAIL}нарезка не работает на этой сборке FFmpeg: {problem}")
            problems += 1
        else:
            print(f"{OK}нарезка и склейка работают (FFmpeg {ffmpeg_utils.major_version()}.x)")

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

    from . import parser

    # Разбираем тем же парсером, что и сборка: заодно видно, все ли файлы
    # ассетов на месте — до того, как запускать долгое распознавание.
    logging.getLogger("src.parser").setLevel(logging.ERROR)
    doc = parser.parse_script(text, cfg)
    logging.getLogger("src.parser").setLevel(logging.NOTSET)

    words = len(doc.speech_words)
    # ~2.6 слова в секунду — типичный темп динамичной речи для коротких роликов.
    print(f"{OK}{project.script_path.name}: {words} слов (~{words / 2.6:.0f}с речи)")

    if not doc.tags:
        print(f"{WARN}тегов не найдено — соберётся просто нарезка с субтитрами")

    missing = 0
    for tag in doc.tags:
        note = ""
        if tag.kind in ("screen", "insert", "sound", "music"):
            if project.find_asset(tag.kind, tag.argument) is None:
                note = "  <- ФАЙЛ НЕ НАЙДЕН"
                missing += 1
        duration = f", {tag.duration:g}с" if tag.duration else ""
        mark = FAIL if note else OK
        print(f"{mark}{tag.raw}{duration}{note}")

    known_tags = {match.group(0) for match in TAG_RE.finditer(text)}
    for raw_tag in sorted(known_tags - {tag.raw for tag in doc.tags}):
        print(f"{WARN}неизвестный тег {raw_tag} — будет пропущен (имена: config.tags.names)")

    if missing:
        print(f"{WARN}не найдено файлов: {missing} — эти теги при сборке пропустятся")

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


def prepare_source(project: Project, cfg: Config, args: argparse.Namespace) -> dict:
    """Общее начало любой сборки: исходник -> звук -> транскрипт.

    Вынесено отдельно, потому что теги [ПАУЗА] находятся уже по транскрипту,
    а влияют на нарезку — значит, распознать нужно ДО автореза.
    """
    from . import transcribe

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
    return {
        "raw": raw,
        "info": info,
        "audio": audio,
        "levels": levels,
        "transcript": transcript,
    }


def run_autocut(
    project: Project,
    cfg: Config,
    args: argparse.Namespace,
    prepared: dict,
    *,
    protected: list[float] | None = None,
    out_path: Path | None = None,
) -> dict:
    """Авторез: находит паузы, режет и склеивает видео без них.

    protected — таймкоды тегов [ПАУЗА]: эта тишина не вырезается.
    Возвращает отчёт и рабочие объекты (куски, карту времени), чтобы сборка
    не пересчитывала то же самое.
    """
    from . import autocut
    from .timeline import TimeMap

    raw = prepared["raw"]
    info = prepared["info"]
    audio = prepared["audio"]
    levels = prepared["levels"]
    transcript = prepared["transcript"]

    heading("Авторез пауз")
    total = info.duration or transcript.duration
    silences = autocut.detect_silence(audio, cfg, total_duration=total)
    segments = autocut.plan_keep_segments(silences, total, cfg, protected=protected)
    time_map = TimeMap(segments)

    out_path = out_path or project.output_dir / f"{project.name}_cut.mp4"
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

    return {
        "report": report,
        "transcript": transcript,
        "segments": segments,
        "time_map": time_map,
        "cut": out_path,
        "duration": total,
    }


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


def read_script(project: Project, cfg: Config, transcript):
    """Разбирает сценарий и привязывает теги к речи.

    Сценарий может отсутствовать или не подходить к записи — тогда работаем
    без тегов, а не отказываемся собирать.
    """
    from . import aligner, parser

    try:
        doc = parser.parse_script(project.script_text(), cfg)
    except EditorError as exc:
        log.warning("сценарий не прочитан (%s) — собираю без тегов", exc)
        return parser.ScriptDoc()

    heading("Сценарий и выравнивание")
    aligner.align(doc, transcript, cfg)
    return doc


def cmd_cut(args: argparse.Namespace) -> int:
    project = Project.load(Path(args.project))
    if not args.no_log_file:
        setup_logging(verbose=args.verbose, log_file=project.log_path)

    cfg = Config.load(project.path)
    _apply_overrides(cfg, args)
    ffmpeg_utils.require_ffmpeg()

    heading(f"Этап 1: {project.name}")
    with collect_warnings() as warnings:
        prepared = prepare_source(project, cfg, args)
        doc = read_script(project, cfg, prepared["transcript"])
        protected = [tag.src_time for tag in doc.tags if tag.kind == "pause" and tag.resolved]
        if protected:
            log.info("тегов [ПАУЗА]: %d — эта тишина останется", len(protected))
        result = run_autocut(project, cfg, args, prepared, protected=protected)
        report = result["report"]
        report["protected_pauses"] = [round(value, 2) for value in protected]
        report["warnings"] = list(warnings)

    report_path = project.output_dir / "autocut-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_cut_summary(project, report)
    return 0


def cmd_subs(args: argparse.Namespace) -> int:
    """Быстрая примерка субтитров: нарезка + субтитры, без оверлеев и зума."""
    from . import compositor, subtitles

    project = Project.load(Path(args.project))
    if not args.no_log_file:
        setup_logging(verbose=args.verbose, log_file=project.log_path)

    cfg = Config.load(project.path)
    ffmpeg_utils.require_ffmpeg()

    heading(f"Примерка субтитров: {project.name}")
    prepared = prepare_source(project, cfg, args)
    doc = read_script(project, cfg, prepared["transcript"])
    protected = [tag.src_time for tag in doc.tags if tag.kind == "pause" and tag.resolved]
    result = run_autocut(
        project, cfg, args, prepared, protected=protected,
        out_path=project.cache_dir / "cut.mp4",
    )

    time_map = result["time_map"]
    ass_path = subtitles.build_ass(
        time_map.map_words(prepared["transcript"].words), project.cache_dir / "subs.ass", cfg
    )
    out_path = project.output_dir / f"{project.name}_subs.mp4"
    compositor.burn_subtitles(result["cut"], ass_path, out_path, cfg)

    heading("Готово")
    print(f"  превью:   {out_path}")
    print(f"  стиль:    {cfg.subtitles.font_name} {cfg.subtitles.font_size}pt, "
          f"подсветка {cfg.subtitles.highlight_color}, до {cfg.subtitles.max_words} слов в плашке")
    print(f"  править:  [subtitles] в config.toml, потом запустить эту команду снова")
    return 0


# --------------------------------------------------------------------------- #
# build — сборка ролика
# --------------------------------------------------------------------------- #


def build_project(project: Project, args: argparse.Namespace) -> int:
    """Полный прогон пайплайна по одному проекту."""
    cfg = Config.load(project.path)
    _apply_overrides(cfg, args)
    project.output_dir.mkdir(parents=True, exist_ok=True)
    project.cache_dir.mkdir(parents=True, exist_ok=True)

    heading(f"Сборка: {project.name}")
    ffmpeg_utils.require_ffmpeg()
    log.info("сценарий: %s", project.script_path)
    log.info("результат: %s", project.output_video())

    with collect_warnings() as warnings:
        report = _run_pipeline(project, cfg, args)
        report["warnings"] = list(warnings)

    timeline_path = project.output_dir / "timeline.json"
    timeline_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_build_summary(project, report)
    return 0


def _print_build_summary(project: Project, report: dict) -> None:
    heading(f"Готово: {project.name}")
    print(f"  ролик:        {report['output']}")
    print(f"  формат:       {report['resolution']}, {report['duration']} с")
    print(
        f"  авторез:      вырезано {report['autocut']['removed_seconds']} с "
        f"({report['autocut']['removed_percent']}%), склеек {report['autocut']['cuts']}"
    )

    resolved = [tag for tag in report["tags"] if tag["final_time"] is not None]
    weak = [tag for tag in resolved if tag["similarity"] < 0.55]
    print(f"  теги:         {len(resolved)} из {len(report['tags'])} привязаны к речи")
    if weak:
        print(f"                {len(weak)} встали приблизительно — проверь timeline.json")
    for event in report["events"]:
        source = f" {event['source']}" if event["source"] else ""
        end = f"-{event['end']}" if event["end"] is not None else ""
        print(f"     {event['kind']:<7} {event['start']}{end} с{source}")

    if report["speech_check"]["words_lost"]:
        print(f"  ПОТЕРЯНО СЛОВ: {report['speech_check']['words_lost']} — см. timeline.json")
    if report["warnings"]:
        print(f"  предупреждений: {len(report['warnings'])} (подробности в build.log)")
    print()
    print(f"  таймлайн:     {project.output_dir / 'timeline.json'}")
    print(f"  лог:          {project.log_path}")


def _run_pipeline(project: Project, cfg: Config, args: argparse.Namespace) -> dict:
    """Полный пайплайн одного ролика. Возвращает отчёт о сборке.

    Порядок принципиален: теги привязываются к словам ДО автореза (иначе
    [ПАУЗА] нечего защищать), а в финальный таймлайн переводятся ПОСЛЕ него
    — через карту времени.
    """
    from . import compositor, subtitles, timeline

    # 1. Исходник, звук, распознавание речи.
    prepared = prepare_source(project, cfg, args)
    transcript = prepared["transcript"]

    # 2. Сценарий: теги привязываются к секундам ИСХОДНОГО видео.
    doc = read_script(project, cfg, transcript)
    protected = [tag.src_time for tag in doc.tags if tag.kind == "pause" and tag.resolved]
    if protected:
        log.info("тегов [ПАУЗА]: %d — эта тишина останется", len(protected))

    # 3. Авторез: паузы вырезаны, таймкоды поехали.
    # Промежуточное видео без пауз — в кэш: пользователю в output/ нужен
    # только готовый ролик.
    result = run_autocut(
        project, cfg, args, prepared, protected=protected,
        out_path=project.cache_dir / "cut.mp4",
    )
    time_map = result["time_map"]

    # 4. Перевод тегов в финальный таймлайн и поиск файлов ассетов.
    heading("События таймлайна")
    events = timeline.build_events(doc, time_map, cfg, project, time_map.total)

    # 5. Субтитры по финальным таймкодам слов.
    ass_path = None
    if cfg.subtitles.enabled:
        heading("Субтитры")
        ass_path = subtitles.build_ass(
            time_map.map_words(transcript.words), project.cache_dir / "subs.ass", cfg
        )

    # 6. Композитинг и экспорт.
    heading("Композитинг и экспорт")
    out = compositor.compose(
        result["cut"], events, project.output_video(), cfg, ass_path=ass_path
    )
    final = ffmpeg_utils.media_info(out)
    log.info("готово: %s — %s", out, final.summary())

    return {
        "project": project.name,
        "output": str(out),
        "duration": round(final.duration, 2),
        "resolution": f"{final.width}x{final.height}",
        "autocut": result["report"]["result"],
        "speech_check": result["report"]["speech_check"],
        "tags": [
            {
                "tag": tag.raw,
                "kind": tag.kind,
                "argument": tag.argument,
                "anchor": tag.anchor,
                "src_time": round(tag.src_time, 2) if tag.resolved else None,
                "final_time": round(time_map.to_final(tag.src_time), 2)
                if tag.resolved
                else None,
                "similarity": round(tag.similarity, 2),
            }
            for tag in doc.tags
        ],
        "events": [
            {
                "kind": event.kind,
                "start": round(event.start, 2),
                "end": round(event.end, 2) if event.end is not None else None,
                "source": event.source.name if event.source else None,
                "tag": event.params.get("tag"),
            }
            for event in events
        ],
    }


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

    subs = sub.add_parser(
        "subs",
        help="примерить субтитры: нарезка + субтитры, без оверлеев (быстро)",
    )
    subs.add_argument("project", help="папка проекта")
    subs.add_argument("--raw", help="конкретный исходник вместо автопоиска в raw/")
    subs.add_argument("--no-cache", action="store_true", help="распознать речь заново")
    subs.add_argument("--no-log-file", action="store_true", help="не писать output/build.log")
    subs.set_defaults(func=cmd_subs, no_calibrate=True)

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
