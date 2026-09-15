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

# ══════════════ Пересборка Next-витрины: собрать РЯДОМ, подменить готовым ══════════════
#
# Порядок «снести .next → собирать новую» стоил простоя 15.09.2026: сборка основной
# витрины была убита по памяти (SIGKILL) уже ПОСЛЕ удаления рабочей сборки, и прод отдавал
# 500, пока сборку не вернули из образа руками. Причина падения — `mem_limit: 512m` у
# сервисного контейнера: `next build` укладывается в него впритык и однажды не уложился.
# Памяти на ХОСТЕ при этом было свободно 6,7 ГБ из 7,9 — то есть дело было не в машине.
#
# Та же беда годом раньше воспроизводилась на локальном стенде и была описана в навыке
# `deploying-locally`; сюда её не перенесли, и она дождалась прода.
#
# Отсюда три свойства:
#   · сборка идёт во ВРЕМЕННОМ контейнере из того же образа — у него лимита памяти нет;
#   · рабочий контейнер не трогается, пока новая сборка не готова. Упавшая сборка теперь
#     означает «ничего не изменилось», а не простой;
#   · исходники в рабочий контейнер тоже едут ПОСЛЕ успеха: иначе там оказался бы новый
#     код со старой сборкой, и следующий, кто заглянет, будет сверять несводимое.

# Что составляет витрину. ОДИН список на временный и на рабочий контейнер: разойдясь,
# они дадут сборку не из того кода, что лежит в контейнере.
#   · `scripts/` обязателен — `prebuild` зовёт гейты (check-nav, check-money, check-tone
#     и другие) именно оттуда. Без него приезжает новый `package.json`, а гейт нет, и
#     сборка падает на «Cannot find module»;
#   · `next.config.js` и `package.json` — из них берётся версия, вшиваемая в меню профиля;
#     без них там останется версия последней полной пересборки образа;
#   · каталога `helpers/` здесь был до 31.08.2026, и он ронял всё действие: каталог убрали
#     из репозитория, а `set -e` на несуществующем источнике обрывал скрипт. Теперь
#     отсутствие любого пункта — явная ошибка с именем файла, а не обрыв на полуслове.
NEXT_SRC="pages components styles public lib scripts next.config.js package.json"

copy_next_src() {
  SRC=$1; DST=$2
  for p in $NEXT_SRC; do
    [ -e "$SRC/$p" ] || { echo "ERROR: нет $SRC/$p — список NEXT_SRC разошёлся с репозиторием"; exit 1; }
    docker cp "$SRC/$p" "$DST:/app/"
  done
}

