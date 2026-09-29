"""Выгрузка по РК для площадок без нашего кода — архивом для трафика (владелец 29.09.2026,
п. 7 списка трафиков от 25.09).

Площадка «не наша» — у неё на сайте нет нашего кода (`sales_publishers.our_code` ложь):
крутит своей системой, креатив заводит трафик руками. В выгрузку идут ВСЕ креативы,
отправленные площадке (включая несогласованные и отозванные — их статус виден в паспорте).

Состав архива:

    <СДЕЛКА>_не_наши/
      паспорт_<СДЕЛКА>.xlsx                  одна строка = креатив × площадка
      <КОДПЛОЩАДКИ>_<домен>/<СДЕЛКА>-<КОДПЛОЩАДКИ>-cr<№>-<nn>.zip

Баннер — ИСХОДНИК КЛИЕНТА, без наших вставок (`originals.path_for_publisher`); площадке
с каналом Adfox — с `%user6%` после `<body>` (шпаргалка docs/ШПАРГАЛКА_креатив_под_площадку.md).
Имена в архиве — латиница: кириллица ломается у части распаковщиков Windows. Полное
имя и путь каждого архива стоят в паспорте, чтобы строку таблицы можно было найти файлом.
"""
import io
import os
import zipfile
from datetime import date
from typing import Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from app.launch_prep import originals, pub_rules, sandbox
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepCreativeSet, LaunchPrepPair,
                                    LaunchPrepReview, LaunchPrepSetTarget, LaunchPrepTarget)
from app.sales.models import SalesDeal, SalesPublisher
from app.traffic.files import _ascii_code, traffic_file_name
from app.xlsx_safe import save_workbook

HEAD = ["Площадка", "Домен", "Поверхность", "Канал", "Креатив №", "Название креатива",
        "Файл клиента", "Имя архива в выгрузке", "Путь в архиве", "Размер", "Статус у площадки",
        "Код пары", "ЕРИД", "Посадочная", "Диплинк", "Старт", "Конец", "План показов",
        "Пиксель Weborama"]
WIDTH = [22, 22, 10, 12, 9, 26, 28, 34, 52, 10, 16, 16, 16, 40, 30, 11, 11, 12, 40]


class NothingToExport(LookupError):
    """В РК нет площадок без нашего кода с отправленными креативами."""


def _status(pair, verdict) -> str:
    if pair.withdrawn_at:
        return "отозван"
    return {"ок": "согласован", "на доработку": "на доработке", "отказ": "отказ"}.get(
        verdict, "ждёт ответа")


def build(db: Session, deal: SalesDeal) -> Tuple[bytes, str]:
    from app.ad.models import AdCampaign, AdCampaignPlacement

    rows = (db.query(LaunchPrepPair, LaunchPrepCreativeSet, LaunchPrepTarget, SalesPublisher)
            .join(LaunchPrepCreativeSet, LaunchPrepCreativeSet.id == LaunchPrepPair.set_id)
            .join(LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id)
            .join(SalesPublisher, SalesPublisher.id == LaunchPrepTarget.publisher_id)
            .filter(LaunchPrepCreativeSet.deal_id == deal.id,
                    LaunchPrepPair.sent_at.isnot(None),
                    SalesPublisher.our_code.isnot(True))
            .order_by(SalesPublisher.name, LaunchPrepCreativeSet.no).all())
    if not rows:
        raise NothingToExport("В РК нет площадок без нашего кода, которым отправлялись креативы")

    pair_ids = [p.id for p, *_ in rows]
    verdicts = dict(db.query(LaunchPrepReview.pair_id, LaunchPrepReview.verdict)
                    .filter(LaunchPrepReview.pair_id.in_(pair_ids),
                            LaunchPrepReview.kind == "площадка").all())
    set_ids = {s.id for _, s, _, _ in rows}
    files = {}
    for f in (db.query(LaunchPrepCreativeFile).filter(LaunchPrepCreativeFile.set_id.in_(set_ids))
              .order_by(LaunchPrepCreativeFile.id)):
        files.setdefault(f.set_id, []).append(f)
    members = {(m.set_id, m.target_id): m for m in db.query(LaunchPrepSetTarget)
               .filter(LaunchPrepSetTarget.set_id.in_(set_ids))}
    placements = {pl.publisher_id: pl for pl in db.query(AdCampaignPlacement)
                  .join(AdCampaign, AdCampaign.id == AdCampaignPlacement.campaign_id)
                  .filter(AdCampaign.deal_id == deal.id)}
    rules = pub_rules.rules_for(db, {(t.publisher_id, t.surface_kind) for _, _, t, _ in rows})

    deal_code = _ascii_code(deal.code, "deal")
    root = f"{deal_code}_offsite"
    wb = Workbook()
    ws = wb.active
    ws.title = "Паспорт"
    ws.append(HEAD)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E3E7EF")
        c.alignment = Alignment(wrap_text=True, vertical="top")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for pair, s, t, pub in rows:
            rule = rules.get((t.publisher_id, t.surface_kind)) or {}
            member = members.get((s.id, t.id))
            pl = placements.get(t.publisher_id)
            # Поверхность — в имени папки: у площадки бывают и web, и app в одной РК, и без
            # неё файлы одного креатива легли бы одним путём и затёрли друг друга (ревью 29.09).
            # Нет кода — номер площадки, чтобы две безымянные не слились в одну папку.
            folder = (f"{_ascii_code(pub.code, f'site{pub.id}')}_"
                      f"{_ascii_code((pub.domain or pub.name or '').replace('.', '_'), 'site')}_"
                      f"{_ascii_code(t.surface_kind, 'web')}")
            for seq, f in enumerate(files.get(s.id, []), start=1):
                ext = os.path.splitext(f.original_name or f.path)[1].lower() or ".bin"
                name = traffic_file_name(deal.code, pub.code, s.no, seq, ext)
                path = f"{root}/{folder}/{name}"
                full = originals.path_for_publisher(f.path)
                if full and os.path.exists(full):
                    with open(full, "rb") as fh:
                        data = fh.read()
                    if f.is_archive and rule.get("channel") == "adfox":
                        data, _ = sandbox.insert_adfox_macro(data)
                    z.writestr(path, data)
                else:
                    path = f"(файл не найден в хранилище) {path}"
                ws.append([
                    pub.name, pub.domain, t.surface_kind, pub_rules.CHANNELS.get(rule.get("channel"), "—"),
                    s.no, s.title, f.original_name, name, path, f.ratio,
                    _status(pair, verdicts.get(pair.id)), pair.code, s.erid,
                    member.advertiser_url if member else None,
                    getattr(member, "deeplink_url", None) if member else None,
                    t.period_from or deal.period_from, t.period_to or deal.period_to,
                    (member.plan_show if member and member.plan_show else (pl.plan_show if pl else None)),
                    pl.weborama_pixel if pl else None])
        for col, w in zip("ABCDEFGHIJKLMNOPQRS", WIDTH):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for c in (row[15], row[16]):
                c.number_format = "DD.MM.YYYY"
            row[17].number_format = "# ##0"
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        x = io.BytesIO()
        save_workbook(wb, x)   # щит от формул: имена от клиента могут начинаться с «=»
        z.writestr(f"{root}/pasport_{deal_code}.xlsx", x.getvalue())
    return buf.getvalue(), f"{deal_code}_offsite_{date.today():%Y%m%d}.zip"
