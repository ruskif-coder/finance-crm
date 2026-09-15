/**
 * Настройки → Статус.
 *
 * Заведено 07.09.2026 после случая, когда база DSP лежала три часа и об этом никто не
 * узнал. Спека — `docs/SPEC_экран_состояния_системы.md`, дизайн — хендофф
 * `docs/статус.zip` (`design_handoff_system_health`).
 *
 * Готового компонента в хендоффе НЕ БЫЛО (только дизайн-система и html-референс), поэтому
 * вёрстка своя — но на наших примитивах и токенах. Палитра хендоффа совпадает с нашей по
 * значениям, отличаются только имена переменных: `--card` → `--bg-card`, `--t1` →
 * `--text-primary` и так далее. Второй набор токенов не заводился.
 *
 * ЧЕТЫРЕ ТОНА, А НЕ ТРИ. `idle` — «данных нет, и это норма»: cron стоит только на сервере,
 * синк с Битриксом запускается руками. В счёт отказов такие строки не идут.
 *
 * Тон плитки и тон экрана ВЫЧИСЛЯЮТСЯ из строк, руками не задаются: хранимая копия
 * состояния разъехалась бы с проверками.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import SettingsTabs from '@/components/SettingsTabs'
import api, { auth } from '@/lib/api'
import { card, MONO, UI, btnSm } from '@/components/salesTableKit'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { fmtTime } from '@/lib/dates'

const CARD = { ...card, padding: '16px 18px' }
const CAPS = { fontFamily: MONO, fontSize: 10, letterSpacing: '.1em',
               textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-muted)' }

/** Тон → цвет, фон, подпись. `idle` серый: это не поломка, а отсутствие данных. */
const TONE = {
  ok:   { fg: 'var(--income)',       bg: 'var(--income-tint)',  bd: 'var(--income-border)',  label: 'всё в норме' },
  warn: { fg: 'var(--warning-text)', bg: 'var(--warning-tint)', bd: 'var(--warning-border)', label: 'внимание' },
  bad:  { fg: 'var(--danger)',       bg: 'var(--danger-tint)',  bd: 'var(--danger-border)',  label: 'отказ' },
  idle: { fg: 'var(--text-faint)',   bg: 'var(--bg-subtle)',    bd: 'var(--border-card)',    label: 'нет данных' },
}
const t = (k) => TONE[k] || TONE.idle

/** Квадратный маркер — все маркеры экрана квадратные (правило хендоффа). */
function Mark({ tone, size = 6 }) {
  return <span style={{ width: size, height: size, borderRadius: 2, flexShrink: 0,
                        background: t(tone).fg, display: 'inline-block' }} />
}

/** Итог плитки считается ИЗ СТРОК: «всё ок · 4», «2 из 5 не настроено», «нет данных». */
function tileSummary(items) {
  const bad = items.filter(i => i.tone === 'bad').length
  const warn = items.filter(i => i.tone === 'warn').length
  const idle = items.filter(i => i.tone === 'idle').length
  if (bad) return { tone: 'bad', text: `${bad} из ${items.length} отказ` }
  if (warn) return { tone: 'warn', text: `${warn} из ${items.length} не настроено` }
  if (idle && idle === items.length) return { tone: 'idle', text: 'нет данных · норма стенда' }
  if (idle) return { tone: 'idle', text: `${items.length - idle} ок · ${idle} без данных` }
  return { tone: 'ok', text: `всё ок · ${items.length}` }
}

function CheckRow({ c }) {
  const muted = c.tone === 'idle'
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '12px minmax(0,1fr) auto', gap: 9,
                  alignItems: 'baseline', padding: '8px 0',
                  borderBottom: '1px solid var(--border-row)' }}>
      <Mark tone={c.tone} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600,
                      color: muted ? 'var(--text-muted)' : 'var(--text-primary)' }}>{c.title}</div>
        {!!c.note && (
          <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)',
                        marginTop: 3, lineHeight: 1.5 }}>{c.note}</div>
        )}
      </div>
      <div style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap',
                    color: muted ? 'var(--text-faint)' : t(c.tone).fg }}>{c.value || '—'}</div>
    </div>
  )
}

