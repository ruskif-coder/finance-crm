import { useState } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import Head from 'next/head'

// Экран входа НИЧЕГО не импортирует из системы — ни навигации, ни справочников.
// Он единственный открывается до авторизации, и всё, что сюда затянуто, уезжает
// анонимному посетителю. До 13.09.2026 ради одной функции `firstAllowedHref`
// подтягивался `components/Navbar` → `Nav` → карта навигации, и вместе с ними в
// бандл логина попадали НАЗВАНИЯ И АДРЕСА ВСЕХ ЭКРАНОВ системы (28 КБ отдельным
// чанком). Куда вести человека после входа, решает `/` — там карта уже к месту.

const POLICY_TEXT = `ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ
ООО «Программатик медиа»

1. ОБЩИЕ ПОЛОЖЕНИЯ

1.1. Настоящая Политика конфиденциальности (далее — Политика) определяет порядок обработки персональных данных пользователей внутренней финансовой информационной системы (далее — Система) ООО «Программатик медиа» (далее — Оператор).

1.2. Обработка персональных данных осуществляется в соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ «О персональных данных».

2. СОСТАВ ОБРАБАТЫВАЕМЫХ ДАННЫХ

Оператор обрабатывает следующие персональные данные пользователей Системы:
— фамилия, имя, отчество;
— адрес электронной почты (используется как логин);
— дата и время входа в Систему;
— журнал действий в Системе (создание, редактирование и удаление записей).

3. ЦЕЛИ ОБРАБОТКИ

Персональные данные обрабатываются исключительно в целях:
— идентификации и аутентификации пользователя в Системе;
— обеспечения разграничения прав доступа;
— ведения журнала действий для обеспечения информационной безопасности и аудита.

4. ПРАВОВЫЕ ОСНОВАНИЯ

Обработка персональных данных осуществляется на основании:
— согласия субъекта персональных данных (ст. 9 Федерального закона № 152-ФЗ);
— необходимости исполнения трудовых обязанностей (ст. 6, ч. 1, п. 5 Федерального закона № 152-ФЗ).

5. ПОРЯДОК ОБРАБОТКИ И ХРАНЕНИЯ

5.1. Персональные данные обрабатываются автоматизированным способом с использованием средств вычислительной техники.

5.2. Персональные данные хранятся на серверах Оператора, расположенных на территории Российской Федерации.

5.3. Срок хранения персональных данных — в течение всего периода работы пользователя в Организации и не более 5 (пяти) лет после прекращения трудовых отношений, если иное не предусмотрено законодательством.

5.4. Персональные данные не передаются третьим лицам, за исключением случаев, предусмотренных законодательством Российской Федерации.

6. ПРАВА СУБЪЕКТА ПЕРСОНАЛЬНЫХ ДАННЫХ

Пользователь имеет право:
— получить информацию об обработке своих персональных данных;
— требовать уточнения, блокирования или уничтожения персональных данных в случае, если они являются неполными, устаревшими, неточными или незаконно обработанными;
— отозвать согласие на обработку персональных данных, направив письменное заявление Оператору.

7. МЕРЫ ЗАЩИТЫ

Оператор принимает необходимые организационные и технические меры для защиты персональных данных от несанкционированного доступа, изменения, раскрытия или уничтожения, в том числе: разграничение прав доступа, использование защищённых протоколов передачи данных, ведение журнала аудита действий.

8. КОНТАКТНАЯ ИНФОРМАЦИЯ ОПЕРАТОРА

ООО «Программатик медиа»
По вопросам обработки персональных данных обращаться к ответственному за организацию обработки персональных данных.`

const CONSENT_TEXT = `СОГЛАСИЕ НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ

Я, нижеподписавшийся(аяся) пользователь информационной системы ООО «Программатик медиа» (далее — Оператор), в соответствии с требованиями Федерального закона от 27.07.2006 № 152-ФЗ «О персональных данных», свободно, своей волей и в своём интересе даю согласие Оператору на обработку следующих моих персональных данных:

— фамилия, имя, отчество;
— адрес электронной почты;
— сведения о действиях в информационной системе (журнал аудита).

ЦЕЛЬ ОБРАБОТКИ: обеспечение работы внутренней финансовой информационной системы Оператора, идентификация пользователя, разграничение прав доступа, ведение журнала действий.

ПЕРЕЧЕНЬ ДЕЙСТВИЙ С ПЕРСОНАЛЬНЫМИ ДАННЫМИ: сбор, запись, систематизация, накопление, хранение, уточнение (обновление, изменение), извлечение, использование, обезличивание, блокирование, удаление, уничтожение.

СРОК ДЕЙСТВИЯ СОГЛАСИЯ: в течение всего периода работы в Организации и 5 (пяти) лет после прекращения трудовых отношений.

Я подтверждаю, что ознакомлен(а) с Политикой конфиденциальности ООО «Программатик медиа» и имею право отозвать настоящее согласие путём направления письменного заявления Оператору.

Факт принятия настоящего согласия фиксируется в информационной системе с указанием даты и времени.`

