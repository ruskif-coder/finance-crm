// Правая колонка экрана «Статус системы» (макет design_handoff_status, 16.11.2026): «Онлайн сейчас», «Активность за
// сутки» и «Диск» с прогнозом. Онлайн — только сотрудники, окно 10 минут; зелёная метка — активность за 2 минуты.
import { MONO } from '@/components/salesTableKit'
import { fmtTime } from '@/lib/dates'
import { fmtGb, initials, pageLabel, plural, whenLabel } from './statusModel'

const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const cardBox = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }
const mono = (x) => <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{x}</span>

const agoText = (m) => (m < 0.5 ? 'сейчас' : `${Math.round(m)} мин назад`)
const xOf = (m) => `${Math.round((10 - Math.min(10, m)) * 10)}%`

function OnlineRow({ u }) {
  const last = Math.min(...u.ago), first = Math.max(...u.ago)
  const page = pageLabel(u.path)
  return (
    <span title={`${u.name} · ${page} · ${agoText(last)} · открытий: ${u.ago.length}`}
      style={{ display: 'grid', gridTemplateColumns: '26px 112px 1fr', gap: 9, alignItems: 'center', height: 33 }}>
      <span style={{ position: 'relative', width: 26, height: 26, boxSizing: 'border-box', borderRadius: 13, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: MONO, fontSize: 9.5, fontWeight: 700, color: 'var(--accent-fg)' }}>
        {initials(u.name)}
        <span style={{ position: 'absolute', right: -2, bottom: -2, width: 11, height: 11, boxSizing: 'border-box', borderRadius: '50%',
          background: u.live ? 'var(--income)' : 'var(--text-faint)', border: '2px solid var(--bg-card)' }} />
      </span>
      <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.name}</span>
        <span style={{ fontSize: 10, lineHeight: 1.2, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{page}</span>
      </span>
      <span style={{ position: 'relative', height: 33 }}>
        <span style={{ position: 'absolute', left: 0, right: 0, top: 16, height: 1, background: 'var(--border-inner)' }} />
        <span style={{ position: 'absolute', left: '50%', top: 6, bottom: 6, width: 1, background: 'var(--border-row)' }} />
        {u.ago.length > 1 && <span style={{ position: 'absolute', left: xOf(first), right: `${Math.round(Math.min(10, last) * 10)}%`, top: 14, height: 5, borderRadius: 3, background: 'var(--income-tint)' }} />}
        {[...u.ago].sort((a, b) => b - a).map((m, i) => {
          const isLast = m === last
          const s = isLast ? 13 : 9
          return <span key={i} title={agoText(m) + (isLast ? ` · ${page}` : '')} style={{ position: 'absolute', left: `calc(${xOf(m)} - ${s / 2}px)`, top: 16 - s / 2,
            width: s, height: s, borderRadius: '50%', background: isLast ? 'var(--income)' : 'var(--income-border)', border: '2px solid var(--bg-card)', boxSizing: 'border-box' }} />
        })}
      </span>
    </span>
  )
}

function Bars({ series, field, color }) {
  const mx = Math.max(1, ...series.map(s => s[field]))
  const hh = (iso) => fmtTime(iso).slice(0, 2)      // час по Москве: метка с сервера — в UTC
  return (
    <>
      <span style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 30, borderBottom: '1px solid var(--border-inner)' }}>
        {series.map(s => {
          const v = s[field]
          return <span key={s.hour} title={`${hh(s.hour)}:00 · ${v}`} style={{ flex: '1 1 0', height: v ? `${Math.max(4, Math.round(v / mx * 100))}%` : 2,
            minHeight: 2, borderRadius: '2px 2px 0 0', background: v ? color : 'var(--border-inner)' }} />
        })}
      </span>
      <span style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>
        <span>{series.length ? `${hh(series[0].hour)}:00 вчера` : ''}</span><span>{series[12] ? `${hh(series[12].hour)}:00` : ''}</span><span>сейчас</span>
      </span>
    </>
  )
}

