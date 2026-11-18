/**
 * Контур «Документы» карточками (экран 13 хендоффа v5): колонка на статус пакета. Пакеты с ходом аккаунта — карточками
 * (код, сделки, сумма, контрагент, договор, период, «что сделать», действие), остальные — компактным списком «без вашего участия».
 * «Ждут оплату» — сводка: пакеты, сделки, сумма. Действие — `PackAction` (шаг реестра или «что сделать»).
 */
import { STICKY_TOP } from '@/components/accounts/deals/TurnGroups'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { MONO } from '@/components/salesTableKit'
import { CopyIcon } from '@/components/CopyCode'
import { monthLabel } from '@/lib/salesFormat'
import { TODO_DOT } from '@/lib/masterStatus'
import { mln } from '@/components/accounts/dashboard/ladder'
import PackAction from '@/components/accounts/deals/packAction'
import { plural } from '@/components/master/kit'
import { DOC_STAGES, packMine, packTurn } from '@/components/accounts/deals/contours'

const SUB = { 'черновик': 'раскладка по ДС и комплектам', 'согласование': 'юрист и аккаунт', 'ждём 1С': 'бухгалтер делает счёт и УПД',
  'выставление': 'финансы отправляют клиенту', 'ждём оплату': 'вне фокуса аккаунта — ведут финансы' }
const SEC = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', padding: '0 4px' }
const deals = (p) => (p.deal_codes || []).length

function Card({ p, canEdit, asking, setAsking, onDone }) {
  const t = p.todo
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14, padding: '12px 12px 10px', display: 'flex', flexDirection: 'column', gap: 8, boxShadow: 'var(--shadow-card)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
          <Link href={`/accounts/master/${p.code}`} target="_blank" style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)' }}>{p.code}</Link>
          <CopyIcon text={p.code} size={12} title="Скопировать код мастер-сделки" />
        </span>
        <span style={{ padding: '2px 7px', borderRadius: 7, border: '1px solid var(--border-card)', fontSize: 11.5, fontWeight: 600 }}>{deals(p)} {plural(deals(p), ['сделка', 'сделки', 'сделок'])}</span>
        <b style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13 }}>{mln(p.net)}</b>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
        <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
          <b style={{ fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.counterparty || '—'}</b>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>договор № {p.contract?.number || '—'}</span>
        </span>
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{monthLabel(p.period)}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 10, padding: '8px 10px' }}>
        <span aria-hidden style={{ width: 7, height: 7, borderRadius: 2, background: t ? TODO_DOT[t.tone] : 'transparent', flex: '0 0 7px', alignSelf: 'center' }} />
        <span style={{ fontSize: 12.5, fontWeight: 700 }}>{t?.text || '—'}</span>
      </div>
      <PackAction p={p} canEdit={canEdit} asking={asking} setAsking={setAsking} onDone={onDone}
        onGo={() => window.open(`/accounts/master/${p.code}`, '_blank', 'noopener')} />
    </div>
  )
}

function Compact({ list, note }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, overflow: 'hidden' }}>
      {list.map((p, i) => (
        <Link key={p.code} href={`/accounts/master/${p.code}`} target="_blank" style={{ display: 'grid', gridTemplateColumns: '10px 64px minmax(0,1fr) auto', gap: 8, alignItems: 'center',
          padding: '7px 10px', borderTop: i ? '1px solid var(--border-row)' : 0, textDecoration: 'none', color: 'inherit' }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: p.todo?.tone === 'bad' ? 'var(--warning)' : 'var(--text-disabled)' }} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}><span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700 }}>{p.code}</span>
            <CopyIcon text={p.code} size={11} title="Скопировать код мастер-сделки" /></span>
          <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.counterparty || '—'}</span>
            <span style={{ fontSize: 10.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.todo?.text || note}</span>
          </span>
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{mln(p.net)}</span>
        </Link>))}
    </div>
  )
}

export default function PackBoard({ packs, picked, canEdit, onReload }) {
  const [asking, setAsking] = useState(null)
  useEffect(() => {
    if (!asking) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setAsking(null) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [asking])
  const stages = picked.length ? DOC_STAGES.filter(st => picked.includes(st.key)) : DOC_STAGES
  const done = () => { setAsking(null); onReload() }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${stages.length}, minmax(0,1fr))`, gap: 14, alignItems: 'start' }}>
      {stages.map(st => {
        const list = packs.filter(p => p.status === st.key)
        const mineL = list.filter(packMine)
        const rest = list.filter(p => !packMine(p))
        const pay = st.key === 'ждём оплату'
        const n = { mine: mineL.length, wait: rest.length }
        return (
          <div key={st.key} style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
            <div style={{ position: 'sticky', top: STICKY_TOP, zIndex: 5, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14, padding: '10px 14px', boxShadow: 'var(--shadow-card)' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <b style={{ fontSize: 14 }}>{st.label}</b>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}>{list.length}</span>
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{mln(list.reduce((s, p) => s + (p.net || 0), 0))}</span>
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{SUB[st.key]}</div>
              <div style={{ display: 'flex', gap: 2, margin: '7px 0 5px', height: 4 }}>
                {!!n.mine && <span style={{ flex: n.mine, borderRadius: 2, background: 'var(--accent)' }} />}
                {!!n.wait && <span style={{ flex: n.wait, borderRadius: 2, background: 'var(--border-hover)' }} />}
                {!list.length && <span style={{ flex: 1, borderRadius: 2, background: 'var(--bg-subtle)' }} />}
              </div>
              <div style={{ display: 'flex', gap: 10, fontFamily: MONO, fontSize: 10.5 }}>
                {!!n.mine && <span style={{ color: 'var(--accent-fg)' }}>● ваш ход {n.mine}</span>}
                {!!n.wait && <span style={{ color: 'var(--text-muted)' }}>● ждём {n.wait}</span>}
              </div>
            </div>
            {!!mineL.length && <span style={{ ...SEC, color: 'var(--accent-fg)' }}>Ваш ход · {mineL.length}</span>}
            {mineL.map(p => <Card key={p.code} p={p} canEdit={canEdit} asking={asking} setAsking={setAsking} onDone={done} />)}
            {!mineL.length && !!list.length && !pay && <span style={{ fontSize: 12, color: 'var(--text-faint)', padding: '2px 4px' }}>Вашего хода нет — ждём других.</span>}
            {pay && !!list.length && (
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '8px 12px', fontSize: 12.5 }}>
                {[['пакетов', list.length], ['сделок', list.reduce((s, p) => s + deals(p), 0)], ['ждём всего', mln(list.reduce((s, p) => s + (p.net || 0), 0))]].map(([l, v]) => (
                  <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}><span style={{ color: 'var(--text-secondary)' }}>{l}</span><b style={{ fontFamily: MONO }}>{v}</b></div>))}
              </div>)}
            {!!rest.length && <>
              <span style={{ ...SEC, color: 'var(--text-muted)' }}>Без вашего участия · {rest.length}</span>
              <Compact list={rest} note={`ждём: ${packTurn(rest[0]).who}`} />
            </>}
            {!list.length && <span style={{ fontSize: 12, color: 'var(--text-faint)', padding: '6px 4px' }}>пакетов нет</span>}
          </div>
        )
      })}
    </div>
  )
}
