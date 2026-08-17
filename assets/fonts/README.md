# Шрифты субтитров

Сюда положи `.ttf` / `.otf` шрифта, которым будут набраны караоке-субтитры,
и укажи его в конфиге:

```toml
[subtitles]
font_name = "Montserrat ExtraBold"        # имя семейства внутри файла
font_file = "Montserrat-ExtraBold.ttf"    # имя файла в этой папке
```

Папка передаётся в FFmpeg параметром `fontsdir`, поэтому шрифт не нужно
устанавливать в систему — достаточно положить файл сюда.

Что хорошо смотрится в вертикальных роликах: жирные гротески с крупным
очком — Montserrat ExtraBold, Inter Black, Manrope ExtraBold, Roboto Black.
Проверь, что в шрифте есть кириллица.

Если файла нет, `python -m src.main check` предупредит, а libass возьмёт
системный шрифт по `font_name`.
