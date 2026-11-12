/**
 * Общие части документов пакета (хендофф «реестр + карточка», 19.10.2026): плашка подписания, кнопки отметок подписи,
 * кнопка «электронный | скан», панель сканов. Ими пользуются карточка ДС (`DsCard`) и расхлоп реестра (`registry/PackDocs`) —
 * разметка одна. С 02.11.2026 подпись — у каждого документа (`sign` с сервера), не у пакета.
 */
import { useRef, useState } from 'react'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { SIGN, signAction } from '@/lib/masterSteps'
import { MONO, UI } from '@/components/salesTableKit'
import safeHref from '@/lib/safeHref'

const CAPS = { fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const ICON = {
  'подписан у нас': 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'выставлен': 'M4 12l16-8-6 16-3-7z', 'подписан': 'M5 12.5l4.5 4.5L19 7.5',
  'отклонён': 'M6 6l12 12M18 6L6 18',
}
const OK = ICON['подписан']
const Svg = ({ d, size = 11, w = 2.2 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
)

// §6: рамка карточки по подписанию; у УПД «не выпущен / не подписан» — --accent-border
/** Скачать файл пакета — скан или PDF из 1С (было собрано вручную в восьми местах). Имя даёт сервер: пакет, контрагент, период
 * и документ (владелец 05.11.2026), а не имя, под которым файл загрузили. */
export const downloadScan = (code, scan, setErr) => downloadFile(`/master-deals/${code}/files/${scan.id}`, null, setErr)

/** Колонка документов комплекта УПД: «электрон. | скан» — Счёт, УПД (+ скан у бумаги), Отчёт; номера, даты и PDF из 1С
 * (с 05.11.2026 их вносит бухгалтер в «Документах для 1С»). Бухгалтер вернула комплект — красная строка и «Исправлено». */
export function KitDocs({ kit, upd_no, paper, code, onPick, setErr, canEdit, onDone }) {
  const f = kit?.onec_files || {}
  const pdf = (file, no) => (file ? { off: false, onDoc: () => downloadScan(code, file, setErr) } : { off: true, offText: no ? 'PDF нет' : 'ждём 1С' })
  const dated = (no, d) => (no ? ` № ${no}${d ? ` от ${String(d).slice(8, 10)}.${String(d).slice(5, 7)}` : ''}` : '')
  return (
    <span data-noexp onClick={e => e.stopPropagation()} style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingLeft: 12, borderLeft: '1px solid var(--accent-border)', alignSelf: 'start' }}>
      <span style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 8, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)', padding: '0 2px' }}>
        <span>электрон.</span><span>{paper ? 'скан · обязательно' : ''}</span></span>
      <DocButton label={`Счёт${dated(kit?.invoice_no, kit?.invoice_date)}`} wide {...pdf(f.invoice, kit?.invoice_no)} />
      <DocButton label={`УПД${dated(kit?.upd_doc_no, kit?.upd_doc_date)}`} wide paper={paper && !!kit} scan={kit?.scan} {...pdf(f.upd, kit?.upd_doc_no)}
        onScan={() => downloadScan(code, kit.scan, setErr)} onPick={() => onPick(`u${upd_no}`)} />
      <DocButton label="Отчёт" off wide />
      {kit?.desk?.state === 'возвращён' && <DeskReturned kit={kit} upd_no={upd_no} code={code} canEdit={canEdit} onDone={onDone} setErr={setErr} />}
      {!!kit?.desk?.question && <DeskQuestion kit={kit} upd_no={upd_no} code={code} canEdit={canEdit} onDone={onDone} setErr={setErr} />}
    </span>
  )
}

