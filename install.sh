#!/usr/bin/env bash
# Установка окружения (macOS / Linux). Запускать из корня репозитория:
#   bash install.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "== 1/3 FFmpeg =="
if command -v ffmpeg >/dev/null 2>&1; then
    echo "уже установлен: $(ffmpeg -version | head -1)"
elif command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
else
    echo "FFmpeg не найден, и brew недоступен."
    echo "Mac:   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\" && brew install ffmpeg"
    echo "Linux: sudo apt install ffmpeg"
    exit 1
fi

echo
echo "== 2/3 Python-окружение =="
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"нужен Python 3.11+, найден {sys.version.split()[0]}")
PY

if [ ! -d .venv ]; then
    "$PYTHON_BIN" -m venv .venv
    echo "создано виртуальное окружение .venv"
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "зависимости установлены"

echo
echo "== 3/3 Проверка =="
./.venv/bin/python -m src.main check || true

echo
echo "Активировать окружение:  source .venv/bin/activate"
echo "Создать проект:          python -m src.main init my-video"
