import { IcoBtn } from '@/components/traffic/dashboardKit'

// Площадка без нашего кода (владелец 29.09.2026): в нашу DSP её не завести, поэтому
// кнопок старта и стопа у неё нет. Вместо них — отметка «заведён и запущен во внешней
// DSP»: трафик ставит её, когда сам завёл креатив у площадки и тот крутится. Отметка =
// статус площадки в РК «запущен» (та же ручка и те же проверки, что у кнопки старта:
// согласованный креатив, объёмы, «в размещении» в сборке); снятие — «пауза».
//
// Пауза долю держит, поэтому рядом — «Отключить» (владелец 31.10.2026): площадка выходит
// из распределения, объём уходит остальным; то же «завершена», что у площадки нашей DSP.
// Отключённую — «Вернуть в распределение»: не запуск, а возврат туда, где её держит
// согласование креативов (креатив — это ЕРИД, в обход согласования не возвращаем).
export default function ExternalLaunch({ status, canStart, onChange }) {
  const on = status === 'запущен'
  const off = status === 'завершена'
  const locked = !on && !canStart
  return (
    // Галочка — на месте кнопки старта, вторая кнопка — на месте «Отключить» у площадки DSP:
    // колонка действий одна на обе строки, и кнопки стоят друг под другом.
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      {/* Только галочка, текст — в подсказке (владелец 29.09.2026): колонка действий узкая. */}
      <label title={'Заведён и запущен во внешней DSP'
        + (locked ? ' — нет согласованного креатива, отмечать нечего'
          : on ? ' — снять: площадка встанет на паузу' : ' — отметьте, когда креатив заведён у площадки и крутится')}
        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26,
          cursor: locked ? 'not-allowed' : 'pointer' }}>
        <input type="checkbox" checked={on} disabled={locked} aria-label="Заведён и запущен во внешней DSP"
          style={{ width: 16, height: 16, cursor: 'inherit' }}
          onChange={e => onChange(e.target.checked ? 'запущен' : 'пауза')} />
      </label>
      {off ? (
        <IcoBtn tone="var(--blue)" onClick={() => onChange('вернуть')}
          title="Вернуть в распределение: площадка снова делит объём РК по правилам раскладки. Запуск — галочкой, только с согласованным креативом">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 12a8 8 0 1 0 2.3-5.6" /><path d="M4 4v4h4" />
          </svg>
        </IcoBtn>
      ) : (
        <IcoBtn tone="var(--danger)" onClick={() => onChange('завершена')}
          title="Отключить: площадка выходит из распределения, её объём уходит остальным. Во внешней DSP креатив остановите сами">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 6h12v12H6z" />
          </svg>
        </IcoBtn>
      )}
    </span>
  )
}
