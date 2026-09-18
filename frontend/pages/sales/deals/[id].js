import { useState, useEffect, useMemo, useCallback } from 'react'
import { num as mpNum, rowClicks, rowImp, rowNet } from '@/lib/mpRow'
import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/api'
import { MONO, UI, HATCH_RED, Modal } from '@/components/salesTableKit'
import { BITRIX_DEAL_URL } from '@/lib/salesLayers'
import { dm, grp0 } from '@/lib/salesFormat'
import { overlayClose } from '@/lib/overlay'
import MoveDealDialog from '@/components/sales/MoveDealDialog'
import StageRequirements from '@/components/sales/StageRequirements'
import { DEAL_DOCS, downloadBlob, pickAndUploadDoc, deleteDoc } from '@/lib/dealDocs'
import { downloadMp } from '@/lib/mpDownload'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
import Navbar from '@/components/Navbar'
import Section from '@/components/deal/Section'
import CreativesSummary, { creativesSummary } from '@/components/creatives/CreativesSummary'
import AssemblyOrd, { OrdPips } from '@/components/ord/AssemblyOrd'
import AssemblyCreatives from '@/components/creatives/AssemblyCreatives'
import CampaignSummary from '@/components/campaign/CampaignSummary'
import ValuePopover from '@/components/ValuePopover'
import { productWithSurface } from '@/lib/dealTitle'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { fmtDateOfMoment } from '@/lib/dates'
import { fmtDateTimeShort } from '@/lib/dates'
import { daysSince } from '@/lib/dates'
const DealCardMobile = dynamic(() => import('@/components/mobile/DealCardMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })

// ── Карточка сделки /sales/deals/[id] ──
// Дизайн строго по хендоффу docs/карточка сделки (design_handoff_deal_card): токены
// нашей дизайн-системы (var(--*)), шрифты Manrope/JetBrains Mono.
// Данные живые: размещение/прогноз/доп/таргетинг — из ПОСЛЕДНЕГО медиаплана сделки,
// документы — реальные файлы (загрузка/замена/удаление), история — audit_log,
// бар стадий — каталог стадий + движение через MoveDealDialog (как в реестре).
// Заглушка осталась одна: оплачено/остаток/срок оплаты — привязки платежей к сделке ещё нет.

// Деньги — две цифры после запятой: сумма строки МП считается до копеек (lib/mpRow).
const rub = (v) => (v == null ? '—' : v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽')

/** Чип саморекламы в шапке. Объявлен на модульном уровне: компонент, созданный внутри
 *  рендера, пересоздаётся на каждом кадре и теряет фокус.
 *
 *  Признак односторонний: поставить может любой с правом правки, снять — только мастер
 *  или админ. Поэтому у выключенного чипа два разных неактивных состояния, и замок
 *  показывается ДО клика: узнавать о запрете из ошибки после подтверждения — худший из
 *  возможных способов об этом сообщить. */
function SelfPromoChip({ on, canEdit, canUnset, onToggle }) {
  const locked = on && !canUnset
  const clickable = canEdit && (!on || canUnset)
  return (
    <button type="button" disabled={!clickable} onClick={onToggle}
      title={locked ? 'Статус «самореклама» присвоен — снять может только мастер аккаунт или админ'
        : on ? 'Снять статус «самореклама»'
          : 'Пометить размещение саморекламой — после подтверждения снять сможет только мастер аккаунт'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 9, borderRadius: 999,
        padding: '5px 12px 5px 6px', whiteSpace: 'nowrap', fontFamily: UI,
        border: `1px solid ${on ? 'var(--warning-border)' : 'var(--border-card)'}`,
        background: on ? 'var(--warning-tint)' : 'var(--bg-subtle)',
        cursor: clickable ? 'pointer' : 'default',
      }}>
      {/* Тумблер, а не галочка: признак включают один раз и он остаётся видимым
          состоянием блока, а не действием, которое ищут в меню. */}
      <span style={{ position: 'relative', width: 28, height: 16, borderRadius: 999, flex: '0 0 28px',
        background: on ? 'var(--warning)' : 'var(--border-hover)', transition: 'background .18s' }}>
        <span style={{ position: 'absolute', top: 2, left: on ? 14 : 2, width: 12, height: 12,
          borderRadius: '50%', background: 'var(--bg-card)', transition: 'left .18s' }} />
      </span>
      <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', fontWeight: 700,
        textTransform: 'uppercase', color: on ? 'var(--warning-text)' : 'var(--text-muted)' }}>
        Самореклама
      </span>
      {locked && <span style={{ fontSize: 10, opacity: 0.7 }}>🔒</span>}
    </button>
  )
}

/** «В стадии N дней» — от даты ВХОДА В СТАДИЮ, которую даёт бэкенд из истории движения.
 *
 *  Раньше считалось по журналу действий: бралась последняя запись `move_deal`. Но журнал
 *  пишут разными действиями (`bulk_update_deals`, `ad_campaign_finish`), и при переводе
 *  не через диалог карточка показывала «в стадии 34 дня», пока очередь аккаунта считала
 *  от сегодня. Оба числа были «правдивы» по своему источнику — расходились они молча.
 *
 *  Даты нет — фразы нет: сделка не двигалась у нас, и выдумывать вход в стадию нельзя. */
function daysInStage(since) {
  const d = daysSince(since)
  return d != null && d >= 0 ? d : null
}

/** «6 дней» / «1 день» / «5 дней» — падежи руками, Intl.PluralRules для ru даёт
 *  категории, но не слова. */
function plDays(n) {
  const t = n % 100
  if (t >= 11 && t <= 14) return `${n} дней`
  const o = n % 10
  return `${n} ${o === 1 ? 'день' : o >= 2 && o <= 4 ? 'дня' : 'дней'}`
}

const OVERLAY = {
  position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(28,36,51,.4)',
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
  overflowY: 'auto', padding: '60px 20px', fontFamily: UI,
}
const SHEET = {
  width: '100%', background: 'var(--bg-card)', borderRadius: 18,
  boxShadow: 'var(--shadow-card)', display: 'flex', flexDirection: 'column',
}

/** Да/нет на необратимое действие. Текст вопроса называет последствие, а не действие:
 *  «уверены?» без последствия не помогает решить. */
function Ask({ title, text, onYes, onNo }) {
  return (
    <div {...overlayClose(onNo)} style={OVERLAY}>
      <div onClick={e => e.stopPropagation()} style={{ ...SHEET, maxWidth: 460, padding: '22px 24px 20px', gap: 12 }}>
        <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em' }}>{title}</span>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{text}</span>
        <span style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 4 }}>
          <button type="button" onClick={onNo} style={{ height: 36, padding: '0 16px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', fontFamily: UI }}>Нет</button>
          <button type="button" onClick={onYes} style={{ height: 36, padding: '0 18px', borderRadius: 10, border: 'none', background: 'var(--warning)', color: 'var(--bg-card)', fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>Да</button>
        </span>
      </div>
    </div>
  )
}

/** Бриф сделки. Тянется лениво — поле живёт в Битриксе и кэшируется у нас при первом
 *  открытии, поэтому грузим по клику, а не вместе с карточкой. */
