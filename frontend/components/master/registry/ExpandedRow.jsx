/**
 * Расхлоп строки реестра (хендофф реестра v2, 21.10.2026): сделки пакета · ДС с комплектами и документами · последние события.
 * Сетка `0.8fr · 2.4fr · 270px` в рамке --accent-border; данные — та же карточка пакета (`GET /master-deals/{код}`).
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { fmtDateTimeShort } from '@/lib/dates'
import { SVC_DOT } from '@/lib/masterStatus'
import { MONO } from '@/components/salesTableKit'
import { ScansPanel } from '@/components/master/docParts'
import PackDocs, { Money } from '@/components/master/registry/PackDocs'
import StepBar from '@/components/master/registry/StepBar'
import { stepBar } from '@/lib/masterStepBar'
import { CAPS } from '@/components/master/registry/kit'
import { detailText } from '@/lib/loadError'

const HEAD = { ...CAPS, fontWeight: 700, letterSpacing: '.1em' }

// Тона зон расхлопа в темах NAVY (хендофф design_handoff_account_navy, 18.11.2026) — одно правило для «Моих сделок» и реестра:
// днём центр — мягкая стальная подложка (navy.css, [data-acc-center]), края светлые; ночью центр светлый, края тёмные.
// Прежние темы — undefined: расхлоп в рамке, как был.
const ZONES = { navy: { center: undefined, side: undefined }, 'navy-dark': { center: 'light', side: 'dark' } }
export const navyZone = (theme) => ZONES[theme]
const COL = { display: 'flex', flexDirection: 'column', minWidth: 0, padding: '14px 18px' }

function Deals({ deals, tone }) {
  return (
    <div data-tone={tone} style={{ ...COL, gap: 6, ...(tone ? { background: 'var(--bg-card)' } : {}) }}>
      <span style={HEAD}>Сделки пакета · {deals.length}</span>
      <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 360, overflowY: 'auto' }}>
        {deals.map(d => (
          <span key={d.id} style={{ display: 'grid', gridTemplateColumns: '78px minmax(0,1.5fr) minmax(0,1fr) 22px 150px', gap: 8, alignItems: 'center', padding: '6px 0', borderTop: '1px solid var(--border-row)', minWidth: 0 }}>
            <Link href={`/sales/deals/${d.code}`} style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', color: 'var(--accent)' }}>{d.code}</Link>
            <span title={d.brand || ''} style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.brand || '—'}</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minWidth: 0, fontSize: 11.5, color: 'var(--text-secondary)' }}>
              <span aria-hidden style={{ width: 5, height: 5, borderRadius: 1, background: SVC_DOT[d.service] || 'var(--text-disabled)', flex: '0 0 5px' }} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.service || '—'}</span>
            </span>
            <span title={d.status} style={{ display: 'inline-flex', justifyContent: 'center' }}>
              <span aria-hidden style={{ width: 8, height: 8, borderRadius: 2, background: d.state === 'done' ? 'var(--income)' : 'var(--warning)' }} />
            </span>
            <Money net={d.total_net} gross={d.total_gross} />
          </span>
        ))}
      </div>
    </div>
  )
}

function Events({ code, events, tone }) {
  return (
    <div data-tone={tone} style={{ ...COL, gap: 6, borderLeft: '1px solid var(--border-inner)', background: tone ? 'var(--bg-card)' : 'var(--bg-tint)' }}>
      <span style={HEAD}>Последнее</span>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {events.slice(0, 3).map((e, i) => (
          <span key={i} style={{ display: 'flex', gap: 9, padding: '5px 0', minWidth: 0 }}>
            <span aria-hidden style={{ width: 6, height: 6, borderRadius: 2, background: i === 0 ? 'var(--accent)' : 'var(--text-disabled)', flex: '0 0 6px', marginTop: 5 }} />
            <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
              <span title={e.what} style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.what}</span>
              <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{e.who} · {fmtDateTimeShort(e.at)}</span>
            </span>
          </span>
        ))}
        {!events.length && <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>событий нет</span>}
      </div>
      <Link href={`/accounts/master/${code}`} data-act=""
        style={{ marginTop: 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: 32, border: '1px solid var(--accent-border)', borderRadius: 9,
          background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 12, fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap' }}>Открыть карточку пакета →</Link>
    </div>
  )
}

/** `zone` — вид «Моих сделок» в NAVY (хендофф design_handoff_account_navy, 18.11.2026): `{ center, side }` — тона центра и боковых
 *  колонок, расхлоп — продолжение строки без рамки. Без `zone` (реестр, прежние темы) — вид прежний. */
