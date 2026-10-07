# -*- coding: utf-8 -*-
"""Нацеливание для страницы «Проверка креатива» (07.10.2026): без сделки, демо-ЕРИД и демо-контур.

Механика ТА ЖЕ, что у первичной проверки трафиков (`targeting_creative`): копия баннера в кабинете
демоклиента с заглушкой `TEST_ERID`, без пикселя верификатора, креатив запускается и кампания
нацеливания просыпается на двое суток. Общие части — `_copy_core` и `_make_live` из того модуля:
второе выражение той же логики разошлось бы с первым на первой же правке.

Отличия: у проверки нет сделки, комплекта и пар, поэтому ссылка перехода — домен, введённый
человеком, а замок и `local_ref` живут в своём пространстве номеров (проверка №5 не должна
считаться комплектом №5).

УДАЛИТЬ креатив в DSP нечем — только остановить (так же устроено у комплектов). Поэтому строка
проверки исчезает только после подтверждённой остановки (`stop`).
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.dsp import targeting_creative as tc
from app.dsp.client import MsClient, MsError
from app.ext_lock import DSP_TARGETING_COPY, only_one
from app.files_safe import inside_uploads

log = logging.getLogger("finance.dsp")

# Номера проверок в замке сдвинуты: иначе проверка №5 и комплект №5 делили бы один замок.
LOCK_OFFSET = 1_000_000_000


class CheckTargetingError(tc.TargetingCreativeError):
    """Нацеливание проверки завести нельзя, причина называется человеку."""


def ref_of(chk) -> str:
    return f"chk{chk.id}"


def title_of(chk) -> str:
    return f"{tc.TITLE_PREFIX}проверка {chk.id} · {chk.title}"[:200]


def _read(chk) -> tuple:
    path = inside_uploads(chk.file_path, root=tc.UPLOADS_ROOT)
    if path is None:
        raise CheckTargetingError(f"некорректный путь файла проверки: {chk.file_path}")
    try:
        with open(path, "rb") as fh:
            return fh.read(), (chk.original_name or "creative.zip")
    except OSError:
        raise CheckTargetingError("файл проверки не найден в хранилище — загрузите креатив заново")


def ensure_live(db: Session, chk, *, client: Optional[MsClient] = None) -> dict:
    """Креатив нацеливания проверки заведён, ЗАПУЩЕН и кампания его крутит (как `ensure_live`)."""
    from app.dsp.config import targeting_cabinet, viewability_src

    partner, campaign = targeting_cabinet(db)
    if not partner or not campaign:
        raise CheckTargetingError(
            "Не задан кабинет или кампания нацеливания: Трафики → Каталог → Скрипты сайта")
    c = client or tc._client(partner)
    woke = tc.wake_campaign(db, client=c)
    ref = ref_of(chk)
    with only_one(DSP_TARGETING_COPY, LOCK_OFFSET + chk.id, CheckTargetingError,
                  "Заведение копии нацеливания", where="по этой проверке"):
        known = chk.dsp_xxhash or c.last_ok_xxhash("Creative.add", "creative", ref)
        xxhash = tc._copy_core(c, campaign, ref=ref, known=known, title=title_of(chk),
                               link=chk.advertiser_url or tc.FALLBACK_LINK, erid=tc.TEST_ERID,
                               get_zip=lambda: _read(chk),
                               viewability_src=viewability_src(db))
        # Хеш — СРАЗУ: объект в чужой системе уже есть, потерять его нельзя.
        chk.dsp_xxhash = xxhash
        chk.dsp_state = "live"
        db.commit()
    live = tc._make_live(c, campaign, xxhash, ref, woke=woke)
    return live


def stop(db: Session, chk, *, client: Optional[MsClient] = None) -> bool:
    """Остановить креатив нацеливания проверки. True — остановлен (или заводить не успели).

    Сбой DSP — исключение: строку проверки удаляют ТОЛЬКО после остановки, иначе креатив
    остался бы крутиться без хозяина."""
    if not chk.dsp_xxhash or chk.dsp_state == "stopped":
        return True
    from app.dsp.config import targeting_cabinet
    partner, _campaign = targeting_cabinet(db)
    c = client or tc._client(partner or "")
    try:
        c.creative_set_status(chk.dsp_xxhash, tc.STOPPED, local_ref=ref_of(chk))
    except (MsError, ValueError) as e:
        raise CheckTargetingError(f"креатив нацеливания не остановлен: {e}")
    chk.dsp_state = "stopped"
    db.commit()
    return True
