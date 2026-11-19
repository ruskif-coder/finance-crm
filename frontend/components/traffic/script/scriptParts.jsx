/**
 * Части вкладки «Скрипт» админки трафика в NAVY (хендофф docs/design_handoff_traffic_admin_script_navy.zip, 19.11.2026) —
 * перенесены из макета буквально: геометрия, токены, тексты. Состояние и сохранение — в `../SiteScript.jsx`.
 *
 * Отличия от макета — только проводка: поля только для чтения без права «правка», кнопка «Сохранить» у изменённого блока
 * (в макете сохранения нет вовсе), превью иконки — заглушка «80» (CSP не пускает картинку с CDN DSP), плитки площадок — ссылки на карточку и показываются все (в макете «+ ещё 8»),
 * плашка демокампании — по живому состоянию (`useTargetingCampaign`): запущена / спит / не проверена.
 *
 * Компоненты — на уровне модуля: объявленные внутри другого компонента теряли бы фокус поля после каждого символа.
 */
import { useState } from 'react'
import { MONO, primaryBtn } from '@/components/salesTableKit'

export const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18,
  padding: '14px 16px', display: 'flex', flexDirection: 'column' }
const CAP = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const H = { fontSize: 15, fontWeight: 800, letterSpacing: '-0.01em' }
const FIELD = { flex: '1 1 auto', minWidth: 0, height: 32, boxSizing: 'border-box', padding: '0 10px', borderRadius: 9,
  border: '1px solid var(--border-card)', background: 'var(--bg-subtle)', color: 'var(--text-primary)', fontFamily: MONO,
  fontSize: 12, outline: 'none' }
const SAVE = { ...primaryBtn, height: 28, padding: '0 12px', fontSize: 12 }

const okChip = { background: 'var(--ok-tint)', border: '1px solid var(--ok-border)', color: 'var(--ok-fg)' }
const attnChip = { background: 'var(--attn-tint)', border: '1px solid var(--attn-border)', color: 'var(--attn-fg)' }

/** Шапка карточки: заголовок, справа — подпись капсом либо «Сохранить», когда в карточке есть несохранённое. */
export function CardHead({ title, cap, dirty, saving, onSave, disabled }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
      <span style={H}>{title}</span>
      {dirty
        ? <button type="button" onClick={onSave} disabled={saving || disabled} style={{ ...SAVE, marginLeft: 'auto', alignSelf: 'center' }}>
            {saving ? 'Сохраняю…' : 'Сохранить'}</button>
        : <span style={{ ...CAP, marginLeft: 'auto' }}>{cap}</span>}
    </div>
  )
}

