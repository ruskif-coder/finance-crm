/**
 * Navbar.js — горизонтальная верхняя навигация Silab-AD.
 * Заменяет предыдущий Navbar с боковой панелью.
 *
 * Используется на: dashboard, pl, balance, planfact, receivables, operations.
 * НЕ используется на: settings, import (у них свой header).
 */
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

// ── Разделы (должны совпадать с backend/app/permissions.py SECTIONS) ──
export const SECTIONS = {
  dashboard:   'dashboard',
  operations:  'operations',
  pl:          'pl',
  balance:     'balance',
  planfact:    'planfact',
  receivables: 'receivables',
  settings:    'settings',
  import:      'import',
};

// ── Пункты основной навигации ──────────────────────────────────────
const NAV_ITEMS = [
  { label: 'ДДС',          href: '/dashboard',   section: SECTIONS.dashboard   },
  { label: 'P&L',          href: '/pl',          section: SECTIONS.pl          },
  { label: 'Баланс',       href: '/balance',     section: SECTIONS.balance     },
  { label: 'Дебиторка',    href: '/receivables', section: SECTIONS.receivables },
  { label: 'План / Факт',  href: '/planfact',    section: SECTIONS.planfact    },
];

// ── Утилиты ──────────────────────────────────────────────────────────
const NAV_ITEMS_SECONDARY = [
  { label: 'Операции', href: '/operations', section: SECTIONS.operations },
  { label: 'Импорт',   href: '/import',     section: SECTIONS.import     },
  { label: 'Настройки',href: '/settings',   section: SECTIONS.settings   },
];

export function getPermissions() {
  try {
    const raw = localStorage.getItem('permissions');
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

export function can(perms, section, action = 'view') {
  if (!perms || !section) return false;
  const s = perms[section];
  if (!s) return false;
  return s[action] === true || s['*'] === true;
}

// ── Стили ──────────────────────────────────────────────────────────
const S = {
  header: {
    position:       'fixed',
    top:            0,
    left:           0,
    right:          0,
    zIndex:         100,
    height:         'var(--navbar-h)',
    background:     'var(--bg-header)',
    borderBottom:   '1px solid var(--border-card)',
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    padding:        '0 30px',
    boxShadow:      '0 1px 3px rgba(28,36,51,.06)',
  },
  left: {
    display:    'flex',
    alignItems: 'center',
    gap:        36,
  },
  logo: { height: 24, width: 'auto', display: 'block' },
  nav: {
    display: 'flex',
    gap:     3,
  },
  navItem: (active) => ({
    display:        'flex',
    alignItems:     'center',
    padding:        '8px 16px',
    borderRadius:   10,
    background:     active ? 'var(--accent-tint)' : 'transparent',
    color:          active ? 'var(--accent)'       : 'var(--text-secondary)',
    fontWeight:     active ? 600                   : 500,
    fontSize:       14,
    cursor:         'pointer',
    transition:     'background .15s, color .15s',
    whiteSpace:     'nowrap',
    userSelect:     'none',
  }),
  right: {
    display:    'flex',
    alignItems: 'center',
    gap:        6,
  },
  utilBtn: {
    padding:      '8px 14px',
    borderRadius: 10,
    background:   'var(--bg-subtle)',
    color:        'var(--text-secondary)',
    fontSize:     13,
    fontWeight:   500,
    cursor:       'pointer',
    border:       'none',
    transition:   'background .15s',
  },
  avatar: {
    width:          34,
    height:         34,
    borderRadius:   '50%',
    background:     'var(--text-primary)',
    color:          '#fff',
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    fontSize:       13,
    fontWeight:     600,
    marginLeft:     6,
    cursor:         'pointer',
    flexShrink:     0,
    userSelect:     'none',
  },
};

// ── Компонент ──────────────────────────────────────────────────────
export default function Navbar() {
  const router = useRouter();
  const [perms, setPerms] = useState({});
  const [userName, setUserName] = useState('А');

  useEffect(() => {
    setPerms(getPermissions());
    const name = localStorage.getItem('name') || '';
    setUserName(name ? name[0].toUpperCase() : 'А');
  }, []);

  const handleLogout = () => {
    ['token','role','role_label','is_admin','permissions','name'].forEach(k => localStorage.removeItem(k));
    router.push('/login');
  };

  const navigate = (href) => {
    if (router.pathname !== href) router.push(href);
  };

  const visibleMain = NAV_ITEMS.filter(i => can(perms, i.section));
  const visibleUtil = NAV_ITEMS_SECONDARY.filter(i => can(perms, i.section));

  return (
    <header style={S.header}>
      {/* Левая часть: лого + основная навигация */}
      <div style={S.left}>
        <img src="/logo.png" alt="Silab-AD" style={S.logo} />
        <nav style={S.nav}>
          {visibleMain.map(item => {
            const active = router.pathname === item.href;
            return (
              <div
                key={item.href}
                style={S.navItem(active)}
                onClick={() => navigate(item.href)}
              >
                {item.label}
              </div>
            );
          })}
        </nav>
      </div>

      {/* Правая часть: утилиты + аватар */}
      <div style={S.right}>
        {visibleUtil.map(item => (
          <button
            key={item.href}
            style={S.utilBtn}
            onClick={() => navigate(item.href)}
          >
            {item.label}
          </button>
        ))}
        <div style={S.avatar} title="Выйти" onClick={handleLogout}>
          {userName}
        </div>
      </div>
    </header>
  );
}
