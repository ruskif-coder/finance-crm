/**
 * Админка трафика → вкладка «Скрипт». Раскладка NAVY (хендофф docs/design_handoff_traffic_admin_script_navy.zip, 19.11.2026):
 * тёмная плашка автоматики сверху и две колонки — слева «Что добавляется в креатив» и «Кабинеты и аккаунты», справа скрипт по
 * площадкам. Функционал прежний; части разметки — `./script/scriptParts.jsx`.
 *
 * Наш счётчик вшивается В КРЕАТИВ перед отправкой в DSP — внутрь его `<head>`, — а НЕ ставится площадкой на сайт (уточнение
 * владельца 06.09.2026). Скриптов ДВА: для площадок, где наш код на сайте уже стоит, и для тех, где его нет. Признак «код
 * стоит» — `sales_publishers.our_code`, тот же, что в карточке паблишера; второго флага для того же факта нет и быть не должно.
 *
 * Кабинеты DSP — три хеша (владелец 28.09.2026): боевые РК идут в кабинет боевого клиента, нацеливание — в кабинет демоклиента
 * и запущенную кампанию в нём; совпадение боевого и демо запрещено (28.09 боевые РК однажды ушли в кабинет демоклиента).
 * Аккаунт WCM — здесь же: кнопка «ПИКСЕЛЬ WR» читает НАСТРОЙКУ, одно значение — одно место (17.09.2026).
 */
import { useCallback, useEffect, useState } from 'react'
import { MONO, UI } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { contrastTone, useThemeKey } from '@/lib/theme'
import { detailText } from '@/lib/loadError'
import { useTargetingCampaign } from './TargetingCampaign'
import { AutoBar, CARD, CampaignPlaque, CardHead, ExtraField, IdRow, SCRIPT_CSS, ScriptGroup } from './script/scriptParts'

// Сервер отдаёт скрипты колонок вложенными, остальное — плоско; форма держит всё плоско
const formOf = (d) => ({
  with_code: d.with_code.script || '', without_code: d.without_code.script || '', viewability: d.viewability || '',
  teaser_icon: d.teaser_icon || '', prod_partner: d.prod_partner || '', targeting_partner: d.targeting_partner || '',
  targeting_campaign: d.targeting_campaign || '', weborama_account: d.weborama_account || '',
})

