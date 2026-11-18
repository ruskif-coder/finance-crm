// Пульт раскрытой РК (хендофф design_handoff_traffic_expand_v2, 17.11.2026, раздел 7): одна строка 46px.
// Слева — цепочка «Заведение → Сбор → Раскладка» из ночного прогона проверок (`/api/rk-check/summary`, те же группы, что
// у прежней строки «Сводка»); справа — люди и управление РК, переехавшие из низа правой колонки.
// Пауза и стоп дублируют кнопки строки РК — осознанно, как на бою.
import { useState } from 'react'
import PersonChip from '@/components/PersonChip'
import { MONO, PortalPopover } from '@/components/salesTableKit'
import { RunToggle, StopBtn, TaskDoc } from '@/components/traffic/dashboardKit'

// Ширина правой колонки расхлопа (аналитика, хендофф v2, 17.11.2026) — общая для пульта и тела расхлопа.
export const ANALYTICS_W = 680

// NAVY (17.11.2026): блокер шага (красный) — оранжевый «действуй сейчас», вопрос (жёлтый) — внимание, норма — сталь
const LEVEL_DOT = { red: 'var(--signal)', yellow: 'var(--attn)', green: 'var(--ok)', skip: 'var(--text-faint)' }
const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer' }
const iconBtn = {
  ...plain, position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 30,
  boxSizing: 'border-box', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, color: 'var(--accent-fg)',
}
const ghost = {
  ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 11px', boxSizing: 'border-box',
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontSize: 12, fontWeight: 600,
  color: 'var(--text-secondary)', whiteSpace: 'nowrap',
}
// Пиктограммы — из макета (viewBox 16).
const ICON = {
  tasks: 'M4 1.5h5.5L12.5 4.5v10h-8.5zM9.5 1.5v3h3M6 8l1 1 2.5-2.5M6 11.5h4',
  report: 'M2 14h12M4 14V9M7 14V4M10 14V7M13 14V10.5',
  log: 'M3.5 1.5h9v13h-9zM6 5h4M6 8h4M6 11h2.5',
}

const Count = ({ n }) => (n > 0 ? (
  <span style={{ fontFamily: MONO, position: 'absolute', top: -6, right: -6, display: 'inline-flex', alignItems: 'center',
    justifyContent: 'center', minWidth: 16, height: 16, padding: '0 3px', boxSizing: 'border-box', borderRadius: 8,
    background: 'var(--accent)', border: '2px solid var(--bg-card)', fontSize: 9, fontWeight: 700, color: 'var(--bg-card)' }}>
    {n > 99 ? '99+' : n}</span>
) : null)

const Glyph = ({ d }) => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
)

/** Плашка шага цепочки — в два этажа (владелец 17.11.2026): сверху название, счёт и ссылка-действие, снизу текст. Высота
 * одна у всех трёх, поэтому длинный текст не двигает кнопки справа. Проблема (красный или жёлтый) — на `--warning-tint`. */
function Step({ g, onAction }) {
  const bad = g.level === 'red' || g.level === 'yellow'
  const act = g.action
  return (
    <span title={`${g.title}${g.total ? ` ${g.ok} из ${g.total}` : ''} · ${g.text || ''}`}
      style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 2, height: 44,
        padding: '0 10px', borderRadius: 9, boxSizing: 'border-box', whiteSpace: 'nowrap',
        background: g.level === 'red' ? 'var(--signal-tint)' : bad ? 'var(--attn-tint)' : 'transparent',
        border: `1px solid ${g.level === 'red' ? 'var(--signal-border)' : bad ? 'var(--attn-border)' : 'var(--border-inner)'}` }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        <span style={{ flex: '0 0 7px', width: 7, height: 7, borderRadius: 2, background: LEVEL_DOT[g.level] || LEVEL_DOT.skip }} />
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 700,
          color: 'var(--text-primary)' }}>{g.title}</span>
        {g.total > 0 && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)' }}>{g.ok}/{g.total}</span>}
        {!!act && (
          <button type="button" onClick={e => { e.stopPropagation(); onAction(act.target, act) }}
            style={{ ...plain, marginLeft: 'auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 11.5,
              fontWeight: 700, color: 'var(--accent-fg)' }}>{act.label} →</button>
        )}
      </span>
      <span style={{ minWidth: 0, fontSize: 12, color: bad ? 'var(--text-primary)' : 'var(--text-muted)', overflow: 'hidden',
        textOverflow: 'ellipsis' }}>{g.text}</span>
    </span>
  )
}

