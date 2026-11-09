// Обвязка боковой панели операции на странице реестра (BUILD.md хендоффа `docs/design_handoff_operation_panel.zip`): запрос
// `/operations/{id}/context`, затемнение (через `overlayClose` — гейт check-overlay), ссылки на наши экраны и действия.
// Сама панель — `OperationPanel.jsx`, вставлена из хендоффа дословно. Короткий номер ДС («ПР № 17») — общим правилом
// `lib/annexNumber.js`, сервер отдаёт полный номер.
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { Z } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { overlayClose } from '@/lib/overlay'
import { shortAnnexNumber } from '@/lib/annexNumber'
import { downloadFile } from '@/lib/download'
import safeHref from '@/lib/safeHref'
import OperationPanel from './OperationPanel'
import DsViewer from '@/components/onecDesk/DsViewer'

const LINKS = {
  package: code => `/accounts/master/${code}`,
  ds: op => `/directory/annexes/${op.ds.id}`,
  deal: code => `/sales/deals/${code}`,
  counterparty: id => `/directory/counterparties/${id}`,
  contract: id => `/directory/contracts/${id}`,
}

/** Ответ сервера → контракт панели (sampleData.js хендоффа): короткий № ДС и id файлов в слотах адресов. */
export function toPanelOp(c) {
  const upd = c.upd && { ...c.upd, amount: c.upd.amount ?? (c.ds ? c.ds.amount : null),
    pdf_inv_url: c.upd.inv_pdf_id, pdf_upd_url: c.upd.upd_pdf_id, xml_upd_url: c.upd.upd_xml_id }
  // ссылку ЭДО внешнего ДС — только http(s) (`safeHref`): её вписывает человек
  return { ...c, ds: c.ds && { ...c.ds, short: shortAnnexNumber(c.ds.number) || 'черновик', edo_link: safeHref(c.ds.edo_link) }, upd,
    note: c.note && { ...c.note, document_link: safeHref(c.note.document_link) } }
}

export default function OperationPanelHost({ opId, hasPrev, hasNext, onPrev, onNext, onClose, onOpen, onRefreshRegistry }) {
  const router = useRouter()
  const [op, setOp] = useState(null)
  const [error, setError] = useState(null)
  const [fail, setFail] = useState('')      // не 404 — у панели слота нет, говорим строкой над ней
  const [dsView, setDsView] = useState(null)   // ДС модалкой экрана бухгалтера (владелец 09.11: «такой же модалкой»)
  useEffect(() => {
    let alive = true
    setOp(null); setError(null); setFail('')
    api.get(`/operations/${opId}/context`, auth())
      .then(r => { if (alive) setOp(toPanelOp(r.data)) })
      .catch(e => { if (!alive) return; if (e.response?.status === 404) setError('not_found'); else setFail(e.response?.data?.detail || 'Не удалось загрузить операцию — повторите') })
    return () => { alive = false }
  }, [opId])
  const onAction = (key, o) => {
    if (key === 'open_package') router.push(`/finance/onec-desk?code=${encodeURIComponent(o.package.code)}`)
    else if (key === 'open_bank_row') onOpen(o.payment.op_id)          // банковских строк нет — оплата это операция цепочки
    else if (key === 'download') downloadFile(`/onec-desk/kit/${o.upd.kit_id}/files/${o.file}`, o.label, msg => alert(msg))
    // модалка бухгалтера живёт под его правом; без права — печатная форма ДС в системе
    else if (key === 'view_ds') { if (o.can_download_docs && o.upd) setDsView({ kitId: o.upd.kit_id, title: `${o.ds.short} · ${o.package.code}` }); else window.open(`/directory/annexes/pdf/${o.ds.id}`, '_blank', 'noopener') }
    else if (key === 'ds_file') downloadFile(`/annexes/${o.ds.id}/external-file`, undefined, msg => alert(msg))
  }
  return (<>
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'var(--scrim)' }}>
      <div style={{ position: 'absolute', top: 0, right: 0, bottom: 0, overflow: 'auto' }}>
        {!!fail && <div role="alert" style={{ width: 560, boxSizing: 'border-box', padding: '10px 26px', background: 'var(--danger-tint)', color: 'var(--danger-fg)', fontSize: 13 }}>{fail}</div>}
        {/* пока открыт ДС, клавиши панели к ней не относятся: Esc закрывает модалку, стрелки не листают операции за ней */}
        <OperationPanel op={op} error={error} now={new Date().toISOString()} hasPrev={hasPrev && !dsView} hasNext={hasNext && !dsView}
          onPrev={onPrev} onNext={onNext} onClose={dsView ? () => setDsView(null) : onClose} onRefreshRegistry={onRefreshRegistry}
          onAction={onAction} links={LINKS} />
      </div>
    </div>
    {dsView && <DsViewer kitId={dsView.kitId} title={dsView.title} onClose={() => setDsView(null)} onError={msg => alert(msg)} />}
  </>)
}