export default function Login() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Состояние модалки согласия
  const [showConsent, setShowConsent] = useState(false)
  const [activeTab, setActiveTab] = useState('policy')
  const [checked, setChecked] = useState(false)
  const [consentLoading, setConsentLoading] = useState(false)
  const [token, setToken] = useState('')

  const handleLogin = async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.append('username', email)
      params.append('password', password)
      const res = await axios.post('/api/auth/login', params)

      // Сохраняем все данные сразу
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('role', res.data.role)
      localStorage.setItem('role_label', res.data.role_label || '')
      localStorage.setItem('is_admin', res.data.is_admin ? '1' : '0')
      localStorage.setItem('permissions', JSON.stringify(res.data.permissions || {}))
      localStorage.setItem('name', res.data.name)

      if (res.data.consent_required) {
        // Первый вход — показываем модалку согласия
        setToken(res.data.access_token)
        setShowConsent(true)
      } else {
        router.push('/')      // корень сам выберет первый доступный экран по правам
      }
    } catch (e) {
      setError('Неверный email или пароль')
    } finally {
      setLoading(false)
    }
  }

  const handleAcceptConsent = async () => {
    if (!checked) return
    setConsentLoading(true)
    try {
      await axios.post('/api/auth/accept-consent', {}, {
        headers: { Authorization: `Bearer ${token}` }
      })
      router.push('/')
    } catch (e) {
      setError('Ошибка при сохранении согласия. Попробуйте войти снова.')
      setShowConsent(false)
    } finally {
      setConsentLoading(false)
    }
  }

  const inputStyle = {
    width: '100%', padding: '10px 14px', borderRadius: '8px',
    border: '1px solid var(--border)', fontSize: '16px', outline: 'none',
    background: 'var(--bg)', color: 'var(--text)', boxSizing: 'border-box'
  }

  // --- Модалка согласия ---
  if (showConsent) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.55)', padding: '20px'
      }}>
        <div style={{
          background: 'var(--card)', borderRadius: '16px', width: '100%', maxWidth: '680px',
          boxShadow: '0 8px 40px rgba(0,0,0,0.18)', display: 'flex', flexDirection: 'column',
          maxHeight: '90vh'
        }}>
          {/* Заголовок */}
          <div style={{ padding: '24px 28px 0' }}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '4px' }}>
              Согласие на обработку персональных данных
            </h2>
            <p style={{ color: 'var(--muted)', fontSize: '14px', marginBottom: '16px' }}>
              В соответствии с Федеральным законом № 152-ФЗ, пожалуйста, ознакомьтесь с документами и примите согласие.
            </p>

            {/* Табы */}
            <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--border)' }}>
              {[
                { key: 'policy', label: 'Политика конфиденциальности' },
                { key: 'consent', label: 'Согласие' },
              ].map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  style={{
                    padding: '8px 16px', border: 'none', background: 'none', cursor: 'pointer',
                    fontSize: '14px', fontWeight: activeTab === tab.key ? '600' : '400',
                    color: activeTab === tab.key ? 'var(--primary)' : 'var(--muted)',
                    borderBottom: activeTab === tab.key ? '2px solid var(--primary)' : '2px solid transparent',
                    marginBottom: '-1px'
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Текст документа */}
          <div style={{
            flex: 1, overflowY: 'auto', padding: '20px 28px',
            fontSize: '13px', lineHeight: '1.7', color: 'var(--text)',
            whiteSpace: 'pre-wrap', fontFamily: 'monospace'
          }}>
            {activeTab === 'policy' ? POLICY_TEXT : CONSENT_TEXT}
          </div>

          {/* Подвал */}
          <div style={{
            padding: '16px 28px 24px',
            borderTop: '1px solid var(--border)'
          }}>
            <label style={{
              display: 'flex', alignItems: 'flex-start', gap: '10px',
              cursor: 'pointer', marginBottom: '16px'
            }}>
              <input
                type="checkbox"
                checked={checked}
                onChange={e => setChecked(e.target.checked)}
                style={{ marginTop: '2px', width: '16px', height: '16px', cursor: 'pointer', flexShrink: 0 }}
              />
              <span style={{ fontSize: '14px', color: 'var(--text)', lineHeight: '1.5' }}>
                Я ознакомился(ась) с Политикой конфиденциальности и даю согласие на обработку
                моих персональных данных ООО «Программатик медиа» в соответствии с требованиями
                Федерального закона № 152-ФЗ.
              </span>
            </label>

            <button
              onClick={handleAcceptConsent}
              disabled={!checked || consentLoading}
              style={{
                width: '100%', padding: '12px',
                background: checked ? 'var(--primary)' : 'var(--border)',
                color: checked ? 'white' : 'var(--muted)',
                border: 'none', borderRadius: '8px', fontSize: '16px',
                fontWeight: '500', cursor: checked ? 'pointer' : 'not-allowed',
                transition: 'background 0.2s'
              }}
            >
              {consentLoading ? 'Сохранение...' : 'Принять и войти в систему'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // --- Форма входа ---
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)', padding: '16px', boxSizing: 'border-box' }}>
      <Head><title>Вход | SIMB-AD ERP</title></Head>
      <div style={{ background: 'var(--card)', padding: 'clamp(28px, 7vw, 40px)', borderRadius: '16px', width: '100%', maxWidth: '380px', boxSizing: 'border-box', boxShadow: '0 4px 24px rgba(0,0,0,0.08)' }}>
        <div style={{ marginBottom: '16px' }}>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
            style={inputStyle}
            placeholder="Email"
          />
        </div>

        <div style={{ marginBottom: '24px' }}>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
            style={inputStyle}
            placeholder="Пароль"
          />
        </div>

        {error && <p style={{ color: 'var(--danger)', fontSize: '15px', marginBottom: '16px' }}>{error}</p>}

        <button
          onClick={handleLogin}
          disabled={loading}
          style={{ width: '100%', padding: '12px', background: 'var(--primary)', color: 'white', border: 'none', borderRadius: '8px', fontSize: '16px', fontWeight: '500', cursor: 'pointer' }}
        >
          {loading ? 'Вход...' : 'Войти'}
        </button>
      </div>
    </div>
  )
}
