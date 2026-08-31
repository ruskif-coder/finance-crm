#!/bin/bash
# deploy.sh - server-side deployment script for Finance CRM
# Called from deploy_server.bat via SSH: ssh root@SERVER bash /root/finance/deploy.sh <action> [arg]

set -e
PROJECT=/root/finance
cd $PROJECT

ACTION=${1:-help}

case "$ACTION" in

  pull)
    echo "[1/1] Git pull..."
    git pull
    echo "Done."
    ;;

  backend)
    echo "[1/2] Git pull..."
    git pull
    echo "[2/2] Copying backend files to container..."
    docker cp $PROJECT/backend/app finance_backend:/app/
    docker restart finance_backend
    echo "Backend deployed."
    ;;

  frontend)
    echo "[1/3] Git pull..."
    git pull
    echo "[2/3] Copying frontend files to container..."
    docker cp $PROJECT/frontend/pages finance_frontend:/app/
    docker cp $PROJECT/frontend/components finance_frontend:/app/
    docker cp $PROJECT/frontend/styles finance_frontend:/app/
    docker cp $PROJECT/frontend/public finance_frontend:/app/
    docker cp $PROJECT/frontend/lib finance_frontend:/app/
    # helpers/ здесь был до 31.08.2026 и ронял всё действие: каталог удалён из репозитория
    # (d195bea, уже на origin/main), а `set -e` на несуществующем источнике обрывает скрипт
    # ДО копирования scripts/ и до пересборки. Новый каталог сюда добавляется вместе с
    # проверкой, что он есть в гите.
    # scripts/ обязателен: prebuild зовёт check-nav, check-money и check-overlay
    # оттуда. Без этой строки package.json приезжает новый, а гейт — нет, и сборка
    # падает на "Cannot find module". Ровно это случилось бы на релизе 31.08.2026,
    # где добавился третий гейт (check-overlay.mjs).
    docker cp $PROJECT/frontend/scripts finance_frontend:/app/
    # next.config.js читает версию из package.json на этапе сборки — без них
    # в меню профиля останется версия, вшитая при последней полной пересборке.
    docker cp $PROJECT/frontend/next.config.js finance_frontend:/app/
    docker cp $PROJECT/frontend/package.json finance_frontend:/app/
    echo "[3/3] Rebuilding Next.js (3-5 min)..."
    docker exec finance_frontend sh -c "cd /app && rm -rf .next && npm run build"
    docker restart finance_frontend
    echo "Frontend deployed."
    ;;

  cabinet-backend)
    echo "[1/2] Git pull..."
    git pull
    echo "[2/2] Copying cabinet backend to container..."
    docker cp $PROJECT/cabinet/app cabinet_backend:/app/
    docker restart cabinet_backend
    echo "Cabinet backend deployed."
    ;;

  cabinet-frontend)
    echo "[1/3] Git pull..."
    git pull
    echo "[2/3] Copying cabinet frontend to container..."
    docker cp $PROJECT/cabinet-frontend/pages cabinet_frontend:/app/
    docker cp $PROJECT/cabinet-frontend/components cabinet_frontend:/app/
    docker cp $PROJECT/cabinet-frontend/lib cabinet_frontend:/app/
    docker cp $PROJECT/cabinet-frontend/styles cabinet_frontend:/app/
    docker cp $PROJECT/cabinet-frontend/public cabinet_frontend:/app/
    # Те же грабли, что у основного фронта: prebuild кабинета зовёт check-tokens и
    # check-hooks из scripts/.
    docker cp $PROJECT/cabinet-frontend/scripts cabinet_frontend:/app/
    docker cp $PROJECT/cabinet-frontend/next.config.js cabinet_frontend:/app/
    docker cp $PROJECT/cabinet-frontend/package.json cabinet_frontend:/app/
    echo "[3/3] Rebuilding cabinet Next.js..."
    docker exec cabinet_frontend sh -c "cd /app && rm -rf .next && npm run build"
    docker restart cabinet_frontend
    echo "Cabinet frontend deployed."
    ;;

  full)
    echo "[1/2] Git pull..."
    git pull
    echo "[2/2] Full rebuild (docker compose up --build, ~10 min)..."
    docker compose up -d --build
    echo "Full rebuild done."
    ;;

  migrate)
    SCRIPT=${2}
    if [ -z "$SCRIPT" ]; then
      echo "ERROR: specify script path, e.g.: deploy.sh migrate scripts/add_column.sql"
      exit 1
    fi
    echo "Applying migration: $SCRIPT"
    docker exec -i finance_db psql -U finance_user -d finance < $PROJECT/$SCRIPT
    echo "Migration applied."
    ;;

  backup)
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    mkdir -p $PROJECT/backups
    # Без -t: TTY добавляет CR в каждую строку дампа. Восстановление такого файла
    # проверено дважды (30 и 31.08.2026) и проходит чисто, данные не портятся — но
    # смысла в TTY здесь нет, а файл на 43 тысячи байт больше.
    docker exec -i finance_db pg_dump -U finance_user finance > $PROJECT/backups/backup_$TIMESTAMP.sql
    # Keep last 14
    ls -t $PROJECT/backups/backup_*.sql 2>/dev/null | tail -n +15 | xargs rm -f 2>/dev/null || true
    echo "Backup created: backups/backup_$TIMESTAMP.sql"
    ls -lh $PROJECT/backups/backup_$TIMESTAMP.sql
    ;;

  retention)
    # Уборка файлов по срокам хранения (скриншоты 30 дней, песочница 60, архивы 730).
    # Правила живут в app/traffic/retention.py, скрипт только обходит хранилище.
    #
    # Вешается в cron ОДНОЙ строкой — рядом с бэкапом и ПОСЛЕ него, чтобы удалённое
    # успевало попасть в свежий дамп:
    #     0 3 * * * bash /root/finance/deploy.sh backup
    #     30 3 * * * bash /root/finance/deploy.sh retention
    #
    # Без аргумента — СУХОЙ ПРОГОН: печатает, что удалил бы, и не трогает диск. Уборка
    # необратима, а сроки отмеряются от выхода со стадии «Отчёты в ОРД» — ошибка в
    # истории стадий стирает не тот файл. Поэтому боевой режим включается явно:
    #     bash deploy.sh retention apply
    MODE=${2:-""}
    mkdir -p $PROJECT/backups
    LOG=$PROJECT/backups/retention_log.txt
    if [ "$MODE" = "apply" ]; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] уборка (боевой режим)" >> $LOG
      docker exec finance_backend python -m scripts.2026-08-30_retention_sweep --apply >> $LOG 2>&1
    else
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] уборка (сухой прогон)" >> $LOG
      docker exec finance_backend python -m scripts.2026-08-30_retention_sweep >> $LOG 2>&1
    fi
    tail -n 3 $LOG
    ;;

  status)
    docker compose ps
    ;;

  logs)
    SERVICE=${2:-""}
    if [ -z "$SERVICE" ]; then
      docker compose logs -f
    else
      docker compose logs -f $SERVICE
    fi
    ;;

  help|*)
    echo "Usage: deploy.sh {pull|backend|frontend|cabinet-backend|cabinet-frontend|full|migrate <script>|backup|retention [apply]|status|logs [service]}"
    echo ""
    echo "  pull              - git pull only"
    echo "  backend           - git pull + copy backend files + restart backend"
    echo "  frontend          - git pull + copy frontend files + rebuild + restart"
    echo "  cabinet-backend   - git pull + copy cabinet backend + restart"
    echo "  cabinet-frontend  - git pull + copy cabinet frontend + rebuild + restart"
    echo "  full              - git pull + full docker compose rebuild (~10 min)"
    echo "  migrate <script>  - apply SQL script to DB"
    echo "  backup            - pg_dump to backups/, keep last 14"
    echo "  retention [apply] - delete stored files past their retention (dry run without apply)"
    echo "  status            - show container status"
    echo "  logs [service]    - follow logs (service: backend/frontend/db/caddy)"
    ;;
esac
