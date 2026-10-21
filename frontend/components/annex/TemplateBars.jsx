/**
 * Полосы окна «Шаблоны ДС»: шапка, строка версии, уведомление «базовый изменился», ответвление, форматы, замечания, подвал.
 * Только показ: данные и действия — в `BaseTemplateModal.jsx` (спринт 2, 14.10.2026).
 */
import { useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { plural } from '@/lib/annexTemplate.mjs'
import { fmtDate } from '@/lib/dates'

const svg = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.9, strokeLinecap: 'round', strokeLinejoin: 'round' }
const roundBtn = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, cursor: 'pointer' }
export const ghost = { display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 14px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }
const small = { display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 11px', border: '1px solid var(--border-card)', borderRadius: 9, background: 'var(--bg-card)', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap', cursor: 'pointer' }
export const stripBox = { display: 'flex', alignItems: 'center', gap: 12, overflow: 'hidden', flex: '0 0 auto', padding: '9px 20px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)', fontSize: 11.5, color: 'var(--text-secondary)' }
const capTxt = { fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-cap)', whiteSpace: 'nowrap' }

export function Head({ title, chip, canBack, edit, dirty, canHist, histOn, canEdit, onBack, onHist, onEdit, onClose }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 20px 12px', borderBottom: '1px solid var(--border-inner)' }}>
      {canBack && <span onClick={onBack} title="К списку шаблонов" style={{ ...roundBtn, width: 30, height: 30, borderRadius: 9, border: '1px solid var(--border-card)', color: 'var(--text-secondary)' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" style={svg}><path d="M15 6l-6 6 6 6" /></svg>
      </span>}
      <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>{title}</span>
      {chip && <span style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 10px', borderRadius: 7, background: 'var(--violet-tint)', border: '1px solid var(--violet-border)', color: 'var(--violet-fg)', fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' }}>{chip}</span>}
      {edit && <span style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', borderRadius: 7, background: 'var(--accent-tint)', color: 'var(--accent-fg)', fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>режим правки</span>}
      {dirty && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 9.5, color: 'var(--warning-fg)', whiteSpace: 'nowrap' }}>
        <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--warning)' }} />есть несохранённые правки
      </span>}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        {canHist && <span onClick={onHist} title="История версий"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 11px', border: `1px solid ${histOn ? 'var(--accent-border)' : 'var(--border-card)'}`, background: histOn ? 'var(--accent-tint)' : 'var(--bg-card)', borderRadius: 10, color: histOn ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" style={svg}><circle cx="12" cy="12" r="8" /><path d="M12 8v4.5l3 1.8" /></svg>
          История
        </span>}
        {canEdit && <span onClick={onEdit} title="Править шаблон" style={{ ...roundBtn, border: '1px solid var(--border-card)', color: 'var(--text-secondary)' }}>
          <svg width="15" height="15" viewBox="0 0 24 24" style={svg}><path d="M4 20h4l10-10-4-4L4 16v4z" /><path d="M14.5 5.5l4 4" /></svg>
        </span>}
        <span onClick={onClose} title="Закрыть" style={{ ...roundBtn, color: 'var(--text-faint)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" style={{ ...svg, strokeWidth: 2 }}><path d="M6 6l12 12M18 6L6 18" /></svg>
        </span>
      </span>
    </div>
  )
}

function EmptyToggle({ on, onClick }) {
  return (
    <span onClick={onClick} title="Проверить, как шаблон ведёт себя на сделке с незаполненными полями"
          style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 11.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
      <span style={{ position: 'relative', display: 'inline-block', width: 28, height: 16, borderRadius: 8, background: on ? 'var(--danger-border)' : 'var(--border-card)' }}>
        <span style={{ position: 'absolute', top: 2, left: on ? 14 : 2, width: 12, height: 12, borderRadius: 4, background: on ? 'var(--danger)' : 'var(--text-disabled)', transition: 'left 150ms ease' }} />
      </span>
      образец с пустыми полями
    </span>
  )
}

export function Strip({ detail, dirty, custom, emptyDemo, onEmpty }) {
  return (
    <div style={stripBox}>
      <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>v{dirty ? `${detail.version + 1} · черновик` : detail.version}</span>
      <span style={{ whiteSpace: 'nowrap' }}>{detail.author || '—'} · {fmtDate(detail.updated_at)}</span>
      {custom && <><span style={{ width: 1, height: 14, background: 'var(--border-card)' }} />
        <span style={capTxt}>кастомный · ответвлён от «{detail.title}» v{detail.base_version}</span></>}
      <EmptyToggle on={emptyDemo} onClick={onEmpty} />
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}><span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--accent)' }} />аккаунт</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}><span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--violet-fg)' }} />юрист</span>
    </div>
  )
}

function ChangeList({ changes }) {
  const word = { '+': 'добавлен', '−': 'убран', '~': 'изменён', '↕': 'перемещён', '🔒': 'обязательность', '↳': 'уровень', '≡': '' }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingTop: 6 }}>
      {changes.map((c, i) => (
        <span key={i} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          <b style={{ color: 'var(--text-primary)' }}>{c[1]}</b> — {word[c[0]] || ''} {c[2]}
        </span>
      ))}
    </div>
  )
}

