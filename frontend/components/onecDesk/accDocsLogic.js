/**
 * Логика страницы «Документы для бухгалтерии» — чистые функции без React.
 * Ей же пользуется сервер (порт на Python) — правила должны совпадать один в один:
 * фронт показывает, сервер повторяет те же проверки при POST /submit и отдаёт readiness в очереди.
 *
 * Время: всё считается по московскому времени (UTC+3, без переходов). Даты в контракте — ISO с +03:00.
 */
import { rub2 } from '@/lib/salesFormat';

export const MSK = 3 * 36e5;
export const SUM_TOLERANCE = 1;          // ₽: расхождение до 1 ₽ включительно — без комментария
export const WORK_DAY = { from: 9, to: 18, hours: 9 };
export const AGE_WARN_H = 9;             // ≥ 1 рабочего дня — жёлтый
export const AGE_BAD_H = 27;             // ≥ 3 рабочих дней — красный

/* ── деньги ── */
// стенд: формат денег — общий (lib/salesFormat.rub2, «1 000 000,40»); пусто — пустая строка, а не «—»: значение идёт и в поля ввода
export const money = v => (v == null || Number.isNaN(v)) ? '' : rub2(v);
/** '1 000 000,40' → 1000000.4; '' → null; мусор → NaN */
export const parseMoney = s => {
  if (s == null || String(s).trim() === '') return null;
  const v = parseFloat(String(s).replace(/[\s ]/g, '').replace(',', '.'));
  return Number.isNaN(v) ? NaN : v;
};
/** gross с НДС → { net, vat, gross } (ставка по умолчанию 22 %) */
export const splitVat = (gross, rate = 22) => { const net = Math.round(gross / (1 + rate / 100) * 100) / 100; return { net, vat: Math.round((gross - net) * 100) / 100, gross }; };

/* ── даты ── */
const DATE_RE = /^(\d{2})\.(\d{2})\.(\d{4})$/;
export const isDate = v => DATE_RE.test((v || '').trim());
/** 'дд.мм.гггг' → 20261031 (для сравнения) | null */
export const ymd = v => { const m = DATE_RE.exec((v || '').trim()); return m ? +(m[3] + m[2] + m[1]) : null; };
/** ISO → { ms, d: 'дд.мм.гггг', dm: 'дд.мм чч:мм', hm } по МСК */
export const msk = iso => {
  const ms = typeof iso === 'number' ? iso : Date.parse(iso); const t = new Date(ms + MSK);
  const p = n => String(n).padStart(2, '0');
  const d = `${p(t.getUTCDate())}.${p(t.getUTCMonth() + 1)}.${t.getUTCFullYear()}`, hm = `${p(t.getUTCHours())}:${p(t.getUTCMinutes())}`;
  return { ms, d, hm, dm: `${d.slice(0, 5)} ${hm}`, dt: `${d} ${hm}` };
};
export const isoToRuDate = iso => iso ? msk(iso).d : '';

/* ── рабочее время ── */
/**
 * Рабочие часы между a и b (мс), пн–пт 9–18 МСК.
 * holidays — ['2026-11-04', …] нерабочие; workdays — ['2026-11-01', …] рабочие выходные (переносы). Брать из производственного календаря.
 */
export function workHours(a, b, { holidays = [], workdays = [] } = {}) {
  if (!(b > a)) return 0;
  const H = new Set(holidays), W = new Set(workdays);
  let t = 0; const d0 = new Date(a + MSK); d0.setUTCHours(0, 0, 0, 0);
  for (let d = d0.getTime(); d < b + MSK; d += 864e5) {
    const key = new Date(d).toISOString().slice(0, 10), wd = new Date(d).getUTCDay();
    const working = W.has(key) || (wd !== 0 && wd !== 6 && !H.has(key)); if (!working) continue;
    const s = Math.max(a + MSK, d + WORK_DAY.from * 36e5), e = Math.min(b + MSK, d + WORK_DAY.to * 36e5); if (e > s) t += e - s;
  }
  return t / 36e5;
}
/** 0.4 → '24 мин'; 7.5 → '7 ч'; 36 → '4 р.д.'; 16.7 → '1 р.д. 7 ч' */
export const ageLabel = h => h < 1 ? `${Math.max(1, Math.round(h * 60))} мин` : h < WORK_DAY.hours ? `${Math.floor(h)} ч`
  : `${Math.floor(h / WORK_DAY.hours)} р.д.` + (Math.floor(h % WORK_DAY.hours) ? ` ${Math.floor(h % WORK_DAY.hours)} ч` : '');
export const ageTone = h => h >= AGE_BAD_H ? 'bad' : h >= AGE_WARN_H ? 'warn' : 'ok';

