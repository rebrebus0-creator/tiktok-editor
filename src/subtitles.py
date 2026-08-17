"""Генерация караоке-субтитров .ass — ЭТАП 2.

Слова с таймкодами Whisper собираются в плашки по 2-3 слова. Внутри плашки
на каждое слово создаётся отдельная строка Dialogue, где это слово выделено
цветом: получается привычный для коротких роликов эффект «текущее слово
подсвечено», а не постепенная закраска всей строки.

Стиль (шрифт, размер, цвета, положение) берётся из config.subtitles,
файл шрифта — из assets/fonts (передаётся в FFmpeg через `fontsdir`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .models import Word

log = logging.getLogger(__name__)

STAGE = 2
STAGE_TITLE = "Караоке-субтитры"

# Плашка держится на экране ещё чуть-чуть после последнего слова —
# иначе текст пропадает ровно в момент, когда его дочитывают.
TAIL_HOLD = 0.25


def group_words(words: list[Word], cfg: Config) -> list[list[Word]]:
    """Разбивает поток слов на плашки субтитров."""
    settings = cfg.subtitles
    chunks: list[list[Word]] = []
    current: list[Word] = []

    for word in words:
        if not word.text:
            continue
        if current:
            gap = word.start - current[-1].end
            length = sum(len(item.text) + 1 for item in current) + len(word.text)
            # Новая плашка, если слов уже достаточно, строка длинная
            # или между словами заметная пауза (значит, новая мысль).
            if (
                len(current) >= settings.max_words
                or length > settings.max_chars
                or gap > settings.max_gap
            ):
                chunks.append(current)
                current = []
        current.append(word)

    if current:
        chunks.append(current)
    return chunks


def build_ass(words: list[Word], out_path: Path, cfg: Config) -> Path:
    """Пишет .ass с караоке-подсветкой. Таймкоды — уже финальные."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    chunks = group_words(words, cfg)
    lines = [_header(cfg)]

    for chunk in chunks:
        lines.extend(_chunk_lines(chunk, cfg))

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info(
        "субтитры: %d слов -> %d плашек -> %s",
        len(words),
        len(chunks),
        out_path.name,
    )
    return out_path


def _chunk_lines(chunk: list[Word], cfg: Config) -> list[str]:
    """Строки Dialogue для одной плашки: по одной на каждое подсвеченное слово."""
    settings = cfg.subtitles
    highlight = to_ass_color_inline(settings.highlight_color)
    primary = to_ass_color_inline(settings.primary_color)

    chunk_end = chunk[-1].end + TAIL_HOLD
    lines: list[str] = []

    for index, word in enumerate(chunk):
        start = word.start
        # Подсветка держится до начала следующего слова, чтобы не мигало.
        end = chunk[index + 1].start if index + 1 < len(chunk) else chunk_end
        if end - start < 0.04:
            continue

        parts: list[str] = []
        for position, item in enumerate(chunk):
            text = _escape(item.text.upper() if settings.uppercase else item.text)
            if position == index:
                parts.append(f"{{\\c{highlight}}}{text}{{\\c{primary}}}")
            else:
                parts.append(text)

        lines.append(
            f"Dialogue: 0,{_timestamp(start)},{_timestamp(end)},Karaoke,,0,0,0,,"
            + " ".join(parts)
        )
    return lines


def _header(cfg: Config) -> str:
    settings = cfg.subtitles
    # PlayRes должен совпадать с разрешением ролика: тогда размер шрифта и
    # отступы в конфиге означают ровно то, что видно в кадре.
    return "\n".join(
        [
            "[Script Info]",
            "; Сгенерировано tiktok-editor",
            "ScriptType: v4.00+",
            f"PlayResX: {cfg.video.width}",
            f"PlayResY: {cfg.video.height}",
            # 0 — умный перенос: длинная плашка переносится на вторую строку,
            # а не уезжает за края кадра.
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Karaoke,"
            f"{settings.font_name},{settings.font_size},"
            f"{to_ass_color(settings.primary_color)},"
            f"{to_ass_color(settings.highlight_color)},"
            f"{to_ass_color(settings.outline_color)},"
            f"{to_ass_color('#000000', alpha=160)},"
            f"{-1 if settings.bold else 0},0,0,0,"
            "100,100,0,0,1,"
            f"{settings.outline},{settings.shadow},"
            f"{settings.alignment},{settings.margin_h},{settings.margin_h},"
            f"{settings.margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )


def _timestamp(seconds: float) -> str:
    """Время в формате ASS: H:MM:SS.cc (сотые доли)."""
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = seconds % 60
    return f"{hours}:{minutes:02d}:{whole:05.2f}"


def _escape(text: str) -> str:
    """Символы, которые в ASS означают разметку, а не текст."""
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR (в ASS порядок байтов обратный)."""
    red, green, blue = _rgb(hex_color)
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"


def to_ass_color_inline(hex_color: str) -> str:
    """#RRGGBB -> &HBBGGRR& — форма для тега \\c внутри строки."""
    red, green, blue = _rgb(hex_color)
    return f"&H{blue:02X}{green:02X}{red:02X}&"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) == 3:  # #FFF -> #FFFFFF
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        log.warning("непонятный цвет «%s» — беру белый", hex_color)
        return (255, 255, 255)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        log.warning("непонятный цвет «%s» — беру белый", hex_color)
        return (255, 255, 255)
