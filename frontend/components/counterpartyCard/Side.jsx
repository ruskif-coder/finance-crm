/**
 * Правая колонка карточки контрагента v2 (440px, хендофф «контрикZ»): реквизиты (ИНН и КПП первыми, «копировать» — наименование,
 * ИНН/КПП, ОГРН и адрес одним блоком), свёрнутые счета; подписанты — проверка как «Готовность к ДС» договора; условия по умолчанию и
 * плашка «СК по контрагенту» (только с правом «Агентские условия»).
 */
import { useState } from 'react'
import Link from 'next/link'
import { MONO } from '@/components/salesTableKit'
import { daysUntil } from '@/lib/dates'
import SignersPanel from '@/components/signers/SignersPanel'
import { cap, Notice, link, panel, btnSm } from '@/components/contractCard/ui'


function Row({ k, v, mono }) {
  return (
    <span style={{ display: 'flex', gap: 14, padding: '7px 0', borderTop: '1px solid var(--border-row)', fontSize: 12.5 }}>
      <span style={{ flex: '0 0 110px', color: 'var(--text-muted)' }}>{k}</span>
      <span style={{ flex: 1, minWidth: 0, textAlign: 'right', overflowWrap: 'anywhere', fontFamily: mono ? MONO : 'inherit', color: v ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{v || '—'}</span>
    </span>
  )
}

function Bank({ b }) {
  const [open, setOpen] = useState(false)
  return (
    <span style={{ display: 'flex', flexDirection: 'column', borderTop: '1px solid var(--border-row)' }}>
      <span onClick={() => setOpen(!open)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', cursor: 'pointer', fontSize: 12.5 }}>
        <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{b.bank_name || 'Банк'}</span>
        <span style={{ fontFamily: MONO, color: 'var(--text-muted)' }}>…{(b.rs || '').slice(-4)}</span>
        <span style={{ color: 'var(--text-faint)' }}>{open ? '▴' : '▾'}</span>
      </span>
      {open && <span style={{ paddingBottom: 6 }}><Row k="Р/с" v={b.rs} mono /><Row k="К/с" v={b.ks} mono /><Row k="БИК" v={b.bik} mono /></span>}
    </span>
  )
}

export function Requisites({ c }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    const lines = [c.name, `ИНН ${c.inn || '—'} / КПП ${c.kpp || '—'}`, c.ogrn ? `ОГРН ${c.ogrn}` : null, c.address || null].filter(Boolean)
    navigator.clipboard.writeText(lines.join('\n')).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1600) })
  }
  const sameFact = c.address_fact && c.address && c.address_fact.trim() === c.address.trim()
  const banks = (c.bank_accounts || []).filter(b => b.bank_name || b.rs)
  return (
    <section style={{ ...panel, gap: 6 }}>
      <span style={{ display: 'flex', alignItems: 'center' }}>
        <span style={cap}>Реквизиты</span>
        <button type="button" onClick={copy} style={{ ...btnSm, marginLeft: 'auto' }}>{copied ? 'скопировано ✓' : 'копировать'}</button>
      </span>
      <Row k="ИНН" v={c.inn} mono /><Row k="КПП" v={c.kpp} mono /><Row k="ОГРН" v={c.ogrn} mono /><Row k="ОКПО" v={c.okpo} mono />
      <Row k="Юр. адрес" v={c.address} /><Row k="Факт. адрес" v={sameFact ? 'совпадает с юридическим' : c.address_fact} />
      <Row k="Телефон" v={c.phone} mono /><Row k="Email" v={c.email} /><Row k="ЭДО" v={c.edo_id} mono /><Row k="Примечание" v={c.note} />
      {!!banks.length && <span style={{ ...cap, paddingTop: 10 }}>Счета · {banks.length}</span>}
      {banks.map((b, i) => <Bank key={b.id || i} b={b} />)}
    </section>
  )
}

/** Подписант по умолчанию годится для ДС: есть должность и основание, доверенность не истекла — та же проверка, что «Готовность к ДС». */
function signerProblem(signers) {
  const d = (signers || []).find(s => s.is_default && !s.is_archived)
  if (!d) return 'подписанта нет'
  const miss = [!(d.signer_position || '').trim() && 'должности', !(d.signer_basis || '').trim() && 'основания'].filter(Boolean)
  if (miss.length) return `у подписанта нет ${miss.join(' и ')}`
  if (d.valid_until && daysUntil(String(d.valid_until).slice(0, 10)) < 0) return 'доверенность подписанта истекла'
  return null
}

export function Signers({ c, canEdit, onChange }) {
  const problem = signerProblem(c.signers)
  return (
    <section style={{ ...panel, gap: 6, border: `1px solid ${problem ? 'var(--danger-border)' : 'var(--border-card)'}` }}>
      <span style={cap}>Подписанты</span>
      {problem && <Notice tone="danger">ДС по договорам контрагента не соберутся: {problem}. Укажите ниже — «изменить» или «+ Подписант».</Notice>}
      <SignersPanel counterpartyId={c.id} signers={c.signers} canEdit={canEdit} onChange={onChange} />
    </section>
  )
}

export function Defaults({ c, sk, showSk, canEdit, onEdit }) {
  return (
    <section style={{ ...panel, gap: 6 }}>
      <span style={{ display: 'flex', alignItems: 'center' }}>
        <span style={cap}>Условия по умолчанию</span>
        {canEdit && <button type="button" onClick={onEdit} style={{ ...btnSm, marginLeft: 'auto' }}>изменить</button>}
      </span>
      <Row k="НДС приход" v={c.vat_rate_income != null ? `${c.vat_rate_income} %` : null} mono />
      <Row k="НДС расход" v={c.vat_rate_expense != null ? `${c.vat_rate_expense} %` : null} mono />
      <Row k="Статья прихода" v={c.default_article_income} /><Row k="Статья расхода" v={c.default_article_expense} />
      {showSk && (
        <span style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8, padding: '10px 12px', background: 'var(--violet-tint)', border: '1px solid var(--violet-border)', borderRadius: 12 }}>
          <span style={{ ...cap, color: 'var(--violet-fg)', fontWeight: 700 }}>СК по контрагенту</span>
          {sk ? (
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 700, color: 'var(--violet-fg)' }}>{sk.percent} %</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--violet-fg)' }}>{sk.mode}</span>
              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>· агентство «{sk.agency}»</span>
            </span>
          ) : <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>правила на агентство контрагента нет — СК задаётся по договору или рекламодателю</span>}
          <Link href="/sales/agency-terms" style={{ ...link, fontSize: 12, fontWeight: 600 }}>Агентские условия →</Link>
        </span>
      )}
    </section>
  )
}
