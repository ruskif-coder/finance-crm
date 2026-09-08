"""Модуль креативов: сбор запуска внутри ядра.

Таблицы создаются миграцией backend/migrations/2026-08-26_launch_prep_creatives.sql,
состав согласован с владельцем 26.08.2026 (docs/SCHEMA_креативы_на_согласование.md).

Три сущности, и путать их — главный способ сломать модуль:

  · **получатель** (`LaunchPrepTarget`) — пара «сделка × площадка». Долгоживущая, несёт
    состояние. Площадки идут своим темпом: одна стартует, вторая ещё правит, поэтому
    стадия сделки становится сводкой, а не источником правды;
  · **комплект** (`LaunchPrepCreativeSet`) — материал и его итерация. Принадлежит СДЕЛКЕ,
    а не получателю: общий уходит всем, персональный цепляется площадке со сложными ТТ;
  · **пара** (`LaunchPrepPair`) — «комплект × получатель». Единица согласования у трафиков
    и единица учёта в DSP; той же гранью ОРД принимает показы в акте.

Состояние комплекта и пары ВЫЧИСЛЯЕТСЯ из вердиктов — хранимое производное разъезжается
с операндами. Состояние получателя хранится: это решение человека, а не следствие данных.
"""
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# Состояния получателя. Пин на этот список стоит в тестах, а не CHECK'ом в базе:
# модуль трафиков добавит свои под-этапы, и расширение не должно требовать миграции.
TARGET_STATES = (
    'согласование',      # отправлено, ждём вердиктов
    'согласован',        # первичная ТТ и площадка сказали «ок»
    'ерид получен',      # маркер выпущен на комплект этой пары
    'заведён в DSP',     # работа модуля трафиков; пока проскакивается
    'в размещении',      # запуск по кнопке или биддеру
    'завершён',
    'сверка завершена',
    'архив',
    # Боковой выход, а не ступень: площадка отказалась брать размещение (нет товара,
    # ограничения по бренду). Стоит в конце списка намеренно — переход в него разрешён
    # с любой ступени, а обратно нельзя, и порядковое сравнение это обеспечивает само.
    'отказ площадки',
)

# Что видит площадка. Три состояния после маркера сворачиваются в одно: «эти три стадии
# важны для нас, для площадки мы не детализируем после получения ЕРИД» (владелец).
# Свёртка ВЫЧИСЛЯЕТСЯ — второго поля под неё нет, иначе копия разъедется с оригиналом.
TARGET_STATE_PUBLIC = {
    'согласование':     'на согласовании',
    'согласован':       'согласован',
    'ерид получен':     'ЕРИД получен',
    'заведён в DSP':    'ЕРИД получен',
    'в размещении':     'ЕРИД получен',
    'завершён':         'завершено',
    'сверка завершена': 'сверка завершена',
    'архив':            'архив',
    'отказ площадки':   'отказ',
}

# 'продление' — комплект, скопированный с прошлой кампании (28.08.2026). Материал тот
# же, поэтому трафик его повторно не смотрит, а площадка отвечает не «согласовать
# креатив», а «запуск разрешён». Отдельное значение нужно затем, чтобы обе эти поблажки
# имели видимое основание: без него «ок» трафика без проверки выглядит как ошибка.
SET_ORIGINS = ('первичный', 'доработка', 'параллельный', 'продление')
ERID_SOURCES = ('наш', 'площадки')

REVIEW_KINDS = ('первичная_тт', 'трафики', 'площадка')
# «Отказ» — третий исход, а не разновидность доработки: доработка означает «переделайте
# и пришлите снова», отказ — «мы это не берём», и новая версия делу не поможет.
REVIEW_VERDICTS = ('ок', 'на доработку', 'отказ')

