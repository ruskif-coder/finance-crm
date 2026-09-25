/**
 * Демо-стенд Weborama (WCM) — по образцу стенда DSP.
 *
 * Живём в контуре АККАУНТОВ: пиксель верификатора заводится вместе с креативами, а это
 * работа аккаунта, не трафика.
 *
 * Шаги отдельные и не автоматические: смысл стенда в том, чтобы видеть ответ КАЖДОГО
 * шага — их форма в доке Weborama не описана вовсе. Поэтому под каждым шагом лежит сырой
 * ответ, а не наш пересказ.
 *
 * Аккаунт вводится ЗДЕСЬ, а не берётся из окружения: аккаунты Weborama выдаёт списком и
 * закрепляет за клиентами, и молчаливое умолчание однажды запишет кампанию одного
 * рекламодателя в измерения другого.
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar, { can } from '@/components/Navbar'
import { getPermissions } from '@/lib/auth'
import { MONO, UI, Modal, card, inp, btn, primaryBtn } from '@/components/salesTableKit'
import api, { auth } from '@/lib/http'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const SECTION = { ...card, padding: '16px 20px', marginBottom: 14 }
const LBL = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const CODE = { fontFamily: MONO, fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '10px 12px', maxHeight: 240, overflow: 'auto' }
const IDV = { fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--income-fg)' }

/** Поле формы. На уровне модуля: компонент внутри компонента теряет фокус на каждом
 *  символе — это ловит гейт check-inline. */
function F({ label, value, onChange, placeholder, width, hint }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ ...LBL, marginBottom: 4 }}>{label}</div>
      <input value={value ?? ''} onChange={e => onChange(e.target.value)} placeholder={placeholder}
             style={{ ...inp, width: width || '100%', fontFamily: MONO, fontSize: 12 }} />
      {!!hint && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 3 }}>{hint}</div>}
    </div>
  )
}

/** Шаг цепочки: заголовок, пояснение, тело, отказ, ответ. */
function Step({ n, title, note, children, result, error, blocked }) {
  return (
    <div style={SECTION}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
        <span style={{ ...IDV, color: 'var(--accent)' }}>{n}</span>
        <span style={{ fontSize: 15, fontWeight: 700 }}>{title}</span>
      </div>
      {!!note && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.5 }}>{note}</div>}
      {/* Почему кнопка не нажимается — словами. Отключённая кнопка молчит, и человек
          считает, что сломался экран, а не что не пройден предыдущий шаг. */}
      {!!blocked && (
        <div style={{ fontSize: 12.5, color: 'var(--warning-text)', marginBottom: 10 }}>{blocked}</div>
      )}
      {children}
      {!!error && (
        <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 10,
          border: '1px solid var(--danger)', background: 'var(--danger-tint)',
          color: 'var(--danger)', fontSize: 12.5, lineHeight: 1.5 }}>{error}</div>
      )}
      {!!result && <div style={{ marginTop: 12 }}>{result}</div>}
    </div>
  )
}

