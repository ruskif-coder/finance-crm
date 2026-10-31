/**
 * Карточка договора (владелец 28.10.2026, вид — хендофф «договорZ» 28.10.2026): шапка с режимом правки и плашкой СК; основная колонка —
 * стороны, готовность к ДС, ДС, закрытие, сделки, агентские условия, площадки; правая (440px) — шаблоны ДС, деньги, ОРД, юр запросы,
 * журнал. Право — «Договоры → просмотр»; блок приходит с сервера только при праве своего раздела (`app/contract_card`), иначе его нет.
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import { UI } from '@/components/salesTableKit'
import api, { auth } from '@/lib/http'
import { can, getPermissions } from '@/lib/auth'
import { saveBlob, filenameFromResponse } from '@/lib/download'
import { errText } from '@/lib/loadError'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import BaseTemplateModal from '@/components/annex/BaseTemplateModal'
import Header from '@/components/contractCard/Header'
import Parties from '@/components/contractCard/Parties'
import Readiness from '@/components/contractCard/Readiness'
import NewTemplateModal from '@/components/contractCard/NewTemplateModal'
import { Annexes, Masters, Deals, Sk, Publishers } from '@/components/contractCard/Tables'
import { Templates, Money, Ord, Legal, Audit } from '@/components/contractCard/Side'
import { btnGhost, Notice } from '@/components/contractCard/ui'

const scrollTo = (id) => { const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }) }

export default function ContractCard() {
  const router = useRouter()
  const { id } = router.query
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [tpl, setTpl] = useState(null)              // окно шаблонов договора: { templateId? }
  const [newTpl, setNewTpl] = useState(null)        // окно «Новый шаблон ДС»: { sourceId? }
  const [openSide, setOpenSide] = useState(null)    // чей список подписантов открыт
  const [editReq, setEditReq] = useState(0)
  const [perm, setPerm] = useState({ edit: false, tpl: false, signer: false })
  useEffect(() => { const p = getPermissions(); setPerm({ edit: can(p, 'contracts', 'edit'), tpl: can(p, 'annex_templates', 'create'), signer: can(p, 'counterparties', 'edit') }) }, [])
  const [editing, setEditing] = useState(false)
  const [drafts, setDrafts] = useState({})          // должность и основание подписантов, правленные в режиме правки: { сторона: поля }

  const load = useCallback(async () => {
    if (!id) return
    try { setD((await api.get(`/contracts/${id}/card`, auth())).data); setErr('') }
    catch (e) { setErr(errText(e)) }
  }, [id])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load, { enabled: !tpl && !newTpl })

  const file = async () => {
    try {
      const r = await api.get(`/contracts/${id}/download`, { ...auth(), responseType: 'blob' })
      saveBlob(r.data, filenameFromResponse(r) || 'Договор')
    } catch (_) { setErr('Не удалось скачать файл договора') }
  }
  /** Подписант стороны договора; `null` — по умолчанию юрлица. Проверка готовности перечитывается вместе с карточкой. */
  const chooseSigner = async (side, signerId) => {
    try { await api.put(`/signers/contract/${id}/${encodeURIComponent(side)}`, { signer_id: signerId }, auth()); await load() }
    catch (e) { setErr(errText(e)) }
  }
  /** Подписанты, правленные в режиме правки шапки, — тем же «Сохранить». Пишется подписанту юрлица (`PUT /signers/{id}`). */
  const saveSigners = async () => {
    for (const p of d.parties) {
      const v = drafts[p.side], s = p.options.find(o => o.id === p.signer_id)
      if (!v || !s || (v.signer_position === (s.signer_position || '') && v.signer_basis === (s.signer_basis || ''))) continue
      await api.put(`/signers/${s.id}`, { signer_position: v.signer_position.trim() || null, signer_basis: v.signer_basis.trim() || null }, auth())
    }
  }
  const onEditChange = (on) => { setEditing(on); setDrafts({}) }
  /** Тумблер «Приложение / ДС» — сразу, без режима правки шапки: это одно значение, а не форма. */
  const saveWord = async (word) => {
    try { await api.put(`/contracts/${id}`, { annex_word: word }, auth()); await load() }
    catch (e) { setErr(errText(e)) }
  }

  /** Клик по красной проверке готовности — к месту правки. */
  const go = (target) => {
    if (target.startsWith('signer:')) { scrollTo('parties'); setOpenSide(target.slice(7)); return }
    if (target.startsWith('counterparty:')) { router.push(`/directory/counterparties/${target.slice(13)}`); return }
    if (target === 'edit') { window.scrollTo({ top: 0, behavior: 'smooth' }); setEditReq(n => n + 1); return }
    scrollTo(target)
  }

  const c = d && d.contract
  const tplWin = (extra) => setTpl({ id: c.id, number: c.contract_number, format: c.cooperation_format, ...extra })
  return (
    <div style={{ fontFamily: UI, minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Head><title>{c ? `Договор № ${c.contract_number || c.id}` : 'Договор'} | SIMB-AD ERP</title></Head>
      <Navbar />
      {/* Ширина до 1600 и прижато к левому краю экрана (владелец 28.10.2026: 1920 на экране 2560 при масштабе 125 % — «куча места»). */}
      <div style={{ boxSizing: 'border-box', padding: '22px 28px 40px' }}>
        <div style={{ width: '100%', maxWidth: 1600, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <span><button type="button" onClick={() => router.push('/directory/contracts')} style={{ ...btnGhost, height: 30, fontSize: 12.5 }}>← К реестру договоров</button></span>
          {err && <Notice tone="danger">{err}</Notice>}
          {!d && !err && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>}
          {c && <Header c={c} sk={d.sk_summary} showSk={'sk_summary' in d} canEdit={perm.edit} onSaved={load} onSk={() => scrollTo('sk')} onFile={file} editRequest={editReq}
                    onEditChange={onEditChange} extraSave={perm.signer ? saveSigners : undefined} />}
          {d && (
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 440px', gap: 14, alignItems: 'start' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
                <Parties parties={d.parties} canEdit={perm.edit} open={openSide} onOpen={setOpenSide} onChoose={chooseSigner}
                         editing={editing && perm.signer} drafts={drafts} onDraft={setDrafts} />
                <Readiness checks={d.readiness} onGo={go} />
                {d.annexes && <Annexes data={d.annexes} />}
                {d.masters && <Masters rows={d.masters} />}
                {d.deals && <Deals rows={d.deals} />}
                {d.sk && <Sk data={d.sk} />}
                {d.publishers && <Publishers rows={d.publishers} outer={c.ord_kind === 'outer'} />}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
                {d.templates && <Templates rows={d.templates} total={d.annexes ? d.annexes.items.length : d.templates.reduce((s, t) => s + t.annexes, 0)}
                                           canCreate={perm.tpl} onNew={() => setNewTpl({})} onCopy={sid => setNewTpl({ sourceId: sid })}
                                           onOpen={tid => tplWin({ templateId: tid })} onAll={() => tplWin({})}
                                           word={c.annex_word} canEditWord={perm.edit} onWord={saveWord} />}
                {d.money && <Money data={d.money} counterpartyId={c.counterparty && c.counterparty.id} />}
                {d.ord && <Ord data={d.ord} />}
                {d.legal && <Legal rows={d.legal} />}
                {d.audit && <Audit rows={d.audit} />}
              </div>
            </div>
          )}
        </div>
      </div>
      <BaseTemplateModal open={!!tpl} contract={tpl} onClose={() => { setTpl(null); load() }} />
      {newTpl && d && d.templates && (
        <NewTemplateModal contractId={c.id} templates={d.templates} sourceId={newTpl.sourceId} onClose={() => setNewTpl(null)}
                          onCreated={tid => { setNewTpl(null); load(); tplWin({ templateId: tid }) }} />
      )}
    </div>
  )
}
