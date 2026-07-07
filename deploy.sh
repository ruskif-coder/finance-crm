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
    echo "[3/3] Rebuilding Next.js (3-5 min)..."
    docker exec finance_frontend sh -c "cd /app && rm -rf .next && npm run build"
    docker restart finance_frontend
    echo "Frontend deployed."
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
    docker exec -t finance_db pg_dump -U finance_user finance > $PROJECT/backups/backup_$TIMESTAMP.sql
    # Keep last 14
    ls -t $PROJECT/backups/backup_*.sql 2>/dev/null | tail -n +15 | xargs rm -f 2>/dev/null || true
    echo "Backup created: backups/backup_$TIMESTAMP.sql"
    ls -lh $PROJECT/backups/backup_$TIMESTAMP.sql
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
    echo "Usage: deploy.sh {pull|backend|frontend|full|migrate <script>|backup|status|logs [service]}"
    echo ""
    echo "  pull              - git pull only"
    echo "  backend           - git pull + copy backend files + restart backend"
    echo "  frontend          - git pull + copy frontend files + rebuild + restart"
    echo "  full              - git pull + full docker compose rebuild (~10 min)"
    echo "  migrate <script>  - apply SQL script to DB"
    echo "  backup            - pg_dump to backups/, keep last 14"
    echo "  status            - show container status"
    echo "  logs [service]    - follow logs (service: backend/frontend/db/caddy)"
    ;;
esac
