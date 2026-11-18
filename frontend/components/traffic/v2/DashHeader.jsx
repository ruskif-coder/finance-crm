// Шапка дашборда трафика v2 (хендофф design_handoff_traffic_expand_v2, 17.11.2026, раздел 4) и панель списка РК (раздел 6).
// Свежесть — плашкой с кнопкой «Обновить из сделок» (кнопка — только админу, как на бою); «без факта» — короткой плашкой с
// прежним текстом баннера в подсказке; сверка с Weborama — плашкой ТОЛЬКО при сбое (владелец 17.11.2026), в норме её нет.
import { Segmented } from '@/lib/motion'
import { useState } from 'react'
import { MONO, PortalPopover } from '@/components/salesTableKit'
import { dm as dmShared } from '@/lib/salesFormat'

const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer' }
export const headBtn = {
  ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 12px', boxSizing: 'border-box',
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 600,
  color: 'var(--text-secondary)', whiteSpace: 'nowrap',
}
const plaque = {
  display: 'inline-flex', alignItems: 'center', gap: 8, height: 28, boxSizing: 'border-box', borderRadius: 9,
  fontSize: 12, whiteSpace: 'nowrap',
}
const warnPlaque = { ...plaque, padding: '0 4px 0 10px', background: 'var(--warning-tint)', border: '1px solid var(--warning-border)',
  fontWeight: 700, color: 'var(--warning-fg)' }
// NAVY (17.11.2026): устаревшие данные — оранжевый «действуй сейчас», кнопка залита
const signalPlaque = { ...plaque, padding: '0 4px 0 10px', background: 'var(--signal-tint)', border: '1px solid var(--signal-border)',
  fontWeight: 700, color: 'var(--signal-text)' }
const innerBtn = { ...plain, display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', borderRadius: 6,
  background: 'var(--bg-card)', border: '1px solid var(--warning-border)', fontSize: 11.5, fontWeight: 700, color: 'var(--text-primary)' }
const dm = (v) => dmShared(v, '')

/** Сбой съёма Weborama — то же условие, что у прежней полосы `VerifierStrip`. */
export const verifierBroken = (v) => !!v && (!v.configured || !!v.cursor?.last_error || !v.mapped_insertions)

function Freshness({ asOf, stale, isAdmin, syncing, syncSaid, onSync }) {
  if (!asOf) return null
  const btn = isAdmin ? (
    <button type="button" disabled={syncing} onClick={onSync} style={stale ? { ...innerBtn, background: 'var(--signal)', borderColor: 'var(--signal)', color: 'var(--signal-fg)' } : innerBtn}
      title="Пересобрать РК, площадки и креативы из сделок. Это же делает крон в 06:00; кнопка — для разбора, когда ждать до утра нельзя">
      {syncing ? 'Обновляю…' : 'Обновить из сделок'}</button>
  ) : null
  return (
    <>
      {stale ? (
        <span style={signalPlaque} title="Статистика DSP не обновлялась больше суток — проверьте ночной съём">
          <span className="tp-beacon" style={{ width: 7, height: 7, borderRadius: 4, background: 'var(--signal)' }} />
          данные на {dm(asOf)} — устарели{btn}
        </span>
      ) : (
        <span style={{ ...plaque, padding: isAdmin ? '0 4px 0 10px' : '0 10px', color: 'var(--text-muted)', border: '1px solid var(--border-card)', background: 'var(--bg-card)' }}>
          данные на {dm(asOf)}{btn}
        </span>
      )}
      {!!syncSaid && <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{syncSaid}</span>}
    </>
  )
}

function WhoPicker({ value, data, onPick }) {
  const [open, setOpen] = useState(false)
  const opts = [['mine', 'Мои'], ['all', 'Все трафики'], ['none', 'Не распределено'],
    ...(data?.reps || []).filter(r => r.user_id !== data?.my_user_id).map(r => [String(r.user_id), `${r.is_master ? '★ ' : ''}${r.name}`])]
  const label = (opts.find(o => o[0] === value) || opts[0])[1]
  return (
    <span data-pop-root style={{ position: 'relative' }}>
      <button type="button" className="tp-head" onClick={() => setOpen(o => !o)} style={headBtn}>
        {label}<span style={{ fontSize: 8, color: 'var(--text-faint)' }}>▾</span></button>
      <PortalPopover open={open} align="right" minWidth={200} maxHeight={420} offset={6}
        style={{ padding: 5, borderRadius: 12, boxShadow: 'var(--shadow-float)' }}>
        {opts.map(([k, l]) => (
          <button key={k} type="button" onClick={() => { setOpen(false); onPick(k) }}
            style={{ ...plain, display: 'flex', alignItems: 'center', width: '100%', height: 30, padding: '0 9px', borderRadius: 8, fontSize: 12.5,
              textAlign: 'left', fontWeight: k === value ? 700 : 500, color: k === value ? 'var(--accent-fg)' : 'var(--text-primary)',
              background: k === value ? 'var(--accent-tint)' : 'transparent' }}>{l}</button>
        ))}
      </PortalPopover>
    </span>
  )
}

