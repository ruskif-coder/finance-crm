// Скрытая вкладка «Спец. условия» по хендоффу 27.10.2026 (право `sk_special`: Мастер Сейлз, «Просто Лев», админ):
// 1) партнёрская СК — отдельные выплаты получателям; 2) спец. условия — особые договорённости (% с порогом или фикс);
// 3) расчёт спец. условий и выплат партнёрской за месяц/квартал. В общий расчёт СК всё это не входит.
// Расчёт — сервер (`app/agency_terms/special.py`): с порогом — «копится» до порога, в месяце прохождения — % со всего
// оборота года задним числом; фикс — равными долями по месяцам срока.
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/http'
import { Modal, MONO, btn, inp, sel } from '@/components/salesTableKit'
import { rub2 } from '@/lib/salesFormat'
import { fmtDate, monthMsk, todayMsk } from '@/lib/dates'
import { moneyNum } from '@/lib/money'
import useLatest from '@/lib/useLatest'
import { FEATURES, calcPeriods, defaultValidFrom, parsePct, periodLabel } from '@/lib/agencyTerms.mjs'
import { CAPS, Card, Field, fmtPct, KpiStrip, MiniSeg, ModePill, NUM, Scroll, Title } from './kit'

const PCOLS = 'minmax(130px,1fr) minmax(170px,1.3fr) minmax(150px,1.2fr) 140px 70px 190px 90px'
const SCOLS = '120px minmax(140px,1fr) minmax(240px,2fr) 70px 120px 170px 40px'
const SPCOLS = 'minmax(200px,1.5fr) minmax(170px,1.2fr) 130px minmax(160px,1.1fr) 70px 130px 120px'
const SCOPES = [['договор', 'contract_id'], ['агентство', 'agency_id'], ['рекламодатель', 'advertiser_id'], ['бренд', 'brand_id']]
const scopeName = (it, names) => (names[(SCOPES.find(([k]) => k === it.scope_kind) || [])[1]] || {})[it.scope_id] || `№${it.scope_id}`
const span = (r) => (r.valid_to ? `с ${fmtDate(r.valid_from)} по ${fmtDate(r.valid_to)}` : `с ${fmtDate(r.valid_from)}`)

