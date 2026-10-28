// Плашка «Условия работы» под брифом конструктора медиаплана (владелец 27.10.2026): договорённости с агентством /
// рекламодателем, которые аккаунт учитывает при сборке МП. Подбор — `lib/agencyTerms.mjs::matchWork` по текущему брифу
// (меняется на лету), все совпавшие, точные выше. Данные — `/agency-terms/work/active` (право на медиапланы).
// Под брифом на всю ширину, условия — блоками в ряд, переносятся на следующую строку (владелец 27.10.2026).
import { useEffect, useMemo, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO } from '@/components/salesTableKit'
import { rub0 } from '@/lib/salesFormat'
import { matchWork, workPeriod } from '@/lib/agencyTerms.mjs'
import { BonusChips } from './WorkTab'

export default function WorkTermsNote({ agencyId, advertiserId, brandId, services, period }) {
  const [terms, setTerms] = useState(null)
  useEffect(() => {
    api.get('/agency-terms/work/active', auth()).then((r) => setTerms(r.data)).catch(() => setTerms(null))   // подсказка: нет права — нет плашки
  }, [])
  const list = useMemo(() => (terms ? matchWork(terms, { agency_id: agencyId, advertiser_id: advertiserId, brand_id: brandId, services, period }) : []),
    [terms, agencyId, advertiserId, brandId, services, period])
  if (!list.length) return null
  return (
    <span style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)',
      borderRadius: 12, padding: '10px 12px' }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--warning-fg)', fontWeight: 700 }}>
          Условия работы · {list.length}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>учесть при сборке МП</span>
      </span>
      <span style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8, alignItems: 'stretch' }}>
        {list.map((t) => (
          <span key={t.id} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '8px 10px', background: 'var(--bg-card)',
            border: '1px solid var(--warning-border)', borderRadius: 9, minWidth: 0 }}>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
              <span style={{ flex: '1 1 auto', minWidth: 0, fontSize: 10.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                title={[t.names?.agency, t.names?.advertiser, t.names?.brand, t.names?.service].filter(Boolean).join(' · ')}>
                {[t.names?.agency, t.names?.advertiser, t.names?.brand, t.names?.service].filter(Boolean).join(' · ')}</span>
              {!!workPeriod(t) && <span title="Срок условия" style={{ flex: '0 0 auto', fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
                {workPeriod(t)}</span>}
            </span>
            {t.commit_net != null && <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--warning-fg)' }}>коммит {rub0(t.commit_net)}</span>}
            <span style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.4, whiteSpace: 'pre-line' }}>{t.body}</span>
            <BonusChips item={t} size={10.5} />
            {!!t.mail_subject && <span style={{ marginTop: 'auto', fontSize: 10.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              title={t.mail_subject}>письмо: {t.mail_subject}</span>}
          </span>))}
      </span>
    </span>
  )
}
