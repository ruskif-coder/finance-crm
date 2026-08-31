/**
 * Кабинеты паблишеров — настройка со стороны ядра.
 *
 * Экран собран по хендоффу `docs/настройка кабинетов.zip` и посажен на общий кит: своих
 * стилевых констант здесь нет, цвета только переменными.
 *
 * Порядок работы (владелец, 28.08.2026): пустой кабинет → площадки → доступы людям →
 * рабочие чаты. Карточка повторяет его слева направо тремя колонками 50/25/25.
 *
 * Пять правил, которые экран обязан держать, — из README хендоффа:
 *
 *  1. контактов у площадки несколько, учётка — у одного или у части. Контакт без учётки
 *     существует нормально: это человек для переписки, а не пользователь;
 *  2. уровень доступа есть ТОЛЬКО у контакта с учёткой — иначе экран обещает права
 *     тому, кто не может войти;
 *  3. кабинет без единой учётки нерабочий: площадка физически не увидит кабинет. Он
 *     попадает в показатель «Без учёток» и получает предупреждение в колонке площадок;
 *  4. служебный кабинет видит все площадки и связей НЕ ХРАНИТ — список в нём
 *     информационный, отвязка невозможна;
 *  5. CPM живёт на площадке, здесь только показывается.
 *
 * «Войти как площадка» из макета убрано решением владельца 30.08.2026: имперсонация
 * администратора во внешнем контуре не делается.
 *
 * Контакт принадлежит ПЛОЩАДКЕ, а форма в макете её не спрашивает — при нескольких
 * площадках в кабинете выбор добавлен, иначе человек не знал бы, кому заводит контакт.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import Head from 'next/head'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, card, CAP, btn, btnSm, inp, sel, chip, ROW_TONE, Modal, PickValue,
  KpiStrip, IconBtn } from '@/components/salesTableKit'
import ValuePopover from '@/components/ValuePopover'
import api, { auth } from '@/lib/api'

/* ── мелкие части, все на модульном уровне ──────────────────────────────────
   Компонент, объявленный внутри рендера родителя, пересоздаётся на каждый ввод, и
   фокус в поле формы слетает после каждого символа. Этот проект на этом уже спотыкался. */

const STATE_TONE = {
  'активен': ['var(--income-tint)', 'var(--income-fg)'],
  'черновик': ['var(--bg-subtle)', 'var(--text-muted)'],
  'приостановлен': ['var(--danger-tint)', 'var(--danger-fg)'],
}
const TONE_COLOR = {
  ok: 'var(--income)', warn: 'var(--warning)', bad: 'var(--danger)',
  info: 'var(--accent)',
}

const Chip = ({ text, tone }) => {
  const [bg, fg] = STATE_TONE[tone || text] || STATE_TONE['черновик']
  return <span style={chip(bg, fg, 'transparent')}>{text}</span>
}

// Маркер квадратный во всём макете — и у площадки, и в ленте.
const Dot = ({ color, size = 7 }) => (
  <span style={{ width: size, height: size, borderRadius: 2, background: color,
    flex: `0 0 ${size}px`, marginTop: 5 }} />
)

const ServiceChip = ({ name, surfaces }) => (
  <span style={{ ...chip('var(--accent-tint)', 'var(--accent)', 'transparent'),
    display: 'inline-flex', alignItems: 'center', gap: 5 }}>
    {name}
    <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.08em',
      textTransform: 'uppercase', opacity: .75 }}>
      {(surfaces || []).join(' · ')}
    </span>
  </span>
)

const Metric = ({ label, value, color }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingRight: 18,
    borderRight: '1px solid var(--border-card)', marginRight: 18 }}>
    <span style={{ ...CAP, marginBottom: 0 }}>{label}</span>
    <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700,
      color: value ? (color || 'var(--text-primary)') : 'var(--text-disabled)' }}>
      {value || '—'}
    </span>
  </div>
)

const LogRow = ({ row }) => (
  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '7px 0',
    borderTop: '1px solid var(--border-row)' }}>
    <Dot color={TONE_COLOR[row.tone] || 'var(--text-faint)'} />
    <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, gap: 2 }}>
      <span style={{ fontSize: 11.5, fontWeight: 600, textWrap: 'pretty' }}>
        {row.label}{row.subject ? ` · ${row.subject}` : ''}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>
        {row.actor} · {String(row.at || '').slice(8, 10)}.{String(row.at || '').slice(5, 7)}
        {' · '}{String(row.at || '').slice(11, 16)}
      </span>
    </span>
  </div>
)

const Avatar = ({ name }) => (
  <span style={{ width: 28, height: 28, borderRadius: 9, flex: '0 0 28px',
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    background: 'var(--accent-tint)', color: 'var(--accent)',
    fontSize: 10.5, fontWeight: 700 }}>
    {(name || '?').split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase()}
  </span>
)

