/**
 * Эффективность пакета в шапке (хендофф «мастер и шапка», 19.10.2026): одна строка — подпись с замком и пять показателей.
 * Предварительно и до НДС; считает сервер (`backend/app/master_deal/efficiency.py`). Нет права «Эффективность мастер-сделок» —
 * сервер не отдаёт `efficiency`, и строка не рендерится вовсе, без заглушек.
 * Вторая строка — «с доп. СК» (владелец 27.10.2026): партнёрская выплата и доля спец. условий вычитаются из прибыли ещё раз.
 * Сервер отдаёт `efficiency.full` только тем, кому открыта вкладка «Спец. условия», — рядом с обычной маржой, не вместо неё.
 */
import { CAP } from '@/components/master/kit'
import { MONO } from '@/components/salesTableKit'
import { pctComma, rub0 } from '@/lib/salesFormat'

const SMALL = { fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap' }

function Kpi({ label, value, fg, hint, title, warn }) {
  return (
    <span title={[title, hint].filter(Boolean).join(' · ')} style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, ...CAP, fontSize: 8.5, whiteSpace: 'nowrap' }}>{label}
        {!!warn && <span title={warn} style={{ color: 'var(--warning)', fontWeight: 700, cursor: 'help' }}>!</span>}</span>
      <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', color: fg || 'var(--text-primary)', whiteSpace: 'nowrap' }}>{value}</span>
    </span>
  )
}

// пороги хендоффа: ≥ 60 % зелёный, ≥ 45 % обычный, ниже — жёлтый; убыток — красный
const toneOf = (m) => (m == null ? 'var(--text-faint)' : m < 0 ? 'var(--danger-fg)' : m >= 60 ? 'var(--income-fg)' : m >= 45 ? 'var(--text-primary)' : 'var(--warning-fg)')
const GRID = { display: 'grid', gridTemplateColumns: 'auto repeat(5, minmax(0,1fr))', gap: 14, alignItems: 'end', padding: '12px 14px', borderRadius: 12 }

function FullRow({ f }) {
  const tone = toneOf(f.margin_pct)
  const wait = f.accumulating.length ? `Копится до порога: ${f.accumulating.join(', ')} — пока не дошли, в доп. СК не входит` : ''
  return (
    <div style={{ ...GRID, background: 'var(--bg-card)', border: '1px dashed var(--accent-border)' }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingRight: 14, borderRight: '1px solid var(--accent-border)' }}>
        <span style={{ ...SMALL, fontWeight: 700, color: 'var(--accent-fg)' }}>С доп. СК</span>
        <span title="Видно тем, кому открыта вкладка «Спец. условия»" style={{ ...SMALL, color: 'var(--text-faint)' }}>партнёрская · спец.</span>
      </span>
      <Kpi label="Партнёрская" value={f.partner ? rub0(f.partner) : '—'} fg={f.partner ? undefined : 'var(--text-faint)'}
        hint="% партнёрских правил от ДС до СК" title="Выплата партнёрам по «Агентским условиям»" />
      <Kpi label="Спец. условия" value={f.special ? rub0(f.special) : '—'} fg={f.special ? undefined : 'var(--text-faint)'}
        hint="доля сделок в начислении" title="Доля спец. условий: % от суммы сделки, фикс — по её доле в обороте месяца" warn={wait} />
      <Kpi label="Доп. СК всего" value={f.extra ? rub0(f.extra) : '—'} fg={f.extra ? undefined : 'var(--text-faint)'} hint="партнёрская + спец." />
      <Kpi label="Прибыль с доп. СК" value={f.profit == null ? '—' : rub0(f.profit)} fg={tone} hint="прибыль − доп. СК" title="Прибыль пакета − партнёрская − спец. условия" />
      <Kpi label="Маржа с доп. СК" value={f.margin_pct == null ? '—' : pctComma(f.margin_pct)} fg={tone} hint="прибыль с доп. СК / ДС до СК" />
    </div>
  )
}

export default function EfficiencyRow({ eff }) {
  if (!eff || !eff.rows.length) return null
  const t = eff.total
  const tone = toneOf(t.margin_pct)
  const noPct = eff.rows.filter(r => r.sk_mode && !r.sk_percent).map(r => r.code)
  const skWarn = noPct.length ? `У ${noPct.join(', ')} задан способ СК, но не задан процент — СК посчитан как 0` : ''
  const warns = [skWarn, t.missing_cost.length ? `Нет себестоимости: ${t.missing_cost.join(', ')} — ни введённой на сверке, ни факта показов для оценки; прибыль пакета не считается` : ''].filter(Boolean)
  return (
    <>
      <div style={{ ...GRID, background: 'var(--bg-tint)', border: '1px solid var(--accent-border)' }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingRight: 14, borderRight: '1px solid var(--accent-border)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--accent-fg)' }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>Эффективность
          </span>
          <span title="Право «Эффективность мастер-сделок» · просмотр; предварительно, до НДС" style={{ ...SMALL, color: 'var(--text-faint)' }}>видно по праву · до НДС</span>
        </span>
        <Kpi label="Выручка до НДС" value={rub0(t.revenue)} hint="сумма ДС пакета" title="Сумма ДС пакета до НДС" />
        <Kpi label="СК постоплатой" value={t.sk_cost ? rub0(t.sk_cost) : '—'} fg={t.sk_cost ? undefined : 'var(--text-faint)'}
          hint={t.sk_amount && !t.sk_cost ? 'скидка в счёт — уже в выручке' : 'наш расход потом'} title="Скидка клиенту, которая уйдёт постоплатой" warn={skWarn} />
        <Kpi label="Себестоимость" value={rub0(t.cost)} hint={t.estimated.length ? `по CPM площадок · ${t.estimated.join(', ')}` : 'введена на сверке'}
          title={t.estimated.length ? 'Оценка: факт показов × CPM договора площадки' : 'Введена аккаунтом на итоговой сверке'} />
        <Kpi label="Прибыль" value={t.profit == null ? '—' : rub0(t.profit)} fg={tone} hint="выручка − СК − себестоимость" title="Выручка − СК постоплатой − себестоимость" />
        <Kpi label="Маржа" value={t.margin_pct == null ? '—' : pctComma(t.margin_pct)} fg={tone} hint="прибыль / ДС до СК"
          title={`Прибыль / сумма ДС до СК${t.gross !== t.revenue ? ` (${rub0(t.gross)}): скидка в счёт в базу маржи возвращается` : ''}`} />
      </div>
      {!!eff.full && <FullRow f={eff.full} />}
      {warns.filter(w => w !== skWarn).map(w => (
        <span key={w} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 9, fontSize: 11.5, color: 'var(--warning-fg)' }}>
          <span aria-hidden style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--warning)', flex: '0 0 6px' }} />{w}.
        </span>
      ))}
    </>
  )
}
