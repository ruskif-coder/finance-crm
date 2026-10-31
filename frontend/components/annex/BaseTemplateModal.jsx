/**
 * «Шаблоны ДС» — окно (спринт 2, 14.10.2026; макет 13.10 — по дизайну `docs/дс 1.zip`). Данные — с сервера (`/api/annex-templates`).
 *
 * Два входа в одно окно:
 *  — из реестра приложений («Базовые шаблоны»): список базовых шаблонов, форматы, новый вариант, правка юристом;
 *  — из реестра договоров и «Юр запросов» (`contract`): шаблоны договора — именованные, их несколько, один может быть основным
 *    (27.10.2026), — и базовый его формата (просмотр); у шаблона договора версии, история, «базовый изменился». Из «Юр запросов»
 *    `contract.templateId` открывает шаблон ДС заявки, `contract.annexId` переключает этот ДС на новый шаблон, если юрист заведёт его.
 *    Без `templateId` окно открывается карточками шаблонов договора; `contract.view = 'annexes'` — «ДС договора», уже подтверждённые
 *    приложения (кнопка в строке реестра договоров, 28.10.2026).
 * Права — секция `annex_templates`: просмотр / создание (кастомный, новый вариант) / правка (версии, форматы, откат).
 */
import { useEffect, useState } from 'react'
import { UI, Z } from '@/components/salesTableKit'
import { overlayClose } from '@/lib/overlay'
import { can, getPermissions } from '@/lib/auth'
import { fmtDate } from '@/lib/dates'
import { moved, check } from '@/lib/annexTemplate.mjs'
import { annexTemplatesApi as API } from '@/lib/annexTemplatesApi'
import useTemplateData from '@/components/annex/useTemplateData'
import TemplatePick from '@/components/annex/TemplatePick'
import TemplateSheet from '@/components/annex/TemplateSheet'
import TemplateHistory from '@/components/annex/TemplateHistory'
import { BlockList, PointEditor } from '@/components/annex/TemplateEditor'
import { Head, Strip, BaseChangedBar, FormatsBar, Issues, Foot, Reason } from '@/components/annex/TemplateBars'
import ContractTemplatesBar from '@/components/annex/ContractTemplatesBar'
import ContractTemplateCards from '@/components/annex/ContractTemplateCards'
import ContractAnnexList from '@/components/annex/ContractAnnexList'
import { Segmented } from '@/components/salesTableKit'

// Вид документа по договору (владелец 31.10.2026): «при пересохранении — выбор ДС/Приложение, если ещё не выбрано».
// Подписи — как на наших экранах; в самом документе слово печатается полностью.
const WORDS = [{ value: 'приложение', label: 'Приложение' }, { value: 'дс', label: 'ДС' }]

