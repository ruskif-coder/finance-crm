/**
 * Премодерация — чистые правила без React. Сервер повторяет то же самое в backend_premod_checks.py
 * (автопроверки считает он при синхронизации; фронт пересчитывает только то, что зависит от выбора галочек).
 */

import { fmtDayOfMoment, fmtTime } from '@/lib/dates';

/* ── время ── */
export const AGE_WARN_H = 4;     // ждёт у SSP > 4 ч — жёлтый
export const AGE_BAD_H = 24;     // > суток — красный
/* Московское время — через lib/dates (гейт check-dates), а не своим сдвигом на +3 ч */
export const msk = iso => ({ d: fmtDayOfMoment(iso), hm: fmtTime(iso), get dm() { return this.d + ' ' + this.hm; } });
/** Ожидание считается от создания заявки в SSP (самая ранняя заявка пакета), не от нашей синхронизации */
export function ageOf(pkg, nowIso) {
  const first = Math.min(...pkg.requests.map(r => Date.parse(r.created_at)));
  const h = (Date.parse(nowIso) - first) / 36e5;
  const label = h < 1 ? `${Math.max(1, Math.round(h * 60))} мин` : h < 24 ? `${Math.floor(h)} ч` : `${Math.floor(h / 24)} дн ${Math.floor(h % 24)} ч`;
  return { h, label, tone: h >= AGE_BAD_H ? 'bad' : h >= AGE_WARN_H ? 'warn' : 'ok', since: new Date(first).toISOString() };
}

export const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 12 || h > 14) ? b : c; };

/* ── посадочная: разбор без перехода (переход засчитал бы клик рекламодателю) ── */
const DEST_RE = /[?&](?:url|to|redirect)=([^&]+)/;
export function parseLanding(url) {
  const host = url.replace(/^https?:\/\//, '').split('/')[0];
  const erid = (/[?&]erid=([^&]+)/.exec(url) || [])[1] || null;
  const dm = DEST_RE.exec(url);
  let dest = null; try { dest = dm ? decodeURIComponent(dm[1]).replace(/^https?:\/\//, '').replace(/\/$/, '') : null; } catch (e) { dest = null; }
  /* куски для подсветки в полной ссылке: kind 'erid' | 'dest' | null */
  let parts = [{ s: url, kind: null }];
  [[/erid=[^&]+/, 'erid'], [DEST_RE, 'dest']].forEach(([re, kind]) => { parts = parts.flatMap(x => { if (x.kind) return [x]; const m = re.exec(x.s); if (!m) return [x];
    return [{ s: x.s.slice(0, m.index), kind: null }, { s: m[0], kind }, { s: x.s.slice(m.index + m[0].length), kind: null }].filter(y => y.s); }); });
  return { host, erid, dest, parts };
}

/** Своя ошибка заявки: ЕРИД в ссылке клика или в разметке не от этой заявки. Сверку делает сервер
 *  (app/premod/checks.py — на любой глубине редиректов), здесь только его вывод. */
export const requestError = r => ({ bad: !!r.err, linkErid: r.link_erid, text: r.err || '' });
/** По умолчанию: при нескольких заявках заявки со своими ошибками не отмечены к одобрению */
export const defaultChecked = pkg => Object.fromEntries(pkg.requests.map(r => [r.uuid, pkg.requests.length > 1 ? !requestError(r).bad : true]));

/* ── автопроверки пакета ──
 * Считает сервер (app/premod/package_checks.py — порт правил макета с решением владельца 08.11.2026:
 * текст картинки не распознаём, отсутствие текста — «посмотреть», а не «нарушение»). Здесь их не повторяем:
 * вторая копия правил разошлась бы с первой.
 * state: 'ok' | 'bad' (нарушение) | 'warn' (посмотреть) | 'na' (не применимо / нечем проверить) | 'off' (позже). */
export const checksOf = pkg => pkg.checks || [];

/** Итог по пакету с учётом галочек: пакетные нарушения (кроме ЕРИД) касаются всех заявок, ЕРИД — только отмеченных ошибочных */
export function verdictOf(pkg, checks, checked) {
  const nBad = checks.filter(c => c.state === 'bad').length, nWarn = checks.filter(c => c.state === 'warn').length;
  const pkgBad = checks.filter(c => c.state === 'bad' && c.key !== 'erid').length;
  const badChecked = pkg.requests.filter(r => checked[r.uuid] && requestError(r).bad).length;
  const nChecked = pkg.requests.filter(r => checked[r.uuid]).length;
  return { nBad, nWarn, pkgBad, badChecked, nChecked, risky: pkgBad > 0 || badChecked > 0 };
}
export const isClean = (pkg, adv) => !checksOf(pkg, adv).some(c => c.state === 'bad');

/* ── доверие: сколько повторных решений совпало с прежним (для будущего автоодобрения) ── */
export const TRUST_MIN = 10;
export const trustOf = adv => { const { same = 0, total = 0 } = adv.trust || {}; return { same, total, candidate: total >= TRUST_MIN && same === total }; };

/* ── очередь ── */
export const sspWaits = (pkg, acc) => pkg.requests.some(r => r.ssp_status === 'ждёт' && (acc == null || String(r.acc) === String(acc)));
export const placeName = (places, acc) => (places[acc] && places[acc].name) || 'учётка ' + acc;
export function sortQueue(pkgs) {   // у SSP ждут — первыми; дальше дольше ждут
  const first = p => Math.min(...p.requests.map(r => Date.parse(r.created_at)));
  return pkgs.slice().sort((a, b) => (sspWaits(b) - sspWaits(a)) || (first(a) - first(b)));
}
/** mode: 'adv' — группа = рекламодатель; 'place' — группа = площадка SSP, пакет попадает в каждую свою площадку */
export function groupQueue(sorted, mode) {
  if (mode === 'place') {
    const by = new Map(); sorted.forEach(p => p.requests.forEach(r => { const k = String(r.acc); if (!by.has(k)) by.set(k, []); const a = by.get(k); if (!a.includes(p)) a.push(p); }));
    const waitN = (k, ps) => ps.filter(p => sspWaits(p, k)).length;
    return [...by.entries()].sort((x, y) => (waitN(y[0], y[1]) - waitN(x[0], x[1])) || (y[1].length - x[1].length)).map(([key, items]) => ({ key, kind: 'place', items }));
  }
  const by = new Map(); sorted.forEach(p => { if (!by.has(p.advertiser)) by.set(p.advertiser, []); by.get(p.advertiser).push(p); });
  return [...by.entries()].map(([key, items]) => ({ key, kind: 'adv', items }));
}
export const matches = (pkg, adv, q) => [adv.short, adv.name, adv.inn, pkg.id, ...pkg.requests.flatMap(r => [r.erid, r.crid || ''])].join(' ').toLowerCase().includes(q.trim().toLowerCase());
/** Фильтры шапки */
export const FILTERS = [['wait', 'Ждут', 'warning'], ['changed', 'Изменились', 'accent'], ['approved', 'Одобрены', 'income'], ['declined', 'Отклонены', 'danger']];

/* ── причины отказа: справочник SSP; подсказки по найденным нарушениям ── */
/* Коды макета (no_mark, erid_mismatch…) у SSP другие — пункты дерева с числовыми id. Какая проверка каким
   пунктом отказа закрывается — решение владельца; пока подсказок нет. */
export const SUGGEST_BY_CHECK = {};
