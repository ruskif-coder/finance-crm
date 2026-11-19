/** Верхняя полоса дебиторки (хендофф, п. 2): контрастный блок «просрочено · чистая позиция · можно зачесть» и три карточки. */
import { useThemeKey } from '@/lib/theme'
import { CAPS, MONO, f } from '@/components/money/kit'
import { cpL, invL, fd } from './model'

const mln = (n) => (n / 1e6).toFixed(2).replace('.', ',') + ' млн'

function Card({ cap, c, v, fg, s, s2 }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 20, padding: '20px 22px',
      display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} /><span style={CAPS}>{cap}</span></span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}><span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700, letterSpacing: '-0.02em', color: fg }}>{v}</span>
        <span style={{ fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>₽</span></span>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s}</span>
      <span style={{ marginTop: 'auto', paddingTop: 8, borderTop: '1px solid var(--border-inner)', fontSize: 12, color: 'var(--text-secondary)' }}>{s2}</span>
    </div>
  )
}

export default function TopStrip({ all, today, bk, onFilter }) {
  const theme = useThemeKey()
  const tot = all.reduce((a, x) => a + x.sum, 0) || 1
  const over = all.reduce((a, x) => a + x.b[0], 0), cur = all.reduce((a, x) => a + x.b[1], 0), due = all.reduce((a, x) => a + x.b[2], 0)
  const weOwe = all.reduce((a, x) => a + x.we, 0), netting = all.reduce((a, x) => a + x.net, 0)
  const nettingN = all.filter(x => x.net > 0).length, overN = all.filter(x => x.late).length, todayN = all.filter(x => x.act).length
  const top3 = all.slice().sort((a, b) => b.sum - a.sum).slice(0, 3).reduce((a, x) => a + x.sum, 0)
  const eom = bk.eom(0)
  let inM = 0, inMr = 0
  all.forEach(x => x.its.forEach(it => {
    if (!it.srok) return
    if (it.srok <= eom && it.srok >= today) inM += it.v
    const e = new Date(it.srok.getFullYear(), it.srok.getMonth(), it.srok.getDate() + x.delta)
    if (e <= eom && e >= today) inMr += it.v
  }))
  const navy = String(theme || '').startsWith('navy')
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.55fr) repeat(3, minmax(0,1fr))', gap: 16 }}>
      <div data-tone={navy ? (theme === 'navy-dark' ? 'light' : 'dark') : undefined} data-motion="rise"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 20, padding: '20px 24px',
          display: 'grid', gridTemplateColumns: 'minmax(0,1.1fr) minmax(0,1fr)', gap: '6px 26px', minWidth: 0 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={CAPS}>Просрочено</span>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={{ fontFamily: MONO, fontSize: 40, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: 'var(--bad-fg)' }}>{f(over)}</span>
            <span style={{ fontFamily: MONO, color: 'var(--text-muted)' }}>₽</span></span>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}><b style={{ fontFamily: MONO, color: 'var(--bad-fg)' }}>{Math.round(over / tot * 100)} %</b> портфеля · {cpL(overN)}</span>
          {todayN > 0 && <button type="button" onClick={() => onFilter('nonote')} style={{ alignSelf: 'flex-start', marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 8, height: 28,
            padding: '0 11px', borderRadius: 9, background: 'var(--signal-tint)', border: '1px solid var(--signal-border)', color: 'var(--signal-text)', fontSize: 12.5, fontWeight: 700,
            cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'inherit' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--signal)' }} />просрочка без примечания · {todayN}</button>}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingLeft: 22, borderLeft: '1px solid var(--border-inner)' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={CAPS}>Чистая позиция</span>
            <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700 }}>{f(tot - weOwe)} ₽</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>дебиторка минус то, что мы должны тем же контрагентам ({f(weOwe)})</span></span>
          <button type="button" onClick={() => netting > 0 && onFilter('net')} style={{ display: 'flex', flexDirection: 'column', gap: 3, cursor: netting > 0 ? 'pointer' : 'default',
            background: 'transparent', border: 0, padding: 0, textAlign: 'left', color: 'inherit', fontFamily: 'inherit' }}>
            <span style={CAPS}>Можно зачесть</span>
            <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: 'var(--money-fg)' }}>{f(netting)} ₽</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{nettingN ? `у ${nettingN} ${nettingN === 1 ? 'контрагента' : 'контрагентов'} — показать` : 'встречных долгов нет'}</span>
          </button>
        </div>
      </div>
      <Card cap="Итого дебиторка" c="var(--hot)" v={f(tot)} fg="var(--text-primary)" s={`${cpL(all.length)} · ${invL(all.reduce((a, x) => a + x.its.length, 0))}`}
        s2={`топ-3 клиента — ${Math.round(top3 / tot * 100)} % суммы`} />
      <Card cap="Текущая" c="var(--attn)" v={f(cur)} fg="var(--attn-fg)" s={`${Math.round(cur / tot * 100)} % портфеля · до 30 дн после срока`} s2="дальше — просрочка" />
      <Card cap="Срок не наступил" c="var(--ok)" v={f(due)} fg="var(--text-primary)" s={`${Math.round(due / tot * 100)} % портфеля`}
        s2={`ждём до ${fd(eom)}: по договору ${mln(inM)} · на деле ${mln(inMr)}`} />
    </div>
  )
}
