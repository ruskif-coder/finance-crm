/**
 * Карточка ДС пакета — по хендоффу «реестр + карточка» (19.10.2026, docs/мастер и шапка.zip): номер, плашка и рамка подписания,
 * тип, чипы услуг, «ДС pdf | скан», сумма; таблица позиций по группам с итогом; перенос платного допа; комплекты УПД —
 * карточки по содержимому с колонкой документов «электрон. | скан» (Счёт, УПД | скан, Отчёт). Клик по комплекту раскрывает
 * позиции и разбивку по сделкам. `doc` — тот же ДС из модели документов пакета (`m.docs`), пока ДС не созданы — нет.
 */
import { useState } from 'react'
import Link from 'next/link'
import { MONO } from '@/components/salesTableKit'
import { downloadFile } from '@/lib/download'
import { grpDash, rub2 } from '@/lib/salesFormat'
import { Dot, groupLabel, lineBtn } from '@/components/master/kit'
import { DocButton, KitDocs, SignBadge, downloadScan, signFrame } from '@/components/master/docParts'
import { BasisRow } from '@/components/master/UpdBasis'
import { SVC_DOT } from '@/lib/masterStatus'

const GRID = 'minmax(220px,2.4fr) 80px 120px 90px 100px 110px 100px 110px'
const KIND = { main: ['основные услуги', 'var(--accent-tint)', 'var(--accent-fg)'], addons: ['доп. услуги', 'var(--violet-tint)', 'var(--violet-fg)'],
  all: ['основные и допы', 'var(--bg-subtle)', 'var(--text-secondary)'] }
// §6: маркер услуги по её названию
const HEAD = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }

