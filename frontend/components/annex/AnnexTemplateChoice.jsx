/**
 * Шаблон ДС на экране сборки (владелец 27.10.2026): какой шаблон собирает черновик и почему, выбор другого — шаблона договора или
 * базового формата, — и «сохранить текущий документ как шаблон договора» под новым именем. Выбор из накопительного списка с добавлением —
 * `ValuePopover`. Подтверждённый ДС заморожен: у него только подпись шаблона, без выбора.
 */
import { useState } from 'react'
import ValuePopover from '@/components/ValuePopover'

const chip = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 22, padding: '0 9px', borderRadius: 7, background: 'var(--violet-tint)', color: 'var(--violet-fg)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }

export function optionLabel(o) {
  return o.scope === 'base' ? `${o.title} · базовый формата` : `${o.title}${o.is_main ? ' · основной' : ''}`
}

export default function AnnexTemplateChoice({ choice, version, canEdit, onChoose, onSaveAs }) {
  const [pop, setPop] = useState(null)
  const cur = choice.options.find(o => o.id === choice.current_id)
  const def = choice.options.find(o => o.id === choice.default_id)
  const label = cur ? `${cur.title}${version ? ` · v${version}` : ''}` : 'шаблон не определён'
  if (!canEdit) return <span style={chip}>{label}<span style={{ fontWeight: 600, opacity: 0.75 }}>· {choice.why}</span></span>
  return (
    <>
      <span onClick={e => setPop(e.currentTarget.getBoundingClientRect())} title="Выбрать другой шаблон или сохранить этот документ как шаблон договора"
            style={{ ...chip, border: '1px dashed var(--violet-border)', cursor: 'pointer' }}>
        {label}<span style={{ fontWeight: 600, opacity: 0.75 }}>· {choice.why}</span>
      </span>
      {pop && (
        <ValuePopover anchor={pop} title="Шаблон ДС" value={choice.current_id}
                      options={choice.options.map(o => ({ value: o.id, label: optionLabel(o) }))}
                      clearLabel={def ? `— по умолчанию: ${def.title} —` : '— по умолчанию —'}
                      onPick={v => { setPop(null); onChoose(v) }} onClose={() => setPop(null)}
                      onAddNew={name => { setPop(null); onSaveAs(name) }}
                      addLabel={name => (name ? `+ Сохранить документ как шаблон «${name}»` : '+ Сохранить как шаблон — введите имя в поиске')} />
      )}
    </>
  )
}