export default function BaseTemplateModal({ open, onClose, contract }) {
  const [step, setStep] = useState('pick')
  const [baseId, setBaseId] = useState(null)
  const [edit, setEdit] = useState(false)
  const [hist, setHist] = useState(false)
  const [hsel, setHsel] = useState(null)
  const [emptyDemo, setEmptyDemo] = useState(false)
  const [sel, setSel] = useState('p1')
  const [draft, setDraft] = useState(null)
  const [adopt, setAdopt] = useState(false)
  const [word, setWord] = useState(null)              // вид, выбранный при пересохранении (если у договора ещё не выбран)
  const [busy, setBusy] = useState(false)
  const [seq, setSeq] = useState(1)
  const [perm, setPerm] = useState({ edit: false, create: false })
  const [tplId, setTplId] = useState(null)
  const [view, setView] = useState('cards')              // договор: cards — шаблоны карточками, tpl — открытый шаблон, annexes — ДС договора
  useEffect(() => {
    setTplId(open && contract ? contract.templateId || null : null)
    setView(!contract ? 'cards' : contract.view || (contract.templateId ? 'tpl' : 'cards'))
  }, [open, contract])
  useEffect(() => {
    const p = getPermissions()
    setPerm({ edit: can(p, 'annex_templates', 'edit'), create: can(p, 'annex_templates', 'create') })
  }, [])

  const D = useTemplateData({ open, contract, baseId, step, tplId })
  const detail = D.detail
  const custom = !!detail && detail.scope === 'custom'
  const tpl = contract ? view === 'tpl' && !!detail : step !== 'pick'
  const blocks = draft || (detail ? detail.blocks : [])
  const issues = check(blocks)
  const ok = issues.length === 0
  const mayEditNow = perm.edit && (!contract || custom)       // базовый из договора правят в реестре приложений

  if (!open) return null

  const put = (next) => setDraft(next)
  const patch = (id, p) => put(blocks.map(b => (b.id === id ? { ...b, ...p } : b)))
  const reset = () => { setEdit(false); setDraft(null); setHist(false); setHsel(null); setAdopt(false); D.setErr(null) }
  const sure = (text) => !draft || window.confirm(text)

  const close = () => {
    if (!sure('Есть несохранённые правки шаблона. Закрыть без сохранения?')) return
    reset(); setStep('pick'); setBaseId(null); onClose()
  }
  const pickBase = (id) => { reset(); setBaseId(id); setStep('tpl'); setSel('p1') }
  const back = () => {
    if (!sure('Есть несохранённые правки шаблона. Выйти без сохранения?')) return
    reset()
    if (contract) { setView('cards'); return }
    setStep('pick'); setBaseId(null)
  }
  const openTpl = (id) => { reset(); setTplId(id); setView('tpl') }
  const startEdit = () => { setDraft(detail.blocks.map(b => ({ ...b }))); setEdit(true); setSel('p1') }
  const add = () => {
    const id = `n${seq}`
    const at = blocks.findIndex(b => b.sys === 'sign')
    put([...blocks.slice(0, at), { id, title: 'Новый пункт', text: 'Текст пункта.' }, ...blocks.slice(at)])
    setSel(id); setSeq(seq + 1)
  }
  const remove = (id) => {
    const next = blocks.filter(b => b.id !== id)
    const first = next.find(b => !b.sys)
    put(next); setSel(first ? first.id : null)
  }
  const save = async () => {
    if (!ok || (needWord && !word)) return
    setBusy(true)
    const done = await D.save(detail.id, draft, adopt, needWord ? word : undefined)
    setBusy(false)
    if (done) reset()
  }
  const rollback = async (row) => {
    if (!window.confirm(`Вернуть шаблон к версии v${row.v}? Появится новая версия с её текстом, история сохранится.`)) return
    if (await D.restore(detail.id, row.v)) { setHist(false); setHsel(null) }
  }
  const adoptBase = async () => {
    try {
      const base = await API.one(detail.base_template_id)
      setDraft(base.blocks.map(b => ({ ...b }))); setAdopt(true); setEdit(true); setSel('p1')
    } catch (_) { D.setErr({ message: 'Не удалось загрузить базовый шаблон', issues: [] }) }
  }
  const pickTpl = (id) => { if (id !== (detail && detail.id) && sure('Есть несохранённые правки шаблона. Перейти без сохранения?')) { reset(); setTplId(id) } }
  const createTpl = async (title, sourceId, main) => {
    setBusy(true)
    const id = await D.fork({ title, sourceId, main, annexId: contract.annexId })
    setBusy(false)
    if (id) openTpl(id)
    return !!id
  }
  const toggleFormat = (f) => {
    const has = detail.formats.includes(f)
    D.setFormats(detail.id, has ? detail.formats.filter(x => x !== f) : [...detail.formats, f])
  }

  const inEdit = tpl && edit && !hist
  // ПОСЛЕ `inEdit`: объявленный выше, он читал бы `inEdit` до инициализации, и окно падало бы при открытии.
  // Шаблон договора, у договора которого вид не выбран, — спрашиваем при пересохранении. Без выбора не сохраняем:
  // пересохранение шаблонов и есть тот проход, на котором вид у договоров фиксируется (выбор без умолчания — у договора
  // может быть и «Приложение», и «ДС», угадывать нельзя). Базовый шаблон договора не имеет — его не касается.
  const needWord = !!(inEdit && detail && detail.scope === 'custom' && !detail.contract_annex_word)
  const rows = D.versions.map(v => ({ v: v.version, date: fmtDate(v.created_at), author: v.author, changes: v.changes || [] }))
  const title = contract ? `${view === 'annexes' ? 'ДС договора' : 'Шаблон ДС'} · ${contract.number || 'договор'}` : (tpl ? 'Базовый шаблон ДС' : 'Базовые шаблоны ДС')
  const chip = !tpl || !detail ? null : custom ? `${detail.title} · v${detail.version}` : detail.title
  const serverIssues = D.err && D.err.issues && D.err.issues.length ? D.err : null

  return (
    <div {...overlayClose(close)}
         style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'var(--scrim)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '32px 24px', boxSizing: 'border-box', overflowY: 'auto', fontFamily: UI }}>
      <div style={{ width: '100%', maxWidth: edit ? 1872 : 1180, background: 'var(--bg-card)', borderRadius: 18, boxShadow: 'var(--shadow-float)', display: 'flex', flexDirection: 'column', maxHeight: 'calc(100vh - 64px)' }}>
        <Head title={title} chip={chip} canBack={contract ? view === 'tpl' : tpl} edit={inEdit} dirty={!!draft}
              canHist={tpl && !!detail && !edit} histOn={hist} canEdit={tpl && !!detail && !edit && !hist && mayEditNow}
              onBack={back} onHist={() => { setHist(!hist); setHsel(null) }} onEdit={startEdit} onClose={close} />

        {D.err && !serverIssues && (
          <div style={{ padding: '10px 20px', background: 'var(--danger-bg)', borderBottom: '1px solid var(--danger-border)', color: 'var(--danger-fg)', fontSize: 12.5 }}>{D.err.message}</div>
        )}
        {contract && D.info && D.info.source === 'none' && <Reason text={D.info.reason} />}
        {contract && view === 'cards' && D.info && (
          <ContractTemplateCards templates={D.info.templates || []} mayCreate={perm.create} busy={busy} onPick={openTpl} onCreate={createTpl} />
        )}
        {contract && view === 'annexes' && <ContractAnnexList contractId={contract.id} />}
        {tpl && detail && <Strip detail={detail} dirty={!!draft} custom={custom} emptyDemo={emptyDemo} onEmpty={() => setEmptyDemo(!emptyDemo)} />}
        {contract && view === 'tpl' && D.info && D.info.templates && !edit && !hist && (
          <ContractTemplatesBar templates={D.info.templates} selectedId={detail ? detail.id : null} mayCreate={perm.create} mayEdit={perm.edit} busy={busy}
                                onSelect={pickTpl} onCreate={createTpl} onRename={D.rename} onMain={D.setMain} />
        )}
        {!contract && tpl && detail && !edit && !hist && (
          <FormatsBar detail={detail} known={D.known} fmtMap={D.fmtMap} bases={D.bases} mayEdit={perm.edit} onToggle={toggleFormat} />
        )}
        {custom && detail.base && detail.base.changed && !edit && !hist && (
          <BaseChangedBar baseTitle={detail.base_title} known={detail.base.known} now={detail.base.now} changes={(D.info && D.info.base_changes) || []}
                          mayEdit={perm.edit} onKeep={() => D.keepOwn(detail.id)} onAdopt={adoptBase} />
        )}
        {!contract && !tpl && <TemplatePick bases={D.bases} canCreate={perm.create} onPick={pickBase} onAdd={(t, src) => D.createBase(t, src)} />}
        {tpl && detail && hist && <TemplateHistory list={rows} version={detail.version} selected={hsel || detail.version} onSelect={setHsel} onRollback={mayEditNow ? rollback : undefined} />}
        {tpl && detail && !hist && (
          <div style={{ flex: '1 1 auto', minHeight: 0, display: 'flex', overflow: 'hidden' }}>
            {inEdit && <BlockList blocks={blocks} sel={sel} onPick={setSel} onMove={(id, d) => put(moved(blocks, id, d))} onAdd={add} />}
            {inEdit && <PointEditor blocks={blocks} sel={sel} onPatch={patch} onRemove={remove} />}
            <TemplateSheet blocks={blocks} edit={inEdit} sel={sel} emptyDemo={emptyDemo} onPick={setSel} />
          </div>
        )}
        {D.loading && !detail && !D.bases.length && <div style={{ padding: 40, color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>}
        {inEdit && !ok && <Issues issues={issues} onGo={setSel} />}
        {inEdit && ok && serverIssues && <Issues issues={serverIssues.issues} serverMessage={serverIssues.message} onGo={setSel} />}
        {needWord && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '10px 20px', borderTop: '1px solid var(--border-inner)', background: 'var(--warning-bg)' }}>
            <span style={{ fontSize: 12.5, color: 'var(--warning-fg)', fontWeight: 700 }}>Вид документа по договору ещё не выбран</span>
            <Segmented value={word} options={WORDS} onChange={setWord}
                       title="Каким словом называются ДС по этому договору — в номере и тексте. Фиксируется в договоре" />
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>выбирается один раз — дальше менять сможет только администратор</span>
          </div>
        )}
        <Foot edit={inEdit} ok={ok} count={issues.length} nextVer={detail ? detail.version + 1 : 1} busy={busy}
              onCancel={reset} onSave={save} onClose={close}
              hold={needWord && !word ? 'выберите вид документа по договору — «Приложение» или «ДС»' : null} />
      </div>
    </div>
  )
}
