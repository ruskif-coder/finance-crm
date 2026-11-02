# -*- coding: utf-8 -*-
"""Ревью 02.11.2026 перед релизом «подпись у каждого документа».

1. Скан в пакете из архива заменялся: проверка смотрела только на документ (бумага, выставлен/подписан), а удаление
   скана в архиве уже запрещено. Поломка: подписанный скан закрытого пакета перезаписывается — оригинал теряется.
2. «Подтвердить номер» на странице ДС двигает пакет в «ждём 1С», но уведомление ставилось ПОСЛЕ последнего коммита
   (`log_action` коммитит) и откатывалось с концом запроса. Поломка: пакет ушёл к бухгалтерии, а ей никто не сказал."""
import inspect
from types import SimpleNamespace

import pytest

from app.master_deal import files as MF
from app.master_deal.service import MasterError


def test_no_scan_into_an_archived_pack():
    m = SimpleNamespace(id=1, status="архив")
    with pytest.raises(MasterError) as e:
        MF.save_scan(None, m, None, filename="a.pdf", content=b"%PDF", annex_id=1, upd_no=None)
    assert e.value.status == 409 and "архив" in e.value.message


def test_pack_notification_is_queued_before_the_last_commit():
    from app.routers import annexes as AX
    src = inspect.getsource(AX.confirm_annex)
    assert src.index("CN.status_changed(") < src.index("log_action("), "уведомление — до коммита журнала"
