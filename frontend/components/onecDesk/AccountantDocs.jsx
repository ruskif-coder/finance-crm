/**
 * Страница «Документы для бухгалтерии» (pages/finance/onec-desk.js → <AccountantDocs/>). Хендофф 05.11.2026 — вставлен дословно;
 * отличия от пакета дизайна — только проводка в систему: файлы ДС и приложенные файлы открывает страница (у нас они под
 * авторизацией, ссылкой не открыть), «убрать» файл удаляет его на сервере, ошибки сервера — тостом, срок закрытия правится
 * по клику на плашку, родительный падеж месяца — с сервера.
 * Очередь заявок на счёт и УПД по мастер-сделкам + рабочая панель заявки. Эталон вида и поведения — reference/Документы для бухгалтерии.dc.html.
 *
 * Пропы:
 *   data                         — ответ GET /api/acc-docs (контракт в sampleData.js)
 *   onUpload(code, kind, file)   — kind: 'invPdf' | 'updPdf' | 'updXml' → Promise<File{name,size,url}>
 *   onParseXml(code, file)       — разбор XML УПД → Promise<XmlParse>
 *   onCheckNumber(kind, no, code)— повтор номера → Promise<null | {code,status,at}>
 *   onSaveDraft(code, form)      — автосохранение (дебаунс 700 мс) → Promise<{saved_at}>
 *   onSubmit(code, form)         — «Внести» → Promise (сервер повторяет evaluate и отклоняет, если не ready)
 *   onReturn(code, {reason,text})— вернуть аккаунту → Promise
 *   onNote(code, text)           — сообщение аккаунту без возврата → Promise
 *   onSeen(code)                 — заявку открыли: снять «ответ»/«исправлено» → Promise
 *   onOpenDeal(code), onExcel(code)
 *   onDsFile(code, 'ds'|'scan')  — открыть ДС (модалкой) или скан подписанного
 *   onOpenFile(code, file)       — скачать приложенный PDF/XML
 *   onRemoveFile(code, kind, file)— убрать приложенный файл → Promise
 *   onEditClose()                — клик по плашке срока закрытия (бухгалтер меняет срок; нет права — не передаётся)
 *   now                          — ISO/мс «сейчас» (по умолчанию data.now); для live-обновления передавать раз в минуту
 */
import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  money, parseMoney, msk, isoToRuDate, workHours, ageLabel, ageTone, closeInfo, EMPTY_FORM, evaluate, rowPips, matches, sortQueue, copyAllText, expectedOf, isStarted,
} from './accDocsLogic';
import { STYLE, MONO, Cap, Card, Btn, Input, Dot, Chip, Pip, CopyField, FileRow, Field, borderFor, StepHead, Sum, TONE } from './accDocsParts';

const AD_RISE = 'adRise 0.4s cubic-bezier(0.22,1,0.36,1) both';   // анимация появления строкой: гейт check-tokens пускает в стили только переменные globals.css
const TABS = [['wait', 'Заявки на документы', 'var(--accent)'], ['returned', 'Возвращены аккаунту', 'var(--warning)'], ['done', 'Внесены', 'var(--income)'], ['all', 'Все', null]];
const RETURN_REASONS = ['реквизиты покупателя', 'сумма не та', 'нет подписанного ДС', 'основание / период'];
const ACCEPT = { invPdf: '.pdf', updPdf: '.pdf', updXml: '.xml,.zip' };
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 12 || h > 14) ? b : c; };
const short = name => name.replace(/ ООО$/, '');

