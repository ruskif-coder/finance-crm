/**
 * Печатная форма приложения к договору.
 *
 * Одна страница на оба формата вывода: её печатает сайдкар headless-Chromium в нативный
 * PDF (тем же способом, что медиаплан), и её же человек видит в предпросмотре. Второй
 * вёрстки документа в проекте нет — расходиться нечему.
 *
 * Данные приходят двумя путями. В режиме сайдкара бэкенд инжектит их в `window.__ANNEX__`
 * ещё до скриптов страницы: браузеру не нужен ни токен, ни доступ к API, потому что
 * доступ уже проверил бэкенд, который единственный ходит в сайдкар. В обычном режиме
 * страница тянет их сама по id.
 *
 * Вёрстка — A4 с типографикой договора: Times, 12 пт, чёрным по белому. Тёмной темы тут
 * нет и быть не может: документ печатают на бумаге.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import api, { auth } from '@/lib/api'

const dm = (d) => {
  const s = String(d || '')
  return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : s
}

/** «600000.16» → «600 000.16» — как в документе: две цифры после точки, разряды пробелом. */
const fix2 = (v) => (v == null ? '—'
  : Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))

const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
  'августа', 'сентября', 'октября', 'ноября', 'декабря']

/** «31.05.2026» → ««31» мая 2026 г.» — форма даты в договорных документах. */
const longDate = (d) => {
  const s = String(d || '')
  if (s.length < 10) return s
  const day = Number(s.slice(8, 10))
  return `«${String(day).padStart(2, '0')}» ${MONTHS[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)} г.`
}

/** Сторона в шапке: «ООО «Ромашка», именуемое в дальнейшем «Заказчик», в лице …». */
/**
 * Сторона в шапке. Оборот «в лице …» требует РОДИТЕЛЬНОГО падежа, и падежные формы
 * приходят с сервера (`app/sales/rugram.py`) — там же, где их получит docx. Здесь
 * склонять нельзя: две реализации разошлись бы, и в двух форматах одного документа
 * стояли бы разные фамилии.
 */
const partyLine = (p, role) => {
  if (!p || !p.name) return `___________, именуемое в дальнейшем «${role}»`
  const pos = p.position_gen || p.position || '___________'
  const fio = p.director_gen || p.director || '___________'
  const basis = p.basis_gen || p.basis || '___________'
  return `${p.name}, именуемое в дальнейшем «${role}», в лице ${pos} ${fio}, `
    + `${p.acting || 'действующего'} на основании ${basis}`
}

