/**
 * Документы закрытия сделки — из мастер-сделки (владелец 13.11.2026: «документы показываем из мастер-сделки, ручную
 * загрузку ДС, счёта, УПД и акта убираем»).
 *
 * Документы живут в пакете; здесь их только показываем. Правило одно на три случая — сделка видит документы, в которых
 * есть её строки, и свою долю:
 *   1) сделка = пакет — всё один к одному, без долей;
 *   2) одна сделка, два ДС (основные + допы) — два ДС и их комплекты;
 *   3) пакет из нескольких сделок — только комплекты со строками сделки, «часть сделки N из M · общий с …».
 *
 * Внешний вид строки задаёт экран (`line`): карточка рисует свои строки, раскрывашка реестра — свои.
 * Данные — `GET /sales/deals/{id}` (`master_docs`) или `/sales/deals/{id}/master-docs`.
 */
import { downloadBlob } from '@/lib/dealDocs'
import { dm, grp, rub2 } from '@/lib/salesFormat'
import { shortAnnexNumber } from '@/lib/annexNumber'

const ACT = {
  display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 7px', border: '1px solid var(--border-card)',
  borderRadius: 7, background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 10, fontWeight: 700, cursor: 'pointer',
  whiteSpace: 'nowrap', textDecoration: 'none',
}

// Колонка документов узкая: доля — коротко, без копеек («123 305 из 412 074 ₽ · с D5ETJ6»), полная сумма — когда
// документ целиком сделки.
const shareText = (share, total, others) => {
  if (!others.length && Math.abs((share || 0) - (total || 0)) < 0.01) return rub2(total)
  return `${grp(share)} из ${grp(total)} ₽${others.length ? ` · с ${others.join(', ')}` : ''}`
}

// «Дополнительное соглашение № 96-01» → «ДС № 96-01»: слово документа длинное, в узкой колонке оно съедало номер.
const dsTitle = (a) => (a.is_draft ? 'ДС · черновик' : shortAnnexNumber(a.number) || `ДС № ${a.no}`)

function dsRows(docs, line) {
  return docs.ds.map(a => line({
    key: `ds-${a.id}`,
    ok: !a.is_draft,
    title: dsTitle(a),
    meta: [a.date ? dm(a.date, '') : null, a.sign_state, shareText(a.share, a.total, a.shared_with)].filter(Boolean).join(' · '),
    right: (
      <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
        <span onClick={() => downloadBlob(`/annexes/${a.id}/pdf`, `${a.number || 'ДС'}.pdf`)} style={ACT}>PDF</span>
        <span onClick={() => downloadBlob(`/annexes/${a.id}/docx`, `${a.number || 'ДС'}.docx`)} style={ACT}>DOC</span>
        <a href={`/directory/annexes/${a.id}`} style={ACT} title="Открыть ДС">↗</a>
      </span>
    ),
  }))
}

function kitRows(docs, line) {
  return docs.kits.map(k => {
    const nums = [k.invoice_no && `Счёт № ${k.invoice_no}`, k.upd_no_1c && `УПД № ${k.upd_no_1c}`].filter(Boolean)
    const file = (slot, name) => k.files[slot] && (
      <span onClick={() => downloadBlob(`/master-deals/${k.master_code}/files/${k.files[slot]}`, name)} style={ACT}
        title={`Скачать ${name}`}>{slot === 'invoice' ? 'Счёт' : 'УПД'}</span>)
    return line({
      key: `kit-${k.master_code}-${k.upd_no}`,
      ok: k.in_1c,
      title: nums.length ? nums.join(' · ') : `Счёт и УПД ${k.upd_no} · ждём 1С`,
      meta: [k.brand, k.service, shareText(k.share_gross, k.total_gross, k.shared_with)].filter(Boolean).join(' · '),
      right: (
        <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
          {file('invoice', `Счёт ${k.invoice_no || k.upd_no}.pdf`)}
          {file('upd', `УПД ${k.upd_no_1c || k.upd_no}.pdf`)}
          <a href={`/accounts/master/${k.master_code}`} style={ACT} title={`Мастер-сделка ${k.master_code}`}>↗</a>
        </span>
      ),
    })
  })
}

/** Строки документов закрытия. `onCreate` — «Создать» ДС на старте, пока у сделки нет ни ДС, ни пакета. */
export default function MasterDocs({ docs, line, onCreate, creating }) {
  if (!docs) return line({ key: 'ds-loading', ok: false, title: 'ДС', meta: 'загрузка…' })
  const out = []
  if (docs.master) {
    out.push(line({
      key: 'master', ok: true, title: `Мастер-сделка ${docs.master.code}`, meta: docs.master.status,
      right: <a href={`/accounts/master/${docs.master.code}`} style={ACT} title="Открыть мастер-сделку">↗</a>,
    }))
  }
  if (docs.ds.length) out.push(...dsRows(docs, line))
  else {
    out.push(line({
      key: 'ds-none', ok: false, title: 'ДС',
      meta: docs.master ? 'ещё не создано в мастер-сделке' : 'не создано',
      right: onCreate && !docs.master ? <span onClick={onCreate} style={ACT}>{creating ? 'Создаю…' : 'Создать'}</span> : null,
    }))
  }
  if (docs.kits.length) out.push(...kitRows(docs, line))
  else {
    out.push(line({
      key: 'kits-none', ok: false, title: 'Счёт и УПД',
      meta: docs.master ? 'появятся после внесения из 1С' : 'появятся в мастер-сделке после «Отправить в ДО»',
    }))
  }
  return out
}

/** Сколько документов закрытия готово — для счётчика «N из M» в карточке. */
export function masterDocsCount(docs) {
  if (!docs) return { ready: 0, total: 2 }
  const ds = docs.ds.length ? docs.ds : [null]
  const kits = docs.kits.length ? docs.kits : [null]
  return {
    ready: ds.filter(a => a && !a.is_draft).length + kits.filter(k => k && k.in_1c).length,
    total: ds.length + kits.length,
  }
}
