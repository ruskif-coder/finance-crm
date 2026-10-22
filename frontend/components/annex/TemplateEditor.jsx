/**
 * Левые две колонки режима правки (макет 13.10.2026): список блоков и редактор пункта.
 * Состояние живёт в окне-родителе; здесь только показ и вызовы.
 */
import { MONO } from '@/components/salesTableKit'
import {
  SUBS, SUB_INFO, PROTECTED_GROUPS, numbering, zoneAt, canMove,
} from '@/lib/annexTemplate.mjs'
import { Segs } from '@/components/annex/TemplateSheet'

const CAP = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const ZN = {
  acc: ['правит аккаунт', 'var(--accent-tint)', 'var(--accent-fg)'],
  law: ['только юрист', 'var(--violet-tint)', 'var(--violet-fg)'],
}

function Toggle({ on, onClick, label, title, disabled, color }) {
  return (
    <span onClick={disabled ? undefined : onClick} title={title}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5, fontWeight: 600, color: disabled ? 'var(--text-disabled)' : 'var(--text-primary)', cursor: disabled ? 'not-allowed' : 'pointer' }}>
      <span style={{ position: 'relative', display: 'inline-block', width: 30, height: 16, borderRadius: 8, background: on ? color[0] : 'var(--border-card)' }}>
        <span style={{ position: 'absolute', top: 2, left: on ? 16 : 2, width: 12, height: 12, borderRadius: 4, background: on ? color[1] : 'var(--text-disabled)', transition: 'left 150ms ease' }} />
      </span>
      {label}
    </span>
  )
}

function MoveBtn({ label, ok, title, onClick }) {
  return (
    <span onClick={ok ? onClick : undefined} title={title}
          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 6, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: ok ? 'var(--text-secondary)' : 'var(--text-disabled)', fontSize: 10, cursor: ok ? 'pointer' : 'default' }}>
      {label}
    </span>
  )
}

function BlockRow({ b, i, blocks, num, on, onPick, onMove }) {
  const zone = b.sys ? null : zoneAt(blocks, i)
  const up = canMove(blocks, i, -1)
  const down = canMove(blocks, i, 1)
  const hint = 'через таблицу МП и системные блоки не перескакивает'
  return (
    <div onClick={() => !b.sys && onPick(b.id)}
         style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 6px 6px 8px', borderRadius: 9, background: on ? 'var(--accent-tint)' : b.sys ? 'var(--bg-subtle)' : 'transparent', border: `1px solid ${on ? 'var(--accent-border)' : 'transparent'}`, cursor: b.sys ? 'default' : 'pointer' }}>
      <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: b.sys ? 'var(--text-disabled)' : 'var(--accent)', flex: '0 0 28px' }}>{b.sys ? '—' : num[b.id]}</span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, flex: '1 1 auto' }}>
        <span style={{ fontSize: 12, fontWeight: on ? 700 : 600, color: b.sys ? 'var(--text-faint)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.req ? '🔒 ' : ''}{b.title}</span>
        <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: b.sys ? 'var(--text-faint)' : zone === 'acc' ? 'var(--accent-fg)' : 'var(--violet-fg)' }}>
          {b.sys ? (b.sys === 'table' ? 'граница зон' : 'системный') : ZN[zone][0]}
        </span>
      </span>
      {!b.sys && (
        <span style={{ display: 'inline-flex', gap: 2, flex: '0 0 auto' }}>
          <MoveBtn label="↑" ok={up} title={up ? 'выше' : hint} onClick={e => { e.stopPropagation(); onMove(b.id, -1) }} />
          <MoveBtn label="↓" ok={down} title={down ? 'ниже' : hint} onClick={e => { e.stopPropagation(); onMove(b.id, 1) }} />
        </span>
      )}
    </div>
  )
}

export function BlockList({ blocks, sel, onPick, onMove, onAdd }) {
  const num = numbering(blocks)
  return (
    <div style={{ flex: '0 0 300px', borderRight: '1px solid var(--border-inner)', padding: '12px 10px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ ...CAP, padding: '0 8px 6px', letterSpacing: '.1em' }}>Блоки документа</span>
      {blocks.map((b, i) => <BlockRow key={b.id} b={b} i={i} blocks={blocks} num={num} on={sel === b.id} onPick={onPick} onMove={onMove} />)}
      <span onClick={onAdd}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, height: 34, marginTop: 8, border: '1px dashed var(--accent-border)', borderRadius: 9, fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>
        + Добавить пункт
      </span>
    </div>
  )
}

function Warn({ w }) {
  return (
    <span style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '10px 12px', background: w.bg, border: `1px solid ${w.border}`, borderRadius: 11 }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: w.dot, flex: '0 0 7px', marginTop: 5 }} />
      <span style={{ fontSize: 12, color: w.fg, lineHeight: 1.45 }}>{w.text}</span>
    </span>
  )
}

const WARN = {
  warn: { bg: 'var(--warning-bg)', border: 'var(--warning-border)', dot: 'var(--warning)', fg: 'var(--warning-fg)' },
  bad: { bg: 'var(--danger-bg)', border: 'var(--danger-border)', dot: 'var(--danger)', fg: 'var(--danger-fg)' },
}

