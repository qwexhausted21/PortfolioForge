#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  PortfolioForge — запуск приложения"
echo "=========================================="
echo

echo "[1/4] Проверка Python…"
command -v python3 >/dev/null || { echo "Python 3 не найден. Установите Python 3.11+."; exit 1; }

echo "[2/4] Виртуальное окружение…"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate

echo "[3/4] Зависимости…"
pip install --upgrade pip >/dev/null 2>&1 || true
pip install -r requirements.txt

echo "[4/4] Настройка .env…"
if [ ! -f .env ]; then
    cp .env.example .env
fi

echo
echo "Запуск PortfolioForge…"
echo "(окно браузера откроется автоматически)"
echo
python app.py
