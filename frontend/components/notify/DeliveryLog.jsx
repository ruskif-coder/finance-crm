/**
 * Общий журнал отправок — часть модуля «Уведомления и письма».
 *
 * Оба контура одной лентой, с указанием канала. До 16.09.2026 журналов было два на
 * разных экранах — доставки сотрудникам в уведомлениях, письма наружу в почте, — а
 * вопрос у человека один: «ушло или нет». Объединение сделано на ЧТЕНИИ, таблицы
 * остались своими: у них разный адресат и разная цена ошибки (устройство — в
 * `backend/app/notify/deliveries.py`).
 */
import { useState } from 'react'
import { UI, MONO, card, inp, sel, th, btnSm, Modal } from '../salesTableKit'
import { fmtDateTime } from '@/lib/dates'
import api, { auth } from '../../lib/http'
import { STATUS, badge, msg, td } from './kit'

export default function DeliveryLog({ data, filter, setFilter, onErr }) {
  /* Письмо разворачивает САМ журнал: состояние там же, где элемент, который его
     показывает. Пока разворот жил на странице, она знала про устройство строки —
     что 'm' в начале ключа означает письмо, — и это знание расползалось. */
  const [letter, setLetter] = useState(null)
  const open = async (id) => {
    try { setLetter((await api.get(`/mail/log/${id}`, auth())).data) }
    catch (e) { onErr(msg(e)) }
  }

  const scan = data?.last_scan
  const ST = { sent: ['var(--income-tint)', 'var(--income-fg)'],
               queued: ['var(--bg-subtle)', 'var(--text-muted)'],
               suppressed: ['var(--bg-subtle)', 'var(--text-muted)'],
               failed: ['var(--danger-tint)', 'var(--danger-fg)'] }
  return (
    <div style={{ ...card, overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-inner)',
        display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', fontSize: 12 }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>Журнал отправок</span>
        <span style={{ color: 'var(--text-muted)' }}>всего записей: {data?.total ?? '—'}</span>
        {/* Отбор по каналу — выпадашкой: каналов четыре, и «почему не пришло письмо»
            разбирается именно по одному каналу, а не по всей ленте. */}
        <select value={filter.channel} onChange={e => setFilter(f => ({ ...f, channel: e.target.value }))}
          style={{ ...sel, marginLeft: 'auto' }}>
          <option value="">все каналы</option>
          {(data?.channels || []).map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        <select value={filter.contour} onChange={e => setFilter(f => ({ ...f, contour: e.target.value }))}
          style={sel}>
          <option value="">оба контура</option>
          {(data?.contours || []).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filter.status} onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
          style={sel}>
          <option value="">любой статус</option>
          <option value="sent">доставлено</option>
          <option value="queued">ждёт канала</option>
          <option value="suppressed">подавлено</option>
          <option value="failed">ошибка</option>
        </select>
        <input value={filter.q} placeholder="кому или о чём"
          onChange={e => setFilter(f => ({ ...f, q: e.target.value }))}
          style={{ ...inp, width: 180 }} />
      </div>
      {/* Прогон сканера — здесь же: «алерты не приходят» надо уметь отличить от
          «сканер вообще не запускался». */}
      {scan && (
        <div style={{ padding: '8px 16px', fontSize: 11.5, color: 'var(--text-muted)',
          borderBottom: '1px solid var(--border-inner)' }}>
          последний прогон сканера: {fmtDateTime(scan.started_at)} · сработок {scan.matches}
          {' '}· отправок {scan.sent} · пропущено {scan.suppressed}
          {scan.dry_run ? ' · сухой прогон' : ''}
          {scan.error ? ` · ошибка: ${scan.error}` : ''}
        </div>
      )}
      <div style={{ overflowX: 'auto', padding: '12px 4px 0' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr>
            <th style={th}>Когда</th><th style={th}>Канал</th><th style={th}>Кому</th>
            <th style={th}>Что ушло</th><th style={th}>О чём</th><th style={th}>Статус</th>
          </tr></thead>
          <tbody>
            {!data && (
              <tr><td colSpan={6} style={{ ...td, color: 'var(--text-muted)' }}>Загрузка…</td></tr>
            )}
            {data?.items?.length === 0 && (
              <tr><td colSpan={6} style={{ ...td, color: 'var(--text-muted)' }}>Пока пусто.</td></tr>
            )}
            {(data?.items || []).map(r => {
              const [bg, fg] = ST[r.status] || ['var(--bg-subtle)', 'var(--text-muted)']
              const isMail = String(r.id).startsWith('m')
              return (
                <tr key={r.id} onClick={() => isMail && open(String(r.id).slice(1))}
                  style={{ cursor: isMail ? 'pointer' : 'default' }}>
                  <td style={{ ...td, whiteSpace: 'nowrap', color: 'var(--text-muted)',
                    fontFamily: MONO, fontSize: 11 }}>{fmtDateTime(r.created_at)}</td>
                  <td style={{ ...td, fontSize: 13 }}>
                    {r.channel_label}
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)' }}>
                      {r.contour}
                    </span>
                  </td>
                  <td style={{ ...td, fontSize: 13 }}>{r.addressee}</td>
                  <td style={{ ...td, fontSize: 13 }}>{r.subject}</td>
                  <td style={{ ...td, fontSize: 12, color: 'var(--text-secondary)' }}>{r.kind_label}</td>
                  <td style={td}>
                    <span style={badge(bg, bg, fg)}>
                      {r.status_label}{r.reason ? ` · ${r.reason}` : ''}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Письмо целиком: в журнале лежит ИТОГОВЫЙ текст, а не ссылка на шаблон, поэтому
          видно ровно то, что получил адресат. */}
      {letter && (
        <Modal title={letter.subject} width={720} onClose={() => setLetter(null)}
               summary={`${letter.kind_label} · ${letter.to_email} · ${fmtDateTime(letter.sent_at || letter.created_at)}`}
               footer={<button style={btnSm(false)} onClick={() => setLetter(null)}>Закрыть</button>}>
          {!!letter.error && (
            <div style={{ color: 'var(--danger)', fontSize: 12.5, marginBottom: 8 }}>{letter.error}</div>
          )}
          <pre style={{ margin: 0, fontFamily: UI, fontSize: 13, whiteSpace: 'pre-wrap' }}>
            {letter.body}
          </pre>
        </Modal>
      )}
    </div>
  )
}
