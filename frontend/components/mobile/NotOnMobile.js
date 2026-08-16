import { useRouter } from 'next/router'
import { UI } from '../salesTableKit'
import { CARD } from './kit'

// Экран-отказ для редактируемых матриц (годовой план, конструктор медиапланов).
// Показать нерабочую сетку хуже, чем сказать прямо: пользователь иначе решает,
// что приложение сломалось.
export default function NotOnMobile({ title, backHref = '/', backLabel = 'Вернуться' }) {
  const router = useRouter()
  return (
    <div style={{ padding: 14, fontFamily: UI }}>
      <div style={{ ...CARD, padding: 24, display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'flex-start' }}>
        <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
        <span style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
          Этот экран не рассчитан на маленькие экраны — здесь таблица с правкой ячеек,
          которая на телефоне нечитаема. Откройте его с компьютера.
        </span>
        <button onClick={() => router.push(backHref)} style={{
          height: 40, padding: '0 16px', borderRadius: 10, border: 'none', cursor: 'pointer',
          background: 'var(--accent)', color: '#fff', fontFamily: UI, fontSize: 14, fontWeight: 700,
        }}>{backLabel}</button>
      </div>
    </div>
  )
}