export default function AccountantDocs({ data, onUpload, onParseXml, onCheckNumber, onSaveDraft, onSubmit, onReturn, onNote, onSeen, onOpenDeal, onExcel, onDsFile, onOpenFile, onRemoveFile, onEditClose, now }) {
  const nowMs = typeof now === 'number' ? now : Date.parse(now || data.now);
  const cal = data.settings.calendar;
  const [tab, setTab] = useState('wait');
  const [group, setGroup] = useState('buyer');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState({});                // локальные переходы до перезагрузки данных: code → 'done' | 'returned'
  const [forms, setForms] = useState(() => Object.fromEntries(data.requests.filter(r => r.draft).map(r => [r.code, { ...EMPTY_FORM, ...r.draft }])));
  const [seen, setSeen] = useState(() => Object.fromEntries(data.requests.map(r => [r.code, r.seen])));
  const [copied, setCopied] = useState({});                // code → { key: true }
  const [lastCopy, setLastCopy] = useState('');            // 'code:key' — п.13, «в буфере» только у одного
  const [dup, setDup] = useState({});                      // code → { inv, upd } строки «M-0004 · внесено 05.11 10:02»
  const [saved, setSaved] = useState({});                  // code → 'чч:мм' | 'error'
  const [ret, setRet] = useState({ open: false, reason: '', text: '' });
  const [note, setNoteDraft] = useState('');
  const [localNotes, setLocalNotes] = useState({});
  const [toast, setToast] = useState('');
  const toastT = useRef(); const showToast = (t, ms = 1900) => { setToast(t); clearTimeout(toastT.current); toastT.current = setTimeout(() => setToast(''), ms); };
  const fail = e => showToast((e && e.message) || 'Не получилось — попробуйте ещё раз', 5000);

  const reqs = useMemo(() => data.requests.map(r => status[r.code] ? { ...r, status: status[r.code] } : r), [data.requests, status]);
  const formOf = code => forms[code] || EMPTY_FORM;
  const searching = q.trim().length > 0;
  const list = useMemo(() => sortQueue(searching ? reqs.filter(r => matches(r, q)) : reqs.filter(r => tab === 'all' || r.status === tab)), [reqs, q, tab, searching]);

  /* группы очереди (по умолчанию — по покупателю и договору) */
  const groups = useMemo(() => {
    if (group !== 'buyer') return [{ key: 'all', items: list }];
    const m = new Map(); list.forEach(r => { const k = r.buyer.inn + '|' + r.contract.no; if (!m.has(k)) m.set(k, []); m.get(k).push(r); });
    return [...m.entries()].map(([key, items]) => ({ key, head: short(items[0].buyer.name), contract: items[0].contract.no, items }));
  }, [list, group]);
  const nav = useMemo(() => groups.flatMap(g => g.items.map(r => r.code)), [groups]);

  const [sel, setSel] = useState(() => (sortQueue(data.requests.filter(r => r.status === 'wait'))[0] || {}).code);
  const r = reqs.find(x => x.code === sel) || list[0];
  const select = useCallback(code => { setSel(code); setRet({ open: false, reason: '', text: '' }); if (!seen[code]) { setSeen(s => ({ ...s, [code]: true })); onSeen && onSeen(code); } }, [seen, onSeen]);

  /* ── форма выбранной заявки ── */
  const readOnly = r && r.status === 'done';
  const f = !r ? EMPTY_FORM : readOnly && r.done ? archiveForm(r) : formOf(r.code);
  const setF = patch => { if (!r || readOnly) return; setForms(s => ({ ...s, [r.code]: { ...formOf(r.code), ...patch } })); };
  const ev = r ? evaluate(r, f, { dupInv: dup[r.code] && dup[r.code].inv, dupUpd: dup[r.code] && dup[r.code].upd, closedUntil: data.settings.closed_until, readOnly }) : null;

  /* п.14: автосохранение черновика */
  useEffect(() => { if (!r || readOnly || !forms[r.code]) return; const code = r.code, form = forms[code];
    const t = setTimeout(() => { Promise.resolve(onSaveDraft && onSaveDraft(code, form)).then(() => setSaved(s => ({ ...s, [code]: msk(Date.now()).hm })), () => setSaved(s => ({ ...s, [code]: 'error' }))); }, 700);
    return () => clearTimeout(t); }, [forms, r && r.code]); // eslint-disable-line react-hooks/exhaustive-deps

  /* п.2: повтор номера — дебаунс 400 мс */
  useEffect(() => { if (!r || readOnly || !onCheckNumber) return; const code = r.code, inv = f.invNo, upd = f.updNo;
    const t = setTimeout(async () => { const fmt = h => h ? `${h.code}${h.status === 'done' && h.at ? ' · внесено ' + msk(h.at).dm : ' · в работе'}` : null;
      const [a, b] = await Promise.all([inv ? onCheckNumber('inv', inv, code) : null, upd ? onCheckNumber('upd', upd, code) : null]);
      setDup(s => ({ ...s, [code]: { inv: fmt(a), upd: fmt(b) } })); }, 400);
    return () => clearTimeout(t); }, [r && r.code, f.invNo, f.updNo]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── действия ── */
  const copy = (key, text) => { try { const p = navigator.clipboard && navigator.clipboard.writeText(text); p && p.catch(() => legacyCopy(text)); } catch (e) { legacyCopy(text); }
    setCopied(s => ({ ...s, [r.code]: { ...(s[r.code] || {}), [key]: true } })); setLastCopy(r.code + ':' + key); };
  const cstate = key => lastCopy === r.code + ':' + key ? 'last' : (copied[r.code] || {})[key] ? 'was' : '';
  const COPY_KEYS = ['inn', 'ct', 'basis', 'svc', 'net', 'vat', 'gross'];
  const copyAll = () => { copy('all', copyAllText(r)); setCopied(s => ({ ...s, [r.code]: Object.fromEntries(COPY_KEYS.concat('all').map(k => [k, true])) })); showToast('Всё для 1С — в буфере одним блоком'); };

  const fileInput = useRef(); const pending = useRef(null);
  const pick = kind => { if (readOnly) return; pending.current = kind; fileInput.current.accept = ACCEPT[kind]; fileInput.current.value = ''; fileInput.current.click(); };
  const onFile = async e => { const file = e.target.files && e.target.files[0], kind = pending.current; if (!file || !kind) return; const code = r.code;
    let up; try { up = await onUpload(code, kind, file); } catch (err) { fail(err); return; }
    if (kind === 'updXml') { let x; try { x = await onParseXml(code, file); } catch (err) { setForms(s => ({ ...s, [code]: { ...formOf(code), updXml: up, xml: null, fromXml: false } })); fail(err); return; }
      const cur = formOf(code);   // п.4: номер/дата — если пусто, суммы — всегда
      setForms(s => ({ ...s, [code]: { ...cur, updXml: up, xml: x, fromXml: true, updNo: cur.updNo || x.number, updDate: cur.updDate || x.date, net: x.net, vat: x.vat, gross: x.gross } }));
    } else setForms(s => ({ ...s, [code]: { ...formOf(code), [kind]: up } })); };
  const removeFile = (kind, patch) => { const code = r.code, file = formOf(code)[kind];
    Promise.resolve(file && onRemoveFile && onRemoveFile(code, kind, file)).then(() => setF(patch), fail); };
  const nextWait = code => { const w = sortQueue(reqs.filter(x => x.status === 'wait' && x.code !== code)); return w[0] && w[0].code; };
  const submit = async () => { if (!ev || readOnly) return; if (!ev.ready) { showToast('Не хватает: ' + ev.missing.map(m => m.label).join(', ')); return; }
    const code = r.code; try { await onSubmit(code, f); } catch (e) { fail(e); return; } setStatus(s => ({ ...s, [code]: 'done' })); const nx = nextWait(code); nx && select(nx); showToast(code + ' внесено' + (nx ? ' — открыт ' + nx : ' — очередь пуста')); };
  const doReturn = async () => { if (!ret.reason && !ret.text.trim()) return; const code = r.code; try { await onReturn(code, { reason: ret.reason, text: ret.text.trim() }); } catch (e) { fail(e); return; }
    setStatus(s => ({ ...s, [code]: 'returned' })); const nx = nextWait(code); nx && select(nx); showToast(code + ' возвращён аккаунту'); };
  const sendNote = async () => { const t = note.trim(); if (!t) return; try { await onNote(r.code, t); } catch (e) { fail(e); return; } setLocalNotes(s => ({ ...s, [r.code]: [{ at: new Date(nowMs).toISOString(), who: 'Бухгалтер', text: t }].concat(s[r.code] || []) })); setNoteDraft(''); };

  /* п.5: клавиши */
  const keyRef = useRef(); keyRef.current = { submit, nav, sel: r && r.code, select, close: () => setRet(x => ({ ...x, open: false })) };
  useEffect(() => { const h = e => { const k = keyRef.current, inField = e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName);
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); k.submit(); return; }
      if (e.key === 'Escape') { k.close(); return; }
      if (!inField && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && k.nav.length) { e.preventDefault(); const i = k.nav.indexOf(k.sel);
        k.select(k.nav[Math.max(0, Math.min(k.nav.length - 1, i < 0 ? 0 : i + (e.key === 'ArrowDown' ? 1 : -1)))]); } };
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);

  /* ── очередь: подписи ── */
  const waits = reqs.filter(x => x.status === 'wait');
  const oldest = sortQueue(waits)[0];
  const nReady = waits.filter(x => evaluate(x, formOf(x.code)).readiness === 'ready').length;
  const close = closeInfo(nowMs, data.settings.close_at, reqs.filter(x => x.status !== 'done').length, cal);
  const todayDone = reqs.filter(x => x.status === 'done' && (x.done ? msk(x.done.at).d === msk(nowMs).d : true)).length;
  let qSub = `${list.length} · ${money(list.reduce((a, x) => a + expectedOf(x).gross, 0))} ₽`;
  if (!searching && tab === 'wait' && oldest) qSub += ' · дольше всех ' + ageLabel(workHours(Date.parse(oldest.since), nowMs, cal));
  if (!searching && tab === 'wait' && nReady) qSub += ' · готово ' + nReady;
  if (!searching && tab === 'done') qSub += ' · сегодня ' + todayDone;

  return (
    <div className="ad-root" style={{ minHeight: '100vh', boxSizing: 'border-box', padding: '22px 30px', background: 'var(--bg-canvas)', display: 'flex', justifyContent: 'center' }}>
      <style>{STYLE}</style>
      <input ref={fileInput} type="file" hidden onChange={onFile} data-testid="ad-file" />
      <div style={{ width: '100%', maxWidth: 2500, display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', animation: AD_RISE }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em' }}>Закрывающие документы</span>
            <span style={{ fontFamily: MONO, fontSize: 11.5, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>счёт и УПД по мастер-сделкам · сейчас {msk(nowMs).dm} · ожидание — в рабочих часах</span>
          </span>
          <span role="tablist" style={{ display: 'inline-flex', gap: 6, marginLeft: 18 }}>
            {TABS.map(([k, label, dot]) => { const on = !searching && tab === k, n = reqs.filter(x => k === 'all' || x.status === k).length;
              return <span key={k} role="tab" aria-selected={on} tabIndex={0} onClick={() => { setTab(k); setQ(''); }} onKeyDown={e => e.key === 'Enter' && (setTab(k), setQ(''))}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, boxSizing: 'border-box', padding: '0 14px', borderRadius: 12, fontSize: 13, fontWeight: on ? 700 : 600, cursor: 'pointer', background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
                {dot && <Dot c={dot} s={7} />}{label}<span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: on ? 'var(--accent-fg)' : 'var(--text-muted)' }}>{n}</span></span>; })}
          </span>
          <span style={{ marginLeft: 'auto', width: 420 }}><Input value={q} onChange={e => setQ(e.target.value)} placeholder="⌕  Поиск по всем: покупатель, ИНН, № ДС, код" aria-label="Поиск по всем заявкам" /></span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '640px minmax(0,1fr)', gap: 14, alignItems: 'stretch', flex: '1 1 auto', animation: AD_RISE, animationDelay: '0.07s' }}>

          {/* ═════ очередь ═════ */}
          <Card style={{ padding: '14px 14px 10px', display: 'flex', flexDirection: 'column', gap: 8, position: 'sticky', top: 14, alignSelf: 'start', maxHeight: 'calc(100vh - 110px)', boxSizing: 'border-box' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 4px' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <span style={{ fontSize: 15, fontWeight: 700, whiteSpace: 'nowrap' }}>{searching ? 'Поиск по всем' : TABS.find(t => t[0] === tab)[1]}</span>
                <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{qSub}</span>
              </span>
              <span style={{ marginLeft: 'auto', display: 'inline-flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 10, padding: 2 }}>
                {[['buyer', 'по покупателю'], ['flat', 'списком']].map(([v, l]) => { const on = group === v;
                  return <span key={v} role="button" tabIndex={0} onClick={() => setGroup(v)} style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 11px', borderRadius: 8, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer', background: on ? 'var(--bg-card)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-muted)', boxShadow: on ? 'var(--shadow-card)' : 'none' }}>{l}</span>; })}
              </span>
            </div>
            {/* п.8: срок закрытия месяца */}
            <div role={onEditClose ? 'button' : undefined} tabIndex={onEditClose ? 0 : undefined} onClick={onEditClose} title={onEditClose ? 'Изменить срок закрытия месяца' : undefined} style={{ cursor: onEditClose ? 'pointer' : undefined, display: 'flex', alignItems: 'center', gap: 8, margin: '0 4px', padding: '7px 11px', borderRadius: 10, background: close.tone === 'ok' ? 'var(--bg-subtle)' : close.tone === 'warn' ? 'var(--warning-bg)' : 'var(--danger-tint)', border: `1px solid ${close.tone === 'ok' ? 'var(--border-inner)' : TONE[close.tone].border}` }}>
              <Dot c={close.tone === 'ok' ? 'var(--text-faint)' : TONE[close.tone].dot} s={7} />
              <span style={{ fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', color: close.tone === 'ok' ? 'var(--text-secondary)' : TONE[close.tone].fg }}>До закрытия {data.settings.close_month_gen || data.settings.close_month} {close.left} {close.word}</span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{close.at} · открыто {close.openCount}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', overflow: 'auto', minHeight: 0 }}>
              {groups.map(g => (
                <React.Fragment key={g.key}>
                  {g.head && (() => { const nr = g.items.filter(x => x.status === 'wait' && evaluate(x, formOf(x.code)).readiness === 'ready').length;
                    return <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '12px 8px 4px' }}>
                      <span style={{ fontSize: 13, fontWeight: 800 }}>{g.head}</span>
                      <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>договор № {g.contract} · {g.items.length} шт.{nr ? ' · готово ' + nr : ''}</span>
                      <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{money(g.items.reduce((a, x) => a + expectedOf(x).gross, 0))}</span></div>; })()}
                  {g.items.map(x => <QueueRow key={x.code} req={x} grouped={!!g.head} sel={r && x.code === r.code} form={forms[x.code]} seen={seen[x.code]} nowMs={nowMs} cal={cal} onPick={() => select(x.code)} />)}
                </React.Fragment>
              ))}
              {list.length === 0 && <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '40px 16px', textAlign: 'center' }}>
                <span style={{ fontSize: 15, fontWeight: 700, color: searching ? 'var(--text-secondary)' : 'var(--income-fg)' }}>{searching ? 'Ничего не найдено' : tab === 'wait' ? 'Ничего не ждёт' : 'Пусто'}</span>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{searching ? 'Ищем по покупателю, ИНН, коду сделки, № ДС и договора.' : tab === 'wait' ? 'Все заявки внесены. Новые появятся, когда аккаунт отправит пакет.' : 'В этой вкладке заявок нет.'}</span></div>}
            </div>
            <span style={{ fontSize: 11.5, color: 'var(--text-faint)', padding: '4px 6px 0', lineHeight: 1.4 }}>Ожидание в рабочих часах (пн–пт, 9–18 МСК). Жёлтое — больше рабочего дня, красное — больше трёх. ДС: зелёный — подписан, жёлтый — создан, но не подписан. СЧЁТ и УПД появляются, когда заявку начали заполнять. Зелёная строка — всё заполнено, осталось нажать «Внести».</span>
          </Card>

          {/* ═════ рабочая панель ═════ */}
          {!r ? <Card style={{ padding: '60px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, alignSelf: 'start' }}>
              <span style={{ fontSize: 17, fontWeight: 800, color: 'var(--income-fg)' }}>Очередь пуста</span>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Все заявки внесены. Новые появятся, когда аккаунт отправит пакет.</span></Card>
            : <RequestPanel {...{ r, f, ev, readOnly, nowMs, cal, setF, copy, cstate, copyAll, lastCopy, pick, submit, ret, setRet, doReturn, saved: saved[r.code], note, setNoteDraft, sendNote, onOpenDeal, onExcel, onDsFile, onOpenFile, removeFile,
                past: sortQueue(reqs.filter(x => x.buyer.inn === r.buyer.inn && x.code !== r.code && x.status === 'done')).slice(0, 6), select,
                log: (localNotes[r.code] || []).map(n => ({ ...n, mine: true })).concat(r.thread || []), seenNow: seen[r.code], dupRow: dup[r.code] || {} }} />}
        </div>
      </div>
      {toast && <div role="status" style={{ position: 'fixed', right: 24, bottom: 96, background: 'var(--text-primary)', color: '#FFFFFF', padding: '11px 16px', borderRadius: 12, fontSize: 13, fontWeight: 600, boxShadow: 'var(--shadow-float)', animation: 'adRise 0.24s cubic-bezier(0.22,1,0.36,1) both', zIndex: 10 }}>{toast}</div>}
    </div>
  );
}

