#!/bin/bash
# deploy.sh - server-side deployment script for Finance CRM
# Called from deploy_server.bat via SSH: ssh root@SERVER bash /root/finance/deploy.sh <action> [arg]

set -e
PROJECT=/root/finance
cd $PROJECT
SELF="$PROJECT/$(basename "$0")"   # звать себя ТОЛЬКО абсолютным путём: при запуске
                                   # `cd /root/finance && bash deploy.sh migrate X`
                                   # переменная `$0` равна `deploy.sh`, и bash пошёл бы
                                   # искать её в PATH — «command not found» вместо бэкапа.

# `.env` читает не только compose. `BACKUPS_DIR` задаётся там и должен означать ОДИН
# каталог для трёх потребителей: монтажа бэкенду (docker-compose.yml), действия `backup`
# и уборки `retention`. Пока файл здесь не читался, владелец мог поставить
# `BACKUPS_DIR=/mnt/backups`, бэкенд показывал бы свежесть /mnt/backups, а cron писал бы
# в /root/finance/backups — экран состояния зелёный по чужому каталогу (найдено 11.09.2026).
# `set -a` экспортирует всё, что в файле; `|| true` — чтобы отсутствие файла не роняло
# действия, которым он не нужен (`pull`, `backend`, `frontend`).
if [ -f "$PROJECT/.env" ]; then
  set -a; . "$PROJECT/.env" 2>/dev/null || true; set +a
