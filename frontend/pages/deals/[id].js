import { useState, useEffect, useMemo } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '../../lib/api'
import { MONO, UI, HATCH_RED } from '../../components/salesTableKit'
import { BITRIX_DEAL_URL } from '../../lib/salesLayers'
import MoveDealDialog from '../../components/sales/MoveDealDialog'
import { DEAL_DOCS, downloadBlob, pickAndUploadDoc, deleteDoc } from '../../lib/dealDocs'

// ── Карточка сделки /deals/[id] ──
// Дизайн строго по хендоффу docs/карточка сделки (design_handoff_deal_card): токены
// нашей дизайн-системы (var(--*)), шрифты Manrope/JetBrains Mono.
// Данные живые: размещение/прогноз/доп/таргетинг — из ПОСЛЕДНЕГО медиаплана сделки,
// документы — реальные файлы (загрузка/замена/удаление), история — audit_log,
// бар стадий — каталог стадий + движение через MoveDealDialog (как в реестре).
// Заглушка осталась одна: оплачено/остаток/срок оплаты — привязки платежей к сделке ещё нет.

const VAT = 0.22
const rub = (v) => (v == null ? '—' : v.toLocaleString('ru-RU') + ' ₽')
const num = (v) => (v == null ? '—' : v.toLocaleString('ru-RU'))
const dec = (v) => v.toFixed(2).replace('.', ',')
const initials = (name) => (name ? name.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase() : '—')

// время события в московском времени (UTC+3), как в Журнале действий
const fmtWhen = (str) => {
  if (!str) return ''
  const s = /[zZ]|[+-]\d{2}:?\d{2}$/.test(str) ? str : str + 'Z'
  return new Date(s).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}
// Светофор слоёв денег — как в реестре/диалоге движения (единая трактовка цвета).
const LAYER_COLOR = {
  'планируемые': 'var(--text-faint, #A3ABBD)',
  'реализуемые': 'var(--dot-current-dz, #d97706)',
  'фактические': 'var(--income, #1F7D5E)',
}
const EVENT_COLOR = {
  create_deal: 'var(--text-faint)', patch_sales_deal: 'var(--dot-current-dz)',
  save_deal_brief: 'var(--income)', push_deal_to_bitrix: 'var(--accent)', sync_deal_from_bitrix: 'var(--accent)',
}

const MP_STATUS = { draft: 'черновик', review: 'на согласовании', approved: 'согласован', rejected: 'отклонён', archived: 'архив' }
// Список видов документов — общий для карточки, раскрывашки и доски (lib/dealDocs).
const DOC_KINDS = DEAL_DOCS.map(d => [d.kind, d.label, !!d.bx])
const DOC_ACT = { display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 7px', border: '1px solid var(--border-card)', borderRadius: 7, background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 10, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }

// Строка документа
function DocRow({ ok, title, meta, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, background: ok ? 'var(--bg-card)' : '#FBFCFE', border: `1px solid ${ok ? 'var(--border-card)' : 'var(--border-inner)'}`, borderRadius: 11, padding: '9px 10px', minWidth: 0 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 7, background: ok ? 'var(--accent-tint)' : 'var(--bg-subtle)', color: ok ? 'var(--accent)' : '#C3C9D8', flex: '0 0 22px' }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0, flex: 1 }}>
        <span style={{ fontSize: 11.5, fontWeight: 700, color: ok ? 'var(--text-primary)' : 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
        <span title={meta} style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{meta}</span>
      </span>
      {right}
    </div>
  )
}

// стилевые примитивы карточки (из эталона)
const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }
const CAPS = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const SUBCAPS = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }
const MONEY_LBL = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const PL_GRID = '1.8fr 0.9fr 0.6fr 1fr 0.9fr 0.7fr 1.2fr 1.2fr'
const FC_GRID = '2.4fr repeat(8,1fr)'

