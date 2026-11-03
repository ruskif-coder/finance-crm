/**
 * «Загрузить внешний ДС» в реестре приложений (владелец 03.11.2026).
 *
 * Внешний ДС рабочий, как наш, — значит, он живёт в пакете мастер-сделки. Кнопка даёт выбрать пакет, берёт его черновик ДС, а
 * если черновика ещё нет — создаёт его из раскладки той же ручкой, что «В конструктор ДС →», и открывает карточку черновика
 * сразу с формой «Подписан вне системы» (`?external=1`). Новых ручек нет: реестр пакетов, карточка пакета и «В конструктор ДС».
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import { MONO, Modal, inp, btn, primaryBtn } from '@/components/salesTableKit'

// Внешний ДС грузят в пакет, где ДС ещё не подтверждены: «черновик» (ДС создаст кнопка) и «согласование» (черновик уже есть).
const OPEN = ['черновик', 'согласование']

export default function ExternalUploadPick() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open || rows) return
    api.get('/master-deals/registry/list', auth())
      .then(r => setRows((r.data?.rows || []).filter(x => OPEN.includes(x.status))))
      .catch(() => setErr('Пакеты не загрузились'))
  }, [open, rows])

  const pick = async (code) => {
    setBusy(code); setErr('')
    try {
      const m = (await api.get(`/master-deals/${code}`, auth())).data
      let draft = (m.annexes || []).find(a => !a.confirmed)
      if (!draft && m.status === 'черновик') {
        const made = (await api.post(`/master-deals/${code}/to-annex`, {}, auth())).data
        draft = (made.annexes || [])[0]
      }
      if (!draft) { setErr(`${code}: черновика ДС нет — ДС пакета уже подтверждены`); return }
      router.push(`/directory/annexes/${draft.id}?external=1`)
    } catch (e) {
      setErr(`${code}: ${e?.response?.data?.detail || 'не получилось'}`)
    } finally { setBusy('') }
  }

  const s = q.trim().toLowerCase()
  const shown = (rows || []).filter(r => !s || [r.code, r.counterparty, r.payer, r.contract?.number, ...(r.brands || []), ...(r.advertisers || [])]
    .some(v => String(v || '').toLowerCase().includes(s)))
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} title="Клиент подписал свой ДС — загрузить его в пакет мастер-сделки"
              style={{ ...btn(false), height: 34 }}>Загрузить внешний ДС</button>
      {open && (
        <Modal title="Загрузить внешний ДС — выберите пакет" width={720} onClose={() => setOpen(false)}
               summary="Внешний ДС ложится в пакет мастер-сделки: по нему потом УПД и 1С, как по нашему. Нет черновика ДС — создадим его из раскладки."
               footer={<div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                 {!!err && <span style={{ color: 'var(--danger-fg)', fontSize: 12.5, marginRight: 'auto' }}>{err}</span>}
                 <button onClick={() => setOpen(false)} style={{ ...btn(false), marginLeft: 'auto' }}>Закрыть</button>
               </div>}>
          <div style={{ padding: '14px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Код пакета, клиент, бренд, договор…" style={{ ...inp, width: '100%' }} />
            {rows === null && !err && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</span>}
            {rows !== null && !shown.length && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Пакетов с неподтверждённым ДС нет</span>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 420, overflowY: 'auto' }}>
              {shown.map(r => (
                <div key={r.code} style={{ display: 'grid', gridTemplateColumns: '90px minmax(0,1fr) 120px 110px', gap: 10, alignItems: 'center', padding: '8px 10px', border: '1px solid var(--border-card)', borderRadius: 10 }}>
                  <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--accent)' }}>{r.code}</span>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.counterparty || r.payer || '—'}</span>
                    <span style={{ display: 'block', fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {(r.brands || []).join(', ') || '—'} · договор {r.contract?.number || '—'} · {r.period || ''}
                    </span>
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.status}{(r.ds || []).length ? ` · ${r.ds.length} ДС` : ''}</span>
                  <button onClick={() => pick(r.code)} disabled={!!busy} style={{ ...primaryBtn, height: 32, padding: '0 12px' }}>
                    {busy === r.code ? '…' : 'Выбрать'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
