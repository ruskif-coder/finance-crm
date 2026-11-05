// ДС заявки — посмотреть модалкой (владелец 05.11.2026: «при просмотре — модалка, а не скачивание»). PDF во фрейме CSP прода
// не пустит, поэтому вёрстка та же, что печатает сайдкар, — `AnnexDocument`. Внешний ДС (подписан вне системы) — только скачать.
import { useEffect, useState } from 'react'
import { Modal, btn, primaryBtn } from '@/components/salesTableKit'
import AnnexDocument from '@/components/annex/AnnexDocument'
import { deskApi, errText } from './deskApi'

export default function DsViewer({ kitId, title, onClose, onError }) {
  const [doc, setDoc] = useState(null)
  const [fail, setFail] = useState('')
  useEffect(() => { deskApi.dsDoc(kitId).then(setDoc).catch(e => setFail(errText(e, 'Не удалось открыть ДС'))) }, [kitId])
  return (
    <Modal title={title || 'ДС'} width={1240} fill onClose={onClose}
      footer={<>
        <button type="button" style={btn(false)} onClick={() => deskApi.dsFile(kitId, 'docx', onError)}>Скачать Word</button>
        <button type="button" style={btn(false)} onClick={() => deskApi.dsFile(kitId, 'pdf', onError)}>Скачать PDF</button>
        <span style={{ flex: 1 }} />
        <button type="button" style={primaryBtn} onClick={onClose}>Закрыть</button>
      </>}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', background: '#fff', borderRadius: 8, padding: '0 12mm' }}>
        {fail ? <div style={{ padding: 20, color: 'var(--danger-fg)' }}>{fail}</div>
          : doc ? <AnnexDocument d={doc} /> : <div style={{ padding: 20, color: 'var(--text-faint)' }}>Загрузка…</div>}
      </div>
    </Modal>
  )
}
