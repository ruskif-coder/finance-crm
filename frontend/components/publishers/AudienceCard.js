import { useState } from 'react'
import Link from 'next/link'
import { MONO, UI } from '@/components/salesTableKit'
import { shortNum, pct, fmtDateShort } from '@/lib/salesFormat'
import { gapBar, gapTone, surfacesOf, declVal } from '@/components/publishers/audienceKit'

// Карточка площадки по макету Claude Design (09.10.2026): сверху блок сравнения «заявлено ↔
// подтверждено» двумя полосами, под ним две колонки (заявлено / подтверждено + что продаём),
// ниже свёрнутая история замеров. Каждая цифра подписана источником и датой: без них она ничего
// не доказывает. Уники — верхняя оценка (сумма суточных), «охватом» не называются.

const mono = (extra) => ({ fontFamily: MONO, ...extra })
const capS = (color = 'var(--text-cap)') => mono({ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color })
const tiny = mono({ fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' })
const dash = 'var(--text-disabled)'
const srcOf = (m) => (m ? `${m.source} · ${fmtDateShort(m.measured_at)}` : null)

const Small = ({ k, v, n, fg }) => (
  <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
    <span style={tiny}>{k}</span>
    <span style={mono({ fontSize: 12, fontWeight: 700, color: fg })}>{v}</span>
    {!!n && <span style={{ fontSize: 9.5, color: 'var(--text-faint)' }}>{n}</span>}
  </span>
)

export default function AudienceCard({ p, metrics, canEdit, onAdd, onDelete, days = 30 }) {
  const [histOpen, setHistOpen] = useState(false)
  if (!p) return <div style={{ color: 'var(--text-muted)', fontSize: 12.5, padding: 20, textAlign: 'center' }}>Выберите площадку в таблице или на карте</div>
  const d = p.declared || {}, m = p.measured || {}
  const mau = d.mau?.value ?? null, dau = d.dau?.value ?? null, wau = d.wau?.value ?? null
  const u = m.uniques ?? null, g = p.gap_pct ?? null
  const gFg = gapTone(g)[1]
  const maxBar = Math.max(mau || 0, u || 0, 1)
  const webV = declVal(p, 'mau@web'), appV = declVal(p, 'mau@app')
  const hasPair = webV != null && appV != null
  const shares = Object.entries(d).filter(([k]) => k.startsWith('share:')).slice(0, 4)
  const hist = p.history || []
  const sy = p.system || {}
  const reqSum = ['tr:ad_requests_web', 'tr:ad_requests_app_android', 'tr:ad_requests_app_ios'].reduce((a, k) => a + (sy[k]?.value || 0), 0)
  const noShows = !m.shows
  const wrap = { display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }
  const box = (bg, extra) => ({ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 14px', background: bg, borderRadius: 12, ...extra })

  return (
    <div style={wrap}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Link href={`/publishers/${p.id}`} style={{ fontSize: 17, fontWeight: 800, letterSpacing: '-.02em', color: 'var(--text-primary)', textDecoration: 'none' }}>{p.name}</Link>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{[p.kind, surfacesOf(p)].filter(Boolean).join(' · ')}</span>
        {p.media_kit_stale && <span style={mono({ padding: '2px 8px', borderRadius: 7, background: 'var(--warning-tint)', color: 'var(--warning-fg)', fontSize: 9, fontWeight: 700, letterSpacing: '.04em' })}>медиакит старше 6 мес.</span>}
        {canEdit && <button type="button" onClick={onAdd} style={{ marginLeft: 'auto', height: 30, padding: '0 12px', background: 'var(--accent)', color: 'var(--on-accent)', border: 'none', borderRadius: 10, fontFamily: UI, fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+ Замер</button>}
      </div>

      {/* главное — сравнение: видно без таблицы */}
      <div style={box('var(--bg-tint)', { border: '1px solid var(--accent-border)', gap: 9 })}>
        <span style={capS('var(--accent-fg)')}>Заявлено ↔ подтверждено</span>
        {[
          { label: 'MAU заявлен', value: mau, bg: 'var(--accent-soft)', fg: mau ? 'var(--text-primary)' : dash },
          { label: 'Уники под рекламой', value: u, bg: gapBar(g), fg: u != null ? gFg : dash },
        ].map(c => (
          <span key={c.label} style={{ display: 'grid', gridTemplateColumns: '118px minmax(0, 1fr) 92px', gap: 10, alignItems: 'center' }}>
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>{c.label}</span>
            <span style={{ height: 12, background: 'var(--border-inner)', borderRadius: 4, overflow: 'hidden' }}>
              <span style={{ display: 'block', height: '100%', width: c.value ? `${(c.value / maxBar) * 100}%` : '0%', background: c.bg, borderRadius: 4 }} />
            </span>
            <span style={mono({ fontSize: 12.5, fontWeight: 700, color: c.fg, textAlign: 'right', whiteSpace: 'nowrap' })}>{shortNum(c.value)}</span>
          </span>
        ))}
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, paddingTop: 4, borderTop: '1px solid var(--accent-border)' }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>разрыв</span>
          <span style={mono({ fontSize: 15, fontWeight: 700, color: g == null ? dash : gFg })}>{g == null ? '—' : `${Math.round(g)} %`}</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-faint)' }}>
            {g == null ? (mau ? 'уники не измерены — DSP их не отдаёт' : 'нет заявленного MAU') : 'уники ÷ заявленный MAU · верхняя оценка'}
          </span>
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 12 }}>
        <div style={box('var(--bg-subtle)')}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={capS()}>Заявлено площадкой</span>
            <span style={mono({ marginLeft: 'auto', fontSize: 9, color: 'var(--text-faint)' })}>{srcOf(d.mau) || 'нет данных'}</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={mono({ fontSize: 24, fontWeight: 700, letterSpacing: '-.03em', lineHeight: 1 })}>{shortNum(mau)}</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>MAU</span>
          </span>
          <span style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
            <Small k="DAU" v={shortNum(dau)} />
            <Small k="WAU" v={shortNum(wau)} />
            <Small k="DAU/MAU" v={p.stickiness ?? '—'} />
            <Small k="визитов в мес" v={shortNum(p.visits)} n="заявлено площадкой" fg={p.visits ? undefined : dash} />
          </span>
          {hasPair && (
            <span style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 6, borderTop: '1px solid var(--border-card)' }}>
              <span style={mono({ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-faint)' })}><span>web {shortNum(webV)}</span><span>app {shortNum(appV)}</span></span>
              <span style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', gap: 2 }}>
                <span style={{ width: `${(webV / (webV + appV)) * 100}%`, background: 'var(--accent)' }} />
                <span style={{ flex: 1, background: 'var(--violet-fg)' }} />
              </span>
            </span>
          )}
          {!!shares.length && (
            <span style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingTop: 6, borderTop: '1px solid var(--border-card)' }}>
              {shares.map(([k, s]) => (
                <span key={k} style={{ display: 'grid', gridTemplateColumns: '76px minmax(0, 1fr) 40px', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontSize: 10.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.segment}</span>
                  <span style={{ height: 5, background: 'var(--border-card)', borderRadius: 3, overflow: 'hidden' }}>
                    <span style={{ display: 'block', height: '100%', width: `${Math.min(100, s.value)}%`, background: 'var(--accent-soft)', borderRadius: 3 }} />
                  </span>
                  <span style={mono({ fontSize: 10.5, fontWeight: 700, textAlign: 'right' })}>{pct(s.value)}</span>
                </span>
              ))}
            </span>
          )}
          {Object.entries(d).filter(([k]) => k.startsWith('affinity')).slice(0, 2).map(([k, a]) => (
            <span key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: 'var(--text-muted)' }}>
              <span>Affinity · {a.segment || '—'}</span><span style={mono({ fontWeight: 700, color: 'var(--text-primary)' })}>{a.value}</span>
            </span>
          ))}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ ...box('var(--income-bg)', { border: '1px solid var(--income-border)', flex: 1 }) }}>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={capS('var(--income-fg)')}>Подтверждено нами</span>
              <span style={mono({ marginLeft: 'auto', fontSize: 9, color: 'var(--text-faint)' })}>{days} дн. · наш счётчик{m.non_combat ? ' · есть не боевой факт' : ''}</span>
            </span>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={mono({ fontSize: 24, fontWeight: 700, letterSpacing: '-.03em', lineHeight: 1, color: u != null ? 'var(--income-fg)' : dash })}>{shortNum(u)}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>уников · верхняя оценка</span>
            </span>
            <span style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
              <Small k="показы" v={noShows ? '—' : shortNum(m.shows)} n={noShows ? 'нет РК за окно' : `${m.campaigns} РК · ${m.days} дн.`} fg={noShows ? dash : undefined} />
              <Small k="верификатор" v={m.verifier_shows != null ? shortNum(m.verifier_shows) : '—'} n="Weborama, отдельно" fg="var(--text-secondary)" />
              <Small k="CTR" v={noShows ? '—' : pct(m.ctr_pct)} n={noShows ? '' : `${m.clicks} кликов`} fg="var(--text-secondary)" />
              <Small k="fill DSP" v={m.fill_pct != null ? pct(m.fill_pct) : '—'} n={m.fill_pct != null ? 'показы / предложено' : 'нет данных'} fg={m.fill_pct != null ? 'var(--text-secondary)' : dash} />
            </span>
          </div>
          <div style={box('var(--bg-subtle)', { gap: 6, padding: '10px 14px' })}>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={capS()}>Что продаём</span>
              <span style={mono({ marginLeft: 'auto', fontSize: 9, color: 'var(--text-faint)' })}>внутреннее</span>
            </span>
            <span style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
              <Small k="покрытие web" v={p.coverage?.web != null ? `${p.coverage.web} %` : '—'} fg={p.coverage?.web != null ? undefined : dash} />
              <Small k="покрытие app" v={p.coverage?.app != null ? `${p.coverage.app} %` : '—'} fg={p.coverage?.app != null ? undefined : dash} />
              <Small k="сделка" v={p.deal_type || '—'} />
              <Small k="медиакит" v={p.media_kit_at ? fmtDateShort(p.media_kit_at) : '—'} fg={p.media_kit_stale ? 'var(--warning-fg)' : p.media_kit_at ? undefined : dash} />
            </span>
          </div>
        </div>
      </div>

      {/* поля, что в системе уже есть (карточка площадки, балансировщик): читаем, не дублируем */}
      <div style={box('var(--bg-subtle)', { gap: 6, padding: '10px 14px' })}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={capS()}>Трафик и ёмкость</span>
          <span style={mono({ marginLeft: 'auto', fontSize: 9, color: 'var(--text-faint)' })}>из карточки площадки</span>
        </span>
        <span style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
          <Small k="визиты WEB" v={shortNum(sy['tr:web']?.value)} n={sy['tr:web_depth'] ? `глубина ${sy['tr:web_depth'].value}` : 'заявлено площадкой'} fg={sy['tr:web'] ? undefined : dash} />
          <Small k="визиты Android" v={shortNum(sy['tr:app_android']?.value)} fg={sy['tr:app_android'] ? undefined : dash} />
          <Small k="визиты iOS" v={shortNum(sy['tr:app_ios']?.value)} fg={sy['tr:app_ios'] ? undefined : dash} />
          <Small k="SimilarWeb visits" v={shortNum(sy['tr:sw_visits']?.value)} n={p.visits_vs_sw != null ? `заявлено ÷ SW = ${String(p.visits_vs_sw).replace('.', ',')}` : (sy['tr:sw_br'] ? `отказы ${sy['tr:sw_br'].value} %` : null)} fg={sy['tr:sw_visits'] ? undefined : dash} />
          <Small k="запросы кода" v={shortNum(reqSum || null)} n="в месяц" fg={reqSum ? undefined : dash} />
          <Small k="загрузка запросов" v={p.load_pct != null ? pct(p.load_pct) : '—'} n={p.load_pct != null ? 'показы ÷ запросы, оценка' : 'нет запросов или показов'} fg={p.load_pct != null ? undefined : dash} />
        </span>
      </div>

      <span onClick={() => setHistOpen(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', border: '1px solid var(--border-card)', borderRadius: 10, cursor: 'pointer' }}>
        <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{histOpen ? '▾' : '▸'}</span>
        <span style={capS()}>История замеров</span>
        <span style={mono({ marginLeft: 'auto', fontSize: 10, color: 'var(--text-faint)' })}>{hist.length ? `${hist.length} замеров` : 'замеров нет'}</span>
      </span>
      {histOpen && !!hist.length && (
        <div style={{ maxHeight: 150, overflowY: 'auto', display: 'flex', flexDirection: 'column', border: '1px solid var(--border-inner)', borderRadius: 10 }}>
          {hist.map(h => (
            <span key={h.id} style={{ display: 'grid', gridTemplateColumns: '72px 120px minmax(0, 1fr) 100px 24px', gap: 10, alignItems: 'center', padding: '6px 10px', borderBottom: '1px solid var(--border-row)', fontSize: 11.5 }}>
              <span style={mono({ color: 'var(--text-muted)' })}>{fmtDateShort(h.measured_at)}</span>
              <span style={{ fontWeight: 600 }}>{metrics?.[h.metric]?.label || h.metric}{h.segment ? ` · ${h.segment}` : ''}{h.surface_kind ? ` · ${h.surface_kind}` : ''}</span>
              <span style={mono({ fontWeight: 700 })}>{h.metric === 'share' ? pct(h.value) : shortNum(h.value)}</span>
              <span style={{ color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={h.note || ''}>{h.source}</span>
              {canEdit
                ? <span title="Удалить замер" onClick={() => onDelete(h)} style={{ color: 'var(--text-disabled)', cursor: 'pointer', textAlign: 'center' }}>✕</span>
                : <span />}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
