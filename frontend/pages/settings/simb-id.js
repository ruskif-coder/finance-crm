/**
 * Настройки → SIMB ID (владелец 05.10.2026).
 *
 * Коэффициенты для отчётов клиенту по РК: частота (уники = показы ÷ частота дня) и CTR,
 * у каждого базовое значение и поправка ±%. Одни на все РК. Значение дня считается из этих
 * настроек один раз и хранится — поэтому правка здесь действует на новые дни, а уже
 * выгруженные отчёты не меняются. Экран только админа (`/api/settings/simb-id`).
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import SettingsTabs from '@/components/SettingsTabs'
import api, { auth } from '@/lib/api'
import { card, inp, btn, CAP, MONO, UI } from '@/components/salesTableKit'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const FIELDS = [
  { group: 'Частота', hint: 'показов на одного человека; уники = показы ÷ частота дня',
    base: { key: 'freq_base', label: 'Базовое значение', step: '0.1', unit: '' },
    dev: { key: 'freq_dev_pct', label: 'Поправка в обе стороны', unit: '± %' } },
  { group: 'CTR', hint: 'доля кликов от показов',
    base: { key: 'ctr_base', label: 'Базовое значение', step: '0.01', unit: '%' },
    dev: { key: 'ctr_dev_pct', label: 'Поправка в обе стороны', unit: '± %' } },
]
const NUM_INP = { ...inp, width: 120, fontFamily: MONO, textAlign: 'right' }

// Поле объявлено на уровне модуля: внутри компонента фокус слетал бы на каждом символе.
function NumField({ f, value, onChange }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{f.label}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <input type="number" min="0" step={f.step || '1'} style={NUM_INP}
          value={value ?? ''} onChange={e => onChange(f.key, e.target.value)} />
        <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{f.unit}</span>
      </span>
    </label>
  )
}

export default function SimbIdSettings() {
  const [form, setForm] = useState(null)
  const [saved, setSaved] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.get('/settings/simb-id', auth())
      .then(r => { setForm(r.data); setSaved(r.data); setErr('') })
      .catch(e => setErr(e?.response?.status === 403
        ? 'Экран доступен только администратору.' : 'Не удалось загрузить настройки.'))
  }, [])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(() => { if (!form || JSON.stringify(form) === JSON.stringify(saved)) load() })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const dirty = !!form && JSON.stringify(form) !== JSON.stringify(saved)

  const save = async () => {
    setBusy(true)
    try {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v)]))
      const r = await api.put('/settings/simb-id', body, auth())
      setForm(r.data); setSaved(r.data); setErr('')
    } catch (e) {
      setErr(e?.response?.status === 422
        ? 'Проверьте значения: частота больше нуля, CTR и поправки — от 0 до 100.'
        : (e?.response?.data?.detail || 'Не удалось сохранить.'))
    }
    setBusy(false)
  }

  return (
    <>
      <Head><title>SIMB ID · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ width: 1600, maxWidth: '100%', background: 'var(--bg-canvas)',
                    minHeight: '100vh', padding: '20px 26px 48px', fontFamily: UI }}>
        <SettingsTabs active="simb_id" />
        <div style={{ ...card, padding: '18px 22px', maxWidth: 760 }}>
          <div style={{ ...CAP }}>Коэффициенты отчётов клиенту</div>
          <p style={{ margin: '0 0 18px', fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Одни на все РК. Значение каждого дня считается из этих настроек один раз и хранится:
            изменения действуют на новые дни, уже выгруженные отчёты не меняются.
          </p>
          {!!err && <div style={{ marginBottom: 14, fontSize: 12.5, color: 'var(--danger-fg)' }}>{err}</div>}
          {!form && !err && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>}
          {!!form && FIELDS.map(g => (
            <div key={g.group} style={{ padding: '14px 0', borderTop: '1px solid var(--border-row)' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
                <b style={{ fontSize: 14 }}>{g.group}</b>
                <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{g.hint}</span>
              </div>
              <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
                <NumField f={g.base} value={form[g.base.key]} onChange={set} />
                <NumField f={g.dev} value={form[g.dev.key]} onChange={set} />
              </div>
            </div>
          ))}
          {!!form && (
            <div style={{ display: 'flex', gap: 10, paddingTop: 14, borderTop: '1px solid var(--border-row)' }}>
              <button style={btn(true)} disabled={!dirty || busy} onClick={save}>
                {busy ? 'Сохраняю…' : 'Сохранить'}
              </button>
              {dirty && <button style={btn(false)} disabled={busy} onClick={() => setForm(saved)}>Отменить</button>}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
