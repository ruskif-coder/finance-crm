// «Кто имеет доступ» — оба контура одним списком: ядро и кабинеты паблишеров (внешний контур). Только чтение.
// Учётки паблишеров живут отдельно от пользователей ядра (изоляция кабинета), и ответ «у кого есть доступ» иначе
// пришлось бы собирать из двух мест. На экране «Пользователи» по макету 16.11.2026 блока не было — владелец вернул его
// окном по кнопке (16.11.2026). Данные — `GET /users/access-overview`, грузятся при открытии.
import { useEffect, useState } from 'react'
import { MONO, Modal, th, td } from '../../salesTableKit'
import api, { auth } from '../../../lib/http'
import { detailText } from '@/lib/loadError'

export default function AccessOverview({ onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.get('/users/access-overview', auth()).then(r => setData(r.data)).catch(e => setError(detailText(e, 'Не удалось загрузить сводку')))
  }, [])
  return (
    <Modal title="Кто имеет доступ" width={1100} onClose={onClose}
      summary={data ? `ядро ${data.core} · кабинеты паблишеров ${data.outer}` : undefined}>
      {!data && !error && <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</div>}
      {!!error && <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>{error}</div>}
      {!!data?.shared_emails?.length && (
        <div style={{ marginBottom: 10, padding: '8px 12px', borderRadius: 9, background: 'var(--danger-tint)', border: '1px solid var(--danger-border)',
          fontSize: 12.5, color: 'var(--danger-fg)' }}>
          Одна и та же почта заведена в обоих контурах: {data.shared_emails.join(', ')}. Это либо ошибка, либо решение,
          которое принимают осознанно.
        </div>
      )}
      {!!data?.rows?.length && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 700 }}>
            <thead><tr>
              <th style={th}>Контур</th><th style={th}>Имя</th><th style={th}>Почта</th>
              <th style={th}>Доступ</th><th style={th}>Объём</th><th style={th}>Вход</th>
            </tr></thead>
            <tbody>
              {data.rows.map((r, i) => {
                const outer = r.contour === 'кабинет'
                return (
                  <tr key={i} style={{ opacity: r.is_active ? 1 : 0.45 }}>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      <span style={{ fontFamily: MONO, fontSize: 10.5, padding: '2px 7px', borderRadius: 6,
                        background: outer ? 'var(--warning-tint)' : 'var(--bg-subtle)', color: outer ? 'var(--warning-text)' : 'var(--text-muted)',
                        border: `1px solid ${outer ? 'var(--warning-border)' : 'var(--border-card)'}` }}>{r.contour}</span>
                    </td>
                    <td style={td}>{r.name}{r.is_active ? '' : ' · выключен'}</td>
                    <td style={{ ...td, fontFamily: MONO, fontSize: 12 }}>{r.email}</td>
                    <td style={td}>{r.access}</td>
                    <td style={{ ...td, color: 'var(--text-muted)', fontSize: 12.5 }}>{r.scope}</td>
                    <td style={{ ...td, fontFamily: MONO, fontSize: 11.5, color: 'var(--text-faint)' }}>
                      {r.last_login_at ? String(r.last_login_at).slice(0, 10) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}
