/**
 * ribbonChart.js — расчёт данных для дивергентного риббон-графика.
 * Catmull-Rom сплайн интерполирует 12 месячных точек в SUB колонок —
 * получается плавная огибающая кривая.
 *
 * Использование:
 *   import { buildDivBars, Y_LABELS, MONTH_LABELS } from '../helpers/ribbonChart';
 *   const bars = buildDivBars(cashflowByMonth); // [{income, expense}, ...]
 */

// ── Параметры по умолчанию ────────────────────────────────────────
const DEFAULTS = {
  height:  400,   // px, высота контейнера графика
  arm:     182,   // px, максимальная длина бара от нуля (в каждую сторону)
  maxVal:  42,    // млн — максимум по шкале
  sub:     48,    // кол-во капсул (чем больше — плавнее)
};

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
 * buildDivBars(monthlyData, options?)
 *
 * @param {Array<{income: number, expense: number}>} monthlyData  — 12 элементов (млн ₽)
 * @param {object} options — переопределение DEFAULTS
 * @returns {Array<{incTop, incH, expTop, expH}>}  — абсолютные px для каждой капсулы
 */
export function buildDivBars(monthlyData, options = {}) {
  const { height, arm, maxVal, sub } = { ...DEFAULTS, ...options };
  const center = Math.round(height / 2);

  const incArr = monthlyData.map(d => d.income  ?? 0);
  const expArr = monthlyData.map(d => d.expense ?? 0);

  return Array.from({ length: sub }, (_, i) => {
    const t   = i / (sub - 1);
    const inc = Math.max(0, catmullRom(incArr, t));
    const exp = Math.max(0, catmullRom(expArr, t));
    const ih  = Math.round(Math.min(inc, maxVal) / maxVal * arm);
    const eh  = Math.round(Math.min(exp, maxVal) / maxVal * arm);
    return { incTop: center - ih, incH: ih, expTop: center, expH: eh };
  });
}

/**
 * Метки оси Y для шкалы ±40 М.
 * y — абсолютная позиция в px (при height=400, arm=182, maxVal=42).
 */
export function buildYLabels(options = {}) {
  const { height, arm, maxVal } = { ...DEFAULTS, ...options };
  const center = Math.round(height / 2);
  const scale  = arm / maxVal;
  return [
    { v: `${maxVal} М`, y: Math.round(center - arm) },
    { v: `${Math.round(maxVal / 2)} М`, y: Math.round(center - arm / 2) },
    { v: '0',           y: center },
    { v: `${Math.round(maxVal / 2)} М`, y: Math.round(center + arm / 2) },
    { v: `${maxVal} М`, y: Math.round(center + arm) },
  ];
}

export const MONTH_LABELS = ['Июл','Авг','Сен','Окт','Ноя','Дек','Янв','Фев','Мар','Апр','Май','Июн'];
