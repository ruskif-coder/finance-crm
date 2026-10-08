// Окно «Темп размещения» (владелец 08.10.2026; макет — docs/темп модалка.zip). Временно поднимает остаток РК
// на X % на N дней. Лимиты креативов в DSP переписываются сразу, после последнего дня объём возвращается
// ночным пересчётом, дни флайта не меняются. Площадки вне нашей DSP (Adfox) лимитов в DSP не имеют —
// окно называет им новую суточную норму. Действующий буст можно снять досрочно.
// Прогноз считается здесь по числам сервера (`GET …/boost`); добавка — только по площадкам, которых буст
// касается (запущены, без заданного объёма), а не по всей РК.
import { useEffect, useState } from 'react'
import { Modal, MONO } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'
import api from '@/lib/api'

const PCTS = [10, 20, 30, 50, 100]
const DAYS = [1, 2, 3, 5, 7]
const nf = (v) => Math.round(v).toLocaleString('ru-RU')
const dmy = (d) => (d ? `${String(d).slice(8, 10)}.${String(d).slice(5, 7)}` : '—')
const pl = (n, a, b, c) => (n % 10 === 1 && n % 100 !== 11 ? a
  : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? b : c)
// g = план − прогноз: g > 0 — недокрут («−», красный), g < 0 — перекрут («+», зелёный)
const gapText = (g) => (g > 0 ? `−${nf(g)}` : g < 0 ? `+${nf(-g)}` : '0')
const gapFg = (g) => (g > 0 ? 'var(--danger-fg)' : g < 0 ? 'var(--income-fg)' : 'var(--text-secondary)')

const CAP = { fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase',
  color: 'var(--text-cap)' }
const preset = (on) => ({ display: 'inline-flex', alignItems: 'center', height: 36, padding: '0 14px', borderRadius: 10,
  background: on ? 'var(--accent)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`,
  color: on ? 'var(--bg-card)' : 'var(--text-secondary)', fontFamily: MONO, fontSize: 12.5, fontWeight: 700,
  cursor: 'pointer', transition: 'background-color 150ms ease, color 150ms ease' })
const ghost = { display: 'inline-flex', alignItems: 'center', height: 38, padding: '0 16px', borderRadius: 12,
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', fontSize: 13, fontWeight: 600,
  color: 'var(--text-secondary)', cursor: 'pointer' }

const Field = ({ value, onChange, suffix, min, max }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', height: 36, boxSizing: 'border-box', padding: '0 12px',
    border: '1px solid var(--border-card)', borderRadius: 10, background: 'var(--bg-card)', marginLeft: 'auto' }}>
    <input type="number" min={min} max={max} value={value} onChange={onChange}
      style={{ width: 56, border: 'none', outline: 'none', background: 'transparent', fontFamily: MONO,
        fontSize: 13, fontWeight: 700, textAlign: 'right', color: 'var(--text-primary)' }} />
    <span style={{ fontSize: 12, color: 'var(--text-muted)', paddingLeft: 4 }}>{suffix}</span>
  </span>
)

