import { useState, useEffect } from 'react'
import { makeApi as api } from '@/lib/http'
import { fmtFull, fmtDateShort } from '@/lib/salesFormat'
import { todayMsk } from '@/lib/dates'
import { sanMoney, moneyNum } from '@/lib/money'
import { MONO, UI, inp, btn, btnSm, Modal } from '@/components/salesTableKit'

// ─── Цепочка частичных оплат (решение владельца 23.09.2026) ─────────────────────────
//
// Плановую операцию закрывают по частям ОДНИМ действием «Частичная оплата»: сервер сам
// создаёт оплаченную часть со ссылкой на материнскую и уменьшает остаток у материнской
// (backend/app/routers/operation_chains.py). Раньше это делали руками — копия и правка
// двух сумм, — и ошибка в одной из них выглядела как настоящий долг.
//
// Все компоненты объявлены на модульном уровне: поля ввода внутри компонента,
// рождённого в теле страницы, теряли бы фокус на каждом символе.

const tok = () => localStorage.getItem('token')
const PLAN = ['ПЛАН ПОСТУПЛЕНИЙ', 'ПЛАН ОПЛАТ']


const errOf = (e, fallback) => e?.response?.data?.detail || fallback

/** Метка в реестре: операция — часть цепочки или материнская с частями. */
export function ChainMark({ op }) {
  if (op.parent_operation_id) {
    return (
      <span title={`Частичная оплата по операции #${op.parent_operation_id}`}
        style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--accent)',
          background: 'var(--accent-tint)', borderRadius: 6, padding: '1px 5px', whiteSpace: 'nowrap' }}>
        ↳ #{op.parent_operation_id}
      </span>
    )
  }
  if (op.parts_count > 0) {
    return (
      <span title={`Частичных оплат: ${op.parts_count}`}
        style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--warning-fg)',
          background: 'var(--warning-tint)', borderRadius: 6, padding: '1px 5px', whiteSpace: 'nowrap' }}>
        частей {op.parts_count}
      </span>
    )
  }
  return null
}

function ChainList({ chain, canEdit, busy, onUnlink }) {
  const row = (m, isRoot) => (
    <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '70px 80px 1fr 130px 90px', gap: 8,
      alignItems: 'center', fontSize: 12.5, padding: '4px 0', borderBottom: '1px solid var(--border-row)' }}>
      <span style={{ fontFamily: MONO, fontWeight: 700 }}>#{m.id}</span>
      <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{fmtDateShort(m.date)}</span>
      <span style={{ color: 'var(--text-secondary)' }}>{m.status}{isRoot ? ' · материнская' : ''}</span>
      <span style={{ fontFamily: MONO, textAlign: 'right' }}>{fmtFull(m.amount)}</span>
      <span style={{ textAlign: 'right' }}>
        {!isRoot && canEdit && (
          <button type="button" disabled={busy} onClick={() => onUnlink(m.id)}
            title="Сделать операцию самостоятельной — если её связали по ошибке"
            style={btnSm(false)}>Отвязать</button>
        )}
      </span>
    </div>
  )
  return (
    <div>
      {row(chain.root, true)}
      {chain.parts.map(p => row(p, false))}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 8, fontSize: 12.5, color: 'var(--text-secondary)' }}>
        <span>по договору <b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{fmtFull(chain.total)}</b></span>
        <span>оплачено <b style={{ fontFamily: MONO, color: 'var(--income)' }}>{fmtFull(chain.paid)}</b></span>
        <span>остаток <b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{fmtFull(chain.remaining)}</b></span>
      </div>
    </div>
  )
}

function PartialPaymentForm({ op, banks, busy, onSubmit }) {
  const remaining = Number(op.income) > 0 ? Number(op.income) : Number(op.expense) || 0
  const [f, setF] = useState({ amount: '', date: todayMsk(), bank: op.bank || banks[0] || '' })
  const amt = moneyNum(f.amount)
  const valid = amt > 0 && amt <= remaining && f.date && f.bank
  const closes = valid && Math.abs(amt - remaining) < 0.005
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11.5, color: 'var(--text-muted)' }}>
        Сумма оплаты
        <input value={f.amount} onChange={e => setF(s => ({ ...s, amount: sanMoney(e.target.value) }))}
          inputMode="decimal" placeholder={`до ${fmtFull(remaining)}`}
          style={{ ...inp, width: 170, fontFamily: MONO }} />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11.5, color: 'var(--text-muted)' }}>
        Дата оплаты
        <input type="date" value={f.date} onChange={e => setF(s => ({ ...s, date: e.target.value }))}
          style={{ ...inp, width: 150 }} />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11.5, color: 'var(--text-muted)' }}>
        Банк
        <select value={f.bank} onChange={e => setF(s => ({ ...s, bank: e.target.value }))}
          style={{ ...inp, width: 150, cursor: 'pointer' }}>
          {/* Банк операции, которого нет в списке, — тоже вариант: иначе список показывал
              первый банк, а на сервер уходил банк операции (ревью 23.09.2026). */}
          {(op.bank && !banks.includes(op.bank) ? [op.bank, ...banks] : banks)
            .map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </label>
      <button type="button" disabled={busy || !valid} onClick={() => onSubmit({ amount: amt, date: f.date, bank: f.bank })}
        style={{ ...btn(true), opacity: busy || !valid ? 0.5 : 1, cursor: busy || !valid ? 'default' : 'pointer' }}>
        {busy ? 'Провожу…' : closes ? 'Закрыть остаток' : 'Провести оплату'}
      </button>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', flexBasis: '100%' }}>
        {closes
          ? 'Сумма равна остатку — операция закроется целиком, новой части не будет.'
          : `Оплаченная часть станет отдельной операцией «оплачено», здесь останется план на остаток.`}
      </span>
    </div>
  )
}

