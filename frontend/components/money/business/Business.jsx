/**
 * Вкладка «Бизнес» экрана «Деньги» — по хендоффу design_handoff_money_navy (20.11.2026, «Финансы - бизнес NAVY»), разметка
 * дословно; данные — `GET /money/business` (app/money/business.py). Суммы без НДС, за вычетом «скидки в счёт», в млн.
 * Тема — из профиля пользователя (переключатель NAVY Lite/Dark макета у нас общий, в меню профиля).
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { nextDay } from '@/lib/dates'
import { CARD, CAPS, H, MONO, f } from '../kit'
import Lights from './Lights'
import { likely, m1, pc, sure, vs } from './calc'

const BIG = { fontFamily: MONO, fontSize: 40, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1 }
const UNIT = { fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }
const dm = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}` : '')
const head = (title, cap) => (
  <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}><span style={H}>{title}</span>{!!cap && <span style={{ ...CAPS, marginLeft: 'auto' }}>{cap}</span>}</div>
)

function Placement({ p, month }) {
  const cols = 'minmax(0,1fr) 50px 64px 120px'
  return (
    <div style={{ ...CARD, gap: 12 }}>
      {head('Деньги в размещении', `${month} · ${p.deals} сделок`)}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={BIG}>{m1(p.total)}</span><span style={UNIT}>млн ₽</span></div>
      {p.delivered_pct != null && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: 'var(--text-secondary)' }}>
            <span>открутилось <b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{p.delivered_pct} %</b> · {m1(p.delivered)} млн</span>
            {/* РК всегда за прошлый день: статистика за дату среза, загружена на следующий */}
            {!!p.as_of && <span style={{ color: 'var(--text-muted)' }}>статистика РК за {dm(p.as_of)} · загружена {dm(nextDay(p.as_of))}</span>}
          </span>
          <div style={{ height: 8, borderRadius: 4, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', overflow: 'hidden' }}>
            <div style={{ width: `${Math.min(100, p.delivered_pct)}%`, height: '100%', background: 'var(--hot)' }} /></div>
        </div>
      )}
      {p.at_risk > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 12, background: 'var(--attn-tint)', border: '1px solid var(--attn-border)' }}
          title="Прогноз открутки к концу флайта ниже 97 % плана показов — тем же правилом, что дашборд трафика и вердикт итоговой сверки">
          <span style={{ ...CAPS, color: 'var(--attn-fg)' }}>под риском</span>
          <span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: 'var(--attn-fg)' }}>{m1(p.at_risk)} млн</span>
          <span style={{ fontSize: 12.5, color: 'var(--attn-fg)' }}>{p.at_risk_deals} сделок недокручивают по прогнозу</span>
          <Link href="/traffic/dashboard" style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--attn-fg)', whiteSpace: 'nowrap' }}>Трафик →</Link>
        </div>
      )}
      {p.no_rk > 0 && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Без плана показов в РК — {p.no_rk} сделок: их открутку не видно</span>}
      <div style={{ display: 'flex', flexDirection: 'column', paddingTop: 6, borderTop: '1px solid var(--border-inner)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, padding: '4px 0 6px' }}>
          <span style={CAPS}>услуга</span><span style={{ ...CAPS, textAlign: 'right' }}>сделок</span><span style={{ ...CAPS, textAlign: 'right' }}>млн</span><span style={CAPS}>доля</span></div>
        {p.by_service.map(([s, v, n]) => (
          <div key={s} style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, alignItems: 'center', height: 28, borderTop: '1px solid var(--border-row)', fontSize: 13 }}>
            <span style={{ color: s === 'без услуги' ? 'var(--attn-fg)' : 'var(--text-primary)' }}>{s}</span>
            <span style={{ fontFamily: MONO, textAlign: 'right', color: 'var(--text-muted)' }}>{n}</span>
            <span style={{ fontFamily: MONO, textAlign: 'right', fontWeight: 700 }}>{m1(v)}</span>
            <span style={{ height: 6, borderRadius: 3, background: 'var(--bg-subtle)', overflow: 'hidden' }}>
              <span style={{ display: 'block', width: `${p.total ? (v / p.total * 100).toFixed(1) : 0}%`, height: '100%', background: 'var(--ok)' }} /></span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Forecast({ months }) {
  const F = months.filter(m => m.role !== 'past').slice(0, 3)
  const rel = F.reduce((a, m) => a + sure(m), 0), lik = F.reduce((a, m) => a + likely(m), 0)
  const prev = F.reduce((a, m) => a + (m.ly || 0), 0), low = F.reduce((a, m) => a + m.low, 0)
  const plan = F.every(m => m.plan != null) ? F.reduce((a, m) => a + m.plan, 0) : null
  const rows = [['Надёжно', rel, 'документы + в работе', 'var(--money)'], ['С вероятными', lik, '+ брони и средняя вероятность из разметки продаж', 'var(--attn)']]
  const w = (a, b) => `${b ? Math.min(100, a / b * 100).toFixed(1) : 0}%`
  return (
    <div data-tone="dark" style={{ ...CARD, gap: 14 }}>
      {head(`Прогноз · ${F.map(m => m.name.toLowerCase().slice(0, 3)).join(' — ')}`, 'к прошлому году')}
      {rows.map(([name, v, s, c]) => {
        const d = vs(v, prev)
        return (
          <div key={name} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto 64px', gap: '4px 14px', alignItems: 'baseline' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 700 }}><span style={{ width: 9, height: 9, borderRadius: 2, background: c }} />{name}</span>
            <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em', textAlign: 'right' }}>{m1(v)}</span>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right', color: d == null ? 'var(--text-muted)' : d < 0 ? 'var(--bad-fg)' : 'var(--money-fg)' }}>{pc(d)}</span>
            <span style={{ gridColumn: 'span 3', fontSize: 12, color: 'var(--text-muted)', paddingLeft: 17 }}>{s}</span>
          </div>
        )
      })}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={CAPS}>прошлый год, те же месяцы</span><span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700 }}>{m1(prev)} млн</span></span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={CAPS}>цель «плана продаж»</span>
          {plan != null ? <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700 }}>{m1(plan)} млн · {pc(vs(lik, plan))}</span>
            : <Link href="/sales/plan" style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>цели не заданы · задать →</Link>}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 12 }}>
        {F.map(m => (
          <div key={m.key} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px', borderRadius: 12, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
            <span style={CAPS}>{m.name}</span>
            <div style={{ height: 8, borderRadius: 4, background: 'var(--bg-card)', position: 'relative', overflow: 'hidden' }}>
              <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: w(likely(m), m.ly), background: 'var(--attn)' }} />
              <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: w(sure(m), m.ly), background: 'var(--money)' }} />
            </div>
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}><b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{m1(likely(m))}</b> из {m1(m.ly)} пр. года</span>
          </div>
        ))}
      </div>
      <span style={{ marginTop: 'auto', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>Низкая вероятность в прогноз не входит: {m1(low)} млн — на светофоре бледным. Полоса — доля прошлого года, которую уже закрывают надёжные и вероятные сделки.</span>
    </div>
  )
}