export function OnlineAndActivity({ online, activity }) {
  const series = activity?.series || []
  const peak = (f) => Math.max(0, ...series.map(s => s[f]))
  return (
    <div style={{ ...cardBox, padding: '14px 16px 12px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 800, whiteSpace: 'nowrap' }}>Онлайн сейчас</span>
          <span style={{ ...cap, whiteSpace: 'nowrap' }}>за 10 минут</span>
          <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 19, fontWeight: 700, lineHeight: 1 }}>{online.length}</span>
        </span>
        {online.length ? (
          <span style={{ display: 'flex', flexDirection: 'column' }}>
            {online.map(u => <OnlineRow key={u.user_id} u={u} />)}
            <span style={{ display: 'grid', gridTemplateColumns: '26px 112px 1fr', gap: 9 }}>
              <span /><span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>только сотрудники</span>
              <span style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}><span>−10 мин</span><span>−5</span><span>сейчас</span></span>
            </span>
          </span>
        ) : <span style={{ fontSize: 12, color: 'var(--text-muted)', padding: '6px 0' }}>Сейчас никого</span>}
      </span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, paddingTop: 2 }}>
        <span style={{ fontSize: 14, fontWeight: 800 }}>Активность за сутки</span><span style={cap}>по журналу действий</span>
      </span>
      {[['actions', 'Действий в системе', activity?.actions_24h, 'var(--income)'], ['users', 'Пользователей', activity?.users_24h, 'var(--accent)']].map(([f, label, total, color]) => (
        <span key={f} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>{label}</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>пик {peak(f)} в час</span>
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 15, fontWeight: 700 }}>{total ?? '—'}</span>
          </span>
          <Bars series={series} field={f} color={color} />
        </span>
      ))}
    </div>
  )
}

function ForecastLine({ fc }) {
  if (!fc) return <span style={{ fontSize: 11.5, lineHeight: 1.4, color: 'var(--text-muted)' }}>Прогноз появится после недели дневных замеров</span>
  if (fc.flat) return <span style={{ fontSize: 11.5, lineHeight: 1.4, color: 'var(--text-muted)' }}>Рост не заметен — до жёлтого порога далеко</span>
  const w = Math.round(fc.weeks_to_warn)
  return (
    <span style={{ fontSize: 11.5, lineHeight: 1.4, color: 'var(--text-muted)' }}>
      Рост {mono(`${fmtGb(fc.growth_gb_week)} ГБ`)} в неделю — {w ? <>до жёлтого порога {mono(`≈ ${plural(w, 'неделя', 'недели', 'недель')}`)}, {whenLabel(fc.weeks_to_warn)}</> : <>жёлтый порог уже взят</>}
    </span>
  )
}

export function DiskCard({ disk, storage }) {
  const used = disk?.used_pct ?? 0
  const warnAt = 100 - (disk?.warn_pct ?? 20), critAt = 100 - (disk?.crit_pct ?? 10)
  const fill = used >= critAt ? 'var(--danger)' : used >= warnAt ? 'var(--warning)' : 'var(--income)'
  const dirs = disk?.dirs || []
  const max = Math.max(1, ...dirs.map(d => d.mb))
  return (
    <div style={{ ...cardBox, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 800 }}>Диск</span>
        <span style={cap}>занято {disk?.used_gb ?? '—'} из {disk?.total_gb ?? '—'} ГБ</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 15, fontWeight: 700 }}>{Math.round(used)} %</span>
      </span>
      <span style={{ position: 'relative', height: 8, borderRadius: 4, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
        <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, used)}%`, borderRadius: 4, background: fill }} />
        <span title={`Жёлтый порог: свободно ${disk?.warn_pct ?? 20} %`} style={{ position: 'absolute', left: `${warnAt}%`, top: -3, bottom: -3, width: 2, background: 'var(--warning)' }} />
        <span title={`Красный порог: свободно ${disk?.crit_pct ?? 10} %`} style={{ position: 'absolute', left: `${critAt}%`, top: -3, bottom: -3, width: 2, background: 'var(--danger)' }} />
      </span>
      <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--text-muted)' }}>
        <span>свободно {mono(`${disk?.free_gb ?? '—'} ГБ`)}</span>
        <span>пороги: <span style={{ fontFamily: MONO }}>{warnAt} % · {critAt} %</span></span>
      </span>
      <ForecastLine fc={disk?.forecast} />
      <span style={{ height: 1, background: 'var(--border-inner)' }} />
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>Хранилище файлов</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11.5, fontWeight: 700 }}>{storage || '—'}</span>
      </span>
      {dirs.map(d => (
        <span key={d.name} style={{ display: 'grid', gridTemplateColumns: '96px 1fr 54px', gap: 10, alignItems: 'center' }}>
          <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
          <span style={{ height: 6, borderRadius: 3, background: 'var(--bg-subtle)' }}><span style={{ display: 'block', height: 6, width: `${Math.round(d.mb / max * 100)}%`, minWidth: 2, borderRadius: 3, background: 'var(--text-faint)' }} /></span>
          <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, textAlign: 'right' }}>{d.mb} МБ</span>
        </span>
      ))}
    </div>
  )
}
