import { useState, useEffect } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, UI, inp, btn } from '@/components/salesTableKit'
import { overlayClose } from '@/lib/overlay'

/* Маркировка бренда — ОДИН диалог на два места.

   Спрашивают её в двух разных точках, и обе законные: в справочнике рекламодателей,
   когда бренд заводят, и на карточке сделки, когда упёрлись в «не заполнен код ККТУ»
   перед выпуском ЕРИД. Вторая точка и есть та, где нехватку видно: до 27.08.2026
   оттуда приходилось уходить в справочник шестью шагами.

   Хранится код по-прежнему НА БРЕНДЕ — второго места правды не появляется, меняется
   только откуда до него дотянуться. */

/* Выбор кода ККТУ из справочника ОРД (зеркало `ord_kktu`, ручка
   /sales/directories/kktu). До 27.08.2026 код вводился строкой — и на вопрос «а где я
   его возьму» система не отвечала.

   Не ValuePopover: тот про НАКОПИТЕЛЬНЫЕ списки, куда значение можно дописать. Здесь
   классификатор чужой и закрытый — «+ Добавить» означал бы код, которого в реестре нет.

   Незалитое зеркало (`synced:false`) оставляет ручной ввод: справочник — удобство,
   а отнимать единственный рабочий путь удобство не вправе. */
export function KktuPicker({ value, onPick }) {
  const [q, setQ] = useState('')
  const [state, setState] = useState({ loading: true, synced: true, items: [], total: 0, shown: 0 })

  useEffect(() => {
    let alive = true
    const t = setTimeout(() => {
      api.get(`/sales/directories/kktu${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`, auth())
        .then(r => { if (alive) setState({ loading: false, ...r.data }) })
        .catch(() => { if (alive) setState(s => ({ ...s, loading: false })) })
    }, q ? 250 : 0)          // первый показ без задержки, набор — с ней
    return () => { alive = false; clearTimeout(t) }
  }, [q])

  const label = 'Код ККТУ'
  const head = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }

  if (!state.loading && !state.synced) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <div style={head}>{label}</div>
        <input style={{ ...inp, width: 160, fontFamily: MONO }} placeholder="58.13.12"
          value={value} onChange={e => onPick(e.target.value)} />
        <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
          Справочник ККТУ ещё не загружен из ОРД — код вводится вручную. Только третий
          уровень, три группы цифр через точку.
        </div>
      </div>
    )
  }

  const chosen = state.items.find(i => i.code === value)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <div style={head}>{label}</div>
        {!!value && (
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>
            {value}{chosen ? ` · ${chosen.name}` : ''}
          </span>
        )}
      </div>

      <input style={{ ...inp, width: '100%' }} value={q} onChange={e => setQ(e.target.value)}
        placeholder="поиск по коду или названию — «лекарств», «12.2»" />

      <div style={{ maxHeight: 190, overflowY: 'auto', border: '1px solid var(--border-card)',
        borderRadius: 8, background: 'var(--bg-subtle)' }}>
        {state.loading && <div style={{ padding: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>загрузка…</div>}
        {!state.loading && state.items.length === 0 && (
          <div style={{ padding: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>ничего не нашлось</div>
        )}
        {!state.loading && state.items.map(it => (
          <div key={it.code} onClick={() => onPick(it.code)}
            style={{ cursor: 'pointer', padding: '7px 10px', display: 'flex', gap: 10, alignItems: 'baseline',
              borderBottom: '1px solid var(--border-card)',
              background: it.code === value ? 'var(--accent-soft)' : 'transparent' }}>
            <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, minWidth: 56,
              color: it.code === value ? 'var(--accent)' : 'var(--text-secondary)' }}>{it.code}</span>
            <span style={{ fontSize: 12.5, lineHeight: 1.35 }}>
              {it.name}
              {!!it.path && <span style={{ color: 'var(--text-faint)' }}> · {it.path}</span>}
            </span>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
        Ровно один код на бренд, только третий уровень — верхние в списке не предлагаются.
        {!state.loading && state.shown < state.total
          ? ` Показаны ${state.shown} из ${state.total} — уточните поиск.`
          : ''}
      </div>
    </div>
  )
}

/* Маркировка бренда: код ККТУ и описание объекта рекламирования.
   Живут на бренде, а не на комплекте креативов, потому что это свойства товара —
   у одного бренда не меняются от кампании к кампании. Без кода ККТУ не выпустить ЕРИД,
   поэтому код виден прямо на плашке бренда: это состояние готовности, а не настройка.

   Компонент объявлен на модульном уровне — внутри тела страницы он пересоздавался бы
   на каждый рендер, и фокус слетал бы после каждого символа. */
export default function BrandMarkingDialog({ brand, onSave, onClose }) {
  const [kktu, setKktu] = useState(brand.kktu_code || '')
  const [text, setText] = useState(brand.ad_object_description || '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true); setErr('')
    try { await onSave({ kktu_code: kktu, ad_object_description: text }) } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось сохранить'); setBusy(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(16,20,30,.45)', zIndex: 60, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
      {...overlayClose(onClose)}>
      <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-card)', padding: '22px 24px', width: 'min(560px, 96vw)', boxShadow: 'var(--shadow-card)', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div style={{ fontSize: 17, fontWeight: 700 }}>Маркировка бренда «{brand.name}»</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 4 }}>
            Подставляется в каждый комплект креативов при выпуске ЕРИД.
          </div>
        </div>

        <KktuPicker value={kktu} onPick={setKktu} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Объект рекламирования</div>
          <textarea rows={4} value={text} onChange={e => setText(e.target.value)}
            placeholder="что именно рекламируется — товар, услуга, их свойства"
            style={{ ...inp, width: '100%', resize: 'vertical', fontFamily: UI, lineHeight: 1.5 }} />
          <div style={{ fontSize: 11.5, color: text.length > 1000 ? 'var(--dot-overdue)' : 'var(--text-muted)' }}>
            {text.length} из 1000 знаков
          </div>
        </div>

        {!!err && <div style={{ fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button style={btn(false)} onClick={onClose}>Отмена</button>
          <button style={btn(true)} disabled={busy} onClick={save}>Сохранить</button>
        </div>
      </div>
    </div>
  )
}

/* Сохранение маркировки — одно на оба вызова. Ответ возвращается наружу: справочник
   обновляет бренд на месте (перезагрузка списка сбросила бы раскрытые карточки), а
   карточка сделки просто перечитывает готовность к ЕРИД. */
export async function saveBrandMarking(brandId, payload) {
  const r = await api.put(`/sales/directories/brands/${brandId}/marking`, payload, auth())
  return r.data
}
