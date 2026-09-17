"""Вход для СЕРВИСА кабинета: всё, что внешний контур меняет у нас.

Фраза «два действия, и больше здесь ничего не появится» стояла здесь с 28.08.2026 и к
15.09 перестала быть правдой — ручек стало восемь. Правило, ради которого она писалась,
живо: кабинет НЕ ПИШЕТ В БАЗУ, у таблицы один писатель. Растёт этот файл, а не права
роли `cabinet`.

Кабинет не пишет в базу — он зовёт ядро. Разбор решения целиком в шапке миграции
`2026-08-28_publisher_cabinet_verdict.sql`; коротко: правила вердикта нетривиальны, и
вторая их реализация на стороне кабинета разошлась бы с первой.

**Это не пользовательский эндпоинт.** Права роли здесь не при чём: снаружи стоит не
человек, а наш же процесс во внешнем контуре. Пропуск — общий секрет из окружения, и он
свой, отдельный и от `SECRET_KEY` ядра, и от `CABINET_SECRET_KEY`: тот подписывает
сессии паблишеров, этот пускает процесс к процессу.

Чего секрет НЕ даёт: он не удостоверяет, кто именно нажал кнопку. Имя и почта автора
приходят в теле, и ядро кладёт их СНИМКОМ. Доверие здесь ровно то же, что у любого
сервисного вызова: скомпрометированный кабинет может записать вердикт от чужого имени —
но он и так стоит между площадкой и нами. Важно, что читать финансовые данные он при
этом не может: роль `cabinet` в базе прав на `public` не имеет.
"""
import hmac
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Header, HTTPException,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.files_safe import existing_upload_path
from app.database import get_db
from app.launch_prep.models import LaunchPrepPair, LaunchPrepPairFile, LaunchPrepTarget
from app.routers.launch_prep import apply_platform_verdict, url_state
from app.cabinet import journal
from app.sales.models import SalesPublisher

router = APIRouter()

# ВЕБХУК ЖИВЁТ НА ОТДЕЛЬНОМ РОУТЕРЕ, и это не стилистика.
#
# Caddy отдаёт 404 на весь `/api/cabinet-gw/*` намеренно: шлюз — разговор двух наших
# процессов внутри docker-сети, и наружу ему смотреть незачем. А вебхуку смотреть наружу
# ОБЯЗАТЕЛЬНО — стучится Телеграм из интернета. Оставь я его под общим префиксом,
# привязка молча не работала бы на проде: локально всё зелено, апдейты уходят в 404, и
# выглядит это как «код не приходит», то есть как проблема на стороне человека.
#
# Дырявить правило Caddy исключением — хуже: правило перестаёт читаться как правило.
webhook_router = APIRouter()

SERVICE_TOKEN = os.getenv("CABINET_SERVICE_TOKEN", "")
log_gw = logging.getLogger("finance.cabinet.gateway")


def require_cabinet_service(x_cabinet_token: Optional[str] = Header(default=None)):
    """Пропуск сервиса кабинета. Сравнение постоянным временем — секрет длинный, но
    побитовое сравнение всё равно рассказывает о нём по времени ответа.

    Пустой секрет в окружении закрывает вход НАСОВСЕМ, а не открывает всем: забытая
    переменная должна ломать функцию, а не защиту.
    """
    if not SERVICE_TOKEN or not x_cabinet_token or not hmac.compare_digest(
            x_cabinet_token, SERVICE_TOKEN):
        raise HTTPException(status_code=403, detail="Сервисный доступ закрыт")
    return True


def _actor(db: Session, account_id: int, publisher_id: int):
    """Кто действует и в чьей ленте это окажется.

    До 30.08.2026 шлюз не знал действующего вовсе: у вердикта проверялось только, что
    пара принадлежит НАЗВАННОЙ площадке, а имеет ли право вызывающий говорить за неё —
    оставалось на кабинете. Ровно то, что в шапке соседней ручки названо «отсутствием
    проверки». Журналу всё равно понадобилась учётка, и вместе с ней проверка стала
    возможной — поэтому поле обязательное, а не «по возможности».
    """
    from app.cabinet.models import CabinetAccount
    from app.cabinet.scope import account_sees_publisher

    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if acc is None or not account_sees_publisher(db, acc, publisher_id):
        # 404 везде: 403 отвечал бы на вопрос «а есть ли такая связка».
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return acc


def _creative_subject(db: Session, pair) -> Optional[str]:
    """«№4 · Мильгамма» — то, что видно в ленте рядом с действием.

    Бренд, а не название сделки: сделка — наша внутренняя единица, а лента у площадки
    на виду. Правило «в subject не попадает лишнее» начинается здесь.
    """
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.sales.models import SalesBrand, SalesDeal

    s = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.id == pair.set_id).first()
    if s is None:
        return None
    brand = None
    deal = db.query(SalesDeal).filter(SalesDeal.id == s.deal_id).first()
    if deal is not None and deal.brand_id:
        brand = db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
    return f"№{s.no}" + (f" · {brand.name}" if brand and brand.name else "")


