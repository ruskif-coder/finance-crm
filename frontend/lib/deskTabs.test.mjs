// Вкладки «Закрывающих документов» и архив (владелец 12.11.2026: пакеты после оплаты — в архив, грузится по кнопке).
// Поломка: архивная заявка показывается во «Внесены» / «Все» / «Ждут сканов» вперемешку с рабочими, или «Архив» пуст после загрузки.
import test from 'node:test'
import assert from 'node:assert/strict'
import { inTab } from './deskTabs.js'

const done = { status: 'done', ds_signed: true, channel: 'ЭДО' }
const arch = { ...done, archived: true }
const paperNoScan = { status: 'done', ds_signed: false, channel: 'бумага' }

test('архивная заявка — только во вкладке «Архив»', () => {
  assert.deepEqual(['wait', 'returned', 'done', 'scan', 'all', 'archive'].map(t => inTab(arch, t)), [false, false, false, false, false, true])
})

test('рабочие заявки — как раньше, в «Архив» не попадают', () => {
  assert.equal(inTab(done, 'done'), true)
  assert.equal(inTab(done, 'all'), true)
  assert.equal(inTab(done, 'archive'), false)
  assert.equal(inTab(paperNoScan, 'scan'), true)
})