/** «акк. Имя · трафик Имя ▾» — смена трафика своим списком (без нативного select), рядовому — текстом. */
function People({ owners, reps, onPick }) {
  const [open, setOpen] = useState(false)
  if (!owners) return null
  const name = owners.traffic || 'не назначен'
  const opts = [{ user_id: null, name: '— не назначен —' }, ...(reps || [])]
  return (
    // «в 2 этажа с иконкой», как «Команда» в «Моих сделках» (владелец 18.11.2026) — общий PersonChip; трафик меняется кликом по имени
    <span data-pop-root style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 16, paddingRight: 6, minWidth: 0 }}>
      <PersonChip role="аккаунт" name={owners.account} />
      <PersonChip role="трафик" name={owners.traffic}>
        {owners.can_change_traffic ? (
          <button type="button" onClick={() => setOpen(o => !o)} title="Сменить трафика"
            style={{ ...plain, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', borderBottom: '1px dashed var(--text-faint)', whiteSpace: 'nowrap', textAlign: 'left' }}>{name} ▾</button>
        ) : null}
      </PersonChip>
      <PortalPopover open={open} align="right" minWidth={200} offset={6}
        style={{ padding: 5, borderRadius: 12, boxShadow: 'var(--shadow-float)' }}>
        {opts.map(o => {
          const on = (owners.traffic_user_id ?? null) === o.user_id
          return (
            <button key={o.user_id ?? 'none'} type="button" onClick={() => { setOpen(false); if (!on) onPick(o.user_id) }}
              style={{ ...plain, display: 'flex', alignItems: 'center', width: '100%', height: 30, padding: '0 9px', borderRadius: 8,
                fontSize: 12.5, fontWeight: on ? 700 : 500, color: on ? 'var(--accent-fg)' : 'var(--text-primary)',
                background: on ? 'var(--accent-tint)' : 'transparent', textAlign: 'left' }}>
              {o.is_master ? '★ ' : ''}{o.name}</button>
          )
        })}
      </PortalPopover>
    </span>
  )
}

/**
 * props: rk — строка реестра; d — расхлоп (`GET /campaign/{id}`); sum — сводка проверок этой РК (может быть null);
 * mayEdit, mayReport — права; reps — список трафиков; notesCount, logOpen, onToggleLog — лог РК;
 * onAction(target) — ссылка шага цепочки; onPickTraffic(userId); onStart, onPause, onStop, onFinish;
 * onDspRefresh — «Обновить данные в DSP» (null, если нельзя).
 */
