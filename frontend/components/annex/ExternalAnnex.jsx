/**
 * ДС, подписанный вне системы (владелец 02–03.11.2026).
 *
 * На черновике ДС пакета — «Подписан вне системы»: номер и дата клиентского документа, сам документ (файл или ссылка на
 * документ, ранее выгруженный в ЭДО), сумма с НДС и услуги с суммами — под них потом закрываются. Сверки с раскладкой
 * нет: это контроль аккаунта. ДС становится подтверждённым и подписанным, как наш; конструктор и выгрузка у него закрыты.
 */
import { useEffect, useState } from 'react'
import api, { auth } from '../../lib/api'
import { MONO, Modal, inp, sel, btn, primaryBtn } from '../salesTableKit'
import { grp } from '../../lib/salesFormat'
import safeHref from '../../lib/safeHref'
import { saveBlob, filenameFromResponse } from '@/lib/download'

const LBL = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const num = (v) => parseFloat(String(v || '').replace(/\s/g, '').replace(',', '.')) || 0

// Строка — основная услуга («s:ID») или доп. услуга («a:ID»); единица количества — из справочника (сервер: app/sales/units.py).
function ServiceRow({ row, services, addons, onChange, onRemove }) {
  const [kind, id] = (row.key || ':').split(':')
  const picked = (kind === 's' ? services : addons).find(x => String(x.id) === id)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 150px 170px 28px', gap: 8, alignItems: 'center' }}>
      <select value={row.key} onChange={e => onChange({ ...row, key: e.target.value })} style={sel}>
        <option value="">— услуга —</option>
        <optgroup label="Услуги">{services.map(s => <option key={`s${s.id}`} value={`s:${s.id}`}>{s.name}</option>)}</optgroup>
        <optgroup label="Доп. услуги">{addons.map(s => <option key={`a${s.id}`} value={`a:${s.id}`}>{s.name}</option>)}</optgroup>
      </select>
      <input value={row.amount} onChange={e => onChange({ ...row, amount: e.target.value })} placeholder="сумма с НДС"
             style={{ ...inp, textAlign: 'right', fontFamily: MONO }} />
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <input value={row.volume} onChange={e => onChange({ ...row, volume: e.target.value })} placeholder="кол-во"
               style={{ ...inp, width: 100, textAlign: 'right', fontFamily: MONO }} />
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{picked?.unit || ''}</span>
      </span>
      <span onClick={onRemove} title="убрать строку" style={{ cursor: 'pointer', color: 'var(--text-muted)', textAlign: 'center' }}>✕</span>
    </div>
  )
}

