// Правый край панели площадок v2 (хендофф 8.1): «↓ Креативы N», «↓ Excel», «↓ ADFOX», «Пиксель WR», «В DSP».
// Логика кнопок — боевая (pages/traffic/dashboard.js до v2): цвет «Пиксель WR» / «В DSP» по состоянию с сервера
// (владелец 30.09.2026: зелёная — есть что сделать, жёлтая — всё готовое сделано, серая — ещё нечего), счётчик
// незаведённого красной плашкой, подсказка с числами. Геометрия — макета.
//
// ПОРЯДОК «Пиксель WR» → «В DSP» не косметика: пиксель показа вшивается в креатив, DSP без пикселя площадку не берёт.
import { MONO, UI } from '@/components/salesTableKit'
import PassportButton from '@/components/traffic/PassportButton'
import OffsiteButton from '@/components/traffic/OffsiteButton'

export const BTN_TONE = {
  go: { background: 'var(--ok-tint)', color: 'var(--ok-fg)', borderColor: 'var(--ok)' },
  done: { background: 'var(--warning-tint)', color: 'var(--warning-fg)', borderColor: 'var(--warning)' },
  idle: { background: 'var(--bg-subtle)', color: 'var(--text-faint)', borderColor: 'var(--border-card)' },
  off: { background: 'var(--bg-subtle)', color: 'var(--text-faint)', borderColor: 'var(--border-card)' },
}

/** Счётчик незаведённого — вид счётчиков меню (Nav.Badge). Нуля не показываем. */
export const CountBadge = ({ n }) => (n > 0 ? (
  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 16, height: 16,
    padding: '0 5px', marginLeft: 6, borderRadius: 6, background: 'var(--danger-tint)', color: 'var(--danger)',
    fontFamily: MONO, fontSize: 9.5, fontWeight: 700 }}>{n}</span>
) : null)

export const btnTitle = (base, b, what) => {
  if (!b) return base
  if (b.state === 'off') return b.external ? 'Пиксель — внешний тег сделки: вставки в Weborama не заводятся, у всех площадок пиксель уже есть' : `${base}. По этой РК свой пиксель Weborama не заказан`
  if (b.state === 'go') return `${base}. Готово к действию площадок: ${b.go}; уже сделано: ${b.done}`
  if (b.state === 'done') return `${base}. Всё готовое уже сделано (${b.done}); новое появится после согласования и ЕРИД`
  return `${base}. Пока нечего: ни у одной площадки нет согласованного креатива с ЕРИД — ${what} ждёт`
}

/** Кнопка панели в геометрии макета: 26 px, радиус 8, 11,5 px. */
export const TOOL = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 9px', borderRadius: 8,
  fontFamily: UI, fontSize: 11.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer', boxSizing: 'border-box',
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-secondary)' }

// Тон кнопки одной рамкой-сокращением: смесь `border` и `borderColor` в одном style React не любит.
const toned = (t) => (t ? { background: t.background, color: t.color, border: `1px solid ${t.borderColor}` } : null)

export default function SitesToolbar({ rk, d, mayEdit, onDownloadCreatives, onExternal }) {
  const wr = d.buttons?.weborama
  const dsp = d.buttons?.dsp
  return (
    <span id={`rk-${rk.id}-ext`} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6,
      flexWrap: 'wrap' }}>
      {!!rk.volumes?.blocked && (
        <span title={rk.volumes.message} style={{ ...TOOL, cursor: 'default', color: 'var(--danger-fg)',
          border: '1px solid var(--danger-border)', background: 'var(--danger-tint)' }}>⛔ объёмы больше плана РК</span>
      )}
      {/* Архив чистых креативов сделки — тот же, что «Скачать» у документа «Креативы» в карточке (27.09.2026). */}
      {!!rk.creatives_ready && (
        <button type="button" style={TOOL} onClick={onDownloadCreatives}
          title={`Архив с чистыми архивами всех креативов сделки: ${rk.creatives_ready} шт.`}>
          ↓ Креативы {rk.creatives_ready}</button>
      )}
      {/* Паспорт сделки .xlsx (30.09.2026) и архив для площадок без нашего кода (29.09.2026). */}
      <PassportButton dealId={rk.deal_id} label="↓ Excel" style={TOOL} />
      <OffsiteButton dealId={rk.deal_id} style={TOOL} />
      {mayEdit && (
        <>
          <button type="button" style={{ ...TOOL, ...toned(BTN_TONE[wr?.state]) }}
            disabled={wr?.state === 'off'} onClick={() => onExternal('weborama')}
            title={btnTitle('Завести вставки в Weborama и забрать пиксели показа', wr, 'пиксель')}>
            Пиксель WR<CountBadge n={wr?.go} /></button>
          <button type="button" style={{ ...TOOL, ...toned(BTN_TONE[dsp?.state]) }}
            onClick={() => onExternal('dsp')}
            title={btnTitle('Выгрузить креативы согласованных площадок в DSP', dsp, 'выгрузка')}>
            В DSP<CountBadge n={dsp?.go} /></button>
        </>
      )}
    </span>
  )
}