/** Бухгалтер вернула комплект из «Документов для 1С»: что не так и «Исправлено» — комплект снова у неё в очереди. */
function DeskReturned({ kit, upd_no, code, canEdit, onDone, setErr }) {
  const [busy, setBusy] = useState(false)
  const fixed = async () => {
    const text = window.prompt('Что исправили? (можно оставить пустым)')
    if (text === null) return
    setBusy(true); setErr?.('')
    try { onDone?.((await api.post(`/master-deals/${code}/upd/${upd_no}/onec-fixed`, { text: text || null }, auth())).data) }
    catch (e) { setErr?.(e?.response?.data?.detail || 'Не удалось отметить') } finally { setBusy(false) }
  }
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 220, padding: '6px 8px', borderRadius: 7, background: 'var(--danger-tint)' }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--danger-fg)' }}>Бухгалтер вернул: {kit.desk.returned || '—'}</span>
      {canEdit && <button type="button" disabled={busy} onClick={fixed}
        style={{ alignSelf: 'flex-start', height: 22, padding: '0 9px', borderRadius: 7, border: '1px solid var(--danger-border)', background: 'var(--bg-card)',
          color: 'var(--danger-fg)', fontFamily: UI, fontSize: 10.5, fontWeight: 700, cursor: busy ? 'default' : 'pointer' }}>Исправлено</button>}
    </span>
  )
}

/** Бухгалтер спросила в «Документах для бухгалтерии», не возвращая комплект: вопрос и «Ответить» — у неё в очереди будет «ответ». */
function DeskQuestion({ kit, upd_no, code, canEdit, onDone, setErr }) {
  const [busy, setBusy] = useState(false)
  const reply = async () => {
    const text = window.prompt(`Ответ бухгалтеру на «${kit.desk.question}»`)
    if (!text || !text.trim()) return
    setBusy(true); setErr?.('')
    try { onDone?.((await api.post(`/master-deals/${code}/upd/${upd_no}/onec-reply`, { text: text.trim() }, auth())).data) }
    catch (e) { setErr?.(e?.response?.data?.detail || 'Не удалось ответить') } finally { setBusy(false) }
  }
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 220, padding: '6px 8px', borderRadius: 7, background: 'var(--accent-tint)' }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-fg)' }}>Бухгалтер спрашивает: {kit.desk.question}</span>
      {canEdit && <button type="button" disabled={busy} onClick={reply}
        style={{ alignSelf: 'flex-start', height: 22, padding: '0 9px', borderRadius: 7, border: '1px solid var(--accent-border)', background: 'var(--bg-card)',
          color: 'var(--accent-fg)', fontFamily: UI, fontSize: 10.5, fontWeight: 700, cursor: busy ? 'default' : 'pointer' }}>Ответить</button>}
    </span>
  )
}

export const signFrame = (s, upd = false) => ({ 'подписан у нас': 'var(--warning-border)', 'выставлен': 'var(--warning-border)', 'подписан': 'var(--income)',
  'отклонён': 'var(--danger-border)' }[s] || (upd ? 'var(--accent-border)' : 'var(--border-card)'))
/** Половина «скан» у кнопки документа — только у бумаги, ушедшей клиенту (ждём скан или он уже приложен). */
export const scanOpen = (doc) => doc?.sign?.channel === 'бумага' && ['выставлен', 'подписан'].includes(doc?.sign?.state)
export const scanKey = (t) => (t.annex_id != null ? `a${t.annex_id}` : `u${t.upd_no}`)

/** ДС, подписанный вне системы, уже в Диадоке (владелец 12.11.2026): статус «уже в ЭДО» и ссылка туда вместо скачивания —
 * своего файла у такого ДС может не быть. Общая для карточки ДС и расхлопа реестра. */
export function InEdo({ link, small = false }) {
  const href = safeHref(link)
  return (
    <span data-noexp onClick={e => e.stopPropagation()} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, alignSelf: 'center' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'var(--accent-tint)', color: 'var(--accent-fg)', border: '1px solid var(--accent-border)',
        borderRadius: small ? 6 : 7, padding: small ? '2px 7px' : '3px 9px', fontSize: small ? 10 : 11, fontWeight: 700, whiteSpace: 'nowrap' }}>
        <Svg d={OK} size={small ? 10 : 11} />уже в ЭДО</span>
      {!!href && <a href={href} target="_blank" rel="noopener noreferrer" title="Открыть ДС в Диадоке"
        style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 9px', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 7,
          background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', textDecoration: 'none' }}>в Диадоке ↗</a>}
    </span>
  )
}