export function ExternalSignButton({ annex, defaultNo, defaultDate, onDone, autoOpen }) {
  const [open, setOpen] = useState(false)
  // Пришли из реестра по «Загрузить внешний ДС» (`?external=1`) — форма открывается сразу.
  useEffect(() => { if (autoOpen) setOpen(true) }, [autoOpen])
  const [services, setServices] = useState([])
  const [addons, setAddons] = useState([])
  const [f, setF] = useState(null)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open) return
    setErr('')
    // Сбой справочника — словами: пустой список читался бы как «услуг нет».
    api.get('/sales/directories/services?only_active=true', auth()).then(r => setServices(r.data?.items || r.data || []))
      .catch(() => setErr('Справочник услуг не загрузился — список пуст не потому, что услуг нет'))
    api.get('/sales/directories/services/addons?only_active=true', auth()).then(r => setAddons(r.data?.items || []))
      .catch(() => setErr('Справочник доп. услуг не загрузился — список пуст не потому, что их нет'))
    setF({ no: defaultNo || '', number: '', date: defaultDate || '', how: 'file', link: '', total: annex.total_amount ? String(annex.total_amount) : '',
           rows: [{ key: '', amount: annex.total_amount ? String(annex.total_amount) : '', volume: '' }] })
    setFile(null)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (e) => setF(s => ({ ...s, [k]: e.target.value }))
  const submit = async () => {
    setBusy(true); setErr('')
    try {
      const body = new FormData()
      body.append('no', f.no); body.append('doc_date', f.date); body.append('total', String(num(f.total)))
      body.append('number', f.number)
      body.append('items', JSON.stringify(f.rows.filter(r => r.key).map(r => {
        const [kind, id] = r.key.split(':')
        return { [kind === 's' ? 'service_id' : 'addon_id']: Number(id), amount: num(r.amount), volume: r.volume === '' ? null : num(r.volume) }
      })))
      if (f.how === 'link') body.append('edo_link', f.link)
      else if (file) body.append('file', file)
      await api.post(`/annexes/${annex.id}/external`, body, auth())
      setOpen(false); if (onDone) onDone()
    } catch (e) { setErr(e?.response?.data?.detail || 'Не получилось') } finally { setBusy(false) }
  }

  const sum = f ? f.rows.reduce((a, r) => a + num(r.amount), 0) : 0
  return (
    <>
      <button onClick={() => setOpen(true)} title="Клиент подписал свой ДС — загрузить его вместо сборки конструктором"
              style={{ ...btn(false), height: 36 }}>Подписан вне системы</button>
      {open && f && (
        <Modal title="ДС подписан вне системы" width={640} onClose={() => setOpen(false)}
               summary="ДС станет подтверждённым и подписанным, как собранный у нас: сделки, УПД и 1С — от него. Документ — файл или ссылка ЭДО."
               footer={<div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', alignItems: 'center' }}>
                 {!!err && <span style={{ color: 'var(--danger-fg)', fontSize: 12.5, marginRight: 'auto' }}>{err}</span>}
                 <button onClick={() => setOpen(false)} style={btn(false)}>Отмена</button>
                 <button onClick={submit} disabled={busy} style={primaryBtn}>{busy ? 'Сохраняю…' : 'Подписан — сохранить'}</button>
               </div>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '16px 20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '120px minmax(0,1fr) 170px', gap: 10 }}>
              <label><div style={LBL}>Номер</div><input type="number" value={f.no} onChange={set('no')} style={{ ...inp, width: '100%', fontFamily: MONO }} /></label>
              <label><div style={LBL}>Как в документе · необязательно</div><input value={f.number} onChange={set('number')} placeholder="Дополнительное соглашение № 30" style={{ ...inp, width: '100%' }} /></label>
              <label><div style={LBL}>Дата</div><input type="date" value={f.date} onChange={set('date')} style={{ ...inp, width: '100%', fontFamily: MONO }} /></label>
            </div>
            <div>
              <div style={{ ...LBL, marginBottom: 6 }}>Документ</div>
              <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 13 }}>
                <label><input type="radio" checked={f.how === 'file'} onChange={() => setF(s => ({ ...s, how: 'file' }))} /> файл</label>
                <label><input type="radio" checked={f.how === 'link'} onChange={() => setF(s => ({ ...s, how: 'link' }))} /> ссылка на документ в ЭДО</label>
              </div>
              {f.how === 'file'
                ? <input type="file" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.tif,.tiff" onChange={e => setFile(e.target.files?.[0] || null)} />
                : <input value={f.link} onChange={set('link')} placeholder="https://…" style={{ ...inp, width: '100%' }} />}
            </div>
            <div>
              <div style={{ ...LBL, marginBottom: 6 }}>Услуги и суммы · под них закрываются</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {f.rows.map((r, i) => (
                  <ServiceRow key={i} row={r} services={services} addons={addons}
                              onChange={nr => setF(s => ({ ...s, rows: s.rows.map((x, k) => k === i ? nr : x) }))}
                              onRemove={() => setF(s => ({ ...s, rows: s.rows.filter((_, k) => k !== i) }))} />
                ))}
                <span onClick={() => setF(s => ({ ...s, rows: [...s.rows, { key: '', amount: '', volume: '' }] }))}
                      style={{ fontSize: 12.5, color: 'var(--accent)', cursor: 'pointer', fontWeight: 600 }}>+ услуга</span>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '200px minmax(0,1fr)', gap: 10, alignItems: 'end' }}>
              <label><div style={LBL}>Сумма ДС с НДС</div><input value={f.total} onChange={set('total')} style={{ ...inp, width: '100%', textAlign: 'right', fontFamily: MONO }} /></label>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>по услугам: <b style={{ fontFamily: MONO }}>{grp(sum)}</b></span>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}

/** Блок подписанного вне системы ДС: документ, сумма и услуги — вместо конструктора и выгрузки. */
export function ExternalAnnexView({ annex, ext, section }) {
  const [err, setErr] = useState('')
  const download = async () => {
    setErr('')
    try {
      const r = await api.get(`/annexes/${annex.id}/external-file`, { ...auth(), responseType: 'blob' })
      saveBlob(r.data, filenameFromResponse(r) || 'ДС')
    } catch (_) { setErr('Файл не скачался') }
  }
  const href = ext.edo_link ? safeHref(ext.edo_link) : null
  return (
    <div style={section}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', borderRadius: 7, background: 'var(--violet-tint)', color: 'var(--violet-fg)', fontSize: 11, fontWeight: 700 }}>подписан вне системы</span>
        {ext.file && <button onClick={download} style={btn(false)}>Скачать документ · {ext.file.name}</button>}
        {href && <a href={href} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, fontWeight: 600 }}>Открыть в ЭДО ↗</a>}
        {!!err && <span style={{ color: 'var(--danger-fg)', fontSize: 12.5 }}>{err}</span>}
      </div>
      <div style={{ ...LBL, marginBottom: 6 }}>Услуги и суммы</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 560 }}>
        {ext.items.map((it, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13 }}>
            <span>{it.service}{it.addon && <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--text-muted)' }}>доп. услуга</span>}</span>
            <span style={{ display: 'flex', gap: 14 }}>
              {it.volume != null && <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{grp(it.volume)} {it.unit}</span>}
              <span style={{ fontFamily: MONO, fontWeight: 700 }}>{grp(it.amount)}</span>
            </span>
          </div>
        ))}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13, borderTop: '1px solid var(--border-row)', paddingTop: 4 }}>
          <span style={{ color: 'var(--text-muted)' }}>Сумма ДС с НДС</span><span style={{ fontFamily: MONO, fontWeight: 700 }}>{grp(annex.total_amount)}</span>
        </div>
      </div>
    </div>
  )
}