function Editor({ item, names, canEdit, onClose, onSaved }) {
  const [s, setS] = useState({ scope_kind: 'агентство', scope_id: null, title: '', valid_from: defaultValidFrom(todayMsk()),
    valid_to: null, note: '', ...item, percent: item.percent != null ? String(item.percent).replace('.', ',') : '',
    amount: item.amount != null ? String(item.amount).replace('.', ',') : '', threshold: item.threshold != null ? String(item.threshold) : '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const key = (SCOPES.find(([k]) => k === s.scope_kind) || [])[1]
  const list = Object.entries(names[key] || {}).map(([id, name]) => ({ id: Number(id), name }))
    .sort((a, b) => String(a.name).localeCompare(String(b.name), 'ru'))
  const set = (k) => (e) => setS((x) => ({ ...x, [k]: e.target.value }))
  const save = async () => {
    setBusy(true); setErr('')
    const body = { ...s, percent: s.percent === '' ? null : parsePct(s.percent), amount: s.amount === '' ? null : moneyNum(s.amount),
      threshold: s.threshold === '' ? null : moneyNum(s.threshold), valid_to: s.valid_to || null }
    try {
      if (s.id) await api.put(`/agency-terms/special/${s.id}`, body, auth())
      else await api.post('/agency-terms/special', body, auth())
      onSaved()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить') } finally { setBusy(false) }
  }
  const footer = (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center', width: '100%' }}>
      <span style={{ flex: 1, fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>
      <button type="button" style={btn(false)} disabled={busy} onClick={onClose}>{canEdit ? 'Отмена' : 'Закрыть'}</button>
      {canEdit && <button type="button" style={btn(true)} disabled={busy} onClick={save}>Сохранить</button>}
    </div>
  )
  const field = (label, el, hint) => <Field label={label} hint={hint}>{el}</Field>
  return (
    <Modal title={s.id ? 'Спец. условие' : 'Новое спец. условие'} width={680} footer={footer} onClose={() => { if (!busy) onClose() }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', padding: '6px 0 10px' }}>
        {field('К чему *', <select value={s.scope_kind} disabled={!canEdit} style={{ ...sel, width: '100%' }}
          onChange={(e) => setS((x) => ({ ...x, scope_kind: e.target.value, scope_id: null }))}>
          {SCOPES.map(([k]) => <option key={k} value={k}>{k}</option>)}</select>)}
        {field(`${s.scope_kind} *`, <select value={s.scope_id ?? ''} disabled={!canEdit} style={{ ...sel, width: '100%' }}
          onChange={(e) => setS((x) => ({ ...x, scope_id: e.target.value ? Number(e.target.value) : null }))}>
          <option value="">— выберите —</option>{list.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>)}
        <div style={{ gridColumn: '1 / -1' }}>{field('Условие *', <input value={s.title} disabled={!canEdit} placeholder="ретро-бонус при обороте от 30 млн за год…"
          onChange={set('title')} style={{ ...inp, width: '100%' }} />)}</div>
        {field('%', <input value={s.percent} disabled={!canEdit} inputMode="decimal" onChange={set('percent')} style={{ ...inp, fontFamily: MONO, textAlign: 'right' }} />,
          'процент от оборота объекта — или фикс справа')}
        {field('или фикс, ₽', <input value={s.amount} disabled={!canEdit} inputMode="decimal" onChange={set('amount')} style={{ ...inp, fontFamily: MONO, textAlign: 'right' }} />,
          'делится равными долями по месяцам срока')}
        {field('Порог оборота за год, ₽', <input value={s.threshold} disabled={!canEdit || s.percent === ''} inputMode="decimal" onChange={set('threshold')}
          style={{ ...inp, fontFamily: MONO, textAlign: 'right' }} />, 'только у процента: до порога «копится», после — % со всего оборота года')}
        <span />
        {field('Действует с *', <input type="date" value={s.valid_from || ''} disabled={!canEdit} onChange={set('valid_from')} style={inp} />)}
        {field('Действует по', <input type="date" value={s.valid_to || ''} disabled={!canEdit} onChange={(e) => setS((x) => ({ ...x, valid_to: e.target.value || null }))} style={inp} />,
          'у фикса обязательно')}
        <div style={{ gridColumn: '1 / -1' }}>{field('Примечание', <input value={s.note || ''} disabled={!canEdit} onChange={set('note')} style={{ ...inp, width: '100%' }} />)}</div>
      </div>
    </Modal>
  )
}

function Partners({ rules, names, canEdit, onOpen }) {
  return (
    <Card title={<Title>Партнёрская СК · отдельные выплаты</Title>}
      note="отдельная выплата получателю · на агентство или на производителя и его бренды · основную СК не уменьшает"
      right={canEdit && <span onClick={() => onOpen({ kind: 'партнёрская', mode: 'постоплата' })} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center',
        height: 30, padding: '0 12px', border: '1px solid var(--accent-border)', borderRadius: 9, color: 'var(--accent)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+ партнёрская</span>}>
      <Scroll min={1060}>
        <div style={{ display: 'grid', gridTemplateColumns: PCOLS, gap: 14, padding: '0 10px 8px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
          <span>Агентство / рекламодатель</span><span>Получатель выплаты</span><span>Уточнение</span><span>Способ</span>
          <span style={{ textAlign: 'right' }}>СК</span><span>Действует</span><span />
        </div>
        {rules.map((r) => {
          const side = r.agency_id != null ? ['agency_id', 'агентство'] : r.advertiser_id != null ? ['advertiser_id', 'рекламодатель · производитель'] : null
          const tags = FEATURES.filter(([k]) => r[k] != null && (!side || k !== side[0])).map(([k, label]) => `${label} ${(names[k] || {})[r[k]] || `№${r[k]}`}`)
          return (
            <div key={r.id} onClick={() => onOpen(r)} style={{ display: 'grid', gridTemplateColumns: PCOLS, gap: 14, alignItems: 'center', padding: '8px 10px',
              borderBottom: '1px solid var(--border-row)', borderRadius: 9, cursor: 'pointer' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{side ? (names[side[0]] || {})[r[side[0]]] : '—'}</span>
                <span style={{ ...CAPS, color: 'var(--text-faint)' }}>{side ? side[1] : 'без стороны'}</span>
              </span>
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{names.recipient_id?.[r.recipient_id] || '—'}</span>
              <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {tags.map((g) => <span key={g} style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 7px', background: 'var(--bg-subtle)',
                  border: '1px solid var(--border-inner)', borderRadius: 6, fontSize: 11, color: 'var(--text-secondary)' }}>{g}</span>)}
              </span>
              <ModePill mode={r.mode} />
              <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, textAlign: 'right' }}>{fmtPct(r.percent)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>{span(r)}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textAlign: 'right' }}>{canEdit ? 'править' : 'смотреть'} →</span>
            </div>)
        })}
      </Scroll>
      {!rules.length && <span style={{ padding: '18px 0', textAlign: 'center', fontSize: 12.5, color: 'var(--text-muted)' }}>Партнёрских условий нет</span>}
    </Card>
  )
}

function Specials({ items, names, canEdit, onOpen, onDelete }) {
  return (
    <Card title={<>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 24, padding: '0 9px', borderRadius: 7, background: 'var(--violet-tint)',
        color: 'var(--violet-fg)', fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>право «спец. условия»</span>
      <Title>Спец. условия</Title>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>особые договорённости · в общий расчёт СК не входят</span></>}
      right={canEdit && <span onClick={() => onOpen({})} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px',
        background: 'var(--accent)', color: 'var(--on-accent)', borderRadius: 10, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>+ спец. условие</span>}>
      <Scroll min={960}>
        <div style={{ display: 'grid', gridTemplateColumns: SCOLS, gap: 14, padding: '0 10px 8px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
          <span>К чему</span><span>Название</span><span>Условие</span><span style={{ textAlign: 'right' }}>%</span><span style={{ textAlign: 'right' }}>Сумма</span><span>Срок</span><span />
        </div>
        {items.map((s) => (
          <div key={s.id} onClick={() => onOpen(s)} style={{ display: 'grid', gridTemplateColumns: SCOLS, gap: 14, alignItems: 'center', padding: '9px 10px',
            borderBottom: '1px solid var(--border-row)', borderRadius: 9, cursor: 'pointer' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifySelf: 'start', height: 22, padding: '0 8px', background: 'var(--bg-subtle)',
              border: '1px solid var(--border-inner)', borderRadius: 6, fontSize: 11, color: 'var(--text-secondary)' }}>{s.scope_kind}</span>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{scopeName(s, names)}</span>
            <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{s.title}{s.threshold ? ` · порог ${rub2(s.threshold)}` : ''}</span>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{s.percent == null ? '—' : fmtPct(s.percent)}</span>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{s.amount == null ? '—' : rub2(s.amount)}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>{span(s)}</span>
            <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
              {canEdit && <span onClick={(e) => { e.stopPropagation(); onDelete(s) }} title="Удалить — с подтверждением" style={{ display: 'inline-flex',
                alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 7, color: 'var(--text-faint)', cursor: 'pointer' }}>✕</span>}
            </span>
          </div>))}
      </Scroll>
      {!items.length && <span style={{ padding: '26px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Спец. условий пока нет</span>}
    </Card>
  )
}

function SpecialCalc({ names, tick }) {
  const { periods, initial } = calcPeriods(monthMsk())
  const [period, setPeriod] = useState(initial)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const latest = useLatest()
  useEffect(() => {
    const fresh = latest()
    api.get(`/agency-terms/special/calc?period=${period}`, auth()).then((r) => { if (fresh()) { setData(r.data); setErr('') } })
      .catch((e) => { if (fresh()) setErr(e.response?.data?.detail || 'Расчёт спец. условий не загрузился') })
  }, [period, tick])          // eslint-disable-line react-hooks/exhaustive-deps
  const tone = (st) => (st === 'копится' ? ['var(--warning-tint)', 'var(--warning-fg)', 'var(--warning)']
    : st === 'не действует' ? ['var(--bg-subtle)', 'var(--text-muted)', 'var(--text-disabled)'] : ['var(--income-tint)', 'var(--income-fg)', 'var(--income)'])
  const rows = data ? [
    ...data.items.map((i) => {
      const fix = i.percent == null
      const prog = fix ? (i.months ? i.month_no / i.months : 0) : i.threshold ? Math.min(1, (i.ytd || 0) / i.threshold) : null
      return { key: `s${i.id}`, name: `${scopeName(i, names)} · ${fix ? 'фикс' : i.threshold ? 'ретро-бонус' : 'процент'}`, text: i.title,
        basis: fix ? `фикс ${rub2(i.amount)} за ${i.months} мес.` : `оборот ${i.scope_kind === 'агентство' ? 'агентства' : i.scope_kind === 'бренд' ? 'бренда' : i.scope_kind === 'договор' ? 'договора' : 'рекламодателя'}${i.threshold ? ', год нарастающим' : ''}`,
        base: i.base, prog, progC: fix ? 'var(--accent)' : i.status === 'копится' ? 'var(--warning)' : 'var(--income)',
        progText: fix ? `месяц ${i.month_no} из ${i.months}` : i.threshold ? `${rub2(i.ytd)} из ${rub2(i.threshold)}${i.status === 'начислено' ? ' · порог пройден' : ''}` : 'без порога',
        rate: fix ? 'фикс' : fmtPct(i.percent), acc: i.accrued, status: i.status }
    }),
    ...data.partners.map((p) => ({ key: `p${p.rule_id}:${p.recipient_id}`, name: `Партнёрская · ${p.recipient || '—'}`, text: `сделок ${p.deals}`,
      basis: 'база ДС закрытых сделок', base: p.base, prog: null, progText: '', rate: fmtPct(p.percent), acc: p.accrued, status: p.status })),
  ] : []
  return (
    <Card title={<><Title>Расчёт спец. условий · {periodLabel(period)}</Title>
      <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>по закрытым сделкам · отдельно от общего расчёта СК</span></>}
      right={<span style={{ marginLeft: 'auto' }}><MiniSeg subtle h={26} value={period} opts={periods} onPick={setPeriod} /></span>}>
      {err && <div style={{ fontSize: 13, color: 'var(--danger-fg)', paddingBottom: 8 }}>{err}</div>}
      {data && <>
        <div style={{ paddingBottom: 12, borderBottom: '1px solid var(--border-inner)' }}>
          <KpiStrip flat size={26} min={220} items={[
            ['Начислено за период', rub2(data.kpi.accrued), 'var(--violet-fg)', `${rows.length} ${rows.length === 1 ? 'условие' : 'условия'}`],
            ['Копится до порога', String(data.kpi.accumulating), 'var(--warning-fg)', 'начислятся после достижения порога'],
            ['С начала года', rub2(data.kpi.year), 'var(--text-primary)', 'начислено по спец. условиям и партнёрской'],
          ]} />
        </div>
        <Scroll min={1080}>
          <div style={{ display: 'grid', gridTemplateColumns: SPCOLS, gap: 14, padding: '10px 10px 8px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
            <span>Условие</span><span>База расчёта</span><span style={{ textAlign: 'right' }}>База за период</span><span>Порог / прогресс</span>
            <span style={{ textAlign: 'right' }}>Ставка</span><span style={{ textAlign: 'right' }}>Начислено</span><span>Статус</span>
          </div>
          {rows.map((c) => {
            const [bg, fg, dot] = tone(c.status)
            return (
              <div key={c.key} style={{ display: 'grid', gridTemplateColumns: SPCOLS, gap: 14, alignItems: 'center', padding: '9px 10px', borderBottom: '1px solid var(--border-row)' }}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>{c.name}</span>
                  <span style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.text}</span>
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{c.basis}</span>
                <span style={NUM}>{c.base == null ? '—' : rub2(c.base)}</span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                  {c.prog != null && <span style={{ display: 'block', height: 6, borderRadius: 3, background: 'var(--border-inner)', overflow: 'hidden' }}>
                    <span style={{ display: 'block', height: 6, width: `${Math.round(c.prog * 100)}%`, background: c.progC, borderRadius: 3 }} /></span>}
                  <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{c.progText}</span>
                </span>
                <span style={{ ...NUM, fontSize: 12.5, fontWeight: 700 }}>{c.rate}</span>
                <span style={{ ...NUM, fontSize: 13, fontWeight: 700, color: c.acc ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{rub2(c.acc)}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, justifySelf: 'start', height: 24, padding: '0 9px', borderRadius: 7, background: bg,
                  color: fg, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: dot }} />{c.status}</span>
              </div>)
          })}
          {!!rows.length && (
            <div style={{ display: 'grid', gridTemplateColumns: SPCOLS, gap: 14, padding: '10px 10px 2px', fontWeight: 700 }}>
              <span style={CAPS}>Итого начислено</span><span /><span /><span /><span />
              <span style={{ ...NUM, fontSize: 13 }}>{rub2(data.kpi.accrued)}</span><span />
            </div>)}
        </Scroll>
        {!rows.length && <span style={{ padding: '22px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>За {periodLabel(period)} начислять нечего</span>}
        <span style={{ padding: '10px 10px 0', fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          Процентное условие с порогом начисляется только после достижения порога, до этого — «копится»; в месяце прохождения — со всего оборота
          года задним числом. Фикс начисляется равными долями по месяцам срока. Квартал — сумма месяцев.</span>
      </>}
    </Card>
  )
}

export default function SpecialTab({ names, canEdit, tick, onOpenRule, reloadKey }) {
  const [items, setItems] = useState(null)
  const [partners, setPartners] = useState([])
  const [err, setErr] = useState('')
  const [edit, setEdit] = useState(null)
  const load = () => {
    api.get('/agency-terms/special', auth()).then((r) => { setItems(r.data); setErr('') })
      .catch((e) => setErr(e.response?.data?.detail || 'Спец. условия не загрузились'))
    api.get('/agency-terms/special/partner', auth()).then((r) => setPartners(r.data))
      .catch((e) => setErr(e.response?.data?.detail || 'Партнёрская СК не загрузилась'))
  }
  useEffect(() => { load() }, [tick, reloadKey])          // eslint-disable-line react-hooks/exhaustive-deps
  const removeItem = async (it) => {
    if (!window.confirm(`Удалить спец. условие «${it.title}»?`)) return
    try { await api.delete(`/agency-terms/special/${it.id}`, auth()); load() } catch (e) { setErr(e.response?.data?.detail || 'Не удалось удалить') }
  }
  return (
    <>
      {err && <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}
      <Partners rules={partners} names={names} canEdit={canEdit} onOpen={onOpenRule} />
      <Specials items={items || []} names={names} canEdit={canEdit} onOpen={setEdit} onDelete={removeItem} />
      <SpecialCalc names={names} tick={tick} />
      {edit && <Editor item={edit} names={names} canEdit={canEdit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
    </>
  )
}