export function SignBadge({ s, small = false }) {
  const [label, bg, bd, fg] = SIGN[s] || SIGN.none
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: bg, color: fg, border: `1px solid ${bd}`, borderRadius: small ? 6 : 7,
      padding: small ? '2px 7px' : '3px 9px', fontSize: small ? 10 : 11, fontWeight: 700, whiteSpace: 'nowrap', alignSelf: 'center' }}>
      {!!ICON[s] && <Svg d={ICON[s]} size={small ? 10 : 11} />}{label}
    </span>
  )
}

/** «электронный | скан»: левая половина — файл (или «ждём 1С»), правая — скан бумажного: зелёный ✓ или жёлтый пунктир «+». */
export function DocButton({ label, off, offText = 'ждём 1С', onDoc, paper, scan, onScan, onPick, wide = false }) {
  const hasScan = paper
  const line = hasScan && !scan ? 'dashed' : 'solid'
  return (
    <span style={{ display: 'inline-flex', minWidth: wide ? 150 : undefined, height: 24, border: `1px ${line} ${off ? 'var(--border-inner)' : hasScan && !scan ? 'var(--warning-border)' : 'var(--border-card)'}`,
      borderRadius: 7, overflow: 'hidden', background: off ? 'var(--bg-subtle)' : 'var(--bg-card)' }}>
      <span title={off ? offText : `Скачать ${label}`} onClick={off ? undefined : onDoc}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, flex: '1 1 auto', padding: '0 8px', color: off ? 'var(--text-disabled)' : 'var(--text-secondary)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', cursor: off ? 'default' : 'pointer' }}>
        {off ? <span aria-hidden>—</span> : <Svg d="M12 4v12M7 11l5 5 5-5M5 20h14" w={2} />}{off ? `${label} · ${offText}` : label}
      </span>
      {hasScan && (scan ? (
        <span title={`Скан: ${scan.filename} — скачать`} onClick={onScan}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0 8px', borderLeft: '1px solid var(--income-border)', background: 'var(--income-tint)', color: 'var(--income-fg)', fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap', cursor: 'pointer' }}>
          <Svg d={OK} size={10} />скан</span>
      ) : (
        <span title="Скана нет — выбрать этот документ в панели сканов" onClick={onPick}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0 8px', borderLeft: '1px dashed var(--warning-border)', background: 'var(--warning-bg)', color: 'var(--warning-fg)', fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap', cursor: 'pointer' }}>
          <Svg d="M12 5v14M5 12h14" size={10} />скан</span>
      ))}
    </span>
  )
}

/** Кнопки следующей отметки подписи документа (ДС — `annex_id`, УПД — `upd_no`). Отказ — с причиной; отправка бумаги — трек
 * по желанию; подпись бумаги ставит скан, а не кнопка. Правила и запреты — на сервере (`doc_sign.py`). */
export function SignActions({ code, url, target, sign, onDone, setErr, small = false }) {
  const [busy, setBusy] = useState(false)
  const next = sign?.next || []
  if (!next.length) return null
  const run = async (state) => {
    let reason = null
    if (state === 'отклонён') {
      reason = window.prompt('Почему клиент отклонил документ? Причина нужна, чтобы его переделать.')
      if (!reason || !reason.trim()) return
    } else if (state === 'выставлен' && sign?.channel === 'бумага') {
      reason = window.prompt('Трек-номер отправки (можно оставить пустым)')
      if (reason === null) return
    }
    setBusy(true); setErr?.('')
    try { onDone((await api.post(url || `/master-deals/${code}/doc-sign`, { ...target, state, reason: reason || null }, auth())).data) }
    catch (e) { setErr?.(e?.response?.data?.detail || 'Не удалось отметить') } finally { setBusy(false) }
  }
  return (
    <span data-noexp onClick={e => e.stopPropagation()} style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap', alignSelf: 'center' }}>
      {next.map(n => (
        <button key={n} type="button" disabled={busy} onClick={() => run(n)}
          style={{ height: small ? 22 : 24, padding: '0 9px', borderRadius: 7, border: `1px solid ${n === 'отклонён' ? 'var(--danger-border)' : 'var(--accent-border)'}`,
            background: 'var(--bg-card)', color: n === 'отклонён' ? 'var(--danger-fg)' : 'var(--accent-fg)', fontFamily: UI, fontSize: small ? 10.5 : 11,
            fontWeight: 700, whiteSpace: 'nowrap', cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.5 : 1 }}>
          {signAction(n, sign)}</button>
      ))}
    </span>
  )
}

