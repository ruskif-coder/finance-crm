/**
 * Шаблоны ДС: клиент ручек `/api/annex-templates/*` (спринт 2, 14.10.2026). Заменил хранилище макета.
 * Ошибки сервера приходят строкой или `{message, issues}` (422 проверки шаблона) — `errorOf` сводит их к тексту и списку.
 */
import api, { auth } from '@/lib/http'

const base = '/annex-templates'

export const annexTemplatesApi = {
  list: () => api.get(base, auth()).then(r => r.data.items || []),
  formats: () => api.get(`${base}/formats`, auth()).then(r => r.data),
  subs: () => api.get(`${base}/subs`, auth()).then(r => r.data.items || []),
  one: (id) => api.get(`${base}/${id}`, auth()).then(r => r.data),
  forContract: (contractId, templateId) => api.get(`${base}/for-contract/${contractId}`, { ...auth(), params: templateId ? { template_id: templateId } : {} }).then(r => r.data),
  versions: (id) => api.get(`${base}/${id}/versions`, auth()).then(r => r.data.items || []),
  // `annexWord` — вид документа по договору, выбранный при пересохранении (если ещё не выбран; 31.10.2026).
  save: (id, blocks, adoptBase, annexWord) => api.post(`${base}/${id}/versions`,
    { blocks, adopt_base: !!adoptBase, ...(annexWord ? { annex_word: annexWord } : {}) }, auth()).then(r => r.data),
  restore: (id, version) => api.post(`${base}/${id}/restore`, { version }, auth()).then(r => r.data),
  // Шаблон договора — именованный, их у договора несколько (27.10.2026); `sourceId` — копия этого шаблона, пусто — базового формата.
  // `brandId` — бренд, к которому относится шаблон (реестр шаблонов, 31.10.2026): пишется в память «договор + бренд →
  // шаблон», по которой сборка подставит его в ДС бренда. Пусто — все бренды договора.
  fork: (contractId, { title, sourceId, main, annexId, brandId } = {}) => api.post(`${base}/custom`,
    { contract_id: contractId, title, source_id: sourceId ?? null, main: !!main, annex_id: annexId ?? null,
      brand_id: brandId ?? null }, auth()).then(r => r.data),
  brands: (contractId) => api.get(`${base}/brands/${contractId}`, auth()).then(r => r.data || []),
  rename: (id, title) => api.put(`${base}/${id}/title`, { title }, auth()).then(r => r.data),
  setMain: (id, main) => api.put(`${base}/${id}/main`, { main: !!main }, auth()).then(r => r.data),
  // Шаблон в ДС: выбор на сборке (пусто — по умолчанию) и «Сохранить как шаблон» из конструктора — право правки приложений.
  choose: (annexId, templateId) => api.put(`${base}/annex/${annexId}/choice`, { template_id: templateId ?? null }, auth()).then(r => r.data),
  saveAs: (annexId, title, main) => api.post(`${base}/annex/${annexId}/save-as`, { title, main: !!main }, auth()).then(r => r.data),
  behind: () => api.get(`${base}/behind`, auth()).then(r => r.data),
  keepOwn: (id) => api.post(`${base}/${id}/keep-own`, {}, auth()).then(r => r.data),
  createBase: (title, copyFrom, formats) => api.post(`${base}/base`, { title, copy_from: copyFrom, formats: formats || [] }, auth()).then(r => r.data),
  setFormats: (id, formats) => api.put(`${base}/${id}/formats`, { formats }, auth()).then(r => r.data),
}

/** Текст ошибки и список замечаний проверки из ответа сервера. */
export function errorOf(e, fallback = 'Не удалось выполнить действие') {
  const d = e && e.response && e.response.data && e.response.data.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) return { message: d.message || fallback, issues: d.issues || [] }
  if (typeof d === 'string') return { message: d, issues: [] }
  return { message: fallback, issues: [] }
}
