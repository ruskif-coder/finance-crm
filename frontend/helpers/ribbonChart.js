/**
 * ribbonChart.js — расчёт данных для дивергентного риббон-графика ДДС.
 * Catmull-Rom сплайн интерполирует N помесячных точек в SUB колонок —
 * получается плавная огибающая кривая (поступления вверх, списания вниз).
 *
 * Адаптация helper-кода из "Модернизация финансового сервиса/frontend/helpers/ribbonChart.js":
 *  - maxVal больше не хардкод (42) — считается от реальных данных через niceMax();
 *  - подписи месяцев берутся из реальных строк периода 'YYYY-MM', а не фиксированного Июл—Июн;
 *  - короткие входные массивы (n<2) паддятся, чтобы избежать NaN в catmullRom.
 *
 * Использование:
 *   import { buildDivBars, buildYLabels, niceMax, buildMonthLabels } from '../helpers/ribbonChart';
 *   const maxVal = niceMax(Math.max(...incomes, ...expenses, 1));
 *   const bars   = buildDivBars(monthly, { maxVal });   // [{income, expense}, ...]
 *   const labels = buildYLabels(maxVal);
 */

const DEFAULTS = {
  height: 400,   // px, высота контейнера графика
  arm:    182,   // px, максимальная длина бара от нуля (в каждую сторону)
  sub:    48,    // кол-во капсул (чем больше — плавнее)
};

// ── Защита от вырожденных входов ───────────────────────────────────
// Catmull-Rom обращается к arr[i-1]/arr[i+2] — на массиве из 0-1 элементов
// это даёт undefined → NaN. Паддим до минимум 2 точек.
function padArray(arr) {
  if (!arr || arr.length === 0) return [0, 0];
  if (arr.length === 1) return [arr[0], arr[0]];
  return arr;
}

// ── Catmull-Rom интерполяция ──────────────────────────────────────
function catmullRom(arr, t) {
  const n = arr.length;
  const x = t * (n - 1);
  const i = Math.min(n - 2, Math.floor(x));
  const f = x - i;
  const p0 = arr[Math.max(0, i - 1)];
  const p1 = arr[i];
  const p2 = arr[i + 1];
  const p3 = arr[Math.min(n - 1, i + 2)];
  return 0.5 * (
    (2 * p1) +
    (-p0 + p2) * f +
    (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f +
    (-p0 + 3 * p1 - 3 * p2 + p3) * f * f * f
  );
}

/**
 * niceMax(value) — округляет вверх до "красивого" числа (1/2/5 × 10^n) с запасом 10%.
 * Заменяет хардкод maxVal=42 из концепта — шкала подстраивается под реальные обороты компании.
 */
export function niceMax(value) {
  if (!value || value <= 0 || !isFinite(value)) return 1;
  const v = value * 1.1;
  const exp = Math.floor(Math.log10(v));
  const base = v / Math.pow(10, exp);
  let niceBase;
  if (base <= 1) niceBase = 1;
  else if (base <= 2) niceBase = 2;
  else if (base <= 5) niceBase = 5;
  else niceBase = 10;
  return niceBase * Math.pow(10, exp);
}

/**
 * buildDivBars(monthlyData, options?)
 *
 * @param {Array<{income: number, expense: number}>} monthlyData — помесячные суммы (₽)
 * @param {object} options — { height, arm, sub, maxVal } — переопределение DEFAULTS;
 *   maxVal обязателен на практике (см. niceMax), иначе берётся максимум из самих данных.
 * @returns {Array<{incTop, incH, expTop, expH}>} — абсолютные px для каждой капсулы
 */
export function buildDivBars(monthlyData, options = {}) {
  const { height, arm, sub } = { ...DEFAULTS, ...options };
  const center = Math.round(height / 2);

  const incArr = padArray((monthlyData ?? []).map(d => d.income ?? 0));
  const expArr = padArray((monthlyData ?? []).map(d => d.expense ?? 0));
  const maxVal = options.maxVal ?? niceMax(Math.max(...incArr, ...expArr, 1));

  return Array.from({ length: sub }, (_, i) => {
    const t   = sub > 1 ? i / (sub - 1) : 0;
    const inc = Math.max(0, catmullRom(incArr, t));
    const exp = Math.max(0, catmullRom(expArr, t));
    const ih  = Math.round(Math.min(inc, maxVal) / maxVal * arm);
    const eh  = Math.round(Math.min(exp, maxVal) / maxVal * arm);
    return { incTop: center - ih, incH: ih, expTop: center, expH: eh };
  });
}

/**
 * Метки оси Y, симметричные вокруг нуля, под заданный maxVal (₽).
 */
export function buildYLabels(maxVal, options = {}) {
  const { height, arm } = { ...DEFAULTS, ...options };
  const center = Math.round(height / 2);
  const mv = maxVal && isFinite(maxVal) && maxVal > 0 ? maxVal : 1;
  return [
    { v: formatAxisValue(mv),     y: Math.round(center - arm) },
    { v: formatAxisValue(mv / 2), y: Math.round(center - arm / 2) },
    { v: '0',                     y: center },
    { v: formatAxisValue(mv / 2), y: Math.round(center + arm / 2) },
    { v: formatAxisValue(mv),     y: Math.round(center + arm) },
  ];
}

function formatAxisValue(v) {
  if (v >= 1_000_000) {
    const m = v / 1_000_000;
    return (Number.isInteger(m) ? m : m.toFixed(1)).toString().replace('.', ',') + ' М';
  }
  if (v >= 1000) return Math.round(v / 1000) + ' тыс';
  return Math.round(v).toString();
}

// ── Подписи месяцев из реальных периодов ('YYYY-MM') ───────────────
const MONTH_SHORT = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];

export function periodToLabel(period) {
  if (!period || typeof period !== 'string') return '';
  const m = period.match(/^(\d{4})-(\d{2})$/);
  if (m) {
    const idx = parseInt(m[2], 10) - 1;
    return MONTH_SHORT[idx] ?? period;
  }
  return period.length > 7 ? period.slice(0, 7) : period; // напр. 'Q1 2026' — оставляем как есть
}

export function buildMonthLabels(periods) {
  return (periods ?? []).map(periodToLabel);
}
