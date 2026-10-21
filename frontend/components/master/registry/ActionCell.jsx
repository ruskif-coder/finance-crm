/**
 * Колонка «Действие»: шаг-отметка с подтверждением, «в договор» или «открыть».
 * Часть реестра мастер-сделок (`pages/finance/master-deals.js`), вынесено при аудите 20.10.2026.
 */
import Link from 'next/link'
import { MONO } from '@/components/salesTableKit'
import { STEP } from '@/lib/masterSteps'
import StepConfirm from '@/components/master/StepConfirm'
import { BTN_ARCH, BTN_LINK, BTN_STEP } from '@/components/master/registry/kit'

export default function ActionCell({ r, canEdit, open, onAsk, onClose, onDone, onExpand }) {
  const step = canEdit ? STEP[r.step] : null
  return (
    <span data-pop-root style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4, minWidth: 0, position: 'relative' }}>
      {step ? (
        <span style={{ position: 'relative', display: 'inline-flex' }}>
          <button type="button" title={step.title} onClick={step.expand ? onExpand : onAsk} style={step.quiet ? BTN_ARCH : BTN_STEP}>{step.label}</button>
          {open && !step.expand && <StepConfirm code={r.code} step={step} onClose={onClose} onDone={onDone} />}
        </span>
      ) : r.step === 'contract' ? (
        <Link href={`/directory/contracts?q=${encodeURIComponent(r.contract?.number || '')}`} title="Открыть договор: не задано ЭДО или бумага"
          style={{ ...BTN_LINK, color: 'var(--danger-fg)', fontWeight: 700 }}>в договор</Link>
      ) : r.status !== 'архив' ? (
        <Link href={`/accounts/master/${r.code}`} title="Открыть карточку пакета" style={BTN_LINK}>открыть</Link>
      ) : null}
      {!!r.moved && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.04em', color: 'var(--income-fg)', whiteSpace: 'nowrap' }}>✓ перешёл в «{r.moved}»</span>}
    </span>
  )
}