/** Строка контактного лица. Уровень — переключаемый чип, но только при учётке. */
const ContactRow = ({ c, mayEdit, busy, onLevel, onPassword, onGrant, onDisable,
  onEdit, onEnable, onDelete }) => (
  <div style={{ display: 'grid', gap: 10, alignItems: 'center', padding: '9px 0',
    borderTop: '1px solid var(--border-row)',
    gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1.2fr) 70px 116px minmax(196px,1.15fr)' }}>
    <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
      <Avatar name={c.name} />
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name || '—'}</span>
          {/* Главное контактное лицо — тот же зелёный квадрат, что в карточке
              паблишера: это одна и та же пометка, а не вторая её версия. */}
          {c.is_primary && <span title="Главное контактное лицо"
            style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--income)',
              flex: '0 0 auto' }} />}
        </span>
        <span style={{ ...CAP, marginBottom: 0, fontSize: 9 }}>
          {c.role || c.publisher_name}
        </span>
      </span>
    </span>
    <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-secondary)',
      overflow: 'hidden', textOverflow: 'ellipsis' }} title={c.email}>{c.email || '—'}</span>
    <span>
      {c.has_account
        ? <Chip text={c.is_active ? 'есть' : 'выкл'} tone={c.is_active ? 'активен' : 'приостановлен'} />
        : <Chip text="нет" tone="черновик" />}
    </span>
    <span>
      {c.has_account
        ? (
          <button disabled={busy || !mayEdit} onClick={() => onLevel(c)}
            title="Переключить уровень: «все» — согласование, сверки, документы; «просмотр» — только чтение"
            style={{ ...chip(c.level === 'все' ? 'var(--accent-tint)' : 'var(--bg-subtle)',
              c.level === 'все' ? 'var(--accent)' : 'var(--text-muted)', 'transparent'),
              border: 0, cursor: mayEdit ? 'pointer' : 'default', fontFamily: UI }}>
            {c.level}
          </button>
        )
        : <span style={{ color: 'var(--text-disabled)', fontSize: 12 }}>—</span>}
    </span>
    <span style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
      {!mayEdit ? null : (
        <>
          <IconBtn title="Изменить данные" onClick={() => !busy && onEdit(c)}>✎</IconBtn>
          {c.has_account ? (
            <>
              {c.is_active ? (
                <button style={{ ...btnSm(true), whiteSpace: 'nowrap' }} disabled={busy}
                  onClick={() => onPassword(c)}>Выдать пароль</button>
              ) : (
                <button style={{ ...btnSm(false), whiteSpace: 'nowrap' }} disabled={busy}
                  title="Вернуть доступ этому человеку"
                  onClick={() => onEnable(c)}>Включить</button>
              )}
              <IconBtn title={c.is_active
                ? 'Отключить учётку — контакт останется'
                : 'Учётка уже отключена'}
                onClick={() => !busy && c.is_active && onDisable(c)}>×</IconBtn>
            </>
          ) : (
            <>
            <button style={{ ...btnSm(true), whiteSpace: 'nowrap' }}
              disabled={busy || !c.email}
              title={c.email ? 'Создать доступ этому контакту'
                : 'У контакта нет почты — по ней он входит'}
              onClick={() => onGrant(c)}>Создать учётку</button>
            {/* Удаление есть только у контакта БЕЗ учётки: у контакта с учёткой тот же
                крест означает «отключить доступ», а сам человек остаётся. Ядро откажет,
                если удалить контакт с учёткой, — здесь просто не показываем такой путь. */}
            {!!c.contact_id && (
              <IconBtn title="Удалить контакт"
                onClick={() => !busy && onDelete(c)}>🗑</IconBtn>
            )}
            </>
          )}
        </>
      )}
    </span>
  </div>
)

/** Правка строки: контакт площадки или учётка служебного кабинета.
 *
 * Разница не косметическая. У контакта правятся ЕГО поля в реестре площадок — те же,
 * что в карточке паблишера, потому что это одна запись. У служебной учётки контакта
 * нет вовсе (`contact_id` пуст), и правятся поля самой учётки.
 *
 * Почта контакта и почта входа — РАЗНЫЕ значения: учётка копирует адрес при заведении,
 * дальше они живут отдельно. Форма не сводит их молча, а показывает расхождение и
 * предлагает обновить вход отдельным действием: смена логина втихую при правке визитки
 * — сюрприз, который обнаруживается на входе.
 */
function ContactEdit({ c, busy, onCancel, onSave, onSyncLogin, onPickPosition }) {
  const [v, setV] = useState({
    name: c.name || '', email: c.email || '', role: c.role || '',
    telegram: c.telegram || '', is_primary: !!c.is_primary,
  })
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  const isContact = !!c.contact_id
  const loginDiffers = c.has_account && isContact
    && (v.email || '').trim().toLowerCase() !== (c.login_email || c.email || '').toLowerCase()
  return (
    <div style={{ background: 'var(--bg-tint)', border: '1px solid var(--accent-border)',
      borderRadius: 12, padding: 12, margin: '4px 0 10px', display: 'flex',
      flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'grid', gap: 8,
        gridTemplateColumns: isContact ? '1.3fr 1.3fr 1fr 1fr' : '1.3fr 1.3fr' }}>
        <input style={inp} placeholder="ФИО" value={v.name}
          onChange={e => set('name', e.target.value)} />
        <input style={inp} placeholder={isContact ? 'Email' : 'Email — он же вход'}
          value={v.email} onChange={e => set('email', e.target.value)} />
        {isContact && (
          <PickValue value={v.role} placeholder="должность"
            onOpen={e => onPickPosition(e, v.role, x => set('role', x))} />
        )}
        {isContact && (
          <input style={inp} placeholder="Телеграм" value={v.telegram}
            onChange={e => set('telegram', e.target.value)} />
        )}
      </div>
      {isContact && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5,
          cursor: 'pointer' }}>
          <input type="checkbox" checked={v.is_primary}
            onChange={e => set('is_primary', e.target.checked)} />
          Главное контактное лицо площадки
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
            — у площадки он один, с остальных пометка снимется
          </span>
        </label>
      )}
      {loginDiffers && (
        <div style={{ fontSize: 11.5, lineHeight: 1.45, background: 'var(--warning-bg)',
          color: 'var(--warning-text)', border: '1px solid var(--warning-border)',
          borderRadius: 9, padding: '8px 10px', display: 'flex', alignItems: 'center',
          gap: 10 }}>
          <span style={{ flex: 1 }}>
            Почта входа останется прежней — <b>{c.login_email || c.email}</b>.
          </span>
          <button style={btnSm(false)} disabled={busy}
            onClick={() => onSyncLogin(c, v.email.trim())}>Сделать и входом</button>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button style={btn(false)} onClick={onCancel}>Отмена</button>
        <button style={btn(true)} disabled={busy || !v.name.trim()}
          onClick={() => onSave(c, v)}>Сохранить</button>
      </div>
    </div>
  )
}

