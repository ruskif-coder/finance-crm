import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { CARD, monoLbl, Marker } from './kit'
import CardShell from './CardShell'
import AssemblyCreatives from '../creatives/AssemblyCreatives'

// Мобильная карточка сделки /sales/deals/[id]. Контракт как у всех мобильных
// компонентов проекта: страница считает (деньги/цепочка стадий/медиаплан),
// компонент только рисует. См. десктопную pages/sales/deals/[id].js — источник данных.

const rub = (v) => (v == null ? '—' : v.toLocaleString('ru-RU') + ' ₽')
const num = (v) => (v == null ? '—' : v.toLocaleString('ru-RU'))

const LAYER_COLOR = {
  'планируемые': 'var(--text-faint, #A3ABBD)',
  'реализуемые': 'var(--dot-current-dz, #d97706)',
  'фактические': 'var(--income, #1F7D5E)',
}

function Chip({ label, bg, fg }) {
  return <span style={{ display: 'inline-flex', alignItems: 'center', padding: '4px 10px', borderRadius: 8, fontSize: 12, fontWeight: 600, background: bg, color: fg, whiteSpace: 'nowrap', flexShrink: 0 }}>{label}</span>
}

function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, padding: '9px 0', borderTop: '1px solid var(--border-inner)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', flexShrink: 0, paddingTop: 1 }}>{label}</span>
      <span style={{ fontSize: 12.5, fontWeight: 600, color: value ? 'var(--text-primary)' : 'var(--text-faint)', textAlign: 'right', wordBreak: 'break-word' }}>{value || '—'}</span>
    </div>
  )
}

