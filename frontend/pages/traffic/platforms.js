// «Площадки × РК» (владелец 05.11.2026): какие площадки проваливаются поперёк ИДУЩИХ РК — запущенных и не завершённых.
// Экран — компонент хендоффа (`components/traffic/platforms`, docs/design_handoff_platforms_report.zip), вставлен дословно;
// данные — GET /api/traffic-dashboard/platforms через маппер `lib/platformsReport.js`. Считает сервер
// (`backend/app/traffic/platform_report.py`); экран сортирует, фильтрует и рисует.
// Право — как у дашборда (traffic_dashboard · view). Вход — «Сводный отчёт →» в виджете «Площадки-виновники».
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import PlatformsReport from '@/components/traffic/platforms/PlatformsReport'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { toReport, trafficOptions } from '@/lib/platformsReport'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

export default function PlatformsPage() {
  const router = useRouter()
  const [scope, setScope] = useState(null)
  const [raw, setRaw] = useState(null)
  const [err, setErr] = useState('')

  const sc = scope || (router.query.scope ? String(router.query.scope) : '')
  const load = useCallback(async () => {
    if (!router.isReady) return
    try {
      setRaw((await api.get(`/traffic-dashboard/platforms${sc ? `?scope=${encodeURIComponent(sc)}` : ''}`, auth())).data)
      setErr('')
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось загрузить отчёт') }
  }, [sc, router.isReady])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  const data = useMemo(() => toReport(raw), [raw])
  const options = useMemo(() => trafficOptions(raw), [raw])
  const onExcel = () => downloadFile(`/traffic-dashboard/platforms.xlsx${sc || raw?.scope ? `?scope=${encodeURIComponent(sc || raw.scope)}` : ''}`,
    undefined, setErr)

  return (
    <>
      <Head><title>Площадки × РК · Трафики | SIMB-AD ERP</title></Head>
      <Navbar />
      {!!err && <div style={{ margin: '14px 30px 0', padding: '10px 14px', borderRadius: 12, background: 'var(--danger-tint)',
        color: 'var(--danger-fg)', fontSize: 13 }}>{err}</div>}
      {!data && !err && <div style={{ padding: '22px 30px', fontSize: 13, color: 'var(--text-faint)' }}>Площадки × РК · загрузка…</div>}
      {data && (
        <PlatformsReport data={data} traffic={sc || raw?.scope || 'mine'} trafficOptions={options} onTraffic={setScope}
          onExcel={onExcel} onBack={() => router.push('/traffic/dashboard')}
          onOpenRk={code => code && router.push(`/traffic/dashboard?open=${encodeURIComponent(code)}`)}
          initialCode={router.query.p ? String(router.query.p) : null} />
      )}
    </>
  )
}
