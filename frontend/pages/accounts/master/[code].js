/**
 * Мастер-сделка · раскладка закрытия — по дизайну docs/мастер сделка.zip (design_handoff_master_layout, 15.10.2026).
 * Экран между итоговыми сверками сделок и конструктором ДС: сколько ДС и комплектов закрывающих получится из пакета и как
 * они составлены. Настройки меняют черновик (предпросмотр — тот же серверный расчёт, `POST /master-deals/{код}/preview`),
 * «Сохранить раскладку» пишет. К раскладке возвращаются и правят, пока ДС пакета не выпущен; после выпуска — закреплена.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import Navbar from '@/components/Navbar'
import { UI, primaryBtn } from '@/components/salesTableKit'
import { rub2 } from '@/lib/salesFormat'
import MasterHeader from '@/components/master/MasterHeader'
import IssuePanel, { SHOWN as ISSUE_SHOWN } from '@/components/master/IssuePanel'
import { ScansPanel } from '@/components/master/docParts'
import { can, getPermissions } from '@/lib/auth'
import LayoutPanel from '@/components/master/LayoutPanel'
import DsCard from '@/components/master/DsCard'
import { CARD, Note, plural } from '@/components/master/kit'

/** ДС раскладки ↔ выпущенный ДС пакета: основной (или «всё в одном») — первый основной, допы — ДС допов. */
function docOf(m, ds) {
  const list = m.docs?.ds || []
  return ds.kind === 'addons' ? list.find(x => x.kind === 'extra') : list.find(x => x.kind === 'base')
}

