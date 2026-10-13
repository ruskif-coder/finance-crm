import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { EXPORT_COLUMNS, NOT_EXPORTED, exportTable } from './dealsExport.mjs'

// Ключи колонок реестра — из исходника кита (он JSX, импортировать его в node нечем).
const KIT = readFileSync(new URL('../components/salesTableKit.js', import.meta.url), 'utf8')
const block = KIT.slice(KIT.indexOf('export const DEAL_COLS = ['), KIT.indexOf('export const DEAL_DEFAULT_HIDDEN'))
const KEYS = [...block.matchAll(/\{ key: '([a-z_]+)'/g)].map(m => m[1])

test('в реестре есть колонки (разбор исходника не промахнулся)', () => {
  assert.ok(KEYS.length >= 17, KEYS.join(','))
})

test('у КАЖДОЙ колонки реестра есть экспортёр — новая колонка без выгрузки ловится здесь', () => {
  const missing = KEYS.filter(k => !EXPORT_COLUMNS[k] && !NOT_EXPORTED.includes(k))
  assert.deepEqual(missing, [])
})

const DEAL = {
  code: 'AFKJMM', agency: 'DA', advertiser: 'Materia', brand: 'Artics', product: 'еФарм', period: '2026-10',
  bitrix_stage: 'В размещении', amount: 225000, sales_rep: 'Андрей М.', account_manager: 'Валерия М.', payer: 'ООО Тест',
  pipeline: 'Основная', period_from: '2026-10-01', period_to: '2026-10-31', title: 'Сделка', money_layer: 'план',
  units: { model: 'CPM', price_min: 120, price_max: 150, metric: 'impressions', plan: 500000, fact: 136018 },
}

test('строка выгрузки несёт новые поля: продавец, воронка, даты РК, цена, план/факт', () => {
  const { head, rows } = exportTable([DEAL], KEYS)
  const row = Object.fromEntries(head.map((h, i) => [h, rows[0][i]]))
  assert.equal(row['Продавец'], 'Андрей М.')
  assert.equal(row['Воронка'], 'Основная')
  assert.equal(row['Старт РК'], '01.10.2026')        // день.месяц.год
  assert.equal(row['Конец РК'], '31.10.2026')
  assert.equal(row['Цена ед.'], '120–150')
  assert.equal(row['Модель закупки'], 'CPM')
  assert.equal(row['План, ед.'], 500000)
  assert.equal(row['Факт, ед.'], 136018)
  assert.equal(row['Выполнение, %'], 27)
  assert.equal(row['Метрика'], 'показы')
  assert.equal(row['Слой'], 'план')
})

test('ширина строки всегда равна заголовку, в том числе у сделки без медиаплана и без дат', () => {
  const bare = { code: 'X1', bitrix_id: 'x', amount: 0 }
  const { head, rows } = exportTable([DEAL, bare], KEYS)
  rows.forEach(r => assert.equal(r.length, head.length))
  const empty = Object.fromEntries(head.map((h, i) => [h, rows[1][i]]))
  assert.equal(empty['Цена ед.'], '')
  assert.equal(empty['Факт, ед.'], '')
})

test('единая цена — числом, факт ещё не пришёл — пусто', () => {
  const d = { ...DEAL, units: { model: 'CPC', price_min: 15, price_max: 15, metric: 'clicks', plan: 1000, fact: null } }
  const { head, rows } = exportTable([d], KEYS)
  const row = Object.fromEntries(head.map((h, i) => [h, rows[0][i]]))
  assert.equal(row['Цена ед.'], 15)
  assert.equal(row['Факт, ед.'], '')
  assert.equal(row['Метрика'], 'клики')
})