# ВЕРДИКТЫ РАЗНЫЕ У РАЗНЫХ СТУПЕНЕЙ, и `REVIEW_VERDICTS` выше — набор ПЛОЩАДКИ, а не
# всей колонки. Замечено 30.08.2026: трафик пишет в ту же колонку «на переделку»,
# которого в том кортеже нет. Пока это ничем не выстрелило — переделок в данных ноль, —
# но объявление читалось как словарь колонки, и первый же CHECK или валидация, собранные
# из него, отвергли бы возврат трафика.
#
# Слова разные намеренно: площадка просит ДОРАБОТАТЬ материал и остаётся в кампании,
# трафик отправляет комплект на ПЕРЕДЕЛКУ целиком. Сливать их в одно слово нельзя —
# различие несёт смысл, и оно же различает адресата.
REVIEW_VERDICTS_BY_KIND = {
    'первичная_тт': ('ок', 'на доработку'),
    'трафики':      ('ок', 'на переделку'),
    'площадка':     ('ок', 'на доработку', 'отказ'),
}
# 'авто' — вердикт трафиков ПЕРВОЙ версии, до конвейера проверки. С 28.08.2026 таких
# больше не появляется: трафик отвечает сам, источник 'трафики'. Значение остаётся в
# перечне намеренно — им помечены строки, которых никто не смотрел, и стереть эту
# разницу задним числом значило бы выдать машинную отметку за человеческую.
# 'продление' — отметка трафика, перенесённая с прошлой кампании. Это НЕ 'авто':
# материал действительно проверен, просто в прошлый раз. Слить их значило бы потерять
# разницу между «никто не смотрел» и «смотрели в прошлом периоде».
REVIEW_SOURCES = ('авто', 'аккаунт', 'трафики', 'кабинет', 'продление')


class LaunchPrepTarget(Base):
    """Получатель задания: одна строка на пару «сделка × площадка», не на итерацию.

    Итерации в ключе НЕТ намеренно: иначе у одной площадки появляются две строки, и
    становится неясно, у какой из них состояние и к какой цепляются сверка, ОРД и архив.
    """
    __tablename__ = "launch_prep_target"
    __table_args__ = (UniqueConstraint("deal_id", "publisher_id",
                                       name="uq_launch_prep_target"),)
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    # Без каскада: площадка уходит в АРХИВ статусом, а не удалением.
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id"),
                          nullable=False, index=True)
    # Снимок услуги на момент отправки, он же ключ подстановки получателей. Ссылки на
    # услугу у сделки нет, но услуга известна: sales_deals.product хранит имя из
    # справочника и по живым сделкам совпадает в 297 случаях из 298 (замер 26.08.2026).
    service_id = Column(Integer, ForeignKey("sales_services.id"), nullable=False)
    surface_kind = Column(String(8), nullable=False)          # web | app
    state = Column(String(32), nullable=False, default='согласование',
                   server_default='согласование', index=True)
    period_from = Column(Date)
    period_to = Column(Date)
    # Посадочная страница ЭТОЙ площадки: карточка товара или подборка на её сайте.
    # Живёт на получателе, а не на сделке (миграция 2026-08-27_target_landing_urls.sql):
    # одной ссылки на сделку в этой модели не существует — страница всегда чужая и своя
    # у каждого сайта. В ОРД уезжает списком: advertiserUrls в теле креатива — массив.
    advertiser_url = Column(String(512))
    # Ссылку не всегда знаем: иногда её просят собрать саму площадку (подборка).
    # Состояние ссылки ВЫЧИСЛЯЕТСЯ из этих двух полей, третьей колонки под статус нет.
    url_requested_at = Column(DateTime)
    url_request_text = Column(Text)
    ord_submitted_at = Column(DateTime)      # сдан в ОРД — условие ухода в архив
    archived_at = Column(DateTime)           # от неё считаются 180 дней до скрытия
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime)

    pairs = relationship("LaunchPrepPair", back_populates="target")