export default function BoostModal({ row, auth, canEdit = true, onClose, onDone }) {
  const [info, setInfo] = useState(null)
  const [pct, setPct] = useState(20)
  const [days, setDays] = useState(3)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)

  useEffect(() => {
    let alive = true
    api.get(`/traffic-dashboard/campaign/${row.id}/boost`, auth())
      .then(r => { if (alive) setInfo(r.data) })
      .catch(e => { if (alive) setErr(e?.response?.data?.detail || 'Не удалось прочитать состояние') })
    return () => { alive = false }
  }, [row.id, auth])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  const left = info?.days_left || 0
  const maxPct = info?.max_pct || 100
  const bad = !Number.isInteger(pct) || pct < 1 || pct > maxPct ? `Процент — целое число от 1 до ${maxPct}`
    : !Number.isInteger(days) || days < 1 ? 'Дней — целое число, не меньше одного'
      : days > left ? `До конца флайта осталось ${left} дн.` : ''

  // Расчёт макета: прогноз по текущему темпу и после добавки (только по площадкам, которых буст касается).
  const plan = info?.plan || 0
  const fact = info?.fact || 0
  const rest = Math.max(0, plan - fact)
  const dailyNow = left ? rest / left : 0
  const extraDaily = left ? ((info?.rest_free || 0) / left) * (pct / 100) : 0
  const extra = extraDaily * (Number.isFinite(days) ? days : 0)
  const pace = info?.days_done ? fact / info.days_done : 0
  const forecastNow = fact + pace * left
  const gapNow = plan - forecastNow
  const gapNew = plan - (forecastNow + extra)
  const free = info?.sites_free || 0
  const fixed = info?.sites_fixed || 0
  const nothing = !!info && free === 0
  const active = info?.boost

  const run = async (fn) => {
    setBusy(true); setErr('')
    try {
      const r = await fn()
      setRes(r.data)
      onDone && onDone()
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Не удалось выполнить')
    } finally { setBusy(false) }
  }
  const start = () => run(() => api.post(`/traffic-dashboard/campaign/${row.id}/boost`, { pct, days }, auth()))
  const cancel = () => run(() => api.delete(`/traffic-dashboard/campaign/${row.id}/boost`, auth()))

  const ctaOff = busy || !!bad || !info?.can_start || nothing || !canEdit
  const title = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.02em' }}>Темп размещения</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 400 }}>
          <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)' }}>{row.deal_code}</span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {[info?.advertiser, info?.brand, info?.service].filter(Boolean).join(' · ')}
          </span>
        </span>
      </span>
      {!!info && (
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 10px',
          background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, whiteSpace: 'nowrap' }}>
          <span style={{ ...CAP, fontWeight: 400, letterSpacing: '.08em' }}>до конца флайта</span>
          <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700 }}>{left}</span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>дн.</span>
        </span>
      )}
      <button type="button" onClick={() => { if (!busy) onClose() }} aria-label="Закрыть" title="Закрыть"
        style={{ marginLeft: info ? 0 : 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 30, height: 30, borderRadius: 9, border: 'none', background: 'transparent', color: 'var(--text-muted)',
          cursor: 'pointer', flex: '0 0 30px' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>
  )

  const scopeNote = !info ? '' : nothing ? 'нечего поднимать — все площадки с заданным объёмом'
    : fixed ? `${fixed} ${pl(fixed, 'площадка', 'площадки', 'площадок')} с заданным объёмом не меняются` : ''
  const footer = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%' }}>
      {err ? <span style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>⚠ {err}</span>
        : <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase',
          color: 'var(--text-faint)' }}>{!canEdit ? 'меняет трафик' : scopeNote}</span>}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 9 }}>
        <button type="button" style={ghost} onClick={onClose} disabled={busy}>{res ? 'Закрыть' : 'Отмена'}</button>
        {!res && canEdit && !!active && (
          <button type="button" style={ghost} onClick={cancel} disabled={busy}>Снять досрочно</button>
        )}
        {!res && (
          <button type="button" onClick={start} disabled={ctaOff}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 38, padding: '0 18px', border: 'none',
              borderRadius: 12, background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 13, fontWeight: 700,
              whiteSpace: 'nowrap', cursor: ctaOff ? 'default' : 'pointer', opacity: ctaOff ? 0.5 : 1 }}>
            {busy && <Cube variant="spinner" size={14} />}
            {Number.isInteger(pct) && Number.isInteger(days)
              ? `${active ? 'Заменить: ' : ''}Поднять на ${pct} % на ${days} ${pl(days, 'день', 'дня', 'дней')}`
              : 'Поднять'}
          </button>
        )}
      </span>
    </div>
  )

  const lim = res?.limits
  return (
    <Modal title={title} width={660} footer={footer} onClose={() => { if (!busy) onClose() }}>
      {!info && !err && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 16, color: 'var(--text-muted)' }}>
          <Cube variant="spinner" size={14} /> читаю состояние РК…
        </div>
      )}

      {info && !res && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '6px 0 4px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', padding: '12px 0',
            background: 'var(--bg-subtle)', borderRadius: 12 }}>
            {[
              ['факт', nf(fact), `из ${nf(plan)}`, 'var(--income-fg)'],
              ['остаток рк', nf(rest), 'показов', 'var(--text-primary)'],
              ['прогноз недокрута', gapText(gapNow), 'по текущему темпу', gapFg(gapNow)],
              ['площадок без объёма', String(free), `из ${free + fixed}`, 'var(--accent-fg)'],
            ].map(([l, v, u, c], i) => (
              <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '0 14px',
                borderLeft: `1px solid ${i ? 'var(--border-card)' : 'transparent'}` }}>
                <span style={{ ...CAP, fontWeight: 400, letterSpacing: '.08em' }}>{l}</span>
                <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: c, whiteSpace: 'nowrap', lineHeight: 1.1 }}>{v}</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{u}</span>
              </span>
            ))}
          </div>

          {active && (
            <div style={{ padding: '9px 12px', borderRadius: 10, fontSize: 13, background: 'var(--warning-tint)',
              color: 'var(--warning-text)' }}>
              Сейчас действует: +{active.pct} % до {dmy(active.until)} (остаток при старте {nf(active.rest_at_start || 0)}).
              Новое значение заменит его.
            </div>
          )}
          {!info.can_start && (
            <div style={{ fontSize: 13, color: 'var(--danger-fg)' }}>
              Сейчас поднять нельзя: РК не стартовала, флайт закончился или РК окончена.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <span style={CAP}>На сколько процентов</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {PCTS.filter(p => p <= maxPct).map(p => (
                <button key={p} type="button" style={preset(pct === p)} onClick={() => setPct(p)}>+{p} %</button>
              ))}
              <Field value={pct} min={1} max={maxPct} suffix="%"
                onChange={e => setPct(e.target.value === '' ? NaN : parseInt(e.target.value, 10))} />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <span style={CAP}>Сколько дней держать</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {DAYS.filter(d => d <= left).map(d => (
                <button key={d} type="button" style={preset(days === d)} onClick={() => setDays(d)}>{d} дн.</button>
              ))}
              <Field value={days} min={1} max={left || 1} suffix="дн."
                onChange={e => setDays(e.target.value === '' ? NaN : parseInt(e.target.value, 10))} />
            </div>
            {!!bad && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{bad}</span>}
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 14px',
            background: 'var(--bg-tint)', border: '1px solid var(--accent-border)', borderRadius: 12 }}>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 3, flex: '1 1 auto', minWidth: 0 }}>
              <span style={{ ...CAP, fontWeight: 400, letterSpacing: '.08em', color: 'var(--accent-fg)' }}>Что произойдёт</span>
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                {free} {pl(free, 'площадка получит', 'площадки получат', 'площадок получат')} +{Number.isFinite(pct) ? pct : 0} % к дневному объёму
                на {Number.isFinite(days) ? days : 0} {pl(days, 'день', 'дня', 'дней')} — это ещё ~{nf(extra)} показов сверх текущего темпа.
              </span>
            </span>
            <span style={{ display: 'flex', gap: 18, flex: '0 0 auto' }}>
              {[
                ['дневной объём', nf(dailyNow), nf(dailyNow + extraDaily), 'var(--accent-fg)', false],
                ['недокрут после', gapText(gapNow), gapText(gapNew), gapFg(gapNew), true],
              ].map(([l, a, b, c, sep]) => (
                <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end',
                  paddingLeft: sep ? 18 : 0, borderLeft: sep ? '1px solid var(--accent-border)' : 'none' }}>
                  <span style={{ ...CAP, fontWeight: 400, letterSpacing: '.08em' }}>{l}</span>
                  <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
                    <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{a}</span>
                    <span style={{ color: 'var(--text-faint)' }}>→</span>
                    <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: c }}>{b}</span>
                  </span>
                </span>
              ))}
            </span>
          </div>

          <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.45 }}>
            Лимиты креативов в DSP перепишутся сразу. После последнего дня объём вернётся к исходному на ночном
            пересчёте, дни флайта не меняются. Площадки с заданным объёмом не затрагиваются.
          </span>
        </div>
      )}

      {res && (
        <div style={{ padding: '6px 0' }}>
          <div style={{ padding: '10px 12px', borderRadius: 10, fontSize: 13, lineHeight: 1.5, marginBottom: 10,
            background: lim?.failed?.length ? 'var(--warning-tint)' : 'var(--income-tint)',
            color: lim?.failed?.length ? 'var(--warning-text)' : 'var(--income-fg)' }}>
            {res.boost ? `Темп поднят на ${res.boost.pct} % до ${dmy(res.boost.until)}.` : 'Буст снят, исходный план возвращён.'}
            {' '}Лимитов в DSP обновлено: {lim?.updated ?? 0}
            {lim?.skipped ? ' (РК ещё не выгружена в DSP)' : ''}.
            {(lim?.failed || []).map((f, i) => (
              <div key={i}>⚠ креатив {f.creative_id || '—'}: {f.error} — ночной прогон повторит</div>
            ))}
          </div>
          {!!res.external?.length && (
            <div style={{ padding: '10px 12px', borderRadius: 10, background: 'var(--warning-tint)',
              color: 'var(--warning-text)', fontSize: 13, lineHeight: 1.5 }}>
              <b>Измените лимиты Adfox{res.boost ? '' : ' (верните прежние)'}:</b>
              {res.external.map(e => (
                <div key={e.placement_id} style={{ display: 'flex', gap: 10, padding: '3px 0' }}>
                  <span style={{ flex: 1 }}>{e.name}{e.surfaces?.length ? ` · ${e.surfaces.join(', ')}` : ''}</span>
                  <span style={{ fontFamily: MONO }}>{nf(e.per_day || 0)} в сутки · план {nf(e.plan || 0)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