function Kit({ k, rows, rate, doc, paper, code, onPick, setErr, basis, busy, onBasis }) {
  const [open, setOpen] = useState(false)
  const sign = doc?.signed || 'none'
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', background: 'var(--bg-tint)', border: `1px solid ${signFrame(sign, true)}`, borderRadius: 12, minWidth: 0, transition: 'border-color 300ms ease' }}>
    <div onClick={() => setOpen(o => !o)} style={{ flex: '0 1 420px', minWidth: 'min(360px,100%)', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', columnGap: 14, rowGap: 5, padding: '11px 13px',
      minHeight: 0, cursor: 'pointer', alignContent: 'start' }}>
      <span style={{ gridColumn: 1, display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ ...HEAD, fontWeight: 700, color: 'var(--accent-fg)' }}>УПД № {k.upd_no}</span>
        {!!doc && <SignBadge s={sign} small />}
        <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{open ? '▴' : '▾'}</span>
      </span>
      <span style={{ gridColumn: 1, fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{groupLabel(k)}</span>
      <span style={{ gridColumn: 1, display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>{rub2(k.gross)}</span>
        <span style={{ ...HEAD, letterSpacing: '.06em' }}>с НДС</span>
      </span>
      <span style={{ gridColumn: 1, fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>сделки: {k.deals.join(', ')}</span>
      <span style={{ gridColumn: 2, gridRow: '1 / span 4', alignSelf: 'start' }}>
        <KitDocs kit={doc} upd_no={k.upd_no} paper={paper} code={code} onPick={onPick} setErr={setErr} />
      </span>
      {open && (
        <div onClick={e => e.stopPropagation()} style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4, paddingTop: 8, borderTop: '1px solid var(--accent-border)', cursor: 'default' }}>
          <span style={{ ...HEAD, fontSize: 8.5, fontWeight: 700 }}>Позиции</span>
          {rows.filter(r => k.lines.includes(r.id)).map(r => (
            <span key={r.id} style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
              <span style={{ fontSize: 11.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.kind === 'base' || r.kind === 'discount' ? r.position : `доп. · ${r.position}`}</span>
              <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{r.deal}</span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{rub2(r.net * (1 + rate))}</span>
            </span>
          ))}
          <span style={{ ...HEAD, fontSize: 8.5, fontWeight: 700, paddingTop: 5 }}>По сделкам, с НДС</span>
          {k.by_deal.map(x => (
            <span key={x.deal} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>{x.deal}</span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{rub2(x.gross)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
      {/* основание к закрытию этого УПД — в том же блоке, справа (владелец 19.10.2026: «объедини в один блок», карточка УПД — как была) */}
      {!!basis && (
        <div data-noexp style={{ flex: '1 1 0', minWidth: 0, padding: '11px 14px', borderLeft: '1px solid var(--accent-border)' }}>
          <BasisRow code={code} u={basis} busy={busy} onSaved={onBasis} compact />
        </div>
      )}
    </div>
  )
}

export default function DsCard({ ds, vat, locked, moved, separate, flash, onMove, doc, paper, code, onPick, basis, busy, onBasis }) {
  const [err, setErr] = useState('')
  const rate = (vat || 0) / 100
  const all = ds.groups.flatMap(g => g.rows)
  const showHead = ds.groups.length > 1 || ds.groups.some(g => g.brand || g.service)
  const [label, bg, fg] = KIND[ds.kind] || KIND.main
  const sign = doc?.signed
  const kitDoc = (n) => doc?.kits?.find(x => x.upd_no === n)
  return (
    <div style={{ background: 'var(--bg-card)', border: `1px solid ${doc ? signFrame(sign) : 'var(--border-card)'}`, boxShadow: 'var(--shadow-card)', borderRadius: 18,
      padding: '16px 20px 18px', marginBottom: 14, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0,
      outline: flash ? '2px solid var(--accent)' : 'none', transition: 'outline .2s, border-color 300ms ease' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>{doc?.number || `ДС № ${ds.no}`}</span>
        {!!doc && <SignBadge s={sign} />}
        <span style={{ display: 'inline-flex', alignItems: 'center', background: bg, color: fg, borderRadius: 7, padding: '3px 9px', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', alignSelf: 'center' }}>{label}</span>
        {!!doc?.services?.length && (
          <span style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap', alignSelf: 'center' }}>
            {doc.services.map(s => (
              <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 20, padding: '0 7px', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 6, fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                <span aria-hidden style={{ width: 5, height: 5, borderRadius: 1, background: SVC_DOT[s] || 'var(--text-faint)' }} />{s}</span>
            ))}
          </span>
        )}
        {!!doc && (
          <span style={{ alignSelf: 'center' }}>
            <DocButton label="ДС pdf" off={false} paper={paper} scan={doc.scan} onDoc={() => downloadFile(doc.doc_url, null, setErr)}
              onScan={() => downloadScan(code, doc.scan, setErr)} onPick={() => onPick(`a${doc.annex_id}`)} />
          </span>
        )}
        {/* Текст ДС и основание к закрытию правятся в конструкторе ДС — на «согласовании» сюда и идут (владелец 20.10.2026). */}
        {!!doc && (
          <Link href={`/directory/annexes/${doc.annex_id}`} data-noexp onClick={e => e.stopPropagation()}
            style={{ ...lineBtn({ tone: 'accent', size: 'sm' }), alignSelf: 'center', textDecoration: 'none' }}>
            {doc.confirmed ? 'Открыть в конструкторе →' : 'Править ДС →'}</Link>
        )}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
          <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em' }}>{rub2(ds.net)}</span>
          <span style={HEAD}>до НДС</span>
        </span>
      </div>
      {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}

      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 860, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, padding: '0 8px 8px', borderBottom: '1px solid var(--border-card)', ...HEAD }}>
            <span>Позиция</span><span>Сделка</span><span>Модель</span><span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Цена за ед.</span>
            <span style={{ textAlign: 'right' }}>Стоимость</span><span style={{ textAlign: 'right' }}>НДС {vat ?? ''} %</span><span style={{ textAlign: 'right' }}>С НДС</span>
          </div>
          {ds.groups.map((g, gi) => (
            <div key={gi}>
              {showHead && <div style={{ padding: 8, background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-row)', fontSize: 12.5, fontWeight: 700 }}>{groupLabel(g)}</div>}
              {g.rows.map(r => {
                const paid = r.kind === 'extra'
                const isMoved = moved.includes(r.id)
                const disc = r.kind === 'discount'
                const dot = r.kind === 'base' ? 'var(--accent)' : r.kind === 'bonus' ? 'var(--violet-fg)' : disc ? 'var(--danger-fg)' : 'var(--text-faint)'
                const zero = r.kind === 'bonus'
                const sumFg = zero ? 'var(--text-faint)' : disc ? 'var(--danger-fg)' : 'var(--text-primary)'
                const num = { fontFamily: MONO, fontSize: 11.5, textAlign: 'right', whiteSpace: 'nowrap' }
                return (
                  <div key={r.id} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, alignItems: 'center', padding: 8, borderBottom: '1px solid var(--border-row)' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 8, minWidth: 0, paddingLeft: showHead ? 16 : 0 }}>
                      <span style={{ fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: disc ? 'var(--danger-fg)' : 'var(--text-primary)' }}>
                        {r.kind === 'base' || disc ? r.position : `доп. · ${r.position}${zero ? ' (бонус)' : ''}`}</span>
                      {isMoved && <span style={{ ...HEAD, fontSize: 8.5, color: 'var(--warning-fg)', whiteSpace: 'nowrap' }}>перенесён</span>}
                      {paid && separate && !locked && (
                        <span onClick={() => onMove(r.id)} style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
                          {isMoved ? '→ в ДС допов' : '→ в основной ДС'}</span>
                      )}
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{r.deal}</span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 0, minWidth: 0, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}><Dot c={dot} />{zero ? 'Бонус' : (r.model || 'Полная цена')}</span>
                    <span style={{ ...num, color: 'var(--text-secondary)' }}>{grpDash(r.volume)}</span>
                    <span style={{ ...num, color: 'var(--text-secondary)' }}>{r.unit_price ? rub2(r.unit_price) : '—'}</span>
                    <span style={{ ...num, color: sumFg }}>{zero ? '—' : rub2(r.net)}</span>
                    <span style={{ ...num, color: sumFg }}>{zero ? '—' : rub2(r.net * rate)}</span>
                    <span style={{ ...num, fontWeight: 700, color: sumFg }}>{zero ? '—' : rub2(r.net * (1 + rate))}</span>
                  </div>
                )
              })}
            </div>
          ))}
          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, alignItems: 'center', padding: '10px 8px', background: 'var(--bg-subtle)' }}>
            <span style={{ fontSize: 12.5, fontWeight: 700 }}>Итого</span><span /><span /><span /><span />
            {[ds.net, ds.vat, ds.gross].map((v, i) => <span key={i} style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap' }}>{rub2(v)}</span>)}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 6 }}>
        <span style={{ ...HEAD, fontWeight: 700, letterSpacing: '.1em' }}>Закрывающие · комплектов {ds.upds.length}</span>
        {ds.no_kits ? (
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Нет позиций со стоимостью — закрывающие не формируются.</span>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {ds.upds.map(k => <Kit key={k.upd_no} k={k} rows={all} rate={rate} doc={kitDoc(k.upd_no)} paper={paper} code={code} onPick={onPick} setErr={setErr}
              basis={(basis || []).find(u => u.upd_no === k.upd_no)} busy={busy} onBasis={onBasis} />)}
          </div>
        )}
      </div>
    </div>
  )
}