/** Плашка срока закрытия месяца. closeAt — ISO из настроек бухгалтерии. */
export function closeInfo(nowMs, closeAtIso, openCount, cal) {
  const left = Math.ceil(Math.round(workHours(nowMs, Date.parse(closeAtIso), cal) / WORK_DAY.hours * 10) / 10);
  const tone = left <= 1 ? 'bad' : left <= 3 ? 'warn' : 'ok';
  const word = left === 1 ? 'рабочий день' : left > 1 && left < 5 ? 'рабочих дня' : 'рабочих дней';
  return { left, tone, word, at: msk(closeAtIso).dm, openCount };
}

/* ── форма заявки ── */
export const EMPTY_FORM = { invNo: '', invDate: '', invPdf: null, updNo: '', updDate: '', net: '', vat: '', gross: '', updPdf: null, updXml: null, fromXml: false, xml: null, comment: '' };
const FILLED_KEYS = ['invNo', 'invDate', 'invPdf', 'updNo', 'updDate', 'net', 'vat', 'gross', 'updPdf', 'updXml'];
export const isStarted = f => !!f && FILLED_KEYS.some(k => f[k]);

/** Ожидаемые суммы из строк ДС */
export const expectedOf = req => {
  const net = req.lines.reduce((a, l) => a + l.net, 0), vat = req.lines.reduce((a, l) => a + l.vat, 0), gross = req.lines.reduce((a, l) => a + l.gross, 0);
  return { net: Math.round(net * 100) / 100, vat: Math.round(vat * 100) / 100, gross: Math.round(gross * 100) / 100 };
};

/** Сверка сумм УПД с ДС. Пустые поля — сверка не идёт (не «зелёная по умолчанию»). */
export function sumCheck(f, exp, tol = SUM_TOLERANCE) {
  const vals = { net: parseMoney(f.net), vat: parseMoney(f.vat), gross: parseMoney(f.gross) };
  const K = ['net', 'vat', 'gross'];
  const anyEmpty = K.some(k => vals[k] == null), allEmpty = K.every(k => vals[k] == null), badNum = K.some(k => vals[k] != null && Number.isNaN(vals[k]));
  const diff = {}; K.forEach(k => { diff[k] = vals[k] == null || Number.isNaN(vals[k]) ? null : Math.round((vals[k] - exp[k]) * 100) / 100; });
  const maxDiff = Math.max(0, ...K.map(k => Math.abs(diff[k] || 0)));
  const needComment = maxDiff > tol;
  const ok = !anyEmpty && !badNum && (!needComment || !!(f.comment || '').trim());
  const state = badNum ? 'bad' : allEmpty ? 'empty' : anyEmpty ? 'partial' : needComment ? 'diff' : 'match';
  return { vals, diff, anyEmpty, allEmpty, badNum, maxDiff, needComment, ok, state };
}

/** Сверка покупателя/договора из XML со сделкой. xml = ответ разбора (см. sampleData) */
export function xmlCheck(xml, req) {
  if (!xml) return { on: false, err: false, rows: [] };
  const rows = [['ИНН покупателя', xml.buyer && xml.buyer.inn, req.buyer.inn], ['КПП покупателя', xml.buyer && xml.buyer.kpp, req.buyer.kpp], ['договор', xml.contract, req.contract.no]]
    // стенд: согласованное основание — наименование услуги в строке УПД (владелец 05.11.2026); сервер сравнивает без оформления
    .concat(req.basis ? [['основание', xml.basis, req.basis]] : [])
    .map(([label, value, want]) => ({ label, value: value || '—', want, ok: value === want }));
  return { on: true, err: rows.some(r => !r.ok), rows };
}

/** Предупреждение по дате. periodEnd — 'дд.мм.гггг' конца периода ДС; closedUntil — 'дд.мм.гггг' последний день закрытого периода */
export function dateWarn(value, { isUpd, periodEnd, closedUntil }) {
  const d = ymd(value); if (d == null) return '';
  if (closedUntil && d <= ymd(closedUntil)) return 'период закрыт — ' + closedLabel(closedUntil);
  if (isUpd && periodEnd && d < ymd(periodEnd)) return `раньше конца периода ДС (${periodEnd})`;
  return '';
}
const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const closedLabel = d => MONTHS[+d.slice(3, 5) - 1] + ' и раньше';

/**
 * Полная оценка формы: что не хватает (блокирует), что предупреждает (не блокирует), готовность.
 * ctx: { dupInv, dupUpd — строка «M-0004 · внесено 05.11 10:02» | null; closedUntil; readOnly — архив: без предупреждений по датам }
 */
