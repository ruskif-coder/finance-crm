// Вкладка «Условия работы» (владелец 27.10.2026): договорённости с агентствами и рекламодателями, которые аккаунт учитывает
// при сборке медиаплана — фиксированный CPM, бонусные отчёты, деление бюджета. Показ в МП — плашкой под брифом
// (`components/agencyTerms/WorkTermsNote.jsx`). Права — как у «Агентских условий»: смотрят продажи и аккаунты, правят мастера.
import { useEffect, useMemo, useState } from 'react'
import api, { auth } from '@/lib/http'
import { Modal, MONO, btn, inp, sel } from '@/components/salesTableKit'
import { rub0 } from '@/lib/salesFormat'
import { fmtDate, todayMsk } from '@/lib/dates'
import { moneyNum } from '@/lib/money'
import { defaultValidFrom, workBonuses } from '@/lib/agencyTerms.mjs'
import { CAPS, Card, Field, Pick, Scroll, Title } from './kit'

const COLS = 'minmax(120px,.9fr) minmax(150px,1.1fr) minmax(90px,.7fr) minmax(280px,2.6fr) minmax(170px,1.2fr) 120px 150px 40px'
// Креативы / отчёты бонусом (владелец 27.10.2026): флажок и «при каком условии»; снял флажок — комментарий не сохранится
function BonusField({ label, on, note, disabled, onToggle, onNote }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, cursor: disabled ? 'default' : 'pointer' }}>
        <input type="checkbox" checked={!!on} disabled={disabled} onChange={(e) => onToggle(e.target.checked)} />{label}</label>
      {!!on && <input value={note || ''} disabled={disabled} onChange={(e) => onNote(e.target.value)} placeholder="при каком условии: например, при бюджете от 1 млн до НДС"
        style={{ ...inp, width: '100%' }} />}
    </div>
  )
}

export function BonusChips({ item, size = 11 }) {
  const list = workBonuses(item)
  if (!list.length) return null
  return (
    <span style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {list.map((b) => (
        <span key={b.key} title={b.note ? `${b.label} — ${b.note}` : b.label} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 4, maxWidth: '100%', padding: '2px 7px',
          borderRadius: 6, background: 'var(--income-tint)', color: 'var(--income-fg)', fontSize: size, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {b.label}{!!b.note && <span style={{ fontWeight: 500 }}>· {b.note}</span>}</span>))}
    </span>
  )
}