class CabinetVerdictIn(BaseModel):
    publisher_id: int          # чью площадку представляет вызывающий
    account_id: int            # кто именно — им же подписана строка журнала
    verdict: str
    reason: Optional[str] = None
    author_name: str
    author_email: Optional[str] = None


@router.post("/pair/{pair_id}/verdict", dependencies=[Depends(require_cabinet_service)])
def cabinet_verdict(pair_id: int, payload: CabinetVerdictIn,
                    db: Session = Depends(get_db)):
    """Вердикт, поставленный САМОЙ площадкой в кабинете.

    Пара сверяется с заявленной площадкой ЗДЕСЬ, а не только в кабинете: проверка,
    оставленная на вызывающей стороне, — это отсутствие проверки.
    """
    pair = db.query(LaunchPrepPair).filter(LaunchPrepPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    target = db.query(LaunchPrepTarget).filter(
        LaunchPrepTarget.id == pair.target_id).first()
    if not target or target.publisher_id != payload.publisher_id:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    acc = _actor(db, payload.account_id, payload.publisher_id)
    out = apply_platform_verdict(db, pair_id, payload.verdict, payload.reason,
                                 payload.author_name, payload.author_email,
                                 "кабинет", actor=None)
    journal.write(db, {'ок': 'креатив_ок', 'на доработку': 'креатив_доработка',
                       'отказ': 'креатив_отказ'}[payload.verdict],
                  cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=payload.publisher_id, actor_name=payload.author_name,
                  subject=_creative_subject(db, pair),
                  entity_type='launch_prep_pair', entity_id=pair_id)
    db.commit()
    return {"verdict": out["verdict"], "code": out["code"]}


class CabinetUrlIn(BaseModel):
    publisher_id: int
    account_id: int
    url: str
    author_name: str


@router.put("/target/{target_id}/url", dependencies=[Depends(require_cabinet_service)])
def cabinet_target_url(target_id: int, payload: CabinetUrlIn,
                       db: Session = Depends(get_db)):
    """Посадочная страница, присланная площадкой в ответ на наш запрос.

    Ссылка живёт на ПОЛУЧАТЕЛЕ (сделка × площадка), а не на креативе: страница одна на
    всю кампанию у этого сайта, и у второго креатива она та же.

    Схема проверяется, как у ссылки на документ договора: `javascript:` и `data:` в
    кликаемом поле — известный вектор, и то, что поле заполняет внешнее лицо, делает
    проверку не формальностью, а условием.
    """
    target = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == target_id).first()
    if not target or target.publisher_id != payload.publisher_id:
        raise HTTPException(status_code=404, detail="Размещение не найдено")

    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Укажите ссылку")
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400,
                            detail="Ссылка должна начинаться с http:// или https://")
    if len(url) > 512:
        raise HTTPException(status_code=400, detail="Ссылка длиннее 512 знаков")

    acc = _actor(db, payload.account_id, payload.publisher_id)
    target.advertiser_url = url
    journal.write(db, 'посадочная', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=payload.publisher_id, actor_name=payload.author_name,
                  entity_type='launch_prep_target', entity_id=target.id)
    db.commit()
    return {"target_id": target.id, "url_state": url_state(target)}


@router.get("/notify-kinds", dependencies=[Depends(require_cabinet_service)])
def cabinet_notify_kinds(db: Session = Depends(get_db)):
    """Каталог видов уведомлений — ОДИН на оба контура.

    Кабинет мог бы держать свой список меток, и это была бы третья копия словаря после
    `url_state` и списка типовых размеров баннера. Здесь копии не нужно: список
    статический, запрашивается редко, и один сетевой вызов дешевле расхождения, которое
    видно только площадке.
    """
    from app.notify.outward.kinds import KINDS
    from app.routers.cabinets import _notify_off

    # Площадке показываем только то, что ДЕЙСТВИТЕЛЬНО может прийти: построенные виды,
    # не выключенные нами. Выключатель у вида без отправителя — обещание, которого мы не
    # держим: человек снимает галочку, ничего не меняется, и доверие к экрану кончается.
    # Наш собственный каталог со всеми шестнадцатью живёт во вкладке «Что мы шлём».
    off = _notify_off(db)
    # `urgent` нужен экрану, чтобы объяснить, почему этот вид придёт письмом сразу даже
    # при выбранном дайджесте: «наше сразу не понижается» (решение владельца 15.09.2026).
    # Без подписи это выглядело бы как неработающая настройка.
    return {"kinds": [{"key": k.key, "label": k.label, "hint": k.hint,
                       "can_mute": k.can_mute, "urgent": k.schedule == "сразу",
                       "tag": k.tag or ""}
                      for k in KINDS if k.built and k.key not in off]}


class CabinetCellIn(BaseModel):
    publisher_id: int              # чью площадку представляет вызывающий
    kind: str
    channel: str                   # 'бот' | 'почта' | 'дайджест'
    enabled: bool
    author_name: Optional[str] = None


