/**
 * «Документы для бухгалтерии» (Финансы, хендофф 05.11.2026): моста в 1С нет — бухгалтер берёт здесь данные заявки (комплект
 * мастер-сделки: УПД + счёт), выставляет документы в 1С и вносит обратно номера, даты, суммы и PDF. Внесены все комплекты
 * пакета — он сам уходит в «выставление», по счёту рождается операция «план поступлений». Не так — «Вернуть аккаунту».
 *
 * Сам экран — `components/onecDesk/AccountantDocs` (код хендоффа дословно); здесь только данные и обработчики.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import { pageAccess } from '@/lib/pageGuard'
import { can, getPermissions } from '@/lib/auth'
import { Modal, NoAccessScreen, btn, primaryBtn, inp, UI } from '@/components/salesTableKit'
import AccountantDocs from '@/components/onecDesk/AccountantDocs'
import DsViewer from '@/components/onecDesk/DsViewer'
import { deskApi, errText, asError, SLOT_OF } from '@/components/onecDesk/deskApi'

const MINUTE = 60_000

// Файлы комплекта с сервера кладём в черновик формы: экран берёт PDF и XML оттуда
function withFiles(data) {
  return {
    ...data,
    requests: data.requests.map(r => ({
      ...r,
      draft: r.status === 'wait' && (r.draft || Object.keys(r.files || {}).length) ? { ...(r.draft || {}), ...(r.files || {}) } : r.draft,
    })),
  }
}

/** Срок закрытия месяца: дата и время, отметка «закрыт». */
/** «Вернуть на переделку» (12.11.2026): окно в языке экрана, а не браузерный prompt. Что произойдёт — словами, причина обязательна. */
function RedoModal({ req, onSave, onClose }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const save = async () => {
    setBusy(true); setErr('')
    try { await onSave(reason.trim()); onClose() }
    catch (e) { setErr(errText(e, 'Не удалось вернуть на переделку')) } finally { setBusy(false) }
  }
  const later = ['выставление', 'ждём оплату', 'ждём сканы', 'архив'].includes(req.master_status)
  return (
    <Modal title={`Вернуть на переделку · ${req.code}`} width={520} onClose={onClose}
      footer={<>
        {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
        <span style={{ flex: 1 }} />
        <button type="button" style={btn(false)} onClick={onClose}>Отмена</button>
        <button type="button" style={{ ...primaryBtn, opacity: reason.trim() ? 1 : 0.5 }} disabled={busy || !reason.trim()} onClick={save}>Вернуть на переделку</button>
      </>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI, fontSize: 13 }}>
        <span style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          Ответ 1С по этому комплекту снимется, заявка вернётся в «Заявки на документы» — внесёте заново.
          {later ? ' Пакет вернётся на «ждём 1С» и пойдёт дальше сам, когда комплект внесут.' : ''} Остальные внесённые комплекты пакета не трогаем.
          Аккаунту и бухгалтерии уйдёт уведомление с причиной.
        </span>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Причина — что не так в документах</span>
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} maxLength={500} autoFocus
            placeholder="Например: в счёте не тот КПП покупателя" style={{ ...inp, height: 'auto', padding: '8px 10px', resize: 'vertical', fontFamily: UI }} />
        </label>
      </div>
    </Modal>
  )
}

