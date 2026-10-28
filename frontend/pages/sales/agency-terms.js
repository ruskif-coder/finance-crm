// «Продажи → Агентские условия» (владелец 27.10.2026; схема — docs/СХЕМА_СК.md, вёрстка — хендофф docs/_handoff_agency_terms):
// правила основной СК по договорам в связке с агентством или рекламодателем, расчёт СК за месяц и квартал, закрытый месяц,
// Excel; партнёрская СК и спец. условия — скрытой вкладкой.
// Права: `sk_terms` — смотреть (продажи и аккаунты) / править (мастера); `sk_special` — вкладка «Спец. условия» и партнёрская.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import api, { auth } from '@/lib/http'
import Navbar, { can, getPermissions } from '@/components/Navbar'
import { isAdmin } from '@/lib/auth'
import { MONO, LoadErrorScreen } from '@/components/salesTableKit'
import SideTab from '@/components/agencyTerms/SideTab'
import RuleModal from '@/components/agencyTerms/RuleModal'
import CalcView from '@/components/agencyTerms/CalcView'
import SpecialTab from '@/components/agencyTerms/SpecialTab'
import WorkTab from '@/components/agencyTerms/WorkTab'
import { flattenSide, namesOf, sideKpi } from '@/lib/agencyTerms.mjs'
import { todayMsk } from '@/lib/dates'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

export default function AgencyTermsPage() {
  const [tab, setTab] = useState('agency')
  const [opts, setOpts] = useState(null)
  const [tree, setTree] = useState({})
  const [err, setErr] = useState('')
  const [modes, setModes] = useState({ agency: 'all', advertiser: 'all' })
  const [rule, setRule] = useState(null)
  const [tick, setTick] = useState(0)
  const [partnerKey, setPartnerKey] = useState(0)
  const [perm, setPerm] = useState({ edit: false, special: false, specialEdit: false, admin: false })
  useEffect(() => {
    const p = getPermissions()
    setPerm({ edit: can(p, 'sk_terms', 'edit'), special: can(p, 'sk_special', 'view'), specialEdit: can(p, 'sk_special', 'edit'), admin: isAdmin() })
  }, [])

  const load = useCallback(() => {
    setErr('')
    api.get('/agency-terms/options', auth()).then((r) => setOpts(r.data))
      .catch((e) => setErr(e.response?.data?.detail || 'Справочники не загрузились'))
    for (const side of ['agency', 'advertiser']) {
      api.get(`/agency-terms/tree?side=${side}`, auth()).then((r) => setTree((t) => ({ ...t, [side]: r.data.items })))
        .catch((e) => setErr(e.response?.data?.detail || 'Условия не загрузились'))
    }
    setTick((t) => t + 1)
  }, [])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load, { enabled: !rule })

  const names = useMemo(() => (opts ? namesOf(opts) : {}), [opts])
  const emptyCount = useMemo(() => (tree.agency ? sideKpi(tree.agency, flattenSide(tree.agency, todayMsk())).noRule : 0), [tree])
  const nav = <Navbar />
  if (err && !opts) return <LoadErrorScreen nav={nav} text={err} onRetry={load} />

  const tabs = [['agency', 'Агентства', emptyCount], ['advertiser', 'Рекламодатели'], ['work', 'Условия работы'], ['calc', 'Расчёт'], ...(perm.special ? [['special', 'Спец. условия']] : [])]
  const side = tab === 'advertiser' ? 'advertiser' : 'agency'
  const ruleEdit = rule && (rule.kind === 'партнёрская' ? perm.specialEdit : perm.edit)
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Head><title>Агентские условия · Продажи</title></Head>
      {nav}
      <div style={{ maxWidth: 1700, margin: '0 auto', padding: '22px 28px 40px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>Продажи</span>
            <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.025em' }}>Агентские условия</span>
          </span>
          <span style={{ display: 'inline-flex', gap: 4, padding: 3, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 11 }}>
            {tabs.map(([k, label, badge]) => {
              const on = tab === k
              return (
                <span key={k} onClick={() => setTab(k)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 13px', borderRadius: 8,
                  background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 13,
                  fontWeight: on ? 700 : 600, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                  {label}
                  {!!badge && <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 18, height: 18, padding: '0 5px',
                    borderRadius: 6, background: 'var(--warning-tint)', color: 'var(--warning-fg)', fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>{badge}</span>}
                </span>)
            })}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.45, flex: '1 1 320px' }}>
            СК по договорам: чем больше признаков у правила, тем оно главнее. Расчёт — по сделкам, прошедшим согласования в ДО.</span>
        </div>
        {err && <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}
        {(tab === 'agency' || tab === 'advertiser') && opts && tree[side] && (
          <SideTab key={side} items={tree[side]} side={side} names={names} canEdit={perm.edit} onOpen={setRule}
            mode={modes[side]} setMode={(m) => setModes((x) => ({ ...x, [side]: m }))} />)}
        {tab === 'work' && opts && <WorkTab opts={opts} canEdit={perm.edit} tick={tick} />}
        {tab === 'calc' && opts && <CalcView canEdit={perm.edit} isAdmin={perm.admin} tick={tick} onOpenRule={setRule}
          onGoEmpty={() => { setModes((x) => ({ ...x, agency: 'empty' })); setTab('agency') }} />}
        {tab === 'special' && opts && perm.special && (
          <SpecialTab names={names} canEdit={perm.specialEdit} tick={tick} reloadKey={partnerKey} onOpenRule={setRule} />)}
      </div>
      {rule && opts && <RuleModal rule={rule} opts={opts} canEdit={ruleEdit} onClose={() => setRule(null)}
        onSaved={() => { setRule(null); setPartnerKey((k) => k + 1); load() }} />}
    </div>
  )
}
