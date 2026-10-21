/**
 * Документ приложения по шаблону ДС на экране сборки (спринт 2, 14.10.2026): шаблон и версия, недостающее с указанием, где заполнить,
 * уведомление «базовый изменился», сам документ — блоки шаблона с подставленными значениями, таблица «бренд → услуги → допы», стороны.
 * Модель собирает сервер (`app/annex_tpl/assemble.py`); здесь только показ.
 */
import { MONO } from '@/components/salesTableKit'
import { grpDec, fmtDateFull } from '@/lib/salesFormat'

const SERIF = "'Times New Roman', Georgia, serif"
const LBL = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
const money = (v) => (v == null ? '—' : grpDec(v, 2))

function longDate(d) {
  const [y, m, dd] = String(d || '').slice(0, 10).split('-')
  return dd ? `«${dd}» ${MONTHS[Number(m) - 1]} ${y} г.` : '«__» ______ ____ г.'
}

function partyLine(p, role) {
  if (!p || !p.legal_name) return `___________, именуемое в дальнейшем «${role}»`
  return `${p.legal_name}, именуемое в дальнейшем «${role}», в лице ${p.position_gen || p.position || '___________'} ${p.director_gen || p.director || '___________'}, ${p.acting || 'действующего'} на основании ${p.basis_gen || p.basis || '___________'}`
}

function Parts({ parts }) {
  return parts.map((g, i) => {
    if (!g.key) return <span key={i}>{g.t}</span>
    const bad = g.empty || g.unknown
    return (
      <span key={i} title={g.empty ? 'не заполнено — документ нельзя подтвердить' : g.unknown ? 'неизвестная подстановка' : `{${g.key}}`}
            style={{ color: bad ? 'var(--danger-fg)' : 'var(--income-fg)', background: bad ? 'var(--danger-tint)' : 'var(--income-tint)', borderRadius: 3, padding: '0 2px' }}>
        {g.empty ? `нет: ${g.key.replace(/_/g, ' ')}` : g.t}
      </span>
    )
  })
}

const th = { padding: '5px 8px', fontFamily: MONO, fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-cap)', background: 'var(--bg-subtle)', textAlign: 'left', whiteSpace: 'nowrap' }
const td = { padding: '5px 8px', fontSize: 11.5, borderTop: '1px solid var(--border-row)', verticalAlign: 'top' }
const num = { ...td, textAlign: 'right', fontFamily: MONO, whiteSpace: 'nowrap' }

