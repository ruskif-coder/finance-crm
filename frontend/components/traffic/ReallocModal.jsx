// «Темп размещения → Перераспределить» (владелец 24.10.2026). Показывает, как изменятся планы площадок (их сумма — лимиты
// креативов в DSP), если недобор площадок, упёршихся в сеть, отдать площадкам с запасом предложения. Расчёт — сервер
// (`app/ad/realloc.propose`); здесь только показ и правка нового плана руками. «Применить» пишет ручные планы и сразу
// шлёт лимиты в DSP; «Снять ручные планы» возвращает площадки на веса балансировщика.
import { useEffect, useState } from 'react'
import { Modal, MONO } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'
import api from '@/lib/api'
import { grp } from '@/lib/salesFormat'
import PaceCell from './PaceCell'

const CAP = { fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const ghost = { display: 'inline-flex', alignItems: 'center', height: 38, padding: '0 16px', borderRadius: 12, background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }
const ROLE_FG = { 'донор': 'var(--danger-fg)', 'получатель': 'var(--income-fg)', 'запас': 'var(--accent-fg)' }
const ROLE_TXT = { 'донор': 'отдаёт', 'получатель': 'берёт', 'запас': 'есть запас' }
// Те же числа, что в колонке «Темп» дашборда (`PaceCell`), открыто: сутки — показано / предложено сетью; возможность в сутки;
// нужно в сутки до конца; затем перенос: отдаёт или берёт, новый план и сколько нужно в сутки после (владелец 24.10.2026).
const COLS = '1.4fr 1.3fr 0.85fr 0.85fr 0.8fr 0.85fr 0.95fr 0.95fr 1.05fr 0.85fr'
const HEAD = [['площадка'], ['темп'], ['показано', 'за сутки'], ['предложено', 'сетью за сутки'], ['может', 'в сутки ≈'],
  ['нужно', 'в сутки до конца'], ['план', 'сейчас'], ['отдаёт / берёт', 'за флайт'], ['новый план'], ['нужно', 'в сутки после']]
const num = { fontFamily: MONO, textAlign: 'right' }
const signed = (v) => (v > 0 ? `+${grp(v)}` : v < 0 ? `−${grp(-v)}` : '—')

export default function ReallocModal({ row, auth, canEdit = true, onClose, onDone, onBack }) {
  const [v, setV] = useState(null)
  const [edit, setEdit] = useState({})
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)

  useEffect(() => {
    let alive = true
    api.get(`/traffic-dashboard/campaign/${row.id}/realloc`, auth())
      .then(r => { if (alive) setV(r.data) })
      .catch(e => { if (alive) setErr(e?.response?.data?.detail || 'Не удалось посчитать перераспределение') })
    return () => { alive = false }
  }, [row.id, auth])

  const planOf = (r) => (edit[r.id] !== undefined ? edit[r.id] : r.plan_new)
  // «нужно в сутки после» пересчитывается и при ручной правке нового плана — тем же правилом, что на сервере
  const needAfter = (r, np) => (v?.days_left ? Math.round(Math.max(0, (np || 0) - r.fact) / v.days_left) : 0)
  const changed = (v?.rows || []).filter(r => r.running && planOf(r) !== r.plan)
  const total = (v?.rows || []).reduce((a, r) => a + (r.running || r.plan ? (planOf(r) || 0) : 0), 0)
  const over = v?.plan && total > v.plan * 1.001

  const run = async (fn, what) => {
    setBusy(true); setErr('')
    try {
      const r = await fn()
      setV(r.data.view); setEdit({}); setDone(what); onDone && onDone()
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось выполнить') } finally { setBusy(false) }
  }
  const apply = () => run(() => api.post(`/traffic-dashboard/campaign/${row.id}/realloc`,
    { plans: Object.fromEntries(changed.map(r => [r.id, planOf(r)])) }, auth()), 'планы записаны, лимиты ушли в DSP')
  const reset = () => run(() => api.delete(`/traffic-dashboard/campaign/${row.id}/realloc`, auth()),
    'ручные планы сняты — площадки снова по весам')

  const off = busy || !canEdit || !changed.length || over || !v?.can_apply
  const title = (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.02em' }}>Перераспределить объём</span>
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)' }}>{row.deal_code}
        {!!v && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> · до конца флайта {v.days_left} дн.</span>}</span>
    </span>
  )
  const footer = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%' }}>
      {err ? <span style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>⚠ {err}</span>
        : over ? <span style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>⚠ сумма планов {grp(total)} больше плана РК {grp(v.plan)}</span>
          : <span style={{ fontSize: 12, color: done ? 'var(--income-fg)' : 'var(--text-faint)' }}>{done || (!canEdit ? 'меняет трафик' : '')}</span>}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 9 }}>
        {!!onBack && <button type="button" style={ghost} onClick={onBack} disabled={busy}>← Назад</button>}
        {canEdit && !!v?.has_manual && <button type="button" style={ghost} onClick={reset} disabled={busy}>Снять ручные планы</button>}
        {canEdit && (
          <button type="button" onClick={apply} disabled={off}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 38, padding: '0 18px', border: 'none', borderRadius: 12,
              background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 13, fontWeight: 700, cursor: off ? 'default' : 'pointer',
              opacity: off ? 0.5 : 1 }}>
            {busy && <Cube variant="spinner" size={14} />}Применить{changed.length ? ` (${changed.length})` : ''}
          </button>
        )}
      </span>
    </div>
  )

  return (
    <Modal title={title} width={1180} footer={footer} onClose={() => { if (!busy) onClose() }}>
      {!v && !err && <div style={{ display: 'flex', gap: 8, padding: 16, color: 'var(--text-muted)' }}><Cube variant="spinner" size={14} /> считаю…</div>}
      {!!v && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '6px 0 4px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', padding: '12px 0', background: 'var(--bg-subtle)', borderRadius: 12 }}>
            {[['недобор: упёрлись в сеть', grp(v.shortfall), 'var(--danger-fg)'], ['запас у площадок в темпе', grp(v.spare), 'var(--accent-fg)'],
              ['переносим', grp(v.moved), 'var(--income-fg)'], ['не пристроить', grp(v.unplaced), v.unplaced ? 'var(--warning-fg)' : 'var(--text-secondary)']]
              .map(([l, n, c], i) => (
                <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '0 14px', borderLeft: `1px solid ${i ? 'var(--border-card)' : 'transparent'}` }}>
                  <span style={{ ...CAP, fontWeight: 400 }}>{l}</span>
                  <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: c }}>{n}</span>
                </span>
              ))}
          </div>
          {!!v.boost_live && <div style={{ fontSize: 12.5, color: 'var(--warning-fg)' }}>
            Идёт «Поднять темп»: планы площадок сейчас подняты на его процент. Записать их ручными значит продлить буст
            и перекрутить план РК — снимите буст или дождитесь его конца, тогда можно применить.</div>}
          {!!v.unplaced && <div style={{ fontSize: 12.5, color: 'var(--warning-fg)' }}>
            {grp(v.unplaced)} показов отдать некому — у площадок в темпе нет столько запаса: нужны новые площадки.</div>}
          {!v.shortfall && <div style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            Площадок, упёршихся в сеть, нет — переносить нечего. Если темп ниже плана, причина в другом: смотрите пометки
            у площадок (трафик есть, а показов нет — это «Поднять темп» или креатив).</div>}
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 8, padding: '6px 8px', alignItems: 'end' }}>
              {HEAD.map(([h, sub], i) => (
                <span key={h + i} style={{ display: 'flex', flexDirection: 'column', textAlign: i > 1 ? 'right' : 'left' }}>
                  <span style={CAP}>{h}</span>
                  {!!sub && <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{sub}</span>}
                </span>
              ))}
            </div>
            {v.rows.filter(r => r.running).sort((a, b) => (a.delta - b.delta)).map(r => {
              const np = planOf(r)
              return (
                <div key={r.id} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 8, padding: '7px 8px', alignItems: 'center',
                  borderTop: '1px solid var(--border-inner)', fontSize: 12.5 }}>
                  <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                    <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
                    {!!r.note && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{r.note}</span>}
                  </span>
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                    <PaceCell pace={r.pace ? { status: r.pace, day: r.day, shows: r.shows_day, need: r.need, offered: r.offered_day,
                      capacity: r.capacity, chronic: r.chronic } : null} />
                    {r.role !== 'без изменений' && <span style={{ fontSize: 10.5, fontWeight: 700, color: ROLE_FG[r.role] }}>{ROLE_TXT[r.role]}</span>}
                  </span>
                  <span style={num}>{r.shows_day != null ? grp(r.shows_day) : '—'}</span>
                  <span style={num}>{r.offered_day != null ? grp(r.offered_day) : '—'}</span>
                  <span style={num}>{r.capacity != null ? grp(r.capacity) : '—'}</span>
                  <span style={{ ...num, fontWeight: 700 }}>{grp(r.need)}</span>
                  <span style={num}>{grp(r.plan)}{r.fixed_plan != null ? ' ✎' : ''}</span>
                  <span style={{ ...num, fontWeight: 700, color: np > r.plan ? 'var(--income-fg)' : np < r.plan ? 'var(--danger-fg)' : 'var(--text-faint)' }}>
                    {signed(np - r.plan)}</span>
                  {canEdit ? (
                    <input type="number" min={r.fact} value={np ?? ''} disabled={busy}
                      onChange={e => setEdit(s => ({ ...s, [r.id]: e.target.value === '' ? r.plan : Math.round(Number(e.target.value)) }))}
                      style={{ width: '100%', boxSizing: 'border-box', height: 28, padding: '0 8px', fontFamily: MONO, fontSize: 12.5, textAlign: 'right',
                        border: '1px solid var(--border-card)', borderRadius: 8, background: 'var(--bg-card)', color: 'var(--text-primary)' }} />
                  ) : <span style={num}>{grp(np)}</span>}
                  <span style={{ ...num, fontWeight: 700, color: needAfter(r, np) > (r.capacity ?? Infinity) ? 'var(--warning-fg)' : 'var(--text-primary)' }}
                    title={r.capacity != null && needAfter(r, np) > r.capacity ? 'больше, чем площадке предлагает сеть в сутки' : ''}>
                    {grp(needAfter(r, np))}</span>
                </div>
              )
            })}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
            «Показано» и «предложено сетью» — последние отчитанные сутки, «может» — медиана предложенного за 5 суток, как в колонке
            «Темп» дашборда. Донор — площадка, которой сеть предлагает меньше, чем нужно в день: её остаток сверх того, что она успеет по своей
            возможности (медиана предложенного × дни), уходит площадкам в темпе — не больше половины их неиспользованного
            предложения. Сумма планов не меняется, план не ниже факта. Новый план держится ночным пересчётом и балансировщиком
            (✎ — ручной план) до «Снять ручные планы»; площадка, завершённая трафиком, свой объём отдаёт остальным по весам.
          </div>
        </div>
      )}
    </Modal>
  )
}
