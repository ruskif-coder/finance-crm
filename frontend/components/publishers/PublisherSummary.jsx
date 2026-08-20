import { CAP, docCard } from '@/components/salesTableKit'
import { MONO, UI, INTEG_TONE, TRAFFIC_ROWS, Pin, ChatBtn, ServiceChip, tgHref, fmtMoney as num }
  from '@/components/publishers/kit'

/**
 * Сводка строки реестра (уровень L2 из хендоффа «Справочник паблишеров»).
 *
 * Четыре колонки в фиксированном порядке: поверхности с услугами · трафик с
 * материалами · контакты и заметки · договоры и юрлица. Порядок не случайный: слева
 * то, что продаём, справа то, чем это оформлено.
 *
 * Правка здесь только точечная — статус поверхности кликом по пину, замер трафика,
 * заметки. Всё остальное правится в карточке: два места полноценной правки разошлись бы.
 */

// Отметки площадки. Выключенные не прячем — в сводке важно видеть и «нет»,
// иначе непонятно, спрашивали ли вообще.
const FLAGS = [
  ['our_code', 'Код наш', 'var(--accent)', 'var(--accent-tint)', 'var(--accent-border)'],
  ['is_exclusive', 'Эксклюзив', 'var(--accent)', 'var(--accent-tint)', 'var(--accent-border)'],
  ['has_dsp', 'DSP', 'var(--income)', 'var(--income-tint)', '#CDE9DE'],
  ['self_promo_on', 'Самореклама', 'var(--warning-text)', 'var(--warning-tint)', '#F2DFC0'],
]

const cap = { ...CAP, marginBottom: 8 }
const inpSm = { padding: '4px 7px', border: '1px solid var(--border-card)', borderRadius: 8,
  fontSize: 12.5, fontFamily: MONO, background: 'var(--bg-card)', color: 'var(--text-primary)',
  outline: 'none', width: '100%', boxSizing: 'border-box', textAlign: 'right' }
const area = { padding: '8px 10px', border: '1px solid var(--border-card)', borderRadius: 10,
  fontSize: 13, fontFamily: UI, background: 'var(--bg-card)', color: 'var(--text-primary)',
  width: '100%', boxSizing: 'border-box', resize: 'vertical', minHeight: 54, lineHeight: 1.4 }
const iconBtn = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 30, height: 30, borderRadius: 9, border: '1px solid var(--border-card)',
  background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer' }

// Строка поверхности: WEB / APP / APP · AND / APP · IOS.
const SurfaceLine = ({ label, s, servicesCount, canEdit, onCycle, working }) => {
  if (!s) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0' }}>
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, width: 84,
        color: 'var(--text-faint)' }}>{label}</span>
      <Pin dot text="нет" tone={INTEG_TONE['НЕТ']} />
      <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>нет у площадки</span>
    </div>
  )
  const tone = INTEG_TONE[s.integration_status] || INTEG_TONE['НЕТ']
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0' }}>
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, width: 84,
        color: working ? 'var(--text-primary)' : 'var(--text-faint)' }}>{label}</span>
      <Pin dot text={s.integration_status} tone={tone} dim={!working}
        title={canEdit && onCycle ? 'Нажмите, чтобы сменить статус' : s.integration_status}
        onClick={canEdit && onCycle ? onCycle : undefined} />
      <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
        {!working ? 'не работаем' : [
          s.coverage_percent != null ? `покрытие ${s.coverage_percent} %` : null,
          servicesCount != null ? `услуг ${servicesCount}` : null,
        ].filter(Boolean).join(' · ')}
      </span>
      {s.figma_url && (
        <a href={s.figma_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
          style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--accent)' }}>фигма</a>
      )}
    </div>
  )
}