export function evaluate(req, f, ctx = {}) {
  const exp = expectedOf(req), sum = sumCheck(f, exp), xml = xmlCheck(f.updXml ? f.xml : null, req);
  const periodEnd = isoToRuDate(req.period.to);
  const invDateBad = !!f.invDate && !isDate(f.invDate), updDateBad = !!f.updDate && !isDate(f.updDate);
  const invDW = invDateBad || ctx.readOnly ? '' : dateWarn(f.invDate, { isUpd: false, periodEnd, closedUntil: ctx.closedUntil });
  const updDW = updDateBad || ctx.readOnly ? '' : dateWarn(f.updDate, { isUpd: true, periodEnd, closedUntil: ctx.closedUntil });
  const invOk = !!(f.invNo && f.invDate && !invDateBad && f.invPdf);
  const needXml = req.channel !== 'бумага';   // стенд: XML для ЭДО обязателен, кроме бумаги; канал не задан — как ЭДО (владелец 09.11.2026)
  const updOk = !!(f.updNo && f.updDate && !updDateBad && f.updPdf && (f.updXml || !needXml)) && sum.ok && !xml.err;

  const missing = []; const need = label => missing.push({ label, tone: 'need' }); const prob = (label, tone) => missing.push({ label, tone });
  if (!f.invNo) need('№ счёта'); if (!f.invDate) need('дата счёта'); else if (invDateBad) prob('дата счёта', 'bad'); if (!f.invPdf) need('PDF счёта');
  if (!f.updNo) need('№ УПД'); if (!f.updDate) need('дата УПД'); else if (updDateBad) prob('дата УПД', 'bad');
  if (sum.badNum) prob('сумма УПД', 'bad'); else if (sum.anyEmpty) need('суммы УПД');
  if (sum.needComment && !(f.comment || '').trim()) prob('комментарий к расхождению', 'warn');
  if (!f.updPdf) need('PDF УПД');
  if (needXml && !f.updXml) need('XML УПД');
  if (xml.err) prob('XML: покупатель, договор или основание не совпадает', 'bad');

  const warns = [];
  if (!req.ds_signed) warns.push('ДС не подписан');
  if (ctx.dupInv) warns.push('№ счёта уже был'); if (ctx.dupUpd) warns.push('№ УПД уже был');
  if (invDW) warns.push('дата счёта: ' + invDW); if (updDW) warns.push('дата УПД: ' + updDW);

  const ready = missing.length === 0;
  return { exp, sum, xml, invOk, updOk, invDateBad, updDateBad, invDW, updDW, missing, warns, ready,
    readiness: !isStarted(f) ? 'none' : ready ? 'ready' : 'started', periodEnd };
}

/**
 * Вид строки очереди (аудит п.2–3). readiness — из rowPips.
 *  ready → зелёный фон; selected → синяя рамка 2 px по всему контуру (border 1 px + кольцо box-shadow 1 px), без полос слева;
 *  dsWarn — готово, но ДС не подписан: метка ДС на зелёной строке залитая жёлтая (var(--warning), белый текст).
 */
export const rowLook = (req, readiness, selected) => {
  const ready = req.status === 'wait' && readiness === 'ready';
  return { ready, selected, dsWarn: ready && !req.ds_signed };
};

/** Аудит п.4: текст услуги совпадает с основанием — второй раз абзац не показываем */
export const sameAsBasis = (service, basis) => (service || '').trim().replace(/\s+/g, ' ') === (basis || '').trim().replace(/\s+/g, ' ');

/** Аудит п.8: подсказка под датой — только для УПД (не раньше конца периода); у счёта пусто */
export const dateHint = (isUpd, periodEnd) => isUpd && periodEnd ? `не раньше ${periodEnd}` : '';

/**
 * Прогноз «Ещё в пути» (полоса срока закрытия, вторая строка): мастер-сделки периода close_month, по которым процесс запущен
 * (этап сделки — сверка / согласование), а заявки на документы ещё нет. Только для информации: в очередь не попадают, действий нет.
 * items: [{ code, buyer, brand, account, stage: 'сверка' | 'согласование', gross, stage_since: ISO }]
 * Сортировка: сначала согласование (ближе к заявке), внутри — дольше в этапе. «в этапе» — в рабочих часах; ≥ 3 р.д. — жёлтым.
 */
export const STAGE_ORDER = ['согласование', 'сверка'];
export function forecastOf(na, nowMs, cal) {
  const items = (na && na.items) || [];
  const plural = n => n % 10 === 1 && n % 100 !== 11 ? 'сделка' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'сделки' : 'сделок';
  return {
    on: items.length > 0, total: items.length, totalLabel: `${items.length} ${plural(items.length)}`,
    gross: Math.round(items.reduce((a, x) => a + x.gross, 0) * 100) / 100,
    by: STAGE_ORDER.map(stage => ({ stage, n: items.filter(x => x.stage === stage).length })).filter(x => x.n).reverse(),
    items: items.slice().sort((a, b) => STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage) || Date.parse(a.stage_since) - Date.parse(b.stage_since))
      .map(x => { const h = workHours(Date.parse(x.stage_since), nowMs, cal);
        return { ...x, inStage: (x.stage === 'согласование' ? 'у клиента ' : 'в работе ') + (h < WORK_DAY.hours ? Math.max(1, Math.floor(h)) + ' ч' : Math.floor(h / WORK_DAY.hours) + ' р.д.'), late: h >= AGE_BAD_H }; }),
  };
}

