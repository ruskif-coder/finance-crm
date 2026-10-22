// «Статусы продаж» — новая сделка из ячейки (хендофф §5). Месяц и вероятность — из ячейки; рекламодатель и бренд из строки
// зафиксированы. Обязательны рекламодатель, услуга, сумма без НДС. Сделка не создаётся сразу — встаёт пунктирным пином
// в панель «В реестр запишется» и уходит по «Сохранить» обычным путём (POST /sales/deals).
import { useEffect, useState } from 'react'
import { overlayClose } from '@/lib/overlay'
import { grp } from '@/lib/salesFormat'
import { COLS, COL_WORD, GROUP, monthName } from '@/lib/salesStatus'

const MONO = "'JetBrains Mono', monospace"
const LBL = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const BOX = { height: 36, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', borderRadius: 10,
  fontFamily: "'Manrope', sans-serif", fontSize: 13, color: 'var(--text-primary)', outline: 'none' }
const seg = { display: 'inline-flex', padding: 3, height: 36, boxSizing: 'border-box', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10 }
const segItem = (on, fg) => ({ flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 5, borderRadius: 7, whiteSpace: 'nowrap',
  background: on ? 'var(--bg-card)' : 'transparent', color: on ? (fg || 'var(--accent-fg)') : 'var(--text-secondary)', fontSize: 12, fontWeight: on ? 700 : 600, cursor: 'pointer' })

function Fixed({ text }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 7, height: 36, boxSizing: 'border-box', padding: '0 11px', background: 'var(--bg-subtle)',
      border: '1px solid var(--income-border)', borderRadius: 10, fontSize: 13, fontWeight: 600 }}>
      <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--income)' }} />{text}
      <span style={{ marginLeft: 'auto', ...LBL, fontSize: 8.5, color: 'var(--text-faint)' }}>из строки</span>
    </span>
  )
}