class LaunchPrepCreativeSet(Base):
    """Комплект креативов, он же итерация. Принадлежит сделке, а не получателю.

    `publisher_id IS NULL` — общий комплект для всех; заполнен — персональный комплект
    площадки. Ограничение уникальности обязано быть NULLS NOT DISTINCT: по умолчанию
    Postgres считает NULL различными и пропустил бы два общих комплекта с одним номером.
    """
    __tablename__ = "launch_prep_creative_set"
    __table_args__ = (
        UniqueConstraint("deal_id", "publisher_id", "no", name="uq_lp_set_no",
                         postgresql_nulls_not_distinct=True),
        CheckConstraint("replaces_set_id IS NULL OR origin = 'доработка'",
                        name="ck_lp_set_replaces"),
    )
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id"))
    no = Column(Integer, nullable=False)
    # Номер присваивается по порядку и НЕ меняется: на него ссылаются журнал действий,
    # уведомления и код пары. Название — свободная подпись человека, правится отдельно
    # (миграция 2026-08-27_creative_set_title.sql).
    title = Column(Text)
    # Зачем комплект появился. НЕ выводится задним числом: комплект принадлежит сделке, а
    # вердикты — парам, и у комплекта, завёрнутого одной площадкой и принятого другой,
    # правильного ответа нет вообще. Записанное намерение — факт, выведенное — догадка.
    origin = Column(String(16), nullable=False, default='первичный',
                    server_default='первичный')
    # SET NULL, а не CASCADE: удаление заменённого комплекта не должно уносить преемника.
    replaces_set_id = Column(Integer,
                             ForeignKey("launch_prep_creative_set.id", ondelete="SET NULL"))
    sent_at = Column(DateTime)
    form = Column(String(32))            # Banner | BannerHtml5 | Video — выводится из файлов
    # ЗАМОРОЖЕНО 31.08.2026: код ККТУ живёт у бренда и задаётся один раз на сделку в
    # блоке сборки ОРД. Переопределение на отдельный креатив противоречило этому и не
    # было использовано ни разу (0 из 24). Колонка оставлена (правило проекта: поле
    # замораживается, а не дропается), но код её не читает и не пишет.
    kktu_code = Column(String(16))
    description = Column(Text)           # переопределение описания объекта рекламирования
    erid = Column(String(64))
    # У саморекламы маркер выпускает площадка. Без признака код не отличит «ещё не
    # выпустили» от «не будет никогда» и будет опрашивать статус вечно.
    erid_source = Column(String(16), nullable=False, default='наш', server_default='наш')
    ord_creative_id = Column(String(64))
    ord_status = Column(String(40))      # Creating..Active | RegistrationError | MediaDownloadError
    ord_error = Column(Text)             # erirValidationError
    ord_env = Column(String(8))          # demo | prod — контур рядом с идентификатором
    ord_synced_at = Column(DateTime)
    # ТЕСТОВАЯ ссылка нацеливания (2026-08-28_traffic_queue.sql): ставит демо-куку
    # кампании, чтобы трафик увидел рекламу до старта. Живёт на комплекте, потому что
    # кампания в DSP заводится на креатив — два баннера дают две ссылки. Просто хранится
    # и кликается: с посадочной не склеивается, проверку не блокирует, видна и трафику,
    # и аккаунтам. Боевая ссылка запуска — другая сущность, и поле у неё будет своё.
    test_targeting_url = Column(Text)
    # Письмо о правах на изображения (миграция 2026-09-07_rights_letter.sql) — ОДНО на
    # креатив (владелец), поэтому колонками, а не таблицей. Намеренно НЕ в
    # `launch_prep_creative_file`: оттуда `_derive_form` выводит форму креатива для ОРД,
    # и PDF изменил бы то, что уезжает в ЕРИР, а `pub.task_file_v1` нарисовал бы письмо
    # сломанным баннером в предпросмотре кабинета. В ОРД письмо не идёт вовсе.
    rights_letter_path = Column(String(512))     # относительный ключ, не абсолютный путь
    rights_letter_name = Column(String(255))
    rights_letter_type = Column(String(128))
    rights_letter_size = Column(Integer)
    # Кто и когда прикрепил — вместе отвечают на «при каком письме площадка согласовала».
    rights_letter_at = Column(DateTime)
    rights_letter_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime)

    files = relationship("LaunchPrepCreativeFile", back_populates="creative_set")
    pairs = relationship("LaunchPrepPair", back_populates="creative_set")