/**
 * Вкладка «Ждут сканов»: документы внесены, а ДС так и не подписан (внесли с предупреждением «ДС не подписан») — ждём скан подписанного ДС.
 * Скан прикладывает бухгалтер или аккаунт; после этого ds_signed = true, ds_scan_url заполнен, заявка уходит из вкладки.
 */
export const waitsScan = r => r.status === 'done' && !r.ds_signed;
export const inTab = (r, tab) => tab === 'all' ? true : tab === 'scan' ? waitsScan(r) : r.status === tab;

/** Метки строки очереди */
export function rowPips(req, f, seen) {
  const ev = req.status === 'wait' ? evaluate(req, f || EMPTY_FORM) : null, rd = ev ? ev.readiness : 'none';
  const out = [];
  if (req.status === 'wait' && req.resent && !seen) out.push({ kind: 'flag', label: 'исправлено', title: 'Аккаунт исправил и прислал повторно' });
  if ((req.thread || []).some(t => t.from_account && t.unread) && !seen) out.push({ kind: 'flag', label: 'ответ', title: 'Аккаунт ответил в обсуждении' });
  out.push({ kind: req.ds_signed ? 'ok' : 'warn', label: 'ДС', title: req.ds_signed ? 'ДС подписан' : 'ДС создан, но не подписан' });
  if (rd !== 'none') {
    out.push({ kind: ev.invOk ? 'ok' : 'off', label: 'СЧЁТ', title: ev.invOk ? 'Счёт заполнен' : 'Счёт не заполнен' });
    out.push({ kind: ev.updOk ? 'ok' : 'off', label: 'УПД', title: ev.updOk ? 'УПД заполнен' : 'УПД не заполнен' });
  }
  if (req.status === 'done' && req.edo) out.push(edoPip(req.edo));   // стенд: до подключения ЭДО метки нет (владелец 09.11.2026: «убери, я это и так знаю»)
  return { pips: out, readiness: rd };
}

/** ЭДО: null — не подключено. Статусы — после подключения Диадок/СБИС. */
export const EDO = {
  queued: { label: 'ЭДО · в очереди', tone: 'info' }, sent: { label: 'ЭДО · отправлен', tone: 'info' }, delivered: { label: 'ЭДО · доставлен', tone: 'info' },
  signed: { label: 'ЭДО · подписан', tone: 'ok' }, rejected: { label: 'ЭДО · отклонён', tone: 'bad' }, error: { label: 'ЭДО · ошибка', tone: 'bad' },
};
export const edoPip = edo => !edo ? { kind: 'edo-off', label: 'ЭДО', title: 'ЭДО не подключено — статус появится после подключения Диадок / СБИС' }
  : { kind: 'edo-' + EDO[edo.status].tone, label: 'ЭДО', title: EDO[edo.status].label + (edo.reason ? ' — ' + edo.reason : '') };

/** Поиск по всем заявкам */
export const matches = (req, q) => [req.buyer.name, req.buyer.inn, req.code, req.annex.short, req.contract.no, req.brand].join(' ').toLowerCase().includes(q.trim().toLowerCase());

/** Сортировка: ждут — раньше незакрытый период, потом дольше ждут; внесённые — новые сверху */
export const sortQueue = list => list.slice().sort((a, b) => {
  if (a.status === 'done' && b.status === 'done') return Date.parse(b.done.at) - Date.parse(a.done.at);
  if ((a.status === 'done') !== (b.status === 'done')) return a.status === 'done' ? 1 : -1;
  return Date.parse(a.period.to) - Date.parse(b.period.to) || Date.parse(a.since) - Date.parse(b.since);
});

/** Текст «скопировать всё одним блоком» */
export const copyAllText = req => {
  const exp = expectedOf(req);
  return [`ИНН покупателя: ${req.buyer.inn}`, `Договор № ${req.contract.no} от ${isoToRuDate(req.contract.date)}`, `Основание: ${req.basis}`,
    ...req.lines.map(l => `Услуга: ${l.service}`), `Без НДС: ${money(exp.net)}`, `НДС ${req.lines[0].vat_rate} %: ${money(exp.vat)}`, `С НДС: ${money(exp.gross)}`].join('\n');
};
