// «Трафики → Премодерация» (владелец 07.11.2026, экран по макету 08.11): креативы SSP пакетами — один
// баннер на все площадки — и наше согласование. Очередь заполняет крон backend `app.premod.sync` раз
// в 10 минут; экран читает её одним ответом и пишет решения. В SSP решения пока НЕ уходят.
// Право — traffic_premod: просмотр — страница, правка — `can_decide` в ответе. Только десктоп.
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import Premoderation from '@/components/premod/Premoderation'
import { LoadErrorScreen, UI } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const REFRESH_MS = 60000
const detail = (e, fallback) => e?.response?.data?.detail || fallback

export default function PremoderationPage() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    try {
      const r = await api.get('/premod/board', auth())
      setData(r.data)
      setErr('')
    } catch (e) { setErr(detail(e, 'Очередь премодерации не загрузилась')) }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, REFRESH_MS)
    return () => clearInterval(t)
  }, [load])
  useRefreshOnReturn(load)

  const onDecide = async (pkgId, body) => {
    try {
      const r = await api.post(`/premod/packages/${pkgId}/decision`, body, auth())
      load()
      return r.data
    } catch (e) {
      load()
      throw new Error(detail(e, 'Решение не сохранилось'))
    }
  }

  const onBulkApprove = async (ids) => {
    try {
      const r = await api.post('/premod/bulk-approve', { package_ids: ids }, auth())
      load()
      return r.data
    } catch (e) {
      load()
      const dirty = e?.response?.status === 409 ? (e.response.data?.missing || []).length : 0
      throw new Error(dirty ? `Пакетов с нарушениями: ${dirty} — ничего не одобрено, очередь обновлена`
        : detail(e, 'Пакеты не одобрены'))
    }
  }

  const onSetCategory = async (inn, category) => {
    try {
      await api.patch(`/premod/advertisers/${encodeURIComponent(inn)}`, { category }, auth())
      await load()
    } catch (e) { throw new Error(detail(e, 'Категория не сохранилась')) }
  }

  const head = <Head><title>Премодерация · Трафики | SIMB-AD ERP</title></Head>
  if (!data && err) {
    return <>{head}<LoadErrorScreen title="Премодерация не загрузилась" nav={<Navbar />} text={err} onRetry={load} /></>
  }
  return (
    <>
      {head}
      <Navbar />
      {data
        ? <Premoderation data={data} onDecide={onDecide} onBulkApprove={onBulkApprove} onSetCategory={onSetCategory}
            onOpenSnapshot={url => { if (url) window.open(url, '_blank', 'noopener') }} />
        : <div style={{ padding: 40, fontFamily: UI, fontSize: 13, color: 'var(--text-muted)' }}>Загружаю очередь…</div>}
    </>
  )
}
