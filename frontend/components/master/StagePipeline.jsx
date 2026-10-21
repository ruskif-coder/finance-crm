/**
 * Конвейер стадий пакета (хендофф «реестр + карточка», 19.10.2026): полоса сегментов — пройденные приглушены, текущая шире
 * и в цвете стадии; под ней «сейчас: …» с ролью и кнопка шага справа. Стадии — ЭТОГО пакета (`m.sequence`: у ЭДО нет
 * «ждём сканы»). Кнопка: синяя — шаг доступен (тот же `step`, что в строке реестра); серая — ждём внешнюю сторону.
 */
import { useState } from 'react'
import Link from 'next/link'
import { STEP } from '@/lib/masterSteps'
import { MASTER_TONE } from '@/lib/masterStatus'
import { MONO } from '@/components/salesTableKit'
import StepConfirm from '@/components/master/StepConfirm'
import { lineBtn } from '@/components/master/kit'

const TAIL = { 'ждём сканы': 'оплачено, без сканов в архив не уехать', 'ждём оплату': 'документы у клиента' }
const WAITING = { 'согласование': 'ДС у юриста и на подтверждении', 'ждём 1С': 'Ждём документы из 1С', 'ждём оплату': 'Ждём оплату' }

export default function StagePipeline({ m, canEdit, onDone, onScans }) {
  const [asking, setAsking] = useState(false)
  const seq = m.sequence || []
  const cur = seq.indexOf(m.status)
  const step = canEdit ? STEP[m.step] : null
  const t = m.todo
  // «прикрепить сканы подписанных · не хватает 3» → заголовок и пояснение, как в макете
  const [head, ...rest] = (t?.text || '').split(' · ')
  const tail = [rest.join(' · '), TAIL[m.status]].filter(Boolean).join(' — ')
  const btn = lineBtn({ size: 'lg' })
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 14, alignItems: 'center', padding: '12px 14px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 12 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9, minWidth: 0 }}>
      <div style={{ display: 'flex', gap: 3, minWidth: 0 }}>
        {seq.map((s, i) => {
          const tone = MASTER_TONE[s] || MASTER_TONE['черновик']
          const now = i === cur
          return (
            <span key={s} style={{ flex: now ? '2.2 1 0' : '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={{ height: 7, borderRadius: 2, background: now ? tone[3] : i < cur ? 'var(--accent-soft)' : 'var(--border-inner)' }} />
              <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                color: now ? tone[2] : i < cur ? 'var(--text-muted)' : 'var(--text-faint)', fontWeight: now ? 700 : 500 }}>{s}</span>
            </span>
          )
        })}
      </div>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>сейчас</span>
        <b style={{ fontSize: 13.5, fontWeight: 700, color: t?.tone === 'bad' ? 'var(--danger-fg)' : 'var(--text-primary)' }}>{t ? head : 'пакет закрыт'}</b>
        {!!tail && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{tail}</span>}
        {!!t && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{t.who}</span>}
      </span>
      </div>
      <span data-pop-root style={{ alignSelf: 'center', position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        {step && !step.expand ? (
          <>
            <button type="button" onClick={() => setAsking(a => !a)} style={{ ...btn, border: 0, background: step.quiet ? 'var(--income-fg)' : 'var(--accent)', color: 'var(--on-accent)' }}>{step.label}</button>
            {asking && <StepConfirm code={m.code} step={step} onClose={() => setAsking(false)} onDone={(v) => { setAsking(false); onDone(v) }} />}
          </>
        ) : step && step.expand ? (
          <button type="button" onClick={onScans} style={{ ...btn, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)' }}>Сканы ниже ↓</button>
        ) : m.step === 'contract' ? (
          <Link href={`/directory/contracts?q=${encodeURIComponent(m.contract?.number || '')}`} style={{ ...btn, display: 'inline-flex', alignItems: 'center', border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--danger-fg)', textDecoration: 'none' }}>в договор</Link>
        ) : WAITING[m.status] ? (
          <span style={{ ...btn, display: 'inline-flex', alignItems: 'center', border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-muted)', cursor: 'default' }}>{WAITING[m.status]}</span>
        ) : null}
      </span>
    </div>
  )
}