function Unbilled({ u }) {
  const months = [...new Set(u.rows.map(r => r.month))]
  const worst = u.rows.filter(r => r.days != null).sort((a, b) => b.days - a.days)[0]
  const chip = (d) => (d > 10 ? ['var(--bad-tint)', 'var(--bad-border)', 'var(--bad-fg)'] : ['var(--attn-tint)', 'var(--attn-border)', 'var(--attn-fg)'])
  return (
    <div style={{ ...CARD, gap: 10, minHeight: 0 }}>
      {head('Сделано, а счёта нет', `${months.length === 1 ? months[0] : 'закрытые месяцы'} · ${u.rows.length} сделок`)}
      <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>Месяц закрыт, сделка подкреплена документами, а 1С ещё не дала счёт по её комплекту.</span>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={{ ...BIG, color: u.total ? 'var(--bad-fg)' : 'var(--text-primary)' }}>{m1(u.total)}</span><span style={UNIT}>млн ₽</span>
        {worst && <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>дольше всех — <b style={{ color: 'var(--text-primary)' }}>{worst.code}, {worst.days} дн</b></span>}</div>
      <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 300, overflowY: 'auto', borderTop: '1px solid var(--border-inner)' }}>
        {u.rows.map(r => {
          const [bg, bd, fg] = chip(r.days)
          const what = r.package ? `${r.month} · ${r.package} · ${r.package_status}${r.since ? ` с ${dm(r.since)}` : ''}` : `${r.month} · есть в сверке · пакет не найден`
          return (
            <div key={r.code} style={{ display: 'grid', gridTemplateColumns: '76px minmax(0,1fr) auto', gap: '2px 12px', alignItems: 'center', padding: '9px 0', borderBottom: '1px solid var(--border-row)' }}>
              <Link href={`/sales/deals/${r.code}`} style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)' }}>{r.code}</Link>
              <span title={what} style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{what}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
                <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>{f(r.amount)}</span>
                {r.days != null && <span style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 6px', borderRadius: 5, background: bg, border: `1px solid ${bd}`,
                  fontFamily: MONO, fontSize: 10, fontWeight: 700, color: fg, whiteSpace: 'nowrap' }}>{r.days} дн</span>}
              </span>
            </div>
          )
        })}
        {!u.rows.length && <span style={{ padding: '9px 0', fontSize: 12.5, color: 'var(--text-muted)' }}>Всё выставлено.</span>}
      </div>
      <span style={{ marginTop: 'auto', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        {u.outside.deals > 0 ? `Вне пакетов закрытия — ещё ${u.outside.deals} сделок на ${m1(u.outside.total)} млн: закрывались вне системы, про их счёт она не знает. ` : ''}Коралловым — дольше 10 дней.</span>
      <Link href="/finance/master-deals" style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>Пакеты закрытия →</Link>
    </div>
  )
}