function Tile({ title, items, children }) {
  const s = tileSummary(items || [])
  return (
    <div style={{ ...CARD, borderColor: s.tone === 'bad' ? 'var(--danger-border)'
                    : s.tone === 'warn' ? 'var(--warning-border)' : 'var(--border-card)',
                  display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: t(s.tone).fg }} />
        <span style={CAPS}>{title}</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10,
                       color: t(s.tone).fg }}>{s.text}</span>
      </div>
      {children}
      {(items || []).map(c => <CheckRow key={c.key} c={c} />)}
    </div>
  )
}

/** Спарклайн: 24 часа, нулевые серые, у каждого столбика подсказка со значением.
 *  Столбики, а не линия: значения дискретны по часам, линия обещала бы плавность. */
function Spark({ series, field, tone }) {
  const top = Math.max(1, ...series.map(x => x[field]))
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 52 }}>
        {series.map(x => (
          <div key={x.hour} title={`${fmtTime(x.hour, '')} · ${x[field]}`}
               style={{ flex: 1, display: 'flex', flexDirection: 'column',
                        justifyContent: 'flex-end', height: '100%' }}>
            <div style={{ height: Math.max(2, Math.round(x[field] / top * 48)), borderRadius: 2,
                          background: x[field] ? tone : 'var(--border-inner)' }} />
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5,
                    fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>
        <span>{fmtTime(series[0].hour, '')} вчера</span><span>сейчас</span>
      </div>
    </div>
  )
}

/** Полоса занятости диска: цвет по порогам 80 / 90 % занятости. */
function DiskBar({ disk }) {
  const c = disk.used_pct > 90 ? 'var(--danger)'
    : disk.used_pct > 80 ? 'var(--warning)' : 'var(--income)'
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ height: 8, borderRadius: 4, background: 'var(--border-inner)',
                    overflow: 'hidden' }}>
        <div style={{ width: `${disk.used_pct}%`, height: '100%', background: c }} />
      </div>
      <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', marginTop: 5 }}>
        занято {disk.used_gb} из {disk.total_gb} ГБ · порог: жёлтый 20 %, красный 10 % свободного
      </div>
    </div>
  )
}

/* Шесть предложений — статический текст экрана, а не данные с сервера: это не состояние,
   а список того, чего на экране НЕТ. Каждое считается из уже имеющегося в базе. */
const SUGGESTIONS = [
  ['Расхождение с Битриксом', 'var(--danger)',
   'Сколько сделок и сумм разошлось с внешним источником на момент последней синки. Автосинки нет, и узнать это можно только вручную — а цифра нужна каждый день.',
   'сделки · журнал синхронизаций'],
  ['Целостность связок', 'var(--warning)',
   'Контрагенты без юрлица, договоры без контрагента, стадии без слоя денег. Тот же отчёт «требует разбора», сведённый в одно число.',
   'справочники · stage_catalog'],
  ['Очередь уведомлений', 'var(--accent)',
   'Сколько уведомлений ждёт отправки и сколько провалилось. Пока задание не запускалось, очередь копится молча.',
   'notifications'],
  ['Свежесть статистики площадок', 'var(--violet-fg)',
   'Дата последнего замера по каждой поверхности. Дашборд трафика считает недокрут от факта — если факт вчерашний, все цифры врут.',
   'publisher_traffic'],
  ['Медленные запросы', 'var(--warning)',
   'Топ-5 самых долгих запросов за сутки с длительностью. Ответ базы 20 мс — средний, а на реестрах бывает 4 секунды.',
   'pg_stat_statements'],
  ['Последний успешный бэкап', 'var(--income)',
   'Не факт наличия каталога, а дата и размер последнего дампа плюс результат тестового восстановления. Бэкап без проверки восстановления — не бэкап.',
   'каталог бэкапов · шаг 2'],
]