class CabinetMailIn(BaseModel):
    publisher_id: int
    enabled: Optional[bool] = None       # получать ли почту вообще
    author_name: Optional[str] = None


def _notify_account(db: Session, account_id: int, publisher_id: int):
    """Та же проверка, что у бота: учётка существует и эту площадку видит.

    Проверка ЗДЕСЬ, а не только в кабинете. 404, а не 403: 403 подтвердил бы, что такая
    связка существует.
    """
    from app.cabinet.models import CabinetAccount
    from app.cabinet.scope import account_sees_publisher

    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if not acc or not account_sees_publisher(db, acc, publisher_id):
        raise HTTPException(status_code=404, detail="Учётка не найдена")
    return acc


def _contact_mail(db: Session, acc) -> dict:
    """Почтовый адрес человека и включена ли ему почта.

    ОТВЕТ БЕРЁТСЯ У КОНТАКТА, а не из своей таблицы: галочка «получает уведомления» в
    карточке контакта — единственный источник этого факта, по ней и уходят письма.
    Завести рядом второе хранилище значило бы показывать на экране одно, а слать по
    другому, и разошлись бы они молча.

    Учётка без контакта (`contact_id IS NULL`) — не ошибка: так заводили до появления
    связи. Почтой такой человек не управляет, и экран должен сказать это прямо.
    """
    if not acc.contact_id:
        return {"address": None, "enabled": False, "why": "учётка не связана с контактом"}
    row = db.execute(text(
        "SELECT email, notify FROM sales_publisher_contacts WHERE id = :c"),
        {"c": acc.contact_id}).first()
    if not row or not (row.email or "").strip():
        return {"address": None, "enabled": False, "why": "в карточке контакта нет почты"}
    return {"address": row.email, "enabled": bool(row.notify), "why": ""}


def _notify_state(db: Session, acc) -> dict:
    """Всё, что рисует экран «Какие события присылать», одним ответом.

    Клетки отдаются УЖЕ РАЗРЕШЁННЫМИ — с подставленным умолчанием, а не голыми
    отклонениями. Иначе экрану пришлось бы знать правило умолчаний (бот включён, из двух
    почтовых включена объявленная каталогом), и это была бы вторая его копия — в
    JavaScript, где её никто не проверит.
    """
    from app.notify.outward import prefs, schedule
    from app.notify.outward.kinds import KINDS

    stored = prefs.matrix(db, acc.id)
    tg = _tg_row(db, acc.id)
    return {
        # Час отдаётся как ФАКТ, а не как выбор: знать, когда придёт дайджест, полезно,
        # а менять его площадка не будет — он настраивается у нас, на экране «Что мы
        # шлём», и берётся оттуда же, а не из константы: иначе кабинет показывал бы 09:00
        # после того, как мы поставили 12:00.
        "mail": {**_contact_mail(db, acc), "digest_hour": schedule.hours(db)[0]},
        "bot": {"linked": bool(tg and tg.verified_at)},
        # Плоским списком, а не вложенным словарём: JSON-ключом кортеж не бывает, а
        # склеенная строка «вид\x1fканал» — ровно та составная величина, которая в этом
        # проекте уже протекала из фильтра в данные.
        "cells": [{"kind": k.key, "channel": ch, "enabled": prefs.cell(stored, k, ch)}
                  for k in KINDS if k.built
                  for ch in prefs.CHANNELS],
    }


@router.get("/account/{account_id}/notify", dependencies=[Depends(require_cabinet_service)])
def cabinet_notify_state(account_id: int, publisher_id: int, db: Session = Depends(get_db)):
    return _notify_state(db, _notify_account(db, account_id, publisher_id))


