import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '../../components/Navbar'
import SettingsTabs, { settingsSectionAllowed } from '../../components/SettingsTabs'
import { MONO, UI, card, inp, sel, primaryBtn } from '../../components/salesTableKit'
import api, { auth } from '../../lib/http'

// ── Остатки по банкам — отдельная страница раздела «Настройки» ──
// Стартовый остаток по счёту + обороты (из /settings/bank-balances), привязка юрлица
// к счёту и реквизиты компании-плательщика для выгрузки платёжек.
const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))

// Поля реквизитов компании-плательщика (для экспорта платёжек).
const REQ_FIELDS = [
  { key: 'company_name', label: 'Наименование организации', full: true },
  { key: 'inn',            label: 'ИНН' },
  { key: 'kpp',            label: 'КПП' },
  { key: 'rs',             label: 'Расчётный счёт (Р/С)' },
  { key: 'bik',            label: 'БИК банка' },
  { key: 'bank_full_name', label: 'Наименование банка', full: true },
  { key: 'bank_city',      label: 'Город банка' },
  { key: 'ks',             label: 'Корр. счёт (К/С)' },
]

export default function SettingsBalances() {
  const router = useRouter()

  // Остатки по банкам
  const [banks, setBanks] = useState([])
  const [totalBalance, setTotalBalance] = useState(0)
  const [editing, setEditing] = useState({})
  const [saving, setSaving] = useState({})
  const [loading, setLoading] = useState(true)

  // Реквизиты компании для экспорта платёжек — { "АльфаБанк": { inn, kpp, rs, bik, ... } }
  const [companyReq, setCompanyReq] = useState({})
  const [editingReq, setEditingReq] = useState({})
  const [savingReq, setSavingReq] = useState({})
  const [reqOpen, setReqOpen] = useState({})           // { "АльфаБанк": true } — раскрыта секция

  // Юрлица (is_own_company) для привязки к банковскому счёту
  const [ownCompanies, setOwnCompanies] = useState([])  // [{ id, name, inn }, ...]
  const [bankOwnCompany, setBankOwnCompany] = useState({})  // { "АльфаБанк": id|null }
  const [savingOwnCompany, setSavingOwnCompany] = useState({})

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    if (!settingsSectionAllowed('balances')) { router.push('/dashboard'); return }
    loadBalances()
  }, [])

  const loadBalances = async () => {
    setLoading(true)
    try {
      const [balRes, ownRes] = await Promise.all([
        api.get('/settings/bank-balances', auth()),
        api.get('/counterparties/own', auth()),
      ])
      setBanks(balRes.data.banks)
      setTotalBalance(balRes.data.total_balance)
      setOwnCompanies(ownRes.data)
      const ed = {}
      const cr = {}
      const er = {}
      const boc = {}
      balRes.data.banks.forEach(b => {
        ed[b.bank] = b.opening_balance
        cr[b.bank] = {
          company_name: b.company_name || '',
          inn: b.inn || '',
          kpp: b.kpp || '',
          rs: b.rs || '',
          bik: b.bik || '',
          bank_full_name: b.bank_full_name || '',
          bank_city: b.bank_city || '',
          ks: b.ks || '',
        }
        er[b.bank] = { ...cr[b.bank] }
        boc[b.bank] = b.own_company_id || ''
      })
      setEditing(ed)
      setCompanyReq(cr)
      setEditingReq(er)
      setBankOwnCompany(boc)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveBankOwnCompany = async (bank) => {
    setSavingOwnCompany(prev => ({ ...prev, [bank]: true }))
    try {
      const ownId = bankOwnCompany[bank]
      await api.patch('/settings/bank-balances/own-company', {
        bank,
        own_company_id: ownId ? parseInt(ownId, 10) : null,
      }, auth())
      await loadBalances()
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении юрлица')
    } finally {
      setSavingOwnCompany(prev => ({ ...prev, [bank]: false }))
    }
  }

  const handleSave = async (bank) => {
    setSaving(prev => ({ ...prev, [bank]: true }))
    try {
      await api.post('/settings/bank-balances', {
        bank,
        opening_balance: parseFloat(editing[bank]) || 0
      }, auth())
      await loadBalances()
    } catch (e) {
      alert('Ошибка при сохранении')
    } finally {
      setSaving(prev => ({ ...prev, [bank]: false }))
    }
  }

  const handleSaveReq = async (bank) => {
    setSavingReq(prev => ({ ...prev, [bank]: true }))
    try {
      await api.put('/settings/company-requisites', { bank, ...editingReq[bank] }, auth())
      await loadBalances()
    } catch (e) {
      alert(e.response?.data?.detail || 'Ошибка при сохранении реквизитов')
    } finally {
      setSavingReq(prev => ({ ...prev, [bank]: false }))
    }
  }

  // стили — общий модуль components/salesTableKit
  const label = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 600, color: 'var(--text-muted)' }

  return (
    <>
      <Head><title>Остатки | Настройки</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SettingsTabs active="balances" />

        {/* Итоговая карточка */}
        <div style={{ ...card, padding: '20px 22px', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
          <div>
            <div style={{ ...label, marginBottom: 6 }}>Общий остаток по всем счетам</div>
            <div style={{ fontSize: 30, fontWeight: 700, color: totalBalance >= 0 ? 'var(--income)' : 'var(--danger)' }}>{fmt(totalBalance)} ₽</div>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', textAlign: 'right' }}>
            <div>Стартовый остаток + поступления − списания</div>
            <div style={{ marginTop: 4 }}>по всем банкам (только оплаченные)</div>
          </div>
        </div>

        {loading ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Загрузка…</div> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {banks.map(b => (
              <div key={b.bank} style={{ ...card, padding: '20px 22px', borderLeft: '4px solid var(--accent)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 20, flexWrap: 'wrap' }}>

                  {/* Название банка */}
                  <div style={{ minWidth: 120 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: 'var(--accent-tint)', color: 'var(--accent)' }}>
                      {b.bank}
                    </span>
                  </div>

                  {/* Стартовый остаток — редактируемый */}
                  <div style={{ flex: 1, minWidth: 180 }}>
                    <div style={{ ...label, marginBottom: 6 }}>Стартовый остаток</div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input
                        type="number"
                        value={editing[b.bank] ?? b.opening_balance}
                        onChange={e => setEditing(prev => ({ ...prev, [b.bank]: e.target.value }))}
                        style={{ ...inp, width: '100%', textAlign: 'right' }}
                      />
                      <button
                        onClick={() => handleSave(b.bank)}
                        disabled={saving[b.bank]}
                        style={{ ...primaryBtn, opacity: saving[b.bank] ? 0.6 : 1 }}>
                        {saving[b.bank] ? '…' : 'Сохранить'}
                      </button>
                    </div>
                  </div>

                  {/* Обороты */}
                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ ...label, marginBottom: 6 }}>Поступило</div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--income)' }}>{fmt(b.total_income)}</div>
                    </div>
                    <div>
                      <div style={{ ...label, marginBottom: 6 }}>Списано</div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--danger)' }}>{fmt(b.total_expense)}</div>
                    </div>
                    <div>
                      <div style={{ ...label, marginBottom: 6 }}>Текущий остаток</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: b.balance >= 0 ? 'var(--income)' : 'var(--danger)' }}>{fmt(b.balance)} ₽</div>
                    </div>
                  </div>

                </div>

                {/* Юрлицо-плательщик для этого банка */}
                {b.bank !== 'Наличные' && ownCompanies.length > 0 && (
                  <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 13, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>🏢 Юрлицо:</span>
                    <select
                      value={bankOwnCompany[b.bank] || ''}
                      onChange={e => setBankOwnCompany(prev => ({ ...prev, [b.bank]: e.target.value }))}
                      style={{ ...sel, fontSize: 13, padding: '6px 10px', minWidth: 180 }}
                    >
                      <option value="">— не привязано —</option>
                      {ownCompanies.map(cp => (
                        <option key={cp.id} value={cp.id}>{cp.name}{cp.inn ? ` (ИНН ${cp.inn})` : ''}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleSaveBankOwnCompany(b.bank)}
                      disabled={savingOwnCompany[b.bank]}
                      style={{ ...primaryBtn, opacity: savingOwnCompany[b.bank] ? 0.6 : 1 }}
                    >
                      {savingOwnCompany[b.bank] ? '…' : 'Сохранить'}
                    </button>
                  </div>
                )}

                {/* Реквизиты компании для выгрузки платёжек — раскрывающийся блок */}
                {b.bank !== 'Наличные' && (
                  <div style={{ marginTop: 14, borderTop: '1px solid var(--border-row)', paddingTop: 14 }}>
                    <button
                      onClick={() => setReqOpen(prev => ({ ...prev, [b.bank]: !prev[b.bank] }))}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 13,
                               color: 'var(--accent)', padding: 0, display: 'flex', alignItems: 'center', gap: 4, fontFamily: UI, fontWeight: 600 }}
                    >
                      {reqOpen[b.bank] ? '▾' : '▸'} Реквизиты компании-плательщика
                      {editingReq[b.bank]?.inn && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> · ИНН {editingReq[b.bank].inn}</span>}
                    </button>
                    {reqOpen[b.bank] && (
                      <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px' }}>
                        {REQ_FIELDS.map(f => (
                          <div key={f.key} style={f.full ? { gridColumn: '1 / -1' } : {}}>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>{f.label}</div>
                            <input
                              style={{ ...inp, width: '100%', padding: '6px 10px', fontSize: 13 }}
                              value={editingReq[b.bank]?.[f.key] || ''}
                              onChange={e => setEditingReq(prev => ({
                                ...prev,
                                [b.bank]: { ...prev[b.bank], [f.key]: e.target.value }
                              }))}
                            />
                          </div>
                        ))}
                        <div style={{ gridColumn: '1 / -1', marginTop: 4 }}>
                          <button
                            onClick={() => handleSaveReq(b.bank)}
                            disabled={savingReq[b.bank]}
                            style={{ ...primaryBtn, opacity: savingReq[b.bank] ? 0.6 : 1 }}
                          >
                            {savingReq[b.bank] ? 'Сохранение…' : 'Сохранить реквизиты'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