function Editor({ item, opts, canEdit, onClose, onSaved }) {
  const [w, setW] = useState({ valid_from: defaultValidFrom(todayMsk()), valid_to: null, body: '', mail_subject: '', comment: '', ...item,
    commit_net: item.commit_net != null ? String(item.commit_net) : '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (v) => setW((x) => ({ ...x, [k]: v }))
  const brands = (opts.brands || []).filter((b) => !w.advertiser_id || b.advertiser_id === w.advertiser_id)
  const save = async () => {
    setBusy(true); setErr('')
    const body = { ...w, commit_net: w.commit_net === '' ? null : moneyNum(w.commit_net), valid_to: w.valid_to || null }
    try {
      if (w.id) await api.put(`/agency-terms/work/${w.id}`, body, auth())
      else await api.post('/agency-terms/work', body, auth())
      onSaved()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить') } finally { setBusy(false) }
  }
  const field = (label, el, hint) => <Field label={label} hint={hint}>{el}</Field>
  const footer = (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center', width: '100%' }}>
      <span style={{ flex: 1, fontSize: 12, color: err ? 'var(--danger-fg)' : 'var(--text-muted)' }}>
        {err || 'Показывается в медиаплане под брифом, если агентство, рекламодатель, бренд и услуга совпали'}</span>
      <button type="button" style={btn(false)} disabled={busy} onClick={onClose}>{canEdit ? 'Отмена' : 'Закрыть'}</button>
      {canEdit && <button type="button" style={btn(true)} disabled={busy || !w.body.trim()} onClick={save}>Сохранить</button>}
    </div>
  )
  return (
    <Modal title={w.id ? 'Условие работы' : 'Новое условие работы'} width={760} footer={footer} onClose={() => { if (!busy) onClose() }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', padding: '6px 0 10px' }}>
        <Field label="Агентство"><Pick value={w.agency_id} onChange={set('agency_id')} list={opts.agencies || []} empty="— любое —" disabled={!canEdit} /></Field>
        <Field label="Рекламодатель"><Pick value={w.advertiser_id} onChange={(v) => setW((x) => ({ ...x, advertiser_id: v, brand_id: null }))}
          list={opts.advertisers || []} empty="— любой —" disabled={!canEdit} /></Field>
        <Field label="Бренд"><Pick value={w.brand_id} onChange={set('brand_id')} list={brands} empty="— любой —" disabled={!canEdit} /></Field>
        <Field label="Услуга"><Pick value={w.service_id} onChange={set('service_id')} list={opts.services || []} empty="— любая —" disabled={!canEdit} /></Field>
        <div style={{ gridColumn: '1 / -1' }}>{field('Условие *', <textarea value={w.body} disabled={!canEdit} rows={4} onChange={(e) => set('body')(e.target.value)}
          placeholder="cpm 330 фиксируем · отчёт по продажам от 500 тыс. бонусом · деление бюджета 45/55…"
          style={{ ...inp, width: '100%', resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.45 }} />)}</div>
        {field('Тема письма', <input value={w.mail_subject || ''} disabled={!canEdit} onChange={(e) => set('mail_subject')(e.target.value)} style={{ ...inp, width: '100%' }} />,
          'где договорились — чтобы найти переписку')}
        {field('Коммит, ₽ без НДС', <input value={w.commit_net} disabled={!canEdit} inputMode="decimal" onChange={(e) => set('commit_net')(e.target.value)}
          style={{ ...inp, fontFamily: MONO, textAlign: 'right' }} />)}
        {field('Действует с *', <input type="date" value={w.valid_from || ''} disabled={!canEdit} onChange={(e) => set('valid_from')(e.target.value)} style={inp} />)}
        {field('Действует по', <input type="date" value={w.valid_to || ''} disabled={!canEdit} onChange={(e) => set('valid_to')(e.target.value || null)} style={inp} />, 'пусто — бессрочно')}
        <div style={{ gridColumn: '1 / -1' }}>{field('Комментарий', <input value={w.comment || ''} disabled={!canEdit} onChange={(e) => set('comment')(e.target.value)}
          style={{ ...inp, width: '100%' }} />)}</div>
        <BonusField label="Креативы бонусом" on={w.creatives_bonus} note={w.creatives_bonus_note} disabled={!canEdit}
          onToggle={set('creatives_bonus')} onNote={set('creatives_bonus_note')} />
        <BonusField label="Отчёты бонусом" on={w.reports_bonus} note={w.reports_bonus_note} disabled={!canEdit}
          onToggle={set('reports_bonus')} onNote={set('reports_bonus_note')} />
      </div>
    </Modal>
  )
}

export default function WorkTab({ opts, canEdit, tick }) {
  const [items, setItems] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [agency, setAgency] = useState('')
  const [edit, setEdit] = useState(null)
  const load = () => api.get('/agency-terms/work', auth()).then((r) => { setItems(r.data); setErr('') })
    .catch((e) => setErr(e.response?.data?.detail || 'Условия работы не загрузились'))
  useEffect(() => { load() }, [tick])          // eslint-disable-line react-hooks/exhaustive-deps
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (items || []).filter((w) => (!agency || String(w.agency_id) === agency)
      && (!s || [w.body, w.mail_subject, w.comment, ...Object.values(w.names || {})].some((x) => String(x || '').toLowerCase().includes(s))))
      .sort((a, b) => String(a.names?.agency || 'я').localeCompare(String(b.names?.agency || 'я'), 'ru') || a.id - b.id)
  }, [items, q, agency])
  const agencies = [...new Map((items || []).filter((w) => w.agency_id).map((w) => [w.agency_id, w.names?.agency])).entries()]
    .sort((a, b) => String(a[1]).localeCompare(String(b[1]), 'ru'))
  const removeItem = async (w) => {
    if (!window.confirm('Удалить условие работы?')) return
    try { await api.delete(`/agency-terms/work/${w.id}`, auth()); load() } catch (e) { setErr(e.response?.data?.detail || 'Не удалось удалить') }
  }
  return (
    <>
      {err && <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}
      <Card title={<Title>Условия работы</Title>} note={`договорённости для аккаунта при сборке медиаплана · показано ${shown.length}`}
        right={<>
          {canEdit && <span onClick={() => setEdit({})} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px',
            background: 'var(--accent)', color: 'var(--on-accent)', borderRadius: 10, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>+ условие работы</span>}
          <span style={{ flex: '1 1 100%', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="поиск: агентство, клиент, текст, тема письма"
              style={{ width: 300, height: 32, boxSizing: 'border-box', padding: '0 11px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
                borderRadius: 10, fontSize: 12.5, outline: 'none', fontFamily: 'inherit', color: 'var(--text-primary)' }} />
            <select value={agency} onChange={(e) => setAgency(e.target.value)} style={{ ...sel, height: 32, padding: '0 10px' }}>
              <option value="">все агентства</option>{agencies.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </span></>}>
        <Scroll min={1240}>
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, padding: '0 10px 8px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
            <span>Агентство</span><span>Рекламодатель · бренд</span><span>Услуга</span><span>Условие</span><span>Тема письма</span>
            <span style={{ textAlign: 'right' }}>Коммит</span><span>Действует</span><span />
          </div>
          {shown.map((w) => (
            <div key={w.id} onClick={() => setEdit(w)} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'start', padding: '9px 10px',
              borderBottom: '1px solid var(--border-row)', borderRadius: 9, cursor: 'pointer' }}>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{w.names?.agency || <span style={{ fontWeight: 500, color: 'var(--text-muted)' }}>прямой / любое</span>}</span>
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{[w.names?.advertiser, w.names?.brand].filter(Boolean).join(' · ') || '—'}</span>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{w.names?.service || '—'}</span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
                <span style={{ fontSize: 12.5, lineHeight: 1.45, whiteSpace: 'pre-line', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 4,
                  WebkitBoxOrient: 'vertical' }} title={w.body}>{w.body}</span>
                <BonusChips item={w} />
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{w.mail_subject || '—'}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>{w.commit_net == null ? '—' : rub0(w.commit_net)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>
                {w.valid_to ? `${fmtDate(w.valid_from)}–${fmtDate(w.valid_to)}` : `с ${fmtDate(w.valid_from)}`}</span>
              <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
                {canEdit && <span onClick={(e) => { e.stopPropagation(); removeItem(w) }} title="Удалить — с подтверждением"
                  style={{ color: 'var(--text-faint)', cursor: 'pointer', padding: '0 6px' }}>✕</span>}
              </span>
            </div>))}
        </Scroll>
        {items && !shown.length && <span style={{ padding: '22px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Условий нет</span>}
      </Card>
      {edit && <Editor item={edit} opts={opts} canEdit={canEdit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
    </>
  )
}
