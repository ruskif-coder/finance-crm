/**
 * Расхлоп сделки «Моих сделок» (v5, экраны 03–05 хендоффа) и модалка режима «Карточки» (экран 12): три колонки — «Сейчас» (шаги стадий, виджет стадии, кнопка
 * и «Отложить», команда) · «История» (5 записей) · «Медиаплан и документы» + «Деньги» и три пиктограммы внизу.
 *
 * Виджет — с сервера (`/sales/account-deals/{id}/now`, `app/sales/account_now.py`); кнопка — та же, что в строке
 * (`row.action` → `useQueueActions`). Документы закрытия — общий `MasterDocs` (из мастер-сделки).
 */
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { MONO } from '@/components/salesTableKit'
import BusyAct from '@/components/BusyAct'
import ReportDates, { reportUrl } from '@/components/ReportDates'
import { downloadMp } from '@/lib/mpDownload'
import { downloadBlob, downloadDealCreatives } from '@/lib/dealDocs'
import { fmtDateTimeShort } from '@/lib/dates'
import MasterDocs from '@/components/deal/MasterDocs'
import ClosingCompact from '@/components/closing/ClosingCompact'
import PrioFactCard from '@/components/prio/PrioFactCard'
import AssemblyNow from '@/components/accounts/deals/AssemblyNow'
import PrioLaunch from '@/components/accounts/deals/PrioLaunch'
import { mln } from '@/components/accounts/dashboard/ladder'
import { ACT, BOX, CAP, Campaign, ICON, NEXT, OwnRun, Steps, Tile, headline, ini, tilesOf } from '@/components/accounts/deals/nowWidgets'

function History({ hist, code, limit, compact }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', marginBottom: 6 }}>
        <span style={CAP}>{compact ? 'Последнее' : 'История'}</span>
        <a href={`/sales/deals/${code}`} target="_blank" rel="noreferrer" style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)', textDecoration: 'none' }}>вся история →</a>
      </div>
      {hist === null ? <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Загрузка…</span>
        : hist.length ? hist.slice(0, limit).map((e, i) => (compact ? (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '104px minmax(0,1fr) 110px', gap: 10, alignItems: 'baseline', padding: '4px 0', fontSize: 12 }}>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{fmtDateTimeShort(e.at)}</span>
            <span title={`${e.label}${e.details ? ` · ${e.details}` : ''}`} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.label}{e.details ? ` · ${e.details}` : ''}</span>
            <span style={{ fontSize: 10.5, color: 'var(--text-muted)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.who || 'система'}</span>
          </div>) : (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '78px minmax(0,1fr)', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--border-row)' }}>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{fmtDateTimeShort(e.at)}</span>
            <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span style={{ fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.label}{e.details ? ` · ${e.details}` : ''}</span>
              <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>{e.who || 'система'}</span></span>
          </div>))) : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Событий пока нет</span>}
    </div>
  )
}

const AV = { fontFamily: MONO, width: 24, height: 24, borderRadius: 7, background: 'var(--bg-subtle)', display: 'inline-flex', alignItems: 'center',
  justifyContent: 'center', fontSize: 9.5, fontWeight: 700, color: 'var(--text-muted)' }

function Team({ team, column }) {
  if (column) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <span style={CAP}>Команда</span>
        {team.map(([role, name]) => (
          <span key={role} style={{ display: 'grid', gridTemplateColumns: '24px 64px minmax(0,1fr)', gap: 8, alignItems: 'center' }}>
            <span style={AV}>{ini(name)}</span>
            <span style={{ ...CAP, fontSize: 8.5 }}>{role}</span>
            <span style={{ fontSize: 12.5, fontWeight: 600, color: name ? 'var(--text-primary)' : 'var(--text-faint)' }}>{name || 'не назначен'}</span>
          </span>))}
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18, padding: '10px 18px', borderTop: '1px solid var(--border-inner)', flexWrap: 'wrap' }}>
      <span style={CAP}>Команда</span>
      {team.map(([role, name]) => (
        <span key={role} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <span style={AV}>{ini(name)}</span>
          <span style={{ display: 'flex', flexDirection: 'column' }}><span style={{ ...CAP, fontSize: 8.5 }}>{role}</span>
            <span style={{ fontSize: 12.5, fontWeight: 600, color: name ? 'var(--text-primary)' : 'var(--text-faint)' }}>{name || 'не назначен'}</span></span>
        </span>))}
    </div>
  )
}