/** Правила стенда: экраном пользуется не только владелец. */
function ImportantInfo({ onClose }) {
  const P = { fontSize: 13.5, lineHeight: 1.65, margin: '0 0 12px' }
  return (
    <Modal title="Важная информация о стенде" width={720} onClose={onClose}
           summary="Своего демо-аккаунта у Weborama нет. Всё, что вы здесь заводите, появляется в боевом кабинете."
           footer={<button onClick={onClose} style={primaryBtn}>Понятно</button>}>
      <p style={{ ...P, color: 'var(--danger)', fontWeight: 600 }}>
        Проект, кампанию и вставку переименовать в их кабинете нельзя. Имя уезжает навсегда —
        поэтому шаг «Имена» показывает все три ДО отправки, и его стоит прочитать глазами.
      </p>
      <p style={P}>
        <b>Тренируйтесь в проекте TEST_2026.</b> Он уже есть в кабинете и заведён ровно для
        этого. Учебные структуры в чужих брендах разбирать потом придётся руками.
      </p>
      <p style={P}>
        <b>Аккаунт вводится руками.</b> Weborama выдаёт аккаунты списком и закрепляет за
        клиентами; молчаливое умолчание однажды запишет кампанию одного рекламодателя в
        измерения другого. Поле подставляется из настройки, но выбор всегда виден.
      </p>
      <p style={P}>
        <b>Наших площадок в их каталоге нет.</b> Каталог ad_space глобальный — 1080 записей,
        включая чужие сайты, — и все наши размещения висят на ОДНОМ ad_space «SIMB-AD».
        Поэтому какая это площадка, несёт только метка вставки: уникальность метки здесь не
        формальность, а единственный различитель.
      </p>
      <p style={P}>
        <b>Пиксель живёт на вставке</b>, то есть на паре «кампания × площадка», а не на
        креативе: площадку опознаёт номер вставки внутри самого пикселя. Один пиксель
        обслуживает все креативы этой площадки в этой кампании.
      </p>
      <p style={{ ...P, marginBottom: 4 }}>
        <b>8–11 сентября у WCM плановое техобслуживание.</b> Короткие отказы в эти дни
        могут быть не нашей виной.
      </p>
    </Modal>
  )
}

