/**
 * operations.js — страница Операций.
 * Заменяет предыдущий operations.js целиком.
 * Таблица с фильтрами, новые бейджи статусов (точка + нейтральный фон).
 */
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/router';
import axios from 'axios';
import Navbar, { getPermissions, can } from '../components/Navbar';

axios.defaults.baseURL = 'http://localhost:8000/api';

// ── Статусы — точка-индикатор ─────────────────────────────────────
const STATUS_DOT = {
  'ПЛАН ПРИХОДА':  'var(--dot-income)',
  'ПЛАН ОПЛАТ':    'var(--dot-expense)',
  'ФАКТ ПРИХОДА':  'var(--dot-income)',
  'ФАКТ ОПЛАТ':    'var(--dot-expense)',
};
const statusDot = (s) => STATUS_DOT[s] ?? 'var(--text-faint)';

// ── Форматирование ────────────────────────────────────────────────
const fmt = (n) => n == null || n === '' ? '—' : Number(n).toLocaleString('ru-RU');

// ── Колонки таблицы ───────────────────────────────────────────────
const COLS = [
  { key: 'status',      label: 'Статус',      w: 130,  align: 'left'  },
  { key: 'contractor',  label: 'Контрагент',  w: 160,  align: 'left'  },
  { key: 'income',      label: 'Поступление', w: 130,  align: 'right' },
  { key: 'expense',     label: 'Списание',    w: 130,  align: 'right' },
  { key: 'article',     label: 'Статья',      w: 180,  align: 'left'  },
  { key: 'period',      label: 'Период',      w: 100,  align: 'left'  },
  { key: 'vat_rate',    label: 'НДС',         w: 70,   align: 'right' },
  { key: 'vat_amount',  label: 'НДС ₽',       w: 130,  align: 'right' },
  { key: 'date',        label: 'Дата',        w: 100,  align: 'right' },
];
const gridCols = COLS.map(c => c.w + 'px').join(' ');

// ── Стили ─────────────────────────────────────────────────────────
const S = {
  page:  { minHeight: '100vh', background: 'var(--bg-canvas)' },
  inner: { maxWidth: 1440, margin: '0 auto', padding: '26px 30px' },
  card:  {
    background: 'var(--bg-card)', borderRadius: 'var(--radius-card)',
    boxShadow: 'var(--shadow-card)', overflow: 'hidden',
  },
  filterRow: { display: 'flex', gap: 10, marginBottom: 18, flexWrap: 'wrap' },
  filterSelect: {
    padding: '9px 15px', borderRadius: 'var(--radius-input)',
    background: 'var(--bg-card)', border: '1px solid var(--border-card)',
    fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer',
  },
  tableHead: {
    display: 'grid', gridTemplateColumns: gridCols,
    padding: '13px 22px', borderBottom: '1px solid var(--border-inner)',
    fontSize: 10.5, fontWeight: 700, color: 'var(--text-faint)',
    letterSpacing: '.04em', textTransform: 'uppercase',
    background: 'var(--bg-subtle)',
  },
  tableRow: {
    display: 'grid', gridTemplateColumns: gridCols,
    padding: '13px 22px', borderBottom: '1px solid var(--border-row)',
    fontSize: 13.5, alignItems: 'center',
  },
};