@router.put("/account/{account_id}/notify", dependencies=[Depends(require_cabinet_service)])
def cabinet_notify_cell(account_id: int, payload: CabinetCellIn,
                        db: Session = Depends(get_db)):
    """Переключить одну клетку матрицы. Пишет ЯДРО — кабинет в базу не пишет.

    Здесь это не формальность: `cabinet_account_notify` ссылается на учётку каскадом, и
    право на запись означало бы право снести чужую строку подбором номера.
    """
    from app.notify.outward import prefs
    from app.notify.outward.kinds import KINDS

    acc = _notify_account(db, account_id, payload.publisher_id)
    kind = next((k for k in KINDS if k.key == payload.kind), None)
    if kind is None:
        raise HTTPException(status_code=400, detail=f"Нет вида «{payload.kind}»")
    if payload.channel not in prefs.CHANNELS:
        # Панель сюда не проходит: у паблишера панели уведомлений нет вовсе, а лента
        # кабинета — журнал действий, а не канал доставки.
        raise HTTPException(status_code=400,
                            detail="Способ: бот, почта или дайджест")
    if not kind.can_mute and not payload.enabled:
        raise HTTPException(status_code=400,
                            detail=f"«{kind.label}» выключить нельзя")
    # «НАШЕ СРАЗУ НЕ ПОНИЖАЕТСЯ»: вид, объявленный нами срочным, в пачку не уводится.
    # Запрет стоит на ЗАПИСИ, а не только на экране: экран — не защита.
    if (payload.channel == prefs.DIGEST and payload.enabled
            and kind.schedule == "сразу"):
        raise HTTPException(
            status_code=400,
            detail=f"«{kind.label}» приходит письмом сразу — в дайджест его не убрать")

    who = (payload.author_name or acc.name)

    def _set(channel: str, value: bool):
        """Записать клетку — или снести строку, если значение совпало с умолчанием.

        Хранятся ОТКЛОНЕНИЯ: строка, повторяющая умолчание, — это мусор, который потом
        не даст отличить «человек так решил» от «мы так решили», и «Вернуть по
        умолчанию» перестанет что-либо значить.
        """
        if value == prefs.default_on(kind, channel):
            db.execute(text("DELETE FROM cabinet_account_notify "
                            " WHERE account_id = :a AND kind = :k AND channel = :c"),
                       {"a": acc.id, "k": payload.kind, "c": channel})
        else:
            db.execute(text("""
                INSERT INTO cabinet_account_notify
                    (account_id, kind, channel, enabled, changed_by)
                VALUES (:a, :k, :c, :v, :w)
                ON CONFLICT (account_id, kind, channel)
                DO UPDATE SET enabled = :v, changed_at = now(), changed_by = :w"""),
                {"a": acc.id, "k": payload.kind, "c": channel, "v": value, "w": who})

    _set(payload.channel, payload.enabled)
    # ДВЕ ПОЧТОВЫЕ КОЛОНКИ ВЗАИМОИСКЛЮЧАЮЩИ: письмо приходит либо сразу, либо в пачке, и
    # «и то и то» означало бы два письма об одном событии. Снимаем парную здесь, а не на
    # экране: экран может быть старой сборкой, а правило одно.
    if payload.enabled and payload.channel in prefs.MAIL_WAYS:
        other = prefs.DIGEST if payload.channel == prefs.MAIL else prefs.MAIL
        _set(other, False)

    journal.write(db, 'уведомление_вкл' if payload.enabled else 'уведомление_выкл',
                  cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=payload.publisher_id, actor_name=who,
                  subject=f"{kind.label} · {payload.channel}")
    db.commit()
    return _notify_state(db, acc)


@router.delete("/account/{account_id}/notify",
               dependencies=[Depends(require_cabinet_service)])
def cabinet_notify_reset(account_id: int, publisher_id: int,
                         author_name: Optional[str] = None,
                         db: Session = Depends(get_db)):
    """«Вернуть по умолчанию» — снести отклонения. Режим почты при этом НЕ трогается:
    кнопка стоит под матрицей и обещает вернуть галочки, а не час рассылки."""
    acc = _notify_account(db, account_id, publisher_id)
    n = db.execute(text("DELETE FROM cabinet_account_notify WHERE account_id = :a"),
                   {"a": acc.id}).rowcount
    if n:
        journal.write(db, 'уведомление_вкл', cabinet_id=acc.cabinet_id, account_id=acc.id,
                      publisher_id=publisher_id, actor_name=(author_name or acc.name),
                      subject=f"возврат к умолчаниям ({n})")
    db.commit()
    return _notify_state(db, acc)


@router.put("/account/{account_id}/mail", dependencies=[Depends(require_cabinet_service)])
def cabinet_mail_settings(account_id: int, payload: CabinetMailIn,
                          db: Session = Depends(get_db)):
    """Почта: получать ли её вообще. Больше здесь ничего не настраивается.

    ЧТО приходит пачкой, а что срочным письмом, решается в матрице у каждого события.
    Час пачки — константа 09:00 по времени площадки, и настройки у него нет вовсе.

    `enabled` правит ГАЛОЧКУ КОНТАКТА, а не своё поле, — см. `_contact_mail`.
    """
    acc = _notify_account(db, account_id, payload.publisher_id)
    who = (payload.author_name or acc.name)

    if payload.enabled is not None:
        if not acc.contact_id:
            raise HTTPException(status_code=400,
                                detail="Учётка не связана с контактом — почтой управляем мы")
        db.execute(text("UPDATE sales_publisher_contacts SET notify = :v WHERE id = :c"),
                   {"v": payload.enabled, "c": acc.contact_id})
        journal.write(db, 'уведомление_вкл' if payload.enabled else 'уведомление_выкл',
                      cabinet_id=acc.cabinet_id, account_id=acc.id,
                      publisher_id=payload.publisher_id, actor_name=who,
                      subject="почта целиком")

    db.commit()
    return _notify_state(db, acc)


