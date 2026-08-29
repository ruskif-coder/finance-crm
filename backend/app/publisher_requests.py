"""Тикеты к площадке: сверка объёма за месяц и продление кампании.

Одна форма на два вида. У них один жизненный цикл — спросили, ждём, ответили, — и две
таблицы означали бы дважды написать «кто молчит третий день», дважды посчитать срок и
однажды разойтись в этих двух копиях. Отличаются они тем, ЧТО спрашивают, и это
выражено полями: у сверки заполнен `period`, у продления — `deal_id`.

Таблицы созданы миграцией backend/migrations/2026-08-28_publisher_requests.sql.
"""
from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

REQUEST_KINDS = ('сверка', 'пролонгация')

# Исходы разные у разных видов, и это не оплошность перечня: у сверки площадка
# подтверждает объём или оспаривает его, у продления — разрешает запуск или нет.
REQUEST_VERDICTS = {
    'сверка': ('подтверждено', 'оспорено'),
    'пролонгация': ('разрешено', 'отказано'),
}


class PublisherRequest(Base):
    __tablename__ = "publisher_request"
    id = Column(Integer, primary_key=True)
    kind = Column(Text, nullable=False)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="RESTRICT"),
                          nullable=False)
    deal_id = Column(Integer, ForeignKey("sales_deals.id", ondelete="CASCADE"))
    # Ключ сверки — пара «площадка × месяц»: месяц оплачивается ОДНИМ платежом без
    # разбивки по кампаниям (владелец 28.08.2026), поэтому площадка подтверждает одну
    # цифру, а кампании внутри месяца — детализация под ней.
    period = Column(Text)
    asked_at = Column(DateTime, nullable=False, server_default=func.now())
    due_at = Column(Date)
    # Пустой вердикт означает «спросили, ответа нет» — то же соглашение, что у проверок
    # креатива, и из него же считается молчание.
    verdict = Column(Text)
    reason = Column(Text)
    decided_at = Column(DateTime)
    # Снимок автора: под подтверждённый объём закрываются документы, и смена
    # ответственного задним числом не должна переписывать, кто его признал.
    decided_by = Column(Text)
    decided_email = Column(Text)

    recon = relationship("PublisherRecon", back_populates="request", uselist=False,
                         cascade="all, delete-orphan")


class PublisherRecon(Base):
    """Три числа сверки. Здесь факт показов ВПЕРВЫЕ входит в систему.

    До сверки его нет нигде: у кампании есть только состояние «запущен» (владелец
    28.08.2026), автоимпорт откруток появится позже.

    Расхождение НЕ хранится — считается из двух колонок. Хранимая разница разъезжается
    с операндами; так уже было с суммами в импорте Диадока.

    `their_volume` держится отдельно, хотя источник пока один и цифры совпадают всегда.
    Пока это так, подтверждение площадки — ПОДПИСЬ, а не сверка, и ценность её в том,
    что под закрывающие документы есть признанный объём. В день, когда у площадки
    появится свой счётчик, менять придётся данные, а не схему.
    """
    __tablename__ = "publisher_recon"
    request_id = Column(Integer, ForeignKey("publisher_request.id", ondelete="CASCADE"),
                        primary_key=True)
    our_volume = Column(BigInteger)
    their_volume = Column(BigInteger)
    agreed_volume = Column(BigInteger)

    request = relationship("PublisherRequest", back_populates="recon")


def mismatch(recon) -> float:
    """Расхождение в процентах от нашей цифры. Считается, а не хранится.

    Ноль нашего объёма — не «расхождение 100 %», а «сравнивать не с чем»: возвращаем 0,
    иначе первый же месяц без открутки покрасится красным на пустом месте.
    """
    if not recon or not recon.our_volume:
        return 0.0
    theirs = recon.their_volume if recon.their_volume is not None else recon.our_volume
    return abs(theirs - recon.our_volume) / recon.our_volume * 100
