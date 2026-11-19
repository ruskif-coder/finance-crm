// Счёт на оплату — посмотреть окном (владелец 18.11.2026: «счёт в просмотрщике, а там кнопка скачать»). PDF во фрейме CSP прода
// не пустит (`object-src 'none'`), поэтому счёт собран из тех же данных, что XML для Диадока: XML УПД 1С, номер и дата — счёта 1С
// (`GET /onec-desk/kit/{id}/invoice-doc`). Скачать — PDF счёта из 1С (если загружен) и XML для Диадока.
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { Modal, btn, primaryBtn } from '@/components/salesTableKit'
import { detailText } from '@/lib/loadError'

const money = (v) => Number(v || 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
/** Основание из УПД 1С — объект { name, number, date } (договор), изредка строка. */
const basisText = (b) => (!b ? '' : typeof b === 'string' ? b : [b.name, b.number && `№ ${b.number}`, b.date && `от ${b.date}`].filter(Boolean).join(' '))
const cell = { border: '1px solid #000', padding: '4px 6px', fontSize: 12, verticalAlign: 'top' }

function Party({ label, p }) {
  if (!p) return null
  return (
    <p style={{ margin: '4px 0', fontSize: 13 }}><b>{label}:</b> {p.name}{p.inn ? `, ИНН ${p.inn}` : ''}{p.kpp ? `, КПП ${p.kpp}` : ''}{p.address ? `, ${p.address}` : ''}</p>
  )
}

/** Печатная форма счёта: банк получателя, стороны, строки, итоги. Цвета — бумажные, как у печатной формы ДС. */
function InvoiceDocument({ d }) {
  const b = d.seller?.bank || {}
  return (
    <div style={{ color: '#000', fontFamily: "'Times New Roman', serif", padding: '10mm 0', maxWidth: 900, margin: '0 auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 16 }}><tbody>
        <tr><td style={cell} colSpan={2}>{b.name || 'Банк получателя'}</td><td style={cell}>БИК</td><td style={cell}>{b.bik || '—'}</td></tr>
        <tr><td style={cell} colSpan={2}>Банк получателя</td><td style={cell}>Сч. №</td><td style={cell}>{b.corr || '—'}</td></tr>
        <tr><td style={cell}>ИНН {d.seller?.inn || '—'}</td><td style={cell}>КПП {d.seller?.kpp || '—'}</td><td style={cell} rowSpan={2}>Сч. №</td><td style={cell} rowSpan={2}>{b.account || '—'}</td></tr>
        <tr><td style={cell} colSpan={2}>{d.seller?.name}<br />Получатель</td></tr>
      </tbody></table>
      <h2 style={{ fontSize: 18, margin: '0 0 10px', borderBottom: '2px solid #000', paddingBottom: 6 }}>Счёт на оплату № {d.number} от {d.date}</h2>
      <Party label="Поставщик" p={d.seller} />
      <Party label="Покупатель" p={d.buyer} />
      {basisText(d.basis) && <p style={{ margin: '4px 0', fontSize: 13 }}><b>Основание:</b> {basisText(d.basis)}</p>}
      <table style={{ borderCollapse: 'collapse', width: '100%', margin: '12px 0' }}>
        <thead><tr>{['№', 'Наименование', 'Кол-во', 'Цена', 'Сумма без НДС', 'НДС', 'Сумма с НДС'].map(h => <th key={h} style={{ ...cell, fontWeight: 700 }}>{h}</th>)}</tr></thead>
        <tbody>{(d.lines || []).map((ln, i) => (
          <tr key={i}><td style={cell}>{i + 1}</td><td style={cell}>{ln.name}</td><td style={{ ...cell, textAlign: 'right' }}>{ln.qty || ''}</td>
            <td style={{ ...cell, textAlign: 'right' }}>{ln.price ? money(ln.price) : ''}</td><td style={{ ...cell, textAlign: 'right' }}>{money(ln.net)}</td>
            <td style={{ ...cell, textAlign: 'right' }}>{ln.rate_text}{ln.vat ? ` · ${money(ln.vat)}` : ''}</td><td style={{ ...cell, textAlign: 'right' }}>{money(ln.gross)}</td></tr>
        ))}</tbody>
      </table>
      <p style={{ textAlign: 'right', margin: '2px 0', fontSize: 13 }}>Итого без НДС: <b>{money(d.total?.net)}</b></p>
      <p style={{ textAlign: 'right', margin: '2px 0', fontSize: 13 }}>{d.total?.vat ? <>НДС: <b>{money(d.total.vat)}</b></> : 'Без НДС'}</p>
      <p style={{ textAlign: 'right', margin: '2px 0', fontSize: 14 }}>Всего к оплате: <b>{money(d.total?.gross)}</b></p>
      <p style={{ margin: '12px 0 0', fontSize: 13 }}>{d.purpose}</p>
      {d.seller?.signer?.fio && <p style={{ margin: '24px 0 0', fontSize: 13 }}>{d.seller.signer.position} ______________ {d.seller.signer.fio}</p>}
    </div>
  )
}

/** kitId — комплект УПД мастер-сделки; pdfId — файл «счёт 1С», если загружен. */
export default function InvoiceViewer({ kitId, pdfId, title, onClose, onError }) {
  const [doc, setDoc] = useState(null)
  const [fail, setFail] = useState('')
  useEffect(() => {
    api.get(`/onec-desk/kit/${kitId}/invoice-doc`, auth()).then(r => setDoc(r.data)).catch(e => setFail(detailText(e, 'Не удалось открыть счёт')))
  }, [kitId])
  return (
    <Modal title={title || 'Счёт'} width={1100} fill onClose={onClose}
      footer={<>
        {pdfId && <button type="button" style={btn(false)} onClick={() => downloadFile(`/onec-desk/kit/${kitId}/files/${pdfId}`, null, onError)}>Скачать PDF</button>}
        <button type="button" style={btn(false)} onClick={() => downloadFile(`/onec-desk/kit/${kitId}/invoice-xml`, null, onError)}>Скачать XML</button>
        <span style={{ flex: 1 }} />
        <button type="button" style={primaryBtn} onClick={onClose}>Закрыть</button>
      </>}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', background: '#fff', borderRadius: 8, padding: '0 12mm' }}>
        {doc?.warning && <div style={{ margin: '12px 0 0', padding: '8px 12px', borderRadius: 8, background: 'var(--warning-tint)', color: 'var(--warning-fg)', fontSize: 13 }}>{doc.warning}</div>}
        {fail ? <div style={{ padding: 20, color: 'var(--danger-fg)' }}>{fail}{pdfId ? ' Можно скачать PDF счёта из 1С кнопкой внизу.' : ''}</div>
          : doc ? <InvoiceDocument d={doc} /> : <div style={{ padding: 20, color: 'var(--text-faint)' }}>Загрузка…</div>}
      </div>
    </Modal>
  )
}