export default function DealCardMobile({
  deal, chain, curIdx, isLost, net, gross, vat, lines, tVol, tNet, mpExtras, extrasTotal, mp, hasMp, canEdit, canApprove, onBack, onMove,
}) {
  const d = deal
  const title = [d.advertiser, d.brand].filter(Boolean).join(' · ') || d.title || '—'
  const stageLabel = isLost ? (d.our_stage?.name || 'Сделка провалена') : (chain[curIdx]?.name || d.bitrix_stage || '—')
  const stageColor = isLost ? 'var(--danger)' : (LAYER_COLOR[chain[curIdx]?.money_layer] || 'var(--text-faint)')

  const badges = (
    <>
      <Chip label={stageLabel} bg={isLost ? 'var(--danger-tint)' : 'var(--bg-subtle)'} fg={stageColor} />
      {!isLost && chain[curIdx]?.money_layer && <Chip label={chain[curIdx].money_layer} bg="var(--accent-tint)" fg="var(--accent)" />}
    </>
  )

  const [tab, setTab] = useState('summary')
  const TABS = [
    { key: 'summary', label: 'Сводка' },
    { key: 'services', label: 'Услуги' },
    { key: 'mp', label: 'Медиапланы' },
    { key: 'creatives', label: 'Креативы' },
  ]

  return (
    <CardShell
      title={<span style={{ fontSize: 16, fontWeight: 700 }}><span style={{ fontFamily: MONO, color: 'var(--accent)', marginRight: 8 }}>{d.code || d.bitrix_id || d.id}</span>{title}</span>}
      subtitle={d.payer || '—'}
      badges={badges}
      tabs={TABS}
      tab={tab}
      setTab={setTab}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={onBack} style={{ height: 34, padding: '0 12px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', fontFamily: UI }}>‹ Назад</button>
          {canEdit && (
            <button onClick={onMove} style={{ height: 34, padding: '0 12px', borderRadius: 10, border: 'none', background: 'var(--income, #1F7D5E)', color: '#fff', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>Изменить стадию</button>
          )}
        </div>

        {tab === 'summary' && (
          <>
            <div style={{ ...CARD, padding: '14px 16px' }}>
              <div style={monoLbl}>Сумма сделки · с НДС</div>
              <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, letterSpacing: '-.02em', color: 'var(--text-primary)', margin: '4px 0 10px' }}>{rub(gross)}</div>
              <Row label="До НДС" value={rub(net)} />
              <Row label={vat != null ? `НДС ${Math.round(vat * 100)} %` : 'НДС — ставка не задана'} value={gross != null && net != null ? rub(Math.round(gross - net)) : null} />
            </div>
            <div style={{ ...CARD, padding: '14px 16px' }}>
              <div style={{ ...monoLbl, marginBottom: 10 }}>Параметры</div>
              <Row label="Агентство" value={d.agency} />
              <Row label="Рекламодатель" value={d.advertiser} />
              <Row label="Бренд" value={d.brand} />
              <Row label="Контрагент" value={d.payer} />
              <Row label="Период размещения" value={d.period ? `месяц · ${d.period}` : null} />
              <Row label="Продавец" value={d.sales_rep} />
              <Row label="Аккаунт" value={d.account_manager} />
            </div>
            {!isLost && chain.length > 0 && (
              <div style={{ ...CARD, padding: '14px 16px' }}>
                <div style={{ ...monoLbl, marginBottom: 10 }}>Цепочка стадий</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {chain.map((s, i) => {
                    const cur = i === curIdx
                    const past = curIdx >= 0 && i < curIdx
                    return (
                      <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: (cur || past) ? 1 : 0.5 }}>
                        <Marker c={LAYER_COLOR[s.money_layer] || 'var(--border-inner)'} />
                        <span style={{ fontSize: 12.5, fontWeight: cur ? 700 : 500, color: 'var(--text-primary)' }}>{s.name}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
        )}

        {/* Блок креативов переиспользуется десктопный, а не пишется вторым.
            Он собран из плашек и полей во всю ширину — на узком экране раскладка та же,
            а две реализации одного согласования разъехались бы на первой же правке. */}
        {tab === 'creatives' && (
          <div style={{ ...CARD, padding: '14px 16px' }}>
            <AssemblyCreatives dealId={d.id} canEdit={canEdit} canApprove={canApprove} />
          </div>
        )}

        {tab === 'services' && (
          <>
            {!hasMp ? (
              <div style={{ ...CARD, padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Строк размещения нет</div>
            ) : (
              <>
                {lines.map((l, i) => (
                  <div key={i} style={{ ...CARD, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)' }}>{l.position}</span>
                      <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, color: 'var(--accent)' }}>{l.model}</span>
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{l.format}</span>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>
                      <span>{num(l.volume)}</span>
                      <span>{rub(l.net)}</span>
                      <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{rub(l.gross)}</span>
                    </div>
                  </div>
                ))}
                <div style={{ ...CARD, padding: '12px 14px', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={monoLbl}>Итого</span>
                  <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--accent)' }}>{rub(vat != null ? Math.round(tNet * (1 + vat)) : null)}</span>
                </div>
              </>
            )}
            {mpExtras.length > 0 && (
              <div style={{ ...CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={monoLbl}>Дополнительные услуги</div>
                {mpExtras.map((e, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{e.name || '—'}</span>
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--income)' }}>{rub(e.total || 0)}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 6 }}>
                  <span style={monoLbl}>Итого доп. услуги</span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--income)' }}>{rub(extrasTotal)}</span>
                </div>
              </div>
            )}
          </>
        )}

        {tab === 'mp' && (
          <>
            {!mp ? (
              <div style={{ ...CARD, padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Медиаплана нет</div>
            ) : (
              <div style={{ ...CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13.5, fontWeight: 700 }}>{mp.title || 'медиаплан'}</span>
                  <a href={`/accounts/mp/${mp.id}`} style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none' }}>Открыть →</a>
                </div>
                <Row label="Версия" value={`v${mp.version}`} />
                {mp.geo && <Row label="Гео" value={mp.geo} />}
                {mp.period && <Row label="Период" value={mp.period} />}
              </div>
            )}
          </>
        )}
      </div>
    </CardShell>
  )
}
