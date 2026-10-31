/**
 * Данные окна «Шаблоны ДС» с сервера (спринт 2, 14.10.2026): список базовых шаблонов и форматов, шаблоны договора (с 27.10.2026 их
 * несколько, `tplId` — открытый; пусто — шаблон по умолчанию), версии.
 * Все действия возвращают `true`, когда сервер принял, и кладут причину отказа в `err`; после успеха данные перечитываются.
 */
import { useCallback, useEffect, useState } from 'react'
import { annexTemplatesApi as API, errorOf } from '@/lib/annexTemplatesApi'

export default function useTemplateData({ open, contract, baseId, step, tplId }) {
  const [bases, setBases] = useState([])          // базовые шаблоны (scope = base)
  const [fmtMap, setFmtMap] = useState({})        // формат → id шаблона
  const [known, setKnown] = useState([])          // форматы, которые предлагает экран
  const [detail, setDetail] = useState(null)      // открытый шаблон с блоками
  const [info, setInfo] = useState(null)          // режим договора: {source, reason, format, templates, base_changes}
  const [versions, setVersions] = useState([])
  const [err, setErr] = useState(null)            // {message, issues}
  const [loading, setLoading] = useState(false)

  const contractId = contract ? contract.id : null

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      if (contractId) {
        const r = await API.forContract(contractId, tplId)
        setInfo(r)
        setDetail(r.template)
        setVersions(r.template ? await API.versions(r.template.id) : [])
      } else {
        const [items, f] = await Promise.all([API.list(), API.formats()])
        setBases(items.filter(x => x.scope === 'base'))
        setFmtMap(f.map || {})
        setKnown(f.known || [])
        if (step === 'tpl' && baseId) {
          setDetail(await API.one(baseId))
          setVersions(await API.versions(baseId))
        } else {
          setDetail(null)
          setVersions([])
        }
      }
      setErr(null)
    } catch (e) { setErr(errorOf(e, 'Не удалось загрузить шаблоны')) }
    finally { setLoading(false) }
  }, [contractId, baseId, step, tplId])

  useEffect(() => { if (open) reload() }, [open, reload])

  /** Выполнить действие и перечитать данные. Возвращает `true`/`false`; причина отказа — в `err`. */
  const act = useCallback(async (fn) => {
    try {
      await fn()
      await reload()
      return true
    } catch (e) {
      setErr(errorOf(e))
      return false
    }
  }, [reload])

  return {
    bases, fmtMap, known, detail, info, versions, err, loading, setErr, reload,
    save: (id, blocks, adopt, word) => act(() => API.save(id, blocks, adopt, word)),
    restore: (id, v) => act(() => API.restore(id, v)),
    /** Новый шаблон договора; возвращает его id (или null при отказе), чтобы окно сразу открыло его. */
    fork: async ({ title, sourceId, main, annexId }) => {
      try {
        const t = await API.fork(contractId, { title, sourceId, main, annexId })
        setErr(null)
        return t.id
      } catch (e) { setErr(errorOf(e)); return null }
    },
    rename: (id, title) => act(() => API.rename(id, title)),
    setMain: (id, on) => act(() => API.setMain(id, on)),
    keepOwn: (id) => act(() => API.keepOwn(id)),
    createBase: (title, copyFrom) => act(() => API.createBase(title, copyFrom, [])),
    setFormats: (id, formats) => act(() => API.setFormats(id, formats)),
  }
}
