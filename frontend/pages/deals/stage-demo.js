import { useEffect, useState, Fragment } from 'react'
import Head from 'next/head'
import api, { auth } from '../../lib/api'
import { MONO, UI, StageLayerBar } from '../../components/salesTableKit'
import { fmtMoney } from '../../lib/salesFormat'
import DealDetailDemo from '../../components/sales/DealDetailDemo'

// ── ДЕМО: копия реестра сделок + раскрытая сводка сделки (ТЗ «форма сделки») ──
// Объединённая колонка «Стадия» (стадия + индикатор слоя 2\2\2) и раскрытие строки
// по клику с полной 4-колоночной сводкой. Стили/примитивы — из salesTableKit.

const PROB_COLORS = { grey: 'var(--muted)', orange: 'var(--warning, #d97706)', green: 'var(--success)' }
const PROB_LABEL = { grey: 'малая', orange: 'средняя', green: 'высокая' }

// Объединённая ячейка «Стадия»: название стадии + индикатор слоя. Этап (воронка) — отдельная колонка.
function StageCell({ os }) {
  if (!os) return <span style={{ color: 'var(--text-faint)' }}>—</span>
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, overflow: 'hidden' }}>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-primary)', flex: '1 1 auto', minWidth: 0 }}>{os.name}</span>
      <StageLayerBar os={os} />
    </span>
  )
}

const COLS = [
  { key: 'prob', w: '26px', label: '' },
  { key: 'bitrix_id', w: '62px', label: 'BX_ID' },
  { key: 'agency', w: '92px', label: 'Агентство' },
  { key: 'advertiser', w: '1.1fr', label: 'Рекламодатель' },
  { key: 'brand', w: '1fr', label: 'Бренд' },
  { key: 'product', w: '1fr', label: 'Услуга' },
  { key: 'period', w: '78px', label: 'Период' },
  { key: 'stage', w: '1.25fr', label: 'Стадия' },
  { key: 'amount', w: '88px', label: 'Сумма', right: true },
  { key: 'sales_rep', w: '92px', label: 'Продавец' },
  { key: 'account_manager', w: '88px', label: 'Аккаунт' },
  { key: 'payer', w: '1.15fr', label: 'Плательщик' },
  { key: 'title', w: '2.5fr', label: 'Сделка' },
]
const gridTemplate = COLS.map(c => c.w).join(' ')

const el = (v, extra) => <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...extra }}>{v ?? '—'}</span>

function cellFor(key, d) {
  switch (key) {
    case 'prob': {
      const col = PROB_COLORS[d.probability_color]
      return <span title={d.probability_color ? `Вероятность: ${PROB_LABEL[d.probability_color]}` : 'Вероятность не задана'}
        style={{ display: 'inline-block', width: 14, height: 14, borderRadius: '50%', border: col ? 'none' : '1.5px solid var(--border-card)', background: col || 'transparent' }} />
    }
    case 'bitrix_id': return <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)' }}>{d.bitrix_id}</span>
    case 'agency': return el(d.agency, { fontWeight: 600 })
    case 'advertiser': return el(d.advertiser)
    case 'brand': return el(d.brand)
    case 'product': return el(d.product, { color: 'var(--text-secondary)' })
    case 'period': return el(d.period, { fontFamily: MONO, color: 'var(--text-secondary)' })
    case 'stage': return <StageCell os={d.our_stage} />
    case 'amount': return <span style={{ fontFamily: MONO, fontWeight: 700, textAlign: 'right', display: 'block' }}>{fmtMoney(d.amount)}</span>
    case 'sales_rep': return el(d.sales_rep, { color: 'var(--text-secondary)' })
    case 'account_manager': return el(d.account_manager, { color: 'var(--text-secondary)' })
    case 'payer': return el(d.payer, { color: 'var(--text-secondary)' })
    case 'title': return el(d.title, { color: 'var(--text-secondary)' })
    default: return <span />
  }
}

export default function StageDemo() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    api.get('/sales/deals?limit=12&offset=0', auth())
      .then(r => setRows(r.data.items || []))
      .catch(e => setErr(e.response?.data?.detail || 'Ошибка загрузки'))
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI, padding: '28px 32px' }}>
      <Head><title>Демо · реестр + сводка сделки</title></Head>
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        .d2-row:hover { background: var(--bg-subtle) !important; }
        @media (prefers-reduced-motion: reduce) { [style*="animation"] { animation:none !important } }
      `}</style>

      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        <h1 style={{ fontSize: 19, fontWeight: 800, margin: '0 0 4px', color: 'var(--text-primary)' }}>Реестр сделок · демо сводки</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: '0 0 20px' }}>
          Клик по строке раскрывает сводку: Данные сделки · Медиаплан и документы · История · Оплаты. Колонка «Стадия» = стадия + индикатор слоя 2\2\2.
        </p>

        {err && <div style={{ color: 'var(--danger)', fontSize: 13 }}>{err}</div>}
        {rows === null && !err && <div style={{ color: 'var(--text-faint)', fontSize: 13 }}>Загрузка…</div>}

        {rows && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card, 0 1px 3px rgba(28,36,51,.06))', padding: '18px 20px' }}>
            <div style={{ overflowX: 'auto' }}>
              <div style={{ minWidth: 1180 }}>
                <div style={{ display: 'grid', gridTemplateColumns: gridTemplate, gap: 12, padding: '0 0 10px', borderBottom: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                  {COLS.map(c => <span key={c.key} style={{ textAlign: c.right ? 'right' : 'left' }}>{c.label}</span>)}
                </div>
                {rows.map(d => (
                  <Fragment key={d.id}>
                    <div className="d2-row" onClick={() => setExpandedId(x => x === d.id ? null : d.id)}
                      style={{ display: 'grid', gridTemplateColumns: gridTemplate, gap: 12, alignItems: 'center', padding: '7px 8px', margin: '0 -8px', borderRadius: 10, borderBottom: '1px solid var(--border-row)', fontSize: 12, color: 'var(--text-primary)', cursor: 'pointer', background: expandedId === d.id ? '#F6F8FF' : undefined }}>
                      {COLS.map(c => <div key={c.key} style={{ minWidth: 0 }}>{cellFor(c.key, d)}</div>)}
                    </div>
                    {expandedId === d.id && <DealDetailDemo deal={d} onClose={() => setExpandedId(null)} />}
                  </Fragment>
                ))}
                {!rows.length && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Нет сделок</div>}
              </div>
            </div>

            <div style={{ marginTop: 16, display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-muted)', paddingTop: 14, borderTop: '1px solid var(--border-inner)' }}>
              <span><b style={{ color: 'var(--text-secondary)' }}>Слой 2\2\2:</b> 6 позиций по под-этапу — планируемые (1-2) · реализуемые (3-4) · фактические (5-6)</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
