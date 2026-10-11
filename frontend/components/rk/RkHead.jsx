// Шапка «Разбора РК»: код, рекламодатель, статус, KPI по включённым площадкам, флайт, проверки, действия.
import { MONO } from '@/components/salesTableKit'
import CopyCode from '@/components/CopyCode'
import { nf, rub, pf, sg, dm, box, cap, CHECK_COLOR, Dot } from './rkUi'

const btnL = { display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 12px', whiteSpace: 'nowrap',
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12, fontWeight: 600,
  color: 'var(--text-secondary)', cursor: 'pointer', textDecoration: 'none' }

export default function RkHead({ head, k, partial, ix, checks, onExport, exporting }) {
  const items = [
    ['План', nf(k.plan), 'var(--text-primary)', 'показов на флайт', 'сумма планов включённых площадок' + partial],
    ['Факт', nf(k.fact), 'var(--income-fg)', pf(k.plan ? k.fact / k.plan * 100 : null) + ' плана', `DSP ${nf(k.dsp)} · Adfox ${nf(k.adf)}`],
    ['Прогноз', nf(k.forecast), 'var(--accent)', pf(k.plan && k.forecast ? k.forecast / k.plan * 100 : null, 0) + ' плана',
      k.rest ? `темп ${nf(k.avg)}/дн × ${k.days} дн.` : 'флайт закрыт — прогноз равен факту'],
    ['Недокрут', k.under ? '−' + nf(k.under) : '0', k.under ? 'var(--danger-fg)' : 'var(--income-fg)',
      k.under ? pf(k.under / k.plan * 100) : 'в плане', k.rest ? 'план минус прогноз' : 'план минус факт'],
    k.rest ? ['Нужно в день', nf(k.need), 'var(--text-primary)', 'сейчас ' + nf(k.avg), `остаток на ${k.rest} дн.`]
      : ['В среднем в день', nf(k.avg), 'var(--text-primary)', 'план ' + nf(k.plan / (k.days || 1)), 'флайт закрыт'],
    ['Weborama', nf(k.wr), 'var(--text-secondary)', k.wrPct == null ? 'нечего сравнить' : sg(k.wrPct) + ' к факту',
      `верификатор, в факт не входит; сравнение по ${k.wrPlaces} площ., знаменатель — наш факт`],
    ['Расход', rub(k.spend), 'var(--text-primary)', 'прогноз ' + rub(k.spendForecast), 'показы площадки × CPM договора площадки (закуп, до НДС) ÷ 1000'],
    ['CPM в день', rub(k.cpm), 'var(--text-primary)', 'средний по площадкам', 'по каждому дню: расход всех площадок ÷ их показы × 1000, за период — среднее дневных'],
  ]
  const groups = checks?.groups || []
  return (
    <div style={{ ...box, padding: '16px 22px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}><CopyCode text={head.code} /></span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            {[head.adv, head.brand].filter(Boolean).join(' · ') || head.title}</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 680 }}>{head.title}</span>
        </span>
        {!!head.status && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, background: 'var(--income-tint)',
            color: 'var(--income-fg)', fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}><Dot c="var(--income)" />{head.status}</span>
        )}
        {!!head.stage && <span style={{ padding: '4px 10px', borderRadius: 8, background: 'var(--bg-subtle)', color: 'var(--text-secondary)', fontSize: 11.5, fontWeight: 600 }}>{head.stage}</span>}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
          <button type="button" style={btnL} onClick={onExport} disabled={exporting} title="Текущий срез: разрез, метрика, период, включённые площадки">
            {exporting ? 'Готовлю…' : '↓ Срез в Excel'}</button>
          <a style={btnL} href={`/traffic/dashboard?open=${encodeURIComponent(head.code)}`}>На дашборд</a>
          <a style={{ ...btnL, background: 'var(--accent)', borderColor: 'var(--accent)', color: 'var(--bg-card)', fontWeight: 700 }}
            href={`/sales/deals/${encodeURIComponent(head.code)}`} target="_blank" rel="noreferrer">Открыть сделку</a>
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'stretch', flexWrap: 'wrap', rowGap: 10, borderTop: '1px solid var(--border-inner)', paddingTop: 12 }}>
        {items.map(([label, value, fg, hint, title], i) => (
          <span key={label} title={title} style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '0 18px', borderLeft: i ? '1px solid var(--border-inner)' : 'none', minWidth: 0 }}>
            <span style={cap}>{label}</span>
            <span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1, color: fg, whiteSpace: 'nowrap' }}>{value}</span>
            <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{hint}</span>
          </span>
        ))}
        <span style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'column', gap: 6, paddingLeft: 18, borderLeft: '1px solid var(--border-inner)', minWidth: 220 }}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={cap}>Флайт</span>
            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>{dm(head.date_start)} — {dm(head.date_end)}</span>
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)' }}>день {k.elapsed} из {k.days}</span>
          </span>
          <span style={{ display: 'flex', gap: 2 }}>
            {ix.days.map(x => <span key={x} style={{ flex: 1, height: 8, borderRadius: 2, background: x <= ix.asOf ? 'var(--income)' : 'var(--border-inner)' }} />)}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={cap}>Проверки</span>
            {groups.length ? groups.map(g => (
              <span key={g.key} title={g.text} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                <Dot c={CHECK_COLOR[g.level]} s={8} />{g.title.toLowerCase()}</span>
            )) : ['заведение', 'сбор', 'раскладка'].map(l => (
              <span key={l} title="Проверок ночного прогона у этой РК в снимке нет" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                <Dot c="var(--text-disabled)" s={8} />{l}</span>
            ))}
          </span>
        </span>
      </div>
    </div>
  )
}
