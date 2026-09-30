// Площадка без нашего кода (владелец 29.09.2026): в нашу DSP её не завести, поэтому
// кнопок старта и стопа у неё нет. Вместо них — отметка «заведён и запущен во внешней
// DSP»: трафик ставит её, когда сам завёл креатив у площадки и тот крутится. Отметка =
// статус площадки в РК «запущен» (та же ручка и те же проверки, что у кнопки старта:
// согласованный креатив, объёмы, «в размещении» в сборке); снятие — «пауза».
export default function ExternalLaunch({ status, canStart, onChange }) {
  const on = status === 'запущен'
  const locked = !on && !canStart
  return (
    // Только галочка, текст — в подсказке (владелец 29.09.2026): колонка действий узкая.
    <label title={'Заведён и запущен во внешней DSP'
      + (locked ? ' — нет согласованного креатива, отмечать нечего'
        : on ? ' — снять: площадка встанет на паузу' : ' — отметьте, когда креатив заведён у площадки и крутится')}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 60,
        cursor: locked ? 'not-allowed' : 'pointer' }}>
      <input type="checkbox" checked={on} disabled={locked} aria-label="Заведён и запущен во внешней DSP"
        style={{ width: 16, height: 16, cursor: 'inherit' }}
        onChange={e => onChange(e.target.checked ? 'запущен' : 'пауза')} />
    </label>
  )
}
