/**
 * dashboard.js — страница ДДС (Движение денежных средств).
 * Заменяет предыдущий dashboard.js целиком.
 * Структура: KPI → Риббон-график + Банки → Накопительный остаток.
 */
import { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import axios from 'axios';
import Navbar, { getPermissions, can } from '../components/Navbar';
import { buildDivBars, buildYLabels, MONTH_LABELS } from '../helpers/ribbonChart';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, defs, linearGradient, stop } from 'recharts';

axios.defaults.baseURL = 'http://localhost:8000/api';

// ── Цвета банков ──────────────────────────────────────────────────
const BANK_STYLES = {
  'АльфаБанк':  { color: 'var(--bank-alfa)' },
  'ОПТ Банк':   { color: 'var(--bank-opt)'  },
  'Совкомбанк': { color: 'var(--bank-sovkom)'},
  'Наличные':   { color: 'var(--bank-cash)' },
};
const bankColor = (name) => BANK_STYLES[name]?.color ?? 'var(--text-faint)';

// ── Форматирование ─────────────────────────────────────────────────
const fmt   = (n) => n == null ? '—' : Number(n).toLocaleString('ru-RU');
const fmtM  = (n) => n == null ? '—' : (Number(n) / 1_000_000).toFixed(2).replace('.', ',') + ' М';

// ── Стили компонентов ──────────────────────────────────────────────
const card = (extra = {}) => ({
  background:   'var(--bg-card)',
  borderRadius: 'var(--radius-card)',
  padding:      '20px 22px',
  boxShadow:    'var(--shadow-card)',
  ...extra,
});

const kpiCard = () => ({
  ...card(),
  flex: 1,
});

const badge = (color) => ({
  display:       'inline-flex',
  alignItems:    'center',
  gap:           6,
  padding:       '4px 10px',
  borderRadius:  'var(--radius-badge)',
  background:    'var(--bg-subtle)',
  color:         'var(--text-secondary)',
  fontSize:      10.5,
  fontWeight:    600,
  whiteSpace:    'nowrap',
});