/** Строка площадки кабинета: готовность, CPM, переход в карточку, отвязка. */
const SiteRow = ({ p, mayEdit, canDetach, busy, onDetach }) => (
  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 0',
    borderTop: '1px solid var(--border-row)' }}>
    <Dot color={p.problems.length ? 'var(--warning)' : 'var(--income)'} />
    <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
      <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden',
        textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
      <span style={{ ...CAP, marginBottom: 0, fontSize: 9,
        color: p.problems.length ? 'var(--warning-text)' : 'var(--text-faint)' }}>
        {p.problems.length ? p.problems.join(' · ') : 'готова к работе'}
      </span>
    </span>
    <span title="CPM по договору, до НДС"
      style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap',
        color: p.cpm ? 'var(--text-primary)' : 'var(--text-disabled)' }}>
      {p.cpm ? `${p.cpm} ₽` : '—'}
      <span style={{ ...CAP, marginBottom: 0, marginLeft: 4, fontSize: 8.5 }}>cpm</span>
    </span>
    {mayEdit && canDetach && (
      <IconBtn title="Убрать из кабинета" onClick={() => !busy && onDetach(p)}>×</IconBtn>
    )}
  </div>
)

/** Выбор свободных площадок. Занятые не показываются: площадка живёт в одном кабинете. */
function FreePublishers({ options, selected, onToggle }) {
  const [q, setQ] = useState('')
  const list = options.filter(p => !q
    || (p.name || '').toLowerCase().includes(q.toLowerCase())
    || (p.domain || '').toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
        <input style={{ ...inp, flex: 1 }} value={q} onChange={e => setQ(e.target.value)}
          placeholder="Поиск площадки" />
        <span style={{ ...CAP, marginBottom: 0 }}>выбрано {selected.length}</span>
      </div>
      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        {list.map(p => (
          <label key={p.id} style={{ display: 'flex', gap: 9, alignItems: 'center',
            padding: '7px 2px', borderTop: '1px solid var(--border-row)', cursor: 'pointer' }}>
            <input type="checkbox" checked={selected.includes(p.id)}
              onChange={() => onToggle(p.id)} />
            <span style={{ flex: 1, fontSize: 13 }}>{p.name}</span>
            {p.problems.length
              ? <span style={{ ...CAP, marginBottom: 0, color: 'var(--warning-text)' }}
                  title={p.problems.join('; ')}>⚠ {p.problems.length}</span>
              : <span style={{ ...CAP, marginBottom: 0 }}>готова</span>}
          </label>
        ))}
        {!list.length && (
          <div style={{ fontSize: 12.5, color: 'var(--text-faint)', padding: '10px 0' }}>
            Свободных площадок нет
          </div>
        )}
      </div>
    </>
  )
}

/** Форма нового контактного лица. Подпись кнопки зависит от чекбокса — так в макете. */
function NewContactForm({ publishers, service, busy, onCancel, onSubmit, onPickPosition }) {
  // У служебного кабинета человек заводится СРАЗУ учёткой: контактов площадок в нём нет,
  // поэтому ни должности из реестра, ни выбора площадки, ни чекбокса «создать учётку» —
  // без неё запись не имела бы смысла вовсе.
  const [v, setV] = useState({
    name: '', email: '', role: '', publisher_id: publishers[0]?.id || '',
    account: true, level: 'все',
  })
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  return (
    <div style={{ background: 'var(--bg-tint)', border: '1px solid var(--accent-border)',
      borderRadius: 12, padding: 12, marginTop: 10, display: 'flex',
      flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'grid', gap: 8,
        gridTemplateColumns: service ? '1.3fr 1.3fr' : '1.3fr 1.3fr 1fr' }}>
        <input style={inp} placeholder="ФИО" value={v.name}
          onChange={e => set('name', e.target.value)} />
        <input style={inp} placeholder={service ? 'Email — он же вход' : 'Email'}
          value={v.email} onChange={e => set('email', e.target.value)} />
        {!service && (
          <PickValue value={v.role} placeholder="должность"
            onOpen={e => onPickPosition(e, v.role, x => set('role', x))} />
        )}
      </div>
      {!service && publishers.length > 1 && (
        // Контакт принадлежит площадке. В макете этого поля нет — там кабинет с одной
        // площадкой; при нескольких без выбора человек не знал бы, кому заводит контакт.
        <select style={sel} value={v.publisher_id}
          onChange={e => set('publisher_id', Number(e.target.value))}>
          {publishers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      )}
      {!service && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5,
          cursor: 'pointer' }}>
          <input type="checkbox" checked={v.account}
            onChange={e => set('account', e.target.checked)} />
          Создать учётку в кабинете
        </label>
      )}
      {(service || v.account) && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {['все', 'просмотр'].map(l => (
            <button key={l} onClick={() => set('level', l)}
              style={{ ...btnSm(v.level === l) }}>{l}</button>
          ))}
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
            {v.level === 'все'
              ? 'согласование креативов, сверки, документы'
              : 'только чтение кампаний и денег, без решений'}
          </span>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button style={btn(false)} onClick={onCancel}>Отмена</button>
        <button style={btn(true)} disabled={busy || !v.name.trim() || !v.email.trim()}
          onClick={() => onSubmit(v)}>
          {service ? 'Завести доступ'
            : v.account ? 'Добавить и создать учётку' : 'Добавить контакт'}
        </button>
      </div>
    </div>
  )
}

