import api, { auth } from './api'

// ── Документы сделки: ОДИН список на все экраны ──────────────────────────
// Используется в карточке сделки (/sales/deals/[id]), в раскрывашке строки (DealDetail)
// и в блоке «Документы» на канбан-доске дашборда. Ключи должны совпадать с
// DEAL_DOC_KINDS на бэкенде (sales_dashboard.py) — иначе загрузка вернёт 400.
//
// bx: true — файл приезжает синком из Битрикса. Такие только скачиваем: их владелец
// синхронизация, ручная замена разошлась бы с источником.
export const DEAL_DOCS = [
  { kind: 'contract', label: 'Договор', bx: true },
  { kind: 'mp', label: 'МП (Битрикс)', bx: true },
  { kind: 'ds', label: 'Доп. соглашение', short: 'ДС' },
  { kind: 'creatives', label: 'Креативы' },
  { kind: 'invoice', label: 'Счёт' },
  { kind: 'upd', label: 'УПД' },
  { kind: 'report', label: 'Отчёт' },
  { kind: 'act', label: 'Акт' },
]
export const DEAL_DOC_LABEL = Object.fromEntries(DEAL_DOCS.map(d => [d.kind, d.label]))

// Скачивание файла сделки (или любого blob-эндпоинта) с сохранением имени.
export async function downloadBlob(url, filename) {
  try {
    const r = await api.get(url, { ...auth(), responseType: 'blob' })
    const href = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = href; a.download = filename || 'file'; a.click()
    URL.revokeObjectURL(href)
    return true
  } catch { alert('Не удалось скачать файл'); return false }
}

// Выбор файла и загрузка. onDone вызывается только при успехе.
export function pickAndUploadDoc(dealId, kind, onDone, onBusy) {
  const inp = document.createElement('input')
  inp.type = 'file'
  inp.onchange = async () => {
    const f = inp.files && inp.files[0]
    if (!f) return
    const fd = new FormData(); fd.append('file', f)
    onBusy && onBusy(kind)
    try {
      await api.post(`/sales/deals/${dealId}/files/${kind}`, fd,
        { ...auth(), headers: { ...(auth().headers || {}), 'Content-Type': 'multipart/form-data' } })
      onDone && onDone()
    } catch (e) { alert(e.response?.data?.detail || 'Не удалось загрузить файл') }
    finally { onBusy && onBusy('') }
  }
  inp.click()
}

export async function deleteDoc(dealId, kind, onDone, onBusy) {
  if (!window.confirm('Удалить документ?')) return
  onBusy && onBusy(kind)
  try { await api.delete(`/sales/deals/${dealId}/files/${kind}`, auth()); onDone && onDone() }
  catch (e) { alert(e.response?.data?.detail || 'Не удалось удалить') }
  finally { onBusy && onBusy('') }
}

// Статус документа для индикатора на карточке доски: 0 готово · 1 в работе · 2 нет.
// «В работе» есть только у медиаплана — по статусу версии (черновик/на согласовании).
export function docState(deal, kind) {
  const files = deal.files || []
  if (kind === 'brief') return (deal.brief_state === 'filled') ? 0 : 2
  if (kind === 'mp') {
    const ours = (deal.our_mps || [])[0]
    if (ours) return ours.status === 'approved' ? 0 : 1
    return files.some(f => f.kind === 'mp') ? 0 : 2
  }
  return files.some(f => f.kind === kind) ? 0 : 2
}