export default function ExpandedRow({ code, channel, canEdit, onChanged, zone }) {
  const [m, setM] = useState(null)
  const [err, setErr] = useState('')
  const [picked, setPicked] = useState(null)
  useEffect(() => {
    let alive = true
    api.get(`/master-deals/${code}`, auth()).then(r => alive && setM(r.data)).catch(e => alive && setErr(detailText(e, 'Не удалось загрузить пакет')))
    return () => { alive = false }
  }, [code])
  // `md-docs` — документы пакета: «подписано / завершено» зелёным во всех темах NAVY, и на дашборде, где «норма — сталь» (18.11.2026)
  const wrap = (body) => <div className="md-docs" style={{ padding: zone ? 0 : '2px 20px 14px', background: 'var(--bg-subtle)', borderBottom: `1px solid ${zone ? 'var(--border-card)' : 'var(--border-row)'}` }}>{body}</div>
  if (!m) return wrap(<div style={{ padding: '12px 0', fontSize: 12.5, color: err ? 'var(--danger-fg)' : 'var(--text-faint)' }}>{err || 'Загрузка…'}</div>)
  const apply = (v) => { setM(v); onChanged() }
  const ds = m.docs?.ds || []
  const kits = ds.flatMap(d => d.kits)
  const total = ds.length + kits.length * 3
  const ready = ds.length + kits.filter(k => k.onec).length * 3          // ДС скачивается всегда; счёт, УПД, отчёт — после 1С
  return wrap(
    <div data-noexp style={{ display: 'grid', gridTemplateColumns: 'minmax(480px,1fr) minmax(0,2.3fr) 270px', cursor: 'default', overflow: 'hidden',
      ...(zone ? { background: 'transparent' } : { background: 'var(--bg-card)', border: '1px solid var(--accent-border)', borderRadius: 12 }) }}>
      <Deals deals={m.deals} tone={zone?.side} />
      <div data-tone={zone?.center} data-acc-center={zone ? '' : undefined} style={{ ...COL, gap: 8, borderLeft: '1px solid var(--border-inner)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={HEAD}>ДС · комплекты · документы</span>
          {!!ds.length && <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{ready} из {total} готово</span>}
          {/* реестр v3 §4: канал уже есть колонкой строки — здесь серая справка, синий цвет только у действий */}
          <span title="Как документы уходят клиенту — из договора" style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
            · канал: {channel === 'ЭДО' ? 'ЭДО (Диадок)' : channel || 'не задан'}</span>
          {!!ds.length && !stepBar(m, canEdit).zip && (
            <span onClick={() => downloadFile(`/master-deals/${code}/zip`, null, setErr)} title="Скачать все готовые файлы пакета одним архивом"
              style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap', color: 'var(--accent)', cursor: 'pointer' }}>скачать всё · zip</span>
          )}
        </span>
        <StepBar m={m} canEdit={canEdit} onDone={apply} setErr={setErr} />
        {!ds.length && <span style={{ padding: '8px 0', borderTop: '1px solid var(--border-row)', fontSize: 11.5, color: 'var(--text-faint)' }}>ДС ещё не собраны — комплекты и документы появятся после раскладки</span>}
        {!!ds.length && <PackDocs m={m} canEdit={canEdit} onPick={setPicked} setErr={setErr} onDone={apply} />}
        <div style={{ maxWidth: 1120 }}><ScansPanel m={m} picked={picked} setPicked={setPicked} canEdit={canEdit} onChanged={apply} /></div>
        {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
      </div>
      <Events code={code} events={m.events || []} tone={zone?.side} />
    </div>
  )
}
