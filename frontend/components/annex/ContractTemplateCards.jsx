/**
 * Первый экран окна «Шаблон ДС» договора (владелец 28.10.2026): карточки шаблонов, прикреплённых к договору — основной, остальные
 * именованные, базовый формата — с версией, датой правки и отметкой «основной»; нажатие открывает текст шаблона. Карточка «+ Новый
 * шаблон» — копия выбранного шаблона под новым именем. «ДС договора» — отдельной кнопкой в строке реестра договоров.
 */
import { useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { fmtDate } from '@/lib/dates'
import { NameForm } from '@/components/annex/ContractTemplatesBar'
import { capTxt, small } from '@/components/annex/TemplateBars'

function Card({ t, onPick }) {
  const base = t.scope === 'base'
  return (
    <div onClick={onPick}
         style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '16px 18px', background: 'var(--bg-card)', border: `1px solid ${t.is_main ? 'var(--violet-border)' : 'var(--border-card)'}`, borderRadius: 14, cursor: 'pointer' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        {t.is_main && <span style={{ color: 'var(--warning)' }}>★</span>}
        <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em' }}>{t.title}</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>v{t.version}</span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px', borderRadius: 6, background: base ? 'var(--bg-subtle)' : 'var(--violet-tint)', color: base ? 'var(--text-secondary)' : 'var(--violet-fg)', fontSize: 10.5, fontWeight: 700 }}>
          {base ? 'базовый формата договора' : t.is_main ? 'основной шаблон договора' : 'шаблон договора'}
        </span>
        {!base && t.base_title && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>от «{t.base_title}»</span>}
        {t.base && t.base.changed && <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--warning-fg)' }}>базовый изменился</span>}
      </div>
      <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
        правка {fmtDate(t.updated_at)} · {t.author || '—'}
      </span>
    </div>
  )
}

function NewCard({ templates, busy, onCreate }) {
  const [open, setOpen] = useState(false)
  const [src, setSrc] = useState(templates[0] ? templates[0].id : null)
  const [main, setMain] = useState(false)
  const taken = templates.filter(t => t.scope === 'custom').map(t => t.title)
  if (!open) {
    return (
      <div onClick={() => setOpen(true)}
           style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 120, border: '1px dashed var(--violet-border)', borderRadius: 14, fontSize: 13, fontWeight: 600, color: 'var(--violet-fg)', cursor: 'pointer' }}>
        + Новый шаблон
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '14px 16px', border: '1px solid var(--violet-border)', borderRadius: 14, background: 'var(--bg-tint)' }}>
      <NameForm taken={taken} okText={busy ? 'Создаю…' : 'Создать'} onCancel={() => setOpen(false)}
                onOk={async (title) => { if (await onCreate(title, src, main)) setOpen(false) }} />
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 11.5, color: 'var(--text-secondary)' }}>
        копия
        {templates.map(t => (
          <span key={t.id} onClick={() => setSrc(t.id)}
                style={{ ...small, height: 24, borderColor: src === t.id ? 'var(--violet-border)' : 'var(--border-card)', color: src === t.id ? 'var(--violet-fg)' : 'var(--text-secondary)', background: src === t.id ? 'var(--violet-tint)' : 'var(--bg-card)' }}>
            {t.title}
          </span>
        ))}
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
          <input type="checkbox" checked={main} onChange={e => setMain(e.target.checked)} />основной
        </label>
      </span>
    </div>
  )
}

export default function ContractTemplateCards({ templates, mayCreate, busy, onPick, onCreate }) {
  return (
    <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: '22px 24px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <span style={capTxt}>Шаблоны, прикреплённые к договору · основной подставляется в новый ДС, если для бренда шаблон ещё не выбирали</span>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 14 }}>
        {templates.map(t => <Card key={t.id} t={t} onPick={() => onPick(t.id)} />)}
        {mayCreate && !!templates.length && <NewCard templates={templates} busy={busy} onCreate={onCreate} />}
      </div>
      {!templates.length && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Шаблонов нет: у договора не указан формат сотрудничества или формату не назначен базовый шаблон.</span>}
    </div>
  )
}
