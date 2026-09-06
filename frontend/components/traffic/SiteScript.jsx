/**
 * Админка трафика → вкладка «Скрипт».
 *
 * Наш счётчик вшивается В КРЕАТИВ перед отправкой в DSP — внутрь его `<head>`, — а НЕ
 * ставится площадкой на сайт (уточнение владельца 06.09.2026).
 *
 * Скриптов ДВА: свой для площадок, где наш код на сайте уже стоит, и свой для тех, где
 * его нет. Поэтому две колонки: в каждой своя строка скрипта и свой список площадок.
 *
 * Признак «код стоит» — `sales_publishers.our_code`, тот же, что в карточке паблишера.
 * Второго флага для того же факта здесь нет и быть не должно: два признака одного
 * состояния расходятся, и потом не понять, какой верен.
 */
import { useCallback, useEffect, useState } from 'react'
import { MONO, UI, card, inp, btn, primaryBtn } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'

const LBL = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const BOX = { ...card, padding: '16px 18px' }

/** Колонка: скрипт + площадки, к которым он применяется.
 *
 *  Объявлена на уровне модуля: компонент внутри компонента пересоздаётся на каждый рендер,
 *  и поле теряет фокус после каждого символа — это ловит гейт check-inline. */
function Column({ title, tone, hint, script, onScript, items, mayEdit, suggested, onSave, saving, dirty }) {
  const empty = !String(script || '').trim()
  return (
    <div style={BOX}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
        <i style={{ width: 8, height: 8, borderRadius: 2, background: tone }} />
        <span style={{ fontSize: 14, fontWeight: 700 }}>{title}</span>
        <span style={{ ...LBL, marginLeft: 'auto' }}>{items.length}</span>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 10 }}>{hint}</div>

      <div style={{ ...LBL, marginBottom: 4, color: empty ? 'var(--warning-text)' : 'var(--text-faint)' }}>
        Скрипт в креатив{empty ? ' · не задан' : ''}
      </div>
      <input value={script || ''} onChange={e => onScript(e.target.value)} readOnly={!mayEdit}
        placeholder="<script src=…></script>"
        style={{ ...inp, width: '100%', fontFamily: MONO, fontSize: 12.5,
          borderColor: empty ? 'var(--warning)' : 'var(--border-card)',
          background: empty ? 'var(--warning-tint)' : 'var(--bg-card)' }} />
      {mayEdit && (
        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          {dirty && (
            <button onClick={onSave} disabled={saving} style={primaryBtn}>
              {saving ? 'Сохраняю…' : 'Сохранить'}
            </button>
          )}
          {script !== suggested && (
            <button onClick={() => onScript(suggested)} style={btn(false)}>Подставить qq.js</button>
          )}
          {!empty && <button onClick={() => onScript('')} style={btn(false)}>Очистить</button>}
        </div>
      )}

      <div style={{ ...LBL, margin: '16px 0 6px' }}>Площадки</div>
      <div style={{ maxHeight: 380, overflowY: 'auto' }}>
        {items.map(p => (
          <div key={p.id} style={{ display: 'flex', alignItems: 'baseline', gap: 8,
            padding: '7px 0', borderBottom: '1px solid var(--border-row)' }}>
            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700,
              color: p.code ? 'var(--text-faint)' : 'var(--danger)', width: 46, flexShrink: 0 }}>
              {p.code || '—'}
            </span>
            <a href={`/publishers/${p.id}`} style={{ fontSize: 13, fontWeight: 600,
              color: 'var(--text-primary)', textDecoration: 'none' }}>{p.name}</a>
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11.5,
              color: 'var(--text-secondary)' }}>{p.domain}</span>
          </div>
        ))}
        {!items.length && (
          <div style={{ padding: '14px 0', fontSize: 13, color: 'var(--text-secondary)' }}>Пусто.</div>
        )}
      </div>
    </div>
  )
}

export default function SiteScript({ mayEdit }) {
  const [data, setData] = useState(null)
  const [withCode, setWithCode] = useState('')
  const [noCode, setNoCode] = useState('')
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await api.get('/traffic-catalog/site-script', auth())
      setData(r.data)
      setWithCode(r.data.with_code.script || '')
      setNoCode(r.data.without_code.script || '')
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось загрузить настройку') }
  }, [])

  useEffect(() => { load() }, [load])

  const save = async () => {
    setSaving(true); setErr('')
    try {
      await api.put('/traffic-catalog/site-script',
        { with_code: withCode, without_code: noCode }, auth())
      await load()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось сохранить') }
    finally { setSaving(false) }
  }

  if (!data) {
    return <div style={{ padding: 24, color: 'var(--text-muted)', fontFamily: UI }}>Загрузка…</div>
  }
  const dirtyWith = withCode !== (data.with_code.script || '')
  const dirtyNo = noCode !== (data.without_code.script || '')

  return (
    <div style={{ fontFamily: UI }}>
      {!!err && (
        <div style={{ ...BOX, borderColor: 'var(--danger)', color: 'var(--danger)', marginBottom: 14 }}>
          {err}
        </div>
      )}

      {/* Куда именно попадает скрипт — сказано один раз и наверху: от этого зависит,
          что человек вообще сюда впишет. */}
      <div style={{ ...BOX, marginBottom: 14 }}>
        <div style={{ ...LBL, marginBottom: 6 }}>Куда вшивается</div>
        <div style={{ fontSize: 13, lineHeight: 1.6 }}>
          Внутрь <code style={{ fontFamily: MONO }}>&lt;head&gt;</code> самого креатива,
          перед отправкой в DSP — не на сайт площадки. Какой из двух скриптов возьмётся,
          решает признак «наш код стоит» у площадки; он меняется в её карточке.
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Column title="Наш код на сайте стоит" tone="var(--income)"
          hint="Счётчик на сайте уже работает — в креатив вшиваем то, что нужно дополнительно"
          script={withCode} onScript={setWithCode} items={data.with_code.publishers}
          mayEdit={mayEdit} suggested={data.suggested} onSave={save} saving={saving}
          dirty={dirtyWith} />
        <Column title="Нашего кода на сайте нет" tone="var(--warning)"
          hint="Данные собирает только креатив — вшиваем полный счётчик"
          script={noCode} onScript={setNoCode} items={data.without_code.publishers}
          mayEdit={mayEdit} suggested={data.suggested} onSave={save} saving={saving}
          dirty={dirtyNo} />
      </div>
    </div>
  )
}
