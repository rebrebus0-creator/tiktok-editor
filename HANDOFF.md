# HANDOFF — где мы сейчас (для Claude Code в новом окружении)

Прочитай этот файл целиком, потом `README.md` и `jobs/minute1/README.md`.

## Задача
Есть говорящий аватар из HeyGen (ролик ~9:35, немецкий, японский повар Хироси рассказывает, как чистить ананас).
Поверх него нужно наложить графику и картинки по смыслу речи в стиле «уголовного дела» (референс: ролик про перевал Дятлова):
бумажные заметки на скотче, машинописный текст, красные штампы, полароиды, красные обводки, счётчики цифр,
сплит-экран (аватар уезжает в рамку, рядом фото), плёночное зерно. Фото выезжают/разъезжаются, аватар периодически появляется.

Формат 16:9. Текст на экране — на языке ролика (немецкий).

## План, согласованный с заказчиком
1. **Сейчас:** смонтировать **только первую минуту** с картинками из генератора FastGen (без стока Pexels).
2. Если стиль понравится — смонтировать весь ролик (~10 мин).
3. Только потом оформлять это как модуль/плагин для их софта.

## Важные решения
- **Не использовать Anthropic API.** Раскадровку (plan.json) пишет сам Claude Code по транскрипту. В модуле это тоже будет делать
  Claude Code на их сервере. Файл `pipeline/plan.ts` (вызов API) — legacy, не запускать; позже убрать.
- **Картинки — генерация через FastGen** (fast-gen.ai), не сток.
- Транскрипция: `faster-whisper` (pipeline/transcribe.py) или офлайн whisper-base через npm-пакет `sts-whisper-base` + `@huggingface/transformers`.

## Что уже сделано (ветка `claude/confident-rubin-e809s1`)
- Remotion-проект: `src/` — 10 шаблонов сцен (photo, split, note, quote, checklist, numbers, polaroids, stamp, label, board), плёнка, звуки.
- Пайплайн: `pipeline/` — транскрипт → план → ассеты (FastGen/Pexels/fal) → рендер.
- `jobs/minute1/plan.json` — **готовая раскадровка первой минуты** (10 сцен, промпты для картинок на английском).
- `jobs/minute1/transcript.json` — транскрипт первой минуты.
- Превью минуты с заглушками вместо фото уже отрендерено и одобрено по таймингу (ждём картинки).

## Что осталось сделать прямо сейчас
1. Положить первую минуту ролика в `public/input/minute1.mp4` (если её нет — вырезать из исходника):
   `ffmpeg -i <исходник>.mp4 -t 60 -c:v libx264 -crf 16 -c:a aac public/input/minute1.mp4`
2. Создать `settings.json` в корне (он в .gitignore, ключ не коммитить):
   ```json
   {"imageProvider": "fastgen", "fastgen": {"apiKey": "<КЛЮЧ FASTGEN>"}}
   ```
3. Проверить FastGen API:
   - базовый URL не указан в их OpenAPI — по умолчанию стоит `https://api.fast-gen.ai`; проверить `GET <base>/api/health`,
     если не отвечает — попробовать `https://fast-gen.ai`. Поменять `fastgen.baseUrl` в settings.json.
   - `GET <base>/api/v6/capabilities?media_type=image` (заголовок `X-API-Key`) — получить актуальный список моделей
     и выбрать лучшую для фотореалистичных фото (сейчас стоит `gemini_nano_banana_2_image_generate`, 1 кредит; заказчик
     упоминал более новые версии — выбрать актуальную). Поменять `fastgen.operation`.
   - Поток: `POST /api/v6/generations {operation, prompt, aspect_ratio:"16:9"}` → `id` →
     опрос `GET /api/v6/generations/{id}` до `status: succeeded` → `results[0].download_url`.
4. Сгенерировать картинки и отрендерить:
   ```
   npm install
   npm run fetch -- jobs/minute1/plan.json minute1
   npm run render -- jobs/minute1/plan.resolved.json out/minute1.mp4
   ```
5. Проверить кадры (ffmpeg contact sheet), показать заказчику.

## Заметки
- Рендер: на слабом облачном контейнере ~8× от реального времени в 1080p; разрешение по умолчанию = исходник (720p).
- Если Remotion не находит Chrome — он скачает свой; или указать `render.browserExecutable` в settings.json.
- Исходные материалы (референс Дятлова, звуки) уже в репо: звуки в `public/sfx/`.
