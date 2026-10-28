# Браузер для обхода экранов (e2e/walk_screens.py); база — Debian 12, Debian 13 Playwright 1.48 не поддерживает. Свой образ, а не официальный mcr.microsoft.com/playwright: реестр Microsoft
# со стенда не отдаёт слои (27.10.2026), а PyPI и сервер браузеров Playwright доступны. Сборка — e2e/run.sh, если образа нет.
FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir playwright==1.48.0 \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