# Медиакит — презентация площадки. Только PDF и PPTX (владелец 28.08.2026): это документ
# для чтения, а не архив и не картинка, и открытый список расширений во внешнем контуре
# означал бы приём чего угодно от того, кто нам не сотрудник.
MEDIA_KIT_EXT = {".pdf", ".pptx"}
MEDIA_KIT_MAX = 30 * 1024 * 1024
MEDIA_KIT_DIR = "mediakit"


@router.get("/task/{pair_id}/rights-letter",
            dependencies=[Depends(require_cabinet_service)])
def cabinet_rights_letter(pair_id: int, account_id: int, publisher_id: int,
                          db: Session = Depends(get_db)):
    """Письмо о правах — площадке, по её заданию.

    Отдаёт ЯДРО, а не кабинет: тома `uploads` у контейнера кабинета нет вовсе, он видит
    только `pub.*`. Через песочницу тоже нельзя — она раздаётся БЕЗ авторизации (иначе
    баннер не откроется в рамке), и документ о правах туда класть незачем.

    Право проверяется дважды и по-разному: `_actor` — что учётка вправе говорить за эту
    площадку, а запрос ниже — что задание действительно её. Первое без второго пустило бы
    к чужому креативу по подобранному номеру пары.
    """
    from app.launch_prep.models import LaunchPrepCreativeSet
    _actor(db, account_id, publisher_id)
    row = (db.query(LaunchPrepCreativeSet)
           .join(LaunchPrepPair, LaunchPrepPair.set_id == LaunchPrepCreativeSet.id)
           .join(LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id)
           .filter(LaunchPrepPair.id == pair_id,
                   LaunchPrepTarget.publisher_id == publisher_id).first())
    # 404 и на «нет задания», и на «нет письма»: разные коды отвечали бы на вопрос,
    # существует ли пара с таким номером.
    if row is None or not row.rights_letter_path:
        raise HTTPException(status_code=404, detail="Письмо не найдено")
    # Путь из базы — через общую проверку границы хранилища (`app/files_safe`).
    # До 11.09.2026 она была ровно в одном месте из десяти.
    full = existing_upload_path(row.rights_letter_path)
    return FileResponse(full, filename=row.rights_letter_name or "rights-letter",
                        media_type="application/octet-stream")


@router.post("/publisher/{publisher_id}/media-kit",
             dependencies=[Depends(require_cabinet_service)])
async def cabinet_media_kit(publisher_id: int, account_id: int,
                            file: UploadFile = File(...),
                            db: Session = Depends(get_db)):
    """Медиакит, присланный самой площадкой.

    Колонки под него в реестре были с самого начала, но ручки загрузки не существовало —
    поле стояло пустым у всех 41 площадки (замер 28.08.2026). Теперь его заполняет тот,
    кому оно принадлежит.

    Файл пишет ЯДРО, а не кабинет: том с загрузками смонтирован сюда, и давать внешнему
    процессу право писать в общее хранилище значило бы отдать ему то, ради чего он и
    вынесен отдельно.

    Новый файл ЗАМЕЩАЕТ старый — версий у медиакита нет: у площадки он один, и «версия
    от 03.07» это дата загрузки, а не отдельная запись.
    """
    # ИСПРАВЛЕНО 30.08.2026: раньше принадлежность здесь не проверялась вовсе — «её не
    # из чего вывести, номер площадки и есть весь запрос». Теперь запрос несёт ещё и
    # учётку, и проверка стала возможной. Прежний текст оставлен ниже как история того,
    # почему дыра выглядела неизбежной. У вердикта иначе: там пара сама указывает на
    # площадку, и ядро сверяет независимо. Разница честная, и делать вид, что проверка
    # есть, добавив в тело то же число, было бы хуже её отсутствия.
    p = db.query(SalesPublisher).filter(SalesPublisher.id == publisher_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    acc = _actor(db, account_id, publisher_id)

    original = file.filename or "mediakit"
    ext = os.path.splitext(original)[1].lower()
    if ext not in MEDIA_KIT_EXT:
        raise HTTPException(status_code=415,
                            detail="Медиакит принимается в PDF или PPTX")
    content = await file.read()
    if len(content) > MEDIA_KIT_MAX:
        raise HTTPException(status_code=413,
                            detail=f"Файл больше {MEDIA_KIT_MAX // 1024 // 1024} МБ")

    safe = re.sub(r"[^\w.\-]", "_", original)
    # Имя несёт вид сущности: медиакит площадки №7 и файл комплекта №7 в общем каталоге
    # иначе затрут друг друга — это уже случалось с документами площадок.
    stored = f"pub{publisher_id}_{safe}"
    root = os.path.join("/app/uploads", MEDIA_KIT_DIR)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, stored), "wb") as fh:
        fh.write(content)

    p.media_kit_filename = original
    p.media_kit_path = f"{MEDIA_KIT_DIR}/{stored}"
    p.media_kit_uploaded_at = datetime.utcnow()
    journal.write(db, 'медиакит', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=publisher_id, actor_name=acc.name, subject=original,
                  entity_type='sales_publisher', entity_id=publisher_id)
    db.commit()
    return {"name": original, "uploaded_at": p.media_kit_uploaded_at}