class LaunchPrepCreativeFile(Base):
    """Файл комплекта. Первый потребитель соглашения о путях от 23.08.2026.

    В колонке лежит ОТНОСИТЕЛЬНЫЙ ключ от корня хранилища (`creatives/cre<set_id>_<имя>`),
    а имя на диске несёт вид сущности — иначе файлы разных подсистем затирают друг друга
    в общем каталоге, как уже было у площадок (`pub7_`/`con7_`/`doc7_`).
    """
    __tablename__ = "launch_prep_creative_file"
    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("launch_prep_creative_set.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    ratio = Column(String(24))                 # 300x600, 240x400 …
    path = Column(String(512), nullable=False)
    original_name = Column(String(255))
    content_type = Column(String(128))
    size_bytes = Column(Integer)
    # Распаковываемый архив (HTML5-баннер) — едет в ОРД тем же признаком isArchive.
    is_archive = Column(Boolean, nullable=False, default=False, server_default='false')
    # Песочница: каталог раздачи со случайным именем и точка входа внутри архива
    # (миграция 2026-08-27_sandbox.sql). Пусто у картинок и у архивов, которые
    # распаковать не удалось, — тогда предпросмотр честно говорит почему.
    sandbox_token = Column(Text)
    entry_path = Column(Text)
    uploaded_at = Column(DateTime, server_default=func.now())
    uploaded_by = Column(Integer, ForeignKey("users.id"))

    creative_set = relationship("LaunchPrepCreativeSet", back_populates="files")


class LaunchPrepPair(Base):
    """Пара «креатив × площадка»: единица согласования и единица учёта в DSP.

    `code` вида `HCLA6E-MKS-01` выдаётся В МОМЕНТ СХОЖДЕНИЯ, а не при создании: «всё до
    „согласовано“ стабильной парой ещё не является». Отвергнутая итерация имени не
    получает, поэтому в нумерации нет дыр от версий, которых не было, а `NN` считает
    СРОСШИЕСЯ пары внутри размещения, а не итерации.
    """
    __tablename__ = "launch_prep_pair"
    __table_args__ = (UniqueConstraint("set_id", "target_id", name="uq_lp_pair"),)
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True)
    set_id = Column(Integer, ForeignKey("launch_prep_creative_set.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("launch_prep_target.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    sent_at = Column(DateTime)      # ушла площадке — после отмашки трафиков
    agreed_at = Column(DateTime)    # момент схождения, тогда же выдаётся code
    created_at = Column(DateTime, server_default=func.now())

    creative_set = relationship("LaunchPrepCreativeSet", back_populates="pairs")
    target = relationship("LaunchPrepTarget", back_populates="pairs")
    reviews = relationship("LaunchPrepReview", back_populates="pair")
    screenshots = relationship("LaunchPrepPairFile", back_populates="pair")


class LaunchPrepPairFile(Base):
    """Скриншот размещения (2026-08-28_traffic_queue.sql). Зерно — пара, а не сделка.

    Доказательство всегда про конкретный баннер на конкретном сайте: срез «по сделке»
    смешал бы восемь площадок, срез «по площадке» — все креативы кампании.

    Подписи к файлу НЕТ намеренно (владелец 27.08.2026): грузят пакетом, и поштучная
    разметка противоречит самому способу работы. Зато имя на диске собираем МЫ — вся
    цепочка в нём, см. `traffic_file_name`.
    """
    __tablename__ = "launch_prep_pair_file"
    id = Column(Integer, primary_key=True)
    pair_id = Column(Integer, ForeignKey("launch_prep_pair.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    path = Column(Text, nullable=False)
    original_name = Column(Text)
    content_type = Column(Text)
    size_bytes = Column(Integer)
    # 'размещение' — доказательство, снятое трафиком; 'доработка' — картинка, приложенная
    # ПЛОЩАДКОЙ к объяснению, что не так с креативом. Разный смысл и разная судьба при
    # уборке по срокам, поэтому вид, а не общая куча.
    kind = Column(Text, nullable=False, default='размещение', server_default='размещение')
    uploaded_at = Column(DateTime, server_default=func.now())
    # Снимок имени, а не ссылка на учётку — как у вердиктов: смена ответственного не
    # должна переписывать, кто приложил доказательство.
    uploaded_by = Column(Text)

    pair = relationship("LaunchPrepPair", back_populates="screenshots")


class LaunchPrepReview(Base):
    """Проверка. Строка заводится ПУСТОЙ в момент запроса.

    Пустой вердикт означает «спросили, ответа нет». Из этого списка берутся сразу две
    величины: знаменатель порога ЕРИД («те, кому комплект отправлен») и ответ на «кто
    молчит третий день» для пинга. Если строка появляется только вместе с вердиктом,
    обе становятся невычислимыми.

    `pair_id IS NULL` — первичная проверка комплекта целиком: она про материал, а не про
    получателя, и делается до раскладки по площадкам.

    `kind` и `source` — разные поля намеренно. За один день 26.08 проверка трафиков успела
    побыть параллельной веткой, исчезнуть из первой версии и вернуться предварительным
    шагом с разбивкой по площадкам; ни одно из трёх изменений не тронуло структуру.
    """
    __tablename__ = "launch_prep_review"
    __table_args__ = (UniqueConstraint("set_id", "pair_id", "kind", name="uq_lp_review",
                                       postgresql_nulls_not_distinct=True),)
    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("launch_prep_creative_set.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    pair_id = Column(Integer, ForeignKey("launch_prep_pair.id", ondelete="CASCADE"),
                     index=True)
    kind = Column(String(16), nullable=False)
    verdict = Column(String(16))                 # ок | на доработку; NULL = ответа нет
    reason = Column(Text)
    asked_at = Column(DateTime, nullable=False, server_default=func.now())
    decided_at = Column(DateTime)
    # Снимок имени, а не ссылка на учётку: смена ответственного задним числом иначе
    # перепишет историю согласований — вердикт окажется «подписан» тем, кто его не ставил.
    decided_by = Column(String(128))
    # Почта автора — снимком по той же причине (миграция 2026-08-28_publisher_cabinet.sql).
    # Учётка кабинета заводится НА ЧЕЛОВЕКА, людей за одной площадкой несколько, и через
    # год «Иванов» перестанет отличаться от другого «Иванова».
    decided_email = Column(Text)
    source = Column(String(16), nullable=False)

    pair = relationship("LaunchPrepPair", back_populates="reviews")


class SalesRefusalReason(Base):
    """Причины отказа площадки — свой накопитель, а не общий с причинами доработки.

    «Товара нет в наличии» и «тяжёлый файл» отвечают на разные вопросы: первое закрывает
    площадку для этой кампании, второе просит новую версию. В одном списке человек
    выбирал бы из смеси несравнимого.
    """
    __tablename__ = "sales_refusal_reasons"
    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')


class SalesUrlRequestPhrase(Base):
    """Готовые фразы для запроса ссылки у площадки.

    Накопитель того же вида, что причины доработки: набранная фраза уходит в общий
    список и дальше предлагается всем. Хранится текстом, а не ключом, — вставленная
    в запрос фраза не должна меняться задним числом вместе со справочником.
    """
    __tablename__ = "sales_url_request_phrases"
    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')


class SalesReworkReason(Base):
    """Причины доработки — накопитель того же вида, что виды площадок и типы документов."""
    __tablename__ = "sales_rework_reasons"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')


class LaunchPrepSetTarget(Base):
    """Кому адресован ЭТОТ креатив (backend/migrations/2026-08-27_set_targets.sql).

    Список площадок принадлежит креативу, а не сделке: во втором креативе состав свой,
    и добавленная в него площадка не должна появляться в первом. Сама площадка при этом
    остаётся сущностью сделки — там её состояние и посадочная страница, они про площадку
    в кампании, а не про конкретный баннер. Разбор целиком — в шапке миграции.
    """
    __tablename__ = "launch_prep_set_target"
    __table_args__ = (UniqueConstraint("set_id", "target_id", name="uq_lp_set_target"),)
    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("launch_prep_creative_set.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("launch_prep_target.id", ondelete="CASCADE"),
                       nullable=False)
    added_at = Column(DateTime, server_default=func.now(), default=datetime.utcnow)

