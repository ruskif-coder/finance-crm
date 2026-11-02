/**
 * Выставление пакета — сводка по документам (02.11.2026; до того — отметки «подписано у нас / отправлено» на пакете целиком).
 * Клиент может отказать в подписи одного документа пакета, поэтому отметки — у каждого ДС и УПД (`DsCard`, `registry/PackDocs`),
 * а здесь только итог: канал договора, сколько документов у клиента и подписано, какие отклонены. Видна с «выставления».
 * Правила — на сервере (`backend/app/master_deal/issue.py`, `doc_sign.py`).
 */
import { fmtDateTime } from '@/lib/dates'
import { CAP, CARD, Note } from '@/components/master/kit'

export const SHOWN = new Set(['выставление', 'ждём оплату', 'ждём сканы', 'архив'])

const Count = ({ n, of, title, done }) => (
  <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6 }}>
    <span style={{ fontSize: 13, fontWeight: 700, color: done ? 'var(--income-fg)' : 'var(--text-primary)' }}>{title}</span>
    <span style={{ fontSize: 13, fontWeight: 700, color: done ? 'var(--income-fg)' : 'var(--text-secondary)' }}>{n} из {of}</span>
  </span>
)

export default function IssuePanel({ m, footer }) {
  const i = m.issue
  if (!i || !SHOWN.has(m.status)) return null
  const s = i.summary || { total: 0, sent: 0, signed: 0 }
  return (
    <div style={{ ...CARD, padding: '16px 20px', marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 15, fontWeight: 800 }}>Выставление</span>
        <span style={CAP}>{i.channel || 'способ не задан'}</span>
        {!!i.last_sent_at && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>последняя отправка {fmtDateTime(i.last_sent_at)}</span>}
      </div>
      {!i.channel && !s.sent && <Note tone="bad">У договора не задано «Выставление» — ЭДО или бумага. Проставьте его в реестре договоров.</Note>}
      {!!i.rejected?.length && <Note tone="bad" style={{ marginBottom: 10 }}>Клиент отклонил: {i.rejected.join(', ')} — причина в истории документа; переделайте и выставьте снова.</Note>}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px 18px', flexWrap: 'wrap' }}>
        {!!footer && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>{footer}</span>}
        <Count title="У клиента" n={s.sent} of={s.total} done={!!s.total && s.sent === s.total} />
        <Count title="Подписано" n={s.signed} of={s.total} done={!!s.total && s.signed === s.total} />
        <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Отметки — у каждого ДС и УПД ниже: клиент подписывает документы по отдельности.</span>
      </div>
    </div>
  )
}
