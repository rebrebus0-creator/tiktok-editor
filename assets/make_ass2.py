#!/usr/bin/env python3
import re, json

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

HOOK_END = 4.28  # first cue = hook

# Important words in the hook -> RED (+ click). Compared without punctuation, uppercased.
RED_WORDS = {"АМЕРИКАНСКИЙ", "YOUTUBE-КАНАЛ", "5", "МИНУТ", "ЗАРУБЕЖНОГО", "НОМЕРА"}

def norm(w):
    return re.sub(r"[^\w-]", "", w, flags=re.UNICODE).upper()

def strip_punct(w):
    # remove commas, periods, dashes, ellipsis, quotes, ! ? etc. keep letters/digits and inner hyphen
    return re.sub(r"[.,!?…«»\"'—–-]", "", w).strip()

def ass_time(t):
    h = int(t // 3600); t -= h*3600
    m = int(t // 60); t -= m*60
    s = int(t); cs = int(round((t - s) * 100))
    if cs == 100: cs = 0; s += 1
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
Style: Hook,Montserrat ExtraBold,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3.0,0,2,40,40,470,1
"""

WHITE = "&H00FFFFFF&"
RED   = "&H000000FF&"   # BBGGRR -> pure red

events = []
click_times = []

for (start, end, text) in CUES:
    is_hook = start < HOOK_END
    if is_hook:
        continue  # hook subtitles removed — user edits the first seconds himself
    words = [strip_punct(x) for x in text.split()]
    words = [x for x in words if x]
    weights = [max(len(w), 2) for w in words]
    total = sum(weights)
    dur = end - start
    t = start
    for w, wt in zip(words, weights):
        wdur = dur * wt / total
        ws, we = t, t + wdur
        t = we
        disp = w.upper().replace("\\", "").replace("{", "(").replace("}", ")")
        style = "Hook" if is_hook else "Sub"
        red = is_hook and norm(w) in RED_WORDS
        main_col = RED if red else WHITE
        if red:
            click_times.append(round(ws, 2))
        # glow layer (blurred white halo) - layer 0
        glow_blur = 7 if is_hook else 5
        glow = (f"Dialogue: 0,{ass_time(ws)},{ass_time(we)},{style},,0,0,0,,"
                f"{{\\blur{glow_blur}\\bord0\\shad0\\1c{WHITE}\\alpha&H35&}}{disp}")
        # main layer - layer 1. Hook: camera pull-back (125%->100%)
        if is_hook:
            anim = "{\\fscx126\\fscy126\\t(0,190,\\fscx100\\fscy100)}"
        else:
            anim = "{\\fscx88\\fscy88\\t(0,110,\\fscx100\\fscy100)}"
        main = (f"Dialogue: 1,{ass_time(ws)},{ass_time(we)},{style},,0,0,0,,"
                f"{anim}{{\\1c{main_col}}}{disp}")
        events.append(glow)
        events.append(main)

with open("subs2.ass", "w", encoding="utf-8") as f:
    f.write(HEADER + "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    f.write("\n".join(events) + "\n")

with open("clicks.json", "w") as f:
    json.dump(click_times, f)

print(f"subs2.ass: {len(events)} events, red/click words at: {click_times}")
