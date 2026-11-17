// Третий уровень пилюли меню v3 — «раздел · экран · объект» (хендофф design_handoff_nav_mix, README §1). Экран, который
// знает код своего объекта (сделка — H9ZY7B, а не 2665 из адреса; раскрытая РК на дашборде трафика — вовсе не в адресе),
// сообщает его сюда. Не сообщил — меню берёт сегмент адреса (`objectOf` в lib/navModel.mjs).
//
// Значение привязано к адресу без запроса: шапка — у каждой страницы своя, а это хранилище модульное и переживает
// переход, так что чужой код со старой страницы на новой не покажется.
import { useEffect, useSyncExternalStore } from 'react'

let current = null          // { path, code, onBack }
const subs = new Set()
const emit = () => subs.forEach(f => f())
const subscribe = (f) => { subs.add(f); return () => subs.delete(f) }
const snapshot = () => current

export const pathOnly = (asPath) => String(asPath || '').split(/[?#]/)[0]

/** Экран: `useNavObject(router.asPath, code, onBack)`. Пустой code — объекта нет (РК свёрнута). onBack — «назад к списку». */
export function useNavObject(asPath, code, onBack) {
  const path = pathOnly(asPath)
  useEffect(() => {
    current = code ? { path, code: String(code), onBack } : null
    emit()
    return () => { if (current?.path === path) { current = null; emit() } }
  }, [path, code, onBack])
}

/** Меню: объект, объявленный экраном для этого адреса, или null. */
export function useDeclaredObject(asPath) {
  const v = useSyncExternalStore(subscribe, snapshot, () => null)
  return v && v.path === pathOnly(asPath) ? v : null
}
