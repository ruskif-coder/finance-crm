import { useState, useEffect } from 'react'
import Head from 'next/head'
import dynamic from 'next/dynamic'
import api, { auth, signOut, TOKEN_KEY } from '../lib/http'
import { C, btn, card, inp } from '../lib/ui'

/* Кабинет грузится ОТДЕЛЬНЫМ чанком и только после входа: до авторизации по проводу не
   должно уходить ничего, кроме самой формы. Раньше весь код кабинета (пути эндпоинтов,
   ярлыки, структура) ехал одним бандлом и скачивался любым, кто открыл адрес. Данные и
   тогда были за гейтом — но код открывал всю карту приложения.

   `ssr: false` — дашборд читает `localStorage`, на сервере его рендерить нельзя. */
const Dashboard = dynamic(() => import('../components/Dashboard'),
  { ssr: false, loading: () => null })
// Согласие — тоже отдельным чанком: его тексты нужны только тем, кто уже вошёл.
const Consent = dynamic(() => import('../components/Consent'),
  { ssr: false, loading: () => null })

function Login({ onDone }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const r = await api.post('/login', { email: email.trim(), password })
      localStorage.setItem(TOKEN_KEY, r.data.token)
      localStorage.setItem('cabinet_name', r.data.name || '')
      onDone(!!r.data.consent_required)
    } catch (e2) {
      setErr(e2.response?.data?.detail || 'Не удалось войти')
      setBusy(false)
    }
  }

  return (
    <div style={{ minHeight: '100%', display: 'flex', alignItems: 'center',
      justifyContent: 'center', padding: 18 }}>
      <form onSubmit={submit} className="rise"
        style={{ ...card, padding: '30px 28px', width: 'min(400px, 100%)',
          display: 'flex', flexDirection: 'column', gap: 14 }}>
        <img className="logo-light" src="/assets/logo-mediaplan.svg" alt="SIMB-AD" height="26"
          style={{ alignSelf: 'flex-start' }} />
        <img className="logo-dark" src="/assets/logo-mediaplan-dark.svg" alt="SIMB-AD" height="26"
          style={{ alignSelf: 'flex-start' }} />
        <div>
          {/* «Паблишера», а не «площадки» (владелец 15.09.2026): у одной учётки бывает
              несколько сайтов, и «кабинет площадки» обещает вход на один. */}
          <div style={{ fontSize: 20, fontWeight: 800 }}>Кабинет паблишера</div>
          <div style={{ fontSize: 12.5, color: C.muted, marginTop: 4 }}>
            {/* «и кампании» убрано 31.08.2026 вместе с блоком денег: подпись на входной
                двери обещала раздел, которого за ней больше нет. Вернуть — вместе с
                `SHOW_MONEY`. */}
            Согласование креативов и размещений
          </div>
        </div>
        <input style={inp} type="email" autoComplete="username" placeholder="Почта"
          value={email} onChange={e => setEmail(e.target.value)} required />
        <input style={inp} type="password" autoComplete="current-password" placeholder="Пароль"
          value={password} onChange={e => setPassword(e.target.value)} required />
        {!!err && <div style={{ fontSize: 12.5, color: C.danger }}>{err}</div>}
        <button style={btn(true)} disabled={busy} type="submit">
          {busy ? 'Входим…' : 'Войти'}
        </button>
        {/* Честно о том, чего нет: восстановления по почте не будет, и человек должен
            знать, куда идти, а не искать несуществующую ссылку. */}
        <div style={{ fontSize: 11.5, color: C.faint, lineHeight: 1.5 }}>
          Забыли пароль — напишите вашему менеджеру: восстановление по почте
          в кабинете не предусмотрено.
        </div>
      </form>
    </div>
  )
}

const pageTitle = (section) => `SIMB-AD | Кабинет паблишера | ${section}`

export default function Cabinet() {
  const [ready, setReady] = useState(false)
  const [authed, setAuthed] = useState(false)
  const [name, setName] = useState('')
  // Согласие на обработку ПДн (24.09.2026): null — ещё не знаем, true — нужно показать
  // форму. Держит правило сервер; здесь только выбор экрана.
  const [needConsent, setNeedConsent] = useState(null)

  // Открытие с уже сохранённым токеном: спросить сервер, дано ли согласие. Токен мог
  // быть выписан до того, как согласие появилось.
  useEffect(() => {
    if (!authed || needConsent !== null) return
    api.get('/me', auth())
      .then(r => setNeedConsent(!!r.data.consent_required))
      .catch(e => {
        if (e.response?.status === 401 || e.response?.status === 403) {
          signOut(); setAuthed(false)
        } else setNeedConsent(false)      // сеть — кабинет сам покажет ошибку
      })
  }, [authed, needConsent])

  // Токен читаем ОДИН раз после монтирования: `localStorage` на сервере нет, а чтение при
  // рендере дало бы разошедшуюся разметку. До этого чтения не рисуем ничего.
  useEffect(() => {
    try {
      setAuthed(!!localStorage.getItem(TOKEN_KEY))
      setName(localStorage.getItem('cabinet_name') || '')
    } catch { /* приватный режим */ }
    setReady(true)
  }, [])

  if (!ready) return null
  if (!authed) {
    return (
      <>
        <Head><title>{pageTitle('Вход')}</title></Head>
        <Login onDone={(consentRequired) => {
          setNeedConsent(consentRequired)
          setAuthed(true)
          setName(localStorage.getItem('cabinet_name') || '')
        }} />
      </>
    )
  }
  // Выход из кабинета возвращает привратника в состояние «не авторизован»: чанк дашборда
  // уже скачан, но данные из него уходят, и форма показывается снова.
  const exit = () => { signOut(); setAuthed(false); setNeedConsent(null) }
  if (needConsent === null) return null
  if (needConsent) {
    return (
      <>
        <Head><title>{pageTitle('Согласие')}</title></Head>
        <Consent onAccepted={() => setNeedConsent(false)} onDecline={exit} />
      </>
    )
  }
  return <Dashboard name={name} onSignOut={exit} />
}