export function BaseChangedBar({ baseTitle, known, now, changes, mayEdit, onKeep, onAdopt }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ flex: '0 0 auto', padding: '10px 20px', background: 'var(--warning-bg)', borderBottom: '1px solid var(--warning-border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--warning)' }} />
        <span style={{ fontSize: 12.5, color: 'var(--warning-fg)', fontWeight: 600 }}>
          Базовый шаблон «{baseTitle}» изменился: v{known} → v{now}. Надо ли отредактировать текущий?
        </span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
          <span onClick={() => setOpen(!open)} style={small}>{open ? 'Скрыть изменения' : 'Что изменилось'}</span>
          {mayEdit && <span onClick={onKeep} title="Текст шаблона договора не меняется; появится версия с пометкой, что версия базы принята" style={small}>Оставить свой</span>}
          {mayEdit && <span onClick={onAdopt} title="Загрузить текущую базу в редактор; сохранение даст новую версию шаблона договора" style={{ ...small, borderColor: 'var(--accent-border)', color: 'var(--accent-fg)', background: 'var(--accent-tint)' }}>Перенять базу</span>}
        </span>
      </div>
      {open && <ChangeList changes={changes} />}
    </div>
  )
}

export function Fork({ baseTitle, format, mayCreate, onFork }) {
  return (
    <div style={{ ...stripBox, gap: 14 }}>
      <span style={capTxt}>базовый шаблон «{baseTitle}» · формат договора: {format}</span>
      <span style={{ fontSize: 11.5 }}>Договор собирается по базе. Своя редакция — отдельно, со своими версиями.</span>
      {mayCreate && <span onClick={onFork} style={{ ...small, marginLeft: 'auto', borderColor: 'var(--violet-border)', color: 'var(--violet-fg)', background: 'var(--violet-tint)' }}>Сделать кастомный шаблон под договор</span>}
    </div>
  )
}

/** Какие форматы сотрудничества обслуживает базовый шаблон; формат другого шаблона по нажатию переходит к этому. */
export function FormatsBar({ detail, known, fmtMap, bases, mayEdit, onToggle }) {
  const titleOf = (id) => (bases.find(b => b.id === id) || {}).title
  return (
    <div style={{ ...stripBox, flexWrap: 'wrap', gap: 8, overflow: 'visible' }}>
      <span style={capTxt}>обслуживает форматы договора</span>
      {known.map(f => {
        const owner = fmtMap[f]
        const mine = owner === detail.id
        const other = owner != null && !mine
        return (
          <span key={f} onClick={() => mayEdit && onToggle(f)}
                title={other ? `Сейчас за шаблоном «${titleOf(owner) || '?'}» — нажатие переключит формат на этот` : mine ? 'Нажмите, чтобы снять формат с шаблона' : 'Назначить формат этому шаблону'}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 24, padding: '0 9px', borderRadius: 7, border: `1px solid ${mine ? 'var(--accent-border)' : 'var(--border-card)'}`, background: mine ? 'var(--accent-tint)' : 'var(--bg-card)', color: mine ? 'var(--accent-fg)' : other ? 'var(--text-faint)' : 'var(--text-secondary)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', cursor: mayEdit ? 'pointer' : 'default' }}>
            {mine ? '✓ ' : ''}{f}{other ? ` · ${titleOf(owner) || '?'}` : ''}
          </span>
        )
      })}
    </div>
  )
}

export function Issues({ issues, serverMessage, onGo }) {
  return (
    <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', gap: 4, padding: '10px 20px', borderTop: '1px solid var(--danger-border)', background: 'var(--danger-bg)', maxHeight: 104, overflowY: 'auto' }}>
      <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--danger-fg)' }}>
        {serverMessage || `Проверка шаблона · ${issues.length} ${plural(issues.length)} — сохранение заблокировано`}
      </span>
      {issues.map((x, i) => (
        <span key={i} onClick={() => x.id && onGo(x.id)} style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 12, color: 'var(--text-secondary)', cursor: x.id ? 'pointer' : 'default' }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--danger)', flex: '0 0 6px' }} />
          <b style={{ color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{x.where}</b>{x.text}
        </span>
      ))}
    </div>
  )
}

export function Foot({ edit, ok, count, nextVer, busy, onCancel, onSave, onClose }) {
  const tone = ok ? ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)'] : ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger-fg)']
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 20px', borderTop: '1px solid var(--border-inner)' }}>
      {edit && (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 26, padding: '0 10px', borderRadius: 7, background: tone[0], border: `1px solid ${tone[1]}`, fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.04em', color: tone[2], whiteSpace: 'nowrap' }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: tone[2] }} />
          {ok ? 'проверка пройдена' : `${count} ${plural(count)} в шаблоне`}
        </span>
      )}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
        {edit ? (
          <>
            <span onClick={onCancel} style={ghost}>Отмена</span>
            <span onClick={ok && !busy ? onSave : undefined} title={ok ? `сохранить как v${nextVer}` : 'исправьте ошибки в шаблоне'}
                  style={{ display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 16px', background: ok ? 'var(--accent)' : 'var(--accent-soft)', borderRadius: 10, fontSize: 12.5, fontWeight: 700, color: 'var(--on-accent)', whiteSpace: 'nowrap', cursor: ok ? 'pointer' : 'not-allowed' }}>
              {busy ? 'Сохраняю…' : `Сохранить как v${nextVer}`}
            </span>
          </>
        ) : <span onClick={onClose} style={ghost}>Закрыть</span>}
      </span>
    </div>
  )
}

export function Reason({ text }) {
  return (
    <div style={{ flex: '1 1 auto', padding: '40px 32px', display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-start' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 10px', borderRadius: 7, background: 'var(--danger-tint)', color: 'var(--danger-fg)', fontSize: 12, fontWeight: 700 }}>шаблон не определён</span>
      <span style={{ fontSize: 13.5, color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: 600 }}>{text}</span>
    </div>
  )
}
