/** Строка контрагента и её раскрытие (хендофф, пп. 5–6): привычка, возраст долями, примечание двойным кликом, сальдо и «зачесть»;
 *  внутри — счета группами по периоду, статус, «ждём на деле», предпросмотр ДС/ПР и счёта. */
import { useState } from 'react'
import { CAPS, MONO, f } from '@/components/money/kit'
import { STC, clsOf, fd, groupsOf, invL, addDays } from './model'

export const GRID = '28px minmax(0,1.5fr) 128px 150px minmax(0,1.25fr) minmax(0,1.5fr) 170px'
const SUB = '26px minmax(0,1fr) 150px 110px 92px 92px 150px 120px 130px'
const ghost = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 12px', boxSizing: 'border-box', background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', fontFamily: 'inherit' }

function Eye({ title, onClick, hidden }) {
  return (
    <button type="button" title={title} onClick={e => { e.stopPropagation(); onClick?.() }} disabled={hidden}
      style={{ display: 'inline-flex', visibility: hidden ? 'hidden' : 'visible', flex: '0 0 24px', width: 24, height: 24, alignItems: 'center', justifyContent: 'center',
        borderRadius: 7, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', padding: 0 }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
    </button>
  )
}

function Note({ x, canEdit, onSave, status }) {
  const [ed, setEd] = useState(false)
  const save = (v) => { setEd(false); if (v.trim() !== (x.note || '').trim()) onSave(x.id, v.trim()) }
  return (
    <span onClick={e => e.stopPropagation()} onDoubleClick={() => canEdit && setEd(true)} title={canEdit ? 'двойной клик — изменить примечание' : undefined}
      style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, minHeight: 30, borderRadius: 8, cursor: canEdit ? 'text' : 'default' }}>
      {ed ? <input autoFocus defaultValue={x.note} placeholder="примечание — Enter сохранит, Esc отменит"
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() } else if (e.key === 'Escape') setEd(false) }}
        onBlur={e => save(e.currentTarget.value)}
        style={{ width: '100%', height: 30, boxSizing: 'border-box', padding: '0 10px', borderRadius: 8, border: '1.5px solid var(--hot)', background: 'var(--bg-card)',
          color: 'var(--text-primary)', font: 'inherit', fontSize: 12.5, outline: 'none' }} />
        : <span style={{ padding: '0 6px', fontSize: 12.5, color: x.note ? 'var(--text-primary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.note || '—'}</span>}
      {status === 'saving' && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>…</span>}
      {status === 'saved' && <span style={{ fontSize: 11, color: 'var(--money-fg)' }}>✓</span>}
      {status === 'error' && <span title="Не сохранено" style={{ fontSize: 11, color: 'var(--bad-fg)' }}>!</span>}
    </span>
  )
}

function Item({ x, it, sel, onSel, onDs, onInv }) {
  const k = clsOf(it.dd), s = STC[k]
  const exp = it.srok ? addDays(it.srok, x.delta) : null
  const d = it.docs
  return (
    <div style={{ display: 'grid', gridTemplateColumns: SUB, gap: 12, alignItems: 'center', padding: '6px 10px', borderTop: '1px solid var(--border-row)' }}>
      <span onClick={onSel} role="checkbox" aria-checked={sel} style={{ display: 'inline-flex', width: 15, height: 15, alignItems: 'center', justifyContent: 'center', borderRadius: 4,
        border: `1.5px solid ${sel ? 'var(--hot)' : 'var(--border-hover)'}`, background: sel ? 'var(--hot)' : 'transparent', color: 'var(--hot-fg)', fontSize: 10, cursor: 'pointer' }}>{sel ? '✓' : ''}</span>
      <span style={{ fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.art || '—'}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        <Eye hidden={!d?.annex_id} title={d?.annex_external ? 'Внешний ДС — скачать файл' : 'Посмотреть ДС / ПР'} onClick={() => onDs(d, it.doc)} />
        <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.doc || '—'}</span></span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <Eye hidden={!(d?.kit_id && it.inv)} title="Посмотреть счёт" onClick={() => onInv(d, it.inv)} />
        <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{it.inv || '—'}</span></span>
      <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{fd(it.idate)}</span>
      <span style={{ fontFamily: MONO, fontSize: 11.5 }}>{fd(it.srok)}</span>
      <span><span style={{ display: 'inline-flex', alignItems: 'center', height: 19, padding: '0 7px', borderRadius: 6, background: s.bg, border: `1px solid ${s.bd}`, fontSize: 11,
        fontWeight: 600, color: s.tfg, whiteSpace: 'nowrap' }}>{k === 'due' ? `до срока · ${-it.dd} дн` : `${k === 'cur' ? 'текущая' : 'просрочка'} · +${it.dd} дн`}</span></span>
      <span style={{ fontFamily: MONO, fontSize: 11.5, color: x.delta >= 10 ? 'var(--attn-fg)' : 'var(--text-secondary)' }}>{x.delta ? `${fd(exp)} · +${x.delta}` : 'в срок'}</span>
      <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{f(it.v)}</span>
    </div>
  )
}