/* ───────── строка очереди ───────── */
function QueueRow({ req, grouped, sel, form, seen, nowMs, cal, onPick }) {
  const { pips, readiness } = rowPips(req, form, seen);
  const ready = req.status === 'wait' && readiness === 'ready';
  const h = workHours(Date.parse(req.since), nowMs, cal), tone = ageTone(h);
  const age = req.status === 'done' ? ['внесено', 'var(--income-fg)', 'var(--income)'] : req.status === 'returned' ? ['у аккаунта', 'var(--warning-fg)', 'var(--warning)']
    : [ageLabel(h), tone === 'ok' ? 'var(--text-muted)' : TONE[tone].fg, tone === 'ok' ? 'var(--text-faint)' : TONE[tone].dot];
  const exp = expectedOf(req);
  return (
    <div role="button" tabIndex={0} className="ad-row" aria-current={sel || undefined} onClick={onPick} onKeyDown={e => e.key === 'Enter' && onPick()}
      style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 150px 112px', gap: '0 12px', alignItems: 'center', padding: '9px 10px', borderRadius: 12, cursor: 'pointer', marginBottom: 2,
        background: ready ? 'var(--income-tint)' : sel ? 'var(--bg-tint)' : 'transparent', border: `1px solid ${sel ? (ready ? 'var(--income)' : 'var(--accent-border)') : ready ? 'var(--income-border)' : 'transparent'}` }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
          <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)' }}>{req.code}</span>
          <span title={req.buyer.name} style={{ fontSize: 13.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{grouped ? req.annex.short : short(req.buyer.name)}</span>
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{grouped ? req.brand : req.annex.short + ' · ' + req.brand}</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
        <Sum v={exp.gross} />
        <span style={{ display: 'flex', gap: 4 }}>{pips.map(p => <Pip key={p.label} {...p} onGreen={ready} />)}</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: MONO, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', color: age[1] }}><Dot c={age[2]} />{age[0]}</span>
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{req.status === 'done' ? msk(req.done ? req.done.at : nowMs).dm : 'с ' + msk(req.since).dm}</span>
      </span>
    </div>
  );
}