/**
 * props: data — ответ /dashboard; scope + onScope; archive + onArchive; mayEdit; isAdmin; noFact, total — РК без факта;
 * verifier — состояние съёма Weborama (+ wbBusy, onWbRefresh); widgets + onWidgets; onAdfox; sync: {syncing, syncSaid, onSync}.
 */
export default function DashHeader({ data, scope, onScope, archive, onArchive, mayEdit, isAdmin, noFact, total, verifier, wbBusy,
  onWbRefresh, widgets, onWidgets, onAdfox, sync }) {
  const broken = verifierBroken(verifier)
  return (
    <div style={{ position: 'relative', zIndex: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--text-primary)' }}>Дашборд трафика</h1>
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>открутка рекламных кампаний</span>
      </span>
      <Freshness asOf={data?.as_of} stale={!!data?.as_of_stale} isAdmin={isAdmin} {...sync} />
      {noFact > 0 && (
        <span title={`По ${noFact} из ${total} РК факта нет — коннектор статистики ещё не подключён. У этих РК факт, процент, прогноз и недокрут показаны прочерком, а не нулём`}
          style={{ ...plaque, gap: 7, padding: '0 10px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', fontWeight: 600,
            color: 'var(--text-secondary)', cursor: 'help' }}>
          <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{noFact}</span>РК без факта — нет коннектора
        </span>
      )}
      {broken && (
        <span style={warnPlaque} title={verifier.verdict || ''}>
          <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--warning)' }} />
          сверка с Weborama не работает
          {mayEdit && verifier.configured && (
            <button type="button" disabled={wbBusy} onClick={onWbRefresh} style={innerBtn}>{wbBusy ? 'Забираю…' : 'Обновить'}</button>
          )}
        </span>
      )}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <WhoPicker value={scope || data?.scope || 'mine'} data={data} onPick={onScope} />
        <button type="button" className="tp-head" onClick={onArchive} style={archive ? { ...headBtn, background: 'var(--accent-tint)',
          borderColor: 'var(--accent-border)', color: 'var(--accent-fg)' } : headBtn}
          title={archive ? 'Показаны архивные РК — скрыть' : 'РК сделок на «Итоговой сверке» и дальше, а также «не случилась» и «сорвалась» скрыты — показать'}>
          {archive ? 'Скрыть архив' : 'Архив'}
          {!archive && !!data?.archived && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{data.archived}</span>}
        </button>
        {mayEdit && (
          <button type="button" className="tp-head" onClick={onAdfox} style={headBtn}
            title="Импорт ADFOX: загрузить суточный отчёт Adfox — показы площадок вне нашей DSP лягут в факт РК">↑ ADFOX</button>
        )}
        <button type="button" className="tp-head" onClick={onWidgets} title={widgets ? 'Свернуть виджеты в строку-итог' : 'Развернуть виджеты'}
          style={widgets ? { ...headBtn, color: 'var(--accent-fg)', background: 'var(--accent-tint)', borderColor: 'var(--accent-border)' } : headBtn}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
            <rect x="2" y="2.5" width="12" height="5" rx="1.5" /><path d="M2.5 11h11M2.5 13.5h7" /></svg>
          Виджеты
        </button>
      </span>
    </div>
  )
}

/** Панель списка: заголовок · поиск · счётчик · справа переключатель фильтра; пункты с нулём скрыты (кроме выбранного и «Все»). */
export function ListPanel({ q, onQ, shown, total, tabs, tab, onTab }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '4px 0 0' }}>
      <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: '-0.01em' }}>Рекламные кампании</span>
      <input value={q} onChange={e => onQ(e.target.value)} placeholder="Номер, название, бренд, услуга" aria-label="Поиск РК" className="tp-search"
        style={{ width: 260, height: 32, boxSizing: 'border-box', padding: '0 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
          borderRadius: 10, fontSize: 12.5, outline: 'none', fontFamily: 'inherit', color: 'var(--text-primary)' }} />
      <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{shown} из {total}</span>
      <span style={{ marginLeft: 'auto' }}>
        <Segmented tone="hot" size="sm" value={tab} onChange={onTab} options={tabs.filter(([k, , n]) => k === 'all' || k === tab || n > 0).map(([k, label, n]) => [k, label, n])}
          titleOf={k => (tabs.find(x => x[0] === k) || [])[3]} />
      </span>
    </div>
  )
}