/** Поле с крестиком очистки внутри (вместо кнопки «Очистить»): крестик — только у непустого и при праве правки. */
export function ClearInput({ value, onChange, placeholder, readOnly, style, title }) {
  return (
    <span style={{ position: 'relative', flex: '1 1 auto', display: 'flex', minWidth: 0 }}>
      <input value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} readOnly={readOnly} title={title}
        style={{ ...FIELD, paddingRight: 30, ...style }} />
      {!readOnly && !!value && (
        <span role="button" tabIndex={0} onClick={() => onChange('')} onKeyDown={e => e.key === 'Enter' && onChange('')} title="очистить"
          className="tsc-x" style={{ display: 'inline-flex', position: 'absolute', right: 6, top: 6, width: 20, height: 20, alignItems: 'center',
            justifyContent: 'center', borderRadius: 6, color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer' }}>✕</span>
      )}
    </span>
  )
}

/** 1. Плашка автоматики: тумблер, статус, одна строка, полный текст правил — по «подробнее». */
export function AutoBar({ on, busy, mayEdit, onToggle, tone }) {
  const [more, setMore] = useState(false)
  const can = mayEdit && !busy
  return (
    <>
      <div data-tone={tone} style={{ ...CARD, flexDirection: 'row', padding: '14px 18px', alignItems: 'center', gap: 14 }}>
        <span role="switch" aria-checked={on} tabIndex={can ? 0 : -1} title={mayEdit ? 'включить / выключить' : 'нет права правки'}
          onClick={() => can && onToggle(!on)} onKeyDown={e => can && (e.key === 'Enter' || e.key === ' ') && onToggle(!on)}
          style={{ flex: '0 0 36px', width: 36, height: 20, borderRadius: 10, background: on ? 'var(--hot)' : 'var(--border-hover)', position: 'relative',
            cursor: can ? 'pointer' : 'default', opacity: busy ? 0.6 : 1, transition: 'background var(--dur-fast)' }}>
          <span style={{ position: 'absolute', top: 2, left: on ? 18 : 2, width: 16, height: 16, borderRadius: '50%',
            background: on ? 'var(--hot-fg)' : 'var(--text-primary)', boxShadow: '0 1px 2px rgba(16,24,32,.25)', transition: 'left var(--dur-fast)' }} />
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13.5, fontWeight: 700 }}>Пиксель Weborama и выгрузка в DSP — сами</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 7px', borderRadius: 5, fontFamily: MONO, fontSize: 9.5,
              fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
              ...(on ? okChip : { background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', color: 'var(--text-muted)' }) }}>
              {on ? 'включено' : 'выключено — только кнопками'}</span>
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
            Согласованный креатив с ЕРИД: сначала пиксель Weborama, затем выгрузка в DSP. Проверка каждые 5 минут.</span>
        </span>
        <span role="button" tabIndex={0} onClick={() => setMore(m => !m)} onKeyDown={e => e.key === 'Enter' && setMore(m => !m)}
          style={{ marginLeft: 'auto', flex: '0 0 auto', fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
          {more ? 'скрыть ▴' : 'подробнее ▾'}</span>
      </div>
      {more && (
        <div style={{ marginTop: -8, padding: '10px 16px 12px 66px', fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.55 }}>
          Площадка согласовала креатив и у комплекта есть ЕРИД — по её РК сначала заводится вставка Weborama и забирается пиксель, затем
          креатив уходит в DSP. Проверка раз в 5 минут и сразу после автовыпуска ЕРИД. Правила те же, что у кнопок «ПИКСЕЛЬ WR» и «В DSP»;
          кнопки остаются для ручного повтора. Не прошло — уведомление трафику.
        </div>
      )}
    </>
  )
}

/** 2. Поле «что добавляется в креатив»: подпись, «задан / пусто», что вводить; под полем — последствие пустоты. */
export function ExtraField({ label, hint, value, onChange, placeholder, okWord, okNote, emptyNote, thumb, readOnly }) {
  const set = !!String(value || '').trim()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 12.5, fontWeight: 700 }}>{label}</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', height: 17, padding: '0 6px', borderRadius: 5, fontFamily: MONO, fontSize: 9,
          fontWeight: 700, textTransform: 'uppercase', ...(set ? okChip : attnChip) }}>{set ? okWord : 'пусто'}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>{hint}</span>
      </span>
      <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {thumb && (
          <span title="превью 80×80" style={{ flex: '0 0 32px', width: 32, height: 32, borderRadius: 8, border: '1px dashed var(--border-hover)',
            background: 'var(--bg-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
            fontFamily: MONO, fontSize: 8, color: 'var(--text-muted)' }}>
            {/* сама картинка — на CDN DSP, а CSP пускает картинки только со своего адреса (img-src 'self'): превью было бы битым */}
            80
          </span>
        )}
        <ClearInput value={value} onChange={onChange} placeholder={placeholder} readOnly={readOnly} />
      </span>
      <span style={{ fontSize: 11, color: set ? 'var(--text-muted)' : 'var(--attn-fg)' }}>{set ? okNote : emptyNote}</span>
    </div>
  )
}

/** 3. Строка «Кабинеты и аккаунты»: ⓘ с длинным пояснением, поле ID, короткая подпись. */
export function IdRow({ label, value, onChange, placeholder, short, hint, warn, readOnly, inputMode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '200px 190px minmax(0,1fr)', gap: 10, alignItems: 'center', padding: '2px 0' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 600 }}>
        <span title={hint} style={{ display: 'inline-flex', width: 15, height: 15, flex: '0 0 15px', alignItems: 'center', justifyContent: 'center',
          borderRadius: '50%', border: '1px solid var(--border-hover)', fontFamily: MONO, fontSize: 9, color: 'var(--text-muted)', cursor: 'help' }}>i</span>
        {label}
      </span>
      <input value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} readOnly={readOnly} inputMode={inputMode}
        style={{ ...FIELD, flex: 'none', width: 190, ...(warn ? { borderColor: 'var(--attn-border)', background: 'var(--attn-tint)' } : null) }} />
      <span title={hint} style={{ fontSize: 11, color: warn ? 'var(--attn-fg)' : 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis',
        whiteSpace: 'nowrap' }}>{short}</span>
    </div>
  )
}

/* Человеческая причина вместо сырого ответа DSP. Сырое — по «ответ DSP ▾». */
function humanReason(raw) {
  const s = String(raw || '')
  if (/TokenExpired|Token expired/i.test(s)) return 'DSP не ответил: истёк токен доступа (code 102, TokenExpired). Обновите токен — статус кампании подтянется сам.'
  if (/не ответил|timeout|timed out/i.test(s)) return 'DSP не ответил — статус кампании подтянется при следующем открытии.'
  return s ? 'DSP не ответил про кампанию.' : ''
}
const STATUS_RU = { LAUNCHED: 'запущена', STOPPED: 'остановлена', DELETED: 'удалена', ARCHIVE: 'в архиве' }

