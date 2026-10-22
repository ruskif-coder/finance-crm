/**
 * «ДС · комплекты · документы» в расхлопе реестра (хендофф реестра v2, 21.10.2026), перенесено из макета буквально.
 * Каждый ДС — карточка до 1120px; одна сетка `260 · 1fr · 150 · max-content` для шапки ДС и его комплектов, чтобы бренды и суммы
 * стояли на одной вертикали. ✎ — в конструктор ДС, только на сборке и согласовании. Документы комплекта — в одну линию;
 * до 1С — одна серая плашка. Скан — только у бумаги и только к своему документу; пунктир = нужно действие, сплошная = есть.
 */
import Link from 'next/link'
import { downloadFile } from '@/lib/download'
import { rub0 } from '@/lib/salesFormat'
import { SVC_DOT } from '@/lib/masterStatus'
import { MONO } from '@/components/salesTableKit'
import { SignBadge, downloadScan, signFrame } from '@/components/master/docParts'

const GRID = { display: 'grid', gridTemplateColumns: '260px minmax(120px,1fr) 150px max-content', gap: 10, alignItems: 'center' }
const ICON = { dl: 'M12 4v11M7.5 10.5L12 15l4.5-4.5M5 20h14', none: 'M5 12h14', ok: 'M5 12.5l4.5 4.5L19 7.5', plus: 'M12 5v14M5 12h14',
  clock: 'M12 8v4l2.5 1.5' }
const EDIT_STATUSES = new Set(['черновик', 'согласование'])

const Svg = ({ d, size = 11, w = 2, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden>{children || <path d={d} />}</svg>
)

export function Money({ net, gross, bold = 700 }) {
  const unit = { fontSize: 8.5, fontWeight: 400, color: 'var(--text-faint)', letterSpacing: '.04em' }
  return (
    <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, whiteSpace: 'nowrap' }}>
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: bold, color: 'var(--text-primary)' }}>{net == null ? '—' : rub0(net)}<span style={unit}> до НДС</span></span>
      <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)' }}>{gross == null ? '—' : rub0(gross)}<span style={unit}> с НДС</span></span>
    </span>
  )
}

/** Скан как правая половина кнопки документа: есть — зелёный ✓ (скачать), нужен — жёлтый пунктир «+» (выбрать в панели сканов). */
function ScanTail({ scan, onScan, onPick, what }) {
  const base = { display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0 8px', fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap', cursor: 'pointer' }
  return scan ? (
    <span data-noexp title={`Скан подписанного ${what} — ${scan.filename} · скачать`} onClick={onScan}
      style={{ ...base, borderLeft: '1px solid var(--income-border)', background: 'var(--income-tint)', color: 'var(--income-fg)' }}><Svg d={ICON.ok} size={10} w={2.4} />скан</span>
  ) : (
    <span data-noexp title={`Обязательно: скан подписанного ${what} · pdf, jpg, png, tif · до 20 МБ`} onClick={onPick}
      style={{ ...base, borderLeft: '1px dashed var(--warning-border)', background: 'var(--warning-bg)', color: 'var(--warning-fg)' }}><Svg d={ICON.plus} size={10} w={2.4} />скан</span>
  )
}

function Doc({ label, num, ready, title, onClick, tail }) {
  return (
    <span style={{ display: 'inline-flex', height: 24, border: `1px solid ${ready ? 'var(--border-card)' : 'var(--border-inner)'}`, borderRadius: 7, overflow: 'hidden',
      background: ready ? 'var(--bg-card)' : 'var(--bg-subtle)' }}>
      <span title={title} onClick={ready ? onClick : undefined}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '0 8px', color: ready ? 'var(--text-secondary)' : 'var(--text-disabled)', fontSize: 11,
          fontWeight: ready ? 700 : 600, whiteSpace: 'nowrap', cursor: ready && onClick ? 'pointer' : 'default' }}>
        <Svg d={ready ? ICON.dl : ICON.none} />{label}
        {!!num && <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, color: 'var(--text-primary)' }}>№ {num}</span>}
      </span>
      {tail}
    </span>
  )
}

