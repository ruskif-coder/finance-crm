# -*- coding: utf-8 -*-
"""Разбор XML УПД из 1С (формат ФНС, КНД 1115131: версии 5.01 и 5.03) — номер, дата, суммы, покупатель и договор.

Пути (сверено со схемами ФНС; ищем по локальным именам — пространства имён и версии у выгрузок 1С разные):
  Документ/СвСчФакт            @НомерДок @ДатаДок (5.03) | @НомерСчФ @ДатаСчФ (5.01)
  СвСчФакт/СвПокуп/ИдСв        СвЮЛУч @ИННЮЛ @КПП | СвИП @ИННФЛ
  ТаблСчФакт/ВсегоОпл          @СтТовБезНДСВсего @СтТовУчНалВсего, СумНалВсего/СумНал (текст)
  СвПродПер/СвПер/ОснПер       @НомОсн @НаимОсн (5.01) | @РеквНомерДок @РеквНаимДок (5.03) — договор и ДС
Сверку со сделкой делают `rules.evaluate` и фронт по тем же полям: ИНН, КПП, № договора."""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

from app.onec_desk.service import DeskError

_DANGEROUS = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(root, name: str):
    return next((e for e in root.iter() if _local(e.tag) == name), None)


def _all(root, name: str) -> list:
    return [e for e in root.iter() if _local(e.tag) == name]


def _attr(e, *names) -> Optional[str]:
    if e is None:
        return None
    for n in names:
        v = e.get(n)
        if v not in (None, ""):
            return v.strip()
    return None


def _money(v: Optional[str]) -> str:
    """Сумма строкой, как её ввёл бы человек: «1 000 000,40» — форма бухгалтера хранит строки."""
    if v is None:
        return ""
    try:
        x = round(float(v.replace(",", ".")), 2)
    except ValueError:
        return ""
    whole, frac = f"{x:.2f}".split(".")
    return f"{int(whole):,}".replace(",", " ") + "," + frac


def _ru_date(v: Optional[str]) -> str:
    if not v:
        return ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return ""


ZIP_MAX = 10 * 1024 * 1024          # распакованный УПД — килобайты; больше — не выгрузка 1С
_LATIN = str.maketrans("abcehkmoptxy", "авсенкмортху")


def unpack(content: bytes) -> bytes:
    """Архив ЭДО (контейнер оператора, образец Такском 05.11.2026): meta.xml → MainImage@Path — сам УПД; meta.xml нет —
    единственный ON_NSCHFDOPPR*.xml. Не архив — отдаём как есть."""
    if not content.startswith(b"PK"):
        return content
    import io
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise DeskError(400, "Архив не открывается") from None
    names = z.namelist()
    main = None
    if "meta.xml" in names:
        meta = _read(z, "meta.xml")
        try:
            el = _find(ET.fromstring(meta), "MainImage")
            main = el.get("Path") if el is not None else None
        except ET.ParseError:
            main = None
    if main not in names:
        cands = [n for n in names if n.lower().endswith(".xml") and n.rsplit("/", 1)[-1].upper().startswith("ON_NSCHFDOPPR")]
        main = cands[0] if len(cands) == 1 else None
    if main is None:
        raise DeskError(400, "В архиве не нашли УПД (ON_NSCHFDOPPR…xml)")
    return _read(z, main)


def _read(z, name: str) -> bytes:
    if z.getinfo(name).file_size > ZIP_MAX:
        raise DeskError(400, "Файл в архиве слишком большой для УПД")
    return z.read(name)


def contract_key(s: Optional[str]) -> str:
    """Номер договора без написания: «Договор РМ 30-02-2025» = «РМ 30-02-25» = «PM-30-02-25» — без слова «договор» и «№»,
    латиница как кириллица, год из четырёх цифр — двумя, без знаков и пробелов."""
    t = re.sub(r"(?i)договор|№|\bno\b", " ", (s or "").lower()).translate(_LATIN)
    parts = [p[2:] if re.fullmatch(r"20\d\d", p) else p for p in re.split(r"[^0-9a-zа-яё]+", t) if p]
    return "".join(parts)


def text_key(s: Optional[str]) -> str:
    """Текст основания без оформления: пробелы схлопнуты, кавычки «» “” "" — одни, регистр не важен."""
    return re.sub(r"\s+", " ", re.sub(r"[«»“”„\"']", '"', s or "")).strip().lower()


def parse(content: bytes, contract_no: Optional[str] = None, basis: Optional[str] = None) -> dict:
    """→ {number, date, net, vat, gross, buyer: {inn, kpp}, contract, contract_1c, basis}. Принимает и XML, и архив ЭДО.
    contract_no — № договора сделки: если среди оснований есть он (в написании 1С — «Договор РМ 30-02-2025»), отдаём НАШ
    номер — экран и `rules.evaluate` сравнивают строки; `contract_1c` — как записано в УПД. Иначе — основание с «договор» в
    названии или первое: тогда сверка покажет несовпадение."""
    if not content:
        raise DeskError(400, "XML пустой")
    content = unpack(content)
    if _DANGEROUS.search(content[:4096]):
        raise DeskError(400, "XML с DOCTYPE/ENTITY не принимаем — это не выгрузка УПД из 1С")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise DeskError(400, f"XML не читается: {e}") from None
    sf = _find(root, "СвСчФакт")
    if sf is None:
        raise DeskError(400, "Это не XML УПД: нет сведений о счёте-фактуре (СвСчФакт)")
    buyer = _find(sf, "СвПокуп")
    ul = _find(buyer, "СвЮЛУч") if buyer is not None else None
    ip = _find(buyer, "СвИП") if buyer is not None else None
    total = _find(root, "ВсегоОпл")
    vat_el = _find(total, "СумНал") if total is not None else None
    bases = [(_attr(e, "НомОсн", "РеквНомерДок") or "", (_attr(e, "НаимОсн", "РеквНаимДок") or "").lower()) for e in _all(root, "ОснПер")]
    numbers = [n for n, _ in bases if n]
    services = [e.get("НаимТов") or "" for e in _all(root, "СведТов")]
    raw = next((n for n in numbers if contract_no and contract_key(n) == contract_key(contract_no)), None)
    if raw is None:
        raw = next((n for n, name in bases if n and "оговор" in (name + n.lower())), numbers[0] if numbers else None)
        contract = raw
    else:
        contract = contract_no
    return {
        "number": _attr(sf, "НомерДок", "НомерСчФ") or "",
        "date": _ru_date(_attr(sf, "ДатаДок", "ДатаСчФ")),
        "net": _money(_attr(total, "СтТовБезНДСВсего")),
        "vat": _money(vat_el.text.strip() if vat_el is not None and vat_el.text else None),
        "gross": _money(_attr(total, "СтТовУчНалВсего")),
        "buyer": {"inn": _attr(ul, "ИННЮЛ") or _attr(ip, "ИННФЛ") or "", "kpp": _attr(ul, "КПП") or ""},
        "contract": contract,
        "contract_1c": raw,
        # наименование услуги в строке УПД = согласованное основание (владелец 05.11.2026: «они должны идти в документы»);
        # совпало без оформления — отдаём НАШ текст (экран сравнивает строки), иначе — как в УПД
        "basis": (basis if basis and any(text_key(n) == text_key(basis) for n in services) else (services[0] if services else "")),
    }
