import api, { auth } from './api'
import { downloadFile } from './download'

// ── Документы сделки: ОДИН список на все экраны ──────────────────────────
// Используется в карточке сделки (/sales/deals/[id]), в раскрывашке строки (DealDetail)
// и в блоке «Документы» на канбан-доске дашборда. Ключи должны совпадать с
// DEAL_DOC_KINDS на бэкенде (sales_dashboard.py) — иначе загрузка вернёт 400.
//
// bx: true — файл приезжает синком из Битрикса. Такие только скачиваем: их владелец
// синхронизация, ручная замена разошлась бы с источником.
//
// «Креативы» — первыми, сразу под медиапланом (владелец 27.09.2026), и файлом их больше
// НЕ загружают: креативы прикрепляются в блоке «Креативы» на сборке, а здесь только
// «Скачать» — один архив с чистыми исходниками всех прикреплённых (`creatives: true`).
export const DEAL_DOCS = [
  { kind: 'creatives', label: 'Креативы', creatives: true },
  { kind: 'contract', label: 'Договор', bx: true },
  { kind: 'mp', label: 'МП (Битрикс)', bx: true },
  { kind: 'ds', label: 'Доп. соглашение', short: 'ДС' },
  { kind: 'invoice', label: 'Счёт' },
  { kind: 'upd', label: 'УПД' },
  { kind: 'report', label: 'Отчёт' },
  { kind: 'act', label: 'Акт' },
]

// Скачивание файла сделки — через общую точку (lib/download). Реэкспорт под прежним
// именем, чтобы не переписывать вызовы на экранах: правило имени файла и разбор отказа
// живут теперь в одном месте на всё приложение.
export { downloadFile as downloadBlob } from './download'

// Архив креативов сделки: внутри чистые исходники всех прикреплённых на сборке, под
// именами из системы («Креатив №3 — Скидка.zip»). Имя архива даёт сервер.
export function downloadDealCreatives(dealId, onError) {
  return downloadFile(`/launch-prep/deal/${dealId}/creatives-archive`, '', onError)
}

// Подпись карточки «Креативы»: сколько прикреплено, или где их прикрепляют.
export function creativesMeta(n) {
  if (!n) return 'прикрепляются в блоке «Креативы»'
  const w = n % 10 === 1 && n % 100 !== 11 ? 'креатив'
    : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'креатива' : 'креативов'
  return `${n} ${w} · чистые архивы`
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
// «В работе» есть только у медиаплана: план собран, но ещё не проверен — сделка стоит
// на первой стадии. Раньше признаком был статус версии плана (черновик/согласован); с
// 30.08.2026 своего состояния у плана нет, состояние плана — стадия его сделки, и
// «проверен» читается ровно как «сделка ушла с первой стадии».
export function docState(deal, kind) {
  const files = deal.files || []
  if (kind === 'brief') return (deal.brief_state === 'filled') ? 0 : 2
  if (kind === 'mp') {
    const ours = (deal.our_mps || [])[0]
    if (ours) return (deal.our_stage && deal.our_stage.is_first) ? 1 : 0
    return files.some(f => f.kind === 'mp') ? 0 : 2
  }
  // ДС читается по ВЫПУЩЕННОМУ приложению, а не по файлу: файла у него больше нет —
  // документ собирается у нас. Черновик — «в работе»: номер ещё не занят.
  if (kind === 'ds') {
    const a = (deal.annexes || [])[0]
    if (!a) return 2
    return a.is_draft ? 1 : 0
  }
  // Креативы — по прикреплённым на сборке, а не по файлу сделки (27.09.2026).
  if (kind === 'creatives') return (deal.creatives_ready || 0) > 0 ? 0 : 2
  return files.some(f => f.kind === kind) ? 0 : 2
}