// ── Компонент ──────────────────────────────────────────────────────
export default function Dashboard() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary]   = useState(null);   // /api/dashboard/summary
  const [monthly, setMonthly]   = useState([]);     // /api/dashboard/monthly  [{month,income,expense}]
  const [banks,   setBanks]     = useState([]);     // /api/dashboard/banks
  const [cumulative, setCumulative] = useState([]); // /api/dashboard/cumulative [{month,balance}]
  const [period, setPeriod]     = useState('period'); // 'period' | 'date'
  const [bankFilter, setBankFilter] = useState('all');

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/login'); return; }
    const perms = getPermissions();
    if (!can(perms, 'dashboard')) { router.push('/login'); return; }

    const headers = { Authorization: `Bearer ${token}` };
    Promise.all([
      axios.get('/dashboard/summary', { headers }),
      axios.get('/dashboard/monthly',    { headers }),
      axios.get('/dashboard/banks',      { headers }),
      axios.get('/dashboard/cumulative', { headers }),
    ]).then(([s, m, b, c]) => {
      setSummary(s.data);
      setMonthly(m.data);
      setBanks(b.data);
      setCumulative(c.data);
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const divBars   = buildDivBars(monthly.length ? monthly : Array(12).fill({ income: 0, expense: 0 }));
  const yLabels   = buildYLabels();

  if (loading) return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar />
      <div style={{ paddingTop: 'var(--navbar-h)', display: 'flex', alignItems: 'center',
        justifyContent: 'center', height: 'calc(100vh - var(--navbar-h))',
        color: 'var(--text-muted)', fontSize: 15 }}>Загрузка…</div>
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Navbar />
      <div style={{ paddingTop: 'var(--navbar-h)' }}>
        <div style={{ maxWidth: 1440, margin: '0 auto', padding: '26px 30px' }}>

          {/* ── Заголовок + фильтры ── */}
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 22 }}>
            <div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 500 }}>
                Отчёт · {summary?.period_label ?? ''}
              </div>
              <h1 style={{ margin: '6px 0 0', fontSize: 28, fontWeight: 300,
                color: 'var(--text-primary)', letterSpacing: '-.02em' }}>
                Движение <b style={{ fontWeight: 800 }}>денежных средств</b>
              </h1>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              {/* Переключатель период/дата */}
              <div style={{ display: 'flex', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                borderRadius: 12, padding: 4 }}>
                {['period','date'].map(v => (
                  <div key={v} onClick={() => setPeriod(v)} style={{
                    padding: '7px 14px', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 500,
                    background: period === v ? 'var(--text-primary)' : 'transparent',
                    color:      period === v ? '#fff'                : 'var(--text-secondary)',
                    transition: 'all .15s',
                  }}>{ v === 'period' ? 'По периоду' : 'По дате' }</div>
                ))}
              </div>
              <select value={bankFilter} onChange={e => setBankFilter(e.target.value)} style={{
                padding: '11px 16px', borderRadius: 12, background: 'var(--bg-card)',
                border: '1px solid var(--border-card)', fontSize: 13,
                color: 'var(--text-secondary)', fontWeight: 500, cursor: 'pointer',
              }}>
                <option value="all">Все банки</option>
                {banks.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
              </select>
            </div>
          </div>

          {/* ── KPI-полоса ── */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            {[
              { label: 'Актуальный баланс',  val: fmt(summary?.actual_balance) + ' ₽', sub: 'На счетах сегодня', subColor: 'var(--income)' },
              { label: 'Прогнозный баланс',  val: fmt(summary?.forecast_balance) + ' ₽', sub: `+${fmtM(summary?.total_income)} · −${fmtM(summary?.total_expense)}`, subColor: 'var(--text-muted)' },
              { label: 'План поступлений',   val: fmt(summary?.total_income) + ' ₽', valColor: 'var(--income)', sub: `${summary?.income_count ?? 0} операций` },
              { label: 'План расходов',      val: fmt(summary?.total_expense) + ' ₽', valColor: 'var(--expense)', sub: 'К списанию' },
            ].map((k, i) => (
              <div key={i} style={kpiCard()}>
                <div style={{ fontSize: 12.5, color: 'var(--text-muted)', fontWeight: 500 }}>{k.label}</div>
                <div style={{ fontSize: 27, fontWeight: 700, marginTop: 9, letterSpacing: '-.01em',
                  fontVariantNumeric: 'tabular-nums', color: k.valColor ?? 'var(--text-primary)' }}>{k.val}</div>
                <div style={{ fontSize: 12, marginTop: 7, fontWeight: 500, color: k.subColor ?? 'var(--text-muted)' }}>{k.sub}</div>
              </div>
            ))}
          </div>

          {/* ── График + Банки ── */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 16, alignItems: 'stretch' }}>

            {/* Риббон-график */}
            <div style={{ ...card(), flex: 1, padding: '22px 26px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                  Движение денег по месяцам
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {[['var(--ribbon-income-from)','Поступления'],['var(--ribbon-expense-to)','Списания']].map(([c,l]) => (
                    <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ width: 10, height: 10, borderRadius: 3, background: c }} />{l}
                    </span>
                  ))}
                </div>
              </div>

              {/* Холст графика */}
              <div style={{ position: 'relative', height: 400, paddingLeft: 54 }}>
                {/* Метки оси Y */}
                {yLabels.map(l => (
                  <div key={l.y} style={{ position: 'absolute', left: 0, top: l.y,
                    transform: 'translateY(-7px)', fontSize: 11,
                    color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums' }}>{l.v}</div>
                ))}

                {/* Область с барами */}
                <div style={{ position: 'relative', height: '100%', borderLeft: '1px solid var(--border-inner)' }}>
                  {/* Горизонтальные сетки */}
                  {yLabels.map(l => (
                    <div key={l.y} style={{ position: 'absolute', left: 0, right: 0,
                      top: l.y, height: 1, background: 'var(--border-inner)' }} />
                  ))}
                  {/* Нулевая линия */}
                  <div style={{ position: 'absolute', left: 0, right: 0, top: 200, height: 2, background: '#D7DCEA' }} />

                  {/* Капсулы */}
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', gap: 2, padding: '0 10px' }}>
                    {divBars.map((bar, i) => (
                      <div key={i} style={{ flex: 1, position: 'relative', height: '100%' }}>
                        {bar.incH > 0 && (
                          <div style={{
                            position: 'absolute', left: '50%', transform: 'translateX(-50%)',
                            width: 11, top: bar.incTop, height: bar.incH, borderRadius: 6,
                            background: 'linear-gradient(180deg, var(--ribbon-income-from), var(--ribbon-income-mid), var(--ribbon-income-to))',
                          }} />
                        )}
                        {bar.expH > 0 && (
                          <div style={{
                            position: 'absolute', left: '50%', transform: 'translateX(-50%)',
                            width: 11, top: bar.expTop, height: bar.expH, borderRadius: 6,
                            background: 'linear-gradient(180deg, var(--ribbon-expense-from), var(--ribbon-expense-to))',
                          }} />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Метки месяцев */}
              <div style={{ display: 'flex', justifyContent: 'space-between',
                padding: '10px 10px 0 54px', fontSize: 10.5, color: 'var(--text-faint)' }}>
                {MONTH_LABELS.map(m => <span key={m}>{m}</span>)}
              </div>
            </div>

            {/* Банки — плашки */}
            <div style={{ width: 330, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {banks.map(b => (
                <div key={b.name} style={{
                  ...card({ padding: '16px 20px', borderRadius: 'var(--radius-card-sm)' }),
                  flex: 1, borderLeft: `3px solid ${bankColor(b.name)}`,
                  display: 'flex', flexDirection: 'column', justifyContent: 'center',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--text-primary)' }}>{b.name}</span>
                    <span style={{ fontSize: 18, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                      color: bankColor(b.name) }}>{fmt(b.balance)} ₽</span>
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginTop: 9, fontSize: 11.5, color: 'var(--text-muted)' }}>
                    <span>↓ {fmtM(b.income_sum)}</span>
                    <span>↑ {fmtM(b.expense_sum)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Накопительный остаток ── */}
          <div style={card({ padding: '22px 24px 14px' })}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
              Накопительный остаток
            </div>
            <ResponsiveContainer width="100%" height={150}>
              <AreaChart data={cumulative} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="var(--accent)" stopOpacity={0.20} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" tick={{ fontSize: 10.5, fill: 'var(--text-faint)' }}
                  axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                    borderRadius: 10, fontSize: 12, color: 'var(--text-primary)' }}
                  formatter={(v) => [fmt(v) + ' ₽', 'Остаток']}
                />
                <Area dataKey="balance" stroke="var(--accent)" strokeWidth={2.5}
                  fill="url(#areaGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

        </div>
      </div>
    </div>
  );
}