function warningsOf(sel) {
  const out = []
  const t = sel.text || ''
  if (sel.money) {
    const miss = PROTECTED_GROUPS.filter(g => !g.some(k => t.indexOf(`{${k}}`) >= 0))
    if (miss.length) out.push({ ...WARN.warn, text: `Убрана защищённая подстановка ${miss.map(g => g.map(k => `{${k}}`).join(' или ')).join(', ')} — сумма в тексте перестанет сходиться с таблицей медиаплана.` })
  }
  const bad = (t.match(/\{([^{}]+)\}/g) || []).filter(x => !SUBS[x.slice(1, -1)])
  if (bad.length) out.push({ ...WARN.bad, text: `Неизвестная подстановка ${bad.join(', ')} — при сборке ДС останется как есть.` })
  return out
}

export function PointEditor({ blocks, sel, onPatch, onRemove }) {
  const i = blocks.findIndex(b => b.id === sel)
  const b = blocks[i]
  if (!b || b.sys) {
    return <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Выберите текстовый пункт слева</div>
  }
  const num = numbering(blocks)
  const z = ZN[zoneAt(blocks, i)]
  const prevMain = blocks.slice(0, i).reverse().find(x => !x.sys)
  const canSub = !!prevMain || !!b.sub
  const baseReq = !!b.pin                      // закреплённый пункт: обязательность не снимается, убрать нельзя
  const subLabel = b.sub ? num[b.id].replace(/\.$/, '') : (prevMain ? `${num[prevMain.id].split('.')[0]}.1` : '1.1')
  const addSub = (k) => onPatch(b.id, { text: `${(b.text || '').replace(/\s*$/, '')} {${k}}` })
  return (
    <div style={{ flex: '1 1 0', minWidth: 0, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>{num[b.id]}</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', borderRadius: 7, background: z[1], color: z[2], fontSize: 10.5, fontWeight: 700 }}>{z[0]}</span>
        {!!b.req && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>🔒 обязательный — убрать нельзя</span>}
      </div>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <span style={CAP}>Название пункта</span>
        <input value={b.title} onChange={e => onPatch(b.id, { title: e.target.value })}
               style={{ height: 36, boxSizing: 'border-box', padding: '0 11px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, fontWeight: 600, outline: 'none', color: 'var(--text-primary)' }} />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <span style={CAP}>Текст · подстановки в фигурных скобках</span>
        <textarea value={b.text || ''} rows={6} onChange={e => onPatch(b.id, { text: e.target.value })}
                  style={{ boxSizing: 'border-box', padding: '10px 12px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 13, lineHeight: 1.55, resize: 'vertical', outline: 'none', color: 'var(--text-primary)', fontFamily: 'inherit' }} />
      </label>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={CAP}>Вставить подстановку · добавится в конец текста</span>
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {Object.keys(SUBS).map(k => {
            const prot = SUBS[k][1]
            return (
              <span key={k} onClick={() => addSub(k)} title={`${SUB_INFO[k]} · образец: ${SUBS[k][0]}`}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 26, padding: '0 9px', borderRadius: 7, background: prot ? 'var(--warning-tint)' : 'var(--bg-subtle)', border: `1px solid ${prot ? 'var(--warning-border)' : 'var(--border-card)'}`, color: prot ? 'var(--warning-fg)' : 'var(--text-secondary)', fontFamily: MONO, fontSize: 10.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>
                {prot ? '🔒 ' : ''}{`{${k}}`}
              </span>
            )
          })}
        </div>
      </div>
      {warningsOf(b).map(w => <Warn key={w.text} w={w} />)}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={CAP}>Как увидит аккаунт · на образце</span>
        <div style={{ padding: '12px 14px', background: 'var(--bg-subtle)', borderRadius: 11, fontFamily: "'Times New Roman', Georgia, serif", fontSize: 14, lineHeight: 1.55 }}>
          <b>{num[b.id]} </b><Segs text={b.text} />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, paddingTop: 4, borderTop: '1px solid var(--border-row)' }}>
        <Toggle on={!!b.sub} disabled={!canSub} label={`подпункт (${subLabel})`} color={['var(--accent-border)', 'var(--accent)']}
                onClick={() => onPatch(b.id, { sub: b.sub ? 0 : 1 })} />
        <Toggle on={!!b.req} disabled={baseReq} label="🔒 обязательный" color={['var(--warning-border)', 'var(--warning)']}
                title={baseReq ? 'пункт базового шаблона — обязательность закреплена' : b.req ? 'снять обязательность: аккаунт сможет убрать пункт в конкретном ДС' : 'сделать обязательным: пункт нельзя убрать в конкретном ДС'}
                onClick={() => onPatch(b.id, { req: b.req ? 0 : 1 })} />
        <span onClick={b.req ? undefined : () => onRemove(b.id)} title={b.req ? 'обязательный пункт — убрать нельзя' : 'убрать пункт из шаблона'}
              style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', borderRadius: 9, border: `1px solid ${b.req ? 'var(--border-card)' : 'var(--danger-border)'}`, color: b.req ? 'var(--text-disabled)' : 'var(--danger-fg)', background: 'var(--bg-card)', fontSize: 12, fontWeight: 700, cursor: b.req ? 'not-allowed' : 'pointer' }}>
          Убрать пункт
        </span>
      </div>
    </div>
  )
}