/** Проверка демокампании — одной плашкой (в оригинале было две одинаковые красные строки). */
export function CampaignPlaque({ state, hash }) {
  const [open, setOpen] = useState(false)
  if (!state) return <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>читаю состояние демокампании…</span>
  const raw = state.error || (!state.running && !state.asleep ? state.reason : '') || ''
  const tone = state.running ? 'ok' : state.asleep ? 'attn' : 'bad'
  const title = state.running ? 'Демокампания запущена' : state.asleep ? 'Демокампания спит — кнопка нацеливания сама её запустит'
    : state.status ? `Демокампания ${STATUS_RU[state.status] || state.status}` : 'Демокампания не проверена'
  const fmt = (iso) => (iso ? String(iso).slice(0, 10).split('-').reverse().join('.') : '—')
  const note = state.running ? 'Копия баннера уедет сюда, и ссылка покажет его на сайте площадки.'
    : state.asleep ? '' : humanReason(raw) || state.reason || ''
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px', borderRadius: 12,
      background: `var(--${tone}-tint)`, border: `1px solid var(--${tone}-border)` }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: `var(--${tone})` }} />
        <span style={{ fontSize: 12.5, fontWeight: 700 }}>{title}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>
          {state.campaign_xxhash || hash || '—'} · {state.title || 'кампания без имени'} · срок {state.date_start ? `${fmt(state.date_start)} — ${fmt(state.date_end)}` : '—'}</span>
        {!!raw && (
          <span role="button" tabIndex={0} onClick={() => setOpen(o => !o)} onKeyDown={e => e.key === 'Enter' && setOpen(o => !o)}
            style={{ marginLeft: 'auto', fontSize: 11.5, color: `var(--${tone}-fg)`, cursor: 'pointer', whiteSpace: 'nowrap' }}>
            {open ? 'скрыть ответ ▴' : 'ответ DSP ▾'}</span>
        )}
      </span>
      {!!note && <span style={{ fontSize: 12, color: tone === 'ok' ? 'var(--text-secondary)' : `var(--${tone}-fg)` }}>{note}</span>}
      {open && !!raw && (
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-secondary)', lineHeight: 1.6, wordBreak: 'break-all' }}>{raw}</span>
      )}
    </div>
  )
}

/** Плитка площадки `код · название`; домен — только если отличается от названия, полный — в подсказке. */
function SiteTile({ p }) {
  const dom = p.domain || ''
  const showDom = !!dom && dom.toLowerCase() !== String(p.name || '').toLowerCase()
  return (
    <a href={`/publishers/${p.id}`} title={dom || p.name} className="tsc-tile"
      style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 28, padding: '0 9px', borderRadius: 8, background: 'var(--bg-subtle)',
        border: '1px solid var(--border-inner)', whiteSpace: 'nowrap', color: 'var(--text-primary)', textDecoration: 'none' }}>
      <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, color: p.code ? 'var(--text-muted)' : 'var(--bad-fg)' }}>{p.code || '—'}</span>
      <span style={{ fontSize: 12, fontWeight: 600 }}>{p.name}</span>
      {showDom && <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{dom}</span>}
    </a>
  )
}

/** 4. Группа «скрипт по площадкам»: скрипт в креатив и площадки плитками. */
export function ScriptGroup({ title, dot, sub, script, onScript, items, suggested, readOnly, dirty, saving, onSave }) {
  const empty = !String(script || '').trim()
  return (
    <div style={{ ...CARD, gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: dot }} />
        <span style={H}>{title}</span>
        <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>{items.length}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-muted)' }}>{sub}</span>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ ...CAP, flex: '0 0 auto' }}>скрипт в креатив</span>
        <ClearInput value={script} onChange={onScript} readOnly={readOnly} placeholder={'<script src="…"></script>'}
          style={empty ? { borderColor: 'var(--attn-border)', background: 'var(--attn-tint)' } : null} />
        {!readOnly && empty && (
          <button type="button" onClick={() => onScript(suggested)} className="tsc-act"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 11px', boxSizing: 'border-box', background: 'var(--bg-card)',
              border: '1px solid var(--border-card)', borderRadius: 9, fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap',
              cursor: 'pointer', fontFamily: 'inherit' }}>Подставить qq.js</button>
        )}
        {!readOnly && dirty && (
          <button type="button" onClick={onSave} disabled={saving} style={SAVE}>{saving ? 'Сохраняю…' : 'Сохранить'}</button>
        )}
      </div>
      {empty && <span style={{ fontSize: 11.5, color: 'var(--attn-fg)' }}>Скрипт не задан — креативы этих площадок уйдут без счётчика.</span>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, paddingTop: 6, borderTop: '1px solid var(--border-inner)' }}>
        {items.map(p => <SiteTile key={p.id} p={p} />)}
        {!items.length && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Площадок нет.</span>}
      </div>
    </div>
  )
}

/** Наведение на крестик, плитку и кнопку — классами: инлайн-стиль hover не умеет. */
export const SCRIPT_CSS = `.tsc-x:hover{background:var(--bg-card);color:var(--text-primary)}
.tsc-tile:hover{border-color:var(--border-hover)}
.tsc-act:hover{border-color:var(--border-hover)}`
