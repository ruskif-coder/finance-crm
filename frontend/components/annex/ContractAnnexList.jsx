/**
 * «ДС договора» в окне «Шаблон ДС» (владелец 28.10.2026): уже подтверждённые приложения договора — номер, дата, период, сумма, шаблон,
 * по которому собран документ, сделки. Строка открывает ДС. Данные — реестр приложений с отбором по договору (`GET /annexes?contract_id`),
 * та же область видимости «свои», что у реестра.
 */
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, th, td } from '@/components/salesTableKit'
import { grpDec, fmtDateFull } from '@/lib/salesFormat'

export default function ContractAnnexList({ contractId }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let alive = true
    api.get('/annexes', { ...auth(), params: { contract_id: contractId } })
      .then(r => { if (alive) setRows((r.data.items || []).filter(a => a.no != null)) })
      .catch(e => { if (alive) setErr((e.response && e.response.data && e.response.data.detail) || 'Не удалось загрузить ДС договора') })
    return () => { alive = false }
  }, [contractId])

  if (err) return <div style={{ padding: '24px', color: 'var(--danger-fg)', fontSize: 13 }}>{err}</div>
  if (!rows) return <div style={{ padding: '24px', color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
  return (
    <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: '22px 24px 24px' }}>
      {!rows.length
        ? <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Подтверждённых ДС по договору нет — черновики видны в реестре приложений.</span>
        : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr>
              <th style={th}>ДС</th><th style={th}>Дата</th><th style={th}>Период</th>
              <th style={{ ...th, textAlign: 'right' }}>Сумма</th><th style={th}>Шаблон</th><th style={th}>Сделки</th>
            </tr></thead>
            <tbody>
              {rows.map(a => (
                <tr key={a.id} onClick={() => window.open(`/directory/annexes/${a.id}`, '_blank', 'noopener')} style={{ cursor: 'pointer' }}>
                  <td style={{ ...td, fontWeight: 700 }}>{a.number}</td>
                  <td style={{ ...td, fontFamily: MONO }}>{fmtDateFull(a.date)}</td>
                  <td style={{ ...td, fontFamily: MONO }}>{fmtDateFull(a.period_from)} — {fmtDateFull(a.period_to)}</td>
                  <td style={{ ...td, fontFamily: MONO, textAlign: 'right' }}>{a.total_amount == null ? '—' : grpDec(a.total_amount, 2)}</td>
                  <td style={td}>{a.template ? `${a.template.title} · v${a.template.version}` : '—'}</td>
                  <td style={{ ...td, fontFamily: MONO, fontSize: 12 }}>{(a.deals || []).map(d => d.code).join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  )
}