export default function NewDealForm({ init, months, dirs, onClose, onCreate }) {
  const [adv, setAdv] = useState(init.adv?.id ? String(init.adv.id) : '')
  const [brand, setBrand] = useState(init.brand?.id ? String(init.brand.id) : '')
  const [month, setMonth] = useState(init.month)
  const [col, setCol] = useState(init.col)
  const [service, setService] = useState('')
  const [net, setNet] = useState('')
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const advFixed = !!init.adv?.id, brandFixed = !!init.brand?.id
  const advName = (dirs.advertisers.find(a => String(a.value) === adv) || {}).label || init.adv?.name || ''
  const brands = adv ? (dirs.brands[adv] || []) : []
  const brandName = (brands.find(b => String(b.value) === brand) || {}).label || init.brand?.name || ''
  // Строка «без сделки»: рекламодатель подбирается по совпадению названия клиента
  const guess = init.client && !adv ? dirs.advertisers.find(a => {
    const w = String(a.label).split(' | ')[0].toLowerCase()
    return w.length >= 3 && init.client.toLowerCase().includes(w)
  }) : null
  // «150 000,50» и «1 500 000.00» — рубли с копейками, а не 15 000 050 (ревью 22.10.2026)
  const amount = Math.round((parseFloat(String(net).replace(/[\s ]/g, '').replace(',', '.')) || 0) * 100) / 100
  const ok = !!adv && !!service && amount > 0
  const missing = [!adv && 'рекламодатель', !service && 'услуга', !amount && 'сумма'].filter(Boolean)
  const vat = dirs.vat ?? 22

  const create = () => ok && onCreate({ adv: { id: Number(adv), name: advName.split(' | ')[0] }, brand: brand ? { id: Number(brand), name: brandName } : null,
    month, col, service, amount })

  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'var(--scrim)', display: 'flex', alignItems: 'flex-start',
      justifyContent: 'center', padding: '72px 20px', boxSizing: 'border-box', overflow: 'auto' }}>
      <div style={{ width: '100%', maxWidth: 560, background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-float)', borderRadius: 18,
        padding: '20px 22px 18px', display: 'flex', flexDirection: 'column', gap: 14, animation: 'ssPop .2s cubic-bezier(.22,1,.36,1) both' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
            <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: '-.02em' }}>Новая сделка</span>
            <span style={{ ...LBL, fontSize: 9.5 }}>{brandFixed ? 'из строки бренда' : advFixed ? 'из строки рекламодателя — выберите бренд' : init.client ? `из таблицы продаж · ${init.client}` : 'новая'}</span>
          </div>
          <span onClick={onClose} title="Закрыть · Esc" style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28,
            borderRadius: 8, color: 'var(--text-faint)', cursor: 'pointer' }}>✕</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 14px' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
            <span style={LBL}>Рекламодатель *</span>
            {advFixed ? <Fixed text={advName.split(' | ')[0]} /> : <>
              <select value={adv} onChange={e => { setAdv(e.target.value); setBrand('') }}
                style={{ ...BOX, border: `1px solid ${adv ? 'var(--income-border)' : 'var(--warning-border)'}` }}>
                <option value="">выберите…</option>
                {dirs.advertisers.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
              </select>
              {init.client && !adv && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>
                {guess ? <>по названию похож: <b style={{ cursor: 'pointer', color: 'var(--accent)' }} onClick={() => setAdv(String(guess.value))}>{guess.label.split(' | ')[0]}</b></>
                  : 'совпадений в справочнике нет — выберите вручную'}</span>}
            </>}
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
            <span style={LBL}>Бренд</span>
            {brandFixed ? <Fixed text={brandName} /> : (
              <select value={brand} disabled={!adv} onChange={e => setBrand(e.target.value)} style={{ ...BOX, border: '1px solid var(--border-card)' }}>
                <option value="">{adv ? 'без бренда' : 'сначала рекламодатель'}</option>
                {brands.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
              </select>
            )}
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
            <span style={LBL}>Планируется в период *</span>
            <span style={seg}>{months.map(m => <span key={m} onClick={() => setMonth(m)} style={segItem(month === m)}>{monthName(m)}</span>)}</span>
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
            <span style={LBL}>Вероятность · светофор реестра</span>
            <span style={seg}>{COLS.map(c => (
              <span key={c} onClick={() => setCol(c)} style={{ ...segItem(col === c, GROUP[c].fg), fontSize: 11.5 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: GROUP[c].dot }} />{COL_WORD[c]}
              </span>
            ))}</span>
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
            <span style={LBL}>Услуга *</span>
            <select value={service} onChange={e => setService(e.target.value)} style={{ ...BOX, border: `1px solid ${service ? 'var(--income-border)' : 'var(--warning-border)'}` }}>
              <option value="">выберите…</option>
              {dirs.services.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
            <span style={LBL}>Сумма без НДС, ₽ *</span>
            <input value={net} onChange={e => setNet(e.target.value)} placeholder="0" inputMode="decimal"
              style={{ ...BOX, padding: '0 11px', border: `1px solid ${amount ? 'var(--income-border)' : 'var(--warning-border)'}`, fontFamily: MONO, fontWeight: 700, textAlign: 'right' }} />
            <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)', textAlign: 'right' }}>
              {amount ? `с НДС ${vat} % · ${grp(amount * (1 + vat / 100))} ₽` : 'с НДС считается автоматически'}
            </span>
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{ok ? 'Стадия — МП Подготовка, воронка Песочница' : `Не заполнено: ${missing.join(', ')}`}</span>
          <button onClick={onClose} style={{ marginLeft: 'auto', height: 34, padding: '0 14px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10,
            fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }}>Отмена</button>
          <button onClick={create} disabled={!ok} title={ok ? '' : 'Заполните обязательные поля'} style={{ height: 34, padding: '0 16px', border: 'none', borderRadius: 10,
            background: ok ? 'var(--accent)' : 'var(--accent-soft)', color: 'var(--on-accent)', fontSize: 12.5, fontWeight: 700, cursor: ok ? 'pointer' : 'not-allowed' }}>Создать сделку</button>
        </div>
      </div>
    </div>
  )
}
