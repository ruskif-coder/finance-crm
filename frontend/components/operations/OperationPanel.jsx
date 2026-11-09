/**
 * Боковая панель операции (frontend/components/operations/OperationPanel.jsx). Эталон — reference/Операция - панель.dc.html.
 * Пропы:
 *   op          — ответ /context | null (пока грузится)       error — 'not_found' | null
 *   now         — серверное «сейчас» (todayMsk), ISO
 *   hasPrev, hasNext, onPrev, onNext, onClose, onRefreshRegistry
 *   onAction(key, op)  — 'open_package' | 'remind' | 'copy_id' | 'open_bank_row' (+ payment)
 *   links       — { package(code), ds(op), deal(code), counterparty(id), contract(id) } → href
 * Клавиши ↑ ↓ Esc вешаются здесь; затемнение рисует страница (как CellPanel). Ширина 560.
 *
 * Вставлено из хендоффа `docs/design_handoff_operation_panel.zip` дословно (09.11.2026). Отличия — только то, без чего у нас
 * не работает, каждое помечено «стенд:»:
 *   · PDF/XML — не `<a href>`, а onAction('download', …): файлы 1С отдаются под авторизацией (токен в заголовке), ссылкой не скачать;
 *   · контрагент, договор и наше юрлицо бывают пустыми (ручная операция без пакета) — строку без данных не рисуем, иначе падение;
 *   · площадки у сделки может не быть — пустые части строки сделки не печатаем («Бренд ·  · аккаунт»).
 * Добавлено по слову владельца 09.11.2026 (поверх хендоффа):
 *   · строка «рекламодатель» в «Откуда операция» — по сделкам ДС («не хватает рекламодателя»);
 *   · у ДС справа — «просмотр» своего ДС (печатная форма в системе) или «PDF» / «ЭДО ↗» внешнего («кнопку пдф к дс, или просмотр,
 *     если внутри системы»): onAction('view_ds' | 'ds_file');
 *   · блок «описание» у операций без документов 1С — старых, ручных, вне контура («там фиксировалась важная информация»):
 *     текст описания и вписанные руками № ДС, счёт, ссылка на документ;
 *   · «агентство» в «Сторонах» над контрагентом, полным названием — из-под какого агентства шла сделка, если было;
 *   · «просмотр» ДС — модалкой экрана бухгалтера (`onecDesk/DsViewer`), если есть право «Закрывающие документы».
 */
import React, { useEffect, useState } from 'react';
import { money, date, dateTime, paidOf, stateOf, blocksOf } from './operationLogic';

const MONO = "'JetBrains Mono',monospace";
const TONE = { need: ['var(--bg-subtle)', 'var(--border-inner)', 'var(--text-faint)', 'var(--text-primary)'], info: ['var(--accent-tint)', 'var(--accent-border)', 'var(--accent)', 'var(--accent-fg)'],
  ok: ['var(--income-tint)', 'var(--income-border)', 'var(--income)', 'var(--income-fg)'], bad: ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger)', 'var(--danger-fg)'], warn: ['var(--warning-bg)', 'var(--warning-border)', 'var(--warning)', 'var(--warning-fg)'] };