/* ───────── рабочая панель заявки ───────── */
function RequestPanel({ r, f, ev, readOnly, nowMs, cal, setF, copy, cstate, copyAll, lastCopy, pick, submit, ret, setRet, doReturn, saved, note, setNoteDraft, sendNote, onOpenDeal, onExcel, onDsFile, onOpenFile, removeFile, past, select, log, seenNow, dupRow }) {
  const h = workHours(Date.parse(r.since), nowMs, cal), tone = ageTone(h);
  const st = r.status === 'done' ? ['внесено', 'ok'] : r.status === 'returned' ? ['возвращено аккаунту', 'warn'] : ev.ready ? ['готово к внесению', 'ok'] : ['ждёт бухгалтера', 'info'];
  const exp = ev.exp, line = r.lines[0], allCp = lastCopy === r.code + ':all';
  const c1done = ['inn', 'ct', 'basis', 'svc', 'net', 'vat', 'gross'].every(k => cstate(k)) || cstate('all');
  const S = ev.sum, sumTone = S.state === 'bad' ? 'bad' : S.state === 'diff' ? 'warn' : S.state === 'match' ? 'ok' : 'need';
  const verdict = (f.fromXml && !S.anyEmpty ? 'Из XML · ' : '') + ({ bad: 'Сумма не распознана — проверьте ввод', empty: 'Введите суммы из УПД в 1С — сверим с ДС', partial: 'Заполните все три суммы',
    diff: `Расходится с ДС на ${money(S.maxDiff)} ₽ — объясните ниже`, match: S.maxDiff ? `Расхождение ${money(S.maxDiff)} ₽ — в пределах 1 ₽` : 'Суммы совпадают с ДС ✓' })[S.state];
  const dateNote = (v, bad, w) => bad ? ['формат дд.мм.гггг', 'bad'] : w ? [w, 'warn'] : [`по ДС — ${ev.periodEnd}`, ''];
  const [invDN, invDT] = dateNote(f.invDate, ev.invDateBad, ev.invDW), [updDN, updDT] = dateNote(f.updDate, ev.updDateBad, ev.updDW);
  const bar = readOnly ? [] : ev.missing.map(m => ({ ...m })).concat(ev.warns.map(label => ({ label, tone: 'warn' })));
  const head = readOnly ? `Внесено ${msk(r.done.at).dm} — заявка в архиве` : ev.ready ? (ev.warns.length ? 'Можно вносить — проверьте:' : 'Всё на месте — можно вносить') : 'Не хватает:';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0, minHeight: 'calc(100vh - 110px)' }}>
      {/* шапка заявки */}
      <Card style={{ padding: '16px 22px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <a href="#" onClick={e => { e.preventDefault(); onOpenDeal && onOpenDeal(r.code); }} style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700 }}>{r.code}</a>
        <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.01em' }}>{r.buyer.name}</span>
        <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>ИНН {r.buyer.inn} · КПП {r.buyer.kpp}</span>
        <Chip tone={st[1]}>{st[0]}</Chip>
        <Chip tone={r.ds_signed ? 'ok' : 'warn'}>{r.ds_signed ? 'ДС подписан' : 'ДС создан, не подписан'}</Chip>
        {r.status === 'done' && <EdoChip edo={r.edo} />}
        <span style={{ fontFamily: MONO, fontSize: 12, color: r.status === 'wait' ? (tone === 'ok' ? 'var(--text-muted)' : TONE[tone].fg) : 'var(--text-muted)' }}>
          {r.status === 'wait' ? `ждёт ${ageLabel(h)} (рабочих) · с ${msk(r.since).dm}` : r.status === 'returned' ? `возвращено ${r.returned ? msk(r.returned.at).dm : ''}` : `внесено ${msk(r.done.at).dm}`}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}><Btn onClick={() => onExcel && onExcel(r.code)}>Excel пакета</Btn><Btn onClick={() => onOpenDeal && onOpenDeal(r.code)}>мастер-сделка {r.code} ↗</Btn></span>
      </Card>

      {/* п.7: пришла повторно */}
      {r.resent && r.status === 'wait' && (
        <Card style={{ padding: '12px 22px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', background: 'var(--accent-tint)', borderColor: 'var(--accent-border)' }}>
          <span style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--accent-fg)' }}>Пришла повторно · {msk(r.resent.at).dm}</span>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{r.resent.was}</span>
          <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{r.resent.changes.map(c => (
            <span key={c.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--accent-border)', fontFamily: MONO, fontSize: 12 }}>
              <span style={{ fontFamily: 'inherit', fontWeight: 700 }}>{c.label}</span><span style={{ color: 'var(--text-faint)', textDecoration: 'line-through' }}>{c.from}</span>→<span style={{ fontWeight: 700, color: 'var(--income-fg)' }}>{c.to}</span></span>))}</span>
        </Card>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.05fr) minmax(0,1fr)', gap: 14, alignItems: 'stretch' }}>
        {/* шаг 1: перенести в 1С */}
        <Card style={{ padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 14, borderColor: c1done ? 'var(--income-border)' : 'var(--border-card)' }}>
          <StepHead n="1" done={c1done} title="Перенести в 1С" sub="клик по значению — копирует"
            right={<Btn onClick={copyAll} style={{ height: 30, fontSize: 12.5, color: allCp ? 'var(--accent-fg)' : undefined, borderColor: allCp ? 'var(--accent)' : undefined, background: allCp ? 'var(--accent-tint)' : undefined }}>{allCp ? 'в буфере ✓' : 'скопировать всё одним блоком'}</Btn>} />
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.3fr)', gap: 8 }}>
            <CopyField label="ИНН покупателя" value={r.buyer.inn} hint="по нему ищем контрагента в 1С" state={cstate('inn')} onCopy={() => copy('inn', r.buyer.inn)} />
            <CopyField label="договор №" value={r.contract.no} hint={'от ' + isoToRuDate(r.contract.date)} state={cstate('ct')} onCopy={() => copy('ct', r.contract.no)} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)' }}>Основание</span><span style={{ fontSize: 12, color: 'var(--text-faint)' }}>согласовано в мастер-сделке — наименование услуги в строке УПД</span><span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{r.basis.length} зн.</span></span>
            <CopyField value={r.basis} big={false} state={cstate('basis')} onCopy={() => copy('basis', r.basis)} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)' }}>Строки УПД</span><span style={{ fontSize: 12, color: 'var(--text-faint)' }}>из ДС — так должно быть в 1С</span></span>
            {r.lines.map((l, i) => (
              <div key={i} style={{ border: '1px solid var(--border-inner)', borderRadius: 12, overflow: 'hidden' }}>
                <CopyField label="услуга" state={cstate('svc')} onCopy={() => copy('svc', l.service)} style={{ borderRadius: 0, border: 'none', borderBottom: '1px solid var(--border-inner)' }}>
                  <span style={{ fontSize: 13.5, lineHeight: 1.5 }}>{l.service}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{r.brand} · {isoToRuDate(r.period.from)} – {isoToRuDate(r.period.to)}</span>
                </CopyField>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))' }}>
                  {[['net', 'без НДС', money(l.net), 600], ['rate', 'ставка', l.vat_rate + ' %', 500], ['vat', 'НДС', money(l.vat), 600], ['gross', 'с НДС', money(l.gross), 700]].map(([k, lab, v, w]) => {
                    const can = k !== 'rate', s = can ? cstate(k) : '';
                    return <span key={k} role={can ? 'button' : undefined} tabIndex={can ? 0 : undefined} className={can ? 'ad-copy' : undefined} onClick={() => can && copy(k, v)}
                      style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', alignItems: 'flex-end', background: s === 'last' ? 'var(--accent-tint)' : can ? 'var(--bg-subtle)' : 'var(--bg-card)', borderLeft: '1px solid var(--border-inner)' }}>
                      <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}><span style={{ fontSize: 11, fontWeight: 700, color: s === 'last' ? 'var(--accent-fg)' : 'var(--text-faint)' }}>{s === 'last' ? 'в буфере' : s === 'was' ? '✓' : ''}</span><Cap>{lab}</Cap></span>
                      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: w }}>{v}</span></span>; })}
                </div>
              </div>))}
          </div>
          <div style={{ marginTop: 'auto', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 12, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
            <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{r.annex.title} от {isoToRuDate(r.annex.date)}</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 14, fontSize: 12.5, fontWeight: 700 }}>{r.ds_file_url ? <a href="#" onClick={e => { e.preventDefault(); onDsFile && onDsFile(r.code, 'ds'); }}>файл ДС</a> : <span style={{ color: 'var(--text-faint)' }}>ДС нет</span>}
              {r.ds_scan_url ? <a href="#" onClick={e => { e.preventDefault(); onDsFile && onDsFile(r.code, 'scan'); }}>скан подписанного</a> : <span style={{ color: 'var(--warning-fg)' }}>скан подписанного не приложен</span>}</span>
          </div>
        </Card>

        {/* шаги 2–3 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
          <Card style={{ padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 12, borderColor: ev.invOk ? 'var(--income-border)' : 'var(--border-card)' }}>
            <StepHead n="2" done={ev.invOk} title="Счёт" sub={ev.invOk ? `№ ${f.invNo} от ${f.invDate}` : 'номер, дата, PDF'} />
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 180px', gap: 10 }}>
              <Field label="№ счёта" note={dupRow.inv ? 'такой № уже: ' + dupRow.inv : ''} noteTone={dupRow.inv ? 'warn' : ''}><Input mono value={f.invNo} onChange={e => setF({ invNo: e.target.value })} placeholder="из 1С" readOnly={readOnly} style={{ borderColor: borderFor(dupRow.inv ? 'warn' : '') }} /></Field>
              <Field label="дата" note={invDN} noteTone={invDT}><Input mono value={f.invDate} onChange={e => setF({ invDate: e.target.value })} placeholder="дд.мм.гггг" readOnly={readOnly} style={{ borderColor: borderFor(invDT) }} /></Field>
            </div>
            <FileRow kind="PDF" label="Счёт · PDF" file={f.invPdf} required note="перетащите файл или нажмите «приложить»" readOnly={readOnly} onOpen={x => onOpenFile && onOpenFile(r.code, x)} onAttach={() => pick('invPdf')} onRemove={() => removeFile('invPdf', { invPdf: null })} />
          </Card>

          <Card style={{ padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 12, borderColor: ev.updOk ? 'var(--income-border)' : 'var(--border-card)' }}>
            <StepHead n="3" done={ev.updOk} title="УПД" sub={ev.updOk ? `№ ${f.updNo} от ${f.updDate}` : 'XML заполнит номер, дату и суммы'} />
            <FileRow kind="XML" label="УПД · XML для ЭДО" file={f.updXml} note="приложите — номер, дата и суммы заполнятся из файла" readOnly={readOnly} onOpen={x => onOpenFile && onOpenFile(r.code, x)} onAttach={() => pick('updXml')} onRemove={() => removeFile('updXml', { updXml: null, xml: null, fromXml: false })} />
            {ev.xml.on && !readOnly && (() => { const t = ev.xml.err ? TONE.bad : TONE.ok; return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px', borderRadius: 12, background: t.bg, border: `1px solid ${t.border}` }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: t.fg }}>{ev.xml.err ? 'XML не совпадает со сделкой — внести нельзя, проверьте УПД или верните аккаунту' : 'XML сверен со сделкой'}</span>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>{ev.xml.rows.map(x => (
                  <span key={x.label} style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0, gridColumn: x.label === 'основание' ? '1 / -1' : undefined }}>
                    <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}><Cap>{x.label}</Cap><span style={{ fontSize: 11.5, fontWeight: 700, color: x.ok ? 'var(--income-fg)' : 'var(--danger-fg)' }}>{x.ok ? '✓' : '≠'}</span></span>
                    <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: x.ok ? 'var(--income-fg)' : 'var(--danger-fg)' }}>{x.value}</span>
                    <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{x.ok ? 'как в сделке' : 'в сделке ' + x.want}</span></span>))}</div>
              </div>); })()}
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 180px', gap: 10 }}>
              <Field label="№ УПД" note={dupRow.upd ? 'такой № уже: ' + dupRow.upd : f.fromXml ? 'из XML' : ''} noteTone={dupRow.upd ? 'warn' : ''}><Input mono value={f.updNo} onChange={e => setF({ updNo: e.target.value })} placeholder="из 1С или XML" readOnly={readOnly} style={{ borderColor: borderFor(dupRow.upd ? 'warn' : '') }} /></Field>
              <Field label="дата" note={updDN} noteTone={updDT}><Input mono value={f.updDate} onChange={e => setF({ updDate: e.target.value })} placeholder="дд.мм.гггг" readOnly={readOnly} style={{ borderColor: borderFor(updDT) }} /></Field>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 14px', borderRadius: 12, background: sumTone === 'need' ? 'var(--bg-subtle)' : sumTone === 'warn' ? 'var(--warning-bg)' : TONE[sumTone].bg, border: `1px solid ${TONE[sumTone].border}` }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 10 }}>
                {[['net', 'без НДС'], ['vat', `НДС ${line.vat_rate} %`], ['gross', 'с НДС']].map(([k, l]) => { const v = S.vals[k], d = S.diff[k];
                  const tone = v != null && Number.isNaN(v) ? 'bad' : d && Math.abs(d) > 1 ? 'warn' : '';
                  const nt = v == null ? ['в ДС ' + money(exp[k]), ''] : Number.isNaN(v) ? ['не число', 'bad'] : d ? [(d > 0 ? '+' : '−') + money(Math.abs(d)) + ' к ДС', Math.abs(d) > 1 ? 'warn' : ''] : ['как в ДС', 'ok'];
                  return <span key={k} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><Cap>{l}</Cap>
                    <Input mono value={f[k]} onChange={e => setF({ [k]: e.target.value, fromXml: false })} placeholder="0,00" readOnly={readOnly} style={{ textAlign: 'right', borderColor: borderFor(tone) }} aria-label={'УПД ' + l} />
                    <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right', color: nt[1] === 'bad' ? 'var(--danger-fg)' : nt[1] === 'warn' ? 'var(--warning-fg)' : nt[1] === 'ok' ? 'var(--income-fg)' : 'var(--text-faint)' }}>{nt[0]}</span></span>; })}
              </div>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: sumTone === 'need' ? 'var(--text-muted)' : TONE[sumTone].fg }}>{verdict}</span>
              {S.needComment && <Input value={f.comment} onChange={e => setF({ comment: e.target.value })} readOnly={readOnly} placeholder="Почему сумма отличается от ДС — обязательно, увидит аккаунт" style={{ borderColor: f.comment.trim() ? 'var(--border-card)' : 'var(--warning)' }} />}
            </div>
            <FileRow kind="PDF" label="УПД · PDF" file={f.updPdf} required note="обязательно" readOnly={readOnly} onOpen={x => onOpenFile && onOpenFile(r.code, x)} onAttach={() => pick('updPdf')} onRemove={() => removeFile('updPdf', { updPdf: null })} />
          </Card>
        </div>

        {/* ряд 2: прошлые пакеты | обсуждение */}
        <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'minmax(0,1.05fr) minmax(0,1fr)', gap: 14, alignItems: 'stretch' }}>
          <Card style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 14, fontWeight: 700 }}>Прошлые пакеты покупателя</span><span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{past.length || ''}</span></div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', paddingBottom: 4 }}>Как вносили раньше — номера и даты для сверки</span>
            {past.map(x => (
              <div key={x.code} role="button" tabIndex={0} className="ad-row" onClick={() => select(x.code)} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: '2px 10px', padding: 8, borderRadius: 10, cursor: 'pointer', borderBottom: '1px solid var(--border-row)' }}>
                <span style={{ display: 'flex', gap: 8, alignItems: 'baseline', minWidth: 0 }}><span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)' }}>{x.code}</span><span style={{ fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{x.annex.short}</span><span style={{ fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.brand}</span></span>
                <Sum v={expectedOf(x).gross} size={12.5} />
                <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{x.done ? `сч. ${x.done.inv.no} · УПД ${x.done.upd.no} от ${x.done.upd.date}` : '—'}</span>
                <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textAlign: 'right' }}>{x.done ? 'внесено ' + msk(x.done.at).dm : ''}</span>
              </div>))}
            {!past.length && <span style={{ fontSize: 12.5, color: 'var(--text-faint)', padding: '8px 0' }}>Раньше пакетов по этому покупателю не было</span>}
          </Card>
          <Card style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 14, fontWeight: 700 }}>Обсуждение и история</span></div>
            {log.concat(systemLog(r)).map((l, i) => { const fresh = l.from_account && l.unread;
              return <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '7px 10px', margin: '0 -10px', borderRadius: 10, background: fresh ? 'var(--accent-tint)' : 'transparent', borderBottom: '1px solid var(--border-row)' }}>
                <span style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}><span style={{ fontSize: 12.5, fontWeight: 700 }}>{l.who}</span><span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{msk(l.at).dm}</span>
                  {fresh && <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--accent-fg)', background: 'var(--bg-card)', border: '1px solid var(--accent-border)', borderRadius: 5, padding: '0 5px' }}>новое</span>}</span>
                <span style={{ fontSize: 13, lineHeight: 1.45, color: l.tone ? TONE[l.tone].fg : 'var(--text-primary)' }}>{l.text}</span></div>; })}
            <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}><Input value={note} onChange={e => setNoteDraft(e.target.value)} placeholder="Вопрос аккаунту — без возврата сделки" onKeyDown={e => e.key === 'Enter' && !e.ctrlKey && !e.metaKey && sendNote()} /><Btn onClick={sendNote} style={{ height: 38 }}>Написать</Btn></div>
          </Card>
        </div>
      </div>

      {/* нижняя панель */}
      <Card style={{ position: 'sticky', bottom: 12, marginTop: 'auto', padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 14, boxShadow: 'var(--shadow-float)', zIndex: 5 }}>
        {ret.open ? <>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: '1 1 auto', animation: 'adPop 0.2s cubic-bezier(0.22,1,0.36,1) both' }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--warning-fg)' }}>Вернуть аккаунту — что исправить?</span>
            <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{RETURN_REASONS.map(x => { const on = ret.reason === x;
              return <span key={x} role="button" tabIndex={0} onClick={() => setRet(s => ({ ...s, reason: x }))} style={{ display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 11px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer', background: on ? 'var(--warning-tint)' : 'var(--bg-card)', color: on ? 'var(--warning-fg)' : 'var(--text-secondary)', border: `1px solid ${on ? 'var(--warning-border)' : 'var(--border-card)'}` }}>{x}</span>; })}</span>
            <Input value={ret.text} onChange={e => setRet(s => ({ ...s, text: e.target.value }))} placeholder="Подробно: что не так и где смотреть — увидит аккаунт" autoFocus />
          </span>
          <span style={{ display: 'flex', gap: 8, flex: '0 0 auto' }}><Btn onClick={() => setRet(s => ({ ...s, open: false }))}>Отмена</Btn>
            <Btn onClick={doReturn} disabled={!ret.reason && !ret.text.trim()} style={{ borderColor: 'var(--warning-border)', color: 'var(--warning-fg)' }}>Вернуть аккаунту</Btn></span>
        </> : <>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px 8px', flexWrap: 'wrap', flex: '1 1 0', minWidth: 0 }}>
            <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', color: readOnly || ev.ready ? 'var(--income-fg)' : 'var(--text-secondary)' }}>{head}</span>
            {bar.map(m => <span key={m.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 26, padding: '0 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, background: TONE[m.tone].bg, color: TONE[m.tone].fg }}><Dot c={TONE[m.tone].dot} /><span style={{ whiteSpace: 'nowrap' }}>{m.label}</span></span>)}
          </span>
          <span style={{ flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 10, fontFamily: MONO, fontSize: 11.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
            {!readOnly && saved && <span style={{ color: saved === 'error' ? 'var(--danger-fg)' : undefined }}>{saved === 'error' ? 'не сохранено · повторить' : 'черновик сохранён · ' + saved}</span>}
            <span title="Ctrl+Enter — внести и к следующему · ↑ ↓ — соседняя заявка · Esc — закрыть возврат" style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 8px', border: '1px solid var(--border-card)', borderRadius: 7, color: 'var(--text-muted)', cursor: 'help' }}>Ctrl+Enter · ↑↓</span>
          </span>
          {!readOnly && <span style={{ display: 'flex', gap: 8, flex: '0 0 auto' }}>
            <Btn onClick={() => setRet({ open: true, reason: r.ds_signed ? '' : 'нет подписанного ДС', text: '' })} style={{ height: 38 }}>Вернуть аккаунту</Btn>
            <Btn primary disabled={!ev.ready} onClick={submit} style={{ height: 38, padding: '0 18px' }}>Внести и к следующему →</Btn></span>}
        </>}
      </Card>
    </div>
  );
}

/* системные события в ленте: отправка, повторная отправка, возврат, внесение */
function systemLog(r) {
  const out = [];
  if (r.status === 'done' && r.done) out.push({ at: r.done.at, who: 'Бухгалтер', text: `Внесла: счёт № ${r.done.inv.no}, УПД № ${r.done.upd.no}`, tone: 'ok' });
  if (r.returned) out.push({ at: r.returned.at, who: 'Бухгалтер', text: 'Вернула: ' + r.returned.reason, tone: 'warn' });
  out.push({ at: r.since, who: 'Аккаунт', text: `${r.resent ? 'Отправил повторно' : 'Отправил пакет на закрывающие'}: ${r.annex.title}, ${money(expectedOf(r).gross)} ₽` });
  return out;
}
function EdoChip({ edo }) { /* п.9: до подключения — «не подключено» */
  if (!edo) return <Chip dashed title="Статус отправки и подписания по ЭДО появится после подключения Диадок / СБИС">ЭДО: не подключено</Chip>;
  const map = { queued: ['в очереди', 'info'], sent: ['отправлен', 'info'], delivered: ['доставлен', 'info'], signed: ['подписан покупателем', 'ok'], rejected: ['отклонён', 'bad'], error: ['ошибка', 'bad'] }[edo.status];
  return <Chip tone={map[1]} title={edo.reason || ''}>ЭДО: {map[0]}</Chip>;
}
function archiveForm(r) {
  const e = expectedOf(r), d = r.done;
  return { ...EMPTY_FORM, invNo: d.inv.no, invDate: d.inv.date, invPdf: d.inv.pdf, updNo: d.upd.no, updDate: d.upd.date, updPdf: d.upd.pdf, updXml: d.upd.xml, fromXml: true,
    net: money(e.net), vat: money(e.vat), gross: money(e.gross) };
}
function legacyCopy(text) { try { const t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0'; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); } catch (e) { /* noop */ } }
