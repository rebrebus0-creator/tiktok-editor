# minute1 — первая минута ролика с Хироси (ананас, немецкий)

- Исходник: первые 60 с `video_57_szhatoe.mp4` (в git не лежит — положи файл в `public/input/minute1.mp4`).
  `ffmpeg -i video_57_szhatoe.mp4 -t 60 -c:v libx264 -crf 16 -c:a aac public/input/minute1.mp4`
- `transcript.json` — транскрипт (whisper-base, de).
- `plan.json` — раскадровка (10 сцен), промпты для генерации картинок на английском.

Генерация картинок FastGen + рендер:
```
npm run fetch -- jobs/minute1/plan.json minute1
npm run render -- jobs/minute1/plan.resolved.json out/minute1.mp4
```
Ключ FastGen — в `settings.json` (`"fastgen": {"apiKey": "..."}`) или переменной `FASTGEN_API_KEY`.
