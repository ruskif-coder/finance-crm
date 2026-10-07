// Раскладка выбранного в конструкторе ролей УРОВНЯ по флагам действий раздела.
//
// Зависимостей нет намеренно: модуль импортирует и страница `pages/settings/roles.js`, и гейт
// сборки `scripts/check-role-levels.mjs` (как `lib/legacy.mjs` для `check-nav`).
//
// ПОЧЕМУ ВЫНЕСЕНО. Уровни «нет / просмотр / редактирование» выставляют сразу несколько булевых
// полей. «Редактирование» включало ВСЕ действия раздела, и снять «удаление», оставив правку, было
// нечем. А у разделов с выбором «свои/все» уровень выставлял только `view` и `edit`, остальные
// флаги пропадали — и при сохранении роли «удаление» молча обнулялось бы. Оба места невидимы
// глазами, поэтому правило лежит в одном месте и стережётся гейтом.
//
// level  — 'none' | 'view' | 'edit' | 'view_own' | 'view_all' | 'edit_own' | 'edit_all'
// prev   — флаги раздела ДО выбора ({ view, edit, delete, … }); нужны, чтобы смена «свои → все» не
//          сбрасывала галочку «удаление», которую владелец снял вручную.

export function flagsForLevel(section, level, prev = {}, scoped = false) {
  const actions = section.actions || []
  const has = (a) => actions.includes(a)
  const isEdit = level === 'edit' || String(level).startsWith('edit')

  if (scoped) {
    // Исторически у разделов «свои/все» задавались только просмотр и правка. «Удаление» — новое
    // действие: при переходе на правку включается, если раньше правки не было, и сохраняется как
    // есть, если уже была (смена своих на все не должна возвращать снятую галочку).
    const sec = { view: level !== 'none', edit: isEdit }
    if (has('delete')) sec.delete = isEdit ? (prev.edit ? !!prev.delete : true) : false
    return sec
  }
  if (level === 'view') return Object.fromEntries(actions.map(a => [a, a === 'view']))
  if (level === 'edit') return Object.fromEntries(actions.map(a => [a, true]))
  return Object.fromEntries(actions.map(a => [a, false]))   // none
}

// Показывать ли галочку «удаление» у раздела в этой ячейке: только при уровне «правка» и не админу.
export function showDeleteBox(section, level, isAdmin) {
  return !isAdmin && (section.actions || []).includes('delete') && String(level).startsWith('edit')
}

// Может ли пользователь УДАЛЯТЬ записи раздела по снимку его прав (`perms[section]`).
//
// «Удаление» — отдельное право с 07.10.2026. Снимок прав лежит в браузере и делается при входе,
// поэтому у тех, кто вошёл ДО выкладки, ключа `delete` в нём нет: для них действует «правка» (как было
// до разделения). Иначе у них пропали бы кнопки удаления до следующего входа, хотя сервер их пускает.
// У тех, кто вошёл после, ключ есть, и решает он — в том числе когда `delete: false` при `edit: true`.
export function deleteAllowed(sectionPerms) {
  if (!sectionPerms) return false
  return 'delete' in sectionPerms ? !!sectionPerms.delete : !!sectionPerms.edit
}