export default function AnnexPrint() {
  const router = useRouter()
  const { id } = router.query
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.__ANNEX__) { setD(window.__ANNEX__); return }
    if (!id) return
    api.get(`/annexes/${id}`, auth())
      .then(r => setD(r.data.doc ? { ...r.data.doc, rows: r.data.rows || [] } : r.data))
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить приложение'))
  }, [id])

  // Флаг для сайдкара: он ждёт его, прежде чем печатать, — иначе в PDF уедет пустая
  // страница, пока данные ещё грузятся.
  useEffect(() => { if (d && typeof window !== 'undefined') window.__ANNEX_RENDERED__ = true }, [d])

  if (err) return <div style={{ padding: 40, fontFamily: 'Times New Roman, serif' }}>{err}</div>
  if (!d) return <div style={{ padding: 40, fontFamily: 'Times New Roman, serif' }}>Загрузка…</div>

  const rows = d.rows || []
  // Итоги считаются по строкам таблицы, а не берутся из шапки: если они разойдутся,
  // это видно сразу — значит строки и общая сумма собраны из разного.
  const totals = rows.reduce((a, r) => ({
    volume: a.volume + (r.volume || 0),
    net: a.net + (r.amount || 0),
    vat: a.vat + (r.vat || 0),
    gross: a.gross + (r.gross || 0),
  }), { volume: 0, net: 0, vat: 0, gross: 0 })
  const cust = d.customer || {}
  const exec = d.executor || {}

  return (
    <>
      <Head><title>{d.number || 'Приложение'}</title></Head>
      <style>{`
        /* Альбомная ориентация: в документе таблица медиаплана из семи колонок, и в
           портретной A4 она сжимается до нечитаемого. Сайдкар печатает с
           preferCSSPageSize, поэтому размер страницы задаётся здесь, а не в его коде —
           значит ориентация принадлежит документу, а не печатающему сервису. */
        @page { size: A4 landscape; margin: 15mm 16mm; }
        html, body { background: #fff; }
        .doc { font-family: 'Times New Roman', Times, serif; font-size: 11.5pt;
               line-height: 1.4; color: #000; max-width: 265mm; margin: 0 auto;
               padding: 8mm 0; text-align: justify; }
        .doc h1 { font-size: 12pt; font-weight: bold; text-align: center; margin: 0 0 2mm; }
        .doc .sub { text-align: center; margin: 0 0 6mm; }
        .row { display: flex; justify-content: space-between; margin-bottom: 6mm; }
        .doc p { margin: 0 0 3mm; text-indent: 0; }
        /* Нумерованный пункт: номер висит слева, текст выровнен по общей линии —
           так набраны пункты в подписанном образце, и по ЛЕВОМУ краю, а не по ширине
           (правило владельца 05.09.2026). Модификатор вложенного пункта называется
           lvl2, а не sub: селектор .doc .sub центрирует подзаголовок шапки и молча
           ловил бы пункты тоже — так они и уехали в центр. */
        .item { display: grid; grid-template-columns: 12mm 1fr; gap: 0;
                margin: 0 0 3mm; text-align: left; }
        .item.lvl2 { grid-template-columns: 12mm 1fr; padding-left: 8mm; }
        .item .n { font-weight: normal; }
        /* Шапка синяя с белым текстом — как в подписанном образце и в наших выгрузках
           медиаплана. Цвета здесь литералами, а не токенами: документ печатают на
           бумаге, темы у него нет, и var(--*) в PDF взять неоткуда. */
        table { width: 100%; border-collapse: collapse; margin: 4mm 0 5mm;
                font-size: 7.5pt; }
        /* Рамки белые — как в наших выгрузках медиаплана: разделители видны на
           заливке шапки и строки ИТОГО, а тело таблицы держится на самих заливках. */
        th, td { border: 1px solid #fff; padding: 1.2mm 1.5mm; vertical-align: middle; }
        th { background: #4472C4; color: #fff; font-weight: bold; text-align: center;
             font-size: 7pt; line-height: 1.15; }
        td { text-align: center; }
        td.pos { text-align: left; font-style: italic; font-size: 7pt; line-height: 1.2; }
        td.net { font-weight: bold; }
        td.num { text-align: right; white-space: nowrap; }
        tr.total td { background: #D9E2F3; font-weight: bold; }
        /* Стороны разводятся по противоположным краям листа: исполнитель прижат
           влево, заказчик вправо — так подписи не читаются как один общий блок. */
        .signs { display: flex; justify-content: space-between; align-items: flex-start;
                 gap: 10mm; margin-top: 10mm; page-break-inside: avoid; }
        .signs > div { width: 45%; text-align: left; }
        .signs > div:last-child { text-align: right; }
        .signs b { display: block; margin-bottom: 4mm; }
        .signs .line { margin-top: 8mm; }
        /* Номер договора не переносится по частям: «68/2026-МЗ» рвётся по слэшу и дефису,
           и в документе оказываются два разных на вид номера на двух строках. */
        .nb { white-space: nowrap; }
      `}</style>

      <div className="doc">
        <h1>{d.number || 'Приложение'}</h1>
        <div className="sub">
          к Договору <span className="nb">№ {d.contract?.number || '________'}</span>{' '}
          об оказании услуг от {longDate(d.contract?.date)}
        </div>

        <div className="row">
          <span>{d.signed_place || 'г. Москва'}</span>
          <span>{longDate(d.date)}</span>
        </div>

        <p className="flat">
          {partyLine(cust, 'Заказчик')}, с одной стороны, и {partyLine(exec, 'Исполнитель')},
          с другой стороны, заключили настоящее {d.number} к Договору{' '}
          <span className="nb">№ {d.contract?.number || '________'}</span> об оказании услуг
          от {longDate(d.contract?.date)} (далее по тексту – «Договор») о нижеследующем:
        </p>

        {/* Нумерация пунктов повторяет подписанный образец: 1 — предмет со ссылкой на
            медиаплан, 1.1 — стоимость, 1.2 — порядок оказания, 2 — доработки,
            3 — заключительные положения. В исходном docx часть номеров автоматические
            (списком Word), часть набрана руками — здесь они текстом, чтобы номер
            копировался вместе с пунктом и не зависел от рендерера. */}
        <div className="item">
          <span className="n">1.</span>
          <span>{d.body}</span>
        </div>

        {/* Медиаплан НАСТОЯЩЕЙ таблицей, а не картинкой из экселя, как в образце:
            суммы совпадают с базой по построению, и документ ищется текстом. Колонки —
            один в один с подписанным документом, включая «Место размещения» и «Тип
            ротации»; последняя пока пустая — такого поля у нас нет. */}
        {!!rows.length && (
          <table>
            <thead>
              <tr>
                <th>Место<br />размещения</th>
                <th style={{ width: '22%' }}>Позиция</th>
                <th>Гео</th><th>Формат</th><th>Девайс</th>
                <th>Тип ротации<br />(для медийных<br />форматов)</th>
                <th>Модель<br />закупки</th>
                <th>Объем размещения</th>
                <th>Период</th>
                <th>Стоимость<br />за единицу<br />закупки</th>
                <th>Стоимость<br />размещения</th>
                <th>НДС {d.vat_rate}%</th>
                <th>Стоимость<br />размещения<br />с учетом НДС</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 'bold' }}>{r.network || '—'}</td>
                  <td className="pos">
                    {r.doc_position || r.position || '—'}
                  </td>
                  <td>{r.geo || '—'}</td>
                  <td>{r.format || '—'}</td>
                  <td>{r.device || '—'}</td>
                  <td>{r.rotation || '—'}</td>
                  <td>{r.model || '—'}</td>
                  <td className="num">
                    {r.volume == null ? '—' : Number(r.volume).toLocaleString('ru-RU')}
                  </td>
                  <td>
                    {dm(r.date_from || d.period_from)} –<br />{dm(r.date_to || d.period_to)}
                  </td>
                  <td className="num">{fix2(r.unit_price)}</td>
                  <td className="num net">{fix2(r.amount)}</td>
                  <td className="num">{fix2(r.vat)}</td>
                  <td className="num net">{fix2(r.gross)}</td>
                </tr>
              ))}
              <tr className="total">
                <td colSpan={7}>ИТОГО:</td>
                <td className="num">{Number(totals.volume).toLocaleString('ru-RU')}</td>
                <td />
                <td />
                <td className="num">{fix2(totals.net)}</td>
                <td className="num">{fix2(totals.vat)}</td>
                <td className="num">{fix2(totals.gross)}</td>
              </tr>
            </tbody>
          </table>
        )}

        <div className="item lvl2">
          <span className="n">1.1.</span>
          <span>
          Общая стоимость Услуг Исполнителя по настоящему Приложению составляет сумму
          в размере {d.amount_words}, в том числе НДС {d.vat_rate}% — {d.vat_words}.
          Оплата услуг Исполнителя по настоящему Приложению осуществляется Заказчиком
          на основании выставленного счета, счет-фактуры, Акта оказания услуг согласно
          разделу 4 Договора.
          </span>
        </div>

        <div className="item lvl2">
          <span className="n">1.2.</span>
          <span>
          Услуги оказываются в соответствии с требованиями Заказчика. Стороны вправе
          согласовывать требования к Услугам, предоставлять и получать исходные материалы,
          необходимые для оказания Услуг. Любое изменение условий настоящего Приложения
          согласовывается сторонами отдельными Приложениями к Договору.
          </span>
        </div>

        <div className="item">
          <span className="n">2.</span>
          <span>
          В случае если Заказчик недоволен оказанными Услугами, он мотивированно сообщает
          Исполнителю, что его не устраивает в конкретной Услуге, и Исполнитель, согласовав
          с Заказчиком сроки на выполнение данных исправлений, приступает к доработке.
          </span>
        </div>

        <div className="item">
          <span className="n">3.</span>
          <span>
          Во всем остальном, не урегулированном настоящим Приложением, стороны
          руководствуются положениями Договора. Настоящее Приложение вступает в силу
          с момента его подписания Сторонами и распространяет свое действие на отношения
          Сторон, возникшие с {dm(d.period_from)} г. Настоящее Приложение составлено
          в 2 (двух) экземплярах, имеющих равную юридическую силу, по одному для каждой
          из Сторон, и является неотъемлемой частью Договора.
          </span>
        </div>

        <p className="flat"><b>Подписи Сторон:</b></p>

        <div className="signs">
          <div>
            <b>Исполнитель:</b>
            {exec.name}<br />
            {exec.position || '____________'}
            <div className="line">____________________ /{exec.short_fio || '_________'}/</div>
            <div>М.П.</div>
          </div>
          <div>
            <b>Заказчик:</b>
            {cust.name}<br />
            {cust.position || '____________'}
            <div className="line">____________________ /{cust.short_fio || '_________'}/</div>
            <div>М.П.</div>
          </div>
        </div>
      </div>
    </>
  )
}