const ROW_BOX = { display: 'flex', alignItems: 'center', gap: 8, ...BOX, padding: '8px 10px', background: 'var(--bg-card)' }

function Docs({ d, now, links }) {
  const mp = (d.our_mps || [])[0]
  return (
    <>
      <span style={CAP}>Медиаплан и документы</span>
      <div style={ROW_BOX}>
        <span style={{ fontSize: 12.5, fontWeight: 700, flex: 1 }}>МП наш</span>
        {mp ? <>
          <BusyAct run={() => downloadMp(mp, 'pdf')} label="PDF" style={ACT} />
          <BusyAct run={() => downloadMp(mp, 'xlsx')} label="XLS" style={ACT} />
          <a href={`/accounts/mp/${mp.id}`} style={{ ...ACT, textDecoration: 'none' }} title="Открыть конструктор">✎</a>
        </> : <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>не создан</span>}
      </div>
      {(d.creatives_ready || 0) > 0 && (
        <div style={ROW_BOX}>
          <span style={{ fontSize: 12.5, fontWeight: 700, flex: 1 }}>Креативы</span>
          <span onClick={() => downloadDealCreatives(d.id)} style={ACT} title="Архив со всеми креативами">↓</span>
        </div>)}
      {(now?.slot === 'live' || now?.slot === 'recon') && (
        <div style={ROW_BOX}>
          <span style={{ fontSize: 12.5, fontWeight: 700, flex: 1, color: d.report_ready ? 'var(--text-primary)' : 'var(--text-muted)' }}>Отчёт по РК</span>
          {/* «XLS» — весь отчёт; календарик — за выбранные дни (владелец 17.11.2026) */}
          {d.report_ready ? (
            <>
              <BusyAct label="XLS" title="Отчёт клиенту в Excel — весь флайт" style={ACT}
                run={() => downloadBlob(reportUrl(d.id))} />   {/* имя — с сервера: «…_по_<последний день данных>» */}
              <ReportDates dealId={d.id} startDate={d.report_from} groups={d.report_groups || []} style={{ ...ACT, padding: 0, width: 26 }} />
            </>
          ) : <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>после первого дня показов</span>}
        </div>)}
      {(now?.slot === 'recon' || d.master_docs?.master) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <MasterDocs docs={d.master_docs || null}
            line={({ key, ok, title, meta, right }) => (
              <div key={key} style={{ ...ROW_BOX, padding: '7px 10px', opacity: ok ? 1 : 0.8 }}>
                <span style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
                  <span title={meta} style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{meta}</span>
                </span>{right}
              </div>)} />
        </div>)}
      <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
        {now?.slot === 'recon' ? 'ДС, счёт и УПД появятся в пакете мастер-сделки.' : (now?.slot === 'prep' || now?.slot === 'live') ? 'ДС, счёт, УПД и акт — на закрытии. ДС можно выпустить на старте из карточки сделки.' : 'Креативы и документы появятся со «Сборки».'}</span>
      <span style={{ ...CAP, marginTop: 6 }}>Деньги</span>
      {[['сумма клиента', mln(d.amount)], ['наша сумма', d.our_sum != null ? mln(d.our_sum) : '—', 'var(--income-fg)'], ['оплата', 'после закрывающих']].map(([l, v, fg]) => (
        <div key={l} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '4px 0', borderBottom: '1px solid var(--border-row)', fontSize: 12.5 }}>
          <span style={{ color: 'var(--text-secondary)' }}>{l}</span>
          <span style={{ fontFamily: MONO, fontWeight: 700, color: fg || 'var(--text-primary)' }}>{v}</span>
        </div>))}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginTop: 'auto', paddingTop: 8 }}>
        {links.map(([t, href, path]) => (
          <a key={t} href={href} target="_blank" rel="noreferrer" title={t} aria-label={t} style={{ ...ACT, width: 34, height: 34, padding: 0, textDecoration: 'none' }}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path} /></svg>
          </a>))}
      </div>
    </>
  )
}