const STEP = { no_bill: 'Счёта ещё нет', diff: 'Сумма сделки ≠ счёт', outside: 'Выручка вне сделок месяца' }
const sgn = (v) => (v ? `${v > 0 ? '+' : '−'}${m1(Math.abs(v))}` : '0')

function Recon({ r }) {
  const st = Object.fromEntries(r.steps.map(s => [s.key, s.v]))
  const rows = [
    ['Подкреплено документами', m1(r.from), 800, 'var(--text-primary)', '', 'var(--border-inner)'],
    ...r.steps.map(s => [STEP[s.key], sgn(s.v), 500, s.v ? 'var(--bad-fg)' : 'var(--text-muted)',
      s.items.map(i => `${i.code} ${i.v > 0 ? '+' : '−'}${f(Math.abs(i.v))}`).join(' · '), 'var(--border-row)']),
    ['Выручка в учёте', m1(r.to), 800, 'var(--text-primary)', '', 'var(--border-inner)'],
  ]
  const note = !st.diff && !st.outside ? (st.no_bill ? 'Разница сходится: всё, что не попало в учёт, — сделки без счёта. Расхождения сумм и выручки вне сделок — ноль.'
    : 'Сходится полностью: всё подкреплённое документами — в учёте.') : 'Разница — счета без сделок месяца или суммы, разошедшиеся со сделкой: строки выше.'
  return (
    <div style={{ ...CARD, gap: 4 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, paddingBottom: 6 }}><span style={H}>Сверка с учётом · {r.month}</span><span style={{ ...CAPS, marginLeft: 'auto' }}>светофор → бухгалтерия · млн</span></div>
      {rows.map(([k, v, w, fg, s, bd]) => (
        <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '10px 0', borderTop: `1px solid ${bd}` }}>
          <span style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}><span style={{ fontSize: 13.5, fontWeight: w }}>{k}</span><span style={{ fontFamily: MONO, fontSize: 14, fontWeight: w, color: fg }}>{v}</span></span>
          {!!s && <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>{s}</span>}
        </div>
      ))}
      <span style={{ marginTop: 'auto', paddingTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>{note}</span>
    </div>
  )
}