export default function WeboramaDemo() {
  const [state, setState] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const [stepErr, setStepErr] = useState({})
  const [showInfo, setShowInfo] = useState(false)

  const [account, setAccount] = useState('')
  const [deals, setDeals] = useState([])

  // Шаги
  const [loginOut, setLoginOut] = useState(null)
  const [spaces, setSpaces] = useState(null)
  const [form, setForm] = useState({ deal_code: '', brand: '', month: '', ident: '',
                                     landing_url: '', domain: '', channel: 'Desktop', fmt: 'banner' })
  const [names, setNames] = useState(null)
  const [projOut, setProjOut] = useState(null)
  const [campOut, setCampOut] = useState(null)
  const [netId, setNetId] = useState('')
  const [netOut, setNetOut] = useState(null)
  const [spaceId, setSpaceId] = useState('')
  const [delivery, setDelivery] = useState('4')
  const [insOut, setInsOut] = useState(null)
  const [tagOut, setTagOut] = useState(null)
  const [pixel, setPixel] = useState('')
  const [kind, setKind] = useState('dsp')
  // Размер баннера: им заменяются ~WIDTH~/~HEIGHT~ в пикселе формата 3.
  const [size, setSize] = useState({ w: '', h: '' })
  const [asmOut, setAsmOut] = useState(null)

  const load = useCallback(async () => {
    try {
      const r = await api.get('/weborama-demo/state', auth())
      setState(r.data)
      setAccount(prev => prev || r.data?.account_hint || '')
      const d = await api.get('/weborama-demo/deals', auth())
      setDeals(d.data?.rows || [])
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось прочитать состояние стенда') }
  }, [])

  useRefreshOnReturn(() => load())
  useEffect(() => { load() }, [load])
  // Шаги, которые сервер пускает только с правом правки (вход, проект, кампания, сеть,
  // вставка), при одном просмотре неактивны и говорят почему — раньше они были видны и
  // отвечали 403 (аудит 23.09.2026, 7.L4). Право читается в эффекте, не при рендере.
  const [canEdit, setCanEdit] = useState(false)
  useEffect(() => { setCanEdit(can(getPermissions(), 'weborama_demo', 'edit')) }, [])
  const noEdit = canEdit ? undefined : 'Нужно право «Аккаунты · Weborama демо» — правка'

  const run = async (key, fn) => {
    setBusy(key); setErr(''); setStepErr(s => ({ ...s, [key]: '' }))
    try { await fn() } catch (e) {
      const msg = e.response?.data?.detail || `Шаг «${key}» не прошёл`
      setErr(msg); setStepErr(s => ({ ...s, [key]: msg }))
    } finally { setBusy('') }
  }

  const acc = () => ({ account_id: account })

  const doLogin = () => run('login', async () => {
    const r = await api.post('/weborama-demo/login', acc(), auth()); setLoginOut(r.data)
  })
  const doSpaces = () => run('spaces', async () => {
    const r = await api.post('/weborama-demo/ad-spaces', acc(), auth()); setSpaces(r.data)
    // Константы аккаунта подставляем сразу: вводить их руками — лишний повод ошибиться.
    if (r.data?.ad_space?.id) setSpaceId(String(r.data.ad_space.id))
    if (r.data?.ad_space?.network) setNetId(String(r.data.ad_space.network))
  })
  const doNames = () => run('names', async () => {
    const r = await api.post('/weborama-demo/names', {
      deal_code: form.deal_code, brand: form.brand, month: form.month,
      ident: form.ident || null, domain: form.domain || 'example.ru',
      channel: form.channel, fmt: form.fmt,
    }, auth())
    setNames(r.data)
  })
  const doProject = () => run('project', async () => {
    const r = await api.post('/weborama-demo/project', {
      ...acc(), deal_code: form.deal_code, brand: form.brand, month: form.month }, auth())
    setProjOut(r.data)
  })
  const doCampaign = () => run('campaign', async () => {
    const r = await api.post('/weborama-demo/campaign', {
      ...acc(), project_id: projOut?.id, brand: form.brand,
      ident: form.ident || form.deal_code, landing_url: form.landing_url }, auth())
    setCampOut(r.data)
  })
  const doNetwork = () => run('network', async () => {
    const r = await api.post('/weborama-demo/ad-network', { ...acc(), label: 'SIMB-AD' }, auth())
    setNetOut(r.data); setNetId(r.data?.id || netId)
  })
  const doInsertion = () => run('insertion', async () => {
    const r = await api.post('/weborama-demo/insertion', {
      ...acc(), campaign_id: campOut?.id, ad_network_id: netId, ad_space_id: spaceId,
      campaign_label: campOut?.label || '', domain: form.domain,
      channel: form.channel, fmt: form.fmt, delivery_format_id: Number(delivery) }, auth())
    setInsOut(r.data)
  })
  const doTag = () => run('tag', async () => {
    const r = await api.post('/weborama-demo/tag', { ...acc(), insertion_id: insOut?.id }, auth())
    setTagOut(r.data)
    // Берём ТОЛЬКО показной пиксель, разобранный сервером. Прежний поиск «любого
    // адреса с [RANDOM]» хватал кликовый счётчик — поймано на живой пробе 09.09.2026.
    if (r.data?.pixel) setPixel(r.data.pixel)
  })
  const doAssemble = () => run('assemble', async () => {
    const r = await api.post('/weborama-demo/assemble',
      { pixel, domain: form.domain, kind,
        width: size.w ? Number(size.w) : null, height: size.h ? Number(size.h) : null }, auth())
    setAsmOut(r.data)
  })

  const ready = state?.configured
  const pickDeal = (v) => {
    const d = deals.find(x => `${x.campaign_id}` === v)
    if (!d) return
    setForm(f => ({ ...f, deal_code: d.deal_code || '', brand: d.brand || '',
                    month: d.month || '', ident: d.deal_code || '' }))
  }

  return (
    <>
      <Head><title>Weborama демо · Аккаунты | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ fontFamily: UI, padding: '18px 22px 60px', maxWidth: 1180, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14 }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>Weborama демо</h1>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            заведение пикселя верификатора: проект → кампания → сеть → вставка → тег
          </span>
        </div>

        {!!err && (
          <div style={{ ...SECTION, borderColor: 'var(--danger)', color: 'var(--danger)' }}>{err}</div>
        )}

        <div style={{ ...SECTION, display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div style={LBL}>Контур</div>
            <div style={{ ...IDV, color: ready ? 'var(--danger)' : 'var(--warning-text)' }}>
              {ready ? 'БОЕВОЙ КАБИНЕТ' : 'не настроен'}
            </div>
          </div>
          <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-card)' }} />
          <div>
            <div style={LBL}>Вход</div>
            <div style={{ fontFamily: MONO, fontSize: 12.5 }}>{state?.email || '—'}</div>
          </div>
          <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-card)' }} />
          <div>
            <div style={LBL}>Адрес API</div>
            <div style={{ fontFamily: MONO, fontSize: 12 }}>{state?.url || '—'}</div>
          </div>
          <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-card)' }} />
          <F label="Аккаунт WCM" value={account} onChange={setAccount} width={140}
             placeholder="10419" hint="вводится руками — он адресует весь обмен" />
          <button onClick={() => setShowInfo(true)}
                  style={{ ...btn(false), marginLeft: 'auto', borderColor: 'var(--danger)', color: 'var(--danger)' }}>
            Важная информация
          </button>
        </div>

        {!ready && (
          <div style={{ ...SECTION, background: 'var(--bg-subtle)' }}>
            <div style={{ ...LBL, marginBottom: 8 }}>Стенд ещё не включён</div>
            <div style={{ fontSize: 13, lineHeight: 1.6 }}>
              В <code style={{ fontFamily: MONO }}>.env</code> нужны{' '}
              <code style={{ fontFamily: MONO }}>{state?.env?.email}</code> и{' '}
              <code style={{ fontFamily: MONO }}>{state?.env?.password}</code>
              {' '}(необязательно <code style={{ fontFamily: MONO }}>{state?.env?.url}</code> и{' '}
              <code style={{ fontFamily: MONO }}>{state?.env?.account}</code> — второй только
              подставляет номер аккаунта в поле). Значения кладёт владелец: из переписки они
              не переносятся.
            </div>
          </div>
        )}

        <Step n="1" title="Вход" error={stepErr.login}
              blocked={!ready ? 'Нет учётных данных в .env.' : (!account ? 'Введите номер аккаунта.' : '')}
              note="JWT по email и паролю. Токен на экран НЕ возвращается — он ключ ко всему аккаунту; показываем только факт входа и длину."
              result={loginOut && (
                <div style={{ fontSize: 13 }}>
                  Вошли в аккаунт <b style={{ fontFamily: MONO }}>{loginOut.account_id}</b>,
                  токен получен ({loginOut.token_length} символов).
                </div>
              )}>
          <button onClick={doLogin} title={noEdit} disabled={!canEdit || !ready || !account || !!busy} style={primaryBtn}>
            {busy === 'login' ? 'Вхожу…' : 'Войти'}
          </button>
        </Step>

        <Step n="2" title="Наш ad_space и сеть" error={stepErr.spaces}
              blocked={!loginOut ? 'Сначала шаг 1.' : ''}
              note="Каталог ad_space у них ГЛОБАЛЬНЫЙ — 1080 записей, включая чужие сайты, и ни одного нашего домена в нём нет. Все наши вставки висят на одном ad_space «SIMB-AD». Значит ad_space и сеть — константы аккаунта, а какая это площадка, несёт только метка вставки."
              result={spaces && (
                <>
                  <div style={{ fontSize: 13, marginBottom: 8 }}>
                    В каталоге <b>{spaces.total}</b> ad_space (ответ постраничный, выгружено всё).
                  </div>
                  {spaces.ad_space?.id ? (
                    <div style={{ fontSize: 13, lineHeight: 1.9 }}>
                      <div><span style={LBL}>ad_space_id</span>{' '}<b style={{ fontFamily: MONO }}>{spaces.ad_space.id}</b>{' '}«{spaces.ad_space.label}»</div>
                      <div><span style={LBL}>ad_network_id</span>{' '}<b style={{ fontFamily: MONO }}>{spaces.ad_space.network}</b></div>
                    </div>
                  ) : (
                    <div style={{ fontSize: 13, color: 'var(--warning-text)' }}>{spaces.ad_space?.reason}</div>
                  )}
                  <div style={{ ...LBL, margin: '12px 0 4px' }}>Первые записи каталога</div>
                  <div style={CODE}>{JSON.stringify(spaces.sample, null, 2)}</div>
                </>
              )}>
          <button onClick={doSpaces} disabled={!loginOut || !!busy} style={btn(false)}>
            {busy === 'spaces' ? 'Читаю…' : 'Найти наш ad_space'}
          </button>
        </Step>

        <Step n="3" title="Имена — до отправки" error={stepErr.names}
              note="Переименовать проект, кампанию или вставку в их кабинете нельзя. Поэтому все три имени показываются здесь, сетью этот шаг не пользуется."
              result={names && (
                <div style={{ fontSize: 13, lineHeight: 1.9 }}>
                  <div><span style={LBL}>проект</span>{' '}<b style={{ fontFamily: MONO }}>{names.project}</b></div>
                  <div><span style={LBL}>кампания</span>{' '}<b style={{ fontFamily: MONO }}>{names.campaign}</b></div>
                  <div><span style={LBL}>вставка</span>{' '}<b style={{ fontFamily: MONO }}>{names.insertion}</b></div>
                </div>
              )}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 10 }}>
            <div>
              <div style={{ ...LBL, marginBottom: 4 }}>Взять из РК</div>
              <select onChange={e => pickDeal(e.target.value)} defaultValue=""
                      style={{ ...inp, width: '100%', fontSize: 12 }}>
                <option value="">— выбрать —</option>
                {deals.map(d => (
                  <option key={d.campaign_id} value={d.campaign_id}>
                    {d.deal_code} · {d.brand || 'без бренда'} · {d.month}
                  </option>
                ))}
              </select>
            </div>
            <F label="Код сделки" value={form.deal_code} onChange={v => setForm(f => ({ ...f, deal_code: v }))} />
            <F label="Бренд" value={form.brand} onChange={v => setForm(f => ({ ...f, brand: v }))} />
            <F label="Месяц" value={form.month} onChange={v => setForm(f => ({ ...f, month: v }))} placeholder="2026-09" />
            <F label="ID для кампании" value={form.ident} onChange={v => setForm(f => ({ ...f, ident: v }))} hint="пусто = код сделки" />
            <F label="Домен площадки" value={form.domain} onChange={v => setForm(f => ({ ...f, domain: v }))} placeholder="maksavit.ru" />
            <F label="Канал" value={form.channel} onChange={v => setForm(f => ({ ...f, channel: v }))} />
            <F label="Формат" value={form.fmt} onChange={v => setForm(f => ({ ...f, fmt: v }))} />
          </div>
          <button onClick={doNames} disabled={!!busy} style={btn(false)}>Показать имена</button>
        </Step>

        <Step n="4" title="Проект" error={stepErr.project}
              blocked={!loginOut ? 'Сначала шаг 1.' : (!names ? 'Сначала посмотрите имена — переименовать потом нельзя.' : '')}
              note="У них проект = бренд + год. У нас — код сделки, бренд и месяц: по их имени нельзя понять, к какой сделке относится проект."
              result={projOut && (
                <>
                  <div style={LBL}>project_id</div>
                  <div style={IDV}>{projOut.id}</div>
                  <div style={{ fontFamily: MONO, fontSize: 12.5, marginTop: 4 }}>{projOut.label}</div>
                  <div style={{ ...CODE, marginTop: 8 }}>{JSON.stringify(projOut.raw, null, 2)}</div>
                </>
              )}>
          <button onClick={doProject} title={noEdit} disabled={!canEdit || !loginOut || !names || !!busy} style={primaryBtn}>
            {busy === 'project' ? 'Завожу…' : 'Завести проект'}
          </button>
        </Step>

        <Step n="5" title="Кампания" error={stepErr.campaign}
              blocked={!projOut ? 'Сначала шаг 4: кампания заводится ВНУТРИ проекта.' : ''}
              note="landing_url обязателен у них. У нас посадочная своя у каждой площадки, единой на сделку не существует — поэтому её вводят руками."
              result={campOut && (
                <>
                  <div style={LBL}>campaign_id</div>
                  <div style={IDV}>{campOut.id}</div>
                  <div style={{ fontFamily: MONO, fontSize: 12.5, marginTop: 4 }}>{campOut.label}</div>
                  <div style={{ ...CODE, marginTop: 8 }}>{JSON.stringify(campOut.raw, null, 2)}</div>
                </>
              )}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
            <F label="landing_url" value={form.landing_url}
               onChange={v => setForm(f => ({ ...f, landing_url: v }))}
               placeholder="https://…" width={420} />
            <button onClick={doCampaign} title={noEdit} disabled={!canEdit || !projOut || !!busy} style={primaryBtn}>
              {busy === 'campaign' ? 'Завожу…' : 'Завести кампанию'}
            </button>
          </div>
        </Step>

        <Step n="6" title="Рекламная сеть" error={stepErr.network}
              note="В боевом аккаунте она уже есть, id 106 — подставляется шагом 2. Число 1080 из кабинета это НЕ сеть, а ad_space. Кнопка нужна только для нового аккаунта: метода «получить список сетей» у них нет."
              result={netOut && (
                <>
                  <div style={LBL}>ad_network_id</div>
                  <div style={IDV}>{netOut.id}</div>
                  <div style={{ ...CODE, marginTop: 8 }}>{JSON.stringify(netOut.raw, null, 2)}</div>
                </>
              )}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
            <F label="ad_network_id" value={netId} onChange={setNetId} width={160} />
            <button onClick={doNetwork} title={noEdit} disabled={!canEdit || !loginOut || !!busy} style={btn(false)}>
              {busy === 'network' ? 'Завожу…' : 'Завести новую сеть'}
            </button>
          </div>
        </Step>

        <Step n="7" title="Вставка" error={stepErr.insertion}
              blocked={!campOut ? 'Сначала шаг 5.' : (!spaceId ? 'Укажите ad_space из шага 2.' : '')}
              note="Вставка и есть «кампания × площадка» — на ней живёт тег. Формат решает, ЧЕМ она меряет: 4 отдаёт js-блок и считает видимость (в DSP это js_code_audit), 3 отдаёт пиксель a.A=im без видимости (в DSP это pixel). Картинкой 1×1 видимость не измерить — отсюда и разница."
              result={insOut && (
                <>
                  <div style={LBL}>insertion_id</div>
                  <div style={IDV}>{insOut.id}</div>
                  <div style={{ fontFamily: MONO, fontSize: 12.5, marginTop: 4 }}>{insOut.label}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                    формат: {insOut.delivery_format}
                  </div>
                  <div style={{ ...CODE, marginTop: 8 }}>{JSON.stringify(insOut.raw, null, 2)}</div>
                </>
              )}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
            <F label="ad_space_id" value={spaceId} onChange={setSpaceId} width={160} />
            <div>
              <div style={{ ...LBL, marginBottom: 4 }}>Формат</div>
              <select value={delivery} onChange={e => setDelivery(e.target.value)}
                      style={{ ...inp, width: 330, fontSize: 12.5 }}>
                <option value="4">4 — показы, клики и видимость → js-блок</option>
                <option value="3">3 — показы и клики → пиксель a.A=im</option>
              </select>
            </div>
            <button onClick={doInsertion} title={noEdit} disabled={!canEdit || !campOut || !spaceId || !!busy} style={primaryBtn}>
              {busy === 'insertion' ? 'Завожу…' : 'Завести вставку'}
            </button>
          </div>
        </Step>

        <Step n="8" title="Тег" error={stepErr.tag}
              blocked={!insOut ? 'Сначала шаг 7.' : ''}
              note="В их js-теге ДВЕ разные ссылки: пиксель показа (a.A=im) и счётчик клика (a.A=cl). В поле pixel креатива DSP нужен ПЕРВЫЙ. Подставляем в следующий шаг только его — кликовый вместо показного означает, что показы не считаются вовсе."
              result={tagOut && (
                <>
                  {!!tagOut.warning && (
                    <div style={{ marginBottom: 10, padding: '10px 12px', borderRadius: 10,
                      border: '1px solid var(--danger)', background: 'var(--danger-tint)',
                      color: 'var(--danger)', fontSize: 12.5, lineHeight: 1.5 }}>
                      {tagOut.warning}
                    </div>
                  )}
                  <div style={{ fontSize: 13, lineHeight: 1.9, marginBottom: 8 }}>
                    <div><span style={LBL}>пиксель показа (a.A=im)</span>{' '}
                      <b style={{ color: tagOut.parsed?.impression ? 'var(--income-fg)' : 'var(--danger)' }}>
                        {tagOut.parsed?.impression ? 'есть' : 'НЕТ'}</b></div>
                    <div><span style={LBL}>счётчик клика (a.A=cl)</span>{' '}
                      {tagOut.parsed?.click ? 'есть' : 'нет'}</div>
                    <div><span style={LBL}>плейсхолдеры</span>{' '}
                      <span style={{ fontFamily: MONO, fontSize: 11.5 }}>
                        {(tagOut.parsed?.placeholders || []).join(' ') || '—'}</span></div>
                  </div>
                  <div style={CODE}>{JSON.stringify(tagOut.raw, null, 2)}</div>
                </>
              )}>
          <button onClick={doTag} disabled={!insOut || !!busy} style={btn(false)}>
            {busy === 'tag' ? 'Читаю…' : 'Получить тег'}
          </button>
        </Step>

        <Step n="9" title="Итоговый тег" error={stepErr.assemble}
              blocked={!pixel ? 'Нет пикселя показа. Он приходит только от вставки с форматом 3 — у формата 4 вместо него js-блок, и собирать из него эту строку нечего.'
                       : (!form.domain ? 'Не указан домен площадки — он идёт в хвост тега.' : '')}
              note="Подстановка макроса рандомизатора и хвост с адресом площадки. Сети не касается. Размер подставляется вместо ~WIDTH~/~HEIGHT~ — он объявлен в самом баннере, выдумывать нечего. Если после сборки остались чужие макросы, экран скажет: DSP их не знает и отправит как есть."
              result={asmOut && (
                <>
                  {!!asmOut.warning && (
                    <div style={{ marginBottom: 10, padding: '10px 12px', borderRadius: 10,
                      border: '1px solid var(--danger)', background: 'var(--danger-tint)',
                      color: 'var(--danger)', fontSize: 12.5, lineHeight: 1.5 }}>
                      {asmOut.warning}
                    </div>
                  )}
                  <div style={LBL}>подстановка</div>
                  <div style={{ fontFamily: MONO, fontSize: 12, marginBottom: 6 }}>{asmOut.macro}</div>
                  <div style={CODE}>{asmOut.tag}</div>
                </>
              )}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
            <F label="Пиксель" value={pixel} onChange={setPixel} width={520}
               placeholder="…&a.ra=[RANDOM]" />
            <div>
              <div style={{ ...LBL, marginBottom: 4 }}>Куда</div>
              <select value={kind} onChange={e => setKind(e.target.value)}
                      style={{ ...inp, width: 140, fontSize: 12.5 }}>
                <option value="dsp">DSP</option>
                <option value="adfox">Adfox</option>
              </select>
            </div>
            <F label="Ширина" value={size.w} onChange={v => setSize(s => ({ ...s, w: v }))} width={90} />
            <F label="Высота" value={size.h} onChange={v => setSize(s => ({ ...s, h: v }))} width={90} />
            <button onClick={doAssemble} disabled={!pixel || !form.domain || !!busy} style={primaryBtn}>
              Собрать
            </button>
          </div>
        </Step>
      </div>

      {showInfo && <ImportantInfo onClose={() => setShowInfo(false)} />}
    </>
  )
}