function CloseEditor({ settings, onSave, onClose }) {
  const [at, setAt] = useState(settings.close_at.slice(0, 16))
  const [closed, setClosed] = useState(!!settings.month_closed)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const save = async () => {
    setBusy(true); setErr('')
    try { await onSave({ month: settings.month, close_at: `${at}:00+03:00`, closed }); onClose() }
    catch (e) { setErr(errText(e, 'Не удалось сохранить')) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Закрытие: ${settings.close_month} ${settings.month.slice(0, 4)}`} width={460} onClose={onClose}
      footer={<>
        <span style={{ flex: 1 }} />
        <button type="button" style={btn(false)} onClick={onClose}>Отмена</button>
        <button type="button" style={primaryBtn} disabled={busy || !at} onClick={save}>Сохранить</button>
      </>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI, fontSize: 13 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Срок закрытия (МСК)</span>
          <input type="datetime-local" value={at} onChange={e => setAt(e.target.value)} style={{ ...inp, width: 240 }} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input type="checkbox" checked={closed} onChange={e => setClosed(e.target.checked)} />
          <span>Месяц закрыт — даты в нём и раньше будут с предупреждением «период закрыт»</span>
        </label>
        {!!err && <span style={{ color: 'var(--danger-fg)' }}>{err}</span>}
      </div>
    </Modal>
  )
}

export default function OnecDeskPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [mayEdit, setMayEdit] = useState(false)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [now, setNow] = useState(() => Date.now())
  const [ds, setDs] = useState(null)               // { kitId, title } — ДС открыт модалкой
  const [closeEdit, setCloseEdit] = useState(false)
  const [archive, setArchive] = useState(null)
  const [mayRedo, setMayRedo] = useState(false)
  const [redo, setRedo] = useState(null)           // заявка, которую возвращаем на переделку    // «Вернуть на переделку» — по праву «Мастер-сделки · возврат стадии»     // заявки архивных пакетов — только по кнопке (владелец 12.11.2026)
  useEffect(() => { setMounted(true); setMayEdit(can(getPermissions(), 'onec_desk', 'edit')); setMayRedo(can(getPermissions(), 'master_deals_revert', 'edit')) }, [])
  const access = pageAccess(router.pathname, mounted)

  const load = useCallback(async () => {
    try { const d = await deskApi.board(); setData(withFiles(d)); setErr('') }
    catch (e) { setErr(errText(e, 'Не удалось загрузить заявки')) }
  }, [])
  useEffect(() => { if (access === 'ok') load() }, [access, load])
  // Ожидание и срок закрытия — живые: «сейчас» раз в минуту, данные — раз в минуту (новые заявки, ответы аккаунтов)
  useEffect(() => {
    if (access !== 'ok') return undefined
    const t = setInterval(() => { setNow(Date.now()); load() }, MINUTE)
    return () => clearInterval(t)
  }, [access, load])

  const loadArchive = useCallback(async () => {
    try { setArchive((await deskApi.board(true)).requests); setErr('') }
    catch (e) { setErr(errText(e, 'Не удалось загрузить архив')) }
  }, [])
  // архивная заявка, которую вернули на переделку, приходит уже с рабочей выдачей — дубля с тем же кодом быть не должно
  const view = useMemo(() => {
    if (!data || !archive) return data
    const live = new Set(data.requests.map(r => r.code))
    return { ...data, requests: [...data.requests, ...archive.filter(r => !live.has(r.code))] }
  }, [data, archive])
  const byCode = useMemo(() => Object.fromEntries((view?.requests || []).map(r => [r.code, r])), [view])
  const kit = code => byCode[code]?.kit_id
  const fileOf = (up, slot) => {
    const f = up?.files?.[slot]
    if (!f) throw new Error('Файл не сохранился — обновите страницу')
    return { id: f.id, name: f.filename, size: f.size || 0, url: null }
  }

  const handlers = {
    onUpload: (code, kind, file) => kind === 'dsScan'
      ? deskApi.dsScan(kit(code), file).then(() => { load(); return { name: file.name, size: file.size, url: null } }, asError('Не удалось приложить скан'))
      : deskApi.upload(kit(code), SLOT_OF[kind], file).then(up => fileOf(up, SLOT_OF[kind]), asError('Не удалось приложить файл')),
    onParseXml: (code) => deskApi.parseXml(kit(code)).catch(asError('XML не разобрался — заполните поля вручную')),
    onCheckNumber: (kind, no, code) => deskApi.checkNumber(kind, no, kit(code)).catch(() => null),
    onSaveDraft: (code, form) => (mayEdit ? deskApi.draft(kit(code), form) : Promise.reject(new Error('нет права'))),
    onSubmit: (code, form) => deskApi.submit(kit(code), form).then(out => {
      if (out.operation_error) setErr(out.operation_error)
      load()
      return out
    }, asError('Не удалось внести')),
    onReturn: (code, body) => deskApi.giveBack(kit(code), body).then(load, asError('Не удалось вернуть')),
    onNote: (code, text) => deskApi.comment(kit(code), text).catch(asError('Не удалось отправить')),
    onSeen: (code) => (mayEdit && kit(code) ? deskApi.seen(kit(code)).catch(() => null) : null),   // метки «ответ» — бухгалтера
    onOpenDeal: (code) => byCode[code] && router.push(`/accounts/master/${byCode[code].master}`),
    onExcel: (code) => byCode[code] && deskApi.xlsx(byCode[code].master, setErr),
    onDsFile: (code, what) => {
      const r = byCode[code]
      if (!r) return
      if (what === 'scan') deskApi.dsFile(r.kit_id, 'scan', setErr)
      else if (r.annex.external) deskApi.dsFile(r.kit_id, 'pdf', setErr)     // подписан вне системы — его файл
      else setDs({ kitId: r.kit_id, title: r.annex.title })
    },
    onOpenFile: (code, file) => file?.id && deskApi.download(kit(code), file.id, setErr),
    onRemoveFile: (code, kind, file) => (file?.id ? deskApi.removeFile(kit(code), file.id).catch(asError('Не удалось убрать файл')) : null),
    onEditClose: mayEdit ? () => setCloseEdit(true) : undefined,
    onReload: load,
    onLoadArchive: loadArchive,
    onInvoiceXml: (code) => byCode[code] && deskApi.invoiceXml(byCode[code].kit_id, setErr),
    onRedo: mayRedo ? (code) => byCode[code] && setRedo(byCode[code]) : undefined,
  }

  const head = <><Head><title>Закрывающие документы · Финансы | SIMB-AD ERP</title></Head><Navbar active="onec_desk" /></>
  if (access === 'denied') return <NoAccessScreen title="Закрывающие документы: нет доступа" what="Закрывающие документы" nav={head} />

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      {head}
      {!!err && <div style={{ maxWidth: 2500, margin: '12px auto 0', padding: '0 30px', fontSize: 13, color: 'var(--danger-fg)', fontFamily: UI }}>{err}</div>}
      {data
        ? <AccountantDocs data={view} now={now} archiveLoaded={!!archive} {...handlers} />
        : !err && <div style={{ padding: 40, color: 'var(--text-faint)', fontFamily: UI }}>Загрузка…</div>}
      {ds && <DsViewer kitId={ds.kitId} title={ds.title} onClose={() => setDs(null)} onError={setErr} />}
      {redo && <RedoModal req={redo} onClose={() => setRedo(null)}
        onSave={why => deskApi.redo(redo.kit_id, why).then(() => { setArchive(null); load() })} />}
      {closeEdit && data && <CloseEditor settings={data.settings} onClose={() => setCloseEdit(false)}
        onSave={body => deskApi.saveClose(body).then(st => setData(d => ({ ...d, settings: st })))} />}
    </div>
  )
}