# Картинка к доработке. Форматы те же, что у скриншотов размещения: это тоже снимок
# экрана, просто снятый с другой стороны и с другой целью.
REWORK_EXT = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
REWORK_MAX = 10 * 1024 * 1024
REWORK_MAX_FILES = 5
REWORK_DIR = "rework"


@router.post("/pair/{pair_id}/rework-file",
             dependencies=[Depends(require_cabinet_service)])
async def cabinet_rework_file(pair_id: int, account_id: int,
                              file: UploadFile = File(...),
                              db: Session = Depends(get_db)):
    """Приложение площадки к объяснению, что не так с креативом.

    Кладётся в ту же таблицу, что скриншоты размещения, но ВИДОМ `доработка`. Без вида
    очередь трафика посчитала бы чужие картинки своими доказательствами, а уборка по
    срокам стёрла бы их вместе: у доказательства и у приложенной к правкам картинки
    разная судьба.

    Имя НЕ переименовывается по цепочке, в отличие от скриншотов размещения: те уходят
    клиенту архивом и должны говорить, где стояли, а это — вложение к переписке, и
    исходное имя в нём осмысленно («меню_перекрыто.png»).
    """
    pair = db.query(LaunchPrepPair).filter(LaunchPrepPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    # Площадка здесь не приходит запросом, а берётся у получателя пары: подставить её
    # снаружи означало бы разрешить прикладывать файл к чужому заданию.
    target = db.query(LaunchPrepTarget).filter(
        LaunchPrepTarget.id == pair.target_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    acc = _actor(db, account_id, target.publisher_id)

    n = (db.query(LaunchPrepPairFile)
         .filter(LaunchPrepPairFile.pair_id == pair_id,
                 LaunchPrepPairFile.kind == "доработка").count())
    if n >= REWORK_MAX_FILES:
        raise HTTPException(status_code=400,
                            detail=f"К одной доработке можно приложить {REWORK_MAX_FILES} файлов")

    original = file.filename or "file"
    ext = os.path.splitext(original)[1].lower()
    if ext not in REWORK_EXT:
        raise HTTPException(status_code=415,
                            detail=f"Разрешены: {', '.join(sorted(REWORK_EXT))}")
    content = await file.read()
    if len(content) > REWORK_MAX:
        raise HTTPException(status_code=413,
                            detail=f"Файл больше {REWORK_MAX // 1024 // 1024} МБ")

    safe = re.sub(r"[^\w.\-]", "_", original)
    stored = f"rw{pair_id}_{n + 1}_{safe}"
    root = os.path.join("/app/uploads", REWORK_DIR)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, stored), "wb") as fh:
        fh.write(content)

    rec = LaunchPrepPairFile(pair_id=pair_id, path=f"{REWORK_DIR}/{stored}",
                             original_name=original, content_type=file.content_type,
                             size_bytes=len(content), kind="доработка")
    db.add(rec)
    journal.write(db, 'файл_доработки', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=target.publisher_id, actor_name=acc.name,
                  subject=_creative_subject(db, pair),
                  entity_type='launch_prep_pair', entity_id=pair_id)
    db.commit()
    return {"id": rec.id, "name": original, "size_bytes": len(content)}


# ─────────────────────────── Заявки о сбоях ───────────────────────────
#
# Площадка пишет в ТОТ ЖЕ журнал, что и сотрудники, — с пометкой контура (решение
# владельца 17.09.2026). Отдельный список для неё означал бы, что половина заявок
# теряется из виду просто потому, что лежит в другом месте.
#
# Кабинет в базу не пишет сам: приём и уведомление живут в `routers/bugs.py`, здесь
# только дверь для внешнего контура. Вторая копия приёма разошлась бы с первой молча.


class BugIn(BaseModel):
    publisher_id: int
    comment: str
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    app_version: Optional[str] = None
    viewport: Optional[str] = None


@router.post("/account/{account_id}/bug", dependencies=[Depends(require_cabinet_service)])
def cabinet_bug_create(account_id: int, payload: BugIn, db: Session = Depends(get_db)):
    from app.bugs import models as bug_models
    from app.routers import bugs as bug_api

    acc = _actor(db, account_id, payload.publisher_id)
    r = bug_api.create_report(
        db, contour=bug_models.PUB, author_name=acc.name or "—",
        account_id=acc.id, publisher_id=payload.publisher_id, comment=payload.comment,
        page_url=payload.page_url, page_title=payload.page_title,
        app_version=payload.app_version, viewport=payload.viewport)
    journal.write(db, 'заявка_о_сбое', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=payload.publisher_id, actor_name=acc.name,
                  entity_type='bug_report', entity_id=r.id)
    db.commit()
    return {"id": r.id}


