/**
 * Гейт сборки: уровни конструктора ролей раскладываются по флагам без потерь.
 *
 * ЗАЧЕМ. Конструктор ролей показывает один уровень на раздел («нет / просмотр / редактирование»),
 * а под ним лежат несколько булевых прав. Если раскладка теряет флаг, это не видно глазами:
 * владелец выбрал уровень, нажал «Сохранить», и у роли тихо пропало «удаление». Такой дефект
 * ловится только здесь — бэкенд честно сохранит то, что ему прислали.
 *
 * Правила: (1) «просмотр» включает только просмотр; (2) «правка» в обычном разделе включает все
 * действия; (3) «правка» в разделе «свои/все» включает просмотр, правку и «удаление» (если оно
 * есть у раздела); (4) смена «свои → все» НЕ возвращает снятую галочку «удаление»; (5) «нет»
 * снимает всё; (6) галочку «удаление» видно только при уровне «правка» и не админу.
 */
import { flagsForLevel, showDeleteBox, deleteAllowed } from '../lib/roleLevels.mjs'

const plain = { key: 'contracts', actions: ['view', 'edit', 'delete'] }
const scoped = { key: 'year_plan', actions: ['view', 'edit', 'delete'] }
const scopedNoDelete = { key: 'sales_dashboard', actions: ['view', 'edit'] }
const withApprove = { key: 'creatives', actions: ['view', 'edit', 'delete', 'approve'] }

const errors = []
const eq = (name, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want)
  if (g !== w) errors.push(`${name}: получено ${g}, ожидалось ${w}`)
}

eq('просмотр', flagsForLevel(plain, 'view'), { view: true, edit: false, delete: false })
eq('правка (обычный раздел) включает всё', flagsForLevel(plain, 'edit'), { view: true, edit: true, delete: true })
eq('правка включает и согласование', flagsForLevel(withApprove, 'edit'),
   { view: true, edit: true, delete: true, approve: true })
eq('нет снимает всё', flagsForLevel(withApprove, 'none'),
   { view: false, edit: false, delete: false, approve: false })

eq('«свои/все»: правка с нуля включает удаление', flagsForLevel(scoped, 'edit_own', { view: true }, true),
   { view: true, edit: true, delete: true })
eq('«свои/все»: просмотр снимает удаление', flagsForLevel(scoped, 'view_all', { view: true, edit: true, delete: true }, true),
   { view: true, edit: false, delete: false })
eq('«свои/все»: нет', flagsForLevel(scoped, 'none', { view: true, edit: true, delete: true }, true),
   { view: false, edit: false, delete: false })
eq('«свои → все» не возвращает снятое удаление',
   flagsForLevel(scoped, 'edit_all', { view: true, edit: true, delete: false }, true),
   { view: true, edit: true, delete: false })
eq('«свои → все» не отнимает оставленное удаление',
   flagsForLevel(scoped, 'edit_all', { view: true, edit: true, delete: true }, true),
   { view: true, edit: true, delete: true })
eq('у раздела без «удаления» флаг не появляется',
   flagsForLevel(scopedNoDelete, 'edit_all', { view: true }, true), { view: true, edit: true })

eq('галочка видна при правке', showDeleteBox(plain, 'edit', false), true)
eq('галочка видна при правке «свои»', showDeleteBox(scoped, 'edit_own', false), true)
eq('галочки нет при просмотре', showDeleteBox(plain, 'view', false), false)
eq('галочки нет у админа', showDeleteBox(plain, 'edit', true), false)
eq('галочки нет у раздела без «удаления»', showDeleteBox(scopedNoDelete, 'edit_all', false), false)

// Кнопки удаления: решает ключ `delete`; снимок прав, снятый до его появления, — запасной вариант «правка»
eq('удаление: ключ delete=true решает', deleteAllowed({ view: true, edit: false, delete: true }), true)
eq('удаление: delete=false при правке — нельзя', deleteAllowed({ view: true, edit: true, delete: false }), false)
eq('удаление: старый снимок с правкой — можно', deleteAllowed({ view: true, edit: true }), true)
eq('удаление: старый снимок без правки — нельзя', deleteAllowed({ view: true }), false)
eq('удаление: раздела нет в снимке — нельзя', deleteAllowed(undefined), false)

if (errors.length) {
  console.error('check-role-levels: ошибки раскладки уровней ролей:')
  errors.forEach(e => console.error('  ' + e))
  process.exit(1)
}
console.log('check-role-levels: ок (раскладка уровней без потерь)')