const MONTH_GEN = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

function Margin({ mg }) {
  const cols = 'minmax(0,1fr) 70px 80px 80px 70px 190px'
  const ks = mg.months
  const period = ks.length ? `${MONTH_GEN[+ks[0].slice(5) - 1]} — ${MONTH_GEN[+ks[ks.length - 1].slice(5) - 1]} ${ks[ks.length - 1].slice(0, 4)}` : ''
  return (
    <div style={{ ...CARD, gap: 4 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, paddingBottom: 6 }}><span style={H}>Маржа по услугам</span><span style={{ ...CAPS, marginLeft: 'auto' }}>итоговые сверки · {period} · млн</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, padding: '4px 0 8px', borderBottom: '1px solid var(--border-inner)' }}>
        <span style={CAPS}>услуга</span><span style={{ ...CAPS, textAlign: 'right' }}>сделок</span><span style={{ ...CAPS, textAlign: 'right' }}>выручка</span>
        <span style={{ ...CAPS, textAlign: 'right' }}>площадки</span><span style={{ ...CAPS, textAlign: 'right' }}>ск пост.</span><span style={CAPS}>маржа</span></div>
      {mg.rows.map(r => {
        const m = r.margin_pct
        return (
          <div key={r.service} style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, alignItems: 'center', height: 42, borderBottom: '1px solid var(--border-row)', fontSize: 13 }}>
            <span style={{ fontWeight: 700 }}>{r.service}</span>
            <span title={`с себестоимостью / всего${r.estimated ? ` · оценкой по показам — ${r.estimated}` : ''}`} style={{ fontFamily: MONO, textAlign: 'right', color: 'var(--text-muted)' }}>{r.with_cost}/{r.deals}</span>
            <span style={{ fontFamily: MONO, textAlign: 'right', fontWeight: 700 }}>{m1(r.revenue)}</span>
            <span style={{ fontFamily: MONO, textAlign: 'right' }}>{r.cost == null ? '—' : m1(r.cost)}</span>
            <span style={{ fontFamily: MONO, textAlign: 'right' }}>{m1(r.sk_cost)}</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {m != null && m >= 0 && <span style={{ flex: '1 1 auto', height: 6, borderRadius: 3, background: 'var(--bg-subtle)', overflow: 'hidden' }}>
                <span style={{ display: 'block', width: `${Math.min(100, m)}%`, height: '100%', background: 'var(--money)' }} /></span>}
              <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', marginLeft: 'auto', color: m == null ? 'var(--text-muted)' : m < 0 ? 'var(--bad-fg)' : 'var(--text-primary)' }}>
                {m == null ? 'нет себестоимости' : pc(m).replace('+', '')}</span>
            </span>
          </div>
        )
      })}
      <span style={{ marginTop: 'auto', paddingTop: 10, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>Прямая маржа: выручка за вычетом площадок и СК постоплатой, от суммы ДС до СК. Только сделки с себестоимостью (введённой или оценкой по показам). Постоянные расходы по услугам — после схемы учёта расходов.</span>
    </div>
  )
}

