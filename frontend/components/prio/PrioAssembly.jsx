/**
 * Карточка сделки · «Приоритезация · сборка запроса» (владелец 19.10.2026; раскладка — правки аккаунтов по живому процессу,
 * хендофф `docs/приоритезация2Z.zip`). Собирает аккаунт: общая часть одна на все площадки; по площадке — цель, ЕРИД и
 * посадочная (даём мы); SKU вписывает площадка. Действие в строке — по статусу. Таблица БЕЗ горизонтальной прокрутки:
 * колонки резиновые, длинное — многоточием с полным текстом в подсказке.
 * Сервер: `/api/prio/deal/{id}` (`app/routers/prio.py`, логика — `app/prio`).
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { MONO, UI, btn, btnSm, inp } from '@/components/salesTableKit'
import { fmtDateTimeShort } from '@/lib/dates'
import { fmtDateFull, grp } from '@/lib/salesFormat'

const CAP = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const ELL = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }
// Тон статуса: [фон, рамка, текст]
const TONE = {
  'черновик': ['var(--bg-subtle)', 'var(--border-card)', 'var(--text-muted)'],
  'у площадки': ['var(--violet-tint)', 'var(--violet-border)', 'var(--violet-fg)'],
  'правки': ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-text)'],
  'согласовано': ['var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)'],
  'идёт': ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)'],
  'остановлено': ['var(--bg-subtle)', 'var(--border-card)', 'var(--text-muted)'],
  'отказ': ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger-fg)'],
}
const GRID = 'minmax(0,1.15fr) minmax(0,.7fr) minmax(0,1fr) minmax(0,1.5fr) minmax(0,.75fr) minmax(0,.95fr) minmax(0,1fr)'
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 10 || h >= 20) ? b : c }
const count = (s) => (s || '').split(/[,\n]/).map(x => x.trim()).filter(Boolean).length

function Pill({ s, n }) {
  const [bg, bd, fg] = TONE[s] || TONE['черновик']
  const empty = n === 0
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, fontSize: 12, fontWeight: 600,
      whiteSpace: 'nowrap', background: empty ? 'var(--bg-card)' : bg, border: `1px solid ${empty ? 'var(--border-card)' : bd}`, color: empty ? 'var(--text-faint)' : fg }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: 'currentColor' }} />{s}{n != null && <b style={{ fontFamily: MONO }}>{n}</b>}
    </span>
  )
}

function Field({ label, hint, children }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <span style={CAP}>{label}</span>{children}
      {!!hint && <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{hint}</span>}
    </label>
  )
}

// Общая часть — модульный уровень: внутри поля ввода (ловушка фокуса).
function Common({ c, canEdit, busy, onSave }) {
  const [v, setV] = useState(c)
  const dirty = ['product_name', 'erid_meta', 'target_competitors', 'target_mnn', 'target_meta'].some(k => (v[k] || '') !== (c[k] || ''))
  const set = (k) => (e) => setV(x => ({ ...x, [k]: e.target.value }))
  const ta = { ...inp, width: '100%', minHeight: 64, resize: 'none', lineHeight: 1.45 }
  const n = (k) => count(v[k])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div><span style={CAP}>Общая часть</span> <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>одна на все площадки · заполняет аккаунт · площадка видит, но не правит</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
        <Field label="Название товара" hint="из бренда сделки, можно поправить">
          <input value={v.product_name} disabled={!canEdit} onChange={set('product_name')} style={{ ...inp, width: '100%' }} /></Field>
        <Field label="Период РК" hint="из сделки">
          <input readOnly value={c.date_start ? `${fmtDateFull(c.date_start)} — ${fmtDateFull(c.date_end)}` : '—'}
            style={{ ...inp, width: '100%', background: 'var(--bg-subtle)', color: 'var(--text-secondary)' }} /></Field>
        <Field label="Данные рекламодателя для ЕРИД" hint="юрлицо и ИНН или «самореклама»">
          <input value={v.erid_meta} disabled={!canEdit} onChange={set('erid_meta')} style={{ ...inp, width: '100%' }} /></Field>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
        <Field label={`Конкуренты · ${n('target_competitors')} ${plural(n('target_competitors'), 'позиция', 'позиции', 'позиций')}`} hint="через запятую">
          <textarea value={v.target_competitors} disabled={!canEdit} onChange={set('target_competitors')} style={ta} /></Field>
        <Field label={`МНН · ${n('target_mnn')} ${plural(n('target_mnn'), 'позиция', 'позиции', 'позиций')}`} hint="действующие вещества · через запятую">
          <textarea value={v.target_mnn} disabled={!canEdit} onChange={set('target_mnn')} style={ta} /></Field>
      </div>
      <Field label={`Ключевые слова и симптомы · ${n('target_meta')} ${plural(n('target_meta'), 'позиция', 'позиции', 'позиций')}`}
        hint="через запятую · площадка видит их, но не правит">
        <textarea value={v.target_meta} disabled={!canEdit} onChange={set('target_meta')} style={{ ...ta, minHeight: 84 }} /></Field>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 11.5, color: dirty ? 'var(--warning-text)' : 'var(--text-faint)' }}>
          {dirty ? 'есть несохранённые изменения' : c.saved_by ? `сохранено: ${c.saved_by} · ${fmtDateTimeShort(c.saved_at)}` : 'ещё не сохранялось'}</span>
        {canEdit && <button type="button" disabled={busy || !dirty} onClick={() => onSave(v)}
          style={{ ...btn(false), marginLeft: 'auto', opacity: busy || !dirty ? 0.5 : 1 }}>Сохранить</button>}
      </div>
    </div>
  )
}

function Landing({ p, canEdit, onSave }) {
  const [edit, setEdit] = useState(false)
  const [v, setV] = useState(p.product_url || '')
  const locked = !canEdit || ['идёт', 'остановлено', 'отказ'].includes(p.status)
  if (edit) {
    return (
      <span style={{ display: 'flex', gap: 4, minWidth: 0 }}>
        <input autoFocus value={v} onChange={e => setV(e.target.value)} placeholder="https://…" style={{ ...inp, padding: '5px 8px', fontSize: 12, flex: 1, minWidth: 0, fontFamily: MONO }} />
        <button type="button" style={btnSm(true)} onClick={async () => { if (await onSave({ product_url: v.trim() || null })) setEdit(false) }}>ОК</button>
      </span>
    )
  }
  if (!p.product_url) return locked ? <span style={{ color: 'var(--text-faint)' }}>—</span>
    : <button type="button" onClick={() => setEdit(true)} style={{ border: 0, background: 'none', padding: 0, color: 'var(--accent)', cursor: 'pointer', fontSize: 12.5, textAlign: 'left' }}>+ указать</button>
  return (
    <span style={{ display: 'flex', gap: 6, alignItems: 'center', minWidth: 0 }}>
      <a href={p.product_url} target="_blank" rel="noreferrer" title={p.product_url} style={{ ...ELL, color: 'var(--accent)', fontFamily: MONO, fontSize: 12 }}>{p.product_url.replace(/^https?:\/\//, '')}</a>
      {!locked && <button type="button" title="Изменить посадочную" onClick={() => setEdit(true)} style={{ border: 0, background: 'none', cursor: 'pointer', color: 'var(--text-faint)', padding: 0 }}>✎</button>}
    </span>
  )
}

function Erid({ p, canEdit, onSave }) {
  const [edit, setEdit] = useState(false)
  const [v, setV] = useState(p.erid || '')
  if (edit) {
    return (
      <span style={{ display: 'flex', gap: 4, minWidth: 0 }}>
        <input autoFocus value={v} onChange={e => setV(e.target.value)} placeholder="ЕРИД" style={{ ...inp, padding: '5px 8px', fontSize: 12, flex: 1, minWidth: 0, fontFamily: MONO }} />
        <button type="button" style={btnSm(true)} onClick={async () => { if (await onSave({ erid: v.trim() || null })) setEdit(false) }}>ОК</button>
      </span>
    )
  }
  const draft = canEdit && ['черновик', 'правки'].includes(p.status)
  if (!p.erid) return draft ? <button type="button" onClick={() => setEdit(true)} style={{ border: 0, background: 'none', padding: 0, color: 'var(--danger-fg)', cursor: 'pointer', fontSize: 12, fontFamily: MONO, textAlign: 'left' }}>нет ЕРИД · указать</button>
    : <span style={{ color: 'var(--danger-fg)', fontFamily: MONO, fontSize: 12 }}>нет ЕРИД</span>
  return (
    <span style={{ display: 'flex', gap: 6, alignItems: 'center', minWidth: 0 }}>
      <span title={p.erid} style={{ ...ELL, fontFamily: MONO, fontSize: 12 }}>{p.erid}</span>
      <button type="button" title="Скопировать ЕРИД" onClick={() => navigator.clipboard?.writeText(p.erid)} style={{ border: 0, background: 'none', cursor: 'pointer', color: 'var(--text-faint)', padding: 0 }}>⧉</button>
      {draft && <button type="button" title="Изменить ЕРИД" onClick={() => setEdit(true)} style={{ border: 0, background: 'none', cursor: 'pointer', color: 'var(--text-faint)', padding: 0 }}>✎</button>}
    </span>
  )
}

const ACTION = { 'черновик': ['send', 'Отправить', true], 'у площадки': ['remind', 'Напомнить', false], 'правки': ['reply', 'Ответить', false],
  'согласовано': ['launch', 'Запустить', true], 'идёт': ['stop', 'Стоп', false], 'остановлено': ['start', 'Старт', false] }

function Row({ p, canEdit, busy, act, edit, remove }) {
  const [reply, setReply] = useState(null)
  const a = ACTION[p.status]
  const blocked = p.status === 'черновик' && p.missing.length > 0
  return (
    <div style={{ borderBottom: '1px solid var(--border-row)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, alignItems: 'center', padding: '11px 4px' }}>
        <span style={{ minWidth: 0 }}>
          <b style={{ ...ELL, display: 'block', fontSize: 13 }} title={p.name}>{p.name}</b>
          <span style={{ fontFamily: MONO, fontSize: 10.5, color: p.site_id ? 'var(--text-faint)' : 'var(--danger-fg)' }}>{p.site_id ? `site_id ${p.site_id}` : 'нет site_id'}</span>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', minWidth: 0 }}
          title={p.index != null ? `расчётный индекс ${p.index}` : 'у площадки нет расчётного индекса'}>
          <span style={{ fontFamily: MONO, fontSize: 12.5, color: p.goal_imp ? 'var(--text-primary)' : 'var(--danger-fg)' }}>{p.goal_imp ? grp(p.goal_imp) : '0'}</span>
          <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{p.status === 'отказ' ? 'выбыла' : p.weight_pct != null ? `вес ${String(p.weight_pct).replace('.', ',')} %` : '—'}</span>
          {p.fact_imp != null && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)' }} title="факт по суточной статистике системы приоритезации">факт {grp(p.fact_imp)}</span>}
        </span>
        <Erid key={p.erid || ''} p={p} canEdit={canEdit} onSave={(x) => edit(p.id, x)} />
        <Landing key={p.product_url || ''} p={p} canEdit={canEdit} onSave={(x) => edit(p.id, x)} />
        <span style={{ fontFamily: MONO, fontSize: 12.5, color: p.product_id ? 'var(--violet-fg)' : 'var(--text-faint)' }}>
          {p.product_id || (p.status === 'у площадки' ? 'ждём' : '—')}</span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
          <Pill s={p.status} />
          {!!p.goal_reached_at && <span style={{ fontSize: 10.5, color: 'var(--success)' }} title={`система остановила ${fmtDateTimeShort(p.goal_reached_at)}: факт достиг цели`}>план выполнен</span>}
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3, minWidth: 0 }}>
          {canEdit && a && (
            <button type="button" disabled={busy || blocked}
              onClick={() => (a[0] === 'reply' ? setReply('') : act(p.id, a[0]))}
              title={blocked ? `Не хватает: ${p.missing.join(', ')}` : undefined}
              style={{ ...btnSm(a[2]), opacity: busy || blocked ? 0.45 : 1,
                ...(a[0] === 'stop' ? { color: 'var(--danger-fg)', borderColor: 'var(--danger-border)' } : {}) }}>{a[1]}</button>
          )}
          {blocked && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--danger-fg)', textAlign: 'right' }}>нет {p.missing.join(', ')}</span>}
          {p.status === 'у площадки' && !!p.reminded_at && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>напомнили {fmtDateTimeShort(p.reminded_at)}</span>}
          {canEdit && p.status === 'черновик' && (
            <button type="button" onClick={() => remove(p.id)} style={{ border: 0, background: 'none', padding: 0, cursor: 'pointer', fontSize: 11, color: 'var(--text-faint)' }}>убрать</button>
          )}
        </span>
      </div>
      {!!p.remark && ['правки', 'отказ'].includes(p.status) && (
        <div style={{ margin: '0 4px 11px', padding: '9px 12px', borderRadius: 10, fontSize: 12.5,
          background: p.status === 'отказ' ? 'var(--danger-tint)' : 'var(--warning-tint)',
          border: `1px solid ${p.status === 'отказ' ? 'var(--danger-border)' : 'var(--warning-border)'}` }}>
          <span style={{ ...CAP, color: p.status === 'отказ' ? 'var(--danger-fg)' : 'var(--warning-text)' }}>
            {p.status === 'отказ' ? 'отказ площадки' : 'замечание площадки'}</span>
          <span style={{ fontSize: 10.5, color: 'var(--text-faint)', marginLeft: 8 }}>{fmtDateTimeShort(p.remark.at)}</span>
          <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>{p.name} {p.status === 'отказ' ? 'отказала' : 'вернула с замечанием'}: «{p.remark.text}»</div>
          {reply != null && (
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <input autoFocus value={reply} onChange={e => setReply(e.target.value)} placeholder="ответ площадке" style={{ ...inp, flex: 1 }} />
              <button type="button" style={btn(false)} onClick={() => setReply(null)}>Отмена</button>
              <button type="button" disabled={busy || !reply.trim()} style={{ ...btn(true), opacity: busy || !reply.trim() ? 0.5 : 1 }}
                onClick={async () => { if (await act(p.id, 'reply', reply.trim())) setReply(null) }}>Отправить снова</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AddRow({ pubs, taken, busy, onAdd }) {
  const [open, setOpen] = useState(false)
  const [pid, setPid] = useState('')
  const list = pubs.filter(x => !taken.includes(x.id))
  if (!open) return <button type="button" onClick={() => setOpen(true)} style={{ ...btnSm(false), alignSelf: 'flex-start', marginTop: 8 }}>+ площадка</button>
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
      <select value={pid} onChange={e => setPid(e.target.value)} style={{ ...inp, minWidth: 220 }}>
        <option value="">— площадка —</option>
        {list.map(x => <option key={x.id} value={x.id}>{x.name}{x.site_id ? '' : ' · нет site_id'}</option>)}
      </select>
      <button type="button" style={btn(false)} onClick={() => setOpen(false)}>Отмена</button>
      <button type="button" disabled={busy || !pid} style={{ ...btn(true), opacity: busy || !pid ? 0.5 : 1 }}
        onClick={async () => { if (await onAdd(Number(pid))) { setOpen(false); setPid('') } }}>Добавить</button>
      <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>цель раскладывается сама — по расчётному индексу площадки</span>
    </div>
  )
}

export default function PrioAssembly({ dealId, canEdit, cardStyle }) {
  const [s, setS] = useState(null)
  const [pubs, setPubs] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const base = `/prio/deal/${dealId}`
  const load = useCallback(() => {
    api.get(base, auth()).then(r => { setS(r.data); setErr('') }).catch(e => setErr(e?.response?.data?.detail || 'Запрос не загрузился'))
  }, [base])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (canEdit) api.get('/prio/publishers', auth()).then(r => setPubs(r.data))
      .catch(e => { setPubs([]); setErr(e?.response?.data?.detail || 'Список площадок не загрузился') })   // check-screens: сбой — вслух
  }, [canEdit])
  const call = async (fn) => {
    setBusy(true); setErr('')
    try { const r = await fn(); if (r?.data) setS(r.data); if (r?.data?.failed?.length) setErr(r.data.failed.map(f => f.error).join('; ')); return true }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось'); return false }
    finally { setBusy(false) }
  }
  if (!s) return err ? <div style={{ ...cardStyle, color: 'var(--danger-fg)', fontSize: 12.5 }}>{err}</div> : null
  const act = (pid, a, text) => call(() => api.post(`${base}/placements/${pid}/${a}`, { text: text || null }, auth()))
  const edit = (pid, x) => call(() => api.put(`${base}/placements/${pid}`, x, auth()))
  const remove = (pid) => call(() => api.delete(`${base}/placements/${pid}`, auth()))
  return (
    <div style={{ ...cardStyle, fontFamily: UI }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 17, fontWeight: 800 }}>Приоритезация · сборка запроса</div>
          <div style={{ ...CAP, fontWeight: 600, marginTop: 2 }}>{s.deal_code}</div>
        </div>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {s.pipeline.map((x, i) => <span key={x.status} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {i > 0 && <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>→</span>}<Pill s={x.status} n={x.count} /></span>)}
        </span>
      </div>
      <div style={{ borderTop: '1px solid var(--border-row)', margin: '14px 0', paddingTop: 14 }}>
        <Common key={s.common.saved_at || 'new'} c={s.common} canEdit={canEdit} busy={busy}
          onSave={(v) => call(() => api.put(`${base}/common`, v, auth()))} />
      </div>
      <div style={{ borderTop: '1px solid var(--border-row)', paddingTop: 14 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
          <span style={CAP}>Площадки</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>одна площадка — одна РК · объём {grp(s.plan_volume)} раскладывается по расчётному индексу площадок</span>
          <span style={{ marginLeft: 'auto', fontSize: 11.5, display: 'inline-flex', gap: 12 }}>
            <span style={{ color: 'var(--violet-fg)' }}>■ вписывает площадка</span><span style={{ color: 'var(--accent)' }}>■ даём мы</span></span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '0 4px 8px', borderBottom: '1px solid var(--border-card)', ...CAP, fontWeight: 600 }}>
          <span>Площадка</span><span style={{ textAlign: 'right' }}>Цель · вес</span><span>ЕРИД</span>
          <span style={{ color: 'var(--accent)' }}>Посадочная</span><span style={{ color: 'var(--violet-fg)' }}>SKU</span><span>Статус</span><span style={{ textAlign: 'right' }}>Действие</span>
        </div>
        {s.no_index && <div style={{ margin: '8px 0', padding: '8px 12px', borderRadius: 10, fontSize: 12.5, background: 'var(--warning-tint)',
          border: '1px solid var(--warning-border)', color: 'var(--warning-text)' }}>
          У площадок запроса нет расчётного индекса — объём поделён поровну. Индекс считает балансировщик (Трафики → Балансировщик).</div>}
        {s.placements.length === 0 && <div style={{ padding: '14px 4px', fontSize: 12.5, color: 'var(--text-faint)' }}>Площадок ещё нет — добавьте.</div>}
        {s.placements.map(p => <Row key={`${p.id}:${p.status}:${p.remark?.at || ''}`} p={p} canEdit={canEdit} busy={busy} act={act} edit={edit} remove={remove} />)}
        {canEdit && <AddRow pubs={pubs} taken={s.placements.map(p => p.publisher_id)} busy={busy}
          onAdd={(publisher_id) => call(() => api.post(`${base}/placements`, { publisher_id }, auth()))} />}
        {!!err && <div style={{ fontSize: 12, color: 'var(--danger-fg)', marginTop: 8 }}>{err}</div>}
        {canEdit && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 14 }}>
            <span style={{ fontSize: 11.5, color: 'var(--text-faint)', flex: '1 1 260px' }}>
              «Отправить площадкам» — все готовые черновики разом. «Запустить» — заводит РК в системе приоритезации и включает показ по календарю.</span>
            <button type="button" disabled={busy || !s.ready_to_send} onClick={() => call(() => api.post(`${base}/bulk/send`, {}, auth()))}
              style={{ ...btn(false), opacity: busy || !s.ready_to_send ? 0.5 : 1 }}>Отправить площадкам · {s.ready_to_send}</button>
            <button type="button" disabled={busy || !s.ready_to_launch} onClick={() => call(() => api.post(`${base}/bulk/launch`, {}, auth()))}
              style={{ ...btn(true), opacity: busy || !s.ready_to_launch ? 0.5 : 1 }}>Запустить согласованные · {s.ready_to_launch}</button>
          </div>
        )}
      </div>
    </div>
  )
}