const CHIP = { need: ['var(--warning-tint)', 'var(--warning-fg)', 'var(--warning)'], info: ['var(--accent-tint)', 'var(--accent-fg)', 'var(--accent)'], ok: ['var(--income-tint)', 'var(--income-fg)', 'var(--income)'], bad: ['var(--danger-tint)', 'var(--danger-fg)', 'var(--danger)'], warn: ['var(--warning-tint)', 'var(--warning-fg)', 'var(--warning)'] };
const BANK = { alfa: 'var(--bank-alfa)', opt: 'var(--bank-opt)', sovkom: 'var(--bank-sovkom)', cash: 'var(--bank-cash)' };
const STYLE = `
.opp { font-family:'Manrope',system-ui,sans-serif; color:var(--text-primary) } .opp a { color:var(--accent); font-weight:700; text-decoration:none } .opp a:hover { color:var(--accent-hover); text-decoration:underline }
.opp-cap { font-family:${MONO}; font-size:10.5px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:var(--text-cap) }
.opp-ib { width:36px; height:36px; box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; border:1px solid var(--border-card); border-radius:12px; background:var(--bg-card); color:var(--text-secondary); cursor:pointer }
.opp-ib:hover { border-color:var(--border-hover); color:var(--accent-fg) } .opp-ib[aria-disabled="true"] { opacity:0.4; cursor:not-allowed }
.opp-row { display:grid; grid-template-columns:120px minmax(0,1fr); gap:0 12px; align-items:baseline; padding:4px 0; font-size:13px; line-height:1.5 } .opp-row > .k { color:var(--text-muted) }
.opp-v { display:flex; flex-wrap:wrap; column-gap:6px; align-items:baseline; min-width:0 }
.opp-sec { display:flex; flex-direction:column; gap:2px; padding:14px 0; border-top:1px solid var(--border-inner) }
.opp-no { color:var(--text-disabled); font-weight:700; cursor:not-allowed; border-bottom:1px dashed var(--text-disabled) }
.opp-sk { display:block; height:12px; border-radius:6px; background:linear-gradient(90deg,var(--bg-subtle),var(--border-inner),var(--bg-subtle)); background-size:200% 100%; animation:oppSk 1.2s linear infinite }
@keyframes oppSk { from { background-position:200% 0 } to { background-position:-200% 0 } }
@keyframes oppIn { from { transform:translateX(24px); opacity:0 } to { transform:none; opacity:1 } }
@keyframes oppBar { from { transform:scaleX(0) } to { transform:none } }
@media (prefers-reduced-motion: reduce) { .opp * { animation-duration:1ms !important } }`;

const Row = ({ k, children }) => <div className="opp-row"><span className="k">{k}</span><span className="opp-v">{children}</span></div>;
const Muted = ({ children }) => <span style={{ color: 'var(--text-muted)' }}>{children}</span>;
const Mono = ({ children, style }) => <span style={{ fontFamily: MONO, ...style }}>{children}</span>;
const Dot = ({ c, s = 7 }) => <span style={{ width: s, height: s, borderRadius: 2, background: c, flex: '0 0 auto' }} />;
const Sec = ({ title, right, children }) => <div className="opp-sec"><span style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 4 }}><span className="opp-cap">{title}</span>{right}</span>{children}</div>;

