// «Документы для бухгалтерии» (05.11.2026): все вызовы экрана в одном месте — вся страница, черновик, файлы, разбор XML, внесение.
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'

const base = '/onec-desk'

export const deskApi = {
  board: () => api.get(`${base}/board`, auth()).then(r => r.data),
  draft: (id, form) => api.patch(`${base}/kit/${id}/draft`, form, auth()).then(r => r.data),
  submit: (id, form) => api.post(`${base}/kit/${id}/submit`, form, auth()).then(r => r.data),
  giveBack: (id, body) => api.post(`${base}/kit/${id}/return`, body, auth()).then(r => r.data),
  comment: (id, text) => api.post(`${base}/kit/${id}/comment`, { text }, auth()).then(r => r.data),
  seen: (id) => api.post(`${base}/kit/${id}/seen`, null, auth()).then(r => r.data),
  parseXml: (id) => api.post(`${base}/kit/${id}/upd-xml`, null, auth()).then(r => r.data),
  checkNumber: (kind, no, exclude) => api.get(`${base}/check-number`, { ...auth(), params: { kind, no, exclude } }).then(r => r.data),
  upload: (id, slot, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`${base}/kit/${id}/files/${slot}`, fd, auth()).then(r => r.data)
  },
  removeFile: (id, fileId) => api.delete(`${base}/kit/${id}/files/${fileId}`, auth()).then(r => r.data),
  download: (id, fileId, onError) => downloadFile(`${base}/kit/${id}/files/${fileId}`, undefined, onError),
  dsDoc: (id) => api.get(`${base}/kit/${id}/ds-doc`, auth()).then(r => r.data),
  dsFile: (id, fmt, onError) => downloadFile(`${base}/kit/${id}/ds?fmt=${fmt}`, undefined, onError),
  xlsx: (code, onError) => downloadFile(`${base}/master/${encodeURIComponent(code)}.xlsx`, undefined, onError),
  saveClose: (body) => api.put(`${base}/settings/close`, body, auth()).then(r => r.data),
}

export const errText = (e, fallback) => e?.response?.data?.detail || fallback

/** Ошибка сервера → Error с текстом для человека: экран показывает `e.message` тостом. */
export const asError = (fallback) => (e) => { throw new Error(typeof errText(e, fallback) === 'string' ? errText(e, fallback) : fallback) }

// Вид файла на экране → слот на сервере
export const SLOT_OF = { invPdf: 'invoice', updPdf: 'upd', updXml: 'xml' }