function NowBody({ now, err, row, d, canEdit, onAction, onSnooze, onReload, wide, tight }) {
  const hot = row.urgency === 'overdue'
  const code = row.code || row.id
  // В кампании отставание и площадки уже в показателях — под ними только «осталось N дн.» (макет v5, владелец 13.11.2026).
  const facts = now?.slot === 'live'
    ? (now.end_in != null && now.end_in >= 0 ? [`осталось ${now.end_in} дн.`] : [])
    : (row.state || []).filter(e => e.type === 'alert' || e.type === 'fact').slice(0, 2)
    .map(e => (e.k ? `${e.k}: ${e.v}` : e.v || e.text)).filter(Boolean)
  const next = row.turn?.mine ? NEXT[now?.slot] : `Ход не ваш — ${row.turn?.who || row.action_note || 'ждём'}`
  const a = row.action
  const hh = now?.head?.href || '#creatives'
  // Контур аккаунта: вместо «Продолжить сборку» — «Подтвердить запуск» в блоке сборки.
  const prio = now?.flow === 'приоритезация'
  const goOn = now?.slot === 'prep' && !now.external_launch ? (hh.startsWith('#') ? `/sales/deals/${code}${hh}` : hh) : null
  return (
    <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 12, flex: tight ? 'none' : 1 }}>
      {now ? <Steps steps={now.steps} at={now.at} /> : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{err || 'Загрузка…'}</span>}
      {/* Сборка — в виде блока ОРД; итоговая сверка — компактный блок по хендоффу design_handoff_final_recon (14.11.2026) */}
      {now?.slot === 'prep' && <AssemblyNow now={now} code={code} hot={hot} cols={tight ? 2 : 4} dealId={row.id} canEdit={canEdit} onDone={onReload} />}
      {/* Приоритезация до старта: чек-лист площадок и «Запустить» (16.11.2026) */}
      {now?.slot === 'prep' && prio && <PrioLaunch dealId={row.id} canEdit={canEdit} onDone={onReload} />}
      {/* Приоритезация на закрытии: только факт по площадкам (файл / сервис площадки), без настройки запроса */}
      {now?.slot === 'recon' && now.flow === 'приоритезация' && <PrioFactCard dealId={row.id} canEdit={canEdit}
        cardStyle={{ border: '1px solid var(--border-card)', borderRadius: 12, padding: '0 16px 14px' }} />}
      {now?.slot === 'recon' && <ClosingCompact dealId={row.id} canEdit={canEdit} hot={hot} wide={wide} />}
      {now && now.slot !== 'prep' && now.slot !== 'recon' && (
        <div style={{ ...BOX, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            {now.slot === 'live' && <span style={CAP}>Рекламная кампания</span>}
            {now.slot === 'live' && now.period_from && (
              <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{now.period_from} — {now.period_to}</span>)}
            {now.slot !== 'live' && <span style={{ fontSize: 13.5, fontWeight: 700 }}>{headline(now, row)}</span>}
            {hot && <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--danger-fg)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--danger)' }} />горит</span>}
          </div>
          {now.campaign && <Campaign c={now.campaign} wide={wide} endIn={now.end_in} now={headline(now, row)} />}
          {now.slot === 'live' && !now.campaign && now.own && <OwnRun o={now.own} flow={now.flow} />}
          {/* Приоритезация в размещении: площадка / план / факт, дозапуск (16.11.2026) */}
          {now.slot === 'live' && prio && <PrioLaunch dealId={row.id} live canEdit={canEdit} onDone={onReload} />}
          {(now.slot === 'booking' || now.slot === 'mp_prep' || now.slot === 'mp_sent') && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 8 }}>
              {tilesOf(now, row, d).map(([l, v, s, fg]) => <Tile key={l} l={l} v={v} s={s} fg={fg} />)}</div>)}
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
            {facts.map(t => <li key={t} style={{ display: 'flex', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
              <span style={{ width: 5, height: 5, borderRadius: 2, background: 'var(--warning)', marginTop: 6 }} />{t}</li>)}
            {!!next && <li style={{ display: 'flex', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
              <span style={{ width: 5, height: 5, borderRadius: 2, background: row.turn?.mine ? 'var(--accent)' : 'var(--text-disabled)', marginTop: 6 }} />
              {row.turn?.mine ? `Дальше: ${next}` : next}</li>}
          </ul>
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: tight ? 0 : 'auto' }}>
        {goOn && <a href={goOn} target="_blank" rel="noopener noreferrer" style={{ height: 32, padding: '0 16px', borderRadius: 9, background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 12.5, fontWeight: 700,
          display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}>Продолжить сборку →</a>}
        {/* у приоритезации «Запустить / Дозапустить» — в блоке площадок; кнопка строки «раскрыть» здесь свернула бы расхлоп */}
        {a && !goOn && now?.slot !== 'recon' && !now?.external_launch && !(prio && a.do === 'expand') && <button type="button" onClick={() => onAction(row, a)} disabled={!canEdit && a.do !== 'link' && a.do !== 'expand'}
          style={{ height: 32, padding: '0 16px', borderRadius: 9, border: 0, background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>{a.label}</button>}
        <button type="button" onClick={() => onSnooze(row)} style={{ marginLeft: 'auto', height: 32, padding: '0 12px', borderRadius: 9, border: '1px solid var(--border-card)',
          background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>⏱ Отложить</button>
      </div>
    </div>
  )
}

/**
 * `layout="row"` — расхлоп строки в три колонки; `layout="modal"` — модалка режима «Карточки» (экран 12 хендоффа v5): слева
 * «Сейчас» и «Последнее», справа команда, медиаплан и документы, деньги. Части одни и те же.
 */
export default function DealNow({ row, deal, canEdit, onAction, onSnooze, onReload, wide = true, layout = 'row' }) {
  const modal = layout === 'modal'
  const [now, setNow] = useState(null)
  const [hist, setHist] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let alive = true
    setNow(null); setHist(null); setErr('')
    api.get(`/sales/account-deals/${row.code || row.id}/now`, auth()).then(r => alive && setNow(r.data)).catch(() => alive && setErr('Блок «Сейчас» не загрузился'))
    api.get(`/sales/deals/${row.code || row.id}/history`, auth()).then(r => alive && setHist(r.data.items || [])).catch(() => alive && setHist([]))
    return () => { alive = false }
  }, [row.id, row.code])

  const d = deal || row
  const code = row.code || row.id
  const team = [['сейлз', d.sales_rep], ['аккаунт', d.account_manager], ['трафик', d.traffic_manager]]
  // Пиктограммы — из хендоффа v5 (бриф — планшет, отчёт — столбики, карточка — «открыть в новой вкладке»).
  const links = [['Бриф клиента', `/sales/deals/${code}#sec-traffic-brief`, ICON.brief],
    ['Отчёт по РК', `/traffic/campaign/${code}`, ICON.report], ['Открыть карточку сделки', `/sales/deals/${code}`, ICON.card]]
  const body = <NowBody now={now} err={err} row={row} d={d} canEdit={canEdit} onAction={onAction} onSnooze={onSnooze} onReload={onReload || (() => {})} wide={wide && !modal} tight={modal} />

  if (modal) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.15fr) minmax(0,1fr)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border-inner)', minWidth: 0 }}>
          {body}
          <div style={{ padding: '10px 18px 14px', borderTop: '1px solid var(--border-inner)', marginTop: 'auto' }}><History hist={hist} code={code} limit={3} compact /></div>
        </div>
        <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          <Team team={team} column />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}><Docs d={d} now={now} links={links} /></div>
        </div>
      </div>
    )
  }
  return (
    <div style={{ margin: '0 4px 10px', display: 'grid', gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr) minmax(0,1.05fr)', border: '1px solid var(--border-card)',
      borderRadius: 14, background: 'var(--bg-card)', overflow: 'hidden' }} onClick={e => e.stopPropagation()}>
      <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border-inner)' }}>
        {body}
        <Team team={team} />
      </div>
      <div style={{ padding: '14px 18px', borderRight: '1px solid var(--border-inner)', minWidth: 0 }}><History hist={hist} code={code} limit={5} /></div>
      <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}><Docs d={d} now={now} links={links} /></div>
    </div>
  )
}
