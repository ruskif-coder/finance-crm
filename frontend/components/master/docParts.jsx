/**
 * Общие части документов пакета (хендофф «реестр + карточка», 19.10.2026): плашка подписания, кнопка «электронный | скан»,
 * панель сканов. Ими пользуются карточка ДС (`DsCard`) и расхлоп реестра (`registry/PackDocs`) — разметка одна.
 */
import { useRef, useState } from 'react'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { SIGNED } from '@/lib/masterSteps'
import { MONO, UI } from '@/components/salesTableKit'

const CAPS = { fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const ICON = {
  none: '', issued: '', ours: 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', sent: 'M4 12l16-8-6 16-3-7z', both: 'M5 12.5l4.5 4.5L19 7.5',
}
const Svg = ({ d, size = 11, w = 2.2 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
)

// §6: рамка карточки по подписанию; у УПД «не выпущен / не подписан» — --accent-border
/** Скачать скан документа пакета (было собрано вручную в восьми местах). */
export const downloadScan = (code, scan, setErr) => downloadFile(`/master-deals/${code}/files/${scan.id}`, scan.filename, setErr)

/** Колонка документов комплекта УПД: «электрон. | скан» — Счёт, УПД (+ скан у бумаги), Отчёт; номера из 1С на кнопках. */
export function KitDocs({ kit, upd_no, paper, code, onPick, setErr }) {
  const off = !kit?.onec
  return (
    <span data-noexp onClick={e => e.stopPropagation()} style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingLeft: 12, borderLeft: '1px solid var(--accent-border)', alignSelf: 'start' }}>
      <span style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 8, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)', padding: '0 2px' }}>
        <span>электрон.</span><span>{paper ? 'скан · обязательно' : ''}</span></span>
      <DocButton label={kit?.invoice_no ? `Счёт № ${kit.invoice_no}` : 'Счёт'} off={off} wide />
      <DocButton label={kit?.upd_doc_no ? `УПД № ${kit.upd_doc_no}` : 'УПД'} off={off} wide paper={paper && !!kit} scan={kit?.scan}
        onScan={() => downloadScan(code, kit.scan, setErr)} onPick={() => onPick(`u${upd_no}`)} />
      <DocButton label="Отчёт" off={off} wide />
    </span>
  )
}

export const signFrame = (s, upd = false) => ({ ours: 'var(--warning-border)', sent: 'var(--warning-border)', both: 'var(--income)' }[s] || (upd ? 'var(--accent-border)' : 'var(--border-card)'))
export const scanKey = (t) => (t.annex_id != null ? `a${t.annex_id}` : `u${t.upd_no}`)

export function SignBadge({ s, small = false }) {
  const [label, bg, bd, fg] = SIGNED[s] || SIGNED.none
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
          <Svg d={ICON.both} size={10} />скан</span>
      ) : (
        <span title="Скана нет — выбрать этот документ в панели сканов" onClick={onPick}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0 8px', borderLeft: '1px dashed var(--warning-border)', background: 'var(--warning-bg)', color: 'var(--warning-fg)', fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap', cursor: 'pointer' }}>
          <Svg d="M12 5v14M5 12h14" size={10} />скан</span>
      ))}
    </span>
  )
}

/** Панель сканов: что не хватает, выбор документа радиочипами, загрузка одного файла к выбранному. */
export function ScansPanel({ m, picked, setPicked, canEdit, onChanged }) {
  const s = m.docs.scans
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const target = s.targets.find(t => scanKey(t) === picked) || s.targets[0]
  const upload = async (f) => {
    if (!f || !target) return
    setBusy(true); setErr('')
    const fd = new FormData()
    fd.append('file', f)
    if (target.annex_id != null) fd.append('annex_id', target.annex_id); else fd.append('upd_no', target.upd_no)
    try { onChanged((await api.post(`/master-deals/${m.code}/files`, fd, auth())).data); setPicked(null) }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить скан') } finally { setBusy(false) }
  }
  const dot = (c) => <span aria-hidden style={{ width: 6, height: 6, borderRadius: 2, background: c, flex: '0 0 6px' }} />
  if (!s.missing.length) {
    return <span style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', background: 'var(--income-tint)', border: '1px solid var(--income-border)', borderRadius: 11, fontSize: 12, color: 'var(--income-fg)' }}>
      {dot('var(--income)')}Все сканы на месте: ДС {s.ds[1]} из {s.ds[0]} · УПД {s.upd[1]} из {s.upd[0]} — пакет можно закрывать</span>
  }
  return (
    <div data-scans style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '11px 14px', background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 12 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--warning-fg)' }}>
        {dot('var(--warning)')}Обязательные сканы подписанных: ДС {s.ds[1]} из {s.ds[0]} · УПД {s.upd[1]} из {s.upd[0]} — без них пакет не уходит в архив</span>
      {canEdit && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ ...CAPS, paddingRight: 2 }}>что загружаем</span>
          {s.targets.map(t => {
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
