/**
 * Выставление пакета (19.10.2026): вилка ЭДО / бумага. Видна с «выставления» и дальше.
 * ЭДО — одна отметка «Отправлено в ЭДО» (до интеграции). Бумага — «Подписано у нас» → «Отправлено» (трек).
 * Сканы подписанных — к каждому ДС и УПД, в карточке ДС и панели сканов (`DsCard`, `docParts`), не здесь.
 * Правила и запреты — на сервере (`backend/app/master_deal/issue.py`); здесь только кнопки и что уже отмечено.
 */
import { useState } from 'react'
import { inp, MONO } from '@/components/salesTableKit'
import { fmtDateTime } from '@/lib/dates'
import { CAP, CARD, lineBtn, Note } from '@/components/master/kit'

export const SHOWN = new Set(['выставление', 'ждём оплату', 'ждём сканы', 'архив'])

/** Шаг цепочки — в одну строку с соседями (владелец 19.10.2026: «последовательно, а не друг над другом»). */
function Step({ done, title, sub, children }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
      <span aria-hidden style={{ width: 12, height: 12, borderRadius: 6, flex: '0 0 12px', border: `2px solid ${done ? 'var(--income-fg)' : 'var(--border-hover)'}`,
        background: done ? 'var(--income-fg)' : 'transparent' }} />
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', color: done ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{title}</span>
        {!!sub && <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{sub}</span>}
      </span>
      {children}
    </span>
  )
}

const Arrow = () => <span aria-hidden style={{ color: 'var(--text-faint)', fontSize: 14, padding: '0 2px' }}>→</span>

const by = (x) => (x ? `${fmtDateTime(x.at)}${x.by ? ` · ${x.by}` : ''}` : null)

export default function IssuePanel({ m, busy, canEdit, onSigned, onSent, footer }) {
  const [track, setTrack] = useState('')
  const i = m.issue
  if (!i || !SHOWN.has(m.status)) return null
  const paper = !!i.paper                      // тот же признак, что у сервера (status.is_paper) — правило в одном месте
  const onIssue = m.status === 'выставление'
  const btn = lineBtn({ busy })

  return (
    <div style={{ ...CARD, padding: '16px 20px', marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 15, fontWeight: 800 }}>Выставление</span>
        <span style={CAP}>{i.channel || 'способ не задан'}</span>
      </div>
      {!i.channel && !i.sent && <Note tone="bad">У договора не задано «Выставление» — ЭДО или бумага. Проставьте его в реестре договоров.</Note>}

      <div style={{ display: 'flex', alignItems: 'center', gap: '10px 14px', flexWrap: 'wrap' }}>
        {!!footer && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>{footer}</span>}
        {!!footer && <Arrow />}
        {paper && (
          <Step done={!!i.signed_by_us} title="Подписано у нас" sub={by(i.signed_by_us)}>
            {canEdit && onIssue && !i.signed_by_us && <button type="button" style={btn} disabled={busy} onClick={onSigned}>Подписано у нас</button>}
          </Step>
        )}
        {paper && <Arrow />}
        <Step done={!!i.sent} title={paper ? 'Отправлено клиенту' : 'Отправлено в ЭДО'}
          sub={i.sent ? `${by(i.sent)}${i.sent.track_no ? ` · трек ${i.sent.track_no}` : ''}` : (!paper && i.channel ? 'документы закрываются отправкой' : null)}>
          {canEdit && onIssue && !i.sent && (!paper || i.signed_by_us) && (
            <span style={{ display: 'inline-flex', gap: 6 }}>
              {paper && <input value={track} onChange={e => setTrack(e.target.value)} placeholder="трек, по желанию"
                style={{ ...inp, width: 150, padding: '5px 9px', fontSize: 12, fontFamily: MONO }} />}
              <button type="button" style={btn} disabled={busy || !i.channel} onClick={() => onSent(track)}>Отправлено</button>
            </span>
          )}
        </Step>
      </div>
    </div>
  )
}
