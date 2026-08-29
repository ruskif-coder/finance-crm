import { useState } from 'react'
import { MONO, UI, card, CAP, btnSm, ctaStyle } from '../salesTableKit'
import { overlayClose } from '@/lib/overlay'

// Диалоги очереди аккаунта: отложить · подтвердить бронь · сбор запуска.
// Вынесены из pages/accounts/dashboard.js: страница разрослась до тысячи строк, а эти
// три модалки — самостоятельные куски со своим состоянием. Объявлены на модульном
// уровне (внутри страницы они пересоздавались бы на каждый рендер, и поля теряли фокус).

const dm = (s) => (s ? s.slice(8, 10) + '.' + s.slice(5, 7) : '—')

const Overlay = ({ onClose, width, children }) => (
  <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.35)', zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <div onClick={e => e.stopPropagation()} style={{ ...card, padding: 22, width, fontFamily: UI }}>{children}</div>
  </div>
)

const dealCaption = (row) => [row.advertiser || row.title, row.brand].filter(Boolean).join(' · ')

// Диалог «отложить»: заметка и дата возврата. Компонент объявлен на модульном уровне —
// внутри тела страницы он пересоздавался бы на каждый рендер и поле теряло бы фокус.
export function SnoozeDialog({ row, onClose, onSave }) {
  const [note, setNote] = useState(row.note || '')
  const [until, setUntil] = useState(row.return_at || '')
  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.35)', zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ ...card, padding: 22, width: 420, fontFamily: UI }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4, color: 'var(--text-primary)' }}>Отложить сделку</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14 }}>
          {row.advertiser || row.title} · {row.code}
        </div>
        <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Заметка</label>
        <textarea value={note} onChange={e => setNote(e.target.value)} rows={3} placeholder="почему откладываем"
          style={{ width: '100%', boxSizing: 'border-box', marginTop: 5, marginBottom: 12, padding: '8px 11px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, fontFamily: UI, resize: 'vertical' }} />
        <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Вернуть к дате</label>
        <input type="date" value={until} onChange={e => setUntil(e.target.value)}
          style={{ width: '100%', boxSizing: 'border-box', marginTop: 5, padding: '8px 11px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, fontFamily: MONO }} />
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6, lineHeight: 1.4 }}>
          Без даты строка останется в очереди — заметка только пометит её скрепкой.
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <button onClick={onClose} style={btnSm(false)}>Отмена</button>
          <button onClick={() => onSave(row, note, until || null)} style={btnSm(true)}>Сохранить</button>
        </div>
      </div>
    </div>
  )
}


// Подтверждение брони — выбор пути, а не одно движение. Бронь либо подтверждается
// и уходит на сбор запуска, либо не подтверждается — и тогда это срыв сделки,
// терминальная стадия. Молча вести только вперёд нельзя: сорванные брони иначе
// остались бы висеть в очереди навсегда.
export function BookingConfirm({ row, onClose, onPick }) {
  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.35)', zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ ...card, padding: 22, width: 460, fontFamily: UI }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Бронь</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, marginBottom: 16 }}>
          {[row.advertiser || row.title, row.brand].filter(Boolean).join(' · ')} · {row.code} · {row.reason}
        </div>
        <button onClick={() => onPick({ __to: 'launch_prep' })}
          style={{ ...ctaStyle('launch_ready'), width: '100%', padding: '10px 12px', marginBottom: 8, textAlign: 'left' }}>
          Подтвердить бронь → сбор запуска
        </button>
        <button onClick={() => onPick({ __lost: true })}
          style={{ ...ctaStyle('mp_rework'), width: '100%', padding: '10px 12px', textAlign: 'left' }}>
          Бронь не подтверждена → срыв сделки
        </button>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.45 }}>
          Дальше откроется диалог движения: он спросит комментарий и запишет переход в историю стадий.
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
          <button onClick={onClose} style={btnSm(false)}>Отмена</button>
        </div>
      </div>
    </div>
  )
}

// Сбор запуска. Чек-лист сборки — отдельный модуль, его ещё нет, и здесь стоит
// честная заглушка вместо имитации: показываем состав будущих пунктов и оставляем
// ручной переход в размещение. Когда чек-лист появится, «В размещение» станет
// доступной только по его выполнению, а кнопка строки сменится на неё.
const PREP_CHECKLIST = [
  'Креативы получены от агентства',
  'Набор пропорций собран',
  'Список площадок подтверждён',
  'Креативы согласованы паблишерами',
  'Таргетинги и сроки переданы в трафик',
]

export function LaunchPrepDialog({ row, onClose, onToLaunch }) {
  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, background: 'rgba(28,36,51,.35)', zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ ...card, padding: 22, width: 520, fontFamily: UI }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Сбор запуска</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, marginBottom: 14 }}>
          {[row.advertiser || row.title, row.brand].filter(Boolean).join(' · ')} · {row.code}
          {row.period_from ? ` · старт ${dm(row.period_from)}` : ''}
        </div>

        <span style={CAP}>Чек-лист сборки</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
          {PREP_CHECKLIST.map(item => (
            <span key={item} style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5, color: 'var(--text-faint)' }}>
              <span style={{ width: 14, height: 14, borderRadius: 4, border: '1px solid var(--border-card)', background: 'var(--bg-subtle)', flex: '0 0 14px' }} />
              {item}
            </span>
          ))}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.45, marginBottom: 16 }}>
          Пункты пока не отмечаются: сбор запуска — отдельный модуль (согласование креативов
          в кабинетах паблишеров). До него переход в размещение делается вручную.
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={btnSm(false)}>Закрыть</button>
          <button onClick={onToLaunch} style={{ ...ctaStyle('launch_ready'), padding: '7px 14px' }}>В размещение</button>
        </div>
      </div>
    </div>
  )
}