export default function SiteScript({ mayEdit }) {
  const [data, setData] = useState(null)
  const [saved, setSaved] = useState(null)        // форма как на сервере — с ней сравниваем «изменено»
  const [form, setForm] = useState(null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [autoBusy, setAutoBusy] = useState(false)
  // Что стоит за хешем демокампании: имя, статус и сроки. Остановленная кампания не покажет на площадке ничего.
  const tgt = useTargetingCampaign()
  const tone = contrastTone(useThemeKey())

  const load = useCallback(async () => {
    try {
      const r = await api.get('/traffic-catalog/site-script', auth())
      const f = formOf(r.data)
      setData(r.data); setSaved(f); setForm(f)
    } catch (e) { setErr(detailText(e, 'Не удалось загрузить настройку')) }
  }, [])
  useEffect(() => { load() }, [load])

  const save = async () => {
    setSaving(true); setErr('')
    try { await api.put('/traffic-catalog/site-script', form, auth()); await load() }
    catch (e) { setErr(detailText(e, 'Не удалось сохранить')) }
    finally { setSaving(false) }
  }
  // Пиксель и DSP сами (трафики 19.11.2026): сохраняется сразу, отдельно от полей — остальные значения не трогаются
  const toggleAuto = async (on) => {
    setAutoBusy(true); setErr('')
    try { await api.put('/traffic-catalog/site-script', { auto_external: on }, auth()); setData(d => ({ ...d, auto_external: on })) }
    catch (e) { setErr(detailText(e, 'Не удалось переключить')) }
    finally { setAutoBusy(false) }
  }

  if (!data || !form) {
    return <div style={{ padding: 24, color: 'var(--text-muted)', fontFamily: UI }}>{err || 'Загрузка…'}</div>
  }
  const set = (k) => (v) => setForm(f => ({ ...f, [k]: v }))
  const dirty = (...ks) => ks.some(k => form[k] !== saved[k])
  const empty = (k) => !String(form[k] || '').trim()
  const ro = !mayEdit
  // Одинаковые боевой и демо-кабинет — РК ушли бы в кабинет нацеливания (28.09.2026)
  const sameCab = !empty('prod_partner') && form.prod_partner.trim().toUpperCase() === form.targeting_partner.trim().toUpperCase()
  const envNote = (k, envKey, fallback) => (empty(k) ? (data[envKey] ? 'пусто — берётся из .env сервера' : fallback) : null)
  const tgtEmpty = (empty('targeting_partner') && !data.targeting_partner_env) || (empty('targeting_campaign') && !data.targeting_campaign_env)

  return (
    <div style={{ fontFamily: UI, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <style>{SCRIPT_CSS}</style>
      {!!err && (
        <div style={{ padding: '10px 14px', borderRadius: 12, background: 'var(--bad-tint)', border: '1px solid var(--bad-border)', color: 'var(--bad-fg)',
          fontSize: 12.5 }}>{err}</div>
      )}

      <AutoBar on={!!data.auto_external} busy={autoBusy} mayEdit={mayEdit} onToggle={toggleAuto} tone={tone} />

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 14, alignItems: 'start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ ...CARD, gap: 12 }}>
            <CardHead title="Что добавляется в креатив" cap="одно на все креативы" dirty={mayEdit && dirty('viewability', 'teaser_icon')}
              saving={saving} onSave={save} />
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 10px', borderRadius: 10, background: 'var(--bg-subtle)',
              fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <span style={{ flex: '0 0 6px', width: 6, height: 6, marginTop: 6, borderRadius: 2, background: 'var(--accent)' }} />
              <span>Вшивается внутрь <span style={{ fontFamily: MONO }}>&lt;head&gt;</span> самого креатива перед отправкой в DSP — не на сайт
                площадки. Какой из двух скриптов справа возьмётся, решает признак «наш код стоит» в карточке площадки.</span>
            </div>
            <ExtraField label="Скрипт видимости (viewability)" hint="адрес файла — тег соберём сами" value={form.viewability} onChange={set('viewability')}
              placeholder="https://…/viewability.js" okWord="задан" okNote="Требование DSP: добавляется в каждый креатив."
              emptyNote="Пока пусто — креативы уходят без него." readOnly={ro} />
            <ExtraField label="Иконка тизера 80×80" hint="картинка на CDN DSP" value={form.teaser_icon} onChange={set('teaser_icon')}
              placeholder="https://…/80x80.png" okWord="задана" okNote="Одна на все тизеры." emptyNote="Пока пусто — тизеры в DSP не отправляются."
              thumb readOnly={ro} />
          </div>

          <div style={{ ...CARD, gap: 10 }}>
            <CardHead title="Кабинеты и аккаунты" cap="наведите на ⓘ — пояснение" saving={saving} onSave={save} disabled={sameCab}
              dirty={mayEdit && dirty('prod_partner', 'targeting_partner', 'targeting_campaign', 'weborama_account')} />
            <IdRow label="Боевой клиент" value={form.prod_partner} onChange={set('prod_partner')} placeholder="хеш кабинета" readOnly={ro}
              short={envNote('prod_partner', 'prod_partner_env', 'не задан — выгрузка РК откажет') || 'выгрузка РК кнопкой «D»'}
              warn={empty('prod_partner') && !data.prod_partner_env}
              hint="По нему заводятся кампании и креативы кнопкой «D» на дашборде трафика. Пусто — берётся из настроек сервера (.env)." />
            <IdRow label="Демоклиент" value={form.targeting_partner} onChange={set('targeting_partner')} placeholder="хеш кабинета" readOnly={ro}
              short={envNote('targeting_partner', 'targeting_partner_env', 'не задан') || 'копия баннера для кнопки ◎'}
              warn={empty('targeting_partner') && !data.targeting_partner_env}
              hint="Кабинет, куда на отправке трафику заводится копия баннера для кнопки ◎ в очереди. Боевого креатива в DSP до согласования площадки ещё нет." />
            <IdRow label="Демокампания" value={form.targeting_campaign} onChange={set('targeting_campaign')} placeholder="хеш кампании" readOnly={ro}
              short={envNote('targeting_campaign', 'targeting_campaign_env', 'не задана') || 'должна быть запущена'}
              warn={empty('targeting_campaign') && !data.targeting_campaign_env}
              hint="Кампания внутри кабинета демоклиента. Должна быть ЗАПУЩЕНА — остановленная не покажет ничего." />
            <IdRow label="Аккаунт Weborama (WCM)" value={form.weborama_account} onChange={set('weborama_account')} placeholder="10419" readOnly={ro}
              inputMode="numeric" short={empty('weborama_account') ? 'не задан — «ПИКСЕЛЬ WR» откажет' : 'вставки и пиксели показа'}
              warn={empty('weborama_account')}
              hint="Номер аккаунта адресует весь обмен с верификатором: по нему заводятся вставки и забираются пиксели показа. Weborama выдаёт его списком — из кода он не выводится и умолчания не имеет. Пока пусто, кнопка «ПИКСЕЛЬ WR» честно откажет." />
            {sameCab && (
              <span style={{ fontSize: 12, color: 'var(--bad-fg)' }}>Боевой клиент и демоклиент совпадают — РК и нацеливание ушли бы в один кабинет.</span>
            )}
            {!tgtEmpty && <CampaignPlaque state={tgt.state} hash={form.targeting_campaign} />}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <ScriptGroup title="Наш код на сайте стоит" dot="var(--money)" sub="счётчик уже на сайте — вшиваем дополнительное"
            script={form.with_code} onScript={set('with_code')} items={data.with_code.publishers} suggested={data.suggested} readOnly={ro}
            dirty={dirty('with_code')} saving={saving} onSave={save} />
          <ScriptGroup title="Нашего кода на сайте нет" dot="var(--attn)" sub="данные собирает только креатив — вшиваем полный счётчик"
            script={form.without_code} onScript={set('without_code')} items={data.without_code.publishers} suggested={data.suggested} readOnly={ro}
            dirty={dirty('without_code')} saving={saving} onSave={save} />
        </div>
      </div>
    </div>
  )
}