export default function OperationPanel({ op, error, now, hasPrev, hasNext, onPrev, onNext, onClose, onRefreshRegistry, onAction = () => {}, links = {} }) {
  const [copied, setCopied] = useState(false);
  const [histMode, setHistMode] = useState('all');
  const opId = op && op.id;                                  // стенд: зависимость эффекта именем (гейт check-hooks-lint)
  useEffect(() => setCopied(false), [opId]);
  useEffect(() => { const h = e => { if (/INPUT|TEXTAREA/.test(e.target.tagName)) return;
      if (e.key === 'Escape') onClose(); else if (e.key === 'ArrowUp' && hasPrev) { e.preventDefault(); onPrev(); } else if (e.key === 'ArrowDown' && hasNext) { e.preventDefault(); onNext(); } };
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, [hasPrev, hasNext, onPrev, onNext, onClose]);
  const href = (k, v) => (links[k] ? links[k](v) : '#');

  const head = (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0, flex: '1 1 auto' }}>
        {op && <>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span className="opp-cap">операция #{op.id} · {op.period_label}</span>
            <span role="button" tabIndex={0} title="Скопировать номер операции" onClick={() => { try { const p = navigator.clipboard && navigator.clipboard.writeText('#' + op.id); p && p.catch(() => {}); } catch (e) { /* noop */ } setCopied(true); onAction('copy_id', op); }}
              style={{ fontSize: 11.5, fontWeight: 700, color: copied ? 'var(--income-fg)' : 'var(--accent)', cursor: 'pointer' }}>{copied ? 'скопировано ✓' : 'копировать'}</span></span>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <Mono style={{ fontSize: 22, fontWeight: 700, whiteSpace: 'nowrap' }}>{money(op.amount)}</Mono>
            <span style={{ display: 'inline-flex', gap: 6, alignItems: 'baseline', fontSize: 12.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>с НДС · без НДС <Mono style={{ color: 'var(--text-secondary)', fontWeight: 700 }}>{money(Math.round((op.amount - op.vat) * 100) / 100)}</Mono></span>
          </span>
        </>}
      </span>
      <span role="button" tabIndex={0} className="opp-ib" aria-disabled={!hasPrev} title={hasPrev ? 'Предыдущая операция (↑)' : 'Первая операция на странице'} onClick={() => hasPrev && onPrev()}>↑</span>
      <span role="button" tabIndex={0} className="opp-ib" aria-disabled={!hasNext} title={hasNext ? 'Следующая операция (↓)' : 'Последняя операция на странице'} onClick={() => hasNext && onNext()}>↓</span>
      <span role="button" tabIndex={0} className="opp-ib" title="Закрыть (Esc, клик по затемнению)" onClick={onClose}>×</span>
    </div>);

  let body;
  if (error === 'not_found') body = (
    <div style={{ marginTop: 18, display: 'flex', flexDirection: 'column', gap: 10, padding: 16, borderRadius: 12, background: 'var(--danger-tint)', border: '1px solid var(--danger-border)' }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--danger-fg)' }}>Операция не найдена — возможно, её удалили</span>
      <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>Обновите реестр: строка могла устареть, пока страница была открыта.</span>
      <span role="button" tabIndex={0} onClick={onRefreshRegistry} style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px', borderRadius: 12, background: 'var(--bg-card)', border: '1px solid var(--border-card)', fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', cursor: 'pointer' }}>Обновить реестр</span>
    </div>);
  else if (!op) body = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingTop: 18 }} aria-busy="true">
      <span className="opp-sk" style={{ width: '70%', height: 40, borderRadius: 12 }} />
      <span style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>{[0, 1, 2].map(i => <span key={i} className="opp-sk" style={{ height: 62, borderRadius: 12 }} />)}</span>
      {['40%', '85%', '60%', '75%'].map(w => <span key={w} className="opp-sk" style={{ width: w }} />)}
      <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>загружаем пакет, документы и оплаты…</span>
    </div>);
  else {
    const s = stateOf(op, now), t = TONE[s.tone], ch = CHIP[s.tone], b = blocksOf(op);
    const paid = paidOf(op), rest = Math.round((op.amount - paid) * 100) / 100, out = op.direction === 'out';
    const diff = op.upd && op.ds ? Math.round((op.upd.amount - op.ds.amount) * 100) / 100 : 0;
    const tile = (l, v, note, tone) => { const c = tone === 'warn' ? ['var(--warning-bg)', 'var(--warning-border)', 'var(--warning-fg)', 'var(--warning-fg)'] : tone === 'ok' ? ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)', 'var(--text-faint)'] : tone === 'info' ? ['var(--bg-subtle)', 'var(--border-inner)', 'var(--accent-fg)', 'var(--text-faint)'] : tone === 'off' ? ['var(--bg-subtle)', 'var(--border-inner)', 'var(--text-disabled)', 'var(--text-faint)'] : ['var(--bg-subtle)', 'var(--border-inner)', 'var(--text-primary)', tone === 'match' ? 'var(--income-fg)' : 'var(--text-faint)'];
      return <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', borderRadius: 12, background: c[0], border: `1px solid ${c[1]}` }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{l}</span><Mono style={{ fontSize: 14.5, fontWeight: 700, color: c[2] }}>{v}</Mono><Mono style={{ fontSize: 11, color: c[3] }}>{note}</Mono></span>; };
    const paidTone = !paid ? 'off' : rest > 0 ? 'info' : 'ok', paidNote = paid ? Math.round(paid / op.amount * 100) + ' %' : 'ничего не пришло';
    const tiles = op.ds ? [tile('по ДС', money(op.ds.amount), `НДС ${op.vat_rate} % ${money(op.vat)}`), op.upd ? tile('из 1С', money(op.upd.amount), diff ? (diff > 0 ? '+' : '−') + money(Math.abs(diff)) + ' к ДС' : 'как в ДС', diff ? 'warn' : 'match') : null, tile('оплачено', money(paid), paidNote, paidTone)]
      : [tile('сумма', money(op.amount), `НДС ${op.vat_rate} % ${money(op.vat)}`), tile('статья', op.article, op.package ? '' : 'ручная операция'), tile(out ? 'списано' : 'оплачено', money(paid), paidNote, paidTone)];
    const hist = histMode === 'money' ? op.history.filter(h => h.kind === 'money') : op.history;
    const pays = op.payments || [];
    const advertisers = [...new Set((op.deals || []).map(d => d.advertiser && d.advertiser.name).filter(Boolean))];
    const agencies = [...new Set((op.deals || []).map(d => d.agency && d.agency.name).filter(Boolean))];
    body = (<>
      <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, background: ch[0], color: ch[1] }}><Dot c={ch[2]} s={6} />{s.status}</span>
        <span style={{ padding: '3px 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, background: 'var(--bg-subtle)', color: 'var(--text-secondary)' }}>{op.article}</span>
      </span>
      <div style={{ margin: '14px 0 4px', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 12, background: t[0], border: `1px solid ${t[1]}` }}>
        <Dot c={t[2]} s={8} />
        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}><span style={{ fontSize: 13, fontWeight: 700, color: t[3] }}>{s.next}</span>{s.sub && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.sub}</span>}</span>
        {s.action && <span role="button" tabIndex={0} title={s.action.title} onClick={() => onAction(s.action.key, op)} style={{ marginLeft: 'auto', flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-card)', fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)', cursor: 'pointer', whiteSpace: 'nowrap' }}>{s.action.label}</span>}
      </div>

      <div className="opp-sec" style={{ borderTop: 'none' }}>
        <span className="opp-cap" style={{ paddingBottom: 6 }}>деньги · ₽ с НДС</span>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>{tiles.filter(Boolean)}</div>
        {op.upd && op.upd.comment && Math.abs(diff) > 0.005 && (
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', borderRadius: 12, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)' }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--warning-fg)' }}>Комментарий бухгалтера к расхождению · {op.upd.comment_by}, {dateTime(op.upd.comment_at).slice(0, 5)}</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>«{op.upd.comment}»</span></div>)}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingTop: 10 }}>
          <div style={{ height: 8, borderRadius: 4, background: 'var(--border-inner)', display: 'flex', overflow: 'hidden' }}>
            {pays.map((p, i) => <span key={i} title={date(p.at) + ' · ' + money(p.amount)} style={{ width: `${p.amount / op.amount * 100}%`, background: i % 2 ? 'var(--income-fg)' : 'var(--income)', transformOrigin: 'left', animation: `oppBar 0.55s cubic-bezier(0.22,1,0.36,1) ${0.1 + i * 0.03}s both` }} />)}</div>
          <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)' }}><span>{paid ? `${out ? 'списано' : 'оплачено'} ${Math.round(paid / op.amount * 100)} %` : 'оплат ещё не было'}</span><Mono>{rest > 0 ? 'осталось ' + money(rest) : 'закрыто'}</Mono></span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', paddingTop: 6 }}>
          {pays.length > 1 && <div className="opp-row"><span className="k">цепочка оплат</span><span style={{ display: 'flex', flexDirection: 'column' }}>
            {pays.map((p, i) => <span key={i} style={{ display: 'grid', gridTemplateColumns: '8px 84px minmax(0,1fr) auto', gap: '0 8px', alignItems: 'center', padding: '2px 0' }}>
              <Dot c={BANK[p.bank]} /><Mono style={{ color: 'var(--text-secondary)' }}>{date(p.at).slice(0, 6) + date(p.at).slice(8)}</Mono>
              <a href="#" title="Открыть банковскую строку, с которой сопоставлена оплата" onClick={e => { e.preventDefault(); onAction('open_bank_row', { ...op, payment: p }); }} style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.doc}</a>
              <Mono style={{ fontWeight: 700, color: 'var(--income-fg)' }}>{money(p.amount)}</Mono></span>)}</span></div>}
          {pays.length === 1 && <Row k="оплата"><Mono>{date(pays[0].at)} · {money(pays[0].amount)}</Mono><a href="#" onClick={e => { e.preventDefault(); onAction('open_bank_row', { ...op, payment: pays[0] }); }}>{pays[0].doc}</a></Row>}
          {!pays.length && <Row k="оплата"><Muted>ещё не было</Muted></Row>}
          {op.kind === 'plan_income' && op.due_at && <Row k="срок оплаты"><Mono style={{ fontWeight: 700, color: s.tone === 'bad' ? 'var(--danger-fg)' : 'var(--text-primary)' }}>{date(op.due_at)}</Mono><Muted>· {op.due_rule}</Muted></Row>}
        </div>
      </div>

      {op.note && <Sec title="описание">  {/* стенд: правка владельца 09.11 */}
        {op.note.description && <div style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', paddingBottom: 4 }}>{op.note.description}</div>}
        {op.note.ds_num && <Row k="№ ДС"><Mono>{op.note.ds_num}</Mono></Row>}
        {op.note.invoice && <Row k="счёт"><Mono>№ {op.note.invoice}{op.note.invoice_date ? ` от ${date(op.note.invoice_date)}` : ''}</Mono></Row>}
        {op.note.document_link && <Row k="документ"><a href={op.note.document_link} target="_blank" rel="noopener noreferrer">открыть ↗</a></Row>}
      </Sec>}

      {b.origin && <Sec title="откуда операция">
        <Row k="пакет"><a href={href('package', op.package.code)} style={{ fontFamily: MONO }}>{op.package.code}</a><Muted>· {op.package.status_label} · УПД {op.package.upd_no}</Muted></Row>
        {advertisers.length > 0 && <Row k="рекламодатель"><span>{advertisers.join(', ')}</span></Row>}
        {op.ds && <Row k="ДС"><a href={href('ds', op)}>{op.ds.short}</a><Muted>от <Mono>{date(op.ds.date)}</Mono> · {op.ds.confirmed ? 'подтверждён' : 'не подтверждён'}</Muted>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 10 }}>
            {!op.ds.external && <a href="#" title="Открыть ДС в системе — та же форма, что печатается в PDF" onClick={e => { e.preventDefault(); onAction('view_ds', op); }}>просмотр</a>}
            {op.ds.external && op.ds.has_file && <a href="#" title="Файл ДС, подписанного вне системы" onClick={e => { e.preventDefault(); onAction('ds_file', op); }}>PDF</a>}
            {op.ds.external && op.ds.edo_link && <a href={op.ds.edo_link} target="_blank" rel="noopener noreferrer" title="ДС в ЭДО">ЭДО ↗</a>}
          </span></Row>}
        {op.deals.length > 0 && <div className="opp-row"><span className="k">{op.deals.length > 1 ? 'сделки' : 'сделка'}</span><span style={{ display: 'flex', flexDirection: 'column' }}>
          {op.deals.map(d => <span key={d.code} className="opp-v"><a href={href('deal', d.code)} style={{ fontFamily: MONO }}>{d.code}</a><span>{[d.brand, d.surface, d.account].filter(Boolean).join(' · ')}</span></span>)}</span></div>}  {/* стенд: пустые части не печатаем */}
      </Sec>}

      {b.docs && <Sec title="документы 1С">
        {[['счёт', op.upd.inv_no, op.upd.inv_date, [['PDF', op.upd.pdf_inv_url]]], ['УПД', op.upd.upd_no, op.upd.upd_date, [['PDF', op.upd.pdf_upd_url], ['XML', op.upd.xml_upd_url]]]].map(([k, no, d, files]) =>
          <div key={k} className="opp-row"><span className="k">{k}</span><span style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}><Mono>№ {no} от {date(d)}</Mono>
            {files.map(([l, url], i) => op.can_download_docs ? <a key={l} href="#" onClick={e => { e.preventDefault(); onAction('download', { ...op, file: url, label: `${k} ${no} ${l}` }); }} style={i === 0 ? { marginLeft: 'auto' } : undefined}>{l}</a>  /* стенд: скачивание под авторизацией */
              : <span key={l} className="opp-no" title="Нет права «Закрывающие документы · просмотр» — скачать нельзя" style={i === 0 ? { marginLeft: 'auto' } : undefined}>{l}</span>)}</span></div>)}
        {!op.can_download_docs && <Row k=""><span style={{ fontSize: 12, color: 'var(--text-faint)' }}>скачать нельзя — нет права «Закрывающие документы · просмотр»</span></Row>}
        <Row k="основание"><span style={{ color: 'var(--text-secondary)' }}>{op.upd.basis}</span></Row>
        <Row k="ЭДО">{op.edo ? <span>{op.edo.status_label}</span> : <><span title="Статус и «открыть в Диадоке» появятся после подключения ЭДО" style={{ padding: '2px 9px', borderRadius: 7, border: '1px dashed var(--border-hover)', fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>не подключено</span><span style={{ color: 'var(--text-faint)' }}>здесь будет статус и «открыть в Диадоке»</span></>}</Row>
        <Row k="внёс"><span>{op.upd.entered_by}</span><Mono style={{ color: 'var(--text-muted)' }}>· {dateTime(op.upd.entered_at)}</Mono></Row>
      </Sec>}

      <Sec title="стороны">
        {/* стенд: у ручной операции договора (и бывает — контрагента) нет */}
        {agencies.length > 0 && <Row k="агентство"><span>{agencies.join(', ')}</span></Row>}  {/* стенд: правка владельца 09.11 — над контрагентом */}
        {op.counterparty && <Row k="контрагент"><a href={href('counterparty', op.counterparty.id)}>{op.counterparty.short}</a>{op.counterparty.inn && <Mono style={{ color: 'var(--text-muted)' }}>ИНН {op.counterparty.inn}</Mono>}</Row>}
        {op.contract && <Row k="договор"><a href={href('contract', op.contract.id)}>№ {op.contract.no}</a><Muted>от <Mono>{date(op.contract.date)}</Mono></Muted></Row>}
        {op.our_entity && <Row k="наше юрлицо"><span>{op.our_entity}</span></Row>}
      </Sec>

      <Sec title="история" right={<span style={{ marginLeft: 'auto', display: 'inline-flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 9, padding: 2 }}>
        {[['all', 'все'], ['money', 'только деньги']].map(([v, l]) => { const on = histMode === v; return <span key={v} role="button" tabIndex={0} onClick={() => setHistMode(v)} style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', borderRadius: 7, fontSize: 11.5, fontWeight: 700, cursor: 'pointer', background: on ? 'var(--bg-card)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-muted)', boxShadow: on ? 'var(--shadow-card)' : 'none' }}>{l}</span>; })}</span>}>
        {hist.map((h, i) => <div key={i} style={{ display: 'grid', gridTemplateColumns: '8px 96px minmax(0,1fr)', gap: '0 8px', alignItems: 'baseline', padding: '4px 0', fontSize: 13, lineHeight: 1.5 }}>
          <Dot c={h.kind === 'money' ? 'var(--income)' : h.kind === 'create' ? 'var(--accent)' : 'var(--text-faint)'} /><Mono style={{ color: 'var(--text-muted)' }}>{dateTime(h.at)}</Mono><span style={{ color: 'var(--text-secondary)' }}>{h.text}</span></div>)}
        {!hist.length && <span style={{ fontSize: 13, color: 'var(--text-faint)' }}>Нет записей</span>}
      </Sec>
    </>);
  }

  return (
    <aside className="opp" role="dialog" aria-label="Операция" style={{ width: 560, boxSizing: 'border-box', background: 'var(--bg-card)', borderLeft: '1px solid var(--border-card)', boxShadow: 'var(--shadow-float)', padding: '20px 26px 28px', display: 'flex', flexDirection: 'column', minHeight: '100%', animation: 'oppIn 0.32s cubic-bezier(0.22,1,0.36,1) both' }}>
      <style>{STYLE}</style>{head}{body}
    </aside>);
}