function KitRow({ k, i, paper, code, onPick, setErr }) {
  return (
    <div style={{ ...GRID, padding: '5px 10px', borderTop: '1px solid var(--border-row)', minWidth: 0 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', minWidth: 0 }}>
        <span aria-hidden style={{ width: 3, height: 18, borderRadius: 2, background: k.signed === 'both' ? 'var(--income)' : signFrame(k.signed, true), flex: '0 0 3px' }} />
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          Комплект {i}{k.upd_doc_no ? ` · УПД № ${k.upd_doc_no}` : ''}</span>
        <SignBadge s={k.signed} small />
      </span>
      <span title={k.deals.length ? `сделки: ${k.deals.join(', ')}` : undefined}
        style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{k.group}</span>
      <Money net={k.net} gross={k.gross} bold={600} />
      {!k.onec ? (
        <span title="Счёт, УПД и отчёт появятся после выпуска в 1С — с номерами из 1С"
          style={{ justifySelf: 'end', display: 'inline-flex', alignItems: 'center', gap: 6, height: 24, padding: '0 9px', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)',
            borderRadius: 7, fontFamily: MONO, fontSize: 9.5, letterSpacing: '.04em', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
          <Svg size={10} w={2.2}><circle cx="12" cy="12" r="8" /><path d={ICON.clock} /></Svg>счёт · УПД · отчёт — после 1С</span>
      ) : (
        <span data-noexp style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', flexWrap: 'nowrap', whiteSpace: 'nowrap' }}>
          <Doc label="Счёт" num={k.invoice_no} ready title={`Счёт${k.invoice_no ? ` № ${k.invoice_no}` : ''} · из 1С`} />
          <Doc label="УПД" num={k.upd_doc_no} ready title={`УПД${k.upd_doc_no ? ` № ${k.upd_doc_no}` : ''} · из 1С`}
            tail={paper ? <ScanTail scan={k.scan} what="УПД" onScan={() => downloadScan(code, k.scan, setErr)} onPick={() => onPick(`u${k.upd_no}`)} /> : null} />
          <Doc label="Отчёт" ready title="Отчёт · из 1С" />
        </span>
      )}
    </div>
  )
}

function Pack({ d, kitStart, status, canEdit, paper, code, onPick, setErr }) {
  const edit = canEdit && EDIT_STATUSES.has(status)
  const extra = d.kind === 'extra'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', border: '1px solid var(--border-card)', borderRadius: 10, overflow: 'hidden', minWidth: 0, maxWidth: 1120 }}>
      <div style={{ ...GRID, padding: '6px 10px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', minWidth: 0 }}>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' }}>{d.number}</span>
          <SignBadge s={d.signed} small />
        </span>
        <span title={`Услуги в ДС: ${d.services.join(', ')}`} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, overflow: 'hidden', whiteSpace: 'nowrap' }}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: '4px 8px', flex: '0 0 auto' }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: extra ? 'var(--violet-fg)' : 'var(--accent-fg)' }}>{extra ? 'доп. услуги' : d.primary ? 'первичный' : 'основные услуги'}</span>
            <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{d.kits.length} {d.kits.length === 1 ? 'комплект' : d.kits.length < 5 ? 'комплекта' : 'комплектов'}</span>
          </span>
          <span style={{ display: 'flex', gap: 4, flexWrap: 'nowrap', minWidth: 0 }}>
            {d.services.map(s => (
              <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 20, padding: '0 7px', background: 'var(--bg-card)', border: '1px solid var(--border-inner)',
                borderRadius: 6, fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap', flex: '0 0 auto' }}>
                <span aria-hidden style={{ width: 5, height: 5, borderRadius: 1, background: SVC_DOT[s] || 'var(--text-disabled)' }} />{s}</span>
            ))}
          </span>
        </span>
        <Money net={d.net} gross={d.gross} />
        <span style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', flexWrap: 'nowrap', whiteSpace: 'nowrap' }}>
          {edit && (
            <Link href={`/directory/annexes/${d.annex_id}`} data-noexp
              title={status === 'согласование' ? 'Редактировать ДС — согласование у юриста начнётся заново' : 'Редактировать ДС в конструкторе'}
              style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, boxSizing: 'border-box', border: '1px solid var(--accent-border)',
                borderRadius: 7, background: 'var(--bg-card)', color: 'var(--accent)', textDecoration: 'none' }}>
              <Svg size={12}><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z" /><path d="M13.5 6.5l3 3" /></Svg>
            </Link>
          )}
          <span data-noexp style={{ display: 'inline-flex', height: 24, border: '1px solid var(--border-card)', borderRadius: 7, overflow: 'hidden', background: 'var(--bg-card)' }}>
            <span title="ДС — скачать" onClick={() => downloadFile(d.doc_url, null, setErr)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '0 9px', color: 'var(--text-secondary)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>
              <Svg d={ICON.dl} />ДС pdf</span>
            {paper && <ScanTail scan={d.scan} what="ДС" onScan={() => downloadScan(code, d.scan, setErr)} onPick={() => onPick(`a${d.annex_id}`)} />}
          </span>
        </span>
      </div>
      {d.kits.map((k, j) => <KitRow key={k.upd_no} k={k} i={kitStart + j} paper={paper} code={code} onPick={onPick} setErr={setErr} />)}
    </div>
  )
}

/** Все ДС пакета. Сканы на ДС/УПД показываются только у бумаги и только когда их уже ждут (после отправки клиенту). */
export default function PackDocs({ m, canEdit, onPick, setErr }) {
  const scansOn = !!m.docs?.scans?.need
  let start = 1
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr)', gap: 10, alignItems: 'start' }}>
      {m.docs.ds.map(d => {
        const s = start
        start += d.kits.length
        return <Pack key={d.annex_id} d={d} kitStart={s} status={m.status} canEdit={canEdit} paper={scansOn} code={m.code} onPick={onPick} setErr={setErr} />
      })}
    </div>
  )
}
