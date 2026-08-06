import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '../../../../lib/api'
import { can } from '../../../../components/Navbar'
import MediaPlanPdf, { NOTES, AGG_RULES, BONUS_NOTE } from '../../../../components/mediaplan/MediaPlanPdf'

// Печатный предпросмотр медиаплана (A4, 1 лист). Открывается в новой вкладке из
// конструктора и из реестра. Данные — /sales/media-plans/{id}/pdf-data (гейт media_plans:view).
const fmtDate = (s) => { if (!s) return '—'; const x = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z'; return new Date(x).toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' }) }

// Таргетинг: группы конструктора → подписи PDF. Значение — массив строк/объектов.
const TG_GROUPS = [['audience', 'Аудитория'], ['buys', 'Покупают'], ['interests', 'Интересы'], ['behavior', 'Поведение'], ['competitors', 'Конкуренты']]
const tval = (v) => Array.isArray(v)
  ? v.map(x => (typeof x === 'string' ? x : (x && (x.value || x.name)) || '')).filter(Boolean).join(' · ')
  : (v || '')

function toPdf(plan) {
  const adv = plan.advertiser || '', brand = plan.brand || '', agency = plan.agency || ''
  // строки размещения = заполненные (позиция + объём + цена), как «filled» в конструкторе
  const placements = (plan.rows || []).filter(r => r.position && r.volume && r.unit_price).map(r => {
    const vol = +r.volume || 0, unit = +r.unit_price || 0, disc = +r.discount || 0
    // CPM — за 1000, иначе кол-во×цена (как в конструкторе)
    const cost = Math.round(vol * unit * (1 - disc) / (r.model === 'CPM' ? 1000 : 1))
    const f = r.forecast || {}
    const freq = +f.freq || 0
    const ctr = (+f.ctr || 0) / 100
    const cr = (+f.cr || 0) / 100
    const price = +f.price || 0
    const sov = +f.sov || 0
    const clicks = vol * ctr
    const checks = clicks * cr
    return {
      position: r.position, format: r.format || '', inventory: r.inventory || 'cross', model: r.model || 'CPM',
      volume: vol, unit, discount: disc, cost,
      freq, reach: freq > 0 ? vol / freq : 0, clicks, checks, price, revenue: checks * price, sov,
    }
  })
  const extras = (plan.extras || []).map(e => ({ name: e.name || '', period: e.period || '', price: +e.price || 0, total: +e.total || 0 }))
  return {
    header: {
      logo: '/assets/logo-mediaplan.svg',
      title: `Медиаплан · ${adv || '—'}${brand ? ' / ' + brand : ''}`,
      // SIMB-AD (площадка) · агентство (или рекламодатель) · дата составления · срок
      subtitle: `SIMB-AD · ${agency || adv || '—'} · от ${fmtDate(plan.created_at)} · МП актуален 14 дней`,
    },
    placementMeta: `гео ${plan.geo || 'РФ'} · период ${plan.period || '—'}`,
    // 4×2, заливка по колонкам (пары в столбик):
    // 1) Название+Агентство  2) Рекламодатель+Бренд  3) Период+Дата старта  4) Место+Гео
    params: [
      ['Название РК', plan.title || '—', false],
      ['Агентство', agency || '—', false],
      ['Рекламодатель', adv || '—', false],
      ['Бренд', brand || '—', false],
      ['Период размещения', plan.period || '—', false],
      ['Дата старта', plan.date_from ? fmtDate(plan.date_from) : '—', true],
      ['Место размещения', 'SIMB-AD', false],
      ['Гео', plan.geo || 'РФ', false],
    ],
    placements,
    extras,
    targeting: TG_GROUPS.map(([k, l]) => [l, tval((plan.targeting || {})[k])]),
    goals: plan.goals || {},
    notes: NOTES, aggRules: AGG_RULES, bonusNote: BONUS_NOTE,
  }
}

export default function MpPdf() {
  const router = useRouter()
  const { id } = router.query
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (typeof window === 'undefined') return
    // Режим сайдкара: бэкенд инжектит данные в window.__MP_PLAN__ — без API и без токена
    // (доступ уже проверен бэкендом). Так headless-Chromium рендерит страницу напрямую.
    if (window.__MP_PLAN__) {
      try { setData(toPdf(window.__MP_PLAN__)) } catch (e) { setErr('Ошибка данных медиаплана') }
      return
    }
    if (!id) return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (localStorage.getItem('role') !== 'admin') {
      let p = {}; try { p = JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) {}
      if (!can(p, 'media_plans', 'view')) { router.replace('/deals/mp'); return }
    }
    api.get(`/sales/media-plans/${id}/pdf-data`, auth())
      .then(r => setData(toPdf(r.data)))
      .catch(e => setErr(e.response?.status === 403 ? 'Нет доступа к этому медиаплану' : 'Не удалось загрузить медиаплан'))
  }, [id])

  // Флаг готовности для сайдкара (ждёт window.__MP_RENDERED__ перед page.pdf()).
  useEffect(() => { if (data && typeof window !== 'undefined') window.__MP_RENDERED__ = true }, [data])

  if (err) return <div style={{ padding: 40, fontFamily: 'Manrope, sans-serif', color: '#79839A' }}>{err}</div>
  if (!data) return <div style={{ padding: 40, fontFamily: 'Manrope, sans-serif', color: '#79839A' }}>Загрузка…</div>

  return (
    <>
      <Head><title>{data.header.title}</title></Head>
      {/* Панель действий — скрывается при печати (.no-print) */}
      <div className="no-print" style={{ position: 'fixed', top: 16, right: 20, zIndex: 100, display: 'flex', gap: 8 }}>
        <button onClick={() => router.back()} style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid #E3E7F1', background: '#FFFFFF', color: '#525C70', fontFamily: 'Manrope, sans-serif', fontSize: 13, fontWeight: 600, cursor: 'pointer', boxShadow: '0 2px 10px rgba(28,36,51,.10)' }}>← Назад</button>
        <button onClick={() => window.print()} style={{ padding: '8px 16px', borderRadius: 10, border: 'none', background: '#4F6CE6', color: '#FFFFFF', fontFamily: 'Manrope, sans-serif', fontSize: 13, fontWeight: 700, cursor: 'pointer', boxShadow: '0 2px 10px rgba(79,108,230,.30)' }}>Печать / Сохранить PDF</button>
      </div>
      <MediaPlanPdf data={data} />
    </>
  )
}