@router.post("/bug/{report_id}/file", dependencies=[Depends(require_cabinet_service)])
async def cabinet_bug_file(report_id: int, account_id: int,
                           file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Снимок к своей заявке. Чужую дополнить нельзя — проверяем по учётке автора."""
    from app.bugs import models as bug_models
    from app.routers import bugs as bug_api

    r = db.query(bug_models.BugReport).filter(
        bug_models.BugReport.id == report_id).first()
    if not r or r.author_account_id != account_id:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    f = bug_api.attach(db, r, content=await file.read(),
                       filename=file.filename or "screen.png",
                       content_type=file.content_type)
    db.commit()
    return {"id": f.id, "name": f.original_name, "size_bytes": f.size_bytes}


@router.post("/bug/{report_id}/sent", dependencies=[Depends(require_cabinet_service)])
def cabinet_bug_sent(report_id: int, account_id: int, db: Session = Depends(get_db)):
    """Заявка дописана — уведомляем владельца. Отдельным вызовом по той же причине, что
    и во внутреннем контуре: снимки приезжают ПОСЛЕ создания."""
    from app.bugs import models as bug_models
    from app.routers import bugs as bug_api

    r = db.query(bug_models.BugReport).filter(
        bug_models.BugReport.id == report_id).first()
    if not r or r.author_account_id != account_id:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    bug_api.announce(db, r)
    db.commit()
    return {"ok": True}


# ─────────────────────────── Бот площадки ───────────────────────────
#
# БОТ ОТДЕЛЬНЫЙ ОТ ВНУТРЕННЕГО (владелец 15.09.2026): свой токен, своё имя, свой вебхук.
# Площадка видит бота подрядчика, а не наш внутренний алёрт-бот, и обработчик `/start`
# не гадает, чей перед ним код — у каждого контура своя таблица привязок.
#
# ПОДКЛЮЧАЕТ ЧЕЛОВЕК СЕБЕ САМ. Это не наша раздача и не следствие галочки «получает
# уведомления» на контакте: та галочка включает ПОЧТУ, а чат в телеграме мы за него
# завести не можем в принципе. Поэтому кнопка доступна каждому, кто вошёл в кабинет.


def _tg_row(db: Session, account_id: int):
    from app.cabinet.models import CabinetAccountTg
    return (db.query(CabinetAccountTg)
            .filter(CabinetAccountTg.account_id == account_id).first())


def _tg_account(db: Session, account_id: int, publisher_id: int):
    """Учётка, за которую говорит кабинет. Проверка ЗДЕСЬ, а не только у вызывающего —
    проверка, оставленная на вызывающей стороне, это отсутствие проверки."""
    from app.cabinet.models import CabinetAccount
    from app.cabinet.scope import account_sees_publisher

    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if not acc or not account_sees_publisher(db, acc, publisher_id):
        # 404, а не 403: 403 подтвердил бы, что такая связка существует.
        raise HTTPException(status_code=404, detail="Учётка не найдена")
    return acc


def _tg_state(db: Session, account_id: int) -> dict:
    """Состояние привязки одним ответом.

    Собирается ЗДЕСЬ, а не представлением для кабинета: половина ответа живёт не в базе.
    Имя бота ядро спрашивает у самого Телеграма (`getMe` по токену), из него же
    собирается диплинк. Отдай мы кабинету view — на экране оказались бы два источника
    одного состояния, и на перепривязке они разошлись бы.
    """
    from app.notify import telegram

    row = _tg_row(db, account_id)
    pending = None
    if row and row.link_code and (not row.link_expires
                                  or row.link_expires > datetime.utcnow()):
        pending = {"code": row.link_code, "expires_at": row.link_expires,
                   "link": telegram.link_url(row.link_code, telegram.PUB)}
    return {"configured": telegram.configured(telegram.PUB),
            "bot": telegram.bot_username(telegram.PUB),
            "linked": bool(row and row.verified_at),
            "linked_at": row.verified_at if row else None,
            "mute_until": row.mute_until if row else None,
            "pending": pending}


class TgIn(BaseModel):
    publisher_id: int


@router.get("/account/{account_id}/tg", dependencies=[Depends(require_cabinet_service)])
def cabinet_tg_state(account_id: int, publisher_id: int, db: Session = Depends(get_db)):
    _tg_account(db, account_id, publisher_id)
    return _tg_state(db, account_id)


@router.post("/account/{account_id}/tg/link",
             dependencies=[Depends(require_cabinet_service)])
def cabinet_tg_link(account_id: int, payload: TgIn, db: Session = Depends(get_db)):
    """Выдать код привязки. Человек отправляет его боту, chat_id запоминается на вебхуке.

    Перепривязка СБРАСЫВАЕТ старый чат: иначе «подключить заново» оставляло бы прежний
    чат получателем, и сообщения продолжали бы идти туда, откуда человек уже ушёл.
    """
    from app.cabinet.models import CabinetAccountTg
    from app.notify import telegram

    _tg_account(db, account_id, payload.publisher_id)
    if not telegram.configured(telegram.PUB):
        raise HTTPException(status_code=400,
                            detail="Бот кабинета не настроен: не задан TELEGRAM_PUB_BOT_TOKEN")
    row = _tg_row(db, account_id)
    if row is None:
        row = CabinetAccountTg(account_id=account_id)
        db.add(row)
    row.link_code, row.link_expires = telegram.new_link_code()
    row.chat_id, row.verified_at = None, None
    db.commit()
    return _tg_state(db, account_id)


@router.delete("/account/{account_id}/tg", dependencies=[Depends(require_cabinet_service)])
def cabinet_tg_unlink(account_id: int, publisher_id: int, author_name: Optional[str] = None,
                      db: Session = Depends(get_db)):
    """Отвязать бота. Строку не удаляем — гасим поля: запись о том, что бот когда-то был,
    остаётся в ленте, а не только в памяти того, кто отключал."""
    acc = _tg_account(db, account_id, publisher_id)
    row = _tg_row(db, account_id)
    if row and (row.chat_id or row.verified_at or row.link_code):
        row.chat_id = row.verified_at = row.link_code = row.link_expires = None
        journal.write(db, 'бот_отвязан', cabinet_id=acc.cabinet_id, account_id=acc.id,
                      publisher_id=publisher_id, actor_name=(author_name or acc.name))
        db.commit()
    return _tg_state(db, account_id)


def _tg_reply_later(chat_id: str, text_: str):
    """Ответ человеку ПОСЛЕ того, как мы уже ответили Телеграму.

    Та же причина, что во внутреннем контуре: связь с Телеграмом рваная, и ответ внутри
    запроса подвешивал обработчик — Телеграм не дожидался и считал доставку неуспешной,
    хотя привязка уже была записана.
    """
    from app.notify import telegram
    try:
        telegram.send_message(chat_id, text_, contour=telegram.PUB)
    except Exception:
        log_gw.warning("pub tg_webhook: ответ не ушёл", exc_info=True)


@webhook_router.post("/webhook/{secret}")
def cabinet_tg_webhook(secret: str, update: Dict[str, Any], bg: BackgroundTasks,
                       db: Session = Depends(get_db)):
    """Апдейты от бота кабинета. БЕЗ сервисного токена — стучится Телеграм, не кабинет.

    Поэтому закрыт секретом в пути (он же ставится в `setWebhook`), из тела берутся
    ТОЛЬКО код и chat_id, и тело апдейта — данные, а не команда: никакой логики по его
    содержимому нет. Всегда отвечаем 200, иначе Телеграм ретраит один и тот же апдейт.

    Секрет СВОЙ, отдельный от внутреннего: общий означал бы, что апдейт одного бота
    принимается адресом другого.

    Адрес — `/api/pub-bot/webhook/<секрет>`, НЕ под `/api/cabinet-gw/`: тот префикс
    закрыт на Caddy наглухо, и апдейты уходили бы в 404.
    """
    from app.cabinet.models import CabinetAccount, CabinetAccountTg
    from app.notify import telegram

    expected = os.getenv("TELEGRAM_PUB_WEBHOOK_SECRET") or ""
    if not expected or secret != expected:
        raise HTTPException(status_code=404, detail="Not found")

    code, chat_id = telegram.parse_start_command(update)
    if not code or not chat_id:
        return {"ok": True}

    row = (db.query(CabinetAccountTg)
           .filter(CabinetAccountTg.link_code == code).first())
    if row is None or (row.link_expires and row.link_expires < datetime.utcnow()):
        bg.add_task(_tg_reply_later, chat_id,
                    "Код не найден или просрочен. Получите новый в кабинете, "
                    "блок «Уведомления».")
        return {"ok": True}

    # Привязка пишется СРАЗУ и синхронно: она и есть результат запроса. В фон уходит
    # только ответное сообщение — не дойдёт оно, человек всё равно уже привязан.
    row.chat_id, row.verified_at = chat_id, datetime.utcnow()
    row.link_code = row.link_expires = None
    acc = db.query(CabinetAccount).filter(CabinetAccount.id == row.account_id).first()
    if acc:
        journal.write(db, 'бот_привязан', cabinet_id=acc.cabinet_id, account_id=acc.id,
                      actor_name=acc.name)
    db.commit()
    bg.add_task(_tg_reply_later, chat_id,
                f"Готово, {acc.name if acc else ''}. Уведомления будут приходить сюда.")
    return {"ok": True}


# ─────────────────────────── Лента ───────────────────────────

@router.get("/log-actions", dependencies=[Depends(require_cabinet_service)])
def cabinet_log_actions():
    """Словарь событий ленты — ОДИН на оба контура, по той же причине, что каталог
    рассылки: вторая копия подписей разошлась бы с первой, и разошлась бы молча.

    Тон и сторона лежат в самой строке журнала (они заданы событием в момент записи и не
    должны меняться задним числом, если словарь поправили). Отсюда берётся только
    подпись — то, чего в строке нет.
    """
    return {"actions": [{"key": a.key, "label": a.label} for a in journal.ACTIONS]}
