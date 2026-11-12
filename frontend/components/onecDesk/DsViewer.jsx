// ДС заявки — посмотреть модалкой (владелец 05.11.2026: «при просмотре — модалка, а не скачивание»). PDF во фрейме CSP прода
// не пустит, поэтому вёрстка та же, что печатает сайдкар, — `AnnexDocument`. Внешний ДС (подписан вне системы) — только скачать.
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { Modal, btn, primaryBtn } from '@/components/salesTableKit'
import AnnexDocument from '@/components/annex/AnnexDocument'
import { deskApi, errText } from './deskApi'

/** `kitId` — ДС заявки бухгалтера; `annexId` — ДС из расхлопа реестра мастер-сделок (12.11.2026: «просмотр ДС — иконка глаза»). */
export default function DsViewer({ kitId, annexId, title, onClose, onError }) {
  const [doc, setDoc] = useState(null)
  const [fail, setFail] = useState('')
  useEffect(() => {
    const load = annexId ? api.get(`/annexes/${annexId}`, auth()).then(r => r.data.doc) : deskApi.dsDoc(kitId)
    load.then(setDoc).catch(e => setFail(errText(e, 'Не удалось открыть ДС')))
  }, [kitId, annexId])
  const file = (kind) => (annexId ? downloadFile(`/annexes/${annexId}/${kind}`, null, onError) : deskApi.dsFile(kitId, kind, onError))
  return (
    <Modal title={title || 'ДС'} width={1240} fill onClose={onClose}
      footer={<>
        <button type="button" style={btn(false)} onClick={() => file('docx')}>Скачать Word</button>
        <button type="button" style={btn(false)} onClick={() => file('pdf')}>Скачать PDF</button>
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
