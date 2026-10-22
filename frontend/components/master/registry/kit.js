/**
 * Стили реестра мастер-сделок: кнопки колонки «Действие» (единый вид 152×30, хендофф §2) и капс-подписи.
 */
import { MONO, UI } from '@/components/salesTableKit'

export const CAPS = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
export const BTN = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 152, height: 30, boxSizing: 'border-box',
  borderRadius: 9, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', textDecoration: 'none', cursor: 'pointer', fontFamily: UI }
export const BTN_STEP = { ...BTN, background: 'var(--accent)', border: '1px solid var(--accent)', color: 'var(--on-accent)' }
export const BTN_ARCH = { ...BTN, background: 'var(--bg-card)', border: '1px solid var(--income-border)', color: 'var(--income-fg)' }
export const BTN_LINK = { ...BTN, background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-secondary)', fontWeight: 600 }

export const KEEP = 'в работе'
