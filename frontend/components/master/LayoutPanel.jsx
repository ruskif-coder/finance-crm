/**
 * Панель раскладки (дизайн §3–4, §7–8): стартовый № ДС, «Раскладка изменена», шаги 1–4, «Получится», «В YYYY-MM закрывали так».
 * Настройки меняют ЧЕРНОВИК (`draft`), предпросмотр считает сервер; «Сохранить раскладку» пишет. После выпуска ДС всё погашено.
 */
import { useState } from 'react'
import Link from 'next/link'
import api, { auth } from '@/lib/api'
import { MONO, UI, btn, inp, Segmented } from '@/components/salesTableKit'
import { isAdmin } from '@/lib/auth'
import { fmtDateTimeShort } from '@/lib/dates'
import { rub2 } from '@/lib/salesFormat'
import { CAP, CARD, Note, SETTING_LABEL, num, plural, sameSettings } from '@/components/master/kit'

// Кнопки внутри узкой панели (330px) — компактные, в одну строку.
const SMALL = { padding: '6px 12px', fontSize: 12.5, whiteSpace: 'nowrap', height: 32 }

const Switch = ({ on, label, disabled, onClick }) => (
  <button type="button" disabled={disabled} onClick={onClick}
    style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 0, padding: '4px 0', cursor: disabled ? 'default' : 'pointer', fontFamily: UI, opacity: disabled ? 0.5 : 1 }}>
    <span style={{ width: 34, height: 20, flex: '0 0 34px', borderRadius: 10, background: on ? 'var(--income)' : 'var(--border-hover)', position: 'relative' }}>
      <span style={{ position: 'absolute', top: 2, left: on ? 16 : 2, width: 16, height: 16, borderRadius: '50%', background: 'var(--bg-card)', transition: 'left .15s' }} /></span>
    <b style={{ fontSize: 13, color: 'var(--text-primary)' }}>{label}</b>
  </button>
)

