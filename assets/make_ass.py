#!/usr/bin/env python3
import re

# (start_sec, end_sec, text) from the cleaned SRT
CUES = [
    (0.38, 4.28, "Как создать американский YouTube-канал с телефона за 5 минут без зарубежного номера?"),
    (4.54, 6.44, "Для начала заходим в Google, выбираем создать аккаунт"),
    (6.44, 9.48, "для личного использования, вписываем имя и фамилию."),
    (9.98, 13.58, "Далее вписываем день рождения, месяц и ставим дату,"),
    (13.76, 15.26, "чтобы нам было больше 18 лет."),
    (16.00, 19.38, "Далее выбираем почту на выбор, вписываем надёжный пароль,"),
    (22.12, 25.58, "дальше принимаем всё, что говорит нам Google, и"),
    (25.58, 27.28, "нас переносит уже в созданный аккаунт."),
    (27.90, 30.28, "Далее заходим на YouTube, нажимаем на наш аккаунт,"),
    (30.66, 34.10, "нажимаем создать канал, выбираем здесь аватарку и имя,"),
    (34.66, 37.12, "нажимаем создать канал — и всё, наш канал создан."),
    (37.54, 40.06, "Далее заходим в Google Play и скачиваем творческую студию."),
    (40.32, 43.76, "Заходим в неё, заходим в наш аккаунт, выбираем"),
    (43.76, 48.20, "шестерёнку сверху справа, и мы можем найти здесь"),
    (48.20, 52.00, "настройки, поставить любую страну, не обязательно ставить Америку,"),
    (52.50, 54.38, "любую страну кроме России и Беларуси."),
]

def ass_time(t):
    h = int(t // 3600); t -= h*3600
    m = int(t // 60); t -= m*60
    s = int(t); cs = int(round((t - s) * 100))
    if cs == 100:
        cs = 0; s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Montserrat ExtraBold,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2.6,0,2,60,60,470,1
"""

events = []
for (start, end, text) in CUES:
    # split into words, drop leftover punctuation-only tokens attached
    words = text.split()
    # allocate duration proportional to word length (min weight 1)
    weights = [max(len(w), 2) for w in words]
    total = sum(weights)
    dur = end - start
    t = start
    for w, wt in zip(words, weights):
        wdur = dur * wt / total
        w_start = t
        w_end = t + wdur
        t = w_end
        disp = w.upper()
        # escape ass special
        disp = disp.replace("\\", "\\\\").replace("{", "(").replace("}", ")")
        events.append(f"Dialogue: 0,{ass_time(w_start)},{ass_time(w_end)},Sub,,0,0,0,,{disp}")

with open("subs.ass", "w", encoding="utf-8") as f:
    f.write(HEADER + "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    f.write("\n".join(events) + "\n")

print(f"Wrote subs.ass with {len(events)} word events")
