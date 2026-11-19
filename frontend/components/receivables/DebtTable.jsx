/** «Контрагенты-должники» (хендофф, п. 5): отбор одним переключателем, сортировка по риску / по сумме, отбор по корзине возраста.
 *  Выбор контрагентов списком и «Факт / Факт + ждём» — из прежней дебиторки (19.11.2026); выгрузка берёт оба. */
import { Segmented } from '@/lib/motion'
import { MultiDrop } from '@/components/salesTableKit'
import { BTN, CAPS, H, MONO, f } from '@/components/money/kit'
import { FILTERS, FILTER_FN } from './model'
import DebtRow, { GRID } from './DebtRow'

export default function DebtTable({ all, list, cps, setCps, cpOptions, fact, setFact, bkLabel, bkOn, onBkReset, flt, setFlt, sort, setSort, open, setOpen, sumOf, only, onExport, rowProps }) {
  const counts = Object.fromEntries(FILTERS.map(q => [q[0], q[0] ? all.filter(FILTER_FN[q[0]]).length : all.length]))
  const hint = flt ? FILTERS.find(q => q[0] === flt)[3] : 'число — сколько контрагентов попадает в отбор'
  return (
    <div data-motion="rise" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 20, padding: '18px 22px 14px',
      display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}><span style={H}>Контрагенты-должники</span>
          <span style={CAPS}>{list.length} из {all.length} · {bkOn ? `только счета «${bkLabel}», по сумме` : sort === 'risk' ? 'по риску: просрочка × сумма × привычка' : 'по убыванию суммы'}</span></span>
        <span style={{ marginLeft: 'auto' }}><MultiDrop label="Контрагенты" options={cpOptions} selected={cps} onChange={setCps} /></span>
        <Segmented tone="hot" value={fact ? 'fact' : 'all'} onChange={v => setFact(v === 'fact')}
          titleOf={v => (v === 'fact' ? 'Только счета, срок оплаты которых наступил: просрочка и текущая' : 'Плюс счета, срок оплаты которых ещё не наступил')}
          options={[['fact', 'Факт'], ['all', 'Факт + ждём']]} />
        <Segmented tone="hot" value={sort} onChange={setSort} options={[['risk', 'По риску'], ['sum', 'По сумме']]} />
        <button type="button" onClick={onExport} style={BTN}
          title={`В Excel: ${cps.length ? `${cps.length} выбранных контрагентов` : 'все контрагенты'}, ${fact ? 'только наступившие счета' : 'все счета, включая ожидаемые'}`}>⭳ Выгрузить</button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '2px 0 4px' }}>
        <span style={CAPS}>показать контрагентов</span>
        <span role="radiogroup" style={{ display: 'inline-flex', padding: 2, borderRadius: 11, background: 'var(--bg-card)', border: '1px solid var(--border-card)', flexWrap: 'wrap' }}>
          {FILTERS.map(([k, label, dot, tip]) => {
            const on = flt === k, n = counts[k], live = n > 0 || !k
            return (
              <button type="button" role="radio" aria-checked={on} key={k || 'all'} title={tip} disabled={!live} onClick={() => setFlt(k)}
                style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', borderRadius: 9, fontSize: 12.5, cursor: live ? 'pointer' : 'default', whiteSpace: 'nowrap',
                  gap: 8, background: on ? 'var(--hot)' : 'transparent', color: on ? 'var(--hot-fg)' : 'var(--text-primary)', fontWeight: on ? 700 : 600, opacity: live ? 1 : 0.4,
                  border: 0, fontFamily: 'inherit' }}>
                {!!dot && <span style={{ width: 7, height: 7, borderRadius: 2, background: dot }} />}{label}
                <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: on ? 'var(--hot-fg)' : 'var(--text-muted)' }}>{n}</span>
              </button>
            )
          })}
        </span>
        {bkOn && <button type="button" onClick={onBkReset} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 32, padding: '0 12px', borderRadius: 10, background: 'var(--hot)',
          color: 'var(--hot-fg)', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap', border: 0, fontFamily: 'inherit' }}>{bkLabel} <span style={{ opacity: 0.7 }}>✕</span></button>}
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{hint}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 14, padding: '0 8px 8px', borderBottom: '1px solid var(--border-inner)' }}>
        <span /><span style={CAPS}>контрагент · ответственный</span><span style={CAPS}>отсрочка · платят</span><span style={{ ...CAPS, textAlign: 'right' }}>сумма</span>
        <span style={CAPS}>возраст</span><span style={CAPS}>примечание</span><span style={{ ...CAPS, textAlign: 'right' }}>сальдо · зачёт</span>
      </div>
      {list.map(x => (
        <DebtRow key={x.id} x={x} open={open(x)} onToggle={() => setOpen(x)} sum={sumOf(x)} only={only(x)} {...rowProps(x)} />
      ))}
      {!list.length && <div style={{ padding: 20, fontSize: 13, color: 'var(--text-muted)' }}>В этом отборе контрагентов нет.</div>}
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 14, padding: '10px 8px 2px' }}>
        <span /><span style={{ fontSize: 13, fontWeight: 800 }}>Итого · {list.length} из {all.length}</span><span />
        <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 800, textAlign: 'right' }}>{f(list.reduce((a, x) => a + sumOf(x), 0))}</span><span /><span />
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{f(list.reduce((a, x) => a + x.sum - x.we, 0))}</span>
      </div>
    </div>
  )
}