const Chip = ({ on, label, disabled, onClick }) => (
  <button type="button" disabled={disabled} onClick={onClick}
    style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 34, padding: '0 12px', borderRadius: 10, fontFamily: UI, fontWeight: 700, fontSize: 13,
      cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1, border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`,
      background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>
    <span style={{ width: 15, height: 15, borderRadius: 4, border: `1.5px solid ${on ? 'var(--accent)' : 'var(--border-hover)'}`, background: on ? 'var(--accent)' : 'transparent',
      color: 'var(--bg-card)', fontSize: 11, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{on ? '✓' : ''}</span>{label}
  </button>
)

const Step = ({ n, title, hint, children }) => (
  <div style={{ padding: '12px 0', borderTop: '1px solid var(--border-row)' }}>
    <b style={{ fontSize: 14 }}>{n}. {title}</b>
    <div style={{ fontSize: 12, color: 'var(--text-muted)', margin: '3px 0 8px', lineHeight: 1.45 }}>{hint}</div>
    {children}
  </div>
)

// Вид документа по договору (владелец 31.10.2026): выбирается здесь, при первой сборке, вместе со стартовым номером, и
// фиксируется в договоре. Дальше переключать может только администратор — сервер держит то же правило (`doc_kind.assign`).
// Не выбран — для мастер-сделки предвыбрано «ДС»: так документы пакета печатаются и сейчас (решение 15.10.2026).
const WORDS = [{ value: 'приложение', label: 'Приложение' }, { value: 'дс', label: 'ДС' }]
const wordLabel = (w) => (w === 'дс' ? 'ДС' : w === 'приложение' ? 'Приложение' : 'не выбран')

function StartNo({ m, locked, busy, onSave }) {
  const fixed = (m.contract && m.contract.annex_word) || null
  const mayWord = !fixed || isAdmin()                          // первичный выбор — любому, кто собирает; дальше — админ
  const [word, setWord] = useState(fixed || 'дс')
  const [edit, setEdit] = useState(m.start_no == null)
  const [v, setV] = useState(m.start_no != null ? String(m.start_no) : (m.last_issued != null ? String(m.last_issued) : ''))
  const [chk, setChk] = useState(null)
  const n = num(v)
  const bad = v !== '' && !(Number.isInteger(n) && n >= 0)
  const check = async (val) => {
    setV(val)
    const x = num(val)
    if (!(Number.isInteger(x) && x >= 0)) { setChk(null); return }
    try { setChk((await api.get(`/master-deals/${m.code}/start-no/check`, { ...auth(), params: { no: x } })).data) } catch { setChk(null) }
  }
  if (!edit) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderRadius: 12, background: 'var(--bg-subtle)', fontSize: 13 }}>
        <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--income)' }} />
        <span>Последний ДС по договору — № <b style={{ fontFamily: MONO }}>{m.start_no}</b></span>
        <span style={{ color: 'var(--text-muted)' }}>· вид документа: <b style={{ color: fixed ? 'var(--text-primary)' : 'var(--warning-fg)' }}>{wordLabel(fixed)}</b></span>
        {!locked && <button type="button" onClick={() => setEdit(true)} style={{ marginLeft: 'auto', border: 0, background: 'none', color: 'var(--accent)', fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>изменить</button>}
      </div>
    )
  }
  const blocked = busy || bad || v === '' || (chk && !chk.ok)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 12px', borderRadius: 12, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)' }}>
      <span style={{ fontSize: 12.5, color: 'var(--warning-text)', fontWeight: 700 }}>{m.start_no == null ? 'Стартовый номер ДС не задан' : 'Последний ДС по договору'}</span>
      <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Введите последний актуальный № по договору — ДС пакета пронумеруются от следующего.</span>
      <div style={{ display: 'flex', gap: 8 }}>
        <input value={v} onChange={e => check(e.target.value)} placeholder="№" disabled={locked}
          style={{ ...inp, width: 90, fontFamily: MONO, borderColor: bad || (chk && !chk.ok) ? 'var(--danger-border)' : undefined }} />
        <button type="button" disabled={blocked} onClick={async () => { if (await onSave(n, mayWord ? word : undefined)) setEdit(false) }} style={{ ...btn(true), opacity: blocked ? 0.5 : 1 }}>Сохранить</button>
        {m.start_no != null && <button type="button" onClick={() => setEdit(false)} style={btn(false)}>Отмена</button>}
      </div>
      {chk && !chk.ok && (
        <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>{chk.text}{' '}
          <button type="button" onClick={() => check(String(chk.last))} style={{ border: 0, background: 'none', color: 'var(--accent)', cursor: 'pointer', fontWeight: 700 }}>Подставить № {chk.last}</button></span>
      )}
      {chk?.warn && <span style={{ fontSize: 11.5, color: 'var(--warning-text)' }}>{chk.warn}</span>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', paddingTop: 2 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Вид документа по договору</span>
        <Segmented value={word} options={WORDS} onChange={setWord} disabled={!mayWord || locked}
                   title={mayWord ? 'Каким словом называются ДС по этому договору — в номере и тексте. Фиксируется в договоре'
                                  : 'Вид уже выбран — изменить может только администратор'} />
        {!fixed && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>выбирается один раз — дальше менять сможет только администратор</span>}
      </div>
    </div>
  )
}

export default function LayoutPanel({ m, draft, preview, locked, busy, onDraft, onSave, onRevert, onStartNo, onTakePrev }) {
  const lay = preview || m.layout
  const changed = !sameSettings(draft, m.settings)
  const set = (patch) => onDraft({ ...draft, ...patch })
  const toggle = (k) => set({ [k]: !draft[k] })
  const diff = m.prev ? Object.keys(SETTING_LABEL).filter(k => m.prev.settings[k] !== draft[k]) : []
  const sumOk = Math.abs(lay.total_net - m.deals_total_net) < 0.05
  return (
    <div style={{ ...CARD, padding: '16px 18px', position: 'sticky', top: 12 }}>
      <div style={{ ...CAP, marginBottom: 10 }}>Раскладка</div>
      {m.issued_ds ? (
        <Note tone="ok">ДС № {m.issued_ds.no} выпущен {fmtDateTimeShort(m.issued_ds.at)} — раскладка закреплена. Изменить — через отзыв ДС у юриста.</Note>
      ) : locked ? (
        <Note tone="ok">ДС пакета созданы — раскладка только для чтения. Править — «Вернуть в раскладку» внизу, пока ДС не подтверждены.</Note>
      ) : <StartNo m={m} locked={locked} busy={busy} onSave={onStartNo} />}
      {changed && !locked && (
        <div style={{ marginTop: 10, padding: '12px 14px', borderRadius: 12, background: 'var(--bg-tint)', border: '1px solid var(--accent-border)' }}>
          <b style={{ display: 'block', fontSize: 14, color: 'var(--accent-fg)' }}>Раскладка изменена</b>
          {!!m.saved && <span style={{ ...CAP, fontWeight: 600, color: 'var(--text-muted)' }}>сохранена {m.saved.by || ''} · {fmtDateTimeShort(m.saved.at)}</span>}
          <span style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button type="button" onClick={onRevert} style={{ ...btn(false), ...SMALL }}>Вернуть</button>
            <button type="button" disabled={busy} onClick={onSave} style={{ ...btn(true), ...SMALL }}>Сохранить раскладку</button>
          </span>
        </div>
      )}
      <div style={{ pointerEvents: locked ? 'none' : 'auto', opacity: locked ? 0.5 : 1, marginTop: 6 }}>
        <Step n={1} title="Допы отдельным ДС" hint={lay.has_paid_extras ? 'Платные допы — своё ДС № n-01. Выключено — строками в ДС основных услуг.' : 'Платных допов нет'}>
          <Switch on={!!draft.addons_separate && lay.has_paid_extras} disabled={!lay.has_paid_extras} label={draft.addons_separate ? 'Допы — ДС № n-01' : 'Всё одним ДС'} onClick={() => toggle('addons_separate')} />
        </Step>
        <Step n={2} title="Бонусные допы" hint="Допы со стоимостью 0.">
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <Chip on={draft.bonus_addons === 'zero'} label="строкой с нулём" onClick={() => set({ bonus_addons: 'zero' })} />
            <Chip on={draft.bonus_addons === 'hide'} label="не включать" onClick={() => set({ bonus_addons: 'hide' })} />
          </div>
        </Step>
        <Step n={3} title="Строки ДС группировать по" hint="Ничего не отмечено — одна группа на ДС.">
          <div style={{ display: 'flex', gap: 6 }}>
            <Chip on={draft.ds_by_brand} label="Бренд" onClick={() => toggle('ds_by_brand')} />
            <Chip on={draft.ds_by_service} label="Услуга" onClick={() => toggle('ds_by_service')} />
          </div>
        </Step>
        <Step n={4} title="Закрывающие делить по" hint="Комплект = счёт + УПД + отчёт. Ничего не отмечено — один комплект на ДС.">
          <div style={{ display: 'flex', gap: 6 }}>
            <Chip on={draft.upd_by_brand} label="Бренд" onClick={() => toggle('upd_by_brand')} />
            <Chip on={draft.upd_by_service} label="Услуга" onClick={() => toggle('upd_by_service')} />
          </div>
        </Step>
      </div>

      <div style={{ marginTop: 6, padding: '12px 14px', borderRadius: 12, background: 'var(--bg-tint)', border: '1px solid var(--accent-border)' }}>
        <span style={CAP}>Получится</span>
        <div style={{ display: 'flex', gap: 22, marginTop: 6 }}>
          <span><b style={{ fontFamily: MONO, fontSize: 24, color: 'var(--accent-fg)' }}>{lay.ds.length}</b><span style={{ display: 'block', fontSize: 11.5, color: 'var(--text-muted)' }}>ДС</span></span>
          <span><b style={{ fontFamily: MONO, fontSize: 24, color: 'var(--accent-fg)' }}>{lay.upd_count}</b>
            <span style={{ display: 'block', fontSize: 11.5, color: 'var(--text-muted)' }}>{plural(lay.upd_count, ['комплект', 'комплекта', 'комплектов'])} закрывающих</span></span>
        </div>
        <div style={{ fontSize: 12.5, marginTop: 8 }}>Пакет <b style={{ fontFamily: MONO }}>{rub2(lay.total_net)}</b> до НДС</div>
        <div style={{ fontSize: 12, marginTop: 4, color: sumOk ? 'var(--income-fg)' : 'var(--danger-fg)' }}>
          {sumOk ? '= сумме сделок к закрытию' : `не сходится с суммой сделок ${rub2(m.deals_total_net)}`}</div>
      </div>

      {m.prev && (
        <div style={{ marginTop: 12, padding: '12px 14px', borderRadius: 12, background: diff.length ? 'var(--warning-bg)' : 'var(--income-tint)',
          border: `1px solid ${diff.length ? 'var(--warning-border)' : 'var(--income-border)'}` }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <b style={{ fontSize: 13, color: diff.length ? 'var(--warning-text)' : 'var(--income-fg)' }}>В {m.prev.period} закрывали так</b>
            <Link href={`/accounts/master/${m.prev.code}`} style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12, color: 'var(--accent)' }}>{m.prev.code}</Link>
          </div>
          <div style={{ fontFamily: MONO, fontSize: 12.5, margin: '4px 0' }}>{m.prev.ds} ДС · {m.prev.kits} {plural(m.prev.kits, ['комплект', 'комплекта', 'комплектов'])}</div>
          {diff.length ? (
            <>
              <div style={{ fontSize: 12, color: 'var(--warning-text)' }}>раскладка отличается — {diff.length} {plural(diff.length, ['настройка', 'настройки', 'настроек'])}</div>
              {diff.map(k => (
                <div key={k} style={{ display: 'flex', gap: 6, fontSize: 11.5, marginTop: 3 }}>
                  <span style={{ color: 'var(--text-muted)' }}>{SETTING_LABEL[k][0]}</span>
                  <span style={{ marginLeft: 'auto', color: 'var(--text-faint)' }}>{SETTING_LABEL[k][1](m.prev.settings[k])}</span>→<b>{SETTING_LABEL[k][1](draft[k])}</b>
                </div>
              ))}
              {!locked && <button type="button" onClick={onTakePrev} style={{ ...btn(false), marginTop: 8, color: 'var(--accent)' }}>Взять раскладку {m.prev.code}</button>}
            </>
          ) : <div style={{ fontSize: 12, color: 'var(--income-fg)' }}>раскладка совпадает</div>}
        </div>
      )}
    </div>
  )
}
