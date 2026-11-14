/**
 * Кнопка пакета в «Моих сделках»: шаг реестра (`ActionCell`), а когда у шага нет кнопки строки (подтвердить ДС, создать ДС — они
 * делаются в расхлопе пакета), основная кнопка названа по «что сделать» и ведёт туда, где это делается.
 */
import { STEP } from '@/lib/masterSteps'
import { BTN_STEP } from '@/components/master/registry/kit'
import ActionCell from '@/components/master/registry/ActionCell'

const cap1 = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t)

export default function PackAction({ p, canEdit, asking, setAsking, onDone, onGo }) {
  if (canEdit && !STEP[p.step] && p.todo?.text) {
    return <button type="button" onClick={onGo} title="Открыть, где это делается" style={{ ...BTN_STEP, whiteSpace: 'nowrap' }}>{cap1(p.todo.text)}</button>
  }
  return (
    <ActionCell r={p} canEdit={canEdit} open={asking === p.code} onAsk={() => setAsking(a => (a === p.code ? null : p.code))}
      onClose={() => setAsking(null)} onDone={onDone} onExpand={onGo} />
  )
}