/** Блок в форме правки: цепочка операции и «Частичная оплата» у плановой. */
export function ChainPanel({ op, canEdit, banks, onChanged }) {
  const inChain = !!op.parent_operation_id || op.parts_count > 0
  const isPlan = PLAN.includes(op.status)
  const [chain, setChain] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!inChain) { setChain(null); return undefined }
    let alive = true
    api(tok()).get(`/operations/${op.id}/chain`)
      .then(r => { if (alive) setChain(r.data) })
      .catch(e => { if (alive) setErr(errOf(e, 'Цепочка оплат не загрузилась')) })
    return () => { alive = false }
  }, [op.id, inChain])

  if (!inChain && !(isPlan && canEdit)) return null

  const run = async (fn, fallback) => {
    setBusy(true); setErr('')
    try { await fn(); onChanged() } catch (e) { setErr(errOf(e, fallback)) } finally { setBusy(false) }
  }
  const pay = (body) => run(() => api(tok()).post(`/operations/${op.id}/partial-payment`, body),
    'Не удалось провести оплату')
  const unlink = (id) => run(() => api(tok()).post(`/operations/${id}/unlink-parent`),
    'Не удалось отвязать операцию')

  return (
    <div style={{ marginTop: 14, padding: '12px 14px', borderRadius: 12, border: '1px solid var(--border-card)',
      background: 'var(--bg-subtle)', display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
      {inChain && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Цепочка частичных оплат</div>
          {chain ? <ChainList chain={chain} canEdit={canEdit} busy={busy} onUnlink={unlink} />
            : !err && <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Загрузка…</div>}
        </div>
      )}
      {isPlan && canEdit && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Частичная оплата</div>
          <PartialPaymentForm op={op} banks={banks} busy={busy} onSubmit={pay} />
        </div>
      )}
      {!!err && <div role="alert" style={{ fontSize: 12.5, color: 'var(--danger)' }}>{err}</div>}
    </div>
  )
}

/** Принудительное удаление материнской операции — с паролем. Пароль проверяет сервер. */
// Подтверждение удаления цепочки паролем. По умолчанию — принудительное удаление одной
// материнской; `submit(pwd)` подменяет запрос: так же спрашивает пароль массовое удаление
// цепочки целиком (решение владельца 23.09.2026 — цепочка удаляется только с паролем).
export function ForceDeleteDialog({ opId, message, onClose, onDone, submit, title, confirmLabel }) {
  const [pwd, setPwd] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async () => {
    if (!pwd || busy) return
    setBusy(true); setErr('')
    try {
      if (submit) await submit(pwd)
      else await api(tok()).post(`/operations/${opId}/force-delete`, { password: pwd })
      onDone()
    } catch (e) {
      setErr(e?.response?.status === 403 ? 'Неверный пароль' : errOf(e, 'Не удалось удалить'))
      setBusy(false)
    }
  }
  return (
    <Modal title={title || `Удалить операцию #${opId}?`} width={460} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose} style={btn(false)}>Отмена</button>
        <button type="button" disabled={!pwd || busy} onClick={go}
          style={{ ...btn(true), background: 'var(--danger)', opacity: !pwd || busy ? 0.5 : 1 }}>
          {busy ? 'Удаляю…' : (confirmLabel || 'Удалить принудительно')}
        </button>
      </>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13, lineHeight: 1.45 }}>
        <span>{message}</span>
        <span style={{ color: 'var(--text-muted)' }}>Подтвердите паролем от своей учётной записи.</span>
        <input type="password" autoFocus value={pwd} onChange={e => setPwd(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') go() }} placeholder="Ваш пароль" style={inp} />
        {!!err && <span role="alert" style={{ color: 'var(--danger)' }}>{err}</span>}
      </div>
    </Modal>
  )
}
