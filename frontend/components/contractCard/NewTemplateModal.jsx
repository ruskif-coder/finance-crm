/**
 * «Новый шаблон ДС» — из карточки договора (хендофф «договорZ») и из реестра шаблонов (хендофф «шаблоны дс», 31.10.2026).
 *
 * Поля по макету реестра: договор, бренд, основа, «сделать основным ★». Из карточки договор уже задан — поле выбора не
 * показывается. Основа — базовый формата, основной договора или другой шаблон договора («пустого» нет: «Предмет» и
 * «Стоимость» обязательны — владелец 28.10.2026: «взять базовый»).
 *
 * Бренд пишется в память «договор + бренд → шаблон» (`annex_tpl_brand_memory`) — ту же, по которой сборка подставит шаблон
 * в следующий ДС этого бренда. Отдельной «привязки» не заводим: она разошлась бы с тем, что реально подставит сборка.
 *
 * Название подсказывается из юрлица и бренда («Альфарм · Ингавирин»), пока его не правили руками. Макет поля названия не
 * показывает, но без него шаблон не создать (название обязательно и уникально в договоре), поэтому оно есть — уже заполненное.
 *
 * Создаёт шаблон договора (`POST /annex-templates/custom`) и открывает его в конструкторе.
 */
import { useEffect, useMemo, useState } from 'react'
import { Modal, inp } from '@/components/salesTableKit'
import api, { auth } from '@/lib/http'
import { annexTemplatesApi as API, errorOf } from '@/lib/annexTemplatesApi'
import { cap, btnGhost, btnPrimary, Notice } from '@/components/contractCard/ui'

