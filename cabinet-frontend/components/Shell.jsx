/**
 * Оболочка кабинета: шапка и правая колонка.
 *
 * Вынесена из страницы, чтобы страница осталась про работу, а не про хром. Ширина 1600,
 * правая колонка фиксированные 280 — по хендоффу; мобильной версии нет.
 */
import { useState, useEffect } from 'react'
import { C, CAP, MONO, UI, btn, btnSm, card, chip } from '../lib/ui'

export const WRAP = { maxWidth: 1600, margin: '0 auto', padding: '0 20px' }

/* Луна/солнце. Иконка одна, поворачивается смыслом — вторую рисовать незачем. */
const Moon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
)
const Sun = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
)

export function ThemeToggle() {
  const [dark, setDark] = useState(false)
  useEffect(() => {
    setDark(document.documentElement.getAttribute('data-theme') === 'dark')
  }, [])
  const flip = () => {
    const next = !dark
    setDark(next)
    document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light')
    try { localStorage.setItem('cabinet_theme', next ? 'dark' : 'light') } catch { /* приватный режим */ }
  }
  return (
    <button onClick={flip} title={dark ? 'Светлая тема' : 'Тёмная тема'}
      style={{ width: 32, height: 32, borderRadius: 9, display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
        background: C.card, border: `1px solid ${C.border}`, color: C.secondary,
        transition: 'color 150ms ease, border-color 150ms ease' }}>
      {dark ? <Sun /> : <Moon />}
    </button>
  )
}

export function Header({ profile, name, account, nav, active, onNav, onExit, count = 1 }) {
  return (
    /* Плавающая карточка, а не полоса во всю ширину: кабинет — гостевой экран, и
       шапка на нём читается как панель приложения, а не как рамка сайта. Не липкая —
       уезжает вместе со страницей: экран один, скроллить по нему нечего, а
       закреплённая панель на такой странице только съедала бы высоту. */
    <div style={{ padding: '14px 0 0', background: C.canvas }}>
      {/* Обёртка во всю ширину нужна ради фона под верхним отступом; `WRAP` задаёт ту
          же колонку и те же боковые отступы, что у страницы; карточка — уже внутри
          неё. Повесить `WRAP` на саму карточку нельзя: его `padding: 0 20px` уходит
          ВНУТРЬ, и карточка выходит на 40 px шире, чем карточки контента, — ровно
          этим шапка и торчала. */}
      <div style={WRAP}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18,
          height: 60, background: C.card, border: `1px solid ${C.border}`,
          borderRadius: 16, boxShadow: 'var(--shadow-card)', padding: '0 20px' }}>
        {/* Два литеральных <img> и переключение ПРАВИЛОМ: подстановка адреса в `src`
            стартует до первого рендера, и браузер запросил бы файл с именем шаблона. */}
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 14,
          flex: '0 0 auto' }}>
          <img className="logo-light" src="/assets/logo-mediaplan.svg" alt="SIMB-AD" height="26" />
          <img className="logo-dark" src="/assets/logo-mediaplan-dark.svg" alt="SIMB-AD" height="26" />
          {/* Подпись продукта отделена чертой, а не отступом: без неё логотип агентства
              читается как «мы у них в гостях», а не «это наш кабинет у них». */}
          <span style={{ paddingLeft: 14, borderLeft: `1px solid ${C.border}`,
            ...CAP, marginBottom: 0 }}>кабинет паблишера</span>
        </span>

        <nav style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {nav.map(n => (
            <button key={n.key} onClick={() => onNav(n.key)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7,
                padding: '7px 12px', borderRadius: 9, border: 0, cursor: 'pointer',
                fontFamily: UI, fontSize: 13,
                fontWeight: active === n.key ? 700 : 600,
                background: active === n.key ? C.accentTint : 'transparent',
                color: active === n.key ? C.accent : C.secondary }}>
              {n.label}
              {!!n.badge && (
                <span style={{ ...chip(C.dangerTint, C.danger, C.dangerBorder),
                  padding: '1px 6px', fontSize: 10, fontFamily: MONO }}>{n.badge}</span>
              )}
            </button>
          ))}
        </nav>

        <span style={{ flex: 1 }} />
        <ThemeToggle />

        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 32, height: 32, borderRadius: 10, background: C.text,
            color: C.card, display: 'inline-flex', alignItems: 'center',
            justifyContent: 'center', fontWeight: 800, fontSize: 11.5 }}>
            {(profile?.domain || name || '?').replace(/\..*$/, '').slice(0, 3).toUpperCase()}
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.25 }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{profile?.domain || name}</span>
            <span style={{ ...CAP, marginBottom: 0 }}>
              {[profile?.kind, profile?.network].filter(Boolean).join(' · ') || 'площадка'}
            </span>
          </span>
          {/* Раскрывашка площадки. У учётки их бывает несколько — переключатель
              появится вместе с выбором; пока показывает, что список не один. */}
          {count > 1 && (
            <span style={{ color: C.faint, fontSize: 10 }}>▾</span>
          )}

          {/* КТО ВОШЁЛ — после площадки, через разделитель (владелец 15.09.2026).
              До этого шапка называла только сайт, и на общей учётке площадки нельзя было
              понять, под кем ты сидишь: «выйти» есть, а из-под кого — неизвестно. Почта
              здесь не украшение, а различитель: имена у коллег совпадают чаще, чем
              адреса, и по ней же человек понимает, куда ему приходят письма. */}
          {!!account?.name && (
            <>
              <span style={{ color: C.border, fontSize: 15, padding: '0 2px' }}>|</span>
              <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.25,
                minWidth: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{account.name}</span>
                <span style={{ ...CAP, marginBottom: 0, textTransform: 'none',
                  fontSize: 9.5, overflow: 'hidden', textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap' }} title={account.email || ''}>
                  {account.email}
                </span>
              </span>
            </>
          )}
        </span>

        <button style={btnSm(false)} onClick={onExit}>Выйти</button>
        </div>
      </div>
    </div>
  )
}

/** Блок правой колонки. Заголовок капсом, содержимое — как передали. */
export function Side({ title, accent, children, footer }) {
  return (
    <div style={{ ...card, padding: '14px 16px',
      borderColor: accent ? C.accentBorder : C.border,
      display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ ...CAP, marginBottom: 0 }}>{title}</div>
      {children}
      {footer}
    </div>
  )
}

export function Demo({ what }) {
  /* Честная метка. Блок нарисован по эталону, но источника данных в системе нет —
     показывать выдумку без пометки значит однажды услышать «вы мне должны 624 753 ₽». */
  return (
    <span style={{ ...chip(C.warningTint, C.warningFg, C.warningBorder), fontFamily: MONO,
      fontSize: 10 }} title={what}>демо</span>
  )
}

export const btnPrimary = btn(true)
