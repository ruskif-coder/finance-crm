// Клавиатура меню v3 (README §4): 1–5 — панель контура; ↑↓ — по экранам по кругу;
// ←→ — соседний раздел, включая «Справочники»; Enter — перейти; Esc — закрыть; Ctrl/⌘ K — поиск (по коду клавиши,
// раскладка не важна). В полях ввода работают только Esc и Ctrl K. Под открытым окном цифры не перехватываются —
// окно может ждать их само.
import { useEffect, useRef } from 'react'

const inField = (t) => !!t && (['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable)

export default function useNavKeys(state) {
  const ref = useRef(state)
  ref.current = state

  useEffect(() => {
    const onKey = (e) => {
      const s = ref.current
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.code === 'KeyK') { e.preventDefault(); s.openSearch(); return }
      if (e.key === 'Escape') { if (s.hov >= 0) s.closeNow(); return }
      if (e.defaultPrevented || inField(e.target) || e.ctrlKey || e.metaKey || e.altKey) return
      if (document.querySelector('[data-overlay]')) return
      if (/^[1-9]$/.test(e.key)) {
        const i = +e.key - 1
        if (i >= s.tops.length) return
        e.preventDefault()
        const cur = s.tops[i].items.findIndex(it => it.href === s.currentHref)
        s.setMoving(s.hov >= 0)
        s.setHov(i); s.setFocused(Math.max(0, cur)); s.setKb(true)
        return
      }
      if (s.hov < 0) return
      const sec = s.panelSecs[s.hov]
      const n = sec.items.length
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const d = e.key === 'ArrowDown' ? 1 : -1
        s.setFocused(s.focused < 0 ? (d > 0 ? 0 : n - 1) : (s.focused + d + n) % n)
        s.setKb(true)
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault()
        const m = s.panelSecs.length
        s.setMoving(true)
        s.setHov((s.hov + (e.key === 'ArrowRight' ? 1 : -1) + m) % m); s.setFocused(0); s.setKb(true)
      } else if (e.key === 'Enter' && s.focused >= 0) {
        e.preventDefault()
        s.go(sec.items[s.focused].href)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
}