// Организационная форма — для подсказки названия: «АЛЬФАРМ ООО» → «АЛЬФАРМ». Само юр. название не трогаем.
const FORM = /(^|\s)(ООО|АО|ПАО|ЗАО|ОАО|НКО|АНО|ИП)(?=\s|$)/g
const entityShort = (s) => (s || '').replace(FORM, ' ').replace(/[«»"]/g, '').replace(/\s+/g, ' ').trim()

const chipStyle = (on) => ({
  display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 10px', borderRadius: 8,
  border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)',
  fontSize: 12, fontWeight: on ? 700 : 600, cursor: 'pointer',
})

export default function NewTemplateModal({ contractId: fixedId, templates: fixedTpls, sourceId, onClose, onCreated }) {
  const [contract, setContract] = useState(fixedId ? { id: fixedId } : null)
  const [contracts, setContracts] = useState(null)          // для выбора договора из реестра шаблонов
  const [q, setQ] = useState('')
  const [templates, setTemplates] = useState(fixedTpls || [])
  const [brands, setBrands] = useState([])
  const [brand, setBrand] = useState(null)                  // null — все бренды договора
  const [name, setName] = useState('')
  const [named, setNamed] = useState(false)                 // название правили руками — больше не подсказываем
  const [src, setSrc] = useState(null)
  const [main, setMain] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (fixedId) return
    api.get('/contracts/registry', auth())
      .then(r => setContracts((r.data && r.data.items) || r.data || []))
      .catch(() => setErr('Не удалось загрузить договоры'))
  }, [fixedId])

  // Выбрали договор — его шаблоны (если не переданы) и бренды. Основа по умолчанию: основной, иначе базовый.
  const cid = contract && contract.id
  useEffect(() => {
    if (!cid) return
    const pick = (list) => {
      const base = list.find(t => t.scope === 'base')
      setSrc(sourceId ?? (list.find(t => t.is_main) || base || list[0] || {}).id ?? null)
      setMain(!list.some(t => t.scope === 'custom' && t.is_main))     // основного нет — новый станет им
    }
    if (fixedTpls) pick(fixedTpls)
    else API.forContract(cid).then(d => { const list = d.templates || []; setTemplates(list); pick(list) })
      .catch(() => setErr('Не удалось загрузить шаблоны договора'))
    // Сбой загрузки брендов — СЛОВОМ, а не пустым списком: иначе осталось бы одно «все бренды договора», и шаблон создали
    // бы без бренда, решив, что брендов у договора нет (гейт check-screens).
    API.brands(cid).then(setBrands)
      .catch(() => setErr('Не удалось загрузить бренды договора — без них шаблон создастся для всех брендов'))
  // Зависимости честные: карточка договора, пока окно открыто, данных не перечитывает (`useRefreshOnReturn` с `enabled: !newTpl`),
  // так что `fixedTpls`/`sourceId` не меняются и выбор основы не сбрасывается посреди правки.
  }, [cid, fixedTpls, sourceId])

  const brandName = brand ? (brands.find(b => b.id === brand) || {}).name : null
  useEffect(() => {
    if (named) return
    const ent = entityShort(contract && contract.counterparty_name)
    setName([ent, brandName || (ent ? 'все бренды' : '')].filter(Boolean).join(' · '))
  }, [contract, brandName, named])

  const found = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (contracts || []).filter(c => !s || [c.contract_number, c.counterparty_name, c.inn]
      .some(v => (v || '').toLowerCase().includes(s))).slice(0, 40)
  }, [contracts, q])

  const base = templates.find(t => t.scope === 'base')
  const noFormat = !!contract && !fixedId && !contract.cooperation_format
  const taken = templates.some(t => t.scope === 'custom' && (t.title || '').toLowerCase() === name.trim().toLowerCase())
  const ok = !!contract && !!name.trim() && !taken && src != null
  const fromBase = base && src === base.id

  const create = async () => {
    setBusy(true); setErr('')
    try {
      const t = await API.fork(contract.id, { title: name.trim(), sourceId: src, main, brandId: brand })
      onCreated(t.id, contract)
    } catch (e) { setErr(errorOf(e, 'Не удалось создать шаблон').message) }
    finally { setBusy(false) }
  }

  return (
    <Modal title="Новый шаблон ДС" width={560} onClose={onClose}
           footer={<span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
             <button type="button" onClick={onClose} style={btnGhost}>Отмена</button>
             <button type="button" onClick={create} disabled={!ok || busy} style={{ ...btnPrimary, opacity: ok ? 1 : 0.5, cursor: ok ? 'pointer' : 'not-allowed' }}>
               {busy ? 'Создаю…' : 'Открыть в конструкторе →'}
             </button>
           </span>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '6px 0' }}>
        {err && <Notice tone="danger">{err}</Notice>}

        {!fixedId && (
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <span style={cap}>Договор</span>
            {contract
              ? <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>{contract.contract_number || `№ ${contract.id}`}</span>
                  <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{contract.counterparty_name}</span>
                  <span onClick={() => { setContract(null); setBrand(null); setBrands([]); setTemplates([]); setSrc(null) }}
                        style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>сменить</span>
                </span>
              : <>
                  <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Номер договора, юрлицо или ИНН"
                         style={{ ...inp, height: 36 }} />
                  <span style={{ display: 'flex', flexDirection: 'column', maxHeight: 220, overflowY: 'auto', border: '1px solid var(--border-card)', borderRadius: 10 }}>
                    {contracts === null && <span style={{ padding: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>Загрузка…</span>}
                    {found.map(c => (
                      <span key={c.id} onClick={() => setContract(c)}
                            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', borderBottom: '1px solid var(--border-row)', cursor: 'pointer' }}
                            onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-subtle)' }}
                            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                        <span style={{ fontSize: 12.5, fontWeight: 700, minWidth: 120 }}>{c.contract_number || '—'}</span>
                        <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.counterparty_name || '—'}</span>
                        {!c.cooperation_format && <span style={{ fontSize: 11, color: 'var(--warning-fg)' }}>нет формата</span>}
                      </span>
                    ))}
                    {contracts !== null && !found.length && <span style={{ padding: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>Ничего не найдено</span>}
                  </span>
                </>}
          </span>
        )}

        {noFormat && (
          <Notice tone="warning">У договора не указан «Формат сотрудничества» — нет базового шаблона, создавать не из чего.
            Сначала укажите формат в реестре договоров.</Notice>
        )}

        {!!contract && !noFormat && (
          <>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={cap}>Бренд</span>
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <span onClick={() => setBrand(null)} style={chipStyle(brand === null)}>все бренды договора</span>
                {brands.map(b => <span key={b.id} onClick={() => setBrand(b.id)} style={chipStyle(brand === b.id)}>{b.name}</span>)}
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Выберите бренд, если шаблон только для него, — тогда ДС этого бренда соберётся по нему.</span>
            </span>

            <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={cap}>Название</span>
              <input value={name} onChange={e => { setName(e.target.value); setNamed(true) }} placeholder="например «Фарма»" style={{ ...inp, height: 36 }} />
              {taken && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>Шаблон с таким названием у договора уже есть</span>}
            </span>

            <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={cap}>Основа</span>
              {fromBase && <Notice>Базовый шаблон общий для формата договора — создаётся копия, базовый не меняется</Notice>}
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {templates.map(t => (
                  <span key={t.id} onClick={() => setSrc(t.id)} style={chipStyle(src === t.id)}>
                    {t.scope === 'base' ? `базовый «${t.title}»` : `${t.is_main ? '★ ' : ''}${t.title}`}
                  </span>
                ))}
              </span>
            </span>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="checkbox" checked={main} onChange={e => setMain(e.target.checked)} />
              сделать основным ★ — новые ДС собираются по нему; у договора основной один, звезда с прежнего снимется
            </label>
          </>
        )}
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.45 }}>Текст шаблона, пункты и подстановки правятся в конструкторе. Уже выпущенные ДС остаются на своей версии.</span>
      </div>
    </Modal>
  )
}
