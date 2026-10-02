# -*- coding: utf-8 -*-
"""Убрать адрес загрузки DSP из старых строк журнала обмена (аудит 01.10.2026, К-2/К-3).

До правки в `dsp_send_log` писались: ответ `Upload.getUploadFileUrl` (сам адрес с одноразовым
токеном) и запрос `Upload.file` (тот же адрес). Адрес несёт имя поставщика и токен, а журнал
виден во вкладке «Логи» и скачивается. Новые строки пишутся уже без него; этот скрипт
чистит прошлые. Больше ничего в строках не меняется.

По умолчанию — пробный прогон (только счёт). Запись — `--apply`. Повтор безопасен.

    docker exec finance_backend python -m scripts.2026-10-01_dsp_log_scrub_upload [--apply]
"""
import sys

from sqlalchemy import text

from app.dsp.db import dsp_engine

MASK = "<адрес загрузки DSP>"


def main():
    apply = "--apply" in sys.argv
    with dsp_engine().begin() as c:
        n_resp = c.execute(text(
            "SELECT count(*) FROM dsp_send_log WHERE method = 'Upload.getUploadFileUrl' "
            "AND response->>'result' LIKE 'http%'")).scalar()
        n_req = c.execute(text(
            "SELECT count(*) FROM dsp_send_log WHERE method = 'Upload.file' "
            "AND request->>'url' LIKE 'http%'")).scalar()
        n_err = c.execute(text(
            "SELECT count(*) FROM dsp_send_log WHERE error ~ 'https?://'")).scalar()
        print({"ответов getUploadFileUrl с адресом": n_resp, "запросов Upload.file с адресом": n_req,
               "ошибок с адресом": n_err})
        if not apply:
            print("пробный прогон — ничего не изменено; для записи --apply")
            return
        c.execute(text(
            "UPDATE dsp_send_log SET response = jsonb_set(response, '{result}', to_jsonb(CAST(:m AS text))) "
            "WHERE method = 'Upload.getUploadFileUrl' AND response->>'result' LIKE 'http%'"), {"m": MASK})
        c.execute(text(
            "UPDATE dsp_send_log SET request = jsonb_set(request, '{url}', to_jsonb(CAST(:m AS text))) "
            "WHERE method = 'Upload.file' AND request->>'url' LIKE 'http%'"), {"m": MASK})
        # Старые ошибки писались `repr` исключения httpx — с полным адресом.
        c.execute(text(
            "UPDATE dsp_send_log SET error = regexp_replace(error, :rx, '<адрес DSP>', 'g') "
            "WHERE error ~ 'https?://'"), {"rx": r"https?://[^\s'\"<>]+"})
        print("ЗАПИСАНО")


if __name__ == "__main__":
    main()
