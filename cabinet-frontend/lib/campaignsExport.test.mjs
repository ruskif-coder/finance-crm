// Выгрузка «Кампаний» в Excel (владелец 29.10.2026): ровно то, что на экране после фильтров, в том же порядке.
// Запуск: node --test lib/campaignsExport.test.mjs
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { campaignsCsv } from './campaignsExport.mjs'

const row = (over = {}) => ({
  site: 'a.ru', advertiser: 'Рекламодатель А', brand_name: 'Бренд Б', service: 'еФарм', surface: 'web',
  flight: '01.10 — 31.10', plan: 10000, fact: 5064, cpm: 100, erid: 'Kra1', status: 'завершён', ...over,
})

test('строка — месяц, площадка и числа как числа; биллинг считан руками: 5 064 × 100 / 1000 = 506', () => {
  const lines = campaignsCsv([{ key: '2026-10', list: [row()] }]).replace(/^﻿/, '').trim().split('\r\n')
  assert.equal(lines[0], 'Месяц;Площадка;Рекламодатель;Бренд;Услуга;Поверхность;Флайт;План показов;Факт показов;Биллинг до НДС, ₽;ЕРИД;Статус')
  assert.equal(lines[1], '2026-10;a.ru;Рекламодатель А;Бренд Б;еФарм;web;01.10 — 31.10;10000;5064;506;Kra1;завершён')
})

test('файл начинается с BOM — иначе Excel читает кириллицу как кракозябры', () => {
  assert.ok(campaignsCsv([]).startsWith('﻿'))
})

test('порядок — как на экране: месяцы и строки в том порядке, в каком пришли', () => {
  const out = campaignsCsv([{ key: '2026-11', list: [row({ erid: 'X' })] }, { key: '2026-10', list: [row({ erid: 'Y' }), row({ erid: 'Z' })] }])
  assert.deepEqual(out.trim().split('\r\n').slice(1).map(l => l.split(';')[10]), ['X', 'Y', 'Z'])
})

test('нет факта — биллинг пустой, а не ноль: на экране там прочерк', () => {
  const line = campaignsCsv([{ key: '2026-10', list: [row({ fact: 0 })] }]).trim().split('\r\n')[1]
  assert.equal(line.split(';')[9], '')
})

test('точка с запятой, кавычки и перевод строки внутри значения экранируются', () => {
  const line = campaignsCsv([{ key: '2026-10', list: [row({ brand_name: 'А; "Б"\nВ' })] }]).trim().split('\r\n').slice(1).join('\r\n')
  assert.ok(line.includes('"А; ""Б""\nВ"'))
})

test('значение, похожее на формулу, уходит текстом — Excel не исполнит его (и с ведущим таб/CR — ревью 29.10.2026)', () => {
  for (const evil of ['=HYPERLINK("x")', '+1', '-1+2', '@SUM(A1)', '\t=1', '\r=1']) {
    const out = campaignsCsv([{ key: '2026-10', list: [row({ brand_name: evil })] }])
    const brandCell = out.split('\r\n')[1].split(';')[3]
    assert.ok(brandCell.startsWith("'") || brandCell.startsWith('"\''), JSON.stringify(evil))
  }
})
