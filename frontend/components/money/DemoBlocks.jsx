/**
 * Блоки, которым в учёте пока нечем питаться (аудит 18.11.2026) — нарисованы по макету с ЕГО цифрами и помечены «демо».
 * Убирать пометку — вместе с данными: «Деньги в обороте» ждут связи оплаты площадке со сделкой, «Заёмные» — кредита
 * отдельным типом с графиком (п. 16), «План/факт» — бюджета месяца (п. 21), «Горизонт денег» — прогноза (п. 23).
 */
import { CARD, CAPS, H, MONO, NUM, STUB, Bar, DemoTag, Dot, f } from './kit'

const TURN = [['Альфарм', 1120000, 2205058, 41, true], ['Восток-Медиа', 610000, 740000, 77, true], ['Адлабс', 980000, 2440000, 26, false],
  ['ДД', 402000, 1220000, 18, false], ['Полисорб', 300000, 773943, 12, false]]

export function Turnover() {
  const total = TURN.reduce((a, r) => a + r[1], 0)
  const over = TURN.filter(r => r[4]).reduce((a, r) => a + r[1], 0)
  const avg = Math.round(TURN.reduce((a, r) => a + r[1] * r[3], 0) / total)
  const cols = 'minmax(0,1fr) 130px 130px minmax(0,150px)'
  return (
    <div style={{ ...CARD, display: 'grid', gridTemplateColumns: '300px minmax(0,1fr)', gap: 24 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}><span style={H}>Деньги в обороте</span>
          <DemoTag why="Нужна связь оплаты площадке со сделкой: выплаты площадкам сейчас заводятся отдельными операциями без ссылки на сверку" /></span>
        <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>Уже оплатили площадкам по сделкам, за которые клиент ещё не заплатил: столько мы сейчас кредитуем клиентов.</span>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={{ ...NUM, fontSize: 34, letterSpacing: '-0.02em' }}>{f(total)}</span>
          <span style={{ fontFamily: MONO, fontSize: 14, color: 'var(--text-muted)' }}>₽</span></span>
        <Bar parts={TURN.map(r => ({ w: r[1], c: r[4] ? 'var(--bad)' : 'var(--ok)', t: `${r[0]} · ${f(r[1])} ₽` }))} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px', paddingTop: 10, borderTop: '1px solid var(--border-inner)' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={CAPS}>у клиентов с просрочкой</span><span style={{ ...NUM, fontSize: 16, color: 'var(--bad-fg)' }}>{f(over)}</span></span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={CAPS}>ждём в среднем</span><span style={{ ...NUM, fontSize: 16 }}>{avg} дн</span></span>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, padding: '0 0 6px', borderBottom: '1px solid var(--border-inner)' }}>
          <span style={CAPS}>клиент</span><span style={{ ...CAPS, textAlign: 'right' }}>оплатили площадкам</span>
          <span style={{ ...CAPS, textAlign: 'right' }}>клиент должен</span><span style={CAPS}>ждём, дней</span></div>
        {TURN.map(r => {
          const c = r[4] ? 'var(--bad)' : 'var(--ok)'
          return (
            <div key={r[0]} style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, alignItems: 'center', height: 42, borderBottom: '1px solid var(--border-row)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}><Dot c={c} /><span style={{ fontSize: 13, fontWeight: 700 }}>{r[0]}</span></span>
              <span style={{ ...NUM, fontSize: 13, textAlign: 'right' }}>{f(r[1])}</span>
              <span style={{ fontFamily: MONO, fontSize: 12.5, textAlign: 'right', color: r[4] ? 'var(--bad-fg)' : 'var(--text-secondary)' }}>{f(r[2])}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ flex: '1 1 auto', height: 6, borderRadius: 3, background: 'var(--bg-subtle)', position: 'relative', overflow: 'hidden' }}>
                  <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, r[3] / 90 * 100)}%`, borderRadius: 3, background: c }} /></span>
                <span style={{ fontFamily: MONO, fontSize: 11.5, width: 26, textAlign: 'right', color: r[4] ? 'var(--bad-fg)' : 'var(--text-primary)' }}>{r[3]}</span>
              </span>
            </div>
          )
        })}
        <span style={{ marginTop: 'auto', paddingTop: 10, fontSize: 12, color: 'var(--text-muted)' }}>Коралловым — клиенты с просроченной оплатой: деньги у них дольше всего.</span>
      </div>
    </div>
  )
}

const NEXT = [['25.11', '127 500', '52 500'], ['25.12', '129 400', '50 600'], ['26.01', '131 300', '48 700']]

export function Loans() {
  return (
    <div style={{ ...CARD, gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={H}>Заёмные</span>
        <DemoTag why="Нужен учёт кредита отдельным типом: тело и проценты раздельно, график погашений (п. 16). Сейчас тело и проценты разбираются по тексту назначения" />
        <span style={{ marginLeft: 'auto', ...NUM, fontSize: 15 }}>3 500 000 ₽</span></div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 14px', borderRadius: 14, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={{ fontSize: 13.5, fontWeight: 700 }}>Кредит · АльфаБанк</span>
          <span style={CAPS}>18 % годовых</span><span style={{ marginLeft: 'auto', ...NUM, fontSize: 14 }}>3 500 000</span></span>
        <div style={{ height: 8, borderRadius: 4, background: 'var(--bg-card)', border: '1px solid var(--border-inner)', position: 'relative', overflow: 'hidden' }}>
          <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '12.5%', background: 'var(--ok)' }} /></div>
        <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--text-muted)' }}>
          <span>погашено <b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>500 000</b> из 4 000 000</span><span>до 25.09.2027</span></span>
        <div style={{ display: 'flex', flexDirection: 'column', marginTop: 4 }}>
          {NEXT.map((x, k) => (
            <div key={x[0]} style={{ display: 'grid', gridTemplateColumns: '62px minmax(0,1fr) auto', gap: 10, alignItems: 'baseline', padding: '7px 0', borderTop: '1px solid var(--border-row)' }}>
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: k ? 500 : 800 }}>{x[0]}</span>
              <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>тело {x[1]} · % {x[2]}</span>
              <span style={{ ...NUM, fontSize: 12.5 }}>180 000</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderRadius: 14, border: '1px solid var(--border-card)' }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}><span style={{ fontSize: 13.5, fontWeight: 700 }}>Овердрафт · ОТП Банк</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>лимит 1 000 000 · использовано 0</span></span>
        <span style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}><span style={CAPS}>свободно</span>
          <span style={{ ...NUM, fontSize: 15, color: 'var(--money-fg)' }}>1 000 000</span></span>
      </div>
    </div>
  )
}

const PF = [['Поступления', 5000000, 9850000, 'var(--money)', 'var(--money-fg)', 'отстаём от темпа на 0,91 млн'],
  ['Списания', 287210, 6420000, 'var(--ok)', 'var(--text-primary)', 'впереди 6,13 млн']]

/** «План / факт» — заготовка «появится с планом месяца», как в макете: содержимое приглушено. */
export function PlanFactStub({ monthName }) {
  return (
    <div style={{ ...STUB, gap: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={CAPS}>появится с бюджетом месяца</span>
        <span style={{ ...H, color: 'var(--text-secondary)' }}>План / факт · {monthName}</span></div>
      <div style={{ flex: '1 1 auto', display: 'flex', flexDirection: 'column', gap: 16, opacity: 0.45, filter: 'grayscale(0.6)', pointerEvents: 'none' }}>
        {PF.map(p => (
          <div key={p[0]} style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={{ fontSize: 13, fontWeight: 700 }}>{p[0]}</span>
              <span style={{ marginLeft: 'auto', ...NUM, fontSize: 15, color: p[4] }}>{f(p[1])}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>из {f(p[2])}</span></div>
            <div style={{ position: 'relative', height: 12, borderRadius: 6, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
              <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, p[1] / p[2] * 100)}%`, borderRadius: 6, background: p[3] }} />
              <span style={{ position: 'absolute', left: '60%', top: -4, bottom: -4, width: 2, borderRadius: 1, background: 'var(--text-primary)' }} /></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-secondary)' }}>
              <span><b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{Math.round(p[1] / p[2] * 100)}%</b> плана</span><span>{p[5]}</span></div>
          </div>
        ))}
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>Ориентир: бюджет поступлений и списаний на месяц, факт по выпискам, чёрная риска — где должен быть факт при ровном темпе. Цифры условные.</span>
    </div>
  )
}

export function HorizonStub() {
  return (
    <div style={{ ...STUB, gap: 10 }}>
      <span style={CAPS}>появится с прогнозом</span>
      <span style={{ ...H, color: 'var(--text-secondary)' }}>Горизонт денег</span>
      <span style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>Дата, когда остаток уйдёт ниже неснижаемого, на 3 месяца вперёд, и сколько не хватит. При угрозе — коралловый баннер над экраном.</span>
      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: 'var(--text-disabled)' }}>дд.мм</span>
        <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-disabled)' }}>не хватит — — — ₽</span></div>
    </div>
  )
}
