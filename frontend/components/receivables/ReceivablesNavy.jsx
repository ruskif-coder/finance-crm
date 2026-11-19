/**
 * Дебиторская задолженность · NAVY — настольный экран (хендофф docs/design_handoff_receivables_navy.zip, 19.11.2026).
 * Данные — /reports/receivables как есть; расчёт — ./model. Мобильная версия — прежняя (components/mobile/ReceivablesMobile).
 *
 * Чего нет в учёте и что поэтому неактивно: «Напомнить по выбранным» и «Записать контакт» — журнала контактов по долгу нет;
 * «Подготовить акт зачёта» — шаблона акта нет. Ответственный — аккаунт последней сделки, где контрагент платит (своего поля нет).
 */
import { useMemo, useState } from 'react'
import { Segmented } from '@/lib/motion'
import { CAPS } from '@/components/money/kit'
import { bucketer, clients, parseDate, fd, FILTER_FN } from './model'
import TopStrip from './TopStrip'
import AgeChart, { ageBuckets } from './AgeChart'
import Concentration from './Concentration'
import DebtTable from './DebtTable'

export default function ReceivablesNavy({ data, notes, saveNote, noteStatus, canEditNote, onExport, onDs, onInv }) {
  const [mode, setMode] = useState('contract')
  const [flt, setFlt] = useState('')
  const [sort, setSort] = useState('risk')
  const [bk, setBk] = useState(null)
  const [openMap, setOpenMap] = useState({})
  const today = parseDate(data.as_of)
  const real = mode === 'real'
  const all = useMemo(() => clients(data, notes), [data, notes])
  const bkr = useMemo(() => bucketer(today, real), [data.as_of, real])   // eslint-disable-line react-hooks/exhaustive-deps
  const buckets = useMemo(() => ageBuckets(all, bkr, real), [all, bkr, real])
  const bkOn = bk != null
  const inBk = (x) => (it) => bkr.of(x, it) === bk
  const sumOf = (x) => (bkOn ? x.its.filter(inBk(x)).reduce((a, it) => a + it.v, 0) : x.sum)
  let list = all.filter(x => (!flt || FILTER_FN[flt](x)) && (!bkOn || sumOf(x) > 0))
  list = list.slice().sort((a, b) => (bkOn ? sumOf(b) - sumOf(a) : sort === 'risk' ? b.risk - a.risk : b.sum - a.sum))
  // при отборе по корзине строки раскрыты сразу (свернуть можно); без отбора — по клику
  const isOpen = (x) => (bkOn ? openMap[x.id] !== 0 : !!openMap[x.id])
  const toggle = (x) => setOpenMap(m => ({ ...m, [x.id]: isOpen(x) ? 0 : 1 }))
  const pickBk = (k) => { setBk(k); setOpenMap({}) }
  return (
    <div className="navy-scr" style={{ maxWidth: 1880, margin: '0 auto', boxSizing: 'border-box', padding: '22px 26px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>Дебиторская задолженность</span>
          <span style={{ ...CAPS, fontSize: 11 }}>на {fd(today)}.{today.getFullYear()} · суммы без НДС</span>
        </div>
        <span style={{ marginLeft: 'auto' }}>
          <Segmented tone="hot" value={mode} onChange={(m) => { setMode(m); setBk(null); setOpenMap({}) }}
            title="Сроки по договору или с учётом того, как клиент обычно платит (среднее время оплаты)"
            options={[['contract', 'По договору'], ['real', 'Как платят на деле']]} />
        </span>
      </div>
      <TopStrip all={all} today={today} bk={bkr} onFilter={(k) => { setFlt(k); setBk(null) }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,2.1fr) minmax(0,1fr)', gap: 16 }}>
        <AgeChart buckets={buckets} real={real} sel={bk} onPick={pickBk} />
        <Concentration all={all} />
      </div>
      <DebtTable all={all} list={list} flt={flt} setFlt={setFlt} sort={sort} setSort={setSort}
        bkOn={bkOn} bkLabel={bkOn ? `${real ? 'придут' : 'возраст'}: ${bkr.labels[bk]}` : ''} onBkReset={() => pickBk(null)}
        open={isOpen} setOpen={toggle} sumOf={sumOf} only={(x) => (bkOn ? inBk(x) : null)} onExport={onExport}
        rowProps={(x) => ({ canEdit: canEditNote, onSaveNote: saveNote, noteStatus: noteStatus[x.id], onDs, onInv })} />
    </div>
  )
}