/** Наши контакты у площадок — соседний виджет справа от показателей.
 *
 * Стоит В ШАПКЕ, а не строкой внизу: это не итог экрана, а его условие. Кабинет без
 * наших контактов работает, но площадке некуда обратиться, и увидеть это надо до того,
 * как разбираешься с конкретным кабинетом.
 */
const OurContactsCard = ({ items, mayEdit, onOpen }) => (
  <div style={{ ...card, padding: '16px 18px', height: '100%', display: 'flex',
    flexDirection: 'column', gap: 10 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ ...CAP, marginBottom: 0 }}>наши контакты у площадок</span>
      <span style={{ flex: 1 }} />
      {mayEdit && <button style={btnSm(false)} onClick={onOpen}>Настроить</button>}
    </div>
    {items.length ? (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(x => (
          <div key={x.id} style={{ display: 'flex', alignItems: 'center', gap: 9,
            opacity: x.is_shown ? 1 : .5 }}>
            <Avatar name={x.name} />
            <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.name}</span>
              <span style={{ ...CAP, marginBottom: 0, fontSize: 9 }}>{x.role}</span>
            </span>
            <span style={{ flex: 1 }} />
            {/* Отсутствие почты — не мелочь: площадка увидит имя без способа связаться,
                поэтому помечается прямо здесь, а не всплывает при сохранении. */}
            {x.email
              ? <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)',
                  overflow: 'hidden', textOverflow: 'ellipsis' }}
                  title={x.email}>{x.email}</span>
              : <span style={chip('var(--warning-bg)', 'var(--warning-text)', 'var(--warning-border)')}>
                  нет почты</span>}
            {!x.is_shown && <Chip text="скрыт" tone="черновик" />}
          </div>
        ))}
      </div>
    ) : (
      <span style={{ fontSize: 12.5, color: 'var(--text-faint)', lineHeight: 1.45 }}>
        Не выбраны — площадка не видит, к кому идти.
      </span>
    )}
  </div>
)

const ColHead = ({ title, count, note, action }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
    <span style={{ ...CAP, marginBottom: 0 }}>{title}</span>
    {count != null && (
      <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>
        {count}
      </span>
    )}
    {!!note && (
      <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{note}</span>
    )}
    <span style={{ flex: 1 }} />
    {action}
  </div>
)

/* ─────────────────────────────── страница ─────────────────────────────── */

