#!/usr/bin/env bash
# Обход экранов браузером на ЛОКАЛЬНОМ стенде (владелец 27.10.2026), см. e2e/walk_screens.py.
#   bash e2e/run.sh                 # админ, сейлз, аккаунт
#   bash e2e/run.sh admin role_9    # свои роли
# Входы выпускает backend/scripts/e2e_sessions.py в файл; файл с токенами удаляется по выходу, в вывод токены не попадают.
# Браузер ходит из сетевого пространства Caddy — https://localhost, тем же путём, что и пользователь.
set -euo pipefail
IMAGE=finance-e2e:1.48            # свой образ, рецепт — e2e/Dockerfile (реестр Microsoft со стенда не отдаёт слои)
ROOT=$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)
ROLES=${*:-admin role_7 role_8}
OUT="$ROOT/.tmp/e2e_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
export MSYS_NO_PATHCONV=1
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -t "$IMAGE" -f "$ROOT/e2e/Dockerfile" "$ROOT/e2e"
# Только локальный стенд: на проде контейнер называется так же, и скрипт выпустил бы боевые токены админа
DOMAIN_IN=$(docker exec finance_backend sh -c 'echo "${DOMAIN:-localhost}"')
if [ "$DOMAIN_IN" != "localhost" ]; then
  echo "Отказ: DOMAIN=$DOMAIN_IN — обход экранов запускается только на локальном стенде" >&2
  exit 2
fi
# Файл с токенами — и на диске, и в контейнере — удаляется при любом выходе, в том числе по ошибке
trap 'rm -f "$OUT/sessions.json"; docker exec finance_backend rm -f /tmp/e2e_sessions.json >/dev/null 2>&1 || true' EXIT
docker exec finance_backend mkdir -p /app/scripts
docker cp "$ROOT/backend/scripts/e2e_sessions.py" finance_backend:/app/scripts/e2e_sessions.py
docker exec -w /app finance_backend python -m scripts.e2e_sessions --out /tmp/e2e_sessions.json $ROLES
docker cp finance_backend:/tmp/e2e_sessions.json "$OUT/sessions.json"
docker exec finance_backend rm -f /tmp/e2e_sessions.json
docker exec finance_backend rm -f /app/scripts/e2e_sessions.py

docker run --rm --network container:finance_caddy -v "$ROOT:/work:ro" -v "$OUT:/out" "$IMAGE" \
  python /work/e2e/walk_screens.py --sessions /out/sessions.json --report /out/report.json