function BriefDialog({ dealId, canEdit, onClose }) {
  const [state, setState] = useState({ loading: true, text: '', err: '', local: false, saving: false })
  const load = (refresh) => {
    setState(s => ({ ...s, loading: true, err: '' }))
    api.get(`/sales/deals/${dealId}/brief${refresh ? '?refresh=1' : ''}`, auth())
      .then(r => setState({ loading: false, text: r.data.brief || '', err: '', local: !!r.data.is_local, saving: false }))
      .catch(e => setState(s => ({ ...s, loading: false, err: e.response?.data?.detail || 'Не удалось загрузить бриф' })))
  }
  useEffect(() => { load(false) }, [dealId])

  const save = () => {
    setState(s => ({ ...s, saving: true, err: '' }))
    api.put(`/sales/deals/${dealId}/brief`, { brief: state.text }, auth())
      .then(() => { setState(s => ({ ...s, saving: false })); onClose() })
      .catch(e => setState(s => ({ ...s, saving: false, err: e.response?.data?.detail || 'Не удалось сохранить' })))
  }

  return (
    <div {...overlayClose(onClose)} style={OVERLAY}>
      <div onClick={e => e.stopPropagation()} style={{ ...SHEET, maxWidth: 620 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '18px 24px', borderBottom: '1px solid var(--border-card)' }}>
          <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.02em' }}>Бриф сделки</span>
          {!state.local && (
            <button type="button" onClick={() => load(true)} title="Перечитать поле из Битрикса"
              style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 0, cursor: 'pointer', fontFamily: UI }}>
              обновить из Битрикса
            </button>
          )}
          <button type="button" onClick={onClose} style={{ marginLeft: 'auto', width: 32, height: 32, borderRadius: 9, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 16 }}>✕</button>
        </div>
        <div style={{ padding: '18px 24px' }}>
          {state.loading
            ? <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Загрузка…</span>
            : (
              <textarea value={state.text} readOnly={!canEdit} rows={12}
                onChange={e => setState(s => ({ ...s, text: e.target.value }))}
                placeholder={canEdit ? 'Бриф пуст — напишите, что заказчик хочет получить' : 'Бриф пуст'}
                style={{ width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '11px 12px', fontSize: 13, lineHeight: 1.5, fontFamily: UI, background: canEdit ? 'var(--bg-card)' : 'var(--bg-subtle)', color: 'var(--text-primary)', outline: 'none', resize: 'vertical' }} />
            )}
          {!!state.err && <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--danger)' }}>{state.err}</div>}
        </div>
        {canEdit && !state.loading && (
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', padding: '0 24px 20px' }}>
            <button type="button" onClick={onClose} style={{ height: 36, padding: '0 16px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', fontFamily: UI }}>Отмена</button>
            <button type="button" onClick={save} disabled={state.saving} style={{ height: 36, padding: '0 18px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 13, fontWeight: 700, cursor: state.saving ? 'default' : 'pointer', opacity: state.saving ? 0.6 : 1, fontFamily: UI }}>
              {state.saving ? 'Сохраняю…' : 'Сохранить'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * «Цели и особенности РК» — что аккаунт передаёт трафику вместе с кампанией.
 *
 * Поле НАШЕ и в Битрикс не уходит, в отличие от соседнего брифа: это передача задачи
 * внутри команды. Поэтому и виджет не диалог, а блок на карточке — его читают, а не
 * открывают: трафик увидит тот же текст у себя, и он должен быть на виду у обоих.
 *
 * Значение приезжает вместе с карточкой (`deal.traffic_brief`), локальное состояние
 * нужно только на время правки — иначе каждый символ уезжал бы на сервер.
 */
// ── Доп. параметры РК ──
// Блок-контейнер: сегодня в нём один параметр, но у него уже своё место в лестнице
// (между «Цели и особенности» и «Креативы») и своя подпись. Следующий параметр будет
// строкой здесь, а не новым блоком и не полем, приклеенным к соседнему смыслу.
//
// ВКЛЮЧЕНИЕ НЕОБРАТИМО для обычного аккаунта (владелец 14.09.2026): оно поднимает
// требование пикселя в выгрузке в DSP и рождает задачу трафику. Поэтому спрашиваем
// подтверждение модалкой, а не переключаем молча по клику.
function CampaignExtra({ dealId, deal, canEdit, onSaved }) {
  const [ask, setAsk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // Способ выбирается В МОДАЛКЕ, вместе с подтверждением: это часть одного решения,
  // а не отдельная настройка, которую можно переключить после.
  const [mode, setMode] = useState('own')
  const [tag, setTag] = useState('')
  const [ins, setIns] = useState('')
  const on = !!deal.weborama_pixel
  const external = (deal.weborama_pixel_mode || 'own') === 'external'
  const canUnset = !!deal.can_unset_weborama_pixel
  const decided = !!deal.weborama_pixel_decided

  const send = (value) => {
    setBusy(true); setErr('')
    const body = value
      ? { weborama_pixel: true, mode, tag: mode === 'external' ? tag.trim() : null,
        insertion: mode === 'external' ? ins.trim() : null }
      : { weborama_pixel: false }
    api.put(`/sales/deals/${dealId}/campaign-extra`, body, auth())
      .then(r => { setBusy(false); setAsk(false); onSaved(r.data) })
      .catch(e => { setBusy(false); setErr(e.response?.data?.detail || 'Не удалось сохранить') })
  }

  const when = deal.weborama_pixel_at
    ? fmtDateOfMoment(deal.weborama_pixel_at)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 11 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 20, height: 20, borderRadius: 6, flex: '0 0 20px', marginTop: 1,
          border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`,
          background: on ? 'var(--accent)' : 'var(--bg-card)',
          color: 'var(--bg-card)', fontSize: 12, fontWeight: 700 }}>{on ? '✓' : ''}</span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
            Нужен пиксель Weborama
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
            {!on
              ? (decided
                ? 'Решено: не нужен. Вставки в Weborama не заводятся, пиксель в креатив не вшивается, выгрузка в DSP его не требует.'
                : 'Решение не принято. Выберите «нужен» или «не нужен» — от этого зависит, потребует ли выгрузка в DSP пиксель по каждой площадке.')
              : external
                ? `Внешний тег${when ? ', загружен ' + when : ''}. Вставку завёл клиент — свою не заводим. Статистику Weborama по такой РК не снимает: показы вносятся руками на сверке.`
                : `Свой${when ? ', заказан ' + when : ''}. Трафик получил задачу; выгрузка в DSP не пойдёт, пока пиксель не получен по всем площадкам.`}
          </span>
        </span>
        {/* ПОКА НЕ РЕШИЛИ — две кнопки, и обе называют решение. «Заказать» в одиночку
            предлагало только один исход, а второй («не надо») делался бездействием — то
            есть был неотличим от «забыли». */}
        {canEdit && !on && !decided && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
            <button type="button" onClick={() => send(false)} disabled={busy}
              style={{ height: 32, padding: '0 14px', borderRadius: 9,
                border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                color: 'var(--text-secondary)', fontSize: 12.5, fontWeight: 700,
                fontFamily: UI, cursor: busy ? 'default' : 'pointer' }}>
              {busy ? '…' : 'Не нужен'}
            </button>
            <button type="button" onClick={() => setAsk(true)} disabled={busy}
              style={{ height: 32, padding: '0 14px', borderRadius: 9,
                border: 'none', background: 'var(--accent)', color: 'var(--bg-card)',
                fontSize: 12.5, fontWeight: 700, fontFamily: UI, cursor: 'pointer' }}>
              Нужен
            </button>
          </span>
        )}
        {/* Решение «не нужен» уже принято — оставляем один ход назад. */}
        {canEdit && !on && decided && (
          <button type="button" onClick={() => setAsk(true)} disabled={busy}
            style={{ marginLeft: 'auto', height: 32, padding: '0 14px', borderRadius: 9,
              border: 'none', background: 'var(--accent)', color: 'var(--bg-card)',
              fontSize: 12.5, fontWeight: 700, fontFamily: UI, cursor: 'pointer' }}>
            Заказать
          </button>
        )}
        {canEdit && on && canUnset && (
          <button type="button" onClick={() => send(false)} disabled={busy}
            style={{ marginLeft: 'auto', height: 32, padding: '0 14px', borderRadius: 9,
              border: '1px solid var(--border-card)', background: 'var(--bg-card)',
              color: 'var(--danger-fg)', fontSize: 12.5, fontWeight: 700, fontFamily: UI,
              cursor: busy ? 'default' : 'pointer' }}>
            {busy ? '…' : 'Снять'}
          </button>
        )}
        {canEdit && on && !canUnset && (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-cap)',
            whiteSpace: 'nowrap', marginTop: 6 }}>снимает мастер аккаунта</span>
        )}
      </div>
      {on && external && !!deal.weborama_pixel_tag && (
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3,
          background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)',
          borderRadius: 9, padding: '8px 10px' }}>
          <span style={{ fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase',
            color: 'var(--text-cap)' }}>
            тег показа{deal.weborama_ext_insertion ? ` · вставка ${deal.weborama_ext_insertion}` : ''}
          </span>
          {/* Тег целиком, без обрезки: его сверяют с присланным файлом посимвольно,
              а многоточие в середине делает сверку невозможной. */}
          <span style={{ fontFamily: MONO, fontSize: 10.5, wordBreak: 'break-all',
            color: 'var(--text-secondary)', lineHeight: 1.5 }}>{deal.weborama_pixel_tag}</span>
        </span>
      )}
      {!!err && <span style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>{err}</span>}

      {ask && (
        <Modal title="Заказать пиксель Weborama?" width={520} onClose={() => { if (!busy) setAsk(false) }}
          footer={
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setAsk(false)} disabled={busy}
                style={{ height: 36, padding: '0 16px', borderRadius: 10,
                  border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                  color: 'var(--text-secondary)', fontSize: 13, fontFamily: UI, cursor: 'pointer' }}>
                Отмена
              </button>
              <button type="button" onClick={() => send(true)}
                disabled={busy || (mode === 'external' && !tag.trim())}
                style={{ height: 36, padding: '0 18px', borderRadius: 10, border: 'none',
                  background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 13,
                  fontWeight: 700, fontFamily: UI, cursor: busy ? 'default' : 'pointer',
                  opacity: busy ? 0.6 : 1 }}>
                {busy ? 'Заказываю…' : 'Заказать'}
              </button>
            </div>
          }>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 11, fontSize: 13,
            lineHeight: 1.6, color: 'var(--text-primary)' }}>
            {/* Способ — первым: от него зависит и что произойдёт, и что надо заполнить. */}
            <span style={{ display: 'flex', gap: 8 }}>
              {[['own', 'Получить свой'], ['external', 'Загрузить внешний']].map(([v, l]) => (
                <button key={v} type="button" onClick={() => setMode(v)}
                  style={{ flex: 1, height: 34, borderRadius: 9, fontSize: 12.5,
                    fontWeight: 700, fontFamily: UI, cursor: 'pointer',
                    border: `1px solid ${mode === v ? 'var(--accent)' : 'var(--border-card)'}`,
                    background: mode === v ? 'var(--accent-tint)' : 'var(--bg-card)',
                    color: mode === v ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>
                  {l}
                </button>
              ))}
            </span>

            {mode === 'own' ? (
              <>
                <span>Что произойдёт:</span>
                <span style={{ color: 'var(--text-secondary)' }}>
                  · трафик получит задачу «нужен пиксель» в своём кабинете;<br />
                  · выгрузка креативов в DSP будет отказывать, пока пиксель не получен по всем площадкам;<br />
                  · тег верификатора вошьётся в разметку каждого креатива.
                </span>
              </>
            ) : (
              <>
                <span style={{ color: 'var(--text-secondary)' }}>
                  Тег из выгрузки клиента — столбец <b>Impression tags</b>. Он один на всю
                  кампанию: свою вставку заводить не будем, а статистику по такой РК
                  Weborama не отдаёт — показы вносятся руками на сверке.
                </span>
                <textarea value={tag} onChange={e => setTag(e.target.value)} rows={4}
                  placeholder="https://wcm.weborama-tech.ru/…&a.ra=[RANDOM]"
                  style={{ width: '100%', boxSizing: 'border-box', fontFamily: MONO,
                    fontSize: 11, lineHeight: 1.5, padding: '9px 10px', borderRadius: 9,
                    border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                    color: 'var(--text-primary)', outline: 'none', resize: 'vertical' }} />
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>ID insertion</span>
                  <input value={ins} onChange={e => setIns(e.target.value)}
                    placeholder="1526"
                    style={{ width: 120, height: 32, fontFamily: MONO, fontSize: 12,
                      padding: '0 9px', borderRadius: 8, border: '1px solid var(--border-card)',
                      background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }} />
                  <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                    по нему сверяемся с их отчётом</span>
                </span>
              </>
            )}

            <span style={{ color: 'var(--warning-fg)' }}>
              Снять заказ сможет только мастер аккаунта или админ. Действие записывается в журнал.
            </span>
          </div>
        </Modal>
      )}
    </div>
  )
}

function TrafficBrief({ dealId, value, canEdit, onSaved }) {
  const [text, setText] = useState(value || '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { setText(value || '') }, [value])

  const dirty = (text || '') !== (value || '')
  const save = () => {
    setBusy(true); setErr('')
    api.put(`/sales/deals/${dealId}/traffic-brief`, { traffic_brief: text }, auth())
      .then(r => { setBusy(false); onSaved(r.data.traffic_brief) })
      .catch(e => { setBusy(false); setErr(e.response?.data?.detail || 'Не удалось сохранить') })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      <textarea value={text} readOnly={!canEdit} rows={6}
        onChange={e => setText(e.target.value)}
        placeholder={canEdit
          ? 'Что важно знать трафику: цель кампании, ограничения площадок, пожелания клиента, на что смотреть в открутке'
          : 'Пока не заполнено'}
        style={{ width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)',
          borderRadius: 10, padding: '11px 12px', fontSize: 13, lineHeight: 1.5, fontFamily: UI,
          background: canEdit ? 'var(--bg-card)' : 'var(--bg-subtle)', color: 'var(--text-primary)',
          outline: 'none', resize: 'vertical' }} />
      {!!err && <span style={{ fontSize: 12.5, color: 'var(--danger)' }}>{err}</span>}
      {canEdit && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
            Видно трафику в его кабинете. В Битрикс не уходит.
          </span>
          <button type="button" onClick={save} disabled={busy || !dirty}
            style={{ marginLeft: 'auto', height: 34, padding: '0 16px', borderRadius: 10,
              border: 'none', background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 13,
              fontWeight: 700, fontFamily: UI, cursor: (busy || !dirty) ? 'default' : 'pointer',
              opacity: (busy || !dirty) ? 0.5 : 1 }}>
            {busy ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Комментарии сделки — подраздел рядом с историей, но ОТДЕЛЬНОЙ лентой (владелец
 * 05.09.2026): история это системные события из журнала, комментарий — то, что человек
 * сказал сам. В одном потоке пришлось бы всегда держать фильтр «только комментарии».
 *
 * До этого здесь стоял отключённый инпут с подписью «скоро». Правок и удалений нет:
 * каждая запись отдельная и остаётся как есть.
 */
function DealComments({ dealId, canEdit }) {
  const [items, setItems] = useState(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    api.get(`/sales/deals/${dealId}/comments`, auth())
      .then(r => { if (alive) setItems(r.data.items || []) })
      .catch(() => { if (alive) setItems([]) })
    return () => { alive = false }
  }, [dealId])

  const send = () => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true); setErr('')
    api.post(`/sales/deals/${dealId}/comments`, { text: t }, auth())
      .then(r => { setItems(x => [r.data, ...(x || [])]); setText(''); setBusy(false) })
      .catch(e => { setBusy(false); setErr(e.response?.data?.detail || 'Не удалось отправить') })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 12,
      borderTop: '1px solid var(--border-card)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={CAPS}>Комментарии</span>
        {!!(items && items.length > 4) && (
          <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9,
            color: 'var(--text-faint)' }}>{items.length}</span>
        )}
      </div>
      {items === null
        ? <div style={{ fontSize: 11, color: 'var(--text-faint)', padding: '4px 0' }}>Загрузка…</div>
        : items.length ? (
          // Высота считается из строки комментария, как у истории рядом: четыре записи
          // видны сразу, дальше прокрутка.
          <div style={items.length > 4 ? { maxHeight: 232, overflowY: 'auto', paddingRight: 4 } : undefined}>
            {items.map(c => (
              <div key={c.id} style={{ display: 'flex', flexDirection: 'column', gap: 2,
                padding: '7px 0', borderTop: '1px solid var(--border-row)' }}>
                <span style={{ fontSize: 11.5, lineHeight: 1.4, whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word' }}>{c.text}</span>
                <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>
                  {fmtWhen(c.at)}{c.author ? ` · ${c.author}` : ''}
                </span>
              </div>
            ))}
          </div>
        ) : <div style={{ fontSize: 11, color: 'var(--text-faint)', padding: '4px 0' }}>Комментариев пока нет.</div>}
      {canEdit && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, paddingTop: 8,
          borderTop: '1px solid var(--border-row)' }}>
          <input value={text} onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') send() }}
            placeholder="Комментарий…"
            style={{ flex: 1, minWidth: 0, height: 30, boxSizing: 'border-box', padding: '0 10px',
              background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9,
              fontFamily: UI, fontSize: 11.5, outline: 'none' }} />
          <button type="button" onClick={send} disabled={busy || !text.trim()}
            title="Отправить (Enter)"
            style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 11px',
              background: 'var(--accent)', color: 'var(--bg-card)', border: 'none', borderRadius: 9,
              fontSize: 11, fontWeight: 700, fontFamily: UI,
              cursor: (busy || !text.trim()) ? 'default' : 'pointer',
              opacity: (busy || !text.trim()) ? 0.5 : 1 }}>→</button>
        </div>
      )}
      {!!err && <span style={{ fontSize: 11, color: 'var(--danger)' }}>{err}</span>}
    </div>
  )
}

const DocIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" />
  </svg>
)

/** дд.мм.гггг из ISO: весь раздел продаж пишет даты так. */
const ru = (x) => (x ? String(x).slice(0, 10).split('-').reverse().join('.') : '—')

/** Сводка медиаплана в заголовке свёрнутой секции — то, ради чего в неё заглядывают. */
function mpSummary(rowCount, net, mp) {
  if (!mp) return 'медиаплан не создан'
  const parts = []
  if (rowCount) parts.push(rowCount + (rowCount === 1 ? ' строка' : rowCount < 5 ? ' строки' : ' строк'))
  if (net != null) parts.push(rub(net))
  if (mp.version) parts.push(`v${mp.version}`)
  return parts.join(' · ')
}

/** Ключевые значения МП для свёрнутого вида. Нейтральные: это цифры, а не состояния. */
function mpFacts({ d, lines, net, gross, tImp, mp }) {
  const svc = [...new Set(lines.map(l => l.position).filter(Boolean))]
  const period = d.period_from ? `${dm(d.period_from, '')} — ${dm(d.period_to, '')}` : (d.period || '—')
  return [
    { label: 'Услуга',
      value: svc.length === 1 ? svc[0] : svc.length ? `${svc.length} услуги` : '—',
      color: svc.length ? null : 'var(--text-faint)' },
    { label: 'Сумма до НДС', value: rub(net) },
    // Прочерк на месте суммы с НДС читается как «нет данных по сделке», хотя причина
    // в другом и она чинится в один клик — поэтому свёрнутый вид называет её сам.
    { label: 'С НДС',
      value: (gross == null && net != null) ? 'ставка НДС не задана' : rub(gross),
      color: gross == null ? 'var(--warning-text)' : 'var(--accent)' },
    // Показы, а не объём: у Фикса и Пакета объём это штуки закупки, и складывать их
    // с показами CPM бессмысленно (так же считает годовая выгрузка).
    { label: 'Показы по прогнозу', value: tImp ? grp0(tImp) : '—',
      color: tImp ? 'var(--income)' : 'var(--text-faint)' },
    { label: 'Период РК', value: period },
    { label: 'Версия', value: mp ? `v${mp.version}` : 'нет',
      color: mp ? 'var(--warning-text)' : 'var(--text-faint)' },
  ]
}

/** Короткая сводка обвязки ОРД: сошлось или где встало. */
function ordSummaryText(a) {
  if (!a) return { text: 'не проверено', tone: null }
  if (!a.payer.ok) return { text: 'плательщик не определён', tone: 'warn' }
  if (!a.final.ok) return { text: 'нет доходного договора', tone: 'warn' }
  if (!a.initial.ok) {
    const k = a.initial.candidates?.length || 0
    return { text: k ? `выберите изначальный из ${k}` : 'нет изначальных договоров', tone: 'warn' }
  }
  // Договорная цепочка сошлась — но секция называется «Цепочка договоров и ЕРИД», и
  // ступень маркера теперь рабочая. Оставить «сошлась» на трёх из четырёх значило бы
  // объявить готовым то, по чему ещё не выпущен ни один маркер.
  const c = a.creatives || {}
  if (!c.total) return { text: 'цепочка сошлась · креативов нет', tone: null }
  if (!c.marked) return { text: 'цепочка сошлась · маркер не выпущен', tone: 'warn' }
  if (!c.ok) return { text: `маркировано ${c.marked} из ${c.total}`, tone: 'warn' }
  return { text: 'цепочка сошлась, все маркированы', tone: 'ok' }
}

/** Ключевые значения обвязки для свёрнутого вида — со статусами, у каждого есть состояние. */
/* Одна ступень — одна плашка. Значение выбирается так же, как в развёрнутой строке:
   один креатив — сам маркер, несколько — счёт; «песочница» приписывается к демовскому,
   потому что снаружи он неотличим от боевого, а в размещение годится только настоящий. */
function ordEridFact(c) {
  if (!c || !c.total) return { label: 'ЕРИД', value: 'не выпущен', tone: 'off' }
  const sandbox = (c.erids || []).some(e => e.env && e.env !== 'prod')
  const one = c.total === 1 && c.erids && c.erids[0]
  return {
    label: sandbox ? 'ЕРИД · песочница' : 'ЕРИД',
    value: c.marked ? (one ? c.erids[0].erid : `${c.marked} из ${c.total}`) : 'не выпущен',
    tone: c.ok ? 'ok' : (c.marked ? 'warn' : 'off'),
  }
}


function ordFacts(a) {
  if (!a) return [{ label: 'Состояние', value: 'не проверено', tone: 'off' }]
  const ini = a.initial.bound || a.initial.proposal
  return [
    { label: 'Плательщик', value: a.payer.ok ? (a.payer.name || 'без названия') : 'не определён',
      tone: a.payer.ok ? 'ok' : 'warn' },
    { label: 'Доходный договор', value: a.final.ok ? (a.final.contract.number || 'без номера') : 'не найден',
      tone: a.final.ok ? 'ok' : 'warn' },
    { label: 'Изначальный',
      value: a.initial.ok ? (ini && ini.number ? ini.number : 'привязан')
        : (a.initial.candidates?.length ? `выбрать из ${a.initial.candidates.length}` : 'нет'),
      tone: a.initial.ok ? 'ok' : 'warn' },
    // Плашка ЕРИД читает ту же ступень, что и развёрнутый вид. Раньше здесь стояла
    // константа «не выпущен» — она была честна, пока выпуска не существовало, а теперь
    // врала бы про маркированную сделку прямо в свёрнутом виде.
    ordEridFact(a.creatives),
  ]
}
const num = (v) => (v == null ? '—' : v.toLocaleString('ru-RU'))
const dec = (v) => v.toFixed(2).replace('.', ',')
const initials = (name) => (name ? name.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase() : '—')

// время события в московском времени (UTC+3), как в Журнале действий
// Время истории. Разбор момента общий, из lib/dates: копий этой функции было шесть.
const fmtWhen = (str) => fmtDateTimeShort(str, '')
// Светофор слоёв денег — как в реестре/диалоге движения (единая трактовка цвета).
const LAYER_COLOR = {
  'планируемые': 'var(--text-faint, var(--text-faint))',
  'реализуемые': 'var(--dot-current-dz, var(--warning))',
  'фактические': 'var(--income, var(--income-fg))',
}
const EVENT_COLOR = {
  create_deal: 'var(--text-faint)', patch_sales_deal: 'var(--dot-current-dz)',
  save_deal_brief: 'var(--income)', push_deal_to_bitrix: 'var(--accent)', sync_deal_from_bitrix: 'var(--accent)',
}

// Список видов документов — общий для карточки, раскрывашки и доски (lib/dealDocs).
const DOC_KINDS = DEAL_DOCS.map(d => [d.kind, d.label, !!d.bx])
const DOC_ACT = { display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 7px', border: '1px solid var(--border-card)', borderRadius: 7, background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 10, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }

// Строка документа
function DocRow({ ok, title, meta, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, background: ok ? 'var(--bg-card)' : 'var(--bg-dim)', border: `1px solid ${ok ? 'var(--border-card)' : 'var(--border-inner)'}`, borderRadius: 11, padding: '9px 10px', minWidth: 0 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 7, background: ok ? 'var(--accent-tint)' : 'var(--bg-subtle)', color: ok ? 'var(--accent)' : 'var(--text-disabled)', flex: '0 0 22px' }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0, flex: 1 }}>
        <span style={{ fontSize: 11.5, fontWeight: 700, color: ok ? 'var(--text-primary)' : 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
        <span title={meta} style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{meta}</span>
      </span>
      {right}
    </div>
  )
}

// стилевые примитивы карточки (из эталона)
const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }

const CAPS = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const SUBCAPS = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }
const MONEY_LBL = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
/* Подписи инвентаря — дословно из конструктора медиаплана (INV_LABEL там же): одно
   значение, названное на двух экранах по-разному, читается как два разных. */
const INV_LABEL = { web: 'Web', app: 'IN-App', cross: 'Кросс-девайс' }

/* Инвентарь стоит третьим, как в конструкторе. Он не украшение: у еФарма веб и
   приложение идут ПО РАЗНОЙ ЦЕНЕ, и по нему же подставляются площадки на сборке
   креативов — строка без него не проверяема. */
const PL_GRID = '1.6fr 0.8fr 0.75fr 0.55fr 0.95fr 0.85fr 0.6fr 1.15fr 1.15fr'
/* Пятнадцать колонок прогноза — ровно те же, что в конструкторе медиаплана.
   Первая колонка ФИКСИРОВАННАЯ, а не долевая: при долевой имя строки забирало тем
   больше места, чем шире экран, и цифрам его переставало хватать первыми. Ширина
   посчитана под доступные ~1174 px левой колонки карточки (1520 − 280 правая − 14
   зазор − 52 поля карточки): 130 + 15×62 + 15 зазоров по 7 = 1165. */
const FC_GRID = '130px repeat(15, minmax(0, 1fr))'
const FC_GAP = 7
/* Единица измерения — в ЗАГОЛОВКЕ, а не в каждой ячейке. Повторённые в пятнадцати
   строках «₽» и «%» съедали по два знака в колонке (≈13 px), из-за чего таблица не
   помещалась и уезжала под прокрутку. В заголовке единица названа один раз и читается
   так же однозначно. */
const FC_HEADS = ['Частота', 'Охват', 'Показы', 'CTR %', 'Клики', 'CPM ₽', 'CPC ₽',
                  'CPU ₽', 'CR %', 'Чеки', 'CPO ₽', 'Цена ₽', 'Доход ₽', 'ROI %', 'SOV %']
/* Цифра не переносится: при нехватке места строка «1 234 567» ломалась пополам и
   таблица начинала «дышать» по высоте. Лучше горизонтальная прокрутка на узком
   экране, чем два яруса в каждой ячейке. */
const FC_NUM = { fontFamily: MONO, fontSize: 11, textAlign: 'right', whiteSpace: 'nowrap' }

export default function DealCard() {
  const router = useRouter()
  const { id } = router.query
  const isMobile = useIsMobile()
  const [deal, setDeal] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [phases, setPhases] = useState([])      // каталог стадий — для бара цепочки
  const [mp, setMp] = useState(null)            // последний медиаплан сделки (полные данные)
  const [moveOpen, setMoveOpen] = useState(false)
  // Требования СЛЕДУЮЩЕГО шага — на карточке, а не только в диалоге: человек должен
  // видеть, чего не хватает, ещё до того как нажмёт «Изменить стадию». Цель не задаём —
  // ручка берёт следующую по цепочке, ту же, что подставит диалог.
  const [nextReq, setNextReq] = useState(null)

  useEffect(() => {
    if (!id) return
    let dead = false
    api.get(`/sales/deals/${id}/move-preview`, auth())
      .then(r => { if (!dead) setNextReq(r.data) })
      .catch(() => { if (!dead) setNextReq(null) })   // молчим: список не обязателен
    return () => { dead = true }
    // Зависимость — `deal`, объявленная ВЫШЕ (строка 486), а не `d` из строки 705:
    // `d` здесь ещё во временной мёртвой зоне, и `?.` от неё не спасает. Такая ссылка
    // роняет карточку целиком в браузере, при этом сервер отдаёт 200 и чистый HTML —
    // страница статическая, ошибка возникает только при гидратации. Ни curl, ни сборка
    // этого не видят (13.09.2026).
  }, [id, deal?.our_stage?.id])
  const [docBusy, setDocBusy] = useState('')    // kind документа в процессе загрузки/удаления
  const [canEdit, setCanEdit] = useState(false)
  // Роль администратора нужна отдельным признаком: за ней спрятаны действия,
  // подменяющие чужую зону ответственности (ответ за площадку, отметка «в эфир»).
  const [isAdmin, setIsAdmin] = useState(false)
  const [canApprove, setCanApprove] = useState(false)
  // Состояние обвязки тянем на уровне карточки, а не внутри секции: свёрнутый вид
  // показывает данные, и до первого разворачивания их иначе взять неоткуда.
  const [ordSummary, setOrdSummary] = useState(null)
  // Сводка креативов грузится ЗДЕСЬ, а не внутри блока: тело секции — функция, и пока
  // секция свёрнута, оно не монтируется. Запрос, живущий внутри, до свёрнутого вида
  // не доходит — на этой же карточке так уже случилось с обвязкой ОРД.
  const [creatives, setCreatives] = useState(null)
  const [ordErr, setOrdErr] = useState('')

  // Постановку признака подтверждают, снятие — нет: подтверждают необратимое, а снять
  // может только мастер, для которого это как раз исправление ошибки. Спрашивать
  // «вы уверены?» на каждом шаге — верный способ научить не читать вопрос.
  const [briefOpen, setBriefOpen] = useState(false)
  const [promoAsk, setPromoAsk] = useState(false)
  const [promoErr, setPromoErr] = useState('')

  const applySelfPromo = async (next) => {
    setPromoAsk(false)
    setPromoErr('')
    const prev = !!deal.is_self_promo
    setDeal(x => ({ ...x, is_self_promo: next }))          // отзывчиво, до ответа
    try {
      await api.patch(`/sales/deals/${deal.id}`, { is_self_promo: next }, auth())
      reload()                                             // история пополнилась записью
    } catch (e) {
      setDeal(x => ({ ...x, is_self_promo: prev }))        // не сохранилось — вернуть как было
      setPromoErr(e.response?.data?.detail || 'Не удалось изменить статус')
    }
  }

  const toggleSelfPromo = () => {
    if (!canEdit || !deal) return
    if (deal.is_self_promo) applySelfPromo(false)
    else setPromoAsk(true)
  }

  const reload = () => {
    api.get(`/sales/deals/${id}`, auth()).then(r => setDeal(r.data)).catch(() => {})
    api.get(`/sales/deals/${id}/history`, auth()).then(r => setHistory(r.data.items || [])).catch(() => {})
  }

  /* Назначение трафика — здесь И на сборке (владелец 03.09.2026). До этого контрол жил
     только на сборке, а карточка показывала прочерк даже у назначенной сделки: строка
     «Трафик» была захардкожена пустой. Ответственного ставят и меняют вручную до старта,
     на отправку материала он больше не влияет.

     Кандидатов тянем лениво — список короткий, но и он не нужен, пока никто не
     назначает. Ручка та же, что на сборке (`/launch-prep/traffic-managers`): второй
     список кандидатов разъехался бы с первым. */
  const [tmPop, setTmPop] = useState(null)      // { rect } — поповер выбора
  const [tmList, setTmList] = useState(null)
  const openTraffic = async (e) => {
    setTmPop({ rect: e.currentTarget.getBoundingClientRect() })
    if (tmList) return
    try {
      const r = await api.get('/launch-prep/traffic-managers', auth())
      setTmList(r.data.items || [])
    } catch { setTmList([]) }
  }
  const pickTraffic = async (userId) => {
    setTmPop(null)
    try {
      await api.put(`/launch-prep/deal/${id}/traffic-manager`,
        { user_id: userId ? Number(userId) : null }, auth())
      reload()
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось назначить трафика') }
  }

  // Состояние обвязки грузит карточка, а не сама секция: секция ленивая, свёрнутый блок
  // не монтируется, и запрос из него не уходил бы вовсе — свёрнутый вид показывал
  // «не проверено» до первого разворачивания.
  /* ЗАЧЕМ useCallback. Обе загрузки уходят в пропсы блока креативов, а он зовёт их после
     каждой своей перезагрузки. Обычная функция получает новую личность на каждом рендере
     страницы — блок видит «проп изменился», перезагружается, дёргает загрузку, страница
     рендерится снова, и так по кругу. 27.08.2026 это дало 1353 запроса `/assembly` за
     сеанс, и часть из них падала — со стороны выглядело как «иногда не загружается
     состояние». Личность функции здесь — не оптимизация, а условие остановки. */
  const dealId = deal && deal.id

  const loadOrd = useCallback(() => {
    if (!dealId) return
    api.get(`/ord/deal/${dealId}/assembly`, auth())
      .then(r => { setOrdSummary(r.data); setOrdErr('') })
      .catch(e => setOrdErr(e.response?.data?.detail || 'Не удалось загрузить состояние'))
  }, [dealId])

  const loadCreatives = useCallback(() => {
    if (!dealId) return
    api.get(`/launch-prep/deal/${dealId}`, auth())
      .then(r => setCreatives(r.data)).catch(() => {})
  }, [dealId])

  const onCreativesChanged = useCallback(() => {
    loadCreatives(); loadOrd()
  }, [loadCreatives, loadOrd])

  useRefreshOnReturn(() => reload())
  useEffect(() => { loadOrd(); loadCreatives() }, [loadOrd, loadCreatives])

  useEffect(() => {
    if (typeof window === 'undefined' || !id) return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try {
      const p = JSON.parse(localStorage.getItem('permissions') || '{}')
      setIsAdmin(localStorage.getItem('role') === 'admin')
      setCanEdit(localStorage.getItem('is_admin') === 'true' || !!(p.sales_registry || {}).edit)
      // Вердикт первичной проверки — отдельное действие: его можно развести с
      // ведением комплектов, чтобы подписывался не тот, кто грузил материал.
      setCanApprove(localStorage.getItem('is_admin') === 'true' || !!(p.creatives || {}).approve)
    } catch { setCanEdit(false); setCanApprove(false) }
    setLoading(true)
    api.get(`/sales/deals/${id}`, auth())
      .then(r => setDeal(r.data))
      .catch(e => setErr(e.response?.status === 404 ? 'Сделка не найдена' : (e.response?.data?.detail || 'Ошибка загрузки')))
      .finally(() => setLoading(false))
    api.get(`/sales/deals/${id}/history`, auth()).then(r => setHistory(r.data.items || [])).catch(() => {})
    api.get('/sales/directories/stage-catalog', auth()).then(r => setPhases(r.data.phases || [])).catch(() => {})
  }, [id])

  // Последний медиаплан сделки: берём свежий по версии и тянем полные данные
  // (строки/доп/таргетинг) — параметры кампании и размещение показываем из него.
  useEffect(() => {
    const list = (deal && deal.our_mps) || []
    if (!list.length) { setMp(null); return }
    const last = [...list].sort((a, b) => (b.version || 0) - (a.version || 0))[0]
    api.get(`/sales/media-plans/${last.id}`, auth())
      .then(r => setMp({ ...r.data, _head: last }))
      .catch(() => setMp(null))
  }, [deal && deal.our_mps && deal.our_mps.map(x => x.id).join(',')])

  // Данные размещения/прогноза/доп/таргетинга — из ПОСЛЕДНЕГО медиаплана сделки.
  // Формула строки повторяет бэкенд (_row_net): CPM — за 1000, иначе объём × цена.
  // Ставку НДС по нашим услугам задаёт юрлицо, от которого работаем (правило
  // владельца), а не константа в коде: зашитые 22 % пережили бы правку справочника
  // молча. Ноль и пусто здесь значат одно — «не задана»: своё юрлицо продаёт с НДС,
  // и ноль означает незаполненную карточку, а не ставку 0 %. Не задана — сумму с НДС
  // не выдумываем: прочерк и подсказка, где её задать. См. _own_company_out.
  const vatPct = (deal && deal.own_company && deal.own_company.vat_rate_income) || null
  const VAT = vatPct != null ? vatPct / 100 : null
  // До копеек: сумма строки считается до копеек (lib/mpRow), и округление здесь
  // разводило бы карточку с медиапланом и с подписанным документом.
  const withVat = (x) => (x == null || VAT == null ? null : Math.round(x * (1 + VAT) * 100) / 100)
  const vatHint = VAT != null ? '' :
    `Ставка НДС не задана в карточке «${(deal && deal.own_company && deal.own_company.name) || 'нашего юрлица'}» — Справочники → Контрагенты, поле «НДС приход». Пока не задана, суммы с НДС не считаются.`

  const mpRows = (mp && mp.rows) || []
  const hasMp = mpRows.length > 0
  const lines = mpRows.map(r => {
    // Сумма и показы — общей арифметикой строки (lib/mpRow), не своей копией: у Фикса
    // и Пакета в объёме лежат штуки закупки, и показы туда не годятся.
    const net = rowNet(r.model, r.volume, r.unit_price, r.discount)
    const fc = r.forecast || {}
    const nn = mpNum          // понимает десятичную запятую: аккаунт вводит «0,8»
    const imp = rowImp(r.model, r.volume, fc)
    const freq = nn(fc.freq)
    const reach = freq > 0 ? imp / freq : 0
    const clicks = rowClicks(r.model, r.volume, fc)
    return {
      position: r.position, format: r.format, model: r.model,
      volume: r.volume || 0, imp,
      inventory: r.inventory,
      unit: r.unit_price || 0, discount: r.discount || 0,
      net, gross: withVat(net), freq, reach, clicks,
      // Вторая половина прогноза — та, что раньше на карточку не доезжала. Формулы
      // повторяют конструктор МП дословно (components/mediaplan/MediaPlanBuilder.jsxx,
      // блок «Прогнозные показатели»): расхождение в них означало бы, что карточка и
      // медиаплан показывают разный прогноз по одним и тем же данным.
      cr: nn(fc.cr) / 100,
      checks: clicks * (nn(fc.cr) / 100),
      price: nn(fc.price),
      sov: nn(fc.sov),
    }
  })
  const withRoi = (r) => {
    const revenue = r.checks * r.price
    const gross = r.gross
    return { revenue, roi: gross > 0 ? (revenue - gross) / gross : NaN }
  }
  const tVol = lines.reduce((a, r) => a + r.volume, 0)      // объём: показы, штуки, клики
  const tImp = lines.reduce((a, r) => a + (r.imp || 0), 0)  // только показы
  const tNet = lines.reduce((a, r) => a + r.net, 0)
  const mpExtras = (mp && mp.extras) || []
  const extrasTotal = mpExtras.reduce((a, e) => a + (e.total || 0), 0)
  const MODE_LBL = { full: '100 %', half: '50 %', bonus: 'бонус' }
  // Таргетинг МП: {группа: [значения]} → плоские строки для вывода
  const TG_TITLES = { audience: 'Аудитория', buys: 'Покупают', interests: 'Интересы', behavior: 'Поведение', competitors: 'Конкуренты' }
  const mpTargeting = Object.entries((mp && mp.targeting) || {})
    .map(([g, arr]) => ({ group: TG_TITLES[g] || g, value: (arr || []).map(v => (typeof v === 'string' ? v : v && v.value)).filter(Boolean).join(' · ') }))
    .filter(x => x.value)

  const wrap = { minHeight: 'calc(100vh - 56px)', boxSizing: 'border-box', padding: '26px 32px 40px', background: 'var(--bg-canvas)', display: 'flex', justifyContent: 'flex-start', fontFamily: UI, color: 'var(--text-primary)' }

  if (loading) return <div style={wrap}><div style={{ color: 'var(--text-muted)', marginTop: 40 }}>Загрузка…</div></div>
  if (err) return <div style={wrap}><div style={{ marginTop: 40 }}><div style={{ color: 'var(--danger)', marginBottom: 12 }}>{err}</div><Link href="/sales/deals" style={{ color: 'var(--accent)' }}>← к реестру сделок</Link></div></div>

  const d = deal
  // Видимость блоков карточки считает бэкенд (app/sales/stage_scope.py): там же лежат
  // три правила — появился и не исчезает, непустое не прячем, нет разметки = видно
  // всегда. Отсутствие ответа (старый кэш, ошибка) показывает ВСЁ: спрятать карточку
  // из-за неполученного поля хуже, чем показать лишний пустой блок.
  const showBlock = (key) => d.card_blocks ? d.card_blocks[key] !== false : true
  const title = [d.advertiser, d.brand].filter(Boolean).join(' · ') || d.title || '—'
  // Услуга с поверхностью (WEB/APP у услуг с раздельным прайсом) — тем же помощником,
  // что в реестрах и на доске: сервер отдаёт `inventory` только там, где метка нужна.
  const svc = productWithSurface(d.product, d.inventory)
  const meta = [d.agency, svc, d.period, d.account_manager && `аккаунт ${d.account_manager}`, d.sales_rep && `продавец ${d.sales_rep}`].filter(Boolean).join(' · ')
  const metaShort = [d.agency, svc, d.period].filter(Boolean).join(' · ')
  const stageDays = daysInStage(d.stage_since)
  const dateVal = (x) => (x ? String(x).slice(0, 10) : '')

  // Цепочка стадий = все нетерминальные стадии каталога по порядку этапов.
  // Терминалы («не случилась» / «сорвалась») в цепочку не входят — они её обрывают.
  const chain = phases.flatMap(ph => (ph.stages || [])
    .filter(s => !s.is_terminal)
    .map(s => ({ ...s, phaseName: ph.name })))
  const curIdx = chain.findIndex(s => s.id === (d.our_stage && d.our_stage.id))
  const isLost = !!(d.our_stage && d.our_stage.is_terminal)

  // Деньги сделки. ИСТОЧНИК ИСТИНЫ — прикреплённый медиаплан: там актуальные строки
  // и доп. услуги (бонусная доп. услуга = 0, поэтому сумма сделки, посчитанная при
  // создании, может расходиться). Нет МП — показываем сумму, введённую при создании.
  // Формула итога повторяет конструктор МП: размещения + доп. услуги (grandNet).
  const netFromMp = hasMp ? tNet + extrasTotal : null
  const net = netFromMp != null ? netFromMp : (d.amount != null ? +d.amount : null)
  const gross = netFromMp != null
    ? withVat(netFromMp)
    : (d.amount_with_vat != null ? +d.amount_with_vat
      : (d.amount != null ? withVat(d.amount) : null))

  // Документы: карта по виду + счётчик готовых (МП считаем отдельной позицией)
  const fileBy = Object.fromEntries((d.files || []).map(f => [f.kind, f]))
  // ДС считается готовым по ВЫПУЩЕННОМУ приложению, а не по файлу: файла у него больше
  // нет вовсе. Черновик не в счёт — номер не занят, документ клиенту не уходил.
  const annex = (d.annexes || [])[0]
  const docsReady = DOC_KINDS.filter(([k]) => (k === 'ds' ? annex && !annex.is_draft : fileBy[k])).length
    + (mp ? 1 : 0)

  // скачивание/загрузка/удаление документов — общие хелперы (lib/dealDocs)
  const blobGet = downloadBlob
  const pickAndUpload = (kind) => pickAndUploadDoc(d.id, kind, reload, setDocBusy)

  // Кнопка «Создать» у доп. соглашения: черновик собирается из самой сделки (плательщик
  // даёт договор, медиаплан — период, сделка — сумму), и человек сразу оказывается на
  // экране сборки. Спрашивать это формой значило бы просить ввести то, что уже известно.
  const createAnnex = async () => {
    setDocBusy('ds')
    try {
      const r = await api.post(`/annexes/from-deal/${d.id}`, {}, auth())
      router.push(`/directory/annexes/${r.data.id}`)
    } catch (e) {
      alert(e.response?.data?.detail || 'Не удалось создать доп. соглашение')
    } finally { setDocBusy('') }
  }
  const removeDoc = (kind) => deleteDoc(d.id, kind, reload, setDocBusy)

  // Порядок = колонки свёрнутой сетки (3×2, заполнение по столбцам): кто рекламируется,
  // через кого продано, когда и где. Пара в столбце — связанные вопросы, а не соседи
  // по алфавиту.
  const params = [
    ['Рекламодатель', d.advertiser], ['Бренд', d.brand],
    ['Агентство', d.agency], ['Контрагент', d.payer],
    // Гео приходит с бэкенда из шапки медиаплана — своего поля у сделки нет.
    // Здесь стоял ЗАШИТЫЙ прочерк: строка «Гео —» рисовалась всегда, чем бы ни был
    // заполнен план (жалоба владельца 15.09.2026, данные при этом были на месте).
    ['Период размещения', d.period ? `месяц · ${d.period}` : '—'], ['Гео', d.geo || '—'],
  ]
  const team = [
    { name: d.sales_rep, role: 'Продавец', bg: 'var(--accent-tint)', fg: 'var(--accent)' },
    { name: d.account_manager, role: 'Аккаунт', bg: 'var(--income-tint)', fg: 'var(--income)' },
    { name: d.traffic_manager, role: 'Трафик', bg: 'var(--mixed-tint)', fg: 'var(--mixed)',
      onPick: canEdit ? openTraffic : null },
  ]
  const links = [
    { name: `Контрагент ${d.payer || ''}`.trim(), href: d.counterparty_id ? `/directory/counterparties/${d.counterparty_id}` : null, dot: 'var(--accent)' },
    { name: 'Медиаплан', href: null, dot: 'var(--income)' },
    { name: 'Сделка в Битриксе', href: (d.bitrix_id && !String(d.bitrix_id).startsWith('local-')) ? BITRIX_DEAL_URL(d.bitrix_id) : null, dot: 'var(--bank-cash)' },
    { name: `Дебиторка ${rub(d.amount)}`, href: '/finance/receivables', dot: 'var(--dot-current-dz)' },
  ]

  // ── МОБИЛЬНАЯ ВЕРСИЯ ──
  if (isMobile) {
    return (
      <>
        <Head><title>{d.code || d.bitrix_id || d.id} · {title} | SIMB-AD ERP</title></Head>
        <Navbar />
        {moveOpen && (
          <MoveDealDialog onCard deal={d} onClose={() => setMoveOpen(false)}
            onMoved={(patch) => { setMoveOpen(false); setDeal(x => ({ ...x, ...patch })); reload() }} />
        )}
        <DealCardMobile
          deal={d} chain={chain} curIdx={curIdx} isLost={isLost}
          net={net} gross={gross} vat={VAT}
          lines={lines} tVol={tVol} tImp={tImp} tNet={tNet}
          mpExtras={mpExtras} extrasTotal={extrasTotal}
          mp={mp} hasMp={hasMp} canEdit={canEdit} canApprove={canApprove}
          onBack={() => router.push('/sales/deals')}
          onMove={() => setMoveOpen(true)} />
      </>
    )
  }

  return (
    <>
      <Head><title>{d.code || d.bitrix_id || d.id} · {title} | SIMB-AD ERP</title></Head>
      {/* Стандартная шапка приложения: на карточке сделки её не было, из-за чего
          со страницы нельзя было уйти иначе как ссылкой «к реестру». */}
      <Navbar />
      {moveOpen && (
        <MoveDealDialog onCard deal={d} onClose={() => setMoveOpen(false)}
          onMoved={(patch) => { setMoveOpen(false); setDeal(x => ({ ...x, ...patch })); reload() }} />
      )}
      {promoAsk && (
        <Ask title="Перевести размещение в «саморекламу»?"
          text="После подтверждения снять статус сможет только мастер или админ. Признак меняет цепочку маркировки: в ОРД у саморекламы свой тип договора, а креатив выпускается с обязательной отметкой."
          onYes={() => applySelfPromo(true)} onNo={() => setPromoAsk(false)} />
      )}
      {briefOpen && <BriefDialog dealId={d.id} canEdit={canEdit} onClose={() => setBriefOpen(false)} />}
      {tmPop && (
        <ValuePopover anchor={tmPop.rect} title="Ответственный трафик"
          dealLabel={d.code || null} value={d.traffic_manager_user_id}
          clearLabel="— не назначен —"
          options={(tmList || []).map(t => ({ value: t.user_id, label: t.name }))}
          onPick={pickTraffic} onClose={() => setTmPop(null)} />
      )}
      <div style={wrap}>
        {/* Ширина под монитор 1600: 1520 = 1600 − поля обёртки (32+32) − запас под полосу
            прокрутки. Под 1920 (1840) оказалось широковато — строки текста в секциях
            растягивались до нечитаемых. На меньших экранах контейнер просто сжимается:
            это потолок, а не жёсткий размер. */}
        <div style={{ width: '100%', maxWidth: 1520, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* назад */}
          {/* `alignSelf` и `width: fit-content` обязательны: колонка — флекс, и ссылка
              без них растягивается во ВСЮ ширину страницы. Кликабельной становится вся
              полоса, и она перехватывает клики по выпадающему меню в шапке — со стороны
              это выглядит как «меню не работает». */}
          <Link href="/sales/deals" style={{ alignSelf: 'flex-start', width: 'fit-content',
            fontSize: 12.5, color: 'var(--text-muted)' }}>← к реестру сделок</Link>

          {/* ── Шапка ── */}
          {/* id — якорь для ссылок «где это чинится» из списка требований. Соглашение
              то же, что у сворачиваемых секций: `sec-<имя>`. */}
          <div id="sec-head" style={{ ...CARD, padding: '22px 26px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
              {/* Код, название и мета — одна базовая линия. Мета MONO капсом: это
                  адресная строка сделки, а не текст. Люди из неё убраны намеренно —
                  они и так стоят в «Ответственных» справа. */}
              <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 10, minWidth: 0, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>{d.code || d.bitrix_id || d.id}</span>
                <span style={{ fontSize: 21, fontWeight: 700, letterSpacing: '-0.02em' }}>{title}</span>
                <span style={{ ...SUBCAPS, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {metaShort || '—'}
                </span>
              </span>
              <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <button type="button" onClick={() => setBriefOpen(true)} title="Бриф сделки"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--bg-card)',
                    border: '1px solid var(--border-card)', color: 'var(--text-secondary)', borderRadius: 10,
                    padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>
                  <DocIcon />Бриф
                </button>
                {/* Самореклама — в шапке, рядом со стадией: признак управляет движением
                    сделки (в ОРД у неё свой тип договора, у креатива обязательная
                    отметка), поэтому читается всегда, а не только когда развёрнут
                    медиаплан. Решение владельца — унести её из блока МП. */}
                <SelfPromoChip on={!!d.is_self_promo} canEdit={canEdit}
                  canUnset={!!d.can_unset_self_promo} onToggle={toggleSelfPromo} />
                {!!d.bitrix_stage && (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--warning-tint)', color: 'var(--warning-text)', borderRadius: 10, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--warning)' }} />{d.bitrix_stage}
                  </span>
                )}
              </span>
              {/* Отказ бэкенда показываем в шапке, а не alert-ом: он относится к чипу
                  рядом, и его должно быть видно вместе с тем, что не изменилось. */}
              {!!promoErr && (
                <span style={{ flex: '1 1 100%', fontSize: 12.5, color: 'var(--danger)' }}>{promoErr}</span>
              )}
            </div>


            {/* Шапка денег: слева всегда суммы, справа — плашка годового плана.
                Две зоны, чтобы плашка не «уезжала» под суммы при их количестве. */}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 20, paddingTop: 2, flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 420px', minWidth: 0, display: 'flex', alignItems: 'flex-end', gap: 26, flexWrap: 'wrap' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>Сумма сделки · с НДС · {hasMp ? 'по медиаплану' : 'при создании сделки'}</span>
                <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, whiteSpace: 'nowrap' }}>{rub(gross)}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>Клиентская цена до НДС</span>
                <span style={{ fontFamily: MONO, fontSize: 21, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{rub(net)}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL} title={vatHint}>
                  {VAT != null ? `НДС ${Math.round(VAT * 100)} %` : 'НДС — ставка не задана'}
                </span>
                <span style={{ fontFamily: MONO, fontSize: 21, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                  {gross != null && net != null ? rub(Math.round((gross - net) * 100) / 100) : '—'}
                </span>
              </span>
              {/* Период размещения вместо срока оплаты: срок брать неоткуда — привязки
                  платежей к сделке ещё нет, и прочерк на видном месте место занимал,
                  а не сообщал. Период — то, что действительно известно. */}
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>Период размещения</span>
                <span style={{ fontFamily: MONO, fontSize: 21, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                  {d.period || (d.period_from ? `${ru(d.period_from)} — ${ru(d.period_to)}` : '—')}
                </span>
              </span>
            </div>
              {/* Материнский годовой план — правая зона шапки */}
              {d.year_plan && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto', maxWidth: 420, minWidth: 0, background: 'var(--bg-subtle, var(--bg-tint))', border: '1px solid var(--border-card)', borderRadius: 12, padding: '8px 12px' }}>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontFamily: MONO, fontSize: 9, letterSpacing: '.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Годовой план</span>
                    <span style={{ display: 'block', fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={[d.year_plan.title, d.year_plan.comment].filter(Boolean).join(' · ')}>
                      {d.year_plan.title || `План ${d.year_plan.year || ''}`}
                      {d.year_plan.comment ? <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}> · {d.year_plan.comment}</span> : null}
                      {d.year_plan.month != null ? <span style={{ fontFamily: MONO, fontWeight: 600, color: 'var(--text-faint)' }}> · мес. {d.year_plan.month + 1}</span> : null}
                    </span>
                  </span>
                  <a href={`/sales/year-plan?year=${d.year_plan.year}${d.year_plan.rep_id ? `&rep=${d.year_plan.rep_id}` : ''}`}
                    title="Открыть годовой план"
                    style={{ display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 11px', borderRadius: 8, background: 'var(--accent-tint)', border: '1px solid var(--accent)', color: 'var(--accent)', fontSize: 11.5, fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap', flex: '0 0 auto' }}>
                    План →
                  </a>
                </span>
              )}
            </div>

            {/* ── Бар стадий: вся цепочка каталога, цвет ячейки — по слою денег стадии.
                   Текущая подписана полным названием и растянута; прошедшие — в цвете,
                   будущие — приглушённые. Терминал (не случилась / сорвалась) — красный штрих. */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 420px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {isLost ? (
                <span title={d.our_stage?.name || 'Сделка провалена'}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 22, borderRadius: 6, background: HATCH_RED, border: '1px solid var(--danger)' }}>
                  <span style={{ fontSize: 11.5, fontWeight: 800, color: 'var(--danger)', letterSpacing: '.02em', background: 'var(--bg-card)', padding: '1px 10px', borderRadius: 6 }}>
                    {d.our_stage?.name || 'Сделка провалена'}
                  </span>
                </span>
              ) : (
                /* Тонкая полоса без подписей внутри: название текущей стадии стоит в
                   строке под ней, и дублировать его в ячейке значило бы отдать высоту
                   тексту, который уже прочитан. Цвет один — путь важнее слоя денег;
                   слой остаётся в подсказке при наведении. */
                <span style={{ display: 'flex', gap: 4, alignItems: 'stretch' }}>
                  {chain.length === 0 && <span style={{ flex: 1, height: 8, borderRadius: 4, background: 'var(--border-inner)' }} />}
                  {chain.map((s, i) => {
                    const cur = curIdx >= 0 && i === curIdx
                    const past = curIdx >= 0 && i < curIdx
                    return (
                      <span key={s.id} title={`${s.name}${s.phaseName ? ' · ' + s.phaseName : ''}`}
                        style={{
                          flex: cur ? '2 1 0' : '1 1 0', minWidth: 6, height: 8, borderRadius: 4,
                          background: cur ? 'var(--accent)' : past ? 'var(--accent-border)' : 'var(--border-inner)',
                          transition: 'flex .25s cubic-bezier(0.22,1,0.36,1)',
                        }} />
                    )
                  })}
                </span>
              )}

              {/* Подпись под полосой: где сделка, сколько тут стоит и что дальше. */}
              {!isLost && curIdx >= 0 && (
              <div style={{ fontSize: 11.5, color: 'var(--text-faint)', display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  стадия {curIdx + 1} из {chain.length}
                </span>
                <b style={{ fontSize: 13, color: 'var(--text-primary)' }}>{d.our_stage?.name}</b>
                {stageDays != null && <span>в стадии {plDays(stageDays)}</span>}
                {!!d.our_next_stage?.name && <span>· следующая: {d.our_next_stage.name}</span>}
              </div>
              )}

              {/* Чего не хватает для следующего шага — ДО нажатия кнопки. Показываем
                  только невыполненное: полный список с галочками на каждой карточке
                  превращается в шум, а «чего не хватает» читается за секунду. */}
              {!isLost && !!(nextReq?.lines || []).some(l => l.state !== 'ok') && (
                <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 10,
                  background: nextReq.allowed ? 'var(--bg-subtle)' : 'var(--danger-tint)',
                  border: `1px solid ${nextReq.allowed ? 'var(--border-card)' : 'var(--danger-border)'}` }}>
                  <StageRequirements
                    onCard
                    lines={nextReq.lines.filter(l => l.state !== 'ok')}
                    title={nextReq.allowed
                      ? `Для перехода в «${nextReq.target?.name || '—'}»`
                      : `Не пускает в «${nextReq.target?.name || '—'}»`} />
                </div>
              )}
              </div>

              {canEdit && (
                <button onClick={() => setMoveOpen(true)} title="Двинуть сделку по каталогу стадий"
                  style={{ display: 'inline-flex', alignItems: 'center', height: 38, padding: '0 18px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: 'var(--bg-card)', fontSize: 13, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap', flex: '0 0 auto', fontFamily: UI }}>
                  Изменить стадию
                </button>
              )}
            </div>
          </div>

          {/* ── Две колонки ── */}
          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }}>

            {/* Левая (центральная) колонка — три виджета. Решение владельца 2026-08-25:
                отдельного экрана сборки нет, разделы живут секциями на карточке и
                сворачиваются; свёрнутый вид несёт данные, а не подпись. */}
            <div style={{ flex: 1, minWidth: 320, display: 'flex', flexDirection: 'column', gap: 14 }}>

              <div style={{ ...CARD, padding: '20px 26px 18px' }}>
              <Section id="mp" dealId={id} title="Медиаплан сделки" defaultOpen={false}
                facts={mpFacts({ d, lines, net, gross, tImp, mp })}
                right={<span style={SUBCAPS}>{mpSummary(mpRows.length, net, mp)}</span>}>
                {() => (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

              {/* параметры кампании */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Параметры кампании</span>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={SUBCAPS}>Старт — стоп РК</span>
                    <input type="date" defaultValue={dateVal(d.period_from)} readOnly style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: MONO, fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', outline: 'none' }} />
                    <span style={{ color: 'var(--border-hover)' }}>→</span>
                    <input type="date" defaultValue={dateVal(d.period_to)} readOnly style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: MONO, fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', outline: 'none' }} />
                  </span>
                </div>
                {/* Сводка сделки — плашкой, как «Услуги от» справа: те же подложка,
                    рамка и скругление. Это реквизиты, а не сам медиаплан, и без визуальной
                    границы они читались как первые строки размещения. */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: 'repeat(2,auto)', gridAutoFlow: 'column', gap: '0 28px',
                  background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
                  borderRadius: 12, padding: '4px 14px 8px' }}>
                  {params.map(([label, value], i) => (
                    <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderTop: i % 2 ? '1px solid var(--border-row)' : 'none' }}>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 600, textAlign: 'right', color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>{value || '—'}</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Медиаплана нет — вся зона медиаплана становится кнопкой создания.
                  Есть МП — обычный блок размещения из его строк. */}
              {!mp ? (
                <div onClick={canEdit ? () => router.push(`/accounts/mp/new?deal=${d.id}`) : undefined}
                  title={canEdit ? 'Создать медиаплан — реквизиты и бриф подставятся из сделки' : 'Медиаплана нет'}
                  style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6,
                    minHeight: 150, padding: '28px 20px', marginTop: 14, borderRadius: 14,
                    background: canEdit ? 'var(--accent)' : 'var(--bg-subtle)',
                    color: canEdit ? 'var(--bg-card)' : 'var(--text-faint)',
                    border: canEdit ? 'none' : '1px dashed var(--border-card)',
                    cursor: canEdit ? 'pointer' : 'default', textAlign: 'center',
                  }}>
                  {canEdit && (
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14" /></svg>
                  )}
                  <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}>
                    {canEdit ? 'Создать медиаплан' : 'Медиаплана нет'}
                  </span>
                  <span style={{ fontSize: 12, opacity: canEdit ? 0.85 : 1 }}>
                    {canEdit
                      ? 'Рекламодатель, бренд, агентство, юрлицо и период подставятся из сделки'
                      : 'Размещение и прогноз появятся, когда его создадут'}
                  </span>
                </div>
              ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7, padding: '14px 0', borderTop: '1px solid var(--border-card)', borderBottom: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  {/* Только заголовок: реквизиты, версия, статус, гео и период уже стоят
                      выше — в шапке блока и в плашке параметров. Дубль читался как
                      отдельная информация, хотя ничего не добавлял. */}
                  <span style={CAPS}>Размещение</span>
                  <a href={`/accounts/mp/${mp.id}`} style={{ marginLeft: 'auto', fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none', whiteSpace: 'nowrap' }}>Открыть МП →</a>
                </div>
                {!hasMp && <div style={{ fontSize: 12, color: 'var(--text-faint)', padding: '6px 0' }}>В медиаплане пока нет строк размещения.</div>}
                {hasMp && (
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ minWidth: 640 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                      <span>Позиция</span><span>Формат</span><span>Инвентарь</span><span>Модель</span><span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Цена/ед.</span><span style={{ textAlign: 'right' }}>Скидка</span><span style={{ textAlign: 'right' }}>До НДС</span><span style={{ textAlign: 'right' }}>С НДС</span>
                    </div>
                    {lines.map((l, i) => (
                      <div key={i} style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                        <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25 }}>{l.position}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{l.format}</span>
                        <span style={{ fontFamily: MONO, fontSize: 10.5,
                          color: l.inventory ? 'var(--text-secondary)' : 'var(--text-faint)',
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {INV_LABEL[l.inventory] || '—'}
                        </span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>{l.model}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>{num(l.volume)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{dec(l.unit)} ₽</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textAlign: 'right' }}>{Math.round((l.discount || 0) * 100)} %</span>
                        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{rub(l.net)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{rub(l.gross)}</span>
                      </div>
                    ))}
                    <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', paddingTop: 7 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого</span>
                      <span /><span /><span />
                      <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, textAlign: 'right' }}>{num(tVol)}</span>
                      <span /><span />
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{rub(tNet)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{rub(withVat(tNet))}</span>
                    </div>
                  </div>
                </div>
                )}
              </div>
              )}

              {/* прогнозные показатели — из медиаплана */}
              {hasMp && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Прогнозные показатели</span>
                  <span style={SUBCAPS}>гарантируются показы и CPM</span>
                </div>
                {/* Прокрутка осталась страховкой для узких экранов, но минимум опущен
                    до реально нужного: на мониторе, под который свёрстана карточка,
                    таблица помещается целиком и полоса не появляется. */}
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ minWidth: 1165 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: FC_GAP, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                      <span>Строка</span>
                      {FC_HEADS.map(h => (
                        <span key={h} style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>{h}</span>
                      ))}
                    </div>
                    {lines.map((r, i) => (
                      <div key={i} style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: FC_GAP, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                        <span title={r.position} style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25, overflow: 'hidden' }}>{r.position}</span>
                        <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.freq ? num(r.freq) : '—'}</span>
                        <span style={FC_NUM}>{r.reach ? num(Math.round(r.reach)) : '—'}</span>
                        {/* ПОКАЗЫ (r.imp), а не объём строки: у Фикса и Пакета объём это
                            штуки закупки — CPM от них выходил в миллионы рублей. */}
                        <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--income)' }}>{r.imp ? num(r.imp) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.imp && r.clicks ? dec(r.clicks / r.imp * 100) : '—'}</span>
                        <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--income)' }}>{r.clicks ? num(Math.round(r.clicks)) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--accent)' }}>{r.imp ? dec(r.net / r.imp * 1000) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--accent)' }}>{r.clicks ? dec(r.net / r.clicks) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--accent)' }}>{r.reach ? dec(r.net / r.reach) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.cr ? dec(r.cr * 100) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.checks ? num(Math.round(r.checks)) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--accent)' }}>{r.checks ? dec(r.net / r.checks) : '—'}</span>
                        <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.price ? dec(r.price) : '—'}</span>
                        <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--income)' }}>{withRoi(r).revenue ? dec(withRoi(r).revenue) : '—'}</span>
                        <span style={{ ...FC_NUM, fontWeight: 700,
                          color: withRoi(r).roi >= 0 ? 'var(--income)' : 'var(--dot-overdue)' }}>
                          {Number.isFinite(withRoi(r).roi)
                            ? `${withRoi(r).roi >= 0 ? '+' : '−'}${Math.abs(withRoi(r).roi * 100).toFixed(0)}` : '—'}
                        </span>
                        <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.sov ? dec(r.sov) : '—'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              )}

              {/* доп. услуги — из медиаплана */}
              {mpExtras.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
                <span style={CAPS}>Дополнительные услуги</span>
                {mpExtras.map((e, i) => (
                  <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                    <span style={{ fontSize: 11.5, fontWeight: 600 }}>{e.name || '—'}</span>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{e.period || ''}{e.mode ? ` · ${MODE_LBL[e.mode] || e.mode}` : ''}</span>
                    <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textDecoration: (e.total || 0) < (e.price || 0) ? 'line-through' : 'none' }}>{rub(e.price || 0)}</span>
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--income)', minWidth: 96, textAlign: 'right' }}>{rub(e.total || 0)}</span>
                    {/* цена с НДС — от «итого» (что в счёте), а не от прайса */}
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)', minWidth: 104, textAlign: 'right' }}>{rub(withVat(e.total || 0))}</span>
                  </span>
                ))}
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 12, paddingTop: 7 }}>
                  <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого доп. услуги · входят в сумму сделки</span>
                  <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--income)' }}>{rub(extrasTotal)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--accent)', minWidth: 104, textAlign: 'right' }}>{rub(withVat(extrasTotal))}</span>
                </span>
              </div>
              )}

              {/* бриф · таргетинг — из медиаплана */}
              {mpTargeting.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                  <span style={CAPS}>Бриф · таргетинг</span>
                  <span style={{ marginLeft: 'auto', ...SUBCAPS }}>из медиаплана</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
                  {mpTargeting.map((t, i) => (
                    <span key={i} style={{ display: 'flex', gap: 12, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                      <span style={{ flex: '0 0 84px', fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', lineHeight: 1.45 }}>{t.group}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{t.value}</span>
                    </span>
                  ))}
                </div>
              </div>
              )}
                </div>
                )}
              </Section>
              </div>

              {showBlock('ord') && (
              <div style={{ ...CARD, padding: '20px 26px 18px' }}>
              <Section id="ord" dealId={id} title="ОРД" subtitle="цепочка договоров и ЕРИД"
                defaultOpen summary={ordSummaryText(ordSummary).text}
                tone={ordSummaryText(ordSummary).tone} facts={ordFacts(ordSummary)}
                factsAs="chips" right={<OrdPips assembly={ordSummary} />}>
                {() => <AssemblyOrd dealId={d.id} data={ordSummary} err={ordErr}
                  canEdit={canEdit} onReload={loadOrd} />}
              </Section>
              </div>
              )}

              {/* Передача РК аккаунт → трафик. Стоит ПЕРЕД креативами: сначала «что и
                  зачем крутим», потом «чем крутим». */}
              {showBlock('traffic-brief') && (
              <div style={{ ...CARD, padding: '20px 26px 18px' }}>
              <Section id="traffic-brief" dealId={id} title="Цели и особенности РК"
                subtitle="что аккаунт передаёт трафику" defaultOpen={false}
                summary={(deal.traffic_brief || '').trim()
                  ? (deal.traffic_brief.trim().length > 90
                    ? deal.traffic_brief.trim().slice(0, 90) + '…' : deal.traffic_brief.trim())
                  : 'не заполнено'}
                tone={(deal.traffic_brief || '').trim() ? 'ok' : 'warn'}>
                {() => (
                  <TrafficBrief dealId={d.id} value={deal.traffic_brief} canEdit={canEdit}
                    onSaved={v => setDeal(x => ({ ...x, traffic_brief: v }))} />
                )}
              </Section>
              </div>
              )}

              {showBlock('campaign-extra') && (
              <div style={{ ...CARD, padding: '20px 26px 18px' }}>
              {/* РАЗВЁРНУТ, ПОКА ВЫБОР НЕ СДЕЛАН (владелец 18.09.2026). Свёрнутый блок
                  с подписью «пиксель не заказан» читался как принятое решение, хотя
                  решения не было: умолчание колонки и осознанное «не надо» выглядели
                  одинаково. Теперь различие хранится (`weborama_pixel_decided_at`), и
                  блок сам просит закрыть вопрос. */}
              <Section id="campaign-extra" dealId={id} title="Доп. параметры РК"
                subtitle="что включено по этой кампании"
                defaultOpen={!deal.weborama_pixel_decided}
                summary={!deal.weborama_pixel_decided
                  ? 'по пикселю Weborama решение не принято'
                  : (deal.weborama_pixel ? 'пиксель Weborama заказан'
                    : 'пиксель Weborama не нужен')}
                tone={!deal.weborama_pixel_decided ? 'warn'
                  : (deal.weborama_pixel ? 'ok' : undefined)}>
                {() => (
                  <CampaignExtra dealId={d.id} deal={deal} canEdit={canEdit}
                    onSaved={v => setDeal(x => ({ ...x, ...v }))} />
                )}
              </Section>
              </div>
              )}

              {showBlock('creatives') && (
              <div style={{ ...CARD, padding: '20px 26px 18px' }}>
              <Section id="creatives" dealId={id} title="Креативы" defaultOpen={false}
                summary={creativesSummary(creatives).text}
                tone={creativesSummary(creatives).tone}
                right={creatives && creatives.sets && creatives.sets.length ? (
                  <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700,
                    color: 'var(--text-secondary)' }}>{creatives.sets.length} в работе</span>
                ) : null}
                collapsed={<CreativesSummary data={creatives} canApprove={canApprove}
                  onReviewed={onCreativesChanged} />}>
                {() => (
                  <AssemblyCreatives dealId={d.id} canEdit={canEdit} canApprove={canApprove}
                    isAdmin={isAdmin} onChanged={onCreativesChanged} />
                )}
              </Section>

              </div>
              )}

              {/* Ход открутки — СВОЯ карточка после креативов, а не хвост внутри них:
                  собрали материал, отправили, дальше живёт кампания, и это отдельная
                  сущность. Карточка появляется сама, когда пошла статистика, и до
                  этого не рисует ни рамки (см. CampaignSummary). Тот же компонент
                  поедет на предварительную сверку. */}
              {showBlock('campaign') && (
                <CampaignSummary dealId={d.id} cardStyle={{ ...CARD, padding: '20px 26px 18px' }} />
              )}
            </div>

            {/* правая: документы / ответственные / история */}
            {/* Правая колонка — ФИКСИРОВАННЫЕ 280 px, а не 25 %. Доля растянула бы её
                вместе со страницей до 460, а там документы, ответственные и история:
                им ширина не нужна, нужна центральной. 280 — ровно то, чем колонка была
                при прежних 1120, так что на глаз она не изменилась. */}
            <div id="sec-docs" style={{ width: 280, flex: '0 0 280px', ...CARD, padding: '20px 22px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* Блок «Документы» внутри правой колонки: саму колонку не прячем — в ней
                  живут ещё ответственные и история, нужные с первой стадии. */}
              {/* От какого юрлица оказываем услуги. Сегодня оно одно и берётся из
                  справочника (см. _own_company_out), выбора на сделке нет — но стоит
                  отдельно и явно: оно задаёт ставку НДС по нашим услугам, и здесь же
                  появится выбор, когда юрлиц станет несколько. */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6,
                background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
                borderRadius: 12, padding: '10px 12px' }}>
                <span style={SUBCAPS}>Услуги от</span>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700,
                  color: 'var(--text-primary)', lineHeight: 1.3 }}>
                  {(deal && deal.own_company && deal.own_company.name) || 'юрлицо не определено'}
                </span>
                <span title={vatHint} style={{ fontFamily: MONO, fontSize: 9,
                  letterSpacing: '.08em', textTransform: 'uppercase',
                  color: VAT != null ? 'var(--text-muted)' : 'var(--warning-text)' }}>
                  {VAT != null ? `НДС ${Math.round(VAT * 100)} %` : 'ставка НДС не задана'}
                </span>
              </div>

              {/* документы — реальные: файлы сделки + наш МП. Загрузка/замена/удаление. */}
              {showBlock('docs') && (<>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={CAPS}>Документы</span>
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, fontWeight: 700, color: 'var(--accent)' }}>{docsReady} из {DOC_KINDS.length + 1}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {/* наш медиаплан — отдельной строкой: скачать PDF/XLSX или открыть конструктор */}
                <DocRow ok={!!mp} title="Медиаплан"
                  meta={mp ? `v${mp.version}${mp.updated_at ? ' · ' + dm(mp.updated_at, '') : ''}` : 'не создан'}
                  right={mp ? (
                    <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                      <span onClick={() => downloadMp(mp, 'pdf')} style={DOC_ACT}>PDF</span>
                      <span onClick={() => downloadMp(mp, 'xlsx')} style={DOC_ACT}>XLS</span>
                      <a href={`/accounts/mp/${mp.id}`} style={{ ...DOC_ACT, textDecoration: 'none' }}>↗</a>
                    </span>
                  ) : (canEdit ? <a href={`/accounts/mp/new?deal=${d.id}`} style={{ ...DOC_ACT, textDecoration: 'none' }}>Создать</a> : null)} />

                {DOC_KINDS.map(([kind, label, fromBitrix]) => {
                  const f = fileBy[kind]
                  const busy = docBusy === kind
                  // ДС у нас не приносят файлом, а СОБИРАЮТ — поэтому строка ведёт себя
                  // как медиаплан: номер с датой и кнопки, а пока документа нет —
                  // «Создать», проваливающее в сборку. Загрузку файла для неё оставлять
                  // нельзя: два источника одного документа разъедутся, и какой из них
                  // ушёл клиенту, будет не установить.
                  if (kind === 'ds') {
                    const ann = annex
                    return (
                      <DocRow key={kind} ok={!!ann && !ann.is_draft} title={label}
                        meta={ann
                          ? `${ann.number || 'черновик'}${ann.date ? ' · ' + dm(ann.date, '') : ''}`
                          : 'не создано'}
                        right={ann ? (
                          <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                            <span onClick={() => blobGet(`/annexes/${ann.id}/pdf`, `${ann.number || 'ДС'}.pdf`)} style={DOC_ACT}>PDF</span>
                            <span onClick={() => blobGet(`/annexes/${ann.id}/docx`, `${ann.number || 'ДС'}.docx`)} style={DOC_ACT}>DOC</span>
                            <a href={`/directory/annexes/${ann.id}`} style={{ ...DOC_ACT, textDecoration: 'none' }}>↗</a>
                          </span>
                        ) : (canEdit ? (
                          <span onClick={createAnnex} style={DOC_ACT}>
                            {docBusy === 'ds' ? 'Создаю…' : 'Создать'}
                          </span>
                        ) : null)} />
                    )
                  }
                  return (
                    <DocRow key={kind} ok={!!f} title={label}
                      meta={busy ? 'загрузка…' : (f ? `${f.filename}${f.size ? ' · ' + Math.max(1, Math.round(f.size / 1024)) + ' КБ' : ''}` : (fromBitrix ? 'из Битрикса — нет' : 'не загружен'))}
                      right={
                        <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                          {f && <span onClick={() => blobGet(`/sales/deals/${d.id}/files/${kind}/download`, f.filename)} style={DOC_ACT}>⭳</span>}
                          {canEdit && !fromBitrix && (
                            <span onClick={() => pickAndUpload(kind)} style={DOC_ACT}>{f ? 'Заменить' : 'Загрузить'}</span>
                          )}
                          {canEdit && !fromBitrix && f && (
                            <span onClick={() => removeDoc(kind)} title="Удалить" style={{ ...DOC_ACT, color: 'var(--danger)', borderColor: 'var(--danger)' }}>×</span>
                          )}
                        </span>
                      } />
                  )
                })}
              </div>
              </>)}

              {/* ответственные */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                <span style={CAPS}>Ответственные</span>
                {team.map((t, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, background: t.bg, color: t.fg, fontSize: 12, fontWeight: 700, flex: '0 0 32px' }}>{initials(t.name)}</span>
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: t.name ? 'var(--text-primary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name || '—'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{t.role}</span>
                    </span>
                    {/* Назначаемая роль выглядит значением с пунктиром, а не полем ввода —
                        как остальные редактируемые значения в разделе продаж. */}
                    {t.onPick && (
                      <span onClick={t.onPick} title="Назначить ответственного за проверку материала"
                        style={{ marginLeft: 'auto', flex: '0 0 auto', cursor: 'pointer',
                          fontSize: 11, fontWeight: 700, color: 'var(--accent)',
                          borderBottom: '1px dashed var(--border-card)' }}>
                        {t.name ? 'сменить' : 'назначить'}
                      </span>
                    )}
                  </div>
                ))}
              </div>

              {/* история (реальная — audit_log) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={CAPS}>История</span>
                  {history.length > 6 && <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{history.length} событий</span>}
                </div>
                {/* Первые 6 событий видны сразу, остальные — в скролле. Высота считается
                    из строки события (≈56 px вместе с разделителем), а не подобрана на глаз:
                    поменяется вёрстка строки — поменять и здесь. */}
                {history.length ? (
                  <div style={history.length > 6 ? { maxHeight: 336, overflowY: 'auto', paddingRight: 4 } : undefined}>
                    {history.map((h, i) => (
                      <div key={i} style={{ display: 'flex', gap: 9, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: EVENT_COLOR[h.action] || 'var(--text-faint)', flex: '0 0 7px', marginTop: 5 }} />
                        <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                          <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.35 }}>{h.label}{h.details ? <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}> · {h.details}</span> : ''}</span>
                          <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{fmtWhen(h.at)}{h.who ? ` · ${h.who}` : ''}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : <div style={{ fontSize: 11, color: 'var(--text-faint)', padding: '4px 0' }}>Событий в журнале пока нет.</div>}
              </div>

              <DealComments dealId={d.id} canEdit={canEdit} />
            </div>
          </div>

          {/* ряд ссылок */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', padding: '0 6px' }}>
            {links.map((l, i) => (
              l.href
                ? <a key={i} href={l.href} target={l.href.startsWith('http') ? '_blank' : undefined} rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}><span style={{ width: 7, height: 7, borderRadius: 2, background: l.dot }} />{l.name}</a>
                : <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600, color: 'var(--text-faint)' }}><span style={{ width: 7, height: 7, borderRadius: 2, background: l.dot }} />{l.name}</span>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
