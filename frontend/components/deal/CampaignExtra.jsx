/**
 * «Доп. параметры РК» — пиксель Weborama по кампании (карточка сделки). Вынесен из pages/sales/deals/[id].js без изменений
 * 13.11.2026 — страница карточки и так перерастает 2000 строк.
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { detailText } from '@/lib/loadError'
import { MONO, UI, Modal } from '@/components/salesTableKit'
import { fmtDateOfMoment } from '@/lib/dates'

// ── Доп. параметры РК ──
// Блок-контейнер: сегодня в нём один параметр, но у него уже своё место в лестнице
// (между «Цели и особенности» и «Креативы») и своя подпись. Следующий параметр будет
// строкой здесь, а не новым блоком и не полем, приклеенным к соседнему смыслу.
//
// ВКЛЮЧЕНИЕ НЕОБРАТИМО для обычного аккаунта (владелец 14.09.2026): оно поднимает
// требование пикселя в выгрузке в DSP и рождает задачу трафику. Поэтому спрашиваем
// подтверждение модалкой, а не переключаем молча по клику.
export default function CampaignExtra({ dealId, deal, canEdit, onSaved }) {
  const [ask, setAsk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // Способ выбирается В МОДАЛКЕ, вместе с подтверждением: это часть одного решения,
  // а не отдельная настройка, которую можно переключить после.
  const [mode, setMode] = useState('own')
  const [tag, setTag] = useState('')
  const [ins, setIns] = useState('')
  // Ссылка на отчёт Weborama (05.11.2026): ляжет в РК, если она собрана; ответ сервера — словами под блоком
  const [reportUrl, setReportUrl] = useState('')
  const [note, setNote] = useState('')
  const on = !!deal.weborama_pixel
  const external = (deal.weborama_pixel_mode || 'own') === 'external'
  const canUnset = !!deal.can_unset_weborama_pixel
  const decided = !!deal.weborama_pixel_decided

  const send = (value) => {
    setBusy(true); setErr('')
    const body = value
      ? { weborama_pixel: true, mode, tag: mode === 'external' ? tag.trim() : null,
        insertion: mode === 'external' ? ins.trim() : null,
        report_url: mode === 'external' ? (reportUrl.trim() || null) : null }
      : { weborama_pixel: false }
    api.put(`/sales/deals/${dealId}/campaign-extra`, body, auth())
      .then(r => { setBusy(false); setAsk(false); setNote(r.data.report_url_note || ''); onSaved(r.data) })
      .catch(e => { setBusy(false); setErr(detailText(e, 'Не удалось сохранить')) })
  }

  const when = deal.weborama_pixel_at
    ? fmtDateOfMoment(deal.weborama_pixel_at)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {!!note && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Отчёт Weborama: {note}</span>}
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
                ? `Внешний тег${when ? ', загружен ' + when : ''}. Вставку завёл клиент — свою не заводим. Показы Weborama снимаются по ссылке клиента на отчёт (блок РК ниже), без ссылки — вносятся руками на сверке.`
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
                  кампанию: свою вставку заводить не будем. Показы Weborama снимем по ссылке
                  клиента на отчёт (ниже, можно вписать и позже); без ссылки — руками на сверке.
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
                {/* Ссылка на отчёт одной кампании — сервер проверит до сохранения (05.11.2026) */}
                <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Ссылка на отчёт Weborama · необязательно</span>
                  <input value={reportUrl} onChange={e => setReportUrl(e.target.value)}
                    placeholder="https://adap-interface.wbrm.ru/…/reportcenter/permalink/link/hash/…"
                    style={{ height: 32, fontFamily: MONO, fontSize: 11.5, padding: '0 9px', borderRadius: 8,
                      border: '1px solid var(--border-card)', background: 'var(--bg-card)',
                      color: 'var(--text-primary)', outline: 'none' }} />
                  <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                    постоянная ссылка клиента на отчёт ОДНОЙ кампании; РК ещё не собрана — впишете после сборки</span>
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