fi

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
      echo "ERROR: specify script path, e.g.: deploy.sh migrate backend/migrations/<file>.sql"
      exit 1
    fi
    [ -f "$PROJECT/$SCRIPT" ] || { echo "ERROR: file not found: $SCRIPT"; exit 1; }
    NAME=$(basename "$SCRIPT")
    # Апостроф в имени файла оборвал бы SQL учёта — уже ПОСЛЕ наката, то есть миграция
    # применена, а записать её нечем. Удваиваем по правилу SQL, а не надеемся на имена.
    NAME_SQL=$(printf '%s' "$NAME" | sed "s/'/''/g")
    SUM=$(sha256sum "$PROJECT/$SCRIPT" | cut -d' ' -f1)
    # `hostname -s` есть не везде (в Git Bash на Windows его нет), а под `set -e` падение
    # подстановки роняет скрипт ДО наката — то есть учёт ломал бы саму миграцию.
    WHO="$(whoami)@$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo unknown)"
    # Базу выбирает ПУТЬ, а не память оператора: файлы из `migrations/dsp/` идут в
    # аналитическую базу, и перепутать их значит завести hypertable рядом с боевыми
    # деньгами. Раньше это держалось только на внимательности и абзаце в README.
    case "$SCRIPT" in
      */migrations/dsp/*) DB_C=finance_dsp_db; DB_U=dsp;           DB_N=dsp_analytics ;;
      *)                  DB_C=finance_db;     DB_U=finance_user;  DB_N=finance ;;
    esac
    psql_() { docker exec -i "$DB_C" psql -U "$DB_U" -d "$DB_N" "$@"; }

    # ── учёт: предупреждаем, НЕ блокируем ───────────────────────────────────
    # Все миграции проекта повторно накатываемые, и законный повтор бывает — например
    # после восстановления из старого дампа. Запрет мешал бы ему; молчание же прячет
    # случай «накатываю второй раз, не заметив». Поэтому вопрос, а не отказ.
    PREV=$(psql_ -tAc "SELECT coalesce(to_char(applied_at,'YYYY-MM-DD HH24:MI'),'время неизвестно')
                         ||' · '|| coalesce(note,'')
                       FROM schema_migrations WHERE filename='$NAME_SQL'" 2>/dev/null || true)
    if [ -n "$PREV" ]; then
      echo "ВНИМАНИЕ: $NAME уже накатывали ($PREV)."
      OLDSUM=$(psql_ -tAc "SELECT coalesce(checksum,'') FROM schema_migrations WHERE filename='$NAME_SQL'" 2>/dev/null || true)
      if [ -n "$OLDSUM" ] && [ "$OLDSUM" != "$SUM" ]; then
        echo "         И ФАЙЛ ИЗМЕНИЛСЯ с тех пор: контрольная сумма другая."
      fi
      if [ -t 0 ]; then
        printf "         Накатить ещё раз? [y/N] "; read -r ANS
        case "$ANS" in y|Y|yes|да) ;; *) echo "Отменено."; exit 0 ;; esac
      else
        echo "         Неинтерактивный запуск — продолжаю."
      fi
    fi

    # Бэкап ПЕРЕД накатом — не пожелание в README, а шаг скрипта. README требовал его
    # словами, а одна команда накатывала SQL без него: оператор, забывший шаг, мог
    # рассчитывать только на ночной cron. Накат схемы необратим, и «откатимся, если что»
    # без свежего дампа означает «не откатимся».
    echo "[1/3] Backup before migration ($DB_N)..."
    # Бэкапим ТУ базу, которую сейчас меняем. До 11.09.2026 здесь стояло голое
    # `"$0" backup`, а `backup` всегда дампил `finance`: перед миграцией аналитической
    # базы печаталось «Backup before migration... ок» про совершенно другую базу.
    "$SELF" backup "$DB_N" || { echo "ABORT: backup failed, migration NOT applied"; exit 1; }

    echo "[2/3] Applying $NAME to $DB_N..."
    # ON_ERROR_STOP=1 ОБЯЗАТЕЛЕН. Без него psql печатает ERROR, идёт дальше и выходит с
    # кодом НОЛЬ — замерено 11.09.2026: файл из трёх команд с делением на ноль посередине
    # создал обе таблицы и вернул 0. То есть `set -e` сюда не доводил (комментарий,
    # стоявший на этом месте, утверждал обратное), наполовину накатанная миграция
    # записывалась в учёт как успешная, с верной контрольной суммой, и `migrate-status`
    # врал «накачено» навсегда.
    #
    # `--single-transaction` добавляем ТОЛЬКО когда файл это допускает:
    # `CREATE INDEX CONCURRENTLY` внутри транзакции запрещён самим Postgres, и такой
    # файл в проекте есть (2026-08-30_missing_fk_indexes.sql). Там остаётся
    # ON_ERROR_STOP: накат оборвётся на первой ошибке, но откатится не весь.
    if grep -qi "CONCURRENTLY" "$PROJECT/$SCRIPT"; then
      echo "      (CONCURRENTLY в файле — без общей транзакции, накат оборвётся на первой ошибке)"
      psql_ -v ON_ERROR_STOP=1 < "$PROJECT/$SCRIPT"
    else
      psql_ -v ON_ERROR_STOP=1 --single-transaction < "$PROJECT/$SCRIPT"
    fi

    echo "[3/3] Recording in schema_migrations..."
    # Учёт может отсутствовать: свежий стенд, вторая база до своего файла учёта,
    # восстановление из дампа старше 11.09.2026. Раньше INSERT в несуществующую таблицу
    # ронял скрипт ПОСЛЕ применения SQL — миграция накачена, в учёте её нет, действие
    # завершилось ошибкой. Теперь говорим об этом словами и не притворяемся провалом.
    if ! psql_ -tAc "SELECT to_regclass('public.schema_migrations')" 2>/dev/null | grep -q .; then
      echo "ВНИМАНИЕ: таблицы schema_migrations в базе $DB_N нет — миграция ПРИМЕНЕНА,"
      echo "         но в учёт не записана. Накатите migrations/.../2026-09-11_schema_migrations.sql"
      echo "         и запишите эту строку вручную (см. docs/runbooks/migrations.md)."
      exit 0
    fi
    psql_ -v ON_ERROR_STOP=1 -qc \
      "INSERT INTO schema_migrations (filename, applied_at, applied_by, checksum, note)
               VALUES ('$NAME_SQL', now(), '$WHO', '$SUM', 'deploy.sh migrate')
               ON CONFLICT (filename) DO UPDATE
                 SET applied_at = now(), applied_by = EXCLUDED.applied_by,
                     checksum = EXCLUDED.checksum, note = EXCLUDED.note;" >/dev/null
    echo "Migration applied and recorded."
    ;;

  migrate-status)
    # Сверка каталога с учётом. Нужна потому, что ledger можно обойти: `psql < файл`
    # руками мимо скрипта записи не оставит. Обойти — можно, а СКРЫТЬ обход нельзя:
    # файл без строки виден здесь сразу.
    for PAIR in "backend/migrations:finance_db:finance_user:finance" \
                "backend/migrations/dsp:finance_dsp_db:dsp:dsp_analytics"; do
      DIR=${PAIR%%:*}; REST=${PAIR#*:}
      DB_C=${REST%%:*}; REST=${REST#*:}
      DB_U=${REST%%:*}; DB_N=${REST#*:}
      echo ""
      echo "── $DB_N ($DIR) ──────────────────────────────"

      # Сперва спрашиваем базу ОДИН раз и отдельно — чтобы отличить «строки в учёте нет»
      # от «база недоступна». Раньше и то и другое давало пустой ответ, и при лежащей
      # базе экран печатал «НЕ НАКАЧЕНО» про все 89 файлов — приглашение накатить всё
      # заново поверх живых данных (найдено 11.09.2026).
      LEDGER=$(docker exec -i "$DB_C" psql -U "$DB_U" -d "$DB_N" -tAc \
                 "SELECT filename||E'\t'||coalesce(checksum,'—') FROM schema_migrations" 2>/dev/null) || {
        echo "  БАЗА НЕДОСТУПНА — состояние учёта неизвестно, НЕ накатывайте по этому выводу"
        continue
      }

      # `find`, а не `ls`: разбор вывода `ls` разваливается на пути с пробелом, а проект
      # уже жил в каталоге «Finance CRM».
      BF=0; OKN=0; MISS=0; CHG=0
      while IFS= read -r F; do
        [ -n "$F" ] || continue
        N=$(basename "$F"); S=$(sha256sum "$F" | cut -d' ' -f1)
        ROW=$(printf '%s\n' "$LEDGER" | awk -F'\t' -v n="$N" '$1==n {print $2; exit}')
        if [ -z "$ROW" ];      then echo "  НЕ НАКАЧЕНО   $N"; MISS=$((MISS+1))
        # «НЕ ПРОВЕРЕНО», а не «накачено»: у строк из бэкфилла нет контрольной суммы,
        # потому что факт их наката никто не подтверждал — список писался по каталогу
        # файлов. Репетиция 11.09.2026 нашла две такие строки, которые на проде
        # накатаны НЕ были. Слово «накачено» тут означало бы уверенность, которой нет.
        elif [ "$ROW" = "—" ]; then echo "  из бэкфилла   $N"; BF=$((BF+1))
        elif [ "$ROW" != "$S" ]; then echo "  ИЗМЕНЁН ПОСЛЕ $N  (сумма не совпадает)"; CHG=$((CHG+1))
        else                        echo "  накачено      $N"; OKN=$((OKN+1))
        fi
      done <<EOF
$(find "$PROJECT/$DIR" -maxdepth 1 -name '*.sql' | sort)
EOF

      # Итог разделом. «Из бэкфилла» — НЕ то же, что «накачено»: у этих строк нет
      # контрольной суммы, потому что факт наката никто не подтверждал — список писался
      # по каталогу файлов с машины разработчика. Репетиция на копии прода 11.09.2026
      # нашла среди них две, которых на боевой базе не было. Поэтому число вынесено
      # отдельной строкой: это мера того, сколько мы про эту базу НЕ знаем.
      echo "  ─ накачено $OKN · из бэкфилла $BF (факт не подтверждён) · не накачено $MISS · изменено $CHG"

      # Обратная сторона: строка есть, файла нет — переименовали или удалили.
      #
      # Хвост конвейера раньше кончался `&&`-выражением, которое на нормальном файле
      # возвращает 1; под `set -e` это роняло ВЕСЬ цикл, и второй каталог (dsp) не
      # печатался ни разу — прибор наполовину не работал с рождения. Замерено 11.09.2026:
      # EXIT = 1, раздела dsp_analytics в выводе нет.
      printf '%s\n' "$LEDGER" | cut -f1 | while IFS= read -r N; do
        if [ -n "$N" ] && [ ! -f "$PROJECT/$DIR/$N" ]; then
          echo "  ФАЙЛА НЕТ     $N  (есть в учёте)"
        fi
      done
    done
    echo ""
    ;;

  backup)
    # Аргумент — какую базу дампить. Без него `finance`, как было: cron и меню зовут
    # действие без аргумента, и их поведение не меняется.
    WHICH=${2:-finance}
    case "$WHICH" in
      finance)       BK_C=finance_db;     BK_U=finance_user; BK_N=finance ;;
      dsp_analytics) BK_C=finance_dsp_db; BK_U=dsp;          BK_N=dsp_analytics ;;
      *) echo "ERROR: unknown database '$WHICH' (finance | dsp_analytics)"; exit 1 ;;
    esac
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    # Каталог — ТОТ ЖЕ, что смонтирован бэкенду на чтение (docker-compose.yml, backend
    # volumes). Одна переменная на оба места: пока их было два, экран состояния мог
    # показывать свежесть одного каталога, а cron писать в другой.
    BACKUPS_DIR="${BACKUPS_DIR:-$PROJECT/backups}"
    LOG="$BACKUPS_DIR/backup_log.txt"
    mkdir -p "$BACKUPS_DIR"
    # Имя несёт базу: дампы двух баз лежат рядом, а ротация ниже режет по маске. Пока
    # маска была общей, четырнадцать слотов делились бы между базами и глубина хранения
    # главной базы молча падала бы вдвое.
    if [ "$BK_N" = "finance" ]; then
      DEST="$BACKUPS_DIR/backup_$TIMESTAMP.sql"
      # `backup_*.sql` поймала бы и дампы второй базы, поэтому их отсекаем явно.
      ROTATE_LIST() { ls -t "$BACKUPS_DIR"/backup_*.sql 2>/dev/null | grep -v '/backup_dsp_analytics_'; }
    else
      DEST="$BACKUPS_DIR/backup_${BK_N}_$TIMESTAMP.sql"
      ROTATE_LIST() { ls -t "$BACKUPS_DIR"/backup_"${BK_N}"_*.sql 2>/dev/null; }
    fi
    # Без -t: TTY добавляет CR в каждую строку дампа. Восстановление такого файла
    # проверено дважды (30 и 31.08.2026) и проходит чисто, данные не портятся — но
    # смысла в TTY здесь нет, а файл на 43 тысячи байт больше.
    #
    # `|| true` и явная проверка ниже — вместо опоры на `set -e`. Редирект `>` создаёт
    # файл ДО запуска pg_dump, поэтому при сбое на диске остаётся НУЛЕВОЙ файл. Он
    # выглядит бэкапом, занимает слот ротации и вытесняет настоящий — глубина хранения
    # тает по суткам за каждый сбой, и замечают это только в аварию (F3-02 аудита).
    RC=0
    docker exec -i "$BK_C" pg_dump -U "$BK_U" "$BK_N" > "$DEST" || RC=$?
    # Годность проверяется ТРЕМЯ признаками, и каждый ловит свой вид обмана:
    #   · код возврата pg_dump — раньше выбрасывался через `|| true`;
    #   · начало файла — ловит «сообщение об ошибке вместо данных»;
    #   · ХВОСТ `-- PostgreSQL database dump complete` — ловит обрыв на середине.
    # Третьего не было, и замер 11.09.2026 показал: обрубок в 50 КБ проходил проверку,
    # писался в лог как «ок» и занимал слот ротации, вытесняя годный дамп. Это ровно
    # та беда (F3-02), от которой всё и строилось.
    BAD=""
    [ "$RC" -ne 0 ] && BAD="pg_dump вернул код $RC"
    [ -z "$BAD" ] && [ ! -s "$DEST" ] && BAD="файл пуст"
    [ -z "$BAD" ] && ! head -c 200 "$DEST" | grep -q "PostgreSQL database dump" \
        && BAD="начало не похоже на дамп"
    [ -z "$BAD" ] && ! tail -c 200 "$DEST" | grep -q "PostgreSQL database dump complete" \
        && BAD="нет строки завершения — дамп оборван"
    if [ -n "$BAD" ]; then
      SIZE=$( [ -f "$DEST" ] && wc -c < "$DEST" || echo 0 )
      rm -f "$DEST"
      echo "$(date '+%F %T')  ПРОВАЛ [$BK_N]: $BAD ($SIZE байт), файл удалён" >> "$LOG"
      echo "Backup FAILED [$BK_N]: $BAD ($SIZE bytes). See $LOG"
      exit 1
    fi
    # Ротация ТОЛЬКО после успешной проверки: иначе негодный файл вытеснил бы годный.
    # `-0`, потому что `xargs` без него рвёт путь с пробелом и `rm` промахивается молча.
    ROTATE_LIST | tail -n +15 | tr '\n' '\0' | xargs -0 rm -f 2>/dev/null || true
    echo "$(date '+%F %T')  ок [$BK_N]: $(basename "$DEST"), $(wc -c < "$DEST") байт" >> "$LOG"
    echo "Backup created: $DEST"
    ls -lh "$DEST"
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
    # Тот же каталог, что у `backup`: пока здесь стоял жёсткий `$PROJECT/backups`,
    # «одна переменная на оба места» из комментария выше была неправдой.
    BACKUPS_DIR="${BACKUPS_DIR:-$PROJECT/backups}"
    mkdir -p "$BACKUPS_DIR"
    LOG="$BACKUPS_DIR/retention_log.txt"
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
    echo "Usage: deploy.sh {pull|backend|frontend|cabinet-backend|cabinet-frontend|full|migrate <script>|migrate-status|backup [db]|retention [apply]|status|logs [service]}"
    echo ""
    echo "  pull              - git pull only"
    echo "  backend           - git pull + copy backend files + restart backend"
    echo "  frontend          - git pull + copy frontend files + rebuild + restart"
    echo "  cabinet-backend   - git pull + copy cabinet backend + restart"
    echo "  cabinet-frontend  - git pull + copy cabinet frontend + rebuild + restart"
    echo "  full              - git pull + full docker compose rebuild (~10 min)"
    echo "  migrate <script>  - backup, apply SQL script (all-or-nothing), record in ledger"
    echo "  migrate-status    - compare migration files on disk against the ledger"
    echo "  backup [db]       - pg_dump to BACKUPS_DIR, keep last 14 (db: finance | dsp_analytics)"
    echo "  retention [apply] - delete stored files past their retention (dry run without apply)"
    echo "  status            - show container status"
    echo "  logs [service]    - follow logs (service: backend/frontend/db/caddy)"
    ;;
esac