export default function PublisherSummary({ data, meta, canEdit, api }) {
  const services = meta.services || []
  const svcRows = data.services || []
  const svcOn = (id, kind) => svcRows.some(x => x.service_id === id && x.surface_kind === kind)
  const working = (kind) => !!data.surfaces?.[kind]?.we_work
  const svcWorking = new Set(svcRows.filter(x => working(x.surface_kind)).map(x => x.service_id)).size
  const app = data.surfaces?.app
  const flagOn = (key) => (key === 'self_promo_on' ? data.self_promo === 'ДА' : !!data[key])

  return (
    <div onClick={e => e.stopPropagation()}
      style={{ padding: '10px 18px 14px', fontFamily: UI }}>

      {/* Отметки площадки — одной полосой, как в макете. */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', paddingBottom: 12, marginBottom: 14,
        borderBottom: '1px solid var(--border-card)' }}>
        {FLAGS.map(([key, label, fg, bg, bd]) => {
          const on = flagOn(key)
          return (
            <span key={key} title={`${label} — ${on ? 'да' : 'нет'}`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '5px 11px',
                borderRadius: 9, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap',
                background: on ? bg : 'var(--bg-card)', color: on ? fg : 'var(--text-faint)',
                border: `1px solid ${on ? bd : 'var(--border-card)'}` }}>
              <span style={{ width: 7, height: 7, borderRadius: 2,
                background: on ? fg : 'var(--border-card)' }} />{label}
            </span>
          )
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 22 }}>

        {/* 1. Поверхности и услуги */}
        <div>
          <div style={cap}>поверхности и услуги</div>
          <SurfaceLine label="WEB" s={data.surfaces?.web} working={working('web')}
            servicesCount={svcRows.filter(x => x.surface_kind === 'web').length}
            canEdit={canEdit} onCycle={() => api.cycleSurface('web', data.surfaces.web)} />
          <SurfaceLine label="APP" s={app} working={working('app')}
            servicesCount={svcRows.filter(x => x.surface_kind === 'app').length}
            canEdit={canEdit} onCycle={() => api.cycleSurface('app', app)} />
          {/* Платформы приложения — своими строками: подключаются они врозь. */}
          {app && ['android', 'ios'].map(pk => {
            const pl = app.platforms?.[pk]
            return (
              <SurfaceLine key={pk} label={`APP · ${pk === 'android' ? 'AND' : 'IOS'}`} s={pl}
                working={!!pl?.is_active} servicesCount={null} canEdit={canEdit}
                onCycle={() => api.cyclePlatform(pk, pl)} />
            )
          })}

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, margin: '14px 0 8px' }}>
            <span style={{ ...CAP, marginBottom: 0 }}>подключенные услуги</span>
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12, fontWeight: 700,
              color: 'var(--accent)' }}>{svcWorking}\{services.length}</span>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {services.map(svc => {
              const parts = ['web', 'app'].filter(k => svcOn(svc.id, k))
                .map(k => ({ label: k.toUpperCase(), working: working(k) }))
              if (!parts.length) return null
              return <ServiceChip key={svc.id} name={svc.name} parts={parts}
                isTarget={svc.name === 'Альфарм-Таргет'} sharesData={data.shares_data} />
            })}
            {!svcRows.length && <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>услуги не отмечены</span>}
          </div>
        </div>

        {/* 2. Трафик и материалы */}
        <div>
          <div style={cap}>трафик за месяц</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 92px 58px', gap: 8, alignItems: 'center' }}>
            <span style={{ ...CAP, marginBottom: 0 }}>показатель</span>
            <span style={{ ...CAP, marginBottom: 0, textAlign: 'right' }}>за месяц</span>
            <span style={{ ...CAP, marginBottom: 0, textAlign: 'right' }}>глубина</span>
            {TRAFFIC_ROWS.map(([scope, label, hasDepth]) => {
              const t = data.traffic?.[scope]
              return (
                <TrafficRow key={scope} scope={scope} label={label} hasDepth={hasDepth}
                  value={t?.value} depth={t?.depth} canEdit={canEdit} onSave={api.saveTraffic} />
              )
            })}
          </div>

          <div style={{ ...cap, marginTop: 16 }}>материалы</div>
          {(data.documents || []).map(d => (
            <div key={d.id} style={{ ...docCard, marginBottom: 6 }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)"
                strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" />
              </svg>
              <span style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename}</div>
                <div style={{ ...CAP, marginBottom: 0 }}>{d.doc_type}</div>
              </span>
              <button onClick={() => api.downloadDocument(d.id, d.filename)}
                style={{ border: 'none', background: 'none', color: 'var(--accent)', fontSize: 12,
                  fontWeight: 600, cursor: 'pointer' }}>скачать</button>
            </div>
          ))}
          {!(data.documents || []).length && (
            <div style={{ ...docCard, justifyContent: 'center', color: 'var(--text-faint)', fontSize: 12.5 }}>
              документов нет
            </div>
          )}

          <div style={{ ...cap, marginTop: 14 }}>техрегламент · критерии к креативам</div>
          <textarea style={area} defaultValue={data.tech_requirements || ''} disabled={!canEdit}
            placeholder="форматы, вес, сроки подачи, запреты"
            onBlur={e => api.patchField('tech_requirements', e.target.value)} />
        </div>

        {/* 3. Контакты и заметки */}
        <div>
          <div style={cap}>контакты и заметки</div>
          {(data.contacts || []).map(c => (
            <div key={c.id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start',
              padding: '6px 0', borderBottom: '1px solid var(--border-inner)' }}>
              <span style={{ minWidth: 0, flex: '1 1 45%' }}>
                <div style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name || 'без имени'}</div>
                <div style={{ ...CAP, marginBottom: 0 }}>{c.role || 'должность не указана'}</div>
              </span>
              <span style={{ minWidth: 0, flex: '1 1 55%', textAlign: 'right' }}>
                <div style={{ fontFamily: MONO, fontSize: 11,
                  color: c.phone ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                  {c.phone || 'телефон не указан'}
                </div>
                <div style={{ fontFamily: MONO, fontSize: 11, overflow: 'hidden',
                  textOverflow: 'ellipsis', color: c.email ? 'var(--text-muted)' : 'var(--text-faint)' }}>
                  {c.email || 'email не указан'}
                </div>
              </span>
              <span style={{ display: 'inline-flex', gap: 4 }}>
                <ChatBtn kind="tg" title="Телеграм" href={tgHref(c.telegram)} size={24} />
                <ChatBtn kind="max" title="MAX" href={c.max_url} size={24} />
              </span>
            </div>
          ))}
          {!(data.contacts || []).length && (
            <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>контактов нет</div>
          )}

          <div style={{ ...cap, marginTop: 14 }}>корзина и избранное</div>
          <textarea style={area} defaultValue={data.basket_note || ''} disabled={!canEdit}
            placeholder="есть ли отложенный товар и какие коммуникации возможны"
            onBlur={e => api.patchField('basket_note', e.target.value)} />

          <div style={{ ...cap, marginTop: 14 }}>заметки</div>
          <textarea style={area} defaultValue={data.note || ''} disabled={!canEdit}
            placeholder="что важно помнить по площадке"
            onBlur={e => api.patchField('note', e.target.value)} />
        </div>

        {/* 4. Договоры и юрлица */}
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', marginBottom: 8 }}>
            <span style={{ ...CAP, marginBottom: 0 }}>договоры и юрлица</span>
          </div>
          {(data.contracts || []).map(c => (
            <div key={c.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 8 }}>
              <span style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, fontFamily: MONO }}>
                  {c.number}
                  {!c.linked && <span title="Договора нет в реестре — записан номером"> ⚠</span>}
                  <span style={{ fontFamily: UI, fontWeight: 600, fontSize: 12,
                    color: 'var(--text-muted)' }}> {c.role}</span>
                </div>
                <div style={{ fontSize: 12.5, color: c.counterparty ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
                  {c.counterparty || 'юрлицо не сопоставлено'}
                </div>
              </span>
              {c.document_source === 'edo' && c.document_url && (
                <a href={c.document_url} target="_blank" rel="noreferrer" style={iconBtn} title="Открыть в ЭДО">↗</a>
              )}
              {c.document_source === 'file' && (
                <button style={iconBtn} title="Скачать документ"
                  onClick={() => api.downloadContractDoc(c.id)}>⤓</button>
              )}
              {!c.document_source && canEdit && (
                <label style={{ ...iconBtn, color: 'var(--accent)' }} title="Приложить документ договора">+
                  <input type="file" style={{ display: 'none' }}
                    onChange={e => e.target.files?.[0] && api.uploadContractDoc(c.id, e.target.files[0])} />
                </label>
              )}
            </div>
          ))}
          {!(data.contracts || []).length && (
            <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>договоры не привязаны</div>
          )}
          {!(data.counterparties || []).length && (
            <div style={{ fontSize: 12.5, color: 'var(--text-faint)', marginTop: 6 }}>юрлицо не сопоставлено</div>
          )}
          {!!data.intermediary_name && (
            <div style={{ fontSize: 12.5, marginTop: 8 }}>
              <span style={{ ...CAP, marginBottom: 0 }}>посредник </span>{data.intermediary_name}
            </div>
          )}

          <div style={{ ...cap, marginTop: 14 }}>самореклама — что размещают</div>
          <textarea style={area} defaultValue={data.self_promo_note || ''} disabled={!canEdit}
            placeholder="что именно площадка размещает у себя"
            onBlur={e => api.patchField('self_promo_note', e.target.value)} />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14 }}>
        {!!(data.documents || []).length && (
          <button style={iconBtn} title="Скачать первый документ"
            onClick={() => api.downloadDocument(data.documents[0].id, data.documents[0].filename)}>⤓</button>
        )}
        {canEdit && (
          <button style={iconBtn} title="Править в карточке" onClick={api.openEdit}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
            </svg>
          </button>
        )}
        <button style={{ ...iconBtn, background: 'var(--accent)', borderColor: 'var(--accent)', color: '#fff' }}
          title="Открыть карточку" onClick={api.openCard}>→</button>
      </div>
    </div>
  )
}

// Замер правится на месте: значение и глубина сохраняются по уходу фокуса.
function TrafficRow({ scope, label, hasDepth, value, depth, canEdit, onSave }) {
  return (
    <>
      <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{label}</span>
      {canEdit
        ? <input style={inpSm} defaultValue={value ?? ''}
            onBlur={e => onSave(scope, e.target.value, depth)} />
        : <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right',
            color: value ? 'var(--accent)' : 'var(--text-faint)' }}>{num(value)}</span>}
      {hasDepth
        ? (canEdit
            ? <input style={inpSm} defaultValue={depth ?? ''}
                onBlur={e => onSave(scope, value, e.target.value)} />
            : <span style={{ fontFamily: MONO, fontSize: 12.5, textAlign: 'right',
                color: 'var(--text-secondary)' }}>
                {depth != null ? String(depth).replace('.', ',') : '—'}</span>)
        : <span style={{ textAlign: 'right', color: 'var(--text-faint)' }}>—</span>}
    </>
  )
}
