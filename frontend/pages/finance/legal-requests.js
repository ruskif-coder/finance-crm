/**
 * «Юр запросы» (Финансы, 14.10.2026): заявки аккаунтов юристу по пунктам ДС после таблицы МП.
 * Юрист берёт заявку, правит шаблон ДС договора («Шаблон ДС» в реестре договоров) и закрывает её — или отклоняет с ответом.
 * Пока заявка открыта или в работе, её ДС нельзя подтвердить и выгрузить чистовик.
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import { pageAccess } from '@/lib/pageGuard'
import { can, getPermissions } from '@/lib/auth'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { fmtDate, fmtDateTime } from '@/lib/dates'
import BaseTemplateModal from '@/components/annex/BaseTemplateModal'
import { annexTemplatesApi } from '@/lib/annexTemplatesApi'
import { card, th, td, btnSm, primaryBtn, btn, inp, Modal, NoAccessScreen, MONO, UI } from '@/components/salesTableKit'

const TONE = {
  'открыта': { color: 'var(--danger-fg)', background: 'var(--danger-tint)' },
  'в работе': { color: 'var(--accent-fg)', background: 'var(--accent-tint)' },
  'сделана': { color: 'var(--income-fg)', background: 'var(--income-tint)' },
  'отклонена': { color: 'var(--text-secondary)', background: 'var(--bg-subtle)' },
}

function StatusPill({ s }) {
  return <span style={{ display: 'inline-block', minWidth: 78, textAlign: 'center', padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700, ...TONE[s] }}>{s}</span>
}

function CloseModal({ req, kind, onClose, onDone }) {
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const done = kind === 'done'
  const submit = async () => {
    setBusy(true); setErr('')
    try { const res = await api.post(`/legal-requests/${req.id}/${kind}`, { answer }, auth()); onDone(res.data.rebuilt) }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось сохранить') }
    finally { setBusy(false) }
  }
  return (
    <Modal title={done ? 'Заявка выполнена' : 'Отклонить заявку'} width={520} onClose={() => !busy && onClose()}
           footer={<>
             <button type="button" style={btn(false)} disabled={busy} onClick={onClose}>Отмена</button>
             <button type="button" style={primaryBtn} disabled={busy || (!done && !answer.trim())} onClick={submit}>{busy ? 'Сохраняю…' : done ? 'Закрыть заявку' : 'Отклонить'}</button>
           </>}>
      <div style={{ fontSize: 13, lineHeight: 1.6, marginBottom: 10 }}>
        {done
          ? <>Закрыть можно после того, как правка сохранена в шаблоне ДС договора <b>№ {req.contract_number || '—'}</b> (реестр договоров → «Шаблон ДС»). ДС и все следующие по этому шаблону соберутся уже с ней; правка в новом шаблоне договора — ДС заявки переключится на него.</>
          : <>Напишите аккаунту, почему правка не нужна или невозможна.</>}
      </div>
      <textarea value={answer} onChange={e => setAnswer(e.target.value)} rows={4} placeholder={done ? 'Ответ аккаунту (необязательно)' : 'Ответ аккаунту'}
                style={{ ...inp, width: '100%', resize: 'vertical' }} />
      {!!err && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}
    </Modal>
  )
}

export default function LegalRequestsPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [rows, setRows] = useState(null)
  const [scope, setScope] = useState('open')
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [closing, setClosing] = useState(null)
  const [mayEdit, setMayEdit] = useState(false)
  const [tpl, setTpl] = useState(null)        // договор, чей шаблон ДС открыт в редакторе
  const [behind, setBehind] = useState([])    // кастомные шаблоны договоров, отставшие от базы
  useEffect(() => { setMounted(true); setMayEdit(can(getPermissions(), 'legal_requests', 'edit')) }, [])
  const access = pageAccess(router.pathname, mounted)

  const load = useCallback(async () => {
    setErr('')
    annexTemplatesApi.behind().then(setBehind).catch(e => { setBehind([]); setErr(e?.response?.data?.detail || 'Не удалось проверить, отстали ли шаблоны ДС от базового') })
    try { setRows((await api.get(`/legal-requests?status=${scope}`, auth())).data) }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить заявки'); setRows([]) }
  }, [scope])
  useEffect(() => { if (access === 'ok') load() }, [access, load])
  // Вернулись на вкладку — перечитываем заявки; не пока открыт диалог закрытия или редактор шаблона (там несохранённое).
  useRefreshOnReturn(load, { enabled: access === 'ok' && !closing && !tpl })

  const take = async (r) => {
    try { await api.post(`/legal-requests/${r.id}/take`, {}, auth()); load() }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось взять заявку') }
  }

  const head = <><Head><title>Юр запросы · Финансы | SIMB-AD ERP</title></Head><Navbar active="legal" /></>
  if (access === 'denied') return <NoAccessScreen title="Юр запросы: нет доступа" what="Юр запросы" nav={head} />

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      {head}
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '20px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800 }}>Юр запросы</h1>
          <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>правки пунктов ДС после таблицы медиаплана — в шаблон ДС договора</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
            {[['open', 'Открытые'], ['all', 'Все']].map(([k, l]) => (
              <button key={k} type="button" onClick={() => setScope(k)} style={{ ...btnSm(scope === k) }}>{l}</button>
            ))}
          </span>
        </div>
        {!!err && <div style={{ marginBottom: 10, fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}
        {!!note && <div style={{ marginBottom: 10, fontSize: 13, color: 'var(--income-fg)' }}>{note}</div>}
        {!!behind.length && (
          <div style={{ ...card, padding: '14px 16px', marginBottom: 14, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)' }}>
            <div style={{ fontWeight: 800, color: 'var(--warning-fg)', marginBottom: 8 }}>Базовый шаблон изменился · договоров: {behind.length}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginBottom: 10 }}>У этих договоров свой шаблон ДС, а база ушла вперёд. Откройте шаблон и решите: оставить свой или перенять базу.</div>
            {behind.map(b => (
              <div key={b.template_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0', borderTop: '1px solid var(--warning-border)' }}>
                <span style={{ fontWeight: 700, minWidth: 170 }}>№ {b.contract_number || '—'}</span>
                <span style={{ flex: 1, fontSize: 12.5, color: 'var(--text-secondary)' }}>{b.counterparty || '—'}</span>
                <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-faint)' }}>база v{b.known} → v{b.now}</span>
                <button type="button" style={btnSm(false)} onClick={() => setTpl({ id: b.contract_id, number: b.contract_number, format: b.format, templateId: b.template_id })}>Шаблон ДС</button>
              </div>
            ))}
          </div>
        )}
        <div style={{ ...card, padding: '16px 14px', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
            <thead>
              <tr>
                <th style={{ ...th, width: 90 }}>Статус</th>
                <th style={{ ...th, width: 220 }}>Договор · ДС</th>
                <th style={{ ...th, width: 170 }}>Пункт</th>
                <th style={th}>Что просят · ответ</th>
                <th style={{ ...th, width: 170 }}>Кто · когда</th>
                <th style={{ ...th, width: 190, textAlign: 'right' }}>Действие</th>
              </tr>
            </thead>
            <tbody>
              {rows === null && <tr><td colSpan={6} style={{ ...td, color: 'var(--text-faint)' }}>Загрузка…</td></tr>}
              {rows && !rows.length && <tr><td colSpan={6} style={{ ...td, color: 'var(--text-faint)' }}>{scope === 'open' ? 'Открытых заявок нет' : 'Заявок пока не было'}</td></tr>}
              {(rows || []).map(r => (
                <tr key={r.id}>
                  <td style={td}><StatusPill s={r.status} /></td>
                  <td style={td}>
                    <div style={{ fontWeight: 700 }}>№ {r.contract_number || '—'}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.counterparty || '—'}</div>
                    <Link href={`/directory/annexes/${r.annex_id}`} style={{ fontSize: 12, color: 'var(--accent)' }}>
                      {r.annex_number} · {fmtDate(r.period_from)}–{fmtDate(r.period_to)}
                    </Link>
                  </td>
                  <td style={{ ...td, fontSize: 12.5 }}>{r.block}</td>
                  <td style={{ ...td, whiteSpace: 'pre-wrap' }}>
                    {r.text}
                    {!!r.answer && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>Ответ: {r.answer}</div>}
                  </td>
                  <td style={{ ...td, fontSize: 12 }}>
                    <div>{r.created_by || '—'}</div>
                    <div style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{fmtDateTime(r.created_at)}</div>
                    {!!r.taken_by && <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>в работе: {r.taken_by}</div>}
                  </td>
                  <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <button type="button" title="Открыть редактор шаблона ДС этого договора — правка ляжет в него"
                            style={{ ...btnSm(false), marginRight: 6 }} onClick={() => setTpl({ id: r.contract_id, number: r.contract_number, format: r.contract_format, templateId: r.template_id, annexId: r.annex_id })}>Шаблон ДС</button>
                    <span style={{ display: 'inline-block', width: 1, height: 22, background: 'var(--border-card)', margin: '0 10px 0 4px', verticalAlign: 'middle' }} />
                    {mayEdit && r.status === 'открыта' && <button type="button" style={{ ...btnSm(false), marginRight: 6 }} onClick={() => take(r)}>Взять</button>}
                    {mayEdit && ['открыта', 'в работе'].includes(r.status) && <>
                      <button type="button" style={{ ...btnSm(true), marginRight: 6 }} onClick={() => setClosing({ req: r, kind: 'done' })}>Сделано</button>
                      <button type="button" style={btnSm(false)} onClick={() => setClosing({ req: r, kind: 'reject' })}>Отклонить</button>
                    </>}
                    {!['открыта', 'в работе'].includes(r.status) && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{fmtDateTime(r.closed_at)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <BaseTemplateModal open={!!tpl} contract={tpl} onClose={() => { setTpl(null); load() }} />
      {closing && <CloseModal req={closing.req} kind={closing.kind} onClose={() => setClosing(null)} onDone={(rebuilt) => { setClosing(null); setNote(rebuilt || ''); load() }} />}
    </div>
  )
}