export default function CabinetsPage() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [mayEdit, setMayEdit] = useState(false)

  const [q, setQ] = useState('')
  const [fState, setFState] = useState('')
  const [fService, setFService] = useState('')
  const [fNoAcc, setFNoAcc] = useState(false)

  const [folded, setFolded] = useState({})
  const [allSites, setAllSites] = useState({})
  const [adding, setAdding] = useState(null)      // id кабинета с открытой формой
  const [editing, setEditing] = useState(null)    // account_id | c<contact_id>
  const [newCab, setNewCab] = useState(null)
  const [attach, setAttach] = useState(null)
  const [shown, setShown] = useState(null)
  const [ourOpen, setOurOpen] = useState(false)
  const [fullLog, setFullLog] = useState(null)
  const [vpop, setVpop] = useState(null)

  useEffect(() => { setMayEdit(can('dir_publishers_cabinets', 'edit')) }, [])

  const load = useCallback(async () => {
    setErr('')
    try { setData((await api.get('/cabinets/', auth())).data) }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить кабинеты') }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (fn) => {
    setBusy(true); setErr('')
    try { await fn(); await load() }
    catch (e) { setErr(e.response?.data?.detail || 'Не удалось выполнить') }
    setBusy(false)
  }

  const issuePassword = async (cabinet, c) => {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/cabinets/accounts/${c.account_id}/password`, {}, auth())
      const pub = (cabinet.publishers || []).find(p => p.chat_url || p.chat_url_max)
      setShown({ email: c.email, password: r.data.password,
        chat: pub ? { url: pub.chat_url || pub.chat_url_max, name: pub.name } : null })
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось выдать пароль') }
    setBusy(false)
  }

  const rowKey = (c) => (c.contact_id ? `c${c.contact_id}` : `a${c.account_id}`)

  /** Сохранить строку. Контакт правится в реестре площадок, служебная учётка — у себя.
      Оба пути частичные: посылаем то, что показывали, а не всю запись целиком. */
  const saveRow = async (c, v) => {
    await run(async () => {
      if (c.contact_id) {
        await api.put(`/publishers/${c.publisher_id}/contacts/${c.contact_id}`, {
          name: v.name.trim(), email: v.email.trim() || null,
          role: v.role || null, telegram: v.telegram || null,
          is_primary: !!v.is_primary,
        }, auth())
      } else {
        await api.put(`/cabinets/accounts/${c.account_id}`,
          { name: v.name.trim(), email: v.email.trim() }, auth())
      }
      setEditing(null)
    })
  }

  const deleteContact = (c) => {
    // Контакт — общая запись с карточкой паблишера, поэтому спрашиваем: удаление здесь
    // убирает человека и оттуда.
    if (!window.confirm(
      `Удалить контакт «${c.name}»? Он исчезнет и из карточки площадки ${c.publisher_name}.`)) return
    return run(() => api.delete(
      `/publishers/${c.publisher_id}/contacts/${c.contact_id}`, auth()))
  }

  // Отдельным действием, а не побочным эффектом правки визитки: смена логина втихую
  // обнаруживается только на входе.
  const syncLogin = (c, email) => run(() =>
    api.put(`/cabinets/accounts/${c.account_id}`, { email }, auth()))

  const addContact = (cabinet) => async (v) => {
    await run(async () => {
      if (cabinet.kind === 'служебный') {
        // У служебного кабинета контактов площадок нет: человек заводится сразу
        // учёткой. Ядро откажет, если сюда прислать contact_id, и наоборот.
        await api.post(`/cabinets/${cabinet.id}/accounts`,
          { name: v.name.trim(), email: v.email.trim(),
            can_approve: v.level === 'все' }, auth())
      } else {
        const r = await api.post(`/publishers/${v.publisher_id}/contacts`,
          { name: v.name.trim(), email: v.email.trim(), role: v.role || null }, auth())
        if (v.account) {
          await api.post(`/cabinets/${cabinet.id}/accounts`,
            { contact_id: r.data.id, can_approve: v.level === 'все' }, auth())
        }
      }
      setAdding(null)
    })
  }

  const openFullLog = async (cabinet) => {
    setErr('')
    try {
      const r = await api.get(`/cabinets/${cabinet.id}/log`, auth())
      setFullLog({ cabinet, rows: r.data.rows || [] })
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось открыть журнал') }
  }

  const cabinets = data?.cabinets || []
  const kpi = data?.kpi

  const services = useMemo(() => {
    const set = new Set()
    cabinets.forEach(c => (c.services || []).forEach(s => set.add(s.name)))
    return [...set].sort()
  }, [cabinets])

  const shownCabinets = useMemo(() => cabinets.filter(c => {
    if (fState && c.state !== fState) return false
    if (fNoAcc && c.accounts.length) return false
    if (fService && !(c.services || []).some(s => s.name === fService)) return false
    if (!q.trim()) return true
    const hay = [c.name, ...(c.publishers || []).map(p => p.name),
      ...(c.contacts || []).flatMap(x => [x.name, x.email])].join(' ').toLowerCase()
    return hay.includes(q.trim().toLowerCase())
  }), [cabinets, q, fState, fService, fNoAcc])

  return (
    <>
      <Head><title>Кабинеты паблишеров</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: '22px 20px 60px', fontFamily: UI }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-.02em' }}>
            Кабинеты паблишеров
          </h1>
          <span style={{ ...CAP, marginBottom: 0 }}>
            {data ? `${cabinets.length} кабинета · ${kpi?.accounts ?? 0} учёток` : 'загрузка…'}
          </span>
          <span style={{ flex: 1 }} />
          <input style={{ ...inp, minWidth: 210 }} value={q} placeholder="Кабинет, площадка, контакт…"
            onChange={e => setQ(e.target.value)} />
          <select style={sel} value={fState} onChange={e => setFState(e.target.value)}>
            <option value="">Статус</option>
            {['активен', 'приостановлен', 'черновик'].map(x => <option key={x}>{x}</option>)}
          </select>
          <select style={sel} value={fService} onChange={e => setFService(e.target.value)}>
            <option value="">Услуга</option>
            {services.map(x => <option key={x}>{x}</option>)}
          </select>
          <button style={btnSm(fNoAcc)} onClick={() => setFNoAcc(v => !v)}
            title="Только кабинеты, в которые никто не может войти">Без учёток</button>
          {mayEdit && (
            <button style={btn(true)} onClick={() => setNewCab({ name: '', manager_id: '', note: '' })}>
              + Кабинет
            </button>
          )}
        </div>

        {!!kpi && (
          <div style={{ display: 'flex', gap: 14, marginBottom: 16,
            alignItems: 'stretch' }}>
            <div style={{ flex: '3 1 0', minWidth: 0 }}>
            <KpiStrip items={[
              { label: 'Кабинетов', value: kpi.cabinets, unit: 'шт.',
                hint: `${kpi.active} активных · ${kpi.draft} черновик` },
              { label: 'Учёток выдано', value: kpi.accounts, unit: 'шт.',
                color: 'var(--accent)', hint: 'у одного контакта — одна учётка' },
              { label: 'Креативов на согласовании', value: kpi.creatives_pending, unit: 'шт.',
                color: 'var(--danger)', hint: 'по всем кабинетам' },
              { label: 'Запущенных РК', value: kpi.campaigns_live, unit: 'РК',
                color: 'var(--income)', hint: 'сейчас в эфире' },
              { label: 'Без учёток', value: kpi.without_accounts, unit: 'кабинет',
                color: 'var(--warning)', hint: 'площадка не видит кабинет' },
            ]} />
            </div>
            <div style={{ flex: '1 1 0', minWidth: 0 }}>
              <OurContactsCard items={data?.our_contacts || []} mayEdit={mayEdit}
                onOpen={() => setOurOpen(true)} />
            </div>
          </div>
        )}

        {!!err && (
          <div style={{ ...card, padding: '10px 14px', marginBottom: 14,
            color: 'var(--danger)', borderColor: ROW_TONE.overdue.border,
            background: ROW_TONE.overdue.bg }}>{err}</div>
        )}

        {shownCabinets.map(c => {
          const service = c.kind === 'служебный'
          const sites = allSites[c.id] ? c.publishers : c.publishers.slice(0, 5)
          const contacts = service
            ? c.accounts.map(a => ({ contact_id: null, account_id: a.id, name: a.name,
              email: a.email, role: null, publisher_name: null, has_account: true,
              level: a.can_approve ? 'все' : 'просмотр', is_active: a.is_active }))
            : (c.contacts || [])
          return (
            <div key={c.id} style={{ ...card, padding: '18px 24px 16px', marginBottom: 14,
              borderColor: service ? 'var(--accent-border)'
                : c.state === 'черновик' ? 'var(--border-inner)' : 'var(--border-card)' }}>

              {/* ── шапка карточки ── */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <button onClick={() => setFolded(f => ({ ...f, [c.id]: !f[c.id] }))}
                  style={{ border: 0, background: 'transparent', cursor: 'pointer',
                    color: 'var(--text-faint)', fontSize: 13, padding: 0 }}>
                  {folded[c.id] ? '▸' : '▾'}
                </button>
                <span style={{ fontSize: 18, fontWeight: 700 }}>{c.name}</span>
                {service && <Chip text="служебный" tone="черновик" />}
                <Chip text={c.state} />
                <span style={{ ...CAP, marginBottom: 0 }}>
                  {service ? 'видит все площадки · связей не хранит'
                    : `кабинет площадки${c.manager ? ` · ведёт ${c.manager}` : ''}`}
                </span>
                <span style={{ flex: 1 }} />
                {mayEdit && (
                  <button style={btnSm(false)} disabled={busy}
                    title={c.state === 'активен'
                      ? 'Приостановить — люди кабинета сразу перестанут видеть задания'
                      : 'Активировать кабинет'}
                    onClick={() => run(() => api.put(`/cabinets/${c.id}`,
                      { state: c.state === 'активен' ? 'приостановлен' : 'активен' }, auth()))}>
                    {c.state === 'активен' ? 'Приостановить' : 'Активировать'}
                  </button>
                )}
              </div>

              {!folded[c.id] && (
                <>
                  {/* ── полоса активности ── */}
                  <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap',
                    gap: 10, background: 'var(--bg-tint)', borderRadius: 12,
                    padding: '12px 16px', margin: '14px 0 16px' }}>
                    <Metric label="Креативов на согласовании" value={c.activity.creatives_pending}
                      color="var(--danger)" />
                    <Metric label="Запущенных РК" value={c.activity.campaigns_live}
                      color="var(--income)" />
                    <Metric label="Сверок открыто" value={c.activity.recons_open}
                      color="var(--warning)" />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <span style={{ ...CAP, marginBottom: 0 }}>Последний вход</span>
                      <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700,
                        color: c.activity.last_login ? 'var(--text-primary)' : 'var(--text-disabled)' }}>
                        {c.activity.last_login
                          ? `${String(c.activity.last_login).slice(8, 10)}.${String(c.activity.last_login).slice(5, 7)}`
                          : '—'}
                      </span>
                    </div>
                    <span style={{ flex: 1 }} />
                    <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {(c.services || []).map(s => (
                        <ServiceChip key={s.name} name={s.name} surfaces={s.surfaces} />
                      ))}
                    </span>
                  </div>

                  {/* ── три колонки 50 / 25 / 25 ──
                      Задаются через flex-основу 0, а не calc(50% - 16px): с учётом gap
                      сумма процентов превышает 100 %, и колонки переносятся в столбец. */}
                  <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>

                    {/* контакты */}
                    <div style={{ flex: '2 1 0', minWidth: 0 }}>
                      <ColHead title="Контактные лица" count={contacts.length}
                        note={service ? 'учётки нашей стороны'
                          : `учёток ${contacts.filter(x => x.has_account).length}`}
                        action={mayEdit && (service || !!c.publishers.length) && (
                          <button style={btnSm(adding === c.id)}
                            onClick={() => setAdding(adding === c.id ? null : c.id)}>
                            {adding === c.id ? '× Закрыть'
                              : service ? '+ Наш человек' : '+ Контактное лицо'}
                          </button>
                        )} />
                      <div style={{ overflowX: 'auto' }}>
                        <div style={{ minWidth: 600 }}>
                          {contacts.map(x => (editing === rowKey(x) ? (
                            <ContactEdit key={rowKey(x)} c={x} busy={busy}
                              onCancel={() => setEditing(null)}
                              onSave={saveRow} onSyncLogin={syncLogin}
                              onPickPosition={(e, value, apply) => setVpop({
                                rect: e.currentTarget.getBoundingClientRect(),
                                title: 'Должность', value, clearLabel: '— не задана —',
                                options: (data?.positions || []).map(pp => ({ value: pp.name, label: pp.name })),
                                apply,
                                onAddNew: async (name) => {
                                  await api.post('/publishers/positions', { name }, auth())
                                  apply(name); setVpop(null); load()
                                },
                              })} />
                          ) : (
                            <ContactRow key={rowKey(x)} c={x}
                              onEdit={t => setEditing(rowKey(t))}
                              mayEdit={mayEdit} busy={busy}
                              onLevel={t => run(() => api.put(`/cabinets/accounts/${t.account_id}`,
                                { can_approve: t.level !== 'все' }, auth()))}
                              onDisable={t => run(() => api.put(`/cabinets/accounts/${t.account_id}`,
                                { is_active: false }, auth()))}
                              onPassword={t => issuePassword(c, t)}
                              onEnable={t => run(() => api.put(`/cabinets/accounts/${t.account_id}`,
                                { is_active: true }, auth()))}
                              onDelete={deleteContact}
                              onGrant={t => run(() => api.post(`/cabinets/${c.id}/accounts`,
                                { contact_id: t.contact_id, can_approve: true }, auth()))} />
                          )))}
                          {!contacts.length && (
                            <div style={{ fontSize: 12.5, color: 'var(--text-faint)',
                              padding: '12px 0' }}>
                              {c.publishers.length
                                ? 'У площадок кабинета нет контактных лиц'
                                : 'Сперва прикрепите площадку — контакты берутся у неё'}
                            </div>
                          )}
                        </div>
                      </div>
                      {adding === c.id && (
                        <NewContactForm publishers={service ? [] : c.publishers}
                          service={service} busy={busy}
                          onCancel={() => setAdding(null)}
                          onSubmit={addContact(c)}
                          onPickPosition={(e, value, apply) => setVpop({
                            rect: e.currentTarget.getBoundingClientRect(),
                            title: 'Должность', value, clearLabel: '— не задана —',
                            options: (data?.positions || []).map(p => ({ value: p.name, label: p.name })),
                            apply,
                            onAddNew: async (name) => {
                              await api.post('/publishers/positions', { name }, auth())
                              apply(name); setVpop(null); load()
                            },
                          })} />
                      )}
                    </div>

                    {/* площадки */}
                    <div style={{ flex: '1 1 0', minWidth: 0 }}>
                      <ColHead title="Площадки кабинета" count={`${c.publishers.length} шт.`}
                        action={mayEdit && !service && (
                          <button style={btnSm(false)} disabled={busy}
                            onClick={() => setAttach({ cabinet: c, ids: [] })}>+ Площадки</button>
                        )} />
                      <div style={{ maxHeight: 216, overflowY: 'auto' }}>
                        {sites.map(p => (
                          <SiteRow key={p.id} p={p} mayEdit={mayEdit} busy={busy}
                            canDetach={!service}
                            onDetach={t => run(() => api.delete(
                              `/cabinets/${c.id}/publishers/${t.id}`, auth()))} />
                        ))}
                        {!c.publishers.length && (
                          <div style={{ fontSize: 12.5, color: 'var(--text-faint)',
                            padding: '12px 0' }}>Площадок нет</div>
                        )}
                      </div>
                      {c.publishers.length > sites.length && (
                        <button style={{ ...btnSm(false), marginTop: 8 }}
                          onClick={() => setAllSites(s => ({ ...s, [c.id]: true }))}>
                          Показать все {c.publishers.length}
                        </button>
                      )}
                      {!c.accounts.length && (
                        <div style={{ marginTop: 10, fontSize: 11.5, lineHeight: 1.45,
                          background: 'var(--warning-bg)', color: 'var(--warning-text)',
                          border: '1px solid var(--warning-border)', borderRadius: 9,
                          padding: '8px 10px' }}>
                          Учёток нет — добавьте контактное лицо и создайте ему доступ,
                          иначе площадка не увидит кабинет.
                        </div>
                      )}
                    </div>

                    {/* лента */}
                    <div style={{ flex: '1 1 0', minWidth: 0 }}>
                      <ColHead title="Лог действий" count={`${c.log_total} за 30 дн.`}
                        action={(
                          <button style={btnSm(false)} onClick={() => openFullLog(c)}>
                            Весь лог
                          </button>
                        )} />
                      <div style={{ maxHeight: 216, overflowY: 'auto' }}>
                        {(c.log || []).map((r, i) => <LogRow key={i} row={r} />)}
                        {!c.log?.length && (
                          <div style={{ fontSize: 12.5, color: 'var(--text-faint)',
                            padding: '12px 0' }}>
                            Действий не было
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )
        })}

        {!!data && !shownCabinets.length && (
          <div style={{ ...card, padding: '20px 24px', color: 'var(--text-muted)' }}>
            Под фильтры не подошёл ни один кабинет.
          </div>
        )}

      </div>

      {/* ── модалки ── */}
      {newCab && (
        <Modal title="Новый кабинет" width={560} onClose={() => setNewCab(null)}
          footer={(
            <button style={btn(true)} disabled={busy || !newCab.name.trim()}
              onClick={() => run(async () => {
                await api.post('/cabinets/', { name: newCab.name.trim(),
                  manager_id: newCab.manager_id || null,
                  note: newCab.note || null }, auth())
                setNewCab(null)
              })}>Создать</button>
          )}
          summary="Кабинет заводится черновиком: площадки и людей добавляют следующими шагами.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input style={inp} placeholder="Название" value={newCab.name}
              onChange={e => setNewCab(v => ({ ...v, name: e.target.value }))} />
            <select style={sel} value={newCab.manager_id}
              onChange={e => setNewCab(v => ({ ...v, manager_id: e.target.value }))}>
              <option value="">Ответственный — не выбран</option>
              {(data?.managers || []).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <input style={inp} placeholder="Заметка" value={newCab.note}
              onChange={e => setNewCab(v => ({ ...v, note: e.target.value }))} />
          </div>
        </Modal>
      )}

      {attach && (
        <Modal title={`Площадки · ${attach.cabinet.name}`} width={680}
          onClose={() => setAttach(null)}
          summary="Показаны только свободные: площадка живёт ровно в одном кабинете."
          footer={(
            <button style={btn(true)} disabled={busy || !attach.ids.length}
              onClick={() => run(async () => {
                await api.post(`/cabinets/${attach.cabinet.id}/publishers`,
                  { publisher_ids: attach.ids }, auth())
                setAttach(null)
              })}>Прикрепить</button>
          )}>
          <FreePublishers options={data?.free_publishers || []} selected={attach.ids}
            onToggle={id => setAttach(a => ({ ...a,
              ids: a.ids.includes(id) ? a.ids.filter(x => x !== id) : [...a.ids, id] }))} />
        </Modal>
      )}

      {ourOpen && (
        <OurContacts data={data} busy={busy} onClose={() => setOurOpen(false)}
          onSave={items => run(async () => {
            await api.put('/cabinets/our-contacts', { items }, auth())
            setOurOpen(false)
          })} />
      )}

      {fullLog && (
        <Modal title={`Журнал · ${fullLog.cabinet.name}`} width={720}
          onClose={() => setFullLog(null)}
          summary="Ту же ленту площадка видит у себя в кабинете.">
          {fullLog.rows.map((r, i) => <LogRow key={i} row={r} />)}
          {!fullLog.rows.length && (
            <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
              За 90 дней действий не было.
            </div>
          )}
        </Modal>
      )}

      {shown && (
        <Modal title="Пароль выдан" width={540} onClose={() => setShown(null)}
          summary="Показывается один раз — скопируйте и передайте в рабочий чат площадки.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontFamily: MONO, fontSize: 15, background: 'var(--bg-subtle)',
              border: '1px solid var(--border-card)', borderRadius: 10, padding: '10px 12px',
              display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ flex: 1 }}>{shown.password}</span>
              <button style={btnSm(false)} title="Скопировать"
                onClick={() => navigator.clipboard?.writeText(shown.password)}>Копировать</button>
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
              Вход: <b>{shown.email}</b>
            </div>
            {shown.chat && (
              <a href={shown.chat.url} target="_blank" rel="noreferrer"
                style={{ ...btnSm(false), textDecoration: 'none', width: 'max-content' }}>
                Открыть чат · {shown.chat.name}
              </a>
            )}
          </div>
        </Modal>
      )}

      {vpop && (
        <ValuePopover anchor={vpop.rect} title={vpop.title} value={vpop.value}
          clearLabel={vpop.clearLabel} options={vpop.options} onAddNew={vpop.onAddNew}
          onPick={v => { vpop.apply(v); setVpop(null) }} onClose={() => setVpop(null)} />
      )}
    </>
  )
}

/** Модалка общих контактов. Список целиком, порядок — часть смысла. */
function OurContacts({ data, busy, onClose, onSave }) {
  const [items, setItems] = useState(
    (data?.our_contacts || []).map(x => ({ role: x.role, rep_id: x.rep_id, is_shown: x.is_shown })))
  const managers = data?.managers || []
  const nameOf = (id) => managers.find(m => m.id === id)?.name || '—'
  const set = (i, k, v) => setItems(s => s.map((x, j) => (j === i ? { ...x, [k]: v } : x)))
  return (
    <Modal title="Наши контакты у площадок" width={620} onClose={onClose}
      summary="Одни на все кабинеты: площадка видит, к кому идти. Порядок — сверху важнее."
      footer={<button style={btn(true)} disabled={busy}
        onClick={() => onSave(items)}>Сохранить</button>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map((it, i) => (
          <div key={i} style={{ display: 'grid', gap: 8, alignItems: 'center',
            gridTemplateColumns: '1.2fr 1.4fr 90px 34px' }}>
            <input style={inp} placeholder="Роль" value={it.role}
              onChange={e => set(i, 'role', e.target.value)} />
            <select style={sel} value={it.rep_id}
              onChange={e => set(i, 'rep_id', Number(e.target.value))}>
              {managers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <button style={btnSm(it.is_shown)} onClick={() => set(i, 'is_shown', !it.is_shown)}>
              {it.is_shown ? 'виден' : 'скрыт'}
            </button>
            <IconBtn title="Убрать"
              onClick={() => setItems(s => s.filter((_, j) => j !== i))}>×</IconBtn>
          </div>
        ))}
        {!items.length && (
          <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>
            Контакты не выбраны — площадка не увидит, к кому обращаться.
          </div>
        )}
        <button style={{ ...btnSm(false), width: 'max-content' }}
          disabled={!managers.length}
          onClick={() => setItems(s => [...s, { role: '', rep_id: managers[0]?.id, is_shown: true }])}>
          + Контакт
        </button>
        <span style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.45 }}>
          Почта берётся из учётки сотрудника. У кого её нет — площадка увидит имя без
          способа связаться: {nameOf(items[0]?.rep_id)} и остальные проверяются при сохранении.
        </span>
      </div>
    </Modal>
  )
}
