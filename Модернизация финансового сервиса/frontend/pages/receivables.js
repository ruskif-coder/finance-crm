/**
 * receivables.js — страница Дебиторской задолженности.
 * Заменяет предыдущий receivables.js целиком.
 * Структура: KPI → Карточки статуса → Фильтры → Таблица должников.
 */
import { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import axios from 'axios';
import Navbar, { getPermissions, can } from '../components/Navbar';

axios.defaults.baseURL = 'http://localhost:8000/api';

// ── Форматирование ────────────────────────────────────────────────
const fmt  = (n) => n == null ? '—' : Number(n).toLocaleString('ru-RU');
const fmtM = (n) => n == null ? '—' : (Number(n) / 1_000_000).toFixed(2).replace('.', ',') + ' М';

// ── Конфигурация карточек-статусов ────────────────────────────────
const AGING_CARDS = [
  { key: 'overdue_sum',  label: 'Просрочено',            dot: 'var(--dot-overdue)',    countKey: 'overdue_count'  },
  { key: 'current_sum',  label: 'Текущая задолженность', dot: 'var(--dot-current-dz)', countKey: 'current_count'  },
  { key: 'plan_sum',     label: 'План',                   dot: 'var(--accent)',          countKey: 'plan_count'     },
];

// Точки для бейджей в таблице
const AGING_DOT = {
  'Просрочка': 'var(--dot-overdue)',
  'Текущая':   'var(--dot-current-dz)',
};

// ── Колонки таблицы ───────────────────────────────────────────────
const COLS = [
  { key: 'name',       label: 'Контрагент', w: '240px', align: 'left'   },
  { key: 'inn',        label: 'ИНН',        w: '120px', align: 'left'   },
  { key: 'delay',      label: 'Отсрочка',   w: '84px',  align: 'left'   },
  { key: 'total_sum',  label: 'Сумма',      w: '140px', align: 'right'  },
  { key: 'count',      label: 'Кол-во',     w: '64px',  align: 'center' },
  { key: 'aging',      label: 'Возраст',    w: '1fr',   align: 'left'   },
  { key: 'note',       label: 'Примечание', w: '170px', align: 'left'   },
];
const gridCols = COLS.map(c => c.w).join(' ');

// ── Стили ─────────────────────────────────────────────────────────
const card = (extra = {}) => ({
  background: 'var(--bg-card)', borderRadius: 'var(--radius-card)',
  boxShadow: 'var(--shadow-card)', ...extra,
});

export default function Receivables() {
  const router = useRouter();
  const [summary,   setSummary]   = useState(null);
  const [debtors,   setDebtors]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [onlyActive, setOnlyActive] = useState(true);
  const [filters, setFilters]     = useState({ contractor: '', article: '', period: '' });
  const [filterOpts, setFilterOpts] = useState({ contractors: [], articles: [], periods: [] });

  useEffect(() => {
    const perms = getPermissions();
    if (!can(perms, 'receivables')) { router.push('/login'); return; }
    const token = localStorage.getItem('token');
    if (!token) { router.push('/login'); return; }
    const h = { Authorization: `Bearer ${token}` };

    Promise.all([
      axios.get('/receivables/summary', { headers: h }),
      axios.get('/receivables/debtors',  { headers: h }),
      axios.get('/receivables/filter-options', { headers: h }),
    ]).then(([s, d, f]) => {
      setSummary(s.data);
      setDebtors(d.data);
      setFilterOpts(f.data);
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const displayed = debtors.filter(d => {
    if (onlyActive && !d.is_active) return false;
    if (filters.contractor && !d.name.includes(filters.contractor)) return false;
    if (filters.article    && !d.articles?.includes(filters.article)) return false;
    if (filters.period     && !d.periods?.includes(filters.period)) return false;
    return true;
  });

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

          {/* Заголовок */}
          <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', marginBottom: 22 }}>
            <h1 style={{ margin: 0, fontSize: 28, fontWeight: 300, color: 'var(--text-primary)', letterSpacing:'-.02em' }}>
              Дебиторская <b style={{ fontWeight: 800 }}>задолженность</b>
            </h1>
            <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 500 }}>
              на {new Date().toLocaleDateString('ru-RU')}
            </span>
          </div>

          {/* KPI — 3 цифры */}
          <div style={{ display:'flex', gap: 16, marginBottom: 16 }}>
            {[
              { label: 'Итого дебиторка',          val: fmt(summary?.total_sum)  + ' ₽' },
              { label: 'Контрагентов-должников',   val: summary?.contractor_count ?? '—' },
              { label: 'Счетов / операций',         val: summary?.invoice_count   ?? '—' },
            ].map((k, i) => (
              <div key={i} style={{ ...card(), flex: 1, padding: '20px 22px' }}>
                <div style={{ fontSize: 12.5, color: 'var(--text-muted)', fontWeight: 500 }}>{k.label}</div>
                <div style={{ fontSize: 27, fontWeight: 700, color: 'var(--text-primary)',
                  marginTop: 9, fontVariantNumeric: 'tabular-nums', letterSpacing:'-.01em' }}>{k.val}</div>
              </div>
            ))}
          </div>

          {/* Пояснение */}
          <div style={{ fontSize: 12, color: 'var(--text-faint)', margin: '0 2px 14px', lineHeight: 1.5 }}>
            Срок оплаты = период + отсрочка контрагента (стандартно 60 дн.).
            Текущая задолженность — до 30 дн. после срока, далее — просрочка.
          </div>

          {/* Карточки старения */}
          <div style={{ display:'flex', gap: 16, marginBottom: 22 }}>
            {AGING_CARDS.map(cfg => (
              <div key={cfg.key} style={{ ...card({ borderRadius: 18 }), flex: 1, padding: '18px 22px' }}>
                <div style={{ display:'flex', alignItems:'center', gap: 8 }}>
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: cfg.dot, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>{cfg.label}</span>
                </div>
                <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)',
                  marginTop: 8, fontVariantNumeric: 'tabular-nums' }}>
                  {fmt(summary?.[cfg.key])} ₽
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 5 }}>
                  {summary?.[cfg.countKey] ?? 0} операций
                </div>
              </div>
            ))}
          </div>

          {/* Фильтры */}
          <div style={{ display:'flex', gap: 10, marginBottom: 18, flexWrap:'wrap', alignItems:'center' }}>
            {[
              ['contractor', 'Все контрагенты', filterOpts.contractors],
              ['article',    'Все статьи',      filterOpts.articles],
              ['period',     'Все периоды',     filterOpts.periods],
            ].map(([key, ph, opts]) => (
              <select key={key} value={filters[key]}
                onChange={e => setFilters(f => ({ ...f, [key]: e.target.value }))} style={{
                padding: '9px 15px', borderRadius: 'var(--radius-input)',
                background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer',
              }}>
                <option value="">{ph}</option>
                {(opts ?? []).map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ))}
            <div onClick={() => setOnlyActive(a => !a)} style={{
              display:'flex', alignItems:'center', gap: 8,
              padding: '9px 15px', borderRadius: 'var(--radius-input)', cursor: 'pointer',
              background: onlyActive ? 'var(--accent-tint)' : 'var(--bg-card)',
              border: `1px solid ${onlyActive ? 'var(--accent-tint)' : 'var(--border-card)'}`,
              fontSize: 13, color: onlyActive ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: 500,
            }}>
              <span style={{
                width: 15, height: 15, borderRadius: 4,
                background: onlyActive ? 'var(--accent)' : 'var(--border-card)',
                display:'flex', alignItems:'center', justifyContent:'center',
                color: '#fff', fontSize: 10, flexShrink: 0,
              }}>{onlyActive ? '✓' : ''}</span>
              Только актуальные
            </div>
          </div>

          {/* Таблица */}
          <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-card)', overflow:'hidden', boxShadow:'var(--shadow-card)' }}>
            {/* Заголовок */}
            <div style={{ display:'grid', gridTemplateColumns: gridCols, padding:'14px 22px',
              borderBottom:'1px solid var(--border-inner)', background:'var(--bg-subtle)',
              fontSize:10.5, fontWeight:700, color:'var(--text-faint)',
              letterSpacing:'.05em', textTransform:'uppercase' }}>
              {COLS.map(c => <span key={c.key} style={{ textAlign: c.align }}>{c.label}</span>)}
            </div>

            {/* Строки */}
            {displayed.map((d, i) => (
              <div key={d.id ?? i} style={{
                display:'grid', gridTemplateColumns: gridCols,
                padding:'13px 22px', borderBottom:'1px solid var(--border-row)',
                fontSize: 13.5, alignItems: 'center',
                background: i % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-subtle)',
              }}>
                <span style={{ color:'var(--text-primary)', fontWeight:600,
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{d.name}</span>
                <span style={{ color:'var(--text-muted)', fontVariantNumeric:'tabular-nums' }}>{d.inn}</span>
                <span style={{ color:'var(--text-muted)' }}>{d.delay_days ? d.delay_days + ' дн.' : '—'}</span>
                <span style={{ textAlign:'right', color:'var(--text-primary)', fontWeight:600,
                  fontVariantNumeric:'tabular-nums' }}>{fmt(d.total_sum)} ₽</span>
                <span style={{ textAlign:'center', color:'var(--text-secondary)',
                  fontVariantNumeric:'tabular-nums' }}>{d.invoice_count}</span>
                {/* Бейджи возраста */}
                <span style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                  {(d.aging ?? []).map((a, j) => (
                    <span key={j} style={{
                      display:'inline-flex', alignItems:'center', gap:6,
                      padding:'4px 10px', borderRadius: 'var(--radius-badge)',
                      background:'var(--bg-subtle)', color:'var(--text-secondary)',
                      fontSize:11, fontWeight:500, whiteSpace:'nowrap',
                      fontVariantNumeric:'tabular-nums',
                    }}>
                      <span style={{ width:7, height:7, borderRadius:'50%', flexShrink:0,
                        background: AGING_DOT[a.type] ?? 'var(--text-faint)' }} />
                      {a.type}: {fmt(a.sum)} ₽
                    </span>
                  ))}
                </span>
                <span style={{ color:'var(--text-muted)', fontSize:12 }}>{d.note ?? '—'}</span>
              </div>
            ))}

            {/* Итого */}
            <div style={{ display:'grid', gridTemplateColumns: gridCols,
              padding:'14px 22px', background:'var(--bg-subtle)',
              fontSize:13, alignItems:'center' }}>
              <span style={{ color:'var(--text-secondary)', fontWeight:600 }}>
                Итого ({displayed.length} из {debtors.length})
              </span>
              <span /><span />
              <span style={{ textAlign:'right', color:'var(--text-primary)', fontWeight:700,
                fontVariantNumeric:'tabular-nums' }}>
                {fmt(displayed.reduce((s, d) => s + (d.total_sum ?? 0), 0))} ₽
              </span>
              <span style={{ textAlign:'center', color:'var(--text-secondary)', fontWeight:600,
                fontVariantNumeric:'tabular-nums' }}>
                {displayed.reduce((s, d) => s + (d.invoice_count ?? 0), 0)}
              </span>
              <span /><span />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
