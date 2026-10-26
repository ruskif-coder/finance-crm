import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar, { can, firstAllowedHref } from '@/components/Navbar'
import { UI } from '@/components/salesTableKit'
import StuckView from '@/components/publishers/StuckView'
import ReconBoard from '@/components/publisherRecon/ReconBoard'
import ReconPivot from '@/components/publisherRecon/ReconPivot'
import { CAPS } from '@/components/publisherRecon/reconKit'
import { todayMsk } from '@/lib/dates'
import api, { auth } from '@/lib/http'
import { counts } from '@/lib/publisherRecon.mjs'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

// «Паблишеры → Взаимодействие» (владелец 26.10.2026) — базовый экран менеджера паблишеров: сверки площадок за месяц,
// сводная за год и дубль «Подвисших» из «Согласований». Хендофф docs/паблишеры взаимодействие.zip, план
// docs/ПЛАН_сверка_паблишера.md. Право dir_publishers_interaction (смотреть / править). Мобильной версии нет.

const SUB = { recon: 'сверка с площадками за месяц', pivot: 'закрытие по месяцам', stuck: 'что подвисло на площадках' }

export default function PublisherInteraction() {
  const router = useRouter()
  const current = todayMsk().slice(0, 7)
  const [ready, setReady] = useState(false)
  const [perms, setPerms] = useState({})
  const [view, setView] = useState(null)
  const [month, setMonth] = useState(current)
  const [year, setYear] = useState(Number(current.slice(0, 4)))
  const [openPub, setOpenPub] = useState(null)
  const [answers, setAnswers] = useState(0)

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    let p = {}
    try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch { p = {} }
    if (!can(p, 'dir_publishers_interaction', 'view')) {
      router.push(firstAllowedHref(p, localStorage.getItem('is_admin') === '1')); return
    }
    setPerms(p)
    setView(can(p, 'dir_publishers_approvals', 'view') ? 'stuck' : 'recon')
    setReady(true)
  }, [router])

  // Счётчик «есть ответ» на вкладке «Сверки» — сразу, а не после её открытия (первой стоит «Подвисшие»).
  const loadCount = useCallback(() => {
    if (!ready) return
    api.get(`/publisher-recon/board?period=${current}`, auth())
      .then(r => setAnswers(counts(r.data.rows || []).answer))
      .catch(() => setAnswers(0))      // счётчик — подсказка; сама вкладка покажет ошибку, если откроют
  }, [ready, current])
  useEffect(() => { loadCount() }, [loadCount])
  useRefreshOnReturn(loadCount)

  if (!ready) return null
  const canEdit = can(perms, 'dir_publishers_interaction', 'edit')
  // «Подвисшие» — первая вкладка и вкладка по умолчанию (владелец 26.10.2026); без права на «Согласования» её нет.
  const tabs = [...(can(perms, 'dir_publishers_approvals', 'view') ? [['stuck', 'Подвисшие', 0]] : []),
    ['recon', 'Сверки', answers], ['pivot', 'Сводная', 0]]

  return (
    <>
      <Head><title>Взаимодействие · Паблишеры | SIMB-AD ERP</title></Head>
      <Navbar active="publishers" />
      <div style={{ minHeight: 'calc(100vh - var(--navbar-h))', background: 'var(--bg-canvas)', fontFamily: UI, padding: '18px 24px 40px', boxSizing: 'border-box' }}>
        <div style={{ maxWidth: 1780, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', padding: '4px 4px 2px' }}>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em' }}>Паблишеры</h1>
            <span style={{ ...CAPS, fontSize: 10 }}>{SUB[view] || ''}</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 2, padding: 4, background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 12 }}>
              {tabs.map(([key, label, n]) => {
                const on = view === key
                return (
                  <span key={key} onClick={() => setView(key)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 14px', borderRadius: 10, cursor: 'pointer', whiteSpace: 'nowrap',
                    background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 13, fontWeight: on ? 700 : 600 }}>
                    {label}
                    {!!n && <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 18, height: 18, padding: '0 5px', borderRadius: 8,
                      background: 'var(--violet-tint)', color: 'var(--violet-fg)', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fontWeight: 700 }}>{n}</span>}
                  </span>
                )
              })}
            </span>
          </div>

          {view === 'recon' && <ReconBoard month={month} setMonth={setMonth} current={current} canEdit={canEdit}
            onAnswers={setAnswers} openPub={openPub} setOpenPub={setOpenPub} />}
          {view === 'pivot' && <ReconPivot year={year} setYear={setYear} current={current}
            onOpenRecon={(m, pid) => { setMonth(m); setOpenPub(pid); setView('recon') }} />}
          {view === 'stuck' && <StuckView />}
        </div>
      </div>
    </>
  )
}