export default function SystemStatus() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [auto, setAuto] = useState(true)
  const autoRef = useRef(auto)
  autoRef.current = auto

  /** `live` — запросы к внешним сервисам. Делает их только РУЧНОЕ «Проверить»:
   *  человек, нажавший кнопку, хочет настоящий ответ, а фон каждые 30 секунд дёргать
   *  чужие API не должен — это способ получить бан по частоте. */
  const load = useCallback(async (live = false) => {
    setBusy(true); setErr('')
    try {
      const { data } = await api.get(`/system/status${live ? '?live=1' : ''}`, auth())
      setD(data)
    } catch (e) {
      setErr(e?.response?.status === 403
        ? 'Экран доступен только администратору.'
        : 'Не удалось получить состояние.')
    }
    setBusy(false)
  }, [])

  useRefreshOnReturn(() => load())
  useEffect(() => { load() }, [load])

  // Интервал живёт всё время, а перерисовывает только при включённом тумблере: снимать и
  // ставить его на каждый щелчок значило бы плодить таймеры, переживающие страницу.
  useEffect(() => {
    const id = setInterval(() => { if (autoRef.current) load() }, 30000)
    return () => clearInterval(id)
  }, [load])

  const by = (g) => (d?.checks || []).filter(c => c.group === g)
  const ov = t(d?.overall)
  const badN = (d?.alerts || []).filter(a => a.tone === 'bad').length

  return (
    <>
      <Head><title>Статус · Настройки | SIMB-AD ERP</title></Head>
      <Navbar active="settings" />
      <div style={{ padding: '18px 20px 0', fontFamily: UI }}>
        <SettingsTabs active="system" />
      </div>

      <div style={{ width: 1600, maxWidth: '100%', margin: '0 auto',
                    padding: '0 20px 48px', fontFamily: UI }}>

        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap',
                      marginBottom: 16 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 25, fontWeight: 800 }}>Статус</h1>
            <div style={{ ...CAPS, marginTop: 5, color: 'var(--text-faint)' }}>
              /settings/system · {d ? `${new Set(d.checks.map(c => c.group)).size} групп проверок` : '…'}
            </div>
          </div>
          {!!d && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
                           background: ov.bg, border: `1px solid ${ov.bd}`, color: ov.fg,
                           padding: '7px 13px', borderRadius: 11, marginTop: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: ov.fg }} />
              <b style={{ ...CAPS, color: ov.fg }}>{ov.label}</b>
              <span style={{ fontSize: 12 }}>
                {d.alerts.length - badN} требуют настройки ·{' '}
                {badN ? `отказов ${badN}` : 'отказов нет'}
              </span>
            </span>
          )}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 10,
                         alignItems: 'center', marginTop: 6 }}>
            {!!d && (
              <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)',
                             textTransform: 'uppercase', letterSpacing: '.06em' }}>
                {fmtTime(d.checked_at, '')}
              </span>
            )}
            <button style={btnSm(auto)} onClick={() => setAuto(a => !a)}
                    title="Обновлять каждые 30 секунд">авто · 30с</button>
            <button style={btnSm(false)} disabled={busy} onClick={() => load(true)}>
              Проверить
            </button>
          </span>
        </div>

        {!!err && (
          <div style={{ ...CARD, borderColor: 'var(--danger-border)', color: 'var(--danger)' }}>{err}</div>
        )}

        {d && (
          <div style={{ display: 'grid', gap: 14 }}>

            <div style={{ ...CARD, display: 'grid',
                          gridTemplateColumns: `repeat(${d.kpi.length}, 1fr)` }}>
              {d.kpi.map((k, i) => (
                <div key={k.key} style={{ padding: '2px 16px',
                                          borderRight: i === d.kpi.length - 1
                                            ? '1px solid transparent'
                                            : '1px solid var(--border-inner)' }}>
                  <div style={CAPS}>{k.label}</div>
                  <div style={{ fontFamily: MONO, fontSize: 23, fontWeight: 700, margin: '6px 0 4px',
                                color: k.key === 'errors' && k.value !== '0'
                                  ? 'var(--warning-text)' : 'var(--text-primary)' }}>{k.value}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{k.hint}</div>
                </div>
              ))}
            </div>

            {/* Блок целиком скрыт, когда очередь пуста: пустая рамка «всё хорошо»
                занимает место и приучает пролистывать. */}
            {!!d.alerts.length && (
              <div style={{ ...CARD, background: 'var(--warning-bg)',
                            borderColor: 'var(--warning-border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--warning)' }} />
                  <span style={CAPS}>Требует внимания</span>
                  <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10,
                                 color: 'var(--text-faint)' }}>{d.alerts.length} строк</span>
                </div>
                {d.alerts.map(a => (
                  <div key={a.key} style={{ display: 'grid',
                        gridTemplateColumns: '170px minmax(0,1fr) 132px 132px', gap: 10,
                        alignItems: 'center', padding: '9px 0',
                        borderBottom: '1px solid var(--border-row)' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
                                   fontSize: 13, fontWeight: 600 }}>
                      <Mark tone={a.tone} /> {a.title}
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12.5 }}>{a.consequence || a.note || '—'}</div>
                      {!!a.keys?.length && (
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)',
                                      marginTop: 3 }}>нет {a.keys.join(', ')}</div>
                      )}
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 10, textAlign: 'right',
                                   textTransform: 'uppercase', letterSpacing: '.05em',
                                   color: t(a.tone).fg }}>{a.value}</span>
                    <span style={{ textAlign: 'right' }}>
                      {/* Кнопка только там, где вопрос ДЕЙСТВИТЕЛЬНО решается. «Открыть
                          .env» из браузера невозможен, и такая кнопка была бы обещанием,
                          которого интерфейс не выполнит. */}
                      {a.action
                        ? <a href={a.action.href} style={{ ...btnSm(false), textDecoration: 'none' }}>
                            {a.action.label}
                          </a>
                        : <span style={{ fontFamily: MONO, fontSize: 9.5,
                                         color: 'var(--text-faint)' }}>правится в .env</span>}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14,
                          alignItems: 'stretch' }}>
              <Tile title="Действий в системе за сутки"
                    items={[{ key: 'a', tone: 'ok', title: 'Действий в системе',
                              value: String(d.activity.actions_24h),
                              note: `пик ${Math.max(...d.activity.series.map(x => x.actions))} в час` }]}>
                <Spark series={d.activity.series} field="actions" tone="var(--income)" />
              </Tile>
              <Tile title="Пользователей за сутки"
                    items={[{ key: 'u', tone: 'ok', title: 'Пользователей',
                              value: String(d.activity.users_24h),
                              note: 'считаются по журналу действий' }]}>
                <Spark series={d.activity.series} field="users" tone="var(--accent)" />
              </Tile>

              <Tile title="Службы" items={by('Службы')} />
              <Tile title="Диск и файлы" items={by('Диск')}>
                <DiskBar disk={d.disk} />
              </Tile>

              <Tile title="Базы" items={by('Базы')} />
              <Tile title="Внешние связи" items={by('Внешние связи')} />

              <Tile title="Конфигурация и бэкапы"
                    items={[...by('Конфигурация'), ...by('Бэкапы')]} />
              <Tile title="Фоновые задания" items={by('Фоновые задания')} />
            </div>

            <div style={CARD}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12,
                            flexWrap: 'wrap' }}>
                <span style={{ ...CAPS, color: 'var(--accent)' }}>Чем дополнить</span>
                <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                  шесть проверок, которых на экране нет — все считаются из того, что уже в базе
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                            gap: 12 }}>
                {SUGGESTIONS.map(([title, tone, text, src]) => (
                  <div key={title} style={{ background: 'var(--bg-subtle)', borderRadius: 13,
                                            padding: '13px 15px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: tone }} />
                      <b style={{ fontSize: 13 }}>{title}</b>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.55 }}>{text}</div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)',
                                  marginTop: 7, textTransform: 'uppercase', letterSpacing: '.06em' }}>{src}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Честная граница экрана: без неё отсутствие раздела читается как «там всё
                хорошо», а на деле там просто нечем смотреть. */}
            <div style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.6 }}>
              Контейнеры, их аптайм и политики перезапуска экран не показывает: у бэкенда
              нет доступа к докеру, и это решение — сокет докера означает root на сервере.
              Их принесёт агент на хосте. Живые запросы к внешним API тоже делает не этот
              экран, а фоновый прогон: дёргать чужие сервисы при каждом открытии — способ
              получить бан по частоте.
            </div>
          </div>
        )}
      </div>
    </>
  )
}
