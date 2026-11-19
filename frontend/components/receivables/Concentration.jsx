/** «Концентрация» (хендофф, п. 4): топ-5 и доля топ-3; больше 40 % у трёх — предупреждение о зависимости. */
import { CAPS, H, MONO, Bar, f } from '@/components/money/kit'

const CN = ['var(--hot)', 'var(--accent)', 'var(--ok)', 'var(--ok-border)', 'var(--border-hover)']

export default function Concentration({ all }) {
  const tot = all.reduce((a, x) => a + x.sum, 0) || 1
  const srt = all.slice().sort((a, b) => b.sum - a.sum)
  const top3 = srt.slice(0, 3).reduce((a, x) => a + x.sum, 0)
  const share = top3 / tot
  return (
    <div data-motion="rise" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 20, padding: '20px 22px',
      display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}><span style={H}>Концентрация</span>
        <span style={{ marginLeft: 'auto', ...CAPS }}>топ-3 · {Math.round(share * 100)} %</span></div>
      <Bar h={12} parts={srt.slice(0, 5).map((x, k) => ({ w: x.sum, c: CN[k], t: `${x.who} · ${f(x.sum)}` }))
        .concat([{ w: srt.slice(5).reduce((a, x) => a + x.sum, 0), c: 'var(--bg-subtle)', t: 'остальные' }])} />
      {srt.slice(0, 5).map((x, k) => (
        <div key={x.id} style={{ display: 'grid', gridTemplateColumns: '10px minmax(0,1fr) auto 48px', gap: 10, alignItems: 'center', padding: '7px 0', borderTop: '1px solid var(--border-row)' }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: CN[k] }} />
          <span style={{ fontSize: 13, fontWeight: k < 3 ? 700 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.who}</span>
          <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700 }}>{f(x.sum)}</span>
          <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)', textAlign: 'right' }}>{Math.round(x.sum / tot * 100)} %</span>
        </div>
      ))}
      <span style={{ marginTop: 'auto', fontSize: 12, color: share > 0.4 ? 'var(--attn-fg)' : 'var(--text-muted)', lineHeight: 1.45 }}>
        {share > 0.4 ? `${Math.round(share * 100)} % дебиторки — у трёх клиентов. Задержка одного из них сдвигает весь месяц.` : 'Дебиторка распределена ровно: у трёх крупнейших — меньше 40 %.'}
      </span>
    </div>
  )
}
