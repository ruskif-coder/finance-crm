/**
 * Справочник ОРД — зеркало кабинета МедиаСкаута.
 *
 * Живёт в контуре «Аккаунты», а не в Справочниках: обвязка ОРД — часть работы
 * аккаунта, а не самостоятельный справочник первичных данных (решение владельца
 * 2026-08-25). Подвкладку контура рисует Nav.js из карты, свой компонент не нужен.
 *
 * Две вкладки. Изначальные договоры — своя сущность, первое звено чужой цепочки, у нас
 * ей места в основных справочниках нет. Наши договоры показываются только те, где есть
 * отметка ОРД: две трети реестра к ОРД отношения не имеют, и показывать их здесь было
 * бы шумом.
 *
 * Юрлиц отдельной вкладкой нет — они живут в Контрагентах с колонкой ord_client_id.
 */
import { useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar from '../../components/Navbar'
import { UI, MONO, card, inp, primaryBtn, btnSm, th, td } from '../../components/salesTableKit'
import { fmtDateFull } from '../../lib/salesFormat'
import api, { auth } from '../../lib/http'
import { can, getPermissions } from '../../lib/auth'

const TABS = [
  { key: 'initial', label: 'Изначальные договоры' },
  { key: 'contracts', label: 'Наши договоры в ОРД' },
]

export default function OrdDirectory() {
  const [tab, setTab] = useState('initial')
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [stat, setStat] = useState(null)
  const [mayEdit, setMayEdit] = useState(false)

  // localStorage не существует на сервере — читаем право только после монтирования.
  useEffect(() => { setMayEdit(can(getPermissions(), 'ord', 'edit')) }, [])

  const load = async () => {
    setErr('')
    try {
      const url = tab === 'initial' ? '/ord/initial' : '/ord/contracts'
      const r = await api.get(url, { ...auth(), params: tab === 'initial' && q ? { q } : {} })
      setRows(r.data)
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить') }
  }
  useEffect(() => { load() }, [tab])

  const upload = async (e) => {
    const files = e.target.files
    if (!files?.length) return
    // Кабинет отдаёт три файла с говорящими именами — раскладываем по полям сами,
    // чтобы не заставлять человека выбирать трижды.
    const fd = new FormData()
    for (const f of files) {
      const n = f.name.toLowerCase()
      if (n.includes('изначальн')) fd.append('initial', f)
      else if (n.includes('доходн')) fd.append('final', f)
      else if (n.includes('расходн')) fd.append('outer', f)
    }
    setBusy(true); setErr(''); setStat(null)
    try {
      const r = await api.post('/ord/import', fd, auth())
      setStat(r.data); load()
    } catch (e2) { setErr(e2.response?.data?.detail || 'Не удалось загрузить файл') }
    finally { setBusy(false); e.target.value = '' }
  }

  return (
    <>
      <Head><title>ОРД · Справочник</title></Head>
      <Navbar />
      <div style={{ padding: '18px 22px', fontFamily: UI }}>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14 }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={btnSm(tab === t.key)}>
              {t.label}
            </button>
          ))}
          {tab === 'initial' && (
            <input value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && load()}
              placeholder="рекламодатель, исполнитель, номер или ИНН"
              style={{ ...inp, width: 300, marginLeft: 8 }} />
          )}
          <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
            строк: {rows.length}
          </span>
          {mayEdit && (
            <label style={{ ...primaryBtn, cursor: busy ? 'default' : 'pointer' }}>
              {busy ? 'Загрузка…' : 'Загрузить выгрузку'}
              <input type="file" accept=".xlsx" multiple onChange={upload}
                style={{ display: 'none' }} disabled={busy} />
            </label>
          )}
        </div>

        {!!err && (
          <div style={{ ...card, padding: 12, marginBottom: 12, color: 'var(--dot-overdue)' }}>
            {err}
          </div>
        )}

        {!!stat && (
          <div style={{ ...card, padding: 12, marginBottom: 12, fontSize: 13 }}>
            <div style={{ color: 'var(--text-muted)' }}>
              Прочитано строк: изначальных {stat.read_initial ?? 0},
              доходных {stat.read_final ?? 0}, расходных {stat.read_outer ?? 0}.
            </div>
            <div style={{ marginTop: 4 }}>
              Заведено: изначальных {stat.initial}, связей {stat.links},
              договоров помечено {stat.contracts}, контрагентов сопоставлено по ИНН {stat.clients}.
            </div>
            {/* «Заведено» по нулям на повторной загрузке — норма: импорт
                идемпотентен. «Прочитано» по нулям при непустом файле — нет: значит
                приложен не тот файл, или кабинет переименовал колонку (см.
                предупреждение ниже) — по одним «заведено 0» эти два случая было не
                различить. */}
            {!!stat.warnings?.length && (
              <div style={{ marginTop: 8, color: 'var(--dot-current-dz)', fontSize: 12 }}>
                предупреждений {stat.warnings.length} — договоры ОРД, которых нет
                в нашем реестре, незнакомые значения справочников, и листы, где
                прочитанные строки не распознаны ни разу
              </div>
            )}
          </div>
        )}

        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto', padding: '12px 4px 0' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                {tab === 'initial' ? (
                  <tr>
                    <th style={th}>Рекламодатель</th><th style={th}>Исполнитель</th>
                    <th style={th}>Номер</th><th style={th}>Дата</th>
                    <th style={th}>Вид</th><th style={th}>Статус</th>
                  </tr>
                ) : (
                  <tr>
                    <th style={th}>Номер</th><th style={th}>Дата</th>
                    <th style={th}>Контрагент</th><th style={th}>Вид</th>
                    <th style={th}>Статус в ОРД</th>
                  </tr>
                )}
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={6} style={{ ...td, color: 'var(--text-muted)' }}>
                    {tab === 'initial'
                      ? 'Пусто. Загрузите выгрузку изначальных договоров из кабинета ОРД.'
                      : 'Ни у одного договора нет отметки ОРД.'}
                  </td></tr>
                )}
                {rows.map(r => tab === 'initial' ? (
                  <tr key={r.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{r.advertiser?.name || '—'}</td>
                    <td style={td}>{r.contractor?.name || '—'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.number || 'б/н'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.date ? fmtDateFull(r.date) : '—'}</td>
                    <td style={td}>{r.subject_type || '—'}</td>
                    <td style={td}>{r.status || '—'}</td>
                  </tr>
                ) : (
                  <tr key={r.id}>
                    <td style={{ ...td, fontFamily: MONO }}>{r.number || 'б/н'}</td>
                    <td style={{ ...td, fontFamily: MONO }}>{r.date ? fmtDateFull(r.date) : '—'}</td>
                    <td style={td}>{r.counterparty || '—'}</td>
                    <td style={td}>{r.ord_kind === 'outer' ? 'расходный' : 'доходный'}</td>
                    <td style={td}>{r.ord_status || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  )
}