export default function DealCard() {
  const router = useRouter()
  const { id } = router.query
  const [deal, setDeal] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [phases, setPhases] = useState([])      // каталог стадий — для бара цепочки
  const [mp, setMp] = useState(null)            // последний медиаплан сделки (полные данные)
  const [moveOpen, setMoveOpen] = useState(false)
  const [docBusy, setDocBusy] = useState('')    // kind документа в процессе загрузки/удаления
  const [canEdit, setCanEdit] = useState(false)

  const reload = () => {
    api.get(`/sales/deals/${id}`, auth()).then(r => setDeal(r.data)).catch(() => {})
    api.get(`/sales/deals/${id}/history`, auth()).then(r => setHistory(r.data.items || [])).catch(() => {})
  }

  useEffect(() => {
    if (typeof window === 'undefined' || !id) return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try {
      const p = JSON.parse(localStorage.getItem('permissions') || '{}')
      setCanEdit(localStorage.getItem('is_admin') === 'true' || !!(p.sales_registry || {}).edit)
    } catch { setCanEdit(false) }
    setLoading(true)
    api.get(`/sales/deals/${id}`, auth())
      .then(r => setDeal(r.data))
      .catch(e => setErr(e.response?.status === 404 ? 'Сделка не найдена' : (e.response?.data?.detail || 'Ошибка загрузки')))
      .finally(() => setLoading(false))
    api.get(`/sales/deals/${id}/history`, auth()).then(r => setHistory(r.data.items || [])).catch(() => {})
    api.get('/sales/directories/stage-catalog', auth()).then(r => setPhases(r.data.phases || [])).catch(() => {})
  }, [id])

  // Последний медиаплан сделки: берём свежий по версии и тянем полные данные
  // (строки/доп/таргетинг) — параметры кампании и размещение показываем из него.
  useEffect(() => {
    const list = (deal && deal.our_mps) || []
    if (!list.length) { setMp(null); return }
    const last = [...list].sort((a, b) => (b.version || 0) - (a.version || 0))[0]
    api.get(`/sales/media-plans/${last.id}`, auth())
      .then(r => setMp({ ...r.data, _head: last }))
      .catch(() => setMp(null))
  }, [deal && deal.our_mps && deal.our_mps.map(x => x.id).join(',')])

  // Данные размещения/прогноза/доп/таргетинга — из ПОСЛЕДНЕГО медиаплана сделки.
  // Формула строки повторяет бэкенд (_row_net): CPM — за 1000, иначе объём × цена.
  const mpRows = (mp && mp.rows) || []
  const hasMp = mpRows.length > 0
  const lines = mpRows.map(r => {
    const div = (r.model || '') === 'CPM' ? 1000 : 1
    const net = Math.round((r.volume || 0) * (r.unit_price || 0) * (1 - (r.discount || 0)) / div)
    const fc = r.forecast || {}
    const nn = (x) => { const v = parseFloat(String(x ?? '').replace(',', '.')); return Number.isFinite(v) ? v : 0 }
    const imp = r.volume || 0
    const freq = nn(fc.freq)
    const reach = freq > 0 ? imp / freq : 0
    const clicks = imp * (nn(fc.ctr) / 100)
    return {
      position: r.position, format: r.format, model: r.model, volume: imp,
      unit: r.unit_price || 0, discount: r.discount || 0,
      net, gross: Math.round(net * (1 + VAT)), freq, reach, clicks,
    }
  })
  const tVol = lines.reduce((a, r) => a + r.volume, 0)
  const tNet = lines.reduce((a, r) => a + r.net, 0)
  const mpExtras = (mp && mp.extras) || []
  const extrasTotal = mpExtras.reduce((a, e) => a + (e.total || 0), 0)
  const MODE_LBL = { full: '100 %', half: '50 %', bonus: 'бонус' }
  // Таргетинг МП: {группа: [значения]} → плоские строки для вывода
  const TG_TITLES = { audience: 'Аудитория', buys: 'Покупают', interests: 'Интересы', behavior: 'Поведение', competitors: 'Конкуренты' }
  const mpTargeting = Object.entries((mp && mp.targeting) || {})
    .map(([g, arr]) => ({ group: TG_TITLES[g] || g, value: (arr || []).map(v => (typeof v === 'string' ? v : v && v.value)).filter(Boolean).join(' · ') }))
    .filter(x => x.value)

  const wrap = { minHeight: '100vh', boxSizing: 'border-box', padding: '26px 32px 40px', background: 'var(--bg-canvas)', display: 'flex', justifyContent: 'center', fontFamily: UI, color: 'var(--text-primary)' }

  if (loading) return <div style={wrap}><div style={{ color: 'var(--text-muted)', marginTop: 40 }}>Загрузка…</div></div>
  if (err) return <div style={wrap}><div style={{ marginTop: 40 }}><div style={{ color: 'var(--danger)', marginBottom: 12 }}>{err}</div><a href="/sales" style={{ color: 'var(--accent)' }}>← к реестру сделок</a></div></div>

  const d = deal
  const title = [d.advertiser, d.brand].filter(Boolean).join(' · ') || d.title || '—'
  const meta = [d.agency, d.product, d.period, d.account_manager && `аккаунт ${d.account_manager}`, d.sales_rep && `продавец ${d.sales_rep}`].filter(Boolean).join(' · ')
  const dateVal = (x) => (x ? String(x).slice(0, 10) : '')

  // Цепочка стадий = все нетерминальные стадии каталога по порядку этапов.
  // Терминалы («не случилась» / «сорвалась») в цепочку не входят — они её обрывают.
  const chain = phases.flatMap(ph => (ph.stages || [])
    .filter(s => !s.is_terminal)
    .map(s => ({ ...s, phaseName: ph.name })))
  const curIdx = chain.findIndex(s => s.id === (d.our_stage && d.our_stage.id))
  const isLost = !!(d.our_stage && d.our_stage.is_terminal)

  // Деньги сделки. ИСТОЧНИК ИСТИНЫ — прикреплённый медиаплан: там актуальные строки
  // и доп. услуги (бонусная доп. услуга = 0, поэтому сумма сделки, посчитанная при
  // создании, может расходиться). Нет МП — показываем сумму, введённую при создании.
  // Формула итога повторяет конструктор МП: размещения + доп. услуги (grandNet).
  const netFromMp = hasMp ? tNet + extrasTotal : null
  const net = netFromMp != null ? netFromMp : (d.amount != null ? Math.round(d.amount) : null)
  const gross = netFromMp != null
    ? Math.round(netFromMp * (1 + VAT))
    : (d.amount_with_vat != null ? Math.round(d.amount_with_vat)
      : (d.amount != null ? Math.round(d.amount * (1 + VAT)) : null))

  // Документы: карта по виду + счётчик готовых (МП считаем отдельной позицией)
  const fileBy = Object.fromEntries((d.files || []).map(f => [f.kind, f]))
  const docsReady = DOC_KINDS.filter(([k]) => fileBy[k]).length + (mp ? 1 : 0)

  // скачивание/загрузка/удаление документов — общие хелперы (lib/dealDocs)
  const blobGet = downloadBlob
  const pickAndUpload = (kind) => pickAndUploadDoc(d.id, kind, reload, setDocBusy)
  const removeDoc = (kind) => deleteDoc(d.id, kind, reload, setDocBusy)

  const params = [
    ['Агентство', d.agency], ['Рекламодатель', d.advertiser], ['Бренд', d.brand],
    ['Контрагент', d.payer], ['Период размещения', d.period ? `месяц · ${d.period}` : '—'], ['Гео', '—'],
  ]
  const team = [
    { name: d.sales_rep, role: 'Продавец', bg: 'var(--accent-tint)', fg: 'var(--accent)' },
    { name: d.account_manager, role: 'Аккаунт', bg: '#E6F5EF', fg: 'var(--income)' },
    { name: null, role: 'Трафик', bg: '#F1EDFC', fg: '#7B62D6' },
  ]
  const links = [
    { name: `Контрагент ${d.payer || ''}`.trim(), href: d.counterparty_id ? `/counterparty/${d.counterparty_id}` : null, dot: 'var(--accent)' },
    { name: 'Медиаплан', href: null, dot: 'var(--income)' },
    { name: 'Сделка в Битриксе', href: (d.bitrix_id && !String(d.bitrix_id).startsWith('local-')) ? BITRIX_DEAL_URL(d.bitrix_id) : null, dot: '#8B7BE8' },
    { name: `Дебиторка ${rub(d.amount)}`, href: '/receivables', dot: 'var(--dot-current-dz)' },
  ]

  return (
    <>
      <Head><title>{title} · сделка {d.code || d.bitrix_id || d.id}</title></Head>
      {moveOpen && (
        <MoveDealDialog deal={d} onClose={() => setMoveOpen(false)}
          onMoved={(patch) => { setMoveOpen(false); setDeal(x => ({ ...x, ...patch })); reload() }} />
      )}
      <div style={wrap}>
        <div style={{ width: '100%', maxWidth: 1120, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* назад */}
          <a href="/sales" style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>← к реестру сделок</a>

          {/* ── Шапка ── */}
          <div style={{ ...CARD, padding: '22px 26px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
                <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9 }}>
                  <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>{d.code || d.bitrix_id || d.id}</span>
                  <span style={{ fontSize: 21, fontWeight: 700, letterSpacing: '-0.02em' }}>{title}</span>
                </span>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{meta || '—'}</span>
              </span>
              {d.bitrix_stage && (
                <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--warning-tint)', color: '#B26A0C', borderRadius: 10, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--warning)' }} />{d.bitrix_stage}
                </span>
              )}
            </div>


            {/* Шапка денег: слева всегда суммы, справа — плашка годового плана.
                Две зоны, чтобы плашка не «уезжала» под суммы при их количестве. */}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 20, paddingTop: 2, flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 420px', minWidth: 0, display: 'flex', alignItems: 'flex-end', gap: 26, flexWrap: 'wrap' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>Сумма сделки · с НДС · {hasMp ? 'по медиаплану' : 'при создании сделки'}</span>
                <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, whiteSpace: 'nowrap' }}>{rub(gross)}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 26, borderLeft: '1px solid var(--border-inner)' }}>
                <span style={MONEY_LBL}>Клиентская цена до НДС</span>
                <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{rub(net)}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>НДС {Math.round(VAT * 100)} %</span>
                <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                  {gross != null && net != null ? rub(Math.round(gross - net)) : '—'}
                </span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>Срок оплаты</span>
                <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--text-faint)' }}>—</span>
              </span>
            </div>
              {/* Материнский годовой план — правая зона шапки */}
              {d.year_plan && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto', maxWidth: 420, minWidth: 0, background: 'var(--bg-subtle, #F6F8FF)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '8px 12px' }}>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontFamily: MONO, fontSize: 9, letterSpacing: '.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Годовой план</span>
                    <span style={{ display: 'block', fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={[d.year_plan.title, d.year_plan.comment].filter(Boolean).join(' · ')}>
                      {d.year_plan.title || `План ${d.year_plan.year || ''}`}
                      {d.year_plan.comment ? <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}> · {d.year_plan.comment}</span> : null}
                      {d.year_plan.month != null ? <span style={{ fontFamily: MONO, fontWeight: 600, color: 'var(--text-faint)' }}> · мес. {d.year_plan.month + 1}</span> : null}
                    </span>
                  </span>
                  <a href={`/deals/year-plan?year=${d.year_plan.year}${d.year_plan.rep_id ? `&rep=${d.year_plan.rep_id}` : ''}`}
                    title="Открыть годовой план"
                    style={{ display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 11px', borderRadius: 8, background: 'var(--accent-tint)', border: '1px solid var(--accent)', color: 'var(--accent)', fontSize: 11.5, fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap', flex: '0 0 auto' }}>
                    План →
                  </a>
                </span>
              )}
            </div>

            {/* ── Бар стадий: вся цепочка каталога, цвет ячейки — по слою денег стадии.
                   Текущая подписана полным названием и растянута; прошедшие — в цвете,
                   будущие — приглушённые. Терминал (не случилась / сорвалась) — красный штрих. */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              {isLost ? (
                <span title={d.our_stage?.name || 'Сделка провалена'}
                  style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', height: 30, borderRadius: 8, background: HATCH_RED, border: '1px solid var(--danger)' }}>
                  <span style={{ fontSize: 11.5, fontWeight: 800, color: 'var(--danger)', letterSpacing: '.02em', background: 'var(--bg-card)', padding: '1px 10px', borderRadius: 6 }}>
                    {d.our_stage?.name || 'Сделка провалена'}
                  </span>
                </span>
              ) : (
                <span style={{ flex: 1, minWidth: 0, display: 'flex', gap: 3, alignItems: 'stretch' }}>
                  {chain.length === 0 && <span style={{ flex: 1, height: 30, borderRadius: 8, background: 'var(--border-inner)' }} />}
                  {chain.map((s, i) => {
                    const cur = curIdx >= 0 && i === curIdx
                    const past = curIdx >= 0 && i < curIdx
                    const col = LAYER_COLOR[s.money_layer] || 'var(--border-inner)'
                    return (
                      <span key={s.id} title={`${s.name}${s.phaseName ? ' · ' + s.phaseName : ''}`}
                        style={{
                          flex: cur ? '1 1 auto' : '0 1 26px', minWidth: cur ? 0 : 10, height: 30,
                          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: cur ? '0 12px' : 0,
                          borderRadius: 8, background: (cur || past) ? col : 'var(--border-inner)',
                          opacity: (cur || past) ? 1 : 0.5,
                          transition: 'flex .25s cubic-bezier(0.22,1,0.36,1)',
                        }}>
                        {cur && (
                          <span style={{ fontSize: 11.5, fontWeight: 800, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.name}</span>
                        )}
                      </span>
                    )
                  })}
                </span>
              )}
              {canEdit && (
                <button onClick={() => setMoveOpen(true)} title="Двинуть сделку по каталогу стадий"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 13px', borderRadius: 9, border: 'none', background: 'var(--income, #1F7D5E)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap', flex: '0 0 auto', fontFamily: UI }}>
                  Изменить стадию
                </button>
              )}
            </div>
          </div>

          {/* ── Две колонки ── */}
          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }}>

            {/* левая: медиаплан */}
            <div style={{ flex: 1, minWidth: 320, ...CARD, padding: '22px 26px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>

              {/* параметры кампании */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Параметры кампании</span>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={SUBCAPS}>Старт — стоп РК</span>
                    <input type="date" defaultValue={dateVal(d.period_from)} readOnly style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: MONO, fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', outline: 'none' }} />
                    <span style={{ color: '#C7D0E8' }}>→</span>
                    <input type="date" defaultValue={dateVal(d.period_to)} readOnly style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: MONO, fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', outline: 'none' }} />
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: 'repeat(3,auto)', gridAutoFlow: 'column', gap: '0 28px' }}>
                  {params.map(([label, value], i) => (
                    <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 600, textAlign: 'right', color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>{value || '—'}</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Медиаплана нет — вся зона медиаплана становится кнопкой создания.
                  Есть МП — обычный блок размещения из его строк. */}
              {!mp ? (
                <div onClick={canEdit ? () => router.push(`/deals/mp/new?deal=${d.id}`) : undefined}
                  title={canEdit ? 'Создать медиаплан — реквизиты и бриф подставятся из сделки' : 'Медиаплана нет'}
                  style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6,
                    minHeight: 150, padding: '28px 20px', marginTop: 14, borderRadius: 14,
                    background: canEdit ? 'var(--accent)' : 'var(--bg-subtle)',
                    color: canEdit ? '#fff' : 'var(--text-faint)',
                    border: canEdit ? 'none' : '1px dashed var(--border-card)',
                    cursor: canEdit ? 'pointer' : 'default', textAlign: 'center',
                  }}>
                  {canEdit && (
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14" /></svg>
                  )}
                  <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}>
                    {canEdit ? 'Создать медиаплан' : 'Медиаплана нет'}
                  </span>
                  <span style={{ fontSize: 12, opacity: canEdit ? 0.85 : 1 }}>
                    {canEdit
                      ? 'Рекламодатель, бренд, агентство, юрлицо и период подставятся из сделки'
                      : 'Размещение и прогноз появятся, когда его создадут'}
                  </span>
                </div>
              ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7, padding: '14px 0', borderTop: '1px solid var(--border-card)', borderBottom: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Размещение</span>
                  <span style={SUBCAPS}>
                    {mp.title || 'медиаплан'} · v{mp.version} · {MP_STATUS[mp.status] || mp.status}
                    {mp.geo ? ` · ${mp.geo}` : ''}{mp.period ? ` · ${mp.period}` : ''}
                  </span>
                  <a href={`/deals/mp/${mp.id}`} style={{ marginLeft: 'auto', fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none', whiteSpace: 'nowrap' }}>Открыть МП →</a>
                </div>
                {!hasMp && <div style={{ fontSize: 12, color: 'var(--text-faint)', padding: '6px 0' }}>В медиаплане пока нет строк размещения.</div>}
                {hasMp && (
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ minWidth: 640 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                      <span>Позиция</span><span>Формат</span><span>Модель</span><span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Цена/ед.</span><span style={{ textAlign: 'right' }}>Скидка</span><span style={{ textAlign: 'right' }}>До НДС</span><span style={{ textAlign: 'right' }}>С НДС</span>
                    </div>
                    {lines.map((l, i) => (
                      <div key={i} style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                        <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25 }}>{l.position}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{l.format}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>{l.model}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>{num(l.volume)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{dec(l.unit)} ₽</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textAlign: 'right' }}>{Math.round((l.discount || 0) * 100)} %</span>
                        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{rub(l.net)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{rub(l.gross)}</span>
                      </div>
                    ))}
                    <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', paddingTop: 7 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого</span>
                      <span /><span />
                      <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, textAlign: 'right' }}>{num(tVol)}</span>
                      <span /><span />
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{rub(tNet)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{rub(Math.round(tNet * (1 + VAT)))}</span>
                    </div>
                  </div>
                </div>
                )}
              </div>
              )}

              {/* прогнозные показатели — из медиаплана */}
              {hasMp && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Прогнозные показатели</span>
                  <span style={SUBCAPS}>гарантируются показы и CPM</span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ minWidth: 640 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: 9, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                      <span>Строка</span><span style={{ textAlign: 'right' }}>Частота</span><span style={{ textAlign: 'right' }}>Охват</span><span style={{ textAlign: 'right' }}>Показы</span><span style={{ textAlign: 'right' }}>CTR</span><span style={{ textAlign: 'right' }}>Клики</span><span style={{ textAlign: 'right' }}>CPM</span><span style={{ textAlign: 'right' }}>CPC</span><span style={{ textAlign: 'right' }}>CPU</span>
                    </div>
                    {lines.map((r, i) => (
                      <div key={i} style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: 9, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                        <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25 }}>{r.position}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{r.freq ? num(r.freq) : '—'}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>{r.reach ? num(Math.round(r.reach)) : '—'}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--income)', textAlign: 'right' }}>{num(r.volume)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{r.volume && r.clicks ? dec(r.clicks / r.volume * 100) + ' %' : '—'}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--income)', textAlign: 'right' }}>{r.clicks ? num(Math.round(r.clicks)) : '—'}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--accent)', textAlign: 'right' }}>{r.volume ? dec(r.net / r.volume * 1000) + ' ₽' : '—'}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--accent)', textAlign: 'right' }}>{r.clicks ? dec(r.net / r.clicks) + ' ₽' : '—'}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--accent)', textAlign: 'right' }}>{r.reach ? dec(r.net / r.reach) + ' ₽' : '—'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              )}

              {/* доп. услуги — из медиаплана */}
              {mpExtras.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
                <span style={CAPS}>Дополнительные услуги</span>
                {mpExtras.map((e, i) => (
                  <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                    <span style={{ fontSize: 11.5, fontWeight: 600 }}>{e.name || '—'}</span>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{e.period || ''}{e.mode ? ` · ${MODE_LBL[e.mode] || e.mode}` : ''}</span>
                    <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textDecoration: (e.total || 0) < (e.price || 0) ? 'line-through' : 'none' }}>{rub(e.price || 0)}</span>
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--income)', minWidth: 96, textAlign: 'right' }}>{rub(e.total || 0)}</span>
                    {/* цена с НДС — от «итого» (что в счёте), а не от прайса */}
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)', minWidth: 104, textAlign: 'right' }}>{rub(Math.round((e.total || 0) * (1 + VAT)))}</span>
                  </span>
                ))}
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 12, paddingTop: 7 }}>
                  <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого доп. услуги · входят в сумму сделки</span>
                  <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--income)' }}>{rub(extrasTotal)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--accent)', minWidth: 104, textAlign: 'right' }}>{rub(Math.round(extrasTotal * (1 + VAT)))}</span>
                </span>
              </div>
              )}

              {/* бриф · таргетинг — из медиаплана */}
              {mpTargeting.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                  <span style={CAPS}>Бриф · таргетинг</span>
                  <span style={{ marginLeft: 'auto', ...SUBCAPS }}>из медиаплана</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
                  {mpTargeting.map((t, i) => (
                    <span key={i} style={{ display: 'flex', gap: 12, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                      <span style={{ flex: '0 0 84px', fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', lineHeight: 1.45 }}>{t.group}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{t.value}</span>
                    </span>
                  ))}
                </div>
              </div>
              )}
            </div>

            {/* правая: документы / ответственные / история */}
            <div style={{ width: '25%', flex: '0 0 25%', minWidth: 260, ...CARD, padding: '20px 22px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* документы — реальные: файлы сделки + наш МП. Загрузка/замена/удаление. */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={CAPS}>Документы</span>
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, fontWeight: 700, color: 'var(--accent)' }}>{docsReady} из {DOC_KINDS.length + 1}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {/* наш медиаплан — отдельной строкой: скачать PDF/XLSX или открыть конструктор */}
                <DocRow ok={!!mp} title="Медиаплан"
                  meta={mp ? `v${mp.version} · ${MP_STATUS[mp.status] || mp.status}` : 'не создан'}
                  right={mp ? (
                    <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                      <span onClick={() => blobGet(`/media-plans/${mp.id}/pdf`, `MP_${mp.id}_v${mp.version}.pdf`)} style={DOC_ACT}>PDF</span>
                      <span onClick={() => blobGet(`/media-plans/${mp.id}/export.xlsx`, `MP_${mp.id}_v${mp.version}.xlsx`)} style={DOC_ACT}>XLS</span>
                      <a href={`/deals/mp/${mp.id}`} style={{ ...DOC_ACT, textDecoration: 'none' }}>↗</a>
                    </span>
                  ) : (canEdit ? <a href={`/deals/mp/new?deal=${d.id}`} style={{ ...DOC_ACT, textDecoration: 'none' }}>Создать</a> : null)} />

                {DOC_KINDS.map(([kind, label, fromBitrix]) => {
                  const f = fileBy[kind]
                  const busy = docBusy === kind
                  return (
                    <DocRow key={kind} ok={!!f} title={label}
                      meta={busy ? 'загрузка…' : (f ? `${f.filename}${f.size ? ' · ' + Math.max(1, Math.round(f.size / 1024)) + ' КБ' : ''}` : (fromBitrix ? 'из Битрикса — нет' : 'не загружен'))}
                      right={
                        <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                          {f && <span onClick={() => blobGet(`/sales/deals/${d.id}/files/${kind}/download`, f.filename)} style={DOC_ACT}>⭳</span>}
                          {canEdit && !fromBitrix && (
                            <span onClick={() => pickAndUpload(kind)} style={DOC_ACT}>{f ? 'Заменить' : 'Загрузить'}</span>
                          )}
                          {canEdit && !fromBitrix && f && (
                            <span onClick={() => removeDoc(kind)} title="Удалить" style={{ ...DOC_ACT, color: 'var(--danger)', borderColor: 'var(--danger)' }}>×</span>
                          )}
                        </span>
                      } />
                  )
                })}
              </div>

              {/* ответственные */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                <span style={CAPS}>Ответственные</span>
                {team.map((t, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, background: t.bg, color: t.fg, fontSize: 12, fontWeight: 700, flex: '0 0 32px' }}>{initials(t.name)}</span>
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: t.name ? 'var(--text-primary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name || '—'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{t.role}</span>
                    </span>
                  </div>
                ))}
              </div>

              {/* история (реальная — audit_log) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={CAPS}>История</span>
                  {history.length > 3 && <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{history.length} событий</span>}
                </div>
                {/* Первые 3 события видны сразу, остальные — в скролле (высота ≈ 3 строк). */}
                {history.length ? (
                  <div style={history.length > 3 ? { maxHeight: 168, overflowY: 'auto', paddingRight: 4 } : undefined}>
                    {history.map((h, i) => (
                      <div key={i} style={{ display: 'flex', gap: 9, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: EVENT_COLOR[h.action] || 'var(--text-faint)', flex: '0 0 7px', marginTop: 5 }} />
                        <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                          <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.35 }}>{h.label}{h.details ? <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}> · {h.details}</span> : ''}</span>
                          <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{fmtWhen(h.at)}{h.who ? ` · ${h.who}` : ''}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : <div style={{ fontSize: 11, color: 'var(--text-faint)', padding: '4px 0' }}>Событий в журнале пока нет.</div>}
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
                  <input placeholder="Комментарий…" disabled style={{ flex: 1, minWidth: 0, height: 30, boxSizing: 'border-box', padding: '0 10px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: UI, fontSize: 11.5, outline: 'none' }} />
                  <span title="скоро" style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 11px', background: 'var(--accent)', color: '#fff', borderRadius: 9, fontSize: 11, fontWeight: 700, opacity: 0.6 }}>→</span>
                </div>
              </div>
            </div>
          </div>

          {/* ряд ссылок */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', padding: '0 6px' }}>
            {links.map((l, i) => (
              l.href
                ? <a key={i} href={l.href} target={l.href.startsWith('http') ? '_blank' : undefined} rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}><span style={{ width: 7, height: 7, borderRadius: 2, background: l.dot }} />{l.name}</a>
                : <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600, color: 'var(--text-faint)' }}><span style={{ width: 7, height: 7, borderRadius: 2, background: l.dot }} />{l.name}</span>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