export default function Operations() {
  const router = useRouter();
  const [ops, setOps]               = useState([]);
  const [total, setTotal]           = useState(0);
  const [loading, setLoading]       = useState(true);
  const [page, setPage]             = useState(1);
  const [perPage]                   = useState(100);
  const [filters, setFilters]       = useState({
    status: '', bank: '', article: '', contractor: '', period: '',
  });
  const [filterOpts, setFilterOpts] = useState({ statuses:[], banks:[], articles:[], contractors:[], periods:[] });

  const load = useCallback(async () => {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/login'); return; }
    setLoading(true);
    try {
      const params = { page, per_page: perPage, ...Object.fromEntries(Object.entries(filters).filter(([,v])=>v)) };
      const { data } = await axios.get('/operations', { params, headers: { Authorization: `Bearer ${token}` } });
      setOps(data.items ?? data);
      setTotal(data.total ?? data.length);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [page, perPage, filters]);

  useEffect(() => {
    const perms = getPermissions();
    if (!can(perms, 'operations')) { router.push('/login'); return; }
    // Загрузить опции фильтров
    const token = localStorage.getItem('token');
    axios.get('/operations/filter-options', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => setFilterOpts(r.data)).catch(() => {});
    load();
  }, []);

  useEffect(() => { load(); }, [page, filters]);

  const setFilter = (key, val) => { setFilters(f => ({ ...f, [key]: val })); setPage(1); };

  return (
    <div style={S.page}>
      <Navbar />
      <div style={{ paddingTop: 'var(--navbar-h)' }}>
        <div style={S.inner}>

          {/* Заголовок */}
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom: 20 }}>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 300, color: 'var(--text-primary)', letterSpacing:'-.01em' }}>
              Операции <b style={{ fontWeight: 800 }}>{total.toLocaleString('ru-RU')}</b>
            </h1>
            <div style={{ display:'flex', gap: 10 }}>
              <button style={{
                padding: '10px 18px', borderRadius: 'var(--radius-btn)',
                background: 'var(--accent)', color: '#fff',
                fontSize: 13.5, fontWeight: 600, border: 'none', cursor: 'pointer',
              }}>+ Новая операция</button>
              <button style={{
                padding: '10px 18px', borderRadius: 'var(--radius-btn)',
                background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                fontSize: 13.5, fontWeight: 500, color: 'var(--text-secondary)', cursor: 'pointer',
              }}>Шаблон</button>
            </div>
          </div>

          {/* Фильтры */}
          <div style={S.filterRow}>
            {[
              ['status',     'Все статусы',     filterOpts.statuses],
              ['bank',       'Все банки',        filterOpts.banks],
              ['article',    'Все статьи',       filterOpts.articles],
              ['contractor', 'Все контрагенты',  filterOpts.contractors],
              ['period',     'Все периоды',      filterOpts.periods],
            ].map(([key, placeholder, opts]) => (
              <select key={key} value={filters[key]} onChange={e => setFilter(key, e.target.value)}
                style={S.filterSelect}>
                <option value="">{placeholder}</option>
                {(opts ?? []).map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ))}
            {Object.values(filters).some(Boolean) && (
              <span onClick={() => setFilters({ status:'', bank:'', article:'', contractor:'', period:'' })}
                style={{ padding:'9px 15px', borderRadius:'var(--radius-input)',
                  background:'var(--accent-tint)', color:'var(--accent)',
                  fontSize:13, fontWeight:500, cursor:'pointer' }}>
                Сбросить всё
              </span>
            )}
          </div>

          {/* Таблица */}
          <div style={S.card}>
            <div style={S.tableHead}>
              {COLS.map(c => (
                <span key={c.key} style={{ textAlign: c.align }}>{c.label}</span>
              ))}
            </div>
            {loading
              ? <div style={{ padding:'32px', textAlign:'center', color:'var(--text-muted)' }}>Загрузка…</div>
              : ops.map((op, i) => (
                <div key={op.id ?? i} style={{
                  ...S.tableRow,
                  background: i % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-subtle)',
                }}>
                  {/* Статус */}
                  <span>
                    <span style={{
                      display:'inline-flex', alignItems:'center', gap:6,
                      padding:'4px 10px', borderRadius:'var(--radius-badge)',
                      background:'var(--bg-subtle)', color:'var(--text-secondary)',
                      fontSize:10.5, fontWeight:600, whiteSpace:'nowrap',
                    }}>
                      <span style={{ width:7, height:7, borderRadius:'50%', background: statusDot(op.status), flexShrink:0 }} />
                      {op.status}
                    </span>
                  </span>
                  <span style={{ color:'var(--text-primary)', fontWeight:500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{op.contractor}</span>
                  <span style={{ textAlign:'right', color:'var(--income)', fontWeight:600, fontVariantNumeric:'tabular-nums' }}>
                    {op.income ? fmt(op.income) : '—'}
                  </span>
                  <span style={{ textAlign:'right', color:'var(--expense)', fontWeight:600, fontVariantNumeric:'tabular-nums' }}>
                    {op.expense ? fmt(op.expense) : '—'}
                  </span>
                  <span style={{ color:'var(--text-secondary)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{op.article}</span>
                  <span style={{ color:'var(--text-muted)' }}>{op.period}</span>
                  <span style={{ textAlign:'right', color:'var(--text-muted)', fontVariantNumeric:'tabular-nums' }}>{op.vat_rate ?? '—'}</span>
                  <span style={{ textAlign:'right', color:'var(--text-secondary)', fontVariantNumeric:'tabular-nums' }}>{op.vat_amount ? fmt(op.vat_amount) : '—'}</span>
                  <span style={{ textAlign:'right', color:'var(--text-muted)', fontVariantNumeric:'tabular-nums' }}>{op.date ?? '—'}</span>
                </div>
              ))
            }
          </div>

          {/* Пагинация */}
          {total > perPage && (
            <div style={{ display:'flex', justifyContent:'center', gap:8, marginTop:20 }}>
              {Array.from({ length: Math.ceil(total / perPage) }, (_, i) => (
                <button key={i} onClick={() => setPage(i + 1)} style={{
                  width:36, height:36, borderRadius:9, border:'1px solid var(--border-card)',
                  background: page === i+1 ? 'var(--accent)' : 'var(--bg-card)',
                  color:      page === i+1 ? '#fff'          : 'var(--text-secondary)',
                  fontSize:13, fontWeight:600, cursor:'pointer',
                }}>{i + 1}</button>
              ))}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
