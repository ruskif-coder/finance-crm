/**
 * «Стороны» карточки договора (владелец 28.10.2026, вид — хендофф «договорZ»): заказчик и исполнитель — реквизиты юрлица и подписант.
 * Подписанта выбирают из подписантов юрлица (клик по ФИО, право «Договоры → правка»); «— по умолчанию юрлица —» снимает выбор.
 * Чего не хватает для ДС — та же проверка, что у конструктора ДС; рамка карточки стороны тогда красная.
 * `open` / `onOpen` — какая сторона показывает список: его открывает и проверка готовности по клику на красный чип.
 */
import { useEffect } from 'react'
import Link from 'next/link'
import { MONO, PortalPopover } from '@/components/salesTableKit'
import { fmtDateFull } from '@/lib/salesFormat'
import { box, cap, h2, note, Notice, link, fieldInp } from '@/components/contractCard/ui'


/** Должность и основание подписанта в режиме правки карточки (владелец 28.10.2026). Пишется подписанту юрлица — значит, во все его договоры. */
function SignerEdit({ s, draft, onDraft }) {
  const v = draft || { signer_position: s.signer_position || '', signer_basis: s.signer_basis || '' }
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingTop: 3 }}>
      <input value={v.signer_position} onChange={e => onDraft({ ...v, signer_position: e.target.value })} placeholder="Должность: Генеральный директор" style={{ ...fieldInp, height: 30 }} />
      <input value={v.signer_basis} onChange={e => onDraft({ ...v, signer_basis: e.target.value })} placeholder="Основание: Устава / доверенности № 5 от 01.01.2026" style={{ ...fieldInp, height: 30 }} />
      <span style={{ fontSize: 11, color: 'var(--warning-fg)' }}>меняется у подписанта юрлица — во всех договорах, где он подписывает</span>
    </span>
  )
}

const role = (s) => `${s.signer_position || 'должность не указана'}, на основании ${s.signer_basis || '—'}${s.valid_until ? ` · до ${fmtDateFull(s.valid_until)}` : ''}`

function Options({ p, onPick }) {
  const row = (key, name, sub, on, pick) => (
    <span key={key} onClick={pick} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '7px 9px', borderRadius: 8, background: on ? 'var(--accent-tint)' : 'transparent', cursor: 'pointer' }}>
      <span style={{ fontSize: 12.5, fontWeight: on ? 700 : 600, color: on ? 'var(--accent-fg)' : 'var(--text-primary)' }}>{name}</span>
      {sub && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sub}</span>}
    </span>
  )
  return (
    <>
      {row('def', '— по умолчанию юрлица —', null, p.source !== 'договор', () => onPick(null))}
      {p.options.map(o => row(o.id, `${o.is_default ? '★ ' : ''}${o.director_name || '—'}`, role(o), p.source === 'договор' && o.id === p.signer_id, () => onPick(o.id)))}
      <span style={{ padding: '7px 9px 3px', marginTop: 4, borderTop: '1px solid var(--border-inner)', fontSize: 11, color: 'var(--text-muted)' }}>подписанты ведутся в карточке контрагента</span>
    </>
  )
}

function Side({ p, canEdit, open, onOpen, onChoose, editing, draft, onDraft }) {
  const cp = p.counterparty
  const s = p.options.find(o => o.id === p.signer_id)
  const bad = p.missing.length > 0
  const pick = (v) => { onOpen(null); onChoose(p.side, v) }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7, padding: '12px 14px', background: 'var(--bg-subtle)', border: `1px solid ${bad ? 'var(--danger-border)' : 'var(--border-card)'}`, borderRadius: 12, minWidth: 0 }}>
      <span style={cap}>{p.side === 'заказчик' ? 'Заказчик' : 'Исполнитель — мы'}</span>
      {!cp ? <span style={{ fontSize: 13, color: 'var(--danger-fg)' }}>юрлицо не указано</span> : (
        <>
          <Link href={`/directory/counterparties/${cp.id}`} style={{ ...link, fontSize: 14, fontWeight: 700 }}>{cp.name}</Link>
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>ИНН {cp.inn || '—'} · КПП {cp.kpp || '—'} · ОГРН {cp.ogrn || '—'}</span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{cp.address || 'юр. адрес не указан'}</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingTop: 9, borderTop: '1px solid var(--border-inner)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={cap}>Подписант</span>
              {p.source && (
                <span style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 6px', borderRadius: 5, fontSize: 10.5, fontWeight: 700,
                               background: p.source === 'договор' ? 'var(--accent-tint)' : 'var(--bg-card)', color: p.source === 'договор' ? 'var(--accent-fg)' : 'var(--text-muted)' }}>
                  {p.source === 'договор' ? 'выбран в договоре' : 'по умолчанию юрлица'}
                </span>
              )}
            </span>
            <span data-pop-root style={{ alignSelf: 'flex-start', position: 'relative' }}>
              <span onClick={canEdit && p.options.length ? () => onOpen(open ? null : p.side) : undefined}
                    title={canEdit ? 'Выбрать подписанта из подписантов юрлица' : undefined}
                    style={{ fontSize: 13.5, fontWeight: 700, cursor: canEdit ? 'pointer' : 'default', borderBottom: canEdit ? '1px dashed var(--border-hover)' : 'none' }}>
                {s ? s.director_name || '—' : 'подписанта нет'}
              </span>
              <PortalPopover open={open} minWidth={300} style={{ padding: 6 }}><Options p={p} onPick={pick} /></PortalPopover>
            </span>
            {editing && s
              ? <SignerEdit s={s} draft={draft} onDraft={onDraft} />
              : <span style={{ fontSize: 12, color: s ? 'var(--text-secondary)' : 'var(--text-muted)' }}>{s ? role(s) : 'заведите подписанта в карточке контрагента'}</span>}
          </div>
        </>
      )}
      {bad && <Notice tone="danger">Для ДС не хватает: {p.missing.join(', ')}</Notice>}
    </div>
  )
}

// editing — режим правки шапки: должность и основание подписанта — инпутами (право «Контрагенты → правка»); drafts — { сторона: поля }.
export default function Parties({ parties, canEdit, open, onOpen, onChoose, editing = false, drafts = {}, onDraft }) {
  useEffect(() => {
    if (!open) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) onOpen(null) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [open, onOpen])
  return (
    <section id="parties" style={{ ...box, padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={h2}>Стороны</span>
        <span style={note}>реквизиты — из карточек юрлиц; подписант выбирается из подписантов юрлица</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {parties.map(p => <Side key={p.side} p={p} canEdit={canEdit} open={open === p.side} onOpen={onOpen} onChoose={onChoose}
                                editing={editing} draft={drafts[p.side]} onDraft={v => onDraft({ ...drafts, [p.side]: v })} />)}
      </div>
    </section>
  )
}