function Table({ table }) {
  const many = table.groups.length > 1
  return (
    <div style={{ overflowX: 'auto', border: '1px solid var(--border-card)', borderRadius: 4, fontFamily: 'Manrope, sans-serif' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead><tr>
          <th style={th}>Позиция</th><th style={th}>Гео</th><th style={th}>Формат</th><th style={th}>Девайс</th><th style={th}>Модель</th>
          <th style={{ ...th, textAlign: 'right' }}>Объём</th><th style={{ ...th, textAlign: 'right' }}>Цена за ед.</th>
          <th style={{ ...th, textAlign: 'right' }}>Стоимость</th><th style={{ ...th, textAlign: 'right' }}>НДС</th><th style={{ ...th, textAlign: 'right' }}>С НДС</th>
        </tr></thead>
        <tbody>
          {table.groups.map((g, gi) => [
            <tr key={`h${gi}`}><td colSpan={10} style={{ ...td, fontWeight: 700, background: 'var(--bg-tint)' }}>{g.brand || 'Без бренда'}</td></tr>,
            ...g.rows.map((r, ri) => (
              <tr key={`${gi}-${ri}`} style={{ color: r.kind === 'extra' ? 'var(--text-secondary)' : 'inherit' }}>
                <td style={{ ...td, paddingLeft: 16, fontStyle: 'italic' }}>{r.doc_position || r.position || '—'}{r.kind === 'extra' ? ' · доп.' : ''}</td>
                <td style={td}>{r.geo || '—'}</td><td style={td}>{r.format || '—'}</td><td style={td}>{r.device || '—'}</td><td style={td}>{r.model || '—'}</td>
                <td style={num}>{r.volume ? grpDec(r.volume, 0) : '—'}</td><td style={num}>{r.bonus ? '—' : money(r.unit_price)}</td>
                <td style={{ ...num, fontWeight: 700 }}>{r.bonus ? '—' : money(r.amount)}</td>
                <td style={num}>{r.bonus ? '—' : money(r.vat)}</td><td style={{ ...num, fontWeight: 700 }}>{r.bonus ? '—' : money(r.gross)}</td>
              </tr>
            )),
            many && (
              <tr key={`s${gi}`}><td colSpan={7} style={{ ...td, textAlign: 'right', color: 'var(--text-secondary)' }}>Итого по бренду</td>
                <td style={num}>{money(g.totals.net)}</td><td style={num}>{money(g.totals.vat)}</td><td style={{ ...num, fontWeight: 700 }}>{money(g.totals.gross)}</td></tr>
            ),
          ])}
          <tr style={{ background: 'var(--bg-subtle)' }}>
            <td colSpan={7} style={{ ...td, textAlign: 'right', fontWeight: 700 }}>ИТОГО:</td>
            <td style={{ ...num, fontWeight: 700 }}>{money(table.totals.net)}</td><td style={{ ...num, fontWeight: 700 }}>{money(table.totals.vat)}</td>
            <td style={{ ...num, fontWeight: 700 }}>{money(table.totals.gross)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function Sign({ model }) {
  const side = (who, p) => (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <b>{who}</b>
      <span>{p.legal_name || p.name || '—'}</span>
      <span>{p.position_nom || p.position || '____________'}</span>
      <span>_______________ / {p.short_fio || '_________'}</span>
      <span style={{ color: 'var(--text-faint)' }}>М.П.</span>
    </span>
  )
  return (
    <div style={{ paddingTop: 10 }}>
      <b>Реквизиты:</b>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 30, paddingTop: 10, fontSize: '0.93em' }}>
        {side('Исполнитель:', model.executor)}{side('Заказчик:', model.customer)}
      </div>
    </div>
  )
}

function Sheet({ model }) {
  const c = model.contract || {}
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 6, padding: '30px 38px', fontFamily: SERIF, fontSize: 14, lineHeight: 1.5, color: 'var(--text-primary)', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {model.blocks.map(b => {
        if (b.sys === 'head') {
          return <span key={b.id} style={{ textAlign: 'center' }}><b>{model.number}</b><br />к Договору № {c.number || '____'} от {fmtDateFull(c.date)}</span>
        }
        if (b.sys === 'place') {
          return <span key={b.id} style={{ display: 'flex', justifyContent: 'space-between' }}><span>{model.signed_place}</span><span>{longDate(model.date)}</span></span>
        }
        if (b.sys === 'pre') {
          return (
            <span key={b.id} style={{ textAlign: 'justify', textIndent: '2em' }}>
              {partyLine(model.customer, 'Заказчик')}, с одной стороны, и {partyLine(model.executor, 'Исполнитель')}, с другой стороны, заключили настоящее {model.number} к Договору № {c.number || '____'} от {fmtDateFull(c.date)} (далее по тексту – «Договор») о нижеследующем:
            </span>
          )
        }
        if (b.sys === 'table') return <Table key={b.id} table={model.table} />
        if (b.sys === 'sign') return <Sign key={b.id} model={model} />
        return (
          <span key={b.id} style={{ textAlign: 'justify', textIndent: b.sub ? '2em' : 0 }}>
            <b>{b.num}</b> <Parts parts={b.parts} />
          </span>
        )
      })}
    </div>
  )
}

function Box({ tone, children }) {
  const t = { warn: ['var(--warning-bg)', 'var(--warning-border)', 'var(--warning-fg)'], bad: ['var(--danger-bg)', 'var(--danger-border)', 'var(--danger-fg)'], info: ['var(--bg-subtle)', 'var(--border-card)', 'var(--text-secondary)'] }[tone]
  return <div style={{ padding: '10px 14px', borderRadius: 10, background: t[0], border: `1px solid ${t[1]}`, color: t[2], fontSize: 12.5, lineHeight: 1.5 }}>{children}</div>
}

function RebuildBtn({ onClick, busy, small }) {
  return (
    <span onClick={busy ? undefined : onClick}
          title="Собрать документ заново по актуальной версии шаблона договора. Номер и дата сохранятся; пока приложение не ушло в 1С"
          style={{ display: 'inline-flex', alignItems: 'center', height: small ? 26 : 32, padding: small ? '0 10px' : '0 14px', borderRadius: 9, border: '1px solid var(--accent-border)', background: 'var(--accent-tint)', color: 'var(--accent-fg)', fontSize: small ? 11.5 : 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: busy ? 'wait' : 'pointer' }}>
      {busy ? 'Пересоздаю…' : 'Пересоздать на новом шаблоне'}
    </span>
  )
}

export default function AnnexModelPanel({ state, onRebuild, rebuildBusy, actions }) {
  const { model, frozen, legacy, reason, template_state: ts } = state
  if (legacy) {
    return (
      <Box tone="info">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span><b>Собрано до конструктора шаблонов.</b> {reason}</span>
          {onRebuild && <span style={{ marginLeft: 'auto' }}><RebuildBtn onClick={onRebuild} busy={rebuildBusy} /></span>}
        </div>
      </Box>
    )
  }
  if (!model) return <Box tone="bad"><b>Шаблон ДС не определён.</b> {reason}</Box>
  const t = model.template || {}
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={LBL}>Документ по шаблону</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', borderRadius: 7, background: 'var(--violet-tint)', color: 'var(--violet-fg)', fontSize: 11, fontWeight: 700 }}>
          {t.scope === 'custom' ? `кастомный · ${t.title} · v${t.version}` : `${t.title} · v${t.version}`}
        </span>
        <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
          {frozen ? 'замороженный документ: правка шаблона его не меняет' : 'черновик: собирается по текущей версии шаблона, при подтверждении фиксируется'}
        </span>
        {(actions || (frozen && onRebuild)) && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {actions}
            {frozen && onRebuild && <RebuildBtn onClick={onRebuild} busy={rebuildBusy} small />}
          </span>
        )}
      </div>
      {ts && ts.changed && (
        <Box tone="warn">
          <b>Базовый шаблон изменился</b> (v{ts.known} → v{ts.now}), а у этого договора свой кастомный шаблон. Надо ли отредактировать текущий — «Справочники → Договоры → Шаблон ДС».
          {!!(ts.changes || []).length && <div style={{ marginTop: 4 }}>{ts.changes.map((c, i) => <div key={i}>• {c[1]} — {c[2]}</div>)}</div>}
        </Box>
      )}
      {!!model.missing.length && (
        <Box tone="bad">
          <b>Подтвердить нельзя — не хватает:</b>
          <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
            {model.missing.map((m, i) => <li key={i}>{m.text} <span style={{ color: 'var(--text-faint)' }}>— {m.where}</span></li>)}
          </ul>
        </Box>
      )}
      {model.consistency && !model.consistency.ok && <Box tone="bad"><b>Числа не сходятся:</b> {model.consistency.details.join('; ')}</Box>}
      <Sheet model={model} />
    </div>
  )
}
