/** «Можно тратить» — тёмный блок героя и днём, и ночью (README хендоффа, п. 2; в темах NAVY). Цифры — из buildDays, тот же
 *  проход, что календарь. */
import { useThemeKey } from '@/lib/theme'
import { CAPS, MONO, NUM, Bar, f, fs } from './kit'
import { WD_FULL, ddmm } from './model'

const CAT_COLORS = ['var(--ok)', 'var(--accent)', 'var(--attn)', 'var(--text-faint)', 'var(--ok-border)', 'var(--border-hover)']

export default function Hero({ R, data, real, thr }) {
  const theme = useThemeKey()
  const { days, mi, minB, out, inAll, outAll } = R
  const end = days[days.length - 1]
  const low = minB < thr
  const worst = outAll - data.balance_total
  const cat = {}
  days.forEach(x => x.ops.forEach(o => { if (o.v < 0) cat[o.cat] = (cat[o.cat] || 0) - o.v }))
  const cats = Object.keys(cat).sort((a, b) => cat[b] - cat[a]).map((k, i) => ({ name: k.toLowerCase(), v: cat[k], c: CAT_COLORS[i % CAT_COLORS.length] }))
  const und = data.undated_out || { count: 0, sum: 0 }
  const fl = [['на счетах', f(data.balance_total), 'var(--text-primary)'], ['+ ждём от клиентов', f(inAll), 'var(--money-fg)'],
    ['− обязательства', f(outAll), 'var(--text-primary)'], [`= на ${ddmm(end.d)}`, fs(end.bal), end.bal < 0 ? 'var(--bad-fg)' : 'var(--text-primary)']]
  return (
    <div data-tone={String(theme || '').startsWith('navy') ? 'dark' : undefined} data-motion="rise"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 20,
        padding: '22px 26px', display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={CAPS}>Можно тратить · до {ddmm(end.d)}</span>
        {low && <span style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px', borderRadius: 6, background: 'var(--bad-tint)',
          border: '1px solid var(--bad-border)', fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
          color: 'var(--bad-fg)' }}>ниже неснижаемого {ddmm(days[mi].d)}</span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 52, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1,
          color: minB < 0 ? 'var(--bad-fg)' : 'var(--text-primary)' }}>{fs(minB)}</span>
        <span style={{ fontFamily: MONO, fontSize: 16, color: 'var(--text-muted)' }}>₽</span>
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
        Минимум остатка за 14 дней — <b style={{ color: 'var(--text-primary)' }}>{WD_FULL[days[mi].d.getDay()].toLowerCase()} {ddmm(days[mi].d)}</b>,{' '}
        {real ? 'если клиенты платят как обычно' : 'если клиенты платят в срок'}.{' '}
        {worst > 0 ? <>Если не заплатит никто — не хватит <b style={{ ...NUM, color: 'var(--bad-fg)' }}>{f(worst)} ₽</b>.</>
          : <>Если не заплатит никто — хватит, останется <b style={NUM}>{f(-worst)} ₽</b>.</>}
        {out > 0 && <span style={{ color: 'var(--attn-fg)' }}> За горизонт 14 дней уйдут поступления на <b style={NUM}>{f(out)} ₽</b>.</span>}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, auto)', justifyContent: 'start', gap: '4px 26px', paddingTop: 12,
        borderTop: '1px solid var(--border-inner)' }}>
        {fl.map(([cap, v, fg]) => (
          <div key={cap} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={CAPS}>{cap}</span><span style={{ ...NUM, fontSize: 17, color: fg }}>{v}</span>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        <span style={CAPS}>Обязательства на 14 дней · {f(outAll)} ₽ · по группам статей</span>
        {cats.length ? <>
          <Bar parts={cats.map(c => ({ w: c.v, c: c.c, t: `${c.name} · ${f(c.v)} ₽` }))} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>
            {cats.map(c => <span key={c.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: c.c }} />{c.name} <b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{f(c.v)}</b></span>)}
          </div>
        </> : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Плановых оплат с датой в эти 14 дней нет.</span>}
        {und.count > 0 && <span style={{ fontSize: 12, color: 'var(--attn-fg)', lineHeight: 1.45 }}>
          Ещё {und.count} плановых оплат на <b style={NUM}>{f(und.sum)} ₽</b> без даты — в календарь не попали. Поставьте им срок в «Операциях».
        </span>}
      </div>
    </div>
  )
}
