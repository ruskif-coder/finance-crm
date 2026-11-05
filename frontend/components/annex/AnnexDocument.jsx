/**
 * Вёрстка ДС — одна на печать и на просмотр (05.11.2026). Её печатает сайдкар PDF через страницу
 * `pages/directory/annexes/pdf/[id].js` и её же показывает модалка просмотра («Документы для 1С»): второй вёрстки
 * документа нет — расходиться нечему. Стили ограничены классом `.annexdoc`: внутри приложения голые `table`/`td`/`.row`
 * переписали бы остальную вёрстку. Размер листа (@page) и фон страницы задаёт печатная страница, не компонент.
 */
import { Fragment } from 'react'

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
  return `${p.legal_name || p.name}, именуемое в дальнейшем «${role}», в лице ${pos} ${fio}, `
    + `${p.acting || 'действующего'} на основании ${basis}`
}

export default function AnnexDocument({ d }) {
  const rows = d.rows || []
  // Слово документа — из бэкенда (`document.with_words`), тем же видом, что DOCX и конструктор:
  // своя таблица форм здесь разошлась с тумблером договора (ревью 31.10.2026).
  const w = d.words || { nom: 'Приложение', gen: 'Приложения', dat: 'Приложению', ins: 'Приложением', pl_ins: 'Приложениями' }
  const W = { dat: `настоящему ${w.dat}`, gen: `настоящего ${w.gen}`, ins: `настоящим ${w.ins}`, nom: `Настоящее ${w.nom}`, plIns: w.pl_ins }
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

  const clauses = d.clauses || []
  const tableEl = (
    <>
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
            {rows.map((r, i) => (r.group_title ? (
              /* ДС мастер-сделки: заголовок группы (бренд · услуга) строкой на всю ширину — как в DOCX */
              <tr key={i}><td colSpan={13} style={{ fontWeight: 'bold', textAlign: 'left' }}>{r.group_title}</td></tr>
            ) : (
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
                <td className="num">{r.bonus ? '—' : fix2(r.unit_price)}</td>
                <td className="num net">{r.bonus ? '—' : fix2(r.amount)}</td>
                <td className="num">{r.bonus ? '—' : fix2(r.vat)}</td>
                <td className="num net">{r.bonus ? '—' : fix2(r.gross)}</td>
              </tr>
            )))}
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
    </>
  )
  // `heading === false` — заголовок подписей уже стоит пунктом шаблона («6. Подписи Сторон:»), второй не печатаем (02.11.2026).
  const signsOf = (heading = true) => (
    <>
      {heading && <p className="flat"><b>Подписи Сторон:</b></p>}

      <div className="signs">
        <div>
          <b>Исполнитель:</b>
          {exec.legal_name || exec.name}<br />
          {exec.position_nom || exec.position || '____________'}
          <div className="line">____________________ /{exec.short_fio || '_________'}/</div>
          <div>М.П.</div>
        </div>
        <div>
          <b>Заказчик:</b>
          {cust.legal_name || cust.name}<br />
          {cust.position_nom || cust.position || '____________'}
          <div className="line">____________________ /{cust.short_fio || '_________'}/</div>
          <div>М.П.</div>
        </div>
      </div>
    </>
  )

  return (
    <div className="annexdoc">
      <style>{`
  .annexdoc .doc { font-family: 'Times New Roman', Times, serif; font-size: 11.5pt;
         line-height: 1.4; color: #000; background: #fff; max-width: 265mm; margin: 0 auto;
         padding: 8mm 0; text-align: justify; }
  .annexdoc .doc h1 { font-size: 12pt; font-weight: bold; text-align: center; margin: 0 0 2mm; }
  .annexdoc .doc .sub { text-align: center; margin: 0 0 6mm; }
  .annexdoc .row { display: flex; justify-content: space-between; margin-bottom: 6mm; }
  .annexdoc .doc p { margin: 0 0 3mm; text-indent: 0; }
  /* Нумерованный пункт: номер висит слева, текст выровнен по общей линии — так набраны пункты в подписанном образце,
     и по ЛЕВОМУ краю, а не по ширине (правило владельца 05.09.2026). Модификатор вложенного пункта — lvl2, а не sub:
     селектор .doc .sub центрирует подзаголовок шапки и молча ловил бы пункты тоже. */
  .annexdoc .item { display: grid; grid-template-columns: 12mm 1fr; gap: 0; margin: 0 0 3mm; text-align: left; }
  .annexdoc .item.lvl2 { grid-template-columns: 12mm 1fr; padding-left: 8mm; }
  .annexdoc .item .n { font-weight: normal; }
  /* Шапка таблицы синяя с белым текстом — как в подписанном образце и в выгрузках медиаплана. Цвета литералами, а не
     токенами: документ печатают на бумаге, темы у него нет, и var(--*) в PDF взять неоткуда. */
  .annexdoc table { width: 100%; border-collapse: collapse; margin: 4mm 0 5mm; font-size: 7.5pt; }
  /* Рамки чёрные (владелец 21.10.2026, просьба бухгалтерии; до того — белые, как в выгрузках медиаплана). */
  .annexdoc th, .annexdoc td { border: 1px solid #000; padding: 1.2mm 1.5mm; vertical-align: middle; }
  .annexdoc th { background: #4472C4; color: #fff; font-weight: bold; text-align: center; font-size: 7pt; line-height: 1.15; }
  .annexdoc td { text-align: center; }
  .annexdoc td.pos { text-align: left; font-style: italic; font-size: 7pt; line-height: 1.2; }
  .annexdoc td.net { font-weight: bold; }
  .annexdoc td.num { text-align: right; white-space: nowrap; }
  .annexdoc tr.total td { background: #D9E2F3; font-weight: bold; }
  /* Стороны разводятся по противоположным краям листа: исполнитель прижат влево, заказчик вправо — так подписи
     не читаются как один общий блок. */
  .annexdoc .basis { page-break-before: always; padding-top: 4mm; }
  .annexdoc .basis .note { font-style: italic; font-size: 0.92em; margin-bottom: 4mm; }
  .annexdoc .signs { display: flex; justify-content: space-between; align-items: flex-start;
           gap: 10mm; margin-top: 10mm; page-break-inside: avoid; }
  .annexdoc .signs > div { width: 45%; text-align: left; }
  .annexdoc .signs > div:last-child { text-align: right; }
  .annexdoc .signs b { display: block; margin-bottom: 4mm; }
  .annexdoc .signs .line { margin-top: 8mm; }
  /* Номер договора не переносится по частям: «68/2026-МЗ» рвётся по слэшу и дефису, и в документе оказываются
     два разных на вид номера на двух строках. */
  .annexdoc .nb { white-space: nowrap; }
`}</style>
        <div className="doc">
          <h1>{d.number || w.nom}</h1>
          <div className="sub">
            к Договору <span className="nb">№ {d.contract?.number || '________'}</span>{' '}
            об оказании услуг от {longDate(d.contract?.date)}
          </div>

          <div className="row">
            <span>{d.signed_place || 'г. Москва'}</span>
            <span>{longDate(d.date)}</span>
          </div>

          {/* Преамбула — текст шаблона (02.11.2026); без него — стандартная формула. */}
          {d.preamble ? <p className="flat">{d.preamble}</p> : <p className="flat">
            {partyLine(cust, 'Заказчик')}, с одной стороны, и {partyLine(exec, 'Исполнитель')},
            с другой стороны, заключили настоящее {d.number} к Договору{' '}
            <span className="nb">№ {d.contract?.number || '________'}</span> об оказании услуг
            от {longDate(d.contract?.date)} (далее по тексту – «Договор») о нижеследующем:
          </p>}

          {/* Пункты — ровно блоки конструктора, в его порядке (владелец 02.11.2026): номера и тексты шаблона, таблица и
              подписи там, где их поставил шаблон. Без модели (ДС до конструктора) — прежний текст ниже. */}
          {clauses.length ? (<>
            {clauses.map((c, i) => (c.sys === 'table' ? <Fragment key={i}>{tableEl}</Fragment>
              : c.sys === 'sign' ? <Fragment key={i}>{signsOf(c.heading !== false)}</Fragment>
              : c.sys ? null
              : (
                <div key={i} className={c.sub ? 'item lvl2' : 'item'}>
                  <span className="n">{c.num}</span>
                  <span style={{ whiteSpace: 'pre-line' }}>{c.text}</span>
                </div>
              )))}
            {!clauses.some(c => c.sys === 'sign') && signsOf()}
          </>) : (<>
          {/* Нумерация пунктов повторяет подписанный образец: 1 — предмет со ссылкой на
              медиаплан, 1.1 — стоимость, 1.2 — порядок оказания, 2 — доработки,
              3 — заключительные положения. В исходном docx часть номеров автоматические
              (списком Word), часть набрана руками — здесь они текстом, чтобы номер
              копировался вместе с пунктом и не зависел от рендерера. */}
          <div className="item">
            <span className="n">1.</span>
            <span>{d.body}</span>
          </div>

          {tableEl}
          <div className="item lvl2">
            <span className="n">1.1.</span>
            <span>
            Общая стоимость Услуг Исполнителя по {W.dat} составляет сумму
            в размере {d.amount_words}, в том числе НДС {d.vat_rate}% — {d.vat_words}.
            Оплата услуг Исполнителя по {W.dat} осуществляется Заказчиком
            на основании выставленного счета, счет-фактуры, Акта оказания услуг согласно
            разделу 4 Договора.
            </span>
          </div>

          <div className="item lvl2">
            <span className="n">1.2.</span>
            <span>
            Услуги оказываются в соответствии с требованиями Заказчика. Стороны вправе
            согласовывать требования к Услугам, предоставлять и получать исходные материалы,
            необходимые для оказания Услуг. Любое изменение условий {W.gen}
            согласовывается сторонами отдельными {W.plIns} к Договору.
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
            Во всем остальном, не урегулированном {W.ins}, стороны
            руководствуются положениями Договора. {W.nom} вступает в силу
            с момента его подписания Сторонами и распространяет свое действие на отношения
            Сторон, возникшие с {dm(d.period_from)} г. {W.nom} составлено
            в 2 (двух) экземплярах, имеющих равную юридическую силу, по одному для каждой
            из Сторон, и является неотъемлемой частью Договора.
            </span>
          </div>

          {signsOf()}
          </>)}

          {/* Файл «для клиента»: после ДС — основание для закрывающих документов (УПД и счёт) на согласование, одним документом. */}
          {d.with_basis && !!d.closing_basis && (
            <div className="basis">
              <p className="flat"><b>Основание для закрывающих документов</b></p>
              <p className="flat note">К {d.number_dat || w.dat} к Договору № {d.contract?.number || '________'}. Формулировка, которая будет указана в УПД и счёте. Просим согласовать.</p>
              <p className="flat" style={{ whiteSpace: 'pre-line' }}>{d.closing_basis}</p>
            </div>
          )}
        </div>
    </div>
  )
}
