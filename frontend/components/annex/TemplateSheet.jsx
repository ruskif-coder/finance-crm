/**
 * Лист документа в окне шаблонов ДС (макет 13.10.2026): блоки по порядку, подстановки зелёным,
 * неизвестные и пустые — красным, метки зон справа в просмотре. Данные — образец.
 */
import { MONO } from '@/components/salesTableKit'
import { numbering, segs, zoneAt, emptyFields } from '@/lib/annexTemplate.mjs'

const SERIF = "'Times New Roman', Georgia, serif"
const GREEN = { color: 'var(--income-fg)', borderBottom: '1px solid var(--income-border)' }

const ZONE = {
  acc: ['правит аккаунт', 'var(--accent-tint)', 'var(--accent-fg)'],
  law: ['только юрист', 'var(--violet-tint)', 'var(--violet-fg)'],
}

const MP_ROWS = [
  ['Мезим', '', '', '', 700, 0, 'var(--text-primary)'],
  ['еФарм · баннеры', '01–30.11', '1 222 222', '450 000,00', 400, 14, 'var(--text-primary)'],
  ['Аптечество · карточка товара', '01–30.11', '—', '80 000,00', 400, 14, 'var(--text-primary)'],
  ['доп. · спецпроект', '01–30.11', '—', '20 000,00', 400, 14, 'var(--text-secondary)'],
]
const MP_TOTALS = [['Итого без НДС', '550 000,00', 400], ['НДС 22 %', '121 000,00', 400], ['Итого с НДС', '671 000,00', 700]]
const MP_GRID = 'minmax(0,1.6fr) 90px 80px 110px'
const mono = { fontFamily: MONO, fontSize: 10.5 }

export function Segs({ text, emptyDemo }) {
  return segs(text || '', emptyDemo).map((g, i) => {
    const mark = g.bad || g.sub
    return (
      <span key={i}
            title={g.empty ? 'не заполнено в сделке — выгрузка заблокирована' : g.bad ? 'неизвестная подстановка' : g.sub ? `{${g.sub}}${g.prot ? ' · защищена' : ''}` : undefined}
            style={mark ? { color: g.bad ? 'var(--danger-fg)' : 'var(--income-fg)', background: g.bad ? 'var(--danger-tint)' : 'var(--income-tint)', borderRadius: 3, padding: '0 2px' } : undefined}>
        {g.t}
      </span>
    )
  })
}

function MpTable() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', fontFamily: 'inherit', fontSize: 11.5, border: '1px solid var(--border-card)', borderRadius: 4 }}>
      <div style={{ display: 'grid', gridTemplateColumns: MP_GRID, gap: 8, padding: '6px 10px', background: 'var(--bg-subtle)', fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>
        <span>Бренд · услуга</span><span>Период</span><span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Сумма без НДС</span>
      </div>
      {MP_ROWS.map(([name, period, vol, sum, w, ind, fg]) => (
        <div key={name} style={{ display: 'grid', gridTemplateColumns: MP_GRID, gap: 8, padding: '5px 10px', borderTop: '1px solid var(--border-row)', fontWeight: w }}>
          <span style={{ paddingLeft: ind, color: fg }}>{name}</span>
          <span style={{ ...mono, color: 'var(--text-secondary)' }}>{period}</span>
          <span style={{ ...mono, textAlign: 'right', color: 'var(--text-secondary)' }}>{vol}</span>
          <span style={{ ...mono, textAlign: 'right' }}>{sum}</span>
        </div>
      ))}
      {MP_TOTALS.map(([label, v, w]) => (
        <div key={label} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 110px', gap: 8, padding: '5px 10px', borderTop: '1px solid var(--border-inner)', fontWeight: w }}>
          <span style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>{label}</span>
          <span style={{ ...mono, textAlign: 'right' }}>{v}</span>
        </div>
      ))}
    </div>
  )
}

function Parties() {
  const side = (who, name, fio) => (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <b>{who}</b><span style={{ ...GREEN, alignSelf: 'flex-start' }}>{name}</span>
      </span>
      <span>_______________ / {fio}</span>
      <span style={{ color: 'var(--text-faint)' }}>М.П.</span>
    </span>
  )
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 30, paddingTop: 14, fontSize: '0.93em' }}>
      {side('Исполнитель', 'ООО «ПРОГРАММАТИК МЕДИА»', 'Макаров Д.С.')}
      {side('Заказчик', 'ООО «Ромашка»', 'И. И. Иванов')}
    </div>
  )
}

