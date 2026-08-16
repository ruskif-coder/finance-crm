/**
 * Точка входа навигации. Исторически здесь жила вся разметка шапки и семь списков
 * с картой приложения; теперь карта переехала в @/lib/nav, а разметка — в @/components/Nav.
 * Файл сохранён именно под этим именем и с этими экспортами, потому что его импортируют
 * 34 страницы: превращение его в обёртку избавляет от правки каждой из них.
 */
import Nav from '@/components/Nav'
import { can } from '@/lib/auth'
import { firstAllowedHref as _first, firstDirectoryHref as _dir } from '@/lib/nav'

export { can }

// Сигнатуры сохранены прежними (perms, role) — так их вызывают существующие страницы.
export const firstAllowedHref = (perms, role) => _first(perms, role === 'admin')
export const firstDirectoryHref = (perms, role) => _dir(perms, role === 'admin')

export default function Navbar({ children, onSearch }) {
  return <Nav onSearch={onSearch}>{children}</Nav>
}
