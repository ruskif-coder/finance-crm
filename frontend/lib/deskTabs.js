/**
 * Вкладки «Закрывающих документов» (`components/onecDesk/AccountantDocs.jsx`). Архив (владелец 12.11.2026): заявки пакетов,
 * закрытых оплатой и подписью, приходят только по кнопке «Загрузить архив» (`archived: true`) и живут только в своей вкладке.
 */
export const waitsScan = r => r.status === 'done' && !r.ds_signed && r.channel === 'бумага'

export const inTab = (r, tab) => {
  if (tab === 'archive') return !!r.archived
  if (r.archived) return false
  return tab === 'all' ? true : tab === 'scan' ? waitsScan(r) : r.status === tab
}