function DocBlock({ b, i, blocks, num, edit, active, emptyDemo, onPick }) {
  const z = b.sys ? null : ZONE[zoneAt(blocks, i)]
  const tag = b.sys === 'table' ? ['граница', 'var(--bg-subtle)', 'var(--text-muted)'] : z
  const dateBad = emptyDemo
  return (
    <div onClick={() => edit && !b.sys && onPick(b.id)}
         style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 4, padding: '6px 8px', margin: '0 -8px', borderRadius: 6, background: active ? 'var(--bg-tint)' : 'transparent', outline: active ? '1px solid var(--accent-border)' : 'none', cursor: edit && !b.sys ? 'pointer' : 'default' }}>
      {b.sys === 'head' && (
        <span style={{ textAlign: 'right', fontSize: '0.93em' }}>
          Приложение № <b style={GREEN}>68</b><br />
          к Договору № <b style={GREEN}>РМ 30-11-2023</b> от{' '}
          <span title={dateBad ? 'не заполнено в реестре договоров — выгрузка заблокирована' : '{договор_дата}'}
                style={dateBad ? { color: 'var(--danger-fg)', background: 'var(--danger-tint)', padding: '0 2px', borderRadius: 3 } : { ...GREEN, padding: '0 2px' }}>
            {dateBad ? 'нет: дата договора' : '30.11.2023'}
          </span>
        </span>
      )}
      {b.sys === 'place' && <span style={{ display: 'flex', justifyContent: 'space-between' }}><span>г. Москва</span><span style={GREEN}>«31» октября 2026 г.</span></span>}
      {b.sys === 'pre' && (
        <span style={{ textAlign: 'justify', textIndent: '2em' }}>
          ООО «Ромашка», именуемое в дальнейшем «Заказчик», в лице Генерального директора Иванова Ивана Ивановича, действующего на основании Устава, с одной стороны, и Общество с ограниченной ответственностью «Программатик Медиа», именуемое в дальнейшем «Исполнитель», в лице Генерального директора Макарова Дениса Сергеевича, действующего на основании Устава, с другой стороны, заключили настоящее Приложение № 68 к Договору № РМ 30-11-2023 от 30.11.2023 (далее по тексту – «Договор») о нижеследующем:
        </span>
      )}
      {!b.sys && (
        <span style={{ textAlign: 'justify', textIndent: b.sub ? '2em' : 0 }}>
          <b>{num[b.id]}</b> <Segs text={b.text} emptyDemo={emptyDemo} />
        </span>
      )}
      {b.sys === 'table' && <MpTable />}
      {b.sys === 'sign' && <Parties />}
      {!edit && tag && (
        <span style={{ position: 'absolute', top: 7, right: -120, display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 7px', borderRadius: 6, background: tag[1], color: tag[2], fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
          {tag[0]}
        </span>
      )}
    </div>
  )
}

export default function TemplateSheet({ blocks, edit, sel, emptyDemo, onPick }) {
  const num = numbering(blocks)
  const empties = emptyDemo ? emptyFields(blocks) : []
  return (
    <div style={{ flex: edit ? '0 0 50%' : '1 1 100%', minWidth: 0, overflowY: 'auto', overflowX: 'hidden', background: 'var(--bg-canvas)', padding: 18, boxSizing: 'border-box', borderLeft: edit ? '1px solid var(--border-inner)' : 'none' }}>
      <div style={{ maxWidth: edit ? 840 : 1000, margin: '0 auto', boxSizing: 'border-box', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 6, boxShadow: 'var(--shadow-card)', padding: edit ? '26px 30px 24px' : '34px 140px 30px 44px', fontFamily: SERIF, fontSize: edit ? 12.5 : 14, lineHeight: 1.5, color: 'var(--text-primary)', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {!!empties.length && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '10px 12px', marginBottom: 4, background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, fontFamily: 'inherit' }}>
            <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--danger-fg)' }}>Выгрузка ДС заблокирована</span>
            {empties.map(e => (
              <span key={e.label} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>не заполнено <b style={{ color: 'var(--text-primary)' }}>{e.label}</b> — {e.where}</span>
            ))}
          </div>
        )}
        {blocks.map((b, i) => (
          <DocBlock key={b.id} b={b} i={i} blocks={blocks} num={num} edit={edit} active={edit && sel === b.id}
                    emptyDemo={emptyDemo} onPick={onPick} />
        ))}
      </div>
    </div>
  )
}
