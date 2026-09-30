/**
 * «Актуальные кампании» → креативы размещения: предпросмотр (глаз) и «Отозвать»
 * (владелец 29.09.2026).
 *
 * «Отозвать» — это запрос аккаунту на переделку баннера по стандартной процедуре: ответ
 * площадки становится «на доработку» с причиной. Можно, пока размещение не запущено;
 * решает ядро (app/launch_prep/revoke.py), здесь только форма.
 */
import { useState } from 'react'
import api, { auth } from '../lib/http'
import { PreviewModal } from '../lib/preview'
import { downloadFile } from '../lib/download'
import Sheet, { SHEET_BTN } from '../lib/sheet'
import { C, MONO, btn, inp } from '../lib/ui'

const label = (cr) => `Креатив №${cr.no}${cr.title ? ` · ${cr.title}` : ''}`

/** Креативы, по которым мы отказали площадке в правках (30.09.2026), и подсказка с ответом.
    Такой креатив не крутится; он виден до сверки месяца, как и остальные. */
export const declinedOf = (c) => (c.creatives || []).filter(cr => cr.status === 'отказ')
export const declinedTitle = (c) => declinedOf(c)
  .map(cr => `${label(cr)} — правки не приняты${cr.decline_reason ? `: ${cr.decline_reason}` : ''}`)
  .join('\n')
const fileOf = (cr) => (cr.files || []).find(f => f.preview_url) || (cr.files || [])[0] || null

export const download = (cr) => {
  const f = fileOf(cr)
  // Исходник клиента, без наших вставок: ядро отдаёт площадке оригинал (originals.py).
  if (f?.id) downloadFile(`/tasks/${cr.task_id}/files/${f.id}`, f.name)
}

/** Скачать из строки: один креатив — сразу, несколько — через выбор (`openChooser`). */
export function downloadCampaign(campaign, openChooser) {
  const list = (campaign.creatives || []).filter(fileOf)
  if (list.length === 1) download(list[0])
  else if (list.length > 1) openChooser()
}

/** Глаз: один креатив — сразу превью; несколько — сначала выбор.
    `mode='download'` — тот же выбор, но креатив скачивается. */
export function CampaignPreview({ campaign, onClose, mode = 'preview' }) {
  const list = (campaign.creatives || []).filter(fileOf)
  const [pick, setPick] = useState(list.length === 1 && mode === 'preview' ? list[0] : null)
  if (pick) {
    const f = fileOf(pick)
    return (
      <PreviewModal file={f} title={`${campaign.brand} · ${label(pick)}`} onClose={onClose}
        onDownload={f?.id ? () => downloadFile(`/tasks/${pick.task_id}/files/${f.id}`, f.name) : undefined} />
    )
  }
  return (
    <Sheet title={mode === 'download' ? 'Какой креатив скачать' : 'Какой креатив показать'} meta={campaign.brand} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 16 }}>
        {list.map(cr => (
          <button key={cr.task_id} style={{ ...btn(false), ...SHEET_BTN, justifyContent: 'flex-start' }}
            onClick={() => (mode === 'download' ? (download(cr), onClose()) : setPick(cr))}>{label(cr)}</button>
        ))}
      </div>
    </Sheet>
  )
}

/** «Отозвать»: выбрать согласованный креатив и написать, что поправить. */
export function CampaignRevoke({ campaign, onClose, onDone }) {
  const list = (campaign.creatives || []).filter(cr => cr.revocable)
  const [taskId, setTaskId] = useState(list.length === 1 ? list[0].task_id : null)
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const send = async () => {
    setBusy(true); setErr('')
    try {
      await api.post(`/campaign-creatives/${taskId}/revoke`, { reason: reason.trim() }, auth())
      onDone('Согласование отозвано — аккаунт получил запрос на переделку баннера')
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Не удалось отозвать')
    }
    setBusy(false)
  }
  return (
    <Sheet title="Отозвать согласование" meta={campaign.brand} onClose={onClose}
      footer={(
        <button style={{ ...btn(true), ...SHEET_BTN, background: C.danger }}
          disabled={busy || !taskId || !reason.trim()} onClick={send}>
          {busy ? '…' : 'Отозвать и попросить переделку'}</button>
      )}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16 }}>
        <div style={{ fontSize: 13, color: C.secondary, lineHeight: 1.5 }}>
          Креатив вернётся на переделку по обычной процедуре: аккаунт подготовит новую версию,
          и она придёт к вам новой задачей. Отозвать можно, пока размещение не запущено.
        </div>
        {list.length > 1 && list.map(cr => (
          <label key={cr.task_id} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
            <input type="radio" checked={taskId === cr.task_id} onChange={() => setTaskId(cr.task_id)} />
            {label(cr)}
          </label>
        ))}
        {list.length === 1 && <div style={{ fontFamily: MONO, fontSize: 12, color: C.muted }}>{label(list[0])}</div>}
        <textarea value={reason} onChange={e => setReason(e.target.value)} rows={4} maxLength={500}
          placeholder="Что поправить в баннере"
          style={{ ...inp, width: '100%', boxSizing: 'border-box', resize: 'vertical' }} />
        {!!err && <div style={{ fontSize: 12.5, color: C.danger }}>{err}</div>}
      </div>
    </Sheet>
  )
}
