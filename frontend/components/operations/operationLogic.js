/**
 * Боковая панель операции — правила отображения (без React). Всё считается из ответа GET /api/operations/{id}/context.
 */
import { fmtDate, fmtDayTime } from '@/lib/dates';
import { rub2 } from '@/lib/salesFormat';

// стенд: деньги — общим `rub2` (те же 2 знака, свой форматтер в странице правилом запрещён); минус — типографский, как в хендоффе
export const money = v => v == null ? '—' : rub2(Number(v)).replace('-', '−');
// стенд: даты — общими помощниками `lib/dates` (гейт check-dates: время с сервера в обход них не разбирается). У нас день
// календарный приходит без времени (`fmtDate`), момент — с поясом (`fmtDayTime` по Москве; « · » убран — в колонку истории 96 px
// «09.11 · 14:00» не влезает, у хендоффа «09.11 14:00»).
export const date = iso => iso ? fmtDate(iso, '') : '';
export const dateTime = iso => iso ? fmtDayTime(iso, '').replace(' · ', ' ') : '';
const days = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 864e5);
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 12 || h > 14) ? b : c; };

/** Оплачено — по всей цепочке траншей, а не по одной строке */
export const paidOf = op => (op.payments || []).reduce((a, p) => a + p.amount, 0);

/**
 * Состояние для шапки и строки «что дальше».
 * tone: need | info | ok | bad | warn. action: null | { key, label, title }
 */
export function stateOf(op, nowIso) {
  const total = op.amount, paid = paidOf(op), rest = Math.round((total - paid) * 100) / 100;
  const diff = op.upd && op.upd.amount != null && op.ds ? Math.round((op.upd.amount - op.ds.amount) * 100) / 100 : 0;
  const isPlan = op.kind === 'plan_income';
  const n = (op.payments || []).length, last = n ? op.payments[n - 1] : null;
  if (rest <= 0.005 && paid > 0) return { status: op.direction === 'out' ? 'расход · оплачено' : 'оплачено', tone: 'ok',
    next: `Оплачено полностью ${date(last.at)}`, sub: op.due_at ? `${n} ${plural(n, 'платёж', 'платежа', 'платежей')} · за ${days(last.at, op.due_at)} дн. до срока` : `${n} ${plural(n, 'платёж', 'платежа', 'платежей')}`, action: null };
  if (isPlan && Math.abs(diff) > 0.005) return { status: 'план поступлений', tone: 'warn',
    next: `Сумма в 1С ${diff > 0 ? 'больше' : 'меньше'} ДС на ${money(Math.abs(diff))}`, sub: 'бухгалтер объяснил расхождение · проверьте, какая сумма верная',
    action: { key: 'open_package', label: 'Пакет у бухгалтера ↗', title: `Открыть заявку ${op.package.code} на странице «Документы для бухгалтерии»` } };
  if (isPlan && op.due_at && Date.parse(nowIso) > Date.parse(op.due_at)) return { status: 'просрочено', tone: 'bad',
    next: `Просрочено на ${days(op.due_at, nowIso)} ${plural(days(op.due_at, nowIso), 'день', 'дня', 'дней')}`, sub: `срок был ${date(op.due_at)} · ${money(rest)} не пришло`,
    // «Напомнить аккаунту» — новое событие, до согласования кнопки нет (BUILD.md хендоффа)
    action: null };
  if (paid > 0) return { status: 'частично оплачено', tone: 'info', next: `Оплачено ${money(paid)} из ${money(total)}`, sub: `осталось ${money(rest)}${op.due_at ? ' до ' + date(op.due_at) : ''}`, action: null };
  if (isPlan) { const left = days(nowIso, op.due_at);
    return { status: 'план поступлений', tone: 'need', next: `Ждём оплату до ${date(op.due_at)}`, sub: `осталось ${left} ${plural(left, 'день', 'дня', 'дней')} · ${op.due_rule}`, action: null }; }
  return { status: op.status_label, tone: 'need', next: op.status_label, sub: '', action: null };
}

/** Блоки, которые показываются: пустой блок не рисуется */
export const blocksOf = op => ({ origin: !!op.package, docs: !!op.upd, money: true, parties: true, history: true });