rebuild_next() {
  C=$1; SRC=$2; NAME=$3
  IMG=$(docker inspect "$C" --format '{{.Config.Image}}')
  TMPC="${C}_build"
  # Каталог под готовую сборку — на ДИСКЕ, а не в /tmp: во многих установках /tmp это
  # tmpfs, то есть оперативная память, а .next весит сотни мегабайт. Класть её в память
  # на машине, которая только что уронила сборку по памяти, — то же самое ещё раз.
  TMPD=$(mktemp -d "${TMPDIR:-/var/tmp}/deploy_next.XXXXXX")
  # Уборка в ЛЮБОМ исходе, включая падение сборки по `set -e`: временный контейнер держит
  # слой образа, а каталог — целую .next. Оба идемпотентны, поэтому ловушка на EXIT
  # безопасна и тогда, когда всё прошло хорошо.
  trap 'docker rm -f "$TMPC" >/dev/null 2>&1 || true; rm -rf "$TMPD"' EXIT

  echo "  [1/4] временный контейнер из образа $IMG (лимита памяти у него нет)..."
  docker rm -f "$TMPC" >/dev/null 2>&1 || true
  docker run -d --name "$TMPC" --entrypoint sh "$IMG" -c "sleep 3600" >/dev/null
  copy_next_src "$SRC" "$TMPC"

  echo "  [2/4] сборка (3-5 мин)..."
  # Читать вывод целиком: `Attempted import error` НЕ роняет next build, и
  # «Compiled successfully» рядом с ним означает «соберётся и упадёт в браузере».
  docker exec "$TMPC" sh -c "cd /app && rm -rf .next && npm run build"

  # Сюда доходим только при удачной сборке: иначе `set -e` оборвал бы скрипт выше,
  # не тронув рабочий контейнер.
  # Готовую сборку достаём НА ХОСТ до того, как трогать рабочий контейнер. Порядок
  # найден прогоном 15.09.2026: при выемке после сноса любая осечка здесь (нет места,
  # недоступен путь) оставляет контейнер вовсе без сборки — то есть ровно тот простой,
  # ради которого всё и переписано, только в узком окне.
  echo "  [3/4] выемка готовой сборки на хост..."
  docker cp "$TMPC:/app/.next" "$TMPD/.next"

  echo "  [4/4] исходники и подмена сборки..."
  copy_next_src "$SRC" "$C"
  # Рабочую .next сносим ДО остановки: `docker exec` в остановленный контейнер не заходит
  # и молча ничего не делает. А сносить обязательно — `docker cp` в существующий каталог
  # не заменяет его, а СЛИВАЕТСЯ с ним, и в .next остаются слои двух сборок.
  docker exec "$C" rm -rf /app/.next
  docker stop "$C" >/dev/null
  docker cp "$TMPD/.next" "$C:/app/"
  docker start "$C" >/dev/null
  sleep 3
  echo "  $NAME готова, сборка $(docker exec "$C" cat /app/.next/BUILD_ID)"
}

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
    # scripts/ ОБЯЗАТЕЛЕН, и его здесь не было до 15.09.2026. Каждый релиз приносит
    # разовые скрипты — сиды разметки, разбор накопленного, уборку журналов, — а в
    # контейнер они не попадали вовсе: копировался только `app`. Команда из руководства
    # по выкладке отвечала «No module named scripts.<имя>», и это выяснялось ровно в тот
    # момент, когда скрипт понадобился. Найдено при постановке journals_sweep в крон.
    #
    # `migrations/` сюда НЕ нужен: `deploy.sh migrate` читает файл с хоста и подаёт его
    # psql на stdin. `tests/` тоже нет — на проде набор не гоняется.
    docker cp $PROJECT/backend/scripts finance_backend:/app/
    docker restart finance_backend
    echo "Backend deployed."
    ;;

  frontend)
    echo "[1/2] Git pull..."
    git pull
    echo "[2/2] Пересборка витрины..."
    rebuild_next finance_frontend "$PROJECT/frontend" "Основная витрина"
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
    echo "[1/2] Git pull..."
    git pull
    echo "[2/2] Пересборка витрины кабинета..."
    # Тот же код, что у основной витрины: у кабинета была ровно та же дыра — рабочая
    # сборка сносилась до начала новой.
    rebuild_next cabinet_frontend "$PROJECT/cabinet-frontend" "Витрина кабинета"
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
    # ДВА ПОМОЩНИКА, и разница между ними — не стиль.
    #
    # `docker exec -i` ПОДКЛЮЧАЕТ stdin контейнеру, и внутри `$( )` он выпивает stdin
    # всего скрипта. Дальше `read -r ANS` упирается в конец ввода, получает пустую
    # строку и уходит в ветку «Отменено» — сколько бы человек ни печатал `y`. Символ он
    # видит (его отображает терминал), а скрипт уже нет.
    #
    # Поймано на боевой выкладке 12.09.2026: подтверждение повторного наката ответить
    # было НЕВОЗМОЖНО. Поэтому `-i` остаётся только там, где на stdin реально едет файл.
    psql_()  { docker exec -i "$DB_C" psql -U "$DB_U" -d "$DB_N" "$@"; }
    psql_q() { docker exec "$DB_C" psql -U "$DB_U" -d "$DB_N" "$@" </dev/null; }

    # ── учёт: предупреждаем, НЕ блокируем ───────────────────────────────────
    # Все миграции проекта повторно накатываемые, и законный повтор бывает — например
    # после восстановления из старого дампа. Запрет мешал бы ему; молчание же прячет
    # случай «накатываю второй раз, не заметив». Поэтому вопрос, а не отказ.
    PREV=$(psql_q -tAc "SELECT coalesce(to_char(applied_at,'YYYY-MM-DD HH24:MI'),'время неизвестно')
                         ||' · '|| coalesce(note,'')
                       FROM schema_migrations WHERE filename='$NAME_SQL'" 2>/dev/null || true)
    if [ -n "$PREV" ]; then
      echo "ВНИМАНИЕ: $NAME уже накатывали ($PREV)."
      OLDSUM=$(psql_q -tAc "SELECT coalesce(checksum,'') FROM schema_migrations WHERE filename='$NAME_SQL'" 2>/dev/null || true)
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
    if ! psql_q -tAc "SELECT to_regclass('public.schema_migrations')" 2>/dev/null | grep -q .; then
      echo "ВНИМАНИЕ: таблицы schema_migrations в базе $DB_N нет — миграция ПРИМЕНЕНА,"
      echo "         но в учёт не записана. Накатите migrations/.../2026-09-11_schema_migrations.sql"
      echo "         и запишите эту строку вручную (см. docs/runbooks/migrations.md)."
      exit 0
    fi
    psql_q -v ON_ERROR_STOP=1 -qc \
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
      LEDGER=$(docker exec "$DB_C" psql -U "$DB_U" -d "$DB_N" -tAc \
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
