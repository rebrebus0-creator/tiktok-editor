"""Сборка ролика через FFmpeg — ЭТАПЫ 4 и 5.

Всё собирается одним проходом FFmpeg: один фильтрограф, один прогон
кодировщика. Промежуточных файлов нет — меньше потерь качества и быстрее.

Слои картинки (снизу вверх):
  1. говорящая голова, вписанная в 1080x1920;
  2. [ЗУМ] — плавный наезд на этом слое (субтитры и оверлеи не едут);
  3. [ЭКРАН] — скринкаст поверх на своём интервале;
  4. [ВСТАВКА] — картинка с альфа-каналом и фейдами;
  5. караоке-субтитры (libass) — поверх всего.

Звук:
  голос + [ЗВУК] на своих таймкодах + [МУЗЫКА] с автодакингом под голос
  (sidechaincompress), затем нормализация громкости.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import ffmpeg_utils
from .config import Config
from .models import Event

log = logging.getLogger(__name__)

STAGE = 4
STAGE_TITLE = "Композитинг"

# Общий формат звука для всех дорожек: sidechaincompress и amix требуют,
# чтобы частота дискретизации и раскладка каналов совпадали.
AUDIO_FORMAT = "aformat=sample_fmts=fltp:sample_rates={rate}:channel_layouts=stereo"


# --------------------------------------------------------------------------- #
# Вписывание кадра
# --------------------------------------------------------------------------- #


def fit_filter(
    cfg: Config,
    mode: str,
    position_y: float = 0.5,
    source: ffmpeg_utils.MediaInfo | None = None,
) -> str:
    """Фильтры, вписывающие любой источник в кадр 1080x1920.

    blur  — по ширине, фон — размытый кадр самого источника (стиль Reels)
    pad   — по ширине, поля залиты цветом
    cover — заполнить кадр целиком с обрезкой краёв
    """
    width, height = cfg.video.width, cfg.video.height

    # Источник уже нужных пропорций (обычный случай — снято вертикально):
    # подложка всё равно окажется полностью закрыта, поэтому не считаем её.
    if source and source.width and source.height:
        if abs(source.width / source.height - width / height) < 0.01:
            return f"scale={width}:{height},setsar=1"

    if mode == "cover":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )

    if mode == "blur":
        # Размытие считаем на уменьшенной копии и растягиваем обратно: результат
        # визуально тот же, а полноразмерный boxblur втрое медленнее.
        small_w, small_h = width // 6, height // 6
        radius = max(1, cfg.screen.blur_sigma // 6)
        return (
            f"split=2[fitbg][fitfg];"
            f"[fitbg]scale={small_w}:{small_h}:force_original_aspect_ratio=increase,"
            f"crop={small_w}:{small_h},boxblur={radius}:2,"
            f"scale={width}:{height},setsar=1[fitbgb];"
            f"[fitfg]scale={width}:-2:force_original_aspect_ratio=decrease,setsar=1[fitfgs];"
            f"[fitbgb][fitfgs]overlay=x=(W-w)/2:y='min(max(0,(H-h)*{position_y:.3f}),H-h)'"
        )

    color = cfg.screen.pad_color.replace("#", "0x")
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={color},setsar=1"
    )


def _unique_labels(chain: str, suffix: str) -> str:
    """Метки внутри fit_filter общие для всех источников — разводим их.

    Иначе второй скринкаст переиспользует метки первого и FFmpeg ругается
    на дубли имён в фильтрографе.
    """
    for label in ("fitbg", "fitfg", "fitbgb", "fitfgs"):
        chain = chain.replace(f"[{label}]", f"[{label}{suffix}]")
    return chain


# --------------------------------------------------------------------------- #
# Видеослои
# --------------------------------------------------------------------------- #


def _zoom_expression(events: list[Event], cfg: Config) -> str:
    """Выражение масштаба для zoompan: трапеция «наехали — держим — отъехали»."""
    amount = cfg.zoom.amount
    ramp = max(0.05, cfg.zoom.ramp)
    expression = "1"
    for event in events:
        start, end = event.start, event.end or (event.start + cfg.zoom.duration)
        ramped = (
            f"1+{amount - 1:.4f}*max(0,min(1,min((in_time-{start:.3f})/{ramp:.3f},"
            f"({end:.3f}-in_time)/{ramp:.3f})))"
        )
        expression = f"if(between(in_time,{start:.3f},{end:.3f}),{ramped},{expression})"
    return expression


def _video_chain(
    events: list[Event],
    inputs: dict[int, Event],
    cfg: Config,
    ass_path: Path | None,
    base_info: ffmpeg_utils.MediaInfo | None = None,
) -> list[str]:
    """Фильтры видеослоёв: база -> зум -> скринкасты -> вставки -> субтитры."""
    parts: list[str] = []
    fit = fit_filter(cfg, cfg.video.fit, cfg.video.position_y, base_info)
    parts.append(f"[0:v]{_unique_labels(fit, 'b')},fps={cfg.video.fps}[base]")
    current = "base"

    zooms = [event for event in events if event.kind == "zoom"]
    if zooms:
        expression = _zoom_expression(zooms, cfg)
        parts.append(
            f"[{current}]zoompan=z='{expression}'"
            f":x='max(0,min(iw*zoom-ow,{cfg.zoom.focus_x:.3f}*iw*zoom-ow/2))'"
            f":y='max(0,min(ih*zoom-oh,{cfg.zoom.focus_y:.3f}*ih*zoom-oh/2))'"
            f":d=1:s={cfg.video.width}x{cfg.video.height}:fps={cfg.video.fps}[zoomed]"
        )
        current = "zoomed"

    for index, event in sorted(inputs.items()):
        if event.kind == "screen":
            label = f"scr{index}"
            fit_screen = _unique_labels(
                fit_filter(
                    cfg,
                    cfg.screen.mode,
                    cfg.screen.position_y,
                    event.params.get("info"),
                ),
                str(index),
            )
            scale = cfg.screen.scale
            extra = f",scale=iw*{scale:.3f}:ih*{scale:.3f}" if abs(scale - 1.0) > 0.01 else ""
            parts.append(
                f"[{index}:v]trim=0:{event.duration:.3f},setpts=PTS-STARTPTS,"
                f"{fit_screen}{extra},fps={cfg.video.fps},"
                f"setpts=PTS-STARTPTS+{event.start:.3f}/TB[{label}]"
            )
            parts.append(
                f"[{current}][{label}]overlay=x=0:y=0:eof_action=pass:"
                f"enable='between(t,{event.start:.3f},{event.end:.3f})'[v{index}]"
            )
            current = f"v{index}"

        elif event.kind == "insert":
            label = f"ins{index}"
            max_width = int(cfg.video.width * cfg.insert.max_width)
            max_height = int(cfg.video.height * cfg.insert.max_height)
            fade = min(cfg.insert.fade, (event.duration or 1.0) / 2.5)
            # min(iw,...) — картинка только уменьшается: мелкую иконку
            # растягивать на пол-экрана не нужно.
            chain = (
                f"[{index}:v]scale=w='min(iw,{max_width})':h='min(ih,{max_height})':"
                f"force_original_aspect_ratio=decrease,format=rgba,setsar=1"
            )
            if fade > 0.05:
                chain += (
                    f",fade=t=in:st=0:d={fade:.3f}:alpha=1"
                    f",fade=t=out:st={max(0.0, (event.duration or 1.0) - fade):.3f}"
                    f":d={fade:.3f}:alpha=1"
                )
            chain += f",setpts=PTS-STARTPTS+{event.start:.3f}/TB[{label}]"
            parts.append(chain)

            x, y = _insert_position(cfg)
            parts.append(
                f"[{current}][{label}]overlay=x={x}:y={y}:eof_action=pass:"
                f"enable='between(t,{event.start:.3f},{event.end:.3f})'[v{index}]"
            )
            current = f"v{index}"

    if ass_path is not None:
        fonts = ffmpeg_utils.escape_filter_value(str(ass_path.parent.resolve()))
        subtitle_args = f"filename={ffmpeg_utils.escape_filter_value(str(ass_path.resolve()))}"
        from .config import FONTS_DIR

        if FONTS_DIR.is_dir():
            fonts = ffmpeg_utils.escape_filter_value(str(FONTS_DIR.resolve()))
        parts.append(f"[{current}]subtitles={subtitle_args}:fontsdir={fonts}[vout]")
    else:
        parts.append(f"[{current}]null[vout]")

    return parts


def _insert_position(cfg: Config) -> tuple[str, str]:
    """Координаты оверлея для позиции из конфига."""
    margin = cfg.insert.margin
    horizontal = {
        "left": f"{margin}",
        "center": "(W-w)/2",
        "right": f"W-w-{margin}",
    }
    vertical = {
        "top": f"{margin}",
        "center": "(H-h)/2",
        "bottom": f"H-h-{margin}",
    }

    position = cfg.insert.position.strip().lower()
    if position == "center":
        return horizontal["center"], vertical["center"]
    if position in ("top", "bottom"):
        return horizontal["center"], vertical[position]
    if position in ("left", "right"):
        return horizontal[position], vertical["center"]

    parts = position.replace("_", "-").split("-")
    if len(parts) == 2 and parts[0] in vertical and parts[1] in horizontal:
        return horizontal[parts[1]], vertical[parts[0]]

    log.warning("непонятная позиция вставки «%s» — ставлю по центру", cfg.insert.position)
    return horizontal["center"], vertical["center"]


# --------------------------------------------------------------------------- #
# Звук
# --------------------------------------------------------------------------- #


def _audio_chain(
    inputs: dict[int, Event],
    cfg: Config,
    has_voice: bool,
    total_duration: float,
) -> tuple[list[str], str | None]:
    """Фильтры звука: голос, эффекты, музыка с дакингом, сведение."""
    rate = cfg.video.sample_rate
    audio_format = AUDIO_FORMAT.format(rate=rate)
    parts: list[str] = []
    mix_labels: list[str] = []

    music_events = {i: e for i, e in inputs.items() if e.kind == "music"}
    screens_with_audio = {
        i: e
        for i, e in inputs.items()
        if e.kind == "screen" and cfg.screen.audio in ("mix", "replace") and e.params.get("has_audio")
    }

    if has_voice:
        voice_chain = f"[0:a]{audio_format}"
        # Режим replace: на время скринкаста голос глушим.
        for event in screens_with_audio.values():
            if cfg.screen.audio == "replace":
                voice_chain += (
                    f",volume=0:enable='between(t,{event.start:.3f},{event.end:.3f})'"
                )
        needs_sidechain = bool(music_events) and cfg.music.duck
        if needs_sidechain:
            parts.append(f"{voice_chain},asplit=2[voice][voicesc]")
        else:
            parts.append(f"{voice_chain}[voice]")
        mix_labels.append("voice")

    for index, event in sorted(inputs.items()):
        if event.kind == "sound":
            delay = int(event.start * 1000)
            parts.append(
                f"[{index}:a]{audio_format},volume={cfg.sound.volume:.3f},"
                f"adelay={delay}:all=1[snd{index}]"
            )
            mix_labels.append(f"snd{index}")

        elif event.kind == "screen" and index in screens_with_audio:
            delay = int(event.start * 1000)
            parts.append(
                f"[{index}:a]{audio_format},atrim=0:{event.duration:.3f},"
                f"asetpts=PTS-STARTPTS,volume={cfg.screen.audio_volume:.3f},"
                f"adelay={delay}:all=1[scra{index}]"
            )
            mix_labels.append(f"scra{index}")

        elif event.kind == "music":
            duration = event.duration or 0.0
            fade_in = min(cfg.music.fade_in, duration / 2)
            fade_out = min(cfg.music.fade_out, duration / 2)
            chain = (
                f"[{index}:a]{audio_format},atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
                f"volume={cfg.music.volume:.3f}"
            )
            if fade_in > 0.05:
                chain += f",afade=t=in:st=0:d={fade_in:.3f}"
            if fade_out > 0.05:
                chain += f",afade=t=out:st={duration - fade_out:.3f}:d={fade_out:.3f}"
            chain += f"[music{index}]"
            parts.append(chain)

            if has_voice and cfg.music.duck:
                # sidechaincompress: первый вход — что сжимаем (музыка),
                # второй — что управляет сжатием (голос).
                parts.append(
                    f"[music{index}][voicesc]sidechaincompress="
                    f"threshold={cfg.music.duck_threshold}:ratio={cfg.music.duck_ratio}:"
                    f"attack={cfg.music.duck_attack_ms}:release={cfg.music.duck_release_ms}"
                    f"[ducked{index}]"
                )
                source = f"ducked{index}"
            else:
                source = f"music{index}"

            parts.append(f"[{source}]adelay={int(event.start * 1000)}:all=1[mus{index}]")
            mix_labels.append(f"mus{index}")

    if not mix_labels:
        return parts, None

    if len(mix_labels) == 1:
        parts.append(f"[{mix_labels[0]}]anull[amixed]")
    else:
        joined = "".join(f"[{label}]" for label in mix_labels)
        # normalize=0: громкости уже выставлены в конфиге, амикс не должен
        # делить их на число дорожек.
        # duration=longest: если голоса нет вовсе, микс не должен обрываться
        # по первой попавшейся дорожке (например, по короткому эффекту).
        parts.append(
            f"{joined}amix=inputs={len(mix_labels)}:duration=longest:"
            f"dropout_transition=0:normalize=0[amixed]"
        )

    # Дотягиваем звук тишиной до конца видео, иначе -shortest обрежет картинку
    # там, где кончилась звуковая дорожка. Длительность обязательно явная:
    # apad без границы генерирует тишину бесконечно, и FFmpeg не завершается.
    pad = f"apad=whole_dur={total_duration:.3f}"
    if cfg.video.loudnorm:
        parts.append(
            f"[amixed]{pad},loudnorm=I={cfg.video.loudnorm_i}:TP={cfg.video.loudnorm_tp}:"
            f"LRA={cfg.video.loudnorm_lra},aresample={rate}[aout]"
        )
    else:
        parts.append(f"[amixed]{pad},aresample={rate}[aout]")
    return parts, "aout"


# --------------------------------------------------------------------------- #
# Сборка
# --------------------------------------------------------------------------- #


def compose(
    video: Path,
    events: list[Event],
    out_path: Path,
    cfg: Config,
    *,
    ass_path: Path | None = None,
) -> Path:
    """Собирает финальный ролик: оверлеи, звук, музыка с дакингом, субтитры, экспорт."""
    video = Path(video)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    base = ffmpeg_utils.media_info(video)
    input_args: list[str] = ["-i", str(video)]
    inputs: dict[int, Event] = {}
    index = 1

    for event in events:
        if event.source is None:
            continue
        args = _input_args_for(event, cfg, base.duration)
        if args is None:
            continue
        input_args.extend(args)
        inputs[index] = event
        index += 1

    graph_parts = _video_chain(events, inputs, cfg, ass_path, base)
    audio_parts, audio_label = _audio_chain(
        inputs, cfg, has_voice=base.has_audio, total_duration=base.duration
    )
    graph_parts.extend(audio_parts)

    output_args = ["-map", "[vout]"]
    if audio_label:
        output_args += ["-map", f"[{audio_label}]"]
    output_args += [
        "-c:v",
        cfg.video.video_codec,
        "-crf",
        str(cfg.video.crf),
        "-preset",
        cfg.video.preset,
        "-pix_fmt",
        cfg.video.pix_fmt,
        "-r",
        str(cfg.video.fps),
    ]
    if audio_label:
        output_args += [
            "-c:a",
            cfg.video.audio_codec,
            "-b:a",
            cfg.video.audio_bitrate,
            "-ar",
            str(cfg.video.sample_rate),
        ]
    output_args += ["-movflags", "+faststart", "-shortest", str(out_path)]

    log.info(
        "композитинг: %d источников, %d событий -> %s",
        len(inputs) + 1,
        len(events),
        out_path.name,
    )
    ffmpeg_utils.run_filter_complex(
        ";".join(graph_parts),
        input_args=input_args,
        output_args=output_args,
        desc="композитинг",
        script_dir=out_path.parent,
    )
    return out_path


def _input_args_for(event: Event, cfg: Config, base_duration: float) -> list[str] | None:
    """Аргументы входа FFmpeg для события. None — событие пропускаем."""
    source = event.source
    if source is None or not source.is_file():
        log.warning("файл %s не найден — событие %s пропущено", source, event.kind)
        return None

    if event.kind == "insert":
        duration = event.duration or cfg.insert.default_duration
        if source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            # Картинка -> видеопоток нужной длины.
            return [
                "-loop",
                "1",
                "-framerate",
                str(cfg.video.fps),
                "-t",
                f"{duration:.3f}",
                "-i",
                str(source),
            ]
        return ["-t", f"{duration:.3f}", "-i", str(source)]

    if event.kind == "screen":
        info = ffmpeg_utils.media_info(source)
        event.params["has_audio"] = info.has_audio
        event.params["info"] = info
        if event.end is not None and info.duration > 0:
            wanted = event.end - event.start
            if wanted > info.duration + 0.05:
                log.warning(
                    "%s: скринкаст короче нужного (%.1f с против %.1f с) — "
                    "показываю сколько есть",
                    event.params.get("tag", source.name),
                    info.duration,
                    wanted,
                )
                event.end = event.start + info.duration
        return ["-i", str(source)]

    if event.kind == "music":
        info = ffmpeg_utils.media_info(source)
        wanted = (event.end or base_duration) - event.start
        if cfg.music.loop and info.duration > 0 and info.duration < wanted:
            log.info(
                "музыка %s короче нужного (%.1f с) — зацикливаю",
                source.name,
                info.duration,
            )
            return ["-stream_loop", "-1", "-i", str(source)]
        return ["-i", str(source)]

    return ["-i", str(source)]


def burn_subtitles(video: Path, ass_path: Path, out_path: Path, cfg: Config) -> Path:
    """Вшивает .ass в видео отдельным быстрым проходом — примерка стиля.

    Кадр приводится к целевому формату, иначе кегль и отступы в превью
    выглядели бы не так, как в готовом ролике. Оверлеи и зум не считаются.
    """
    from .config import FONTS_DIR

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fonts = FONTS_DIR if FONTS_DIR.is_dir() else ass_path.parent
    fit = _unique_labels(
        fit_filter(cfg, cfg.video.fit, cfg.video.position_y, ffmpeg_utils.media_info(video)), "b"
    )
    graph = (
        f"[0:v]{fit},subtitles="
        f"{ffmpeg_utils.escape_filter_value(str(Path(ass_path).resolve()))}"
        f":fontsdir={ffmpeg_utils.escape_filter_value(str(fonts.resolve()))}[vout]"
    )
    ffmpeg_utils.run_filter_complex(
        graph,
        input_args=["-i", str(video)],
        output_args=[
            "-map",
            "[vout]",
            "-map",
            "0:a?",
            "-c:v",
            cfg.video.video_codec,
            "-crf",
            str(cfg.video.crf),
            "-preset",
            cfg.video.preset,
            "-pix_fmt",
            cfg.video.pix_fmt,
            "-c:a",
            "copy",
            str(out_path),
        ],
        desc="вшивание субтитров",
        script_dir=out_path.parent,
    )
    return out_path