export default function MasterDealPage() {
  const router = useRouter()
  const { code } = router.query
  const [m, setM] = useState(null)
  const [draft, setDraft] = useState(null)
  const [preview, setPreview] = useState(null)
  const [flash, setFlash] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [mayEdit, setMayEdit] = useState(false)
  const [picked, setPicked] = useState(null)          // скан какого документа грузим: a<annex_id> | u<upd_no>
  const pickScan = (k) => { setPicked(k); document.querySelector('[data-scans]')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }     // право «Мастер-сделки · редактирование»; без него — только смотреть
  useEffect(() => { setMayEdit(can(getPermissions(), 'master_deals', 'edit')) }, [])
  const seq = useRef(0)

  const apply = (data) => { setM(data); setDraft(data.settings); setPreview(null) }
  const load = useCallback(() => {
    if (!code) return
    api.get(`/master-deals/${code}`, auth()).then(r => { apply(r.data); setErr('') })
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить мастер-сделку'))
  }, [code])
  useEffect(() => { load() }, [load])
  // Вернулись на вкладку — перечитываем (сверки сделок могли завершиться), но не поверх несохранённого черновика.
  useRefreshOnReturn(load, { enabled: !preview })

  // Черновик → серверный предпросмотр; любая смена зажигает рамки ДС на 700 мс.
  const changeDraft = async (next) => {
    setDraft(next)
    setFlash(true); setTimeout(() => setFlash(false), 700)
    const my = ++seq.current
    try {
      const r = await api.post(`/master-deals/${code}/preview`, next, auth())
      if (my === seq.current) setPreview(r.data)
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось пересчитать раскладку') }
  }
  const call = async (fn) => {
    setBusy(true); setErr('')
    try { apply((await fn()).data); return true } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось сохранить'); return false } finally { setBusy(false) }
  }

  if (!m || !draft) {
    return (<><Navbar asPath="/accounts/dashboard" /><div style={{ padding: 24, fontFamily: UI, color: err ? 'var(--danger-fg)' : 'var(--text-muted)' }}>{err || 'Загружаю…'}</div></>)
  }
  const lay = preview || m.layout
  const locked = !!m.issued_ds || m.status !== 'черновик'      // ДС созданы — раскладка только для чтения до «Вернуть в раскладку»
  // Причины считает сервер (`to_annex_why`); черновик раскладки, не сохранённый, — своя причина.
  const why = [...(m.to_annex_why || []), preview && 'раскладка не сохранена'].filter(Boolean)
  const toggleMove = (id) => changeDraft({ ...draft, moved: draft.moved.includes(id) ? draft.moved.filter(x => x !== id) : [...draft.moved, id] })

  const issueShown = ISSUE_SHOWN.has(m.status)
  const docsRow = (
    <>
              {m.annexes.length ? (
                <>
                  <span style={{ fontSize: 12.5, color: 'var(--income-fg)' }}>ДС пакета созданы:</span>
                  {m.annexes.map(a => (
                    <Link key={a.id} href={`/directory/annexes/${a.id}`} style={{ fontWeight: 700, color: 'var(--accent)' }}>
                      {a.number}{a.confirmed ? ' ✓' : ' · черновик'}</Link>
                  ))}
                  {/* Подтвердить основной ДС и ДС допов одним действием: сначала проверка всех, потом номера по очереди. */}
                  {m.annexes.some(a => !a.confirmed) && (
                    <button type="button" disabled={busy} style={{ ...primaryBtn, marginLeft: 'auto' }}
                      onClick={() => { if (window.confirm('Подтвердить все ДС пакета? Номера будут заняты.')) call(() => api.post(`/master-deals/${m.code}/confirm-ds`, {}, auth())) }}>
                      Подтвердить ДС пакета</button>
                  )}
                  {!m.issued_ds && (
                    <button type="button" disabled={busy} style={{ ...primaryBtn, background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-card)' }}
                      onClick={() => { if (window.confirm('Удалить черновики ДС пакета и вернуться к правке раскладки?')) call(() => api.post(`/master-deals/${m.code}/revert`, {}, auth())) }}>
                      Вернуть в раскладку</button>
                  )}
                </>
              ) : (
                <>
                  {why.length ? (
                    <span style={{ fontSize: 12.5, color: 'var(--warning-text)' }}>Перейти нельзя: {why.join(', ')}</span>
                  ) : (
                    <span style={{ fontSize: 12.5, color: 'var(--income-fg)' }}>
                      Раскладка готова · {lay.ds.length} ДС, {lay.upd_count} {plural(lay.upd_count, ['комплект', 'комплекта', 'комплектов'])}, {rub2(lay.total_net)} до НДС</span>
                  )}
                  <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-faint)' }}>Номер ДС занимается при подтверждении в конструкторе ДС.</span>
                  <button type="button" disabled={!!why.length || busy} style={{ ...primaryBtn, opacity: why.length ? 0.5 : 1, cursor: why.length ? 'not-allowed' : 'pointer' }}
                    onClick={async () => {
                      setBusy(true); setErr('')
                      try {
                        const r = await api.post(`/master-deals/${m.code}/to-annex`, {}, auth())
                        apply(r.data)
                        if (r.data.annexes?.[0]) router.push(`/directory/annexes/${r.data.annexes[0].id}`)
                      } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось создать ДС') } finally { setBusy(false) }
                    }}>В конструктор ДС →</button>
                </>
              )}
    </>
  )

  return (
    <>
      <Head><title>{`Закрытие ${m.code}`} · Аккаунты | SIMB-AD ERP</title></Head>
      <Navbar asPath="/accounts/dashboard" />
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: '18px 24px 40px', fontFamily: UI }}>
        <MasterHeader m={m} locked={locked} busy={busy}
          canEdit={mayEdit} onApply={apply}
          onScans={() => document.querySelector('[data-scans]')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
          onStatus={mayEdit ? (to) => call(() => api.post(`/master-deals/${m.code}/status`, { to }, auth())) : null}
          onAdd={(c) => call(() => api.post(`/master-deals/${m.code}/deals`, { deal_id: c.id }, auth()))}
          onRemove={(d) => { if (window.confirm(`Убрать ${d.code} из пакета ${m.code}?`)) call(() => api.delete(`/master-deals/${m.code}/deals/${d.id}`, auth())) }} />
        {!!err && <div style={{ marginBottom: 12, fontSize: 12.5, color: 'var(--danger-fg)' }}>{err}</div>}
        <div style={{ display: 'grid', gridTemplateColumns: '330px minmax(0,1fr)', gap: 16, alignItems: 'start' }}>
          <LayoutPanel m={m} draft={draft} preview={preview} locked={locked} busy={busy}
            onDraft={changeDraft}
            onSave={() => call(() => api.put(`/master-deals/${m.code}/settings`, draft, auth()))}
            onRevert={() => { setDraft(m.settings); setPreview(null) }}
            onStartNo={(no) => call(() => api.put(`/master-deals/${m.code}/start-no`, { no }, auth()))}
            onTakePrev={() => changeDraft({ ...m.prev.settings, moved: [] })} />
          <div>
            {!m.deals.length ? (
              <div style={{ ...CARD, padding: 28, border: '1px dashed var(--border-hover)', boxShadow: 'none', color: 'var(--text-muted)', textAlign: 'center' }}>
                ДС пока не из чего собрать — добавьте сделку в пакет.</div>
            ) : !lay.lines ? (
              <div style={{ ...CARD, padding: 28, border: '1px dashed var(--border-hover)', boxShadow: 'none', color: 'var(--text-muted)', textAlign: 'center' }}>
                Нет позиций для ДС.</div>
            ) : (
              <>
                {m.docs?.scans?.need && <div style={{ marginBottom: 14 }}><ScansPanel m={m} picked={picked} setPicked={setPicked} canEdit={mayEdit} onChanged={apply} /></div>}
                {lay.ds.map(ds => (
                  <DsCard key={ds.kind} ds={ds} vat={lay.vat_rate} locked={locked} moved={draft.moved || []}
                    separate={!!draft.addons_separate && lay.has_paid_extras} flash={flash} onMove={toggleMove}
                    doc={docOf(m, ds)} paper={!!m.docs?.paper} code={m.code} onPick={pickScan}
                    basis={(m.upds || []).filter(u => u.annex_id === docOf(m, ds)?.annex_id)} busy={busy} onBasis={apply} />
                ))}
              </>
            )}
            <IssuePanel m={m} busy={busy} canEdit={mayEdit}
              onSigned={() => call(() => api.post(`/master-deals/${m.code}/issue/signed`, {}, auth()))}
              onSent={(track_no) => call(() => api.post(`/master-deals/${m.code}/issue/sent`, { track_no }, auth()))}
              footer={docsRow} />
            {/* Первичный ДС пакета (выпущен на старте на план, владелец 16.10.2026): не подписан — пересоберём его по факту с тем же
                номером; подписан — не трогаем, закрываем по факту, расхождение видно. Подпись перепроверяется при нажатии. */}
            {!!m.primary && (
              m.primary.error ? <Note tone="bad" style={{ marginBottom: 14 }}>{m.primary.error}</Note>
                : m.primary.branch === 'signed' ? (
                  <Note tone="warn" style={{ marginBottom: 14 }}>
                    <b>Первичный {m.primary.number} подписан</b> ({m.primary.source}) на {rub2(m.primary.gross)} с НДС — ДС не трогаем.
                    Закрываем по факту {rub2(m.primary.closing_gross)}
                    {m.primary.diff < 0 ? `, недокрут ${rub2(m.primary.diff)}` : ''}. Комплекты УПД привяжутся к этому ДС.
                    {m.primary.conflict && <b> Источники подписи расходятся — проверьте.</b>}
                  </Note>
                ) : (
                  <Note tone="ok" style={{ marginBottom: 14 }}>
                    <b>Первичный {m.primary.number} не подписан</b> ({m.primary.source}) — важен только номер: при «В конструктор ДС» он
                    пересоберётся по факту ({rub2(m.primary.closing_gross)} с НДС), номер и дата сохранятся.
                  </Note>
                )
            )}
            {/* ДС пакета: с «выставления» — нижней строкой панели «Выставление» (владелец 19.10.2026: «эти 2 блока в один»), до — своей карточкой */}
            {!issueShown && <div style={{ ...CARD, display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', flexWrap: 'wrap' }}>{docsRow}</div>}
          </div>
        </div>
      </div>
    </>
  )
}