/** Документы пакета, к которым сейчас ждут скан подписанного: бумага, отправленная клиенту. */
export function scanTargets(m) {
  const out = []
  for (const d of m.docs?.ds || []) {
    if (d.sign?.needs_scan) out.push({ annex_id: d.annex_id, upd_no: null, label: d.number })
    for (const k of d.kits || []) if (k.sign?.needs_scan) out.push({ annex_id: null, upd_no: k.upd_no, label: `УПД № ${k.upd_no}` })
  }
  return out
}

/** Панель сканов: бумажные документы у клиента без скана, выбор документа радиочипами, загрузка одного файла к выбранному.
 * Скан подписанного — это и есть отметка «подписан» у бумаги. Ждать нечего — панели нет. */
export function ScansPanel({ m, picked, setPicked, canEdit, onChanged }) {
  const targets = scanTargets(m)
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const target = targets.find(t => scanKey(t) === picked) || targets[0]
  const upload = async (f) => {
    if (!f || !target) return
    setBusy(true); setErr('')
    const fd = new FormData()
    fd.append('file', f)
    if (target.annex_id != null) fd.append('annex_id', target.annex_id); else fd.append('upd_no', target.upd_no)
    try { onChanged((await api.post(`/master-deals/${m.code}/files`, fd, auth())).data); setPicked(null) }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить скан') } finally { setBusy(false) }
  }
  if (!targets.length) return null
  const dot = (c) => <span aria-hidden style={{ width: 6, height: 6, borderRadius: 2, background: c, flex: '0 0 6px' }} />
  return (
    <div data-scans style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '11px 14px', background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 12 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--warning-fg)' }}>
        {dot('var(--warning)')}Ждём скан подписанного: {targets.map(t => t.label).join(', ')} — скан и есть отметка «подписан»</span>
      {canEdit && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ ...CAPS, paddingRight: 2 }}>что загружаем</span>
          {targets.map(t => {
            const on = target && scanKey(t) === scanKey(target)
            return (
              <span key={scanKey(t)} onClick={() => setPicked(scanKey(t))}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 24, padding: '0 9px', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`, borderRadius: 7,
                  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 11, fontWeight: on ? 700 : 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
                <span aria-hidden style={{ width: 10, height: 10, boxSizing: 'border-box', borderRadius: 3, border: `1.5px solid ${on ? 'var(--accent)' : 'var(--border-hover)'}`, background: on ? 'var(--accent)' : 'transparent' }} />
                Скан {t.label}
              </span>
            )
          })}
          <span onClick={() => !busy && fileRef.current?.click()} title="Один файл — один документ: pdf, jpg, png, tif до 20 МБ"
            style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 12px', borderRadius: 8, background: 'var(--accent)', color: 'var(--on-accent)', fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.5 : 1, fontFamily: UI }}>
            <Svg d="M12 16V4M8 8l4-4 4 4M5 20h14" size={12} w={2.1} />{busy ? 'Загружаю…' : `Загрузить · ${target ? target.label : ''}`}
          </span>
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff" style={{ display: 'none' }}
            onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; upload(f) }} />
        </span>
      )}
      {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
    </div>
  )
}