export default function DebtRow({ x, open, onToggle, sum, only, canEdit, onSaveNote, noteStatus, onDs, onInv }) {
  const [sel, setSel] = useState({})
  const ab = [['over', x.b[0], 'просрочено '], ['cur', x.b[1], 'текущая '], ['due', x.b[2], 'до срока ']].filter(q => q[1] > 0)
  const sal = x.sum - x.we
  const habitHi = x.delta >= 10
  const selN = Object.values(sel).filter(Boolean).length
  return (
    <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--border-row)', background: open ? 'var(--bg-subtle)' : 'transparent', borderRadius: open ? 12 : 0 }}>
      <div onClick={onToggle} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 14, alignItems: 'center', padding: '11px 8px', cursor: 'pointer' }}>
        <span style={{ display: 'inline-flex', width: 20, height: 20, alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--border-card)',
          color: 'var(--text-muted)', fontSize: 10 }}>{open ? '▾' : '▸'}</span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            {x.act && <span title="просрочка без примечания" style={{ flex: '0 0 8px', width: 8, height: 8, borderRadius: '50%', background: 'var(--signal)' }} />}
            <span title={x.full} style={{ fontSize: 14, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.who}</span></span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--text-muted)', minWidth: 0, whiteSpace: 'nowrap' }}>
            <span>{x.mgr || 'без аккаунта'} · {invL(x.its.length)}</span>
            {x.inn && <a href={`/directory/counterparties/${x.id}`} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} title="Карточка юрлица — в новой вкладке"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontFamily: MONO, color: 'var(--text-muted)', textDecoration: 'none' }}>· {x.inn}
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M7 17 17 7" /><path d="M9 7h8v8" /></svg></a>}
          </span>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <span style={{ fontFamily: MONO, fontSize: 12 }}>{x.def} дн</span>
          <span style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 6px', borderRadius: 5, background: habitHi ? 'var(--attn-tint)' : 'var(--bg-subtle)',
            border: `1px solid ${habitHi ? 'var(--attn-border)' : 'var(--border-inner)'}`, fontFamily: MONO, fontSize: 10, fontWeight: 700, color: habitHi ? 'var(--attn-fg)' : 'var(--text-secondary)',
            whiteSpace: 'nowrap' }}>{x.delta ? `обычно +${x.delta} дн` : 'платит в срок'}</span>
        </span>
        <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap' }}>{f(sum)}</span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
          <span style={{ display: 'flex', height: 7, borderRadius: 4, overflow: 'hidden', gap: 2, background: 'var(--bg-subtle)' }}>
            {ab.map(q => <span key={q[0]} style={{ flex: `${q[1]} 1 0`, background: STC[q[0]].c }} />)}</span>
          <span style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 10px' }}>
            {ab.map(q => <span key={q[0]} style={{ fontFamily: MONO, fontSize: 11, color: STC[q[0]].fg, whiteSpace: 'nowrap' }}>{q[2]}{f(q[1])}</span>)}</span>
        </span>
        <Note x={x} canEdit={canEdit} onSave={onSaveNote} status={noteStatus} />
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
          <span style={{ fontFamily: MONO, fontSize: 13.5, fontWeight: 700, color: sal < 0 ? 'var(--bad-fg)' : 'var(--text-primary)', whiteSpace: 'nowrap' }}>{sal < 0 ? '−' : '+'}{f(Math.abs(sal))}</span>
          {x.net > 0 && <span style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 7px', borderRadius: 6, background: 'var(--money-tint)', border: '1px solid var(--money-border)',
            fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--money-fg)', whiteSpace: 'nowrap' }}>зачесть&nbsp;{f(x.net)}</span>}
        </span>
      </div>
      {open && (
        <div style={{ padding: '2px 8px 12px 50px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: SUB, gap: 12, padding: '6px 10px', borderBottom: '1px solid var(--border-inner)' }}>
            <span />{['статья', 'документ', 'счёт', 'дата счёта', 'срок', 'статус', 'ждём на деле'].map((h, i) => (
              <span key={h} style={{ ...CAPS, paddingLeft: i === 1 || i === 2 ? 31 : 0 }}>{h}</span>))}
            <span style={{ ...CAPS, textAlign: 'right' }}>сумма</span>
          </div>
          {groupsOf(x, only).map(g => (
            <div key={g.key}>
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 12, padding: '9px 10px 5px' }}>
                <span style={{ fontSize: 12.5, fontWeight: 700 }}>{g.p} <span style={{ fontWeight: 500, color: 'var(--text-muted)' }}>· срок {fd(g.srok)} · {invL(g.items.length)}</span></span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700 }}>{f(g.s)}</span>
              </div>
              {g.items.map(it => <Item key={it.id} x={x} it={it} sel={!!sel[it.id]} onSel={() => setSel(s => ({ ...s, [it.id]: !s[it.id] }))} onDs={onDs} onInv={onInv} />)}
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 10px 2px', borderTop: '1px solid var(--border-inner)', marginTop: 4 }}>
            <button type="button" disabled title="Появится вместе с журналом контактов по долгу" style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px',
              borderRadius: 10, background: selN ? 'var(--hot)' : 'var(--accent-border)', color: 'var(--hot-fg)', fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', border: 0,
              opacity: 0.6, cursor: 'not-allowed', fontFamily: 'inherit' }}>Напомнить по выбранным · {selN}</button>
            <button type="button" disabled title="Появится вместе с журналом контактов по долгу" style={{ ...ghost, opacity: 0.6, cursor: 'not-allowed' }}>Записать контакт</button>
            {x.net > 0 && <button type="button" disabled title="Шаблона акта зачёта в системе пока нет" style={{ ...ghost, borderColor: 'var(--money-border)', color: 'var(--money-fg)',
              opacity: 0.6, cursor: 'not-allowed' }}>Подготовить акт зачёта · {f(x.net)}</button>}
            <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
              {x.we ? `мы должны им ${f(x.we)}${x.we > x.sum ? ' — больше, чем они нам' : ''}` : 'ждём на деле — срок + обычная задержка клиента'}</span>
          </div>
        </div>
      )}
    </div>
  )
}