const IDEAS = [
  ['Точность светофора', 'новое', 'Какая доля «средней вероятности» прошлых месяцев стала сделкой, а какая сорвалась. С этим коэффициентом «с вероятными» станет взвешенным прогнозом, а не суммой.', 'история слоёв светофора + «не случились» по месяцам'],
  ['Клиенты прошлого года без сделок', 'новое', 'Кто давал выручку в эти месяцы прошлого года, а сейчас без сделок и планов. Это и есть провал прогноза к прошлому году, по именам.', 'сделки прошлого года × светофор'],
  ['Продажи по менеджерам', 'новое', 'Надёжно / вероятно / низкая по каждому менеджеру на 3 месяца и разметка планов: у кого планы не обновлялись больше 2 недель.', 'автор плана в разметке продаж'],
  ['Недокрут в деньгах', 'новое', 'Сколько выручки месяца уйдёт из-за недокрута: что из «под риском» можно докрутить до конца флайта, что перенести.', 'прогноз открутки по РК'],
  ['Запас прочности', 'предложение', 'Сколько месяцев проживём на деньгах на счетах при текущих постоянных расходах; точка безубыточности по марже.', 'после схемы учёта расходов'],
  ['Свободные деньги', 'предложение', 'Остаток минус долг площадкам по сверкам, СК постоплатой, агентствам и налоги — что реально наше.', 'сверки + обязательства'],
  ['Зависимость от клиентов', 'предложение', 'Доля пяти крупнейших в выручке; клиенты прошлого года без сделок на эти месяцы — ранний отток.', 'выручка по клиентам'],
  ['Скорость денег', 'предложение', 'Дни от конца флайта до счёта и от счёта до оплаты; где застревает закрытие. На «Деньгах» уже есть в «Пути денег».', 'пакеты закрытия + оплаты'],
]

function Ideas() {
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, paddingTop: 4 }}><span style={H}>Что ещё сюда вынести</span><span style={CAPS}>предложения · данные в системе есть или почти есть</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 16 }}>
        {IDEAS.map(([t, tag, s, src]) => {
          const nw = tag === 'новое'
          return (
            <div key={t} style={{ border: '1.5px dashed var(--border-hover)', borderRadius: 20, background: 'transparent', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 14, fontWeight: 800 }}>{t}</span>
                <span style={{ height: 18, display: 'inline-flex', alignItems: 'center', padding: '0 6px', borderRadius: 5, border: `1px solid ${nw ? 'var(--accent-border)' : 'var(--border-inner)'}`,
                  background: nw ? 'var(--accent-tint)' : 'var(--bg-subtle)', fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                  color: nw ? 'var(--accent-fg)' : 'var(--text-muted)' }}>{tag}</span></span>
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{s}</span>
              <span style={{ marginTop: 'auto', fontSize: 11.5, color: 'var(--text-muted)' }}>{src}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

/** Данные вкладки — и для «Пути денег» на «Деньгах» (первые два шага берутся отсюда, цифры совпадают). */
export function useBusiness() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const load = useCallback(async () => {
    setErr('')
    try { setData((await api.get('/money/business', auth())).data) } catch (e) {
      setErr(e?.response?.status === 403 ? 'Экран доступен только администратору.' : 'Не удалось посчитать «Бизнес». Обновите страницу.')
    }
  }, [])
  useRefreshOnReturn(() => load())
  useEffect(() => { load() }, [load])
  return { data, err }
}

export default function Business({ tabs, biz }) {
  const { data, err } = biz
  const now = data?.months.find(m => m.role === 'now')
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        {tabs}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>Бизнес</span>
          <span style={{ ...CAPS, fontSize: 11 }}>продано и в работе по месяцам · без НДС, за вычетом скидки в счёт · млн ₽</span>
        </div>
      </div>
      {!!err && <div style={{ padding: '14px 18px', borderRadius: 14, background: 'var(--bad-tint)', border: '1px solid var(--bad-border)', color: 'var(--bad-fg)' }}>{err}</div>}
      {!data && !err && <div style={{ ...CARD, color: 'var(--text-muted)' }}>Считаю…</div>}
      {data && <>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr) minmax(0,1fr)', gap: 16 }}>
          <Placement p={data.placement} month={now?.name.toLowerCase()} /><Forecast months={data.months} /><Unbilled u={data.unbilled} />
        </div>
        <Lights months={data.months} />
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.3fr)', gap: 16 }}>
          <Recon r={data.recon} /><Margin mg={data.margin} />
        </div>
        <Ideas />
      </>}
    </>
  )
}