export default function RkPult({ rk, d, sum, mayEdit, mayReport, reps, notesCount, logOpen, onToggleLog, onAction,
  onPickTraffic, onStart, onPause, onStop, onFinish, onDspRefresh }) {
  const running = rk.status === 'запущена'
  const block = rk.dsp_block
  const hint = d?.launch_hint || rk.launch_hint
  const mainTitle = block || (running ? 'Поставить всю РК на паузу'
    : hint ? `Запуск заперт: ${hint}` : rk.status === 'пауза' ? 'Снять РК с паузы' : 'Запустить РК')
  return (
    // Одна строка, разделённая по той же границе, что площадки и аналитика под ней (владелец 17.11.2026): справа колонка
    // `ANALYTICS_W` с людьми и управлением — не сжимается; слева шаги делят остаток, при сужении текст уходит в подсказку.
    <div style={{ display: 'flex', alignItems: 'stretch', boxSizing: 'border-box', borderBottom: '1px solid var(--border-card)' }}>
      <span style={{ flex: '1 1 auto', display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, padding: '8px 14px 8px 18px',
        borderRight: '1px solid var(--border-card)' }}>
        {(sum?.groups || []).map(g => <Step key={g.key} g={g} onAction={onAction} />)}
        {!sum && <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>проверок заведения, сбора и раскладки ещё не было</span>}
      </span>
      <span style={{ flex: `0 0 ${ANALYTICS_W}px`, width: ANALYTICS_W, boxSizing: 'border-box', display: 'flex', alignItems: 'center',
        justifyContent: 'flex-end', gap: 6, padding: '8px 14px', minWidth: 0 }}>
        {/* люди — к левому краю колонки, кнопки остаются справа (владелец 18.11.2026) */}
        <span style={{ marginRight: 'auto', minWidth: 0, display: 'inline-flex' }}><People owners={d?.owners} reps={reps} onPick={onPickTraffic} /></span>
        <TaskDoc text={d?.traffic_brief} brief={d?.mp_brief} deal={rk.deal_code} title={rk.deal_title} advertiser={d?.advertiser_label}
          trigger={(openDoc, has) => (
            <button type="button" className="tp-icon" onClick={openDoc} style={iconBtn}
              title={has ? 'Задачи по РК от аккаунта и бриф медиаплана' : 'Задачи по РК: от аккаунта пусто, есть бриф медиаплана'}>
              <Glyph d={ICON.tasks} /><Count n={has ? 1 : 0} />
            </button>
          )} />
        {mayReport && (
          <a href={`/traffic/campaign/${encodeURIComponent(rk.deal_code || '')}`} className="tp-icon" title="Отчёт по РК"
            style={{ ...iconBtn, textDecoration: 'none' }}><Glyph d={ICON.report} /></a>
        )}
        <button type="button" className="tp-icon" onClick={onToggleLog} title={`Лог РК${notesCount ? ` · записей ${notesCount}` : ''}`}
          style={{ ...iconBtn, ...(logOpen ? { background: 'var(--accent-tint)', borderColor: 'var(--accent-border)' } : null) }}>
          <Glyph d={ICON.log} /><Count n={notesCount} />
        </button>
        {!!onDspRefresh && (
          <button type="button" className="tp-icon" onClick={onDspRefresh} aria-label="Обновить данные в DSP"
            title="Обновить данные в DSP: перезаписать ссылки, пиксели и таргеты по текущим данным; сначала покажет, что изменится"
            style={{ ...ghost, padding: 0, width: 30, justifyContent: 'center' }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.7-4M13.5 2.5V5H11" /></svg>
          </button>
        )}
        {mayEdit && (
          <>
            <span style={{ width: 1, height: 22, background: 'var(--border-inner)', margin: '0 2px' }} />
            {/* Те же кнопки, что в строке РК и у площадок (владелец 17.11.2026), — по высоте соседних кнопок пульта. */}
            <RunToggle running={running} size={30} disabled={!!block} title={mainTitle}
              label={running ? 'Пауза РК' : rk.status === 'пауза' ? 'Возобновить РК' : 'Запустить РК'}
              onClick={() => (running ? onPause() : onStart())} />
            <StopBtn size={30} disabled={!!block} title={block || 'Остановить РК'} label="Стоп РК" onClick={onStop} />
            <button type="button" className="tp-icon" onClick={onFinish}
              title="Двигает сделку на стадию «Итоговая сверка» — хозяином снова становится аккаунт"
              style={{ ...ghost, fontWeight: 700 }}>Завершить РК</button>
          </>
        )}
      </span>
    </div>
  )
}
