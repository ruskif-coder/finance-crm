/**
 * Окно контрагента: заведение и проверка (десктоп ≥ 1024px). Мобайла в этой версии нет.
 *
 * Стили — inline на var(--*) из RULES_TIMON_design.md §2. Хексов нет (кроме белого текста на --accent).
 * Поля всех видов строятся из одной схемы readinessSchema.js. Алерты (`data.checks`) — с сервера.
 *
 * Пропы:
 *   data              — см. sampleData.js (контракт)
 *   onSaveBlock(block, patch) → Promise<{ data?, errors?: { [fieldKey]: string } }>
 *                       сохраняет ОДИН блок через существующие ручки; в ответ — свежие data (с checks) или ошибки ручки
 *   onUploadDocument(contractId, File) → Promise<{ name, size, uploaded_at, url }>
 *   onOpen(url)       — открыть ссылку / файл / другой экран (ОРД, карточку контрагента)
 *   onCreate(kind, values) → Promise<{ id }>   — режим заведения
 *   onModeChange(mode)
 *   onConfirmBank(bankId, { how, note }) → Promise<{ data }>      — подтвердить счёт (четыре глаза: не тот, кто менял)
 *   onUploadSignerScan(signerId, File) → Promise<{ data }>         — скан устава / доверенности
 *   onAcceptCheck(checkId, { why, till }) → Promise<{ data }>      — «принять осознанно» (только жёлтые, acceptable)
 *   onUnacceptCheck(checkId) → Promise<{ data }>
 *   onRequestClient({ to, cc, items, text }) → Promise<{ data }>   — письмо клиенту; в ответ checks с requested_at
 *   onLookupInn(inn, kpp) → Promise<{ counterparties: [], advertisers: [] }> — дубли в режиме заведения
 *
 * `data.kinds` — массив видов юрлица (агентство и площадка сразу), `data.blocks` — видимые блоки, их считает сервер
 * по видам и правам (`app/readiness/service.build`). Кнопки второго шага спецификации — подтверждение счёта, скан
 * основания, «принять осознанно», «запросить у клиента» — рисуются, только когда передан их колбэк.
 *
 * ── Примитивы ── на ките: кнопки — `btnSm`, поле — `inp`, выбор из списка — `ValuePopover`, окно — `Modal`,
 * шрифты — `MONO`/`UI`. Локально остались только обёртки над ними под размеры макета (30 px).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import ValuePopover from '@/components/ValuePopover';
import { MONO, Modal, UI as SANS, btnSm, card, inp } from '@/components/salesTableKit';
import { plural as pluralWord } from '@/components/notify/kit';
import safeHref from '@/lib/safeHref';
import { SCH, BLOCKS, KINDS, NEED_TAG, TONE, blocksForKind, blocksForKinds } from './readinessSchema';

const EASE = 'cubic-bezier(0.22,1,0.36,1)';
const plural = (n, one, few, many) => `${n} ${pluralWord(n, one, few, many)}`;

/* ═════════ примитивы на ките ═════════ */
const Cap = ({ children, style }) => (
  <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-cap)', ...style }}>{children}</span>
);
const BTN_ADD = { borderStyle: 'dashed', borderColor: 'var(--accent-border)', color: 'var(--accent-fg)' };
const Btn = ({ kind = 'ghost', onClick, children, title, style }) => (
  <button type="button" title={title} onClick={onClick}
    style={{ ...btnSm(kind === 'primary'), height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', whiteSpace: 'nowrap', ...(kind === 'add' ? BTN_ADD : {}), ...style }}>{children}</button>
);
const inputStyle = (mono, hl, err) => ({
  ...inp, height: 30, width: '100%', minWidth: 0, padding: '0 9px',
  border: `1px solid ${err ? 'var(--danger-border)' : hl ? 'var(--accent)' : 'var(--border-card)'}`, boxShadow: hl ? '0 0 0 3px var(--accent-tint)' : 'none',
  fontFamily: mono ? MONO : SANS, fontWeight: mono ? 500 : 600, fontSize: 12.5,
});
const Input = ({ value, onChange, mono, hl, err, ph, autoFocus, style }) => (
  <input value={value ?? ''} placeholder={ph} autoFocus={autoFocus} onChange={e => onChange(e.target.value)} style={{ ...inputStyle(mono, hl, err), ...style }} />
);
/** Выбор из списка — ValuePopover у места клика: значения сравниваются буквально, свободного ввода нет. */
function Choice({ value, opts, onChange, hl, err, autoFocus, title }) {
  const [rect, setRect] = useState(null);
  const ref = useRef(null);
  useEffect(() => { if (autoFocus) ref.current?.focus(); }, [autoFocus]);
  return (
    <>
      <button ref={ref} type="button" onClick={e => setRect(e.currentTarget.getBoundingClientRect())}
        style={{ ...inputStyle(false, hl, err), cursor: 'pointer', textAlign: 'left', color: value ? 'var(--text-primary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {value || '— выбрать —'}
      </button>
      {rect && <ValuePopover anchor={rect} title={title} value={value ?? null} options={opts.map(o => ({ value: o, label: o }))}
        clearLabel="— не выбрано —" onPick={v => { onChange(v || null); setRect(null); }} onClose={() => setRect(null)} />}
    </>
  );
}
const Dot = ({ color, size = 8 }) => <span style={{ width: size, height: size, borderRadius: 2, background: color, flex: `0 0 ${size}px`, display: 'inline-block' }} />;
const Pill = ({ tone, children }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', borderRadius: 8, fontSize: 11, fontWeight: 700, background: TONE[tone].bg, color: TONE[tone].fg, whiteSpace: 'nowrap' }}>
    <Dot color={TONE[tone].dot} size={6} />{children}
  </span>
);
const ClipIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
  </svg>
);
const rise = delay => ({ animation: `riseIn 0.4s ${EASE} ${delay}s both` });

/* ═════════ утилиты ═════════ */
const clone = v => JSON.parse(JSON.stringify(v ?? null));
const isEmpty = v => v === null || v === undefined || v === '';   // 0 — значимое значение, не пусто
const show = v => (isEmpty(v) ? null : String(v));
const checkUrl = id => `/directory/add?tab=check&cp=${id}`;
const resolveOpts = (opts, data) => (typeof opts === 'string' && opts[0] === '@' ? data.options?.[opts.slice(1)] ?? [] : opts);
const spanOf = it => (it.span === 4 ? '1 / -1' : it.span ? 'span 2' : 'auto');
const sevOf = (checks, block) => (checks.some(c => c.block === block && c.sev === 'bad') ? 'bad' : checks.some(c => c.block === block) ? 'warn' : 'ok');
const blockLabelOf = id => ({ cp: 'реквизиты', sg: 'подписанты', ct: 'договоры', tpl: 'шаблоны', ag: 'агентство', ad: 'рекламодатели', sk: 'СК', ord: 'ОРД' }[id] || id);
const DRAFT_OF = { cp: d => ({ counterparty: d.counterparty, banks: d.banks }), sg: d => ({ signers: d.signers }), ct: d => ({ contracts: d.contracts }), ag: d => ({ agency: d.agency }), ad: d => ({ advertisers: d.advertisers }), sk: d => ({ sk: d.sk }) };

/* ═════════ поле по схеме ═════════ */
function SchemaField({ it, value, editing, onChange, hl, err, data }) {
  const ro = it.sys != null || it.ro;
  const v = show(value) ?? (it.sys != null && it.sys !== '—' ? it.sys : null);
  const emptyFg = it.emptyTone === 'warn' ? 'var(--warning-fg)' : it.emptyTone === 'none' ? 'var(--text-disabled)' : 'var(--danger-fg)';
  const opts = resolveOpts(it.opts, data);
  return (
    <div style={{ gridColumn: spanOf(it), display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
      <Cap>{it.l}</Cap>
      {editing && !ro ? (
        opts ? <Choice value={value} opts={opts} onChange={onChange} hl={hl} err={err} autoFocus={hl} title={it.l} />
             : <Input value={value} onChange={onChange} mono={it.mono} hl={hl} err={err} ph={it.ph} autoFocus={hl} />
      ) : (
        <span title={ro && editing ? it.roWhy : v ?? ''} style={{ minHeight: editing ? 30 : 19, display: 'flex', alignItems: 'center', fontFamily: it.mono ? MONO : SANS, fontSize: 12.5, fontWeight: it.mono ? 500 : 600,
          color: ro && editing ? 'var(--text-faint)' : v ? 'var(--text-primary)' : emptyFg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {v ?? it.emptyText ?? 'не заполнено'}
        </span>
      )}
      {err && <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--danger-fg)' }}>{err}</span>}
      {editing && !err && it.hint && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{it.hint}</span>}
    </div>
  );
}

const GroupHead = ({ label, first }) => (
  <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 10, paddingTop: first ? 0 : 6 }}>
    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{label}</span>
    <span style={{ flex: '1 1 auto', height: 1, background: 'var(--border-row)' }} />
  </div>
);

/** Группы полей по схеме. src — объект значений, set(k, v) — запись в черновик. */
function SchemaGroups({ groups, src, editing, set, hl, errs, data, cols = 4 }) {
  return (
    <div className="cr-grid" style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: '10px 16px' }}>
      {groups.map(([g, items], gi) => (
        <React.Fragment key={g}>
          <GroupHead label={g} first={gi === 0} />
          {items.map(it => (
            <SchemaField key={it.k} it={it} value={src?.[it.k]} editing={editing} onChange={v => set(it.k, v)} hl={hl === it.k} err={errs?.[it.k]} data={data} />
          ))}
        </React.Fragment>
      ))}
    </div>
  );
}

/** Таблица по колонкам схемы. Один grid-template на шапку и строки, скролл — внутри. */
function SchemaTable({ cols, rows, editing, setCell, extra, minWidth = 760, hl, errs, rowTone }) {
  const ex = extra ? [].concat(extra) : [];
  const tpl = cols.map(c => c.w || 'minmax(0,1fr)').concat(ex.map(x => x.w)).join(' ');
  return (
    <div style={{ overflowX: 'auto' }}>
      <div style={{ minWidth, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'grid', gridTemplateColumns: tpl, gap: '0 12px', padding: '0 6px 6px', borderBottom: '1px solid var(--border-inner)' }}>
          {cols.map(c => <Cap key={c.k} style={{ textAlign: c.align || 'left' }}>{c.l}</Cap>)}
          {ex.map(x => <Cap key={x.l}>{x.l}</Cap>)}
        </div>
        {rows.map((r, i) => {
          const rowEdit = editing && (r._new || editing === 'all');
          return (
            <div key={r.id ?? `n${i}`} style={{ display: 'grid', gridTemplateColumns: tpl, gap: '0 12px', alignItems: 'center', padding: '7px 6px', borderBottom: '1px solid var(--border-row)', borderRadius: 8,
              background: r._new ? 'var(--accent-tint)' : 'transparent', opacity: r.archived ? 0.5 : 1 }}>
              {cols.map(c => (
                <span key={c.k} style={{ minWidth: 0, textAlign: c.align || 'left' }}>
                  {rowEdit && !c.fixed && (!c.ro || r._new) ? (   /* ro — правится только новая строка, fixed — никогда: писателя нет */
                    <Input value={r[c.k]} onChange={v => setCell(i, c.k, v)} mono={c.mono} ph={c.ph || c.l} hl={hl === `${r.id}.${c.k}`} err={errs?.[`${i}.${c.k}`]} autoFocus={hl === `${r.id}.${c.k}`} style={{ height: 28 }} />
                  ) : (
                    <span title={show(r[c.k]) ?? ''} style={{ display: 'block', fontFamily: c.mono ? MONO : SANS, fontSize: 12.5, fontWeight: c.mono ? 500 : (c === cols[0] ? 700 : 600), overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      color: show(r[c.k]) ? (rowTone?.(r, c.k) || 'var(--text-primary)') : (rowTone?.(r, c.k, true) || 'var(--text-disabled)') }}>
                      {show(r[c.k]) ?? (rowTone?.(r, c.k, true) === 'var(--danger-fg)' ? 'нет' : '—')}
                    </span>
                  )}
                </span>
              ))}
              {ex.map(x => <span key={x.l} style={{ minWidth: 0 }}>{x.render(r, i)}</span>)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Документ договора: ссылка ЭДО → файл (если есть) → скрепка. Одна строка. */
function DocumentRow({ ct, editing, canChange, set, hl, err, onUpload, onOpen }) {
  const fileRef = useRef(null);
  const link = ct.document_url, file = ct.document_file, has = !!(link || file);
  return (
    <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px', borderRadius: 12,
      background: has ? 'var(--bg-subtle)' : 'var(--warning-bg)', border: `1px solid ${has ? 'var(--border-inner)' : 'var(--warning-border)'}` }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <Cap>документ договора</Cap>
        <span style={{ fontSize: 11, color: err ? 'var(--danger-fg)' : has ? 'var(--text-faint)' : 'var(--warning-fg)' }}>
          {err || (link && file ? 'есть ссылка и файл' : file ? 'приложен файл' : link ? 'ссылка на договор в ЭДО' : 'ни ссылки, ни файла — хватит одного')}
        </span>
      </span>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        {editing ? (
          <Input value={link} onChange={v => set('document_url', v || null)} mono hl={hl} err={err} ph="https://… ссылка на договор в ЭДО" autoFocus={hl} style={{ flex: '1 1 200px', width: 'auto' }} />
        ) : (
          <span onClick={canChange ? () => onOpen('edit-link') : undefined} title={link || ''} style={{ ...inputStyle(true), flex: '1 1 200px', width: 'auto', display: 'flex', alignItems: 'center',
            color: link ? 'var(--text-primary)' : 'var(--text-disabled)', cursor: canChange ? 'text' : 'default', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>
            {link || (canChange ? 'вставьте ссылку ЭДО…' : '—')}
          </span>
        )}
        {link && !editing && <Btn onClick={() => onOpen(link)}>открыть ↗</Btn>}
        {file && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 8, height: 30, boxSizing: 'border-box', padding: '0 8px', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-inner)', minWidth: 0, maxWidth: '46%' }}>
            <span style={{ display: 'inline-flex', color: 'var(--accent-fg)' }}><ClipIcon /></span>
            <span title={file.name} style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{file.size} · {file.uploaded_at}</span>
            <a href={safeHref(file.url) || '#'} onClick={e => { e.preventDefault(); onOpen(file.url); }} style={{ fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>открыть ↗</a>
          </span>
        )}
        {canChange && (
          <>
            <Btn title="прикрепить файл договора" onClick={() => fileRef.current?.click()} style={{ width: 30, padding: 0, flex: '0 0 30px' }}><ClipIcon /></Btn>
            <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" hidden onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ''; }} />
          </>
        )}
      </div>
    </div>
  );
}

/* ═════════ блок + колонка алертов ═════════ */
const HOWS = ['звонок по номеру из договора', 'письмо с подписью руководителя', 'через ЭДО'];

function AlertCard({ c, onFix, onAccept, bank, currentUser, onConfirmBank }) {
  const t = TONE[c.sev];
  const [mode, setMode] = useState(null);               // 'accept' | 'confirm'
  const [why, setWhy] = useState(''); const [till, setTill] = useState(c.accept_till_default || '');
  const [how, setHow] = useState(''); const [note, setNote] = useState('');
  const self = bank && bank.changed_by_id === currentUser?.id;   // четыре глаза
  const isBank = !!c.fix?.confirm_bank && !!onConfirmBank;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', borderRadius: 12, background: t.bg, border: `1px solid ${t.border}` }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5, fontWeight: 700, color: t.fg }}><Dot color={t.dot} size={7} />{c.title}</span>
      {c.why && <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{c.why}</span>}
      <span style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        {onFix && <a href="#" onClick={e => { e.preventDefault(); isBank ? setMode('confirm') : onFix(c); }} style={{ fontSize: 11.5, fontWeight: 700 }}>{isBank ? 'подтвердить счёт →' : c.fix?.label || (c.fix?.link ? 'открыть экран ↗' : 'исправить →')}</a>}
        {onAccept && c.acceptable && mode !== 'accept' && <a href="#" onClick={e => { e.preventDefault(); setMode('accept'); }} style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-muted)' }}>принять осознанно…</a>}
        {c.requested_at && <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>запрошено у клиента {c.requested_at} · ждём</span>}
      </span>
      {mode === 'accept' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4, paddingTop: 8, borderTop: `1px solid ${t.border}` }}>
          <Input value={why} onChange={setWhy} ph="почему это нормально — увидят финансы и юрист" autoFocus />
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <Cap>пересмотреть</Cap><Input value={till} onChange={setTill} mono ph="дд.мм.гггг" style={{ width: 112 }} />
            <span style={{ marginLeft: 'auto' }} />
            <Btn onClick={() => setMode(null)}>Отмена</Btn>
            <Btn kind="primary" onClick={() => why.trim() && onAccept(c, { why: why.trim(), till }).then(() => setMode(null))} style={{ opacity: why.trim() ? 1 : 0.5 }}>Принять</Btn>
          </div>
        </div>
      )}
      {mode === 'confirm' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4, paddingTop: 8, borderTop: `1px solid ${t.border}` }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Как подтвердили — запишется в журнал:</span>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {HOWS.map(h => <span key={h} onClick={() => setHow(h)} style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: 'pointer',
              background: how === h ? 'var(--accent-tint)' : 'var(--bg-card)', color: how === h ? 'var(--accent-fg)' : 'var(--text-secondary)', border: `1px solid ${how === h ? 'var(--accent-border)' : 'var(--border-card)'}` }}>{h}</span>)}
          </div>
          <Input value={note} onChange={setNote} ph="кому звонили, по какому номеру, кто подтвердил" />
          {self && <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--danger-fg)' }}>реквизиты меняли вы — подтвердить должен другой сотрудник</span>}
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <Btn onClick={() => setMode(null)}>Отмена</Btn>
            <Btn kind="primary" onClick={() => how && !self && onConfirmBank(c.fix.confirm_bank, { how, note }).then(() => setMode(null))} style={{ opacity: how && !self ? 1 : 0.5 }}>Подтвердить счёт</Btn>
          </div>
        </div>
      )}
    </div>
  );
}

function AcceptedCard({ c, onUndo }) {
  const a = c.accepted;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '8px 12px', borderRadius: 12, background: 'var(--bg-subtle)', border: '1px dashed var(--border-card)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}><Dot color="var(--text-faint)" size={7} />принято · {c.title}</span>
      <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.4 }}>«{a.why}» · {a.by}, {a.at} · пересмотреть {a.till}</span>
      {onUndo && <a href="#" onClick={e => { e.preventDefault(); onUndo(c); }} style={{ fontSize: 11, fontWeight: 700, alignSelf: 'flex-start' }}>вернуть в алерты</a>}
    </div>
  );
}

/** Журнал «было → стало». Данные — аудит-лог сервера по разделу блока. */
function HistoryPanel({ items }) {
  const cols = '120px 90px minmax(160px,1fr) minmax(0,2fr)';
  return (
    <div style={{ overflowX: 'auto' }}><div style={{ minWidth: 760, display: 'flex', flexDirection: 'column', borderTop: '1px solid var(--border-row)', paddingTop: 8 }}>
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: '0 12px', padding: '0 6px 6px', borderBottom: '1px solid var(--border-inner)' }}>{['когда', 'кто', 'что', 'было → стало'].map(h => <Cap key={h}>{h}</Cap>)}</div>
      {items.map((l, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: cols, gap: '0 12px', alignItems: 'center', padding: 6, borderBottom: '1px solid var(--border-row)' }}>
          <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{l.at}</span>
          <span style={{ fontSize: 12, fontWeight: 600 }}>{l.who}</span>
          <span title={l.what} style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.what}</span>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0, fontFamily: l.mono ? MONO : SANS, fontSize: 12 }}>
            {l.from && <><span title={l.from} style={{ color: 'var(--text-faint)', textDecoration: 'line-through', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{l.from}</span><span style={{ color: 'var(--text-faint)' }}>→</span></>}
            <span title={l.to} style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{l.to}</span>
          </span>
        </div>
      ))}
    </div></div>
  );
}

/** Скан основания подписанта: файл → открыть, скрепка → загрузить. */
function ScanCell({ signer, canChange, onUpload, onOpen }) {
  const ref = useRef(null);
  const needed = /оверенн/i.test(signer.basis || '');
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      {signer.scan ? (
        <span title={signer.scan.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 26, boxSizing: 'border-box', padding: '0 8px', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-inner)', minWidth: 0, maxWidth: '100%' }}>
          <span style={{ display: 'inline-flex', color: 'var(--accent-fg)' }}><ClipIcon /></span>
          <span style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{signer.scan.name}</span>
          <a href={safeHref(signer.scan.url) || '#'} onClick={e => { e.preventDefault(); onOpen(signer.scan.url); }} style={{ fontSize: 11, fontWeight: 700 }}>↗</a>
        </span>
      ) : <span style={{ fontSize: 11.5, fontWeight: 600, color: needed ? 'var(--warning-fg)' : 'var(--text-disabled)' }}>{needed ? 'нет скана' : '—'}</span>}
      {canChange && !signer.archived && (
        <>
          <Btn title="прикрепить скан основания" onClick={() => ref.current?.click()} style={{ width: 26, height: 26, padding: 0, flex: '0 0 26px' }}><ClipIcon /></Btn>
          <input ref={ref} type="file" accept=".pdf,.jpg,.jpeg,.png" hidden onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ''; }} />
        </>
      )}
    </span>
  );
}

/** Лента «истекает в 60 дней»: 61 клетка — день, цвет по худшему событию. */
function ExpiryStrip({ items, today, onFix }) {
  const cells = Array.from({ length: 61 }, (_, d) => items.filter(x => x.days === d));
  const tone = x => (x.tone === 'warn' ? 'var(--warning)' : 'var(--text-faint)');
  return (
    <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: '260px minmax(0,1fr)', gap: 22, alignItems: 'start', paddingTop: 12, borderTop: '1px solid var(--border-row)' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <Cap>истекает в ближайшие 60 дней · {items.length}</Cap>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(61, minmax(0,1fr))', gap: 1, height: 14 }}>
          {cells.map((hit, d) => <span key={d} title={hit.length ? hit.map(x => `${x.date} · ${x.title}`).join('\n') : d ? `+${d}` : 'сегодня'}
            style={{ borderRadius: 2, background: hit.length ? (hit.some(x => x.tone === 'warn') ? 'var(--warning)' : 'var(--text-faint)') : d === 0 ? 'var(--accent-soft)' : 'var(--border-inner)' }} />)}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}><span>{today}</span><span>+30</span><span>+60</span></div>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignContent: 'flex-start' }}>
        {!items.length && <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>В ближайшие 60 дней ничего не истекает.</span>}
        {items.map((x, i) => (
          <span key={i} className="cr-sitem" onClick={() => onFix(x)} title={x.hint} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 28, padding: '0 10px', borderRadius: 8, border: '1px solid var(--border-inner)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
            <Dot color={tone(x)} size={7} />
            <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700 }}>{x.date.slice(0, 5)}</span>
            <span style={{ fontSize: 12.5, fontWeight: 600, color: x.tone === 'warn' ? 'var(--text-primary)' : 'var(--text-muted)' }}>{x.title}</span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{x.days === 0 ? 'сегодня' : `через ${plural(x.days, 'день', 'дня', 'дней')}`}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Запрос у клиента: перечень недостающего → письмо. Окно — Modal кита (подложка через overlayClose). */
function RequestModal({ items, defaultTo, intro, onSend, onClose, onCopy }) {
  const [to, setTo] = useState(defaultTo || ''); const [cc, setCc] = useState('');
  const [off, setOff] = useState({});
  const on = items.filter(x => !off[x.id]);
  const text = `Здравствуйте!\n\n${intro}, пришлите, пожалуйста:\n\n${on.length ? on.map((x, i) => `${i + 1}. ${x.title}`).join('\n') : '—'}\n\nМожно ответить на это письмо или отправить через ЭДО.\n\nС уважением,\nаккаунт-менеджер · ПРОГРАММАТИК МЕДИА`;
  return (
    <Modal title="Запросить у клиента" width={720} onClose={onClose} footer={<>
      <span style={{ marginRight: 'auto', fontSize: 11.5, color: 'var(--text-muted)' }}>Наших сумм в письме нет. Запрос попадёт в журнал, у алертов появится «запрошено».</span>
      <Btn onClick={onClose}>Отмена</Btn>
      <Btn onClick={() => onCopy(text)}>Скопировать текст</Btn>
      <Btn kind="primary" onClick={() => on.length && onSend({ to, cc, items: on.map(x => x.id), text }).then(onClose)} style={{ opacity: on.length ? 1 : 0.5 }}>Отправить</Btn>
    </>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '6px 0' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: '10px 16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><Cap>кому</Cap><Input value={to} onChange={setTo} /></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><Cap>копия</Cap><Input value={cc} onChange={setCc} ph="юрист, сейлз" /></div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Cap>что запросить · {on.length} из {items.length}</Cap>
          {items.map(x => { const sel = !off[x.id]; return (
            <div key={x.id} onClick={() => setOff(o => ({ ...o, [x.id]: !o[x.id] }))} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '8px 10px', borderRadius: 10, background: sel ? 'var(--bg-card)' : 'var(--bg-subtle)', border: '1px solid var(--border-inner)', cursor: 'pointer' }}>
              <span style={{ flex: '0 0 14px', height: 14, marginTop: 2, borderRadius: 4, boxSizing: 'border-box', border: `1px solid ${sel ? 'var(--accent)' : 'var(--border-hover)'}`, background: sel ? 'var(--accent)' : 'var(--bg-card)', color: 'var(--on-accent)', fontSize: 10, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{sel ? '✓' : ''}</span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: sel ? 'var(--text-primary)' : 'var(--text-faint)' }}>{x.title}</span>
                {x.why && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{x.why}</span>}
              </span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{x.block}</span>
            </div>); })}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Cap>текст письма</Cap>
          <div style={{ whiteSpace: 'pre-line', fontSize: 12.5, lineHeight: 1.55, padding: '12px 14px', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 12 }}>{text}</div>
        </div>
      </div>
    </Modal>
  );
}

/* ═════════ блок + колонка алертов ═════════ */
const BLOCK_META = {
  cp: { live: 'КПП — 9 цифр · ОГРН — 13 цифр · адрес не пустой · БИК — 9 цифр, р/с и к/с — 20 · ОРД увидит реквизиты при следующей отправке', why: 'ИНН не правится — от него зависят договоры и ОРД', ok: ['Реквизиты на месте', 'для ДС, ОРД и платежей хватает'] },
  sg: { live: 'ФИО, должность и основание заполнены · у доверенности есть номер и срок · подписант по умолчанию один', why: 'новую доверенность — новой строкой, старую в архив: история подписей не переписывается', ok: ['Подписанты в порядке', 'у каждого есть основание, подписант по умолчанию выбран'] },
  ct: { live: 'номер и дата есть · формат выбран → шаблон подберётся · подписанты обеих сторон · срок не прошёл · отсрочка сверена с контрагентом · есть файл или ссылка ЭДО', why: 'правка уходит в карточку договора — второго места хранения нет', ok: ['Договоры готовы к ДС', 'формат, подписанты и сроки на месте'] },
  tpl: { ok: ['Шаблоны подбираются', 'для каждого договора есть чем собрать ДС'] },
  ag: { live: 'короткое имя уникально · юрлица агентства — связка с контрагентами', why: 'короткое имя — в интерфейсе и отчётах', ok: ['Агентство заведено', 'короткое имя и холдинг есть'] },
  ad: { live: 'юр. название не пустое · ККТУ вида X.X.X из справочника · для кодов, где ОРД требует, — описание объекта рекламы', why: 'ККТУ — из справочника ОРД, только третий уровень X.X.X', ok: ['Рекламодатели и бренды готовы', 'юр. названия и ККТУ на месте — ДС и ЕРИД соберутся'] },
  sk: { live: 'на каждый договор, агентство или рекламодателя есть основное правило · срок основного не истёк', why: 'правило уходит в «Агентские условия» — здесь только строка', ok: ['СК заданы', 'у каждого договора есть основное правило'] },
  ord: { ok: ['ОРД в порядке', 'договоры зарегистрированы, незарегистрированных изначальных нет'] },
};

function BlockRow({ title, meta, delay, checks, editing, canEdit, editHint, onEdit, onCancel, onSave, saving, tools, hist, log, children, onFix, onAccept, onUnaccept, banks, currentUser, onConfirmBank, id: bid, error }) {
  const [logOpen, setLogOpen] = useState(false);
  const active = checks.filter(c => !c.accepted);
  const sev = sevOf(active, bid);
  const mine = active.filter(c => c.block === bid);
  const accepted = checks.filter(c => c.block === bid && c.accepted);
  const m = BLOCK_META[bid] || {};
  return (
    <div id={`cr-${bid}`} className="cr-pair" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 440px', gap: 14, alignItems: 'stretch', scrollMarginTop: 16, ...rise(delay) }}>
      <div style={{ ...card, padding: '16px 20px 14px', display: 'flex', flexDirection: 'column', gap: 10,
        boxShadow: editing ? '0 0 0 2px var(--accent-border), var(--shadow-float)' : 'var(--shadow-card)', borderColor: editing ? 'var(--accent-border)' : 'var(--border-card)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Dot color={TONE[sev].dot} size={9} />
          <span style={{ fontSize: 15, fontWeight: 700 }}>{title}</span>
          {meta && <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{meta}</span>}
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            {canEdit && !editing && <Btn onClick={onEdit}>✎ править</Btn>}
            {canEdit && tools?.map(t => <Btn key={t.label} kind="add" onClick={t.act}>{t.label}</Btn>)}
          </span>
        </div>
        {children}
        {editing && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end', paddingTop: 12, borderTop: '1px solid var(--border-row)' }}>
            <span style={{ marginRight: 'auto', fontSize: 12, fontWeight: error ? 700 : 400, color: error ? 'var(--danger-fg)' : 'var(--text-muted)' }}>{error || m.why}</span>
            <Btn onClick={onCancel}>Отмена</Btn>
            <Btn kind="primary" onClick={onSave}>{saving ? 'Сохраняю…' : 'Сохранить'}</Btn>
          </div>
        )}
        {(hist || log?.length > 0) && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {hist && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{hist}</span>}
            {log?.length > 0 && <a href="#" onClick={e => { e.preventDefault(); setLogOpen(o => !o); }} style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>{logOpen ? 'скрыть историю' : 'история изменений'} · {log.length}</a>}
          </span>
        )}
        {logOpen && <HistoryPanel items={log} />}
      </div>
      <div style={{ ...card, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <Cap>алерты блока</Cap>
          <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{canEdit ? 'правит: аккаунт' : editHint}</span>
        </div>
        {mine.length ? mine.map(c => <AlertCard key={c.id} c={c} onFix={onFix} onAccept={onAccept} currentUser={currentUser} onConfirmBank={onConfirmBank} bank={c.fix?.confirm_bank ? banks?.find(x => x.id === c.fix.confirm_bank) : null} />)
          : <AlertCard c={{ sev: 'ok', title: m.ok?.[0] || 'Блок в порядке', why: m.ok?.[1] }} />}
        {accepted.map(c => <AcceptedCard key={c.id} c={c} onUndo={onUnaccept} />)}
        {editing && m.live && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', borderRadius: 12, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)' }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)' }}>При сохранении проверим</span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{m.live}</span>
          </div>
        )}
      </div>
    </div>
  );
}

const SubTitle = ({ title, meta, tone, right }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
    {tone && <Dot color={TONE[tone].dot} size={7} />}
    <span style={{ fontSize: 13, fontWeight: 700 }}>{title}</span>
    {meta && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{meta}</span>}
    {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
  </div>
);
const Sub = ({ first, children, newRow }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 10, borderTop: first || newRow ? 0 : '1px solid var(--border-row)', paddingTop: first || newRow ? 0 : 12,
    ...(newRow ? { background: 'var(--accent-tint)', border: '1px dashed var(--accent-border)', borderRadius: 12, padding: 12 } : {}) }}>{children}</div>
);

/* ═════════ режим проверки ═════════ */
function CheckView({ data, onSaveBlock, onUploadDocument, onOpen, onConfirmBank, onUploadSignerScan, onAcceptCheck, onUnacceptCheck, onRequestClient }) {
  const [reqOpen, setReqOpen] = useState(false);
  const [edit, setEdit] = useState(null);      // { block, draft, hl }
  const [errs, setErrs] = useState({});
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState({});        // раскрытые свёрнутые подблоки
  const allChecks = data.checks || [];
  const checks = allChecks.filter(c => !c.accepted);
  const canEdit = sec => data.permissions?.edit?.includes(sec);
  const canView = sec => data.permissions?.view?.includes(sec);
  const D = edit ? { ...data, ...edit.draft } : data;
  const isEd = b => edit?.block === b;

  const startEdit = (block, hl, mutate) => {
    const draft = clone(DRAFT_OF[block](data));
    mutate?.(draft);
    setEdit({ block, draft, hl }); setErrs({});
    requestAnimationFrame(() => document.getElementById(`cr-${block}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };
  const setDraft = fn => setEdit(e => { const draft = clone(e.draft); fn(draft); return { ...e, draft }; });
  const cancel = () => { setEdit(null); setErrs({}); };

  /* Локально — только формат. Запреты сверх нынешних ручек окно не вводит: остальное вернёт сервер в errors. */
  const localCheck = (block, d) => {
    const e = {};
    if (block === 'cp') {
      if (d.counterparty.kpp && !/^\d{9}$/.test(d.counterparty.kpp)) e.kpp = 'КПП — 9 цифр';
      if (d.counterparty.ogrn && !/^\d{13}$|^\d{15}$/.test(d.counterparty.ogrn)) e.ogrn = 'ОГРН — 13 цифр (ОГРНИП — 15)';
      d.banks.forEach((b, i) => SCH.bank.forEach(c => { if (c.re && b[c.k] && !c.re.test(b[c.k])) e[`${i}.${c.k}`] = c.ph; }));
    }
    if (block === 'ct') d.contracts.forEach(c => { if (c.document_url && !/^https?:\/\//.test(c.document_url)) e[`${c.id}.document_url`] = 'ссылка должна начинаться с http'; });
    if (block === 'ad') d.advertisers.forEach(a => a.brands?.forEach((b, i) => { if (b.kktu && !/^\d+\.\d+\.\d+$/.test(b.kktu)) e[`${a.id}.${i}.kktu`] = 'ККТУ — вид X.X.X'; }));
    return e;
  };
  const save = async () => {
    const e = localCheck(edit.block, edit.draft);
    if (Object.keys(e).length) { setErrs(e); return; }
    setSaving(true);
    try {
      const res = await onSaveBlock(edit.block, edit.draft);
      if (res?.errors && Object.keys(res.errors).length) { setErrs(res.errors); return; }   // ручка отказала — причина у поля
      cancel();
    } finally { setSaving(false); }
  };
  const fix = c => {
    if (c.fix?.link) return onOpen(c.fix.link);
    const f = c.fix || {};
    if (f.action === 'new_poa') return addSigner(f.ref);
    if (f.action === 'upload_scan') return document.querySelector(`[data-scan="${f.ref}"] input[type=file]`)?.click();
    if (f.action === 'open_sk') return startEdit('sk');
    if (f.action === 'add_rule') return addSk(f.target);
    if (f.action === 'add_contract') return addContract();
    if (f.block === 'ct') setOpen(o => ({ ...o, [`ct${f.ref}`]: true }));
    startEdit(f.block, f.ref ? `${f.ref}.${f.field}` : f.field);
  };
  const addSigner = ref => startEdit('sg', 'new.basis', d => {
    const old = d.signers.find(s => s.id === ref);
    d.signers.push({ id: null, _new: true, _replaces: ref ?? null, name: old?.name ?? '', role: old?.role ?? '', basis: '', poa_until: '', is_default: false });
  });
  const addBank = () => startEdit('cp', null, d => d.banks.push({ id: null, _new: true, bank: '', bik: '', ks: '', rs: '', city: '', main: d.banks.length === 0 }));
  const addContract = () => startEdit('ct', 'new.number', d => d.contracts.push({ id: null, _new: true, own_company: data.contracts[0]?.own_company ?? null, annex_word: 'ДС', annex_start_no: 1, channel: 'ЭДО' }));
  const addBrand = advId => startEdit('ad', null, d => d.advertisers.find(a => a.id === advId)?.brands.push({ id: null, _new: true, name: '', kktu: '', ad_object: '', active: true }));
  const addSk = target => startEdit('sk', 'new.percent', d => d.sk.push({ id: null, _new: true, target: target ?? '', recipient: data.agency?.short_name ?? '', mode: 'постоплата', percent: '', from: '', till: '', kind: 'основная' }));
  const uploadDoc = async (ct, f) => {
    const file = await onUploadDocument(ct.id, f);
    if (isEd('ct')) setDraft(d => { d.contracts.find(x => x.id === ct.id).document_file = file; });
  };

  const sumBad = checks.filter(c => c.sev === 'bad').length, sumWarn = checks.filter(c => c.sev === 'warn').length;
  const sumAcc = allChecks.length - checks.length;
  const sumOk = Math.max(0, (data.total ?? checks.length) - sumBad - sumWarn - sumAcc);
  const reqItems = !onRequestClient ? [] : checks.filter(c => c.client_request).map(c => ({ id: c.id, title: c.client_request.title, why: c.client_request.why, block: blockLabelOf(c.block) }));
  const blockLabel = Object.fromEntries(BLOCKS.map(b => [b.id, b.title.split(' ')[0].toLowerCase()]));
  const cp = D.counterparty;
  const kinds = data.kinds || [];
  const visible = data.blocks ? BLOCKS.filter(b => data.blocks.includes(b.id)) : blocksForKinds(kinds).filter(b => canView(b.section));
  const delays = Object.fromEntries(visible.map((b, i) => [b.id, Math.min(0.14 + i * 0.07, 0.42)]));
  const ctTone = c => { const ids = checks.filter(x => x.fix?.ref === c.id || x.title.startsWith(c.number)); return ids.some(x => x.sev === 'bad') ? 'bad' : ids.length ? 'warn' : 'ok'; };

  return (
    <>
      {/* шапка */}
      <div style={{ ...card, padding: '18px 22px', display: 'flex', gap: 22, alignItems: 'center', ...rise(0) }}>
        <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Cap>контрагент · проверка готовности к документам и ОРД</Cap>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <span title={data.counterparty.name} style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.025em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{data.counterparty.name}</span>
            <Pill tone="ok">{data.counterparty.status}</Pill>
            {KINDS.filter(k => kinds.includes(k.id)).map(k => <span key={k.id} style={{ padding: '3px 9px', borderRadius: 8, fontSize: 11.5, fontWeight: 700, background: 'var(--violet-tint)', color: 'var(--violet-fg)', whiteSpace: 'nowrap' }}>{k.label}</span>)}
          </div>
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>
            <span>ИНН <b style={{ color: 'var(--text-primary)' }}>{data.counterparty.inn}</b></span>
            <span>КПП <b style={{ color: 'var(--text-primary)' }}>{data.counterparty.kpp || '—'}</b></span>
            <span style={{ fontFamily: SANS, fontSize: 12, color: 'var(--text-muted)' }}>{[data.contracts && plural(data.contracts.length, 'договор', 'договора', 'договоров'),
                data.advertisers && plural(data.advertisers.length, 'рекламодатель', 'рекламодателя', 'рекламодателей'),
                data.advertisers && plural(data.advertisers.reduce((n, a) => n + a.brands.length, 0), 'бренд', 'бренда', 'брендов')].filter(Boolean).join(' · ')}</span>
          </div>
        </div>
        <span style={{ display: 'flex', gap: 8 }}>
          {onRequestClient && <Btn onClick={() => setReqOpen(true)}>запросить у клиента<span style={{ marginLeft: 8, fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{reqItems.length}</span></Btn>}
          <Btn onClick={() => onOpen(`/directory/counterparties/${data.counterparty.id}`)}>карточка контрагента ↗</Btn>
        </span>
      </div>

      {/* сводка */}
      <div style={{ ...card, padding: '16px 22px', display: 'grid', gridTemplateColumns: '260px minmax(0,1fr)', gap: 22, alignItems: 'center', ...rise(0.07) }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Cap>сводка · {data.total ?? checks.length} проверок</Cap>
          <div style={{ display: 'flex', gap: 16, alignItems: 'baseline' }}>
            {[[sumBad, 'горит', sumBad ? 'var(--danger-fg)' : 'var(--text-disabled)'], [sumWarn, 'скоро', sumWarn ? 'var(--warning-fg)' : 'var(--text-disabled)'], [sumOk, 'ок', 'var(--income-fg)'], ...(sumAcc ? [[sumAcc, 'принято', 'var(--text-muted)']] : [])].map(([n, l, fg]) => (
              <span key={l} style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
                <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: fg }}>{n}</span>
                <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{l}</span>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 2, height: 8 }}>
            {sumBad > 0 && <span style={{ flex: `${sumBad} 0 0`, minWidth: 6, background: 'var(--danger)', borderRadius: 2 }} />}
            {sumWarn > 0 && <span style={{ flex: `${sumWarn} 0 0`, minWidth: 6, background: 'var(--warning)', borderRadius: 2 }} />}
            <span style={{ flex: `${sumOk} 0 0`, background: 'var(--income)', borderRadius: 2 }} />
          </div>
          <span style={{ fontSize: 12.5, fontWeight: 700, color: sumBad ? 'var(--danger-fg)' : sumWarn ? 'var(--warning-fg)' : 'var(--income-fg)' }}>{data.headline}</span>
        </div>
        <div className="cr-slist" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: '2px 16px' }}>
          {checks.length === 0 && <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--income-fg)' }}>Алертов нет — контрагент готов к документам и ОРД.</span>}
          {checks.map(c => (
            <span key={c.id} className="cr-sitem" onClick={() => fix(c)} title={c.why} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', borderRadius: 8, cursor: 'pointer', minWidth: 0 }}>
              <Dot color={TONE[c.sev].dot} />
              <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{blockLabel[c.block]}</span>
            </span>
          ))}
        </div>
        <ExpiryStrip items={data.expiring || []} today={data.today?.slice(0, 5)} onFix={x => fix({ fix: x.fix })} />
      </div>

      {visible.map(b => {
        const common = { id: b.id, title: b.title, delay: delays[b.id], checks: allChecks, editing: isEd(b.id), canEdit: b.editable && canEdit(b.section), editHint: b.editHint,
          onEdit: () => startEdit(b.id), onCancel: cancel, onSave: save, saving, hist: data.lastChange?.[b.id], log: data.history?.[b.id], onFix: fix,
          onAccept: onAcceptCheck && canEdit(b.section) ? (c, v) => onAcceptCheck(c.id, v) : null, onUnaccept: onUnacceptCheck && canEdit(b.section) ? c => onUnacceptCheck(c.id) : null,
          banks: data.banks, currentUser: data.currentUser, onConfirmBank, error: isEd(b.id) ? errs._ : null };
        const ed = isEd(b.id);

        if (b.id === 'cp') return (
          <BlockRow key={b.id} {...common} tools={[{ label: '+ счёт', act: addBank }]}>
            <SchemaGroups groups={SCH.cp.slice(0, 2)} src={cp} editing={ed} set={(k, v) => setDraft(d => { d.counterparty[k] = v; })} hl={edit?.hl} errs={errs} data={data} />
            <Sub>
              <SubTitle title="Банковские реквизиты" meta={String(D.banks.length)} />
              <SchemaTable cols={SCH.bank} rows={D.banks} editing={ed ? 'all' : false} minWidth={1040} errs={errs}
                setCell={(i, k, v) => setDraft(d => { d.banks[i][k] = v; })}
                extra={[{ l: '', w: '110px', render: (r, i) => r.main ? <Pill tone="ok">основной</Pill> : ed ? <a href="#" onClick={e => { e.preventDefault(); setDraft(d => d.banks.forEach((x, j) => { x.main = j === i; })); }} style={{ fontSize: 11.5, fontWeight: 700 }}>сделать основным</a> : null },
                  ...(onConfirmBank ? [{ l: 'проверка счёта', w: '150px', render: r => r._new ? <Pill tone="warn">новый</Pill> : r.confirmed ? <span title={`${r.confirmed.how} · ${r.confirmed.by}`} style={{ fontSize: 12, fontWeight: 600, color: 'var(--income-fg)' }}>подтверждён {r.confirmed.at.slice(0, 5)}</span> : <Pill tone="bad">не подтверждён</Pill> }] : [])]} />
              {ed && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>основной счёт подставляется в ДС и счета на оплату · изменённый счёт станет «не подтверждён» до проверки другим сотрудником</span>}
            </Sub>
            <Sub><SchemaGroups groups={SCH.cp.slice(2)} src={cp} editing={ed} set={(k, v) => setDraft(d => { d.counterparty[k] = v; })} hl={edit?.hl} errs={errs} data={data} /></Sub>
          </BlockRow>
        );

        if (b.id === 'sg') return (
          <BlockRow key={b.id} {...common} meta={`${D.signers.filter(s => !s.archived).length} действующих`} tools={[{ label: '+ подписант', act: () => addSigner(null) }]}>
            <SchemaTable cols={SCH.signer} rows={D.signers} editing={ed} minWidth={1040} hl={edit?.hl === 'new.basis' ? 'null.basis' : edit?.hl} errs={errs}
              setCell={(i, k, v) => setDraft(d => { d.signers[i][k] = v; })}
              rowTone={(r, k) => (k === 'poa_until' && r.poa_until && checks.some(c => c.fix?.ref === r.id) ? 'var(--warning-fg)' : null)}
              extra={[...(onUploadSignerScan ? [{ l: 'скан основания', w: 'minmax(180px,1.2fr)', render: (r, i) => (
                <span data-scan={r.id}><ScanCell signer={r} canChange={common.canEdit && (!ed || r._new)} onOpen={onOpen}
                  onUpload={f => (r._new ? onUploadDocument(null, f).then(file => setDraft(d => { d.signers[i].scan = file; })) : onUploadSignerScan(r.id, f))} /></span>) }] : []),
              { l: 'по умолч. · где подписывает', w: 'minmax(170px,1fr)', render: r => (
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  {r.is_default && <Pill tone="ok">да</Pill>}
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r._new ? 'по договору' : (r.where || []).join(', ')}</span>
                </span>) }]} />
            {ed && D.signers.some(s => s._new && s._replaces) && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>старая доверенность уйдёт в архив при сохранении</span>}
          </BlockRow>
        );

        if (b.id === 'ct') return (
          <BlockRow key={b.id} {...common} meta={plural(D.contracts.filter(c => !c._new).length, 'договор', 'договора', 'договоров')} tools={[{ label: '+ договор', act: addContract }]}>
            {D.contracts.map((c, i) => {
              const isNew = !!c._new, tone = isNew ? null : ctTone(c);
              const expanded = isNew || !c.collapsed || open[`ct${c.id}`];
              const set = (k, v, direct) => direct ? onSaveBlock('ct', { contracts: data.contracts.map(x => x.id === c.id ? { ...x, [k]: v } : x) }) : setDraft(d => { d.contracts[i][k] = v; });
              return (
                <Sub key={c.id ?? 'new'} first={i === 0} newRow={isNew}>
                  <SubTitle title={isNew ? 'Новый договор' : c.number || `договор без номера · ${c.id}`} tone={tone}
                    meta={isNew ? `с ${data.counterparty.name} · те же поля, что у действующих` : [c.date && `от ${c.date}`, c.annex_word, c.marketing_name && `«${c.marketing_name}»`].filter(Boolean).join(' · ')}
                    right={!isNew && c.collapsed && <a href="#" onClick={e => { e.preventDefault(); setOpen(o => ({ ...o, [`ct${c.id}`]: !o[`ct${c.id}`] })); }} style={{ fontSize: 12, color: 'var(--text-faint)' }}>{open[`ct${c.id}`] ? 'свернуть' : 'все поля заполнены · раскрыть'}</a>} />
                  {expanded && (
                    <div className="cr-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '10px 16px' }}>
                      {SCH.ct.map(([g, items], gi) => (
                        <React.Fragment key={g}>
                          <GroupHead label={g} first={gi === 0} />
                          {items.map(it => <SchemaField key={it.k} it={it} value={c[it.k]} editing={ed} onChange={v => set(it.k, v)} hl={edit?.hl === `${c.id ?? 'new'}.${it.k}`} err={errs[`${c.id}.${it.k}`]} data={data} />)}
                        </React.Fragment>
                      ))}
                      <DocumentRow ct={c} editing={ed} canChange={common.canEdit && (ed || c.collapsed === false)} set={set} hl={edit?.hl === `${c.id}.document_url`} err={errs[`${c.id}.document_url`]}
                        onUpload={f => uploadDoc(c, f)} onOpen={u => (u === 'edit-link' ? startEdit('ct', `${c.id}.document_url`) : onOpen(u))} />
                    </div>
                  )}
                </Sub>
              );
            })}
            {D.contracts.length === 0 && <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Договоров нет — «+ договор».</span>}
          </BlockRow>
        );

        if (b.id === 'tpl') return (
          <BlockRow key={b.id} {...common} meta="каким шаблоном соберётся ДС по каждому договору">
            <SchemaTable cols={[{ k: 'contract', l: 'договор', mono: true, w: '100px' }, { k: 'template', l: 'каким шаблоном соберётся ДС', w: 'minmax(170px,1.2fr)' }, { k: 'origin', l: 'откуда', w: '150px' }, { k: 'version', l: 'версия', mono: true, w: '60px' }, { k: 'upd_basis', l: 'основание УПД', w: '140px' }]}
              rows={data.templates} minWidth={760} rowTone={(r, k, empty) => (empty && k === 'template' ? 'var(--danger-fg)' : null)}
              extra={{ l: 'проверка', w: '120px', render: r => <Pill tone={r.check}>{r.check === 'ok' ? 'ок' : 'не подобрать'}</Pill> }} />
            {data.brandTemplates?.length > 0 && <Sub>
              <SubTitle title="Запомненные по брендам и последний ДС" />
              <SchemaTable cols={[{ k: 'brand', l: 'бренд', w: 'minmax(120px,1fr)' }, { k: 'contract', l: 'договор', mono: true, w: '100px' }, { k: 'template', l: 'шаблон', w: 'minmax(170px,1.2fr)' }, { k: 'last_annex', l: 'последний ДС', mono: true, w: '150px' }]}
                rows={data.brandTemplates} minWidth={680} extra={{ l: 'состояние', w: '100px', render: r => <Pill tone={r.state === 'у юриста' ? 'warn' : 'ok'}>{r.state}</Pill> }} />
            </Sub>}
          </BlockRow>
        );

        if (b.id === 'ag') return (
          <BlockRow key={b.id} {...common} meta={data.agency.agencies?.length > 1 ? `правится ${data.agency.short_name}` : null}>
            {data.agency.agencies?.length > 1 && (
              // одно юрлицо у нескольких агентств холдинга — у каждого свои правила СК (прод 04.11.2026: Adlabs и Havas)
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
                Это юрлицо — у {plural(data.agency.agencies.length, 'агентства', 'агентств', 'агентств')}: <b>{data.agency.agencies.map(a => a.short_name).join(', ')}</b>.
                {' '}Остальные правятся в справочнике агентств.
              </span>
            )}
            <SchemaGroups groups={SCH.ag} src={D.agency} editing={ed} set={(k, v) => setDraft(d => { d.agency[k] = v; })} hl={edit?.hl} errs={errs} data={data} />
            <Sub>
              <SubTitle title="Юрлица агентства" meta={String(data.agency.legal_entities.length)} />
              {data.agency.legal_entities.map(l => <span key={l.id ?? l.inn} style={{ fontSize: 12.5, fontWeight: 600 }}>{l.name} <span style={{ fontFamily: MONO, fontWeight: 500, color: 'var(--text-muted)' }}>· ИНН {l.inn}</span>{l.self && <span style={{ color: 'var(--text-faint)' }}> · это юрлицо</span>}</span>)}
            </Sub>
          </BlockRow>
        );

        if (b.id === 'ad') return (
          <BlockRow key={b.id} {...common} meta={`плательщик · ${D.advertisers.length}`} tools={[{ label: '+ бренд', act: () => addBrand(D.advertisers[0]?.id) }]}>
            {D.advertisers.map((a, ai) => {
              const tone = checks.some(c => c.block === 'ad' && c.sev === 'bad' && (c.fix?.ref === a.id || a.brands.some(x => x.id === c.fix?.ref))) ? 'bad' : 'ok';
              if (a.collapsed && !open[`ad${a.id}`] && !ed) return (
                <Sub key={a.id}><SubTitle title={a.short_name} meta={`ИНН ${a.inn} · ${plural(a.brands.length, 'бренд', 'бренда', 'брендов')}`} tone={tone}
                  right={<a href="#" onClick={e => { e.preventDefault(); setOpen(o => ({ ...o, [`ad${a.id}`]: true })); }} style={{ fontSize: 12, color: 'var(--text-faint)' }}>всё заполнено · раскрыть</a>} /></Sub>
              );
              return (
                <Sub key={a.id} first={ai === 0}>
                  <SubTitle title={a.short_name} meta={`ИНН ${a.inn}`} tone={tone} />
                  <SchemaGroups groups={SCH.adv} src={a} editing={ed} set={(k, v) => setDraft(d => { d.advertisers[ai][k] = v; })} hl={edit?.hl?.startsWith(`${a.id}.`) ? edit.hl.split('.')[1] : null} errs={errs} data={data} />
                  <SubTitle title={`Бренды ${a.short_name}`} meta={String(a.brands.length)} />
                  <SchemaTable cols={SCH.brand} rows={a.brands} editing={ed ? 'all' : false} minWidth={600} hl={edit?.hl} errs={errs}
                    setCell={(i, k, v) => setDraft(d => { d.advertisers[ai].brands[i][k] = v; })}
                    rowTone={(r, k, empty) => (empty && k === 'kktu' ? 'var(--danger-fg)' : empty && k === 'ad_object' && r.kktu ? 'var(--warning-fg)' : null)}
                    extra={{ l: 'активность', w: '90px', render: r => <Pill tone={r._new ? 'warn' : 'ok'}>{r._new ? 'новый' : r.active ? 'активен' : 'не активен'}</Pill> }} />
                </Sub>
              );
            })}
          </BlockRow>
        );

        if (b.id === 'sk') return (
          <BlockRow key={b.id} {...common} tools={[{ label: '+ правило', act: () => addSk() }]}>
            <SchemaTable cols={SCH.sk} rows={D.sk} editing={ed} minWidth={820} hl={edit?.hl === 'new.percent' ? 'null.percent' : null} errs={errs} setCell={(i, k, v) => setDraft(d => { d.sk[i][k] = v; })} />
          </BlockRow>
        );

        if (b.id === 'ord') return (
          <BlockRow key={b.id} {...common}>
            <Sub first>
              <SubTitle title="Доходные договоры в ОРД" />
              <SchemaTable cols={[{ k: 'contract', l: 'договор', mono: true, w: '100px' }, { k: 'kind', l: 'вид', w: 'minmax(150px,1fr)' }, { k: 'ord_id', l: 'id в ОРД', mono: true, w: '130px' }]} rows={data.ord.contracts} minWidth={640}
                rowTone={(r, k, empty) => (empty ? 'var(--danger-fg)' : null)}
                extra={{ l: 'статус · сделки', w: '230px', render: r => <span style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Pill tone={r.ord_id ? 'ok' : 'bad'}>{r.status}</Pill><span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)' }}>{plural(r.deals, 'сделка', 'сделки', 'сделок')}</span></span> }} />
            </Sub>
            <Sub>
              <SubTitle title="Изначальные договоры по рекламодателям" />
              <SchemaTable cols={[{ k: 'advertiser', l: 'рекламодатель', w: 'minmax(140px,1fr)' }, ...SCH.ordInit.map(c => ({ ...c, w: c.k === 'subject_sum' ? 'minmax(150px,1fr)' : '150px' }))]} rows={data.ord.initial} minWidth={720}
                rowTone={(r, k, empty) => (empty && k === 'number_date' ? 'var(--danger-fg)' : null)}
                extra={{ l: 'статус', w: '110px', render: r => <Pill tone={r.number_date ? 'ok' : 'bad'}>{r.status}</Pill> }} />
            </Sub>
          </BlockRow>
        );
        return null;
      })}
      {reqOpen && <RequestModal items={reqItems} defaultTo={data.counterparty.email} intro={`Чтобы оформить документы по договорам с ${data.counterparty.name}`}
        onClose={() => setReqOpen(false)} onSend={onRequestClient} onCopy={t => { try { navigator.clipboard.writeText(t); } catch (e) { /* нет доступа к буферу */ } }} />}
    </>
  );
}

/* ═════════ режим заведения: те же группы схемы, только ввод ═════════ */

/** Юрлицо при заведении (владелец 05.11.2026): новое · прикрепить существующее · без юрлица (только запись справочника). */
const CP_MODES = [
  { id: 'new', label: 'новое юрлицо' },
  { id: 'attach', label: 'прикрепить существующее' },
  { id: 'none', label: 'без юрлица', hint: 'только запись справочника — юрлицо и договор дозаполнит тот, у кого есть право' },
];

/** Поиск существующего юрлица по названию или ИНН; выбранное не переписывается — к нему только привязывается новое. */
function CpPick({ picked, onPick, onSearch }) {
  const [q, setQ] = useState('');
  const [items, setItems] = useState([]);
  const [fail, setFail] = useState('');
  useEffect(() => {
    const text = q.trim();
    setFail('');
    if (text.length < 2 || !onSearch) { setItems([]); return undefined; }
    const t = setTimeout(() => onSearch(text).then(setItems).catch(() => setFail('Поиск не ответил — попробуйте ещё раз')), 250);
    return () => clearTimeout(t);
  }, [q, onSearch]);
  if (picked) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 12, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)' }}>
      <span style={{ fontSize: 13, fontWeight: 700 }}>{picked.name}</span>
      <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>ИНН {picked.inn || '—'}</span>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>реквизиты не меняются — правятся во вкладке «Проверка»</span>
      <span style={{ marginLeft: 'auto' }}><Btn onClick={() => onPick(null)}>выбрать другое</Btn></span>
    </div>
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Input value={q} onChange={setQ} ph="название или ИНН юрлица" autoFocus />
      {fail && <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--danger-fg)' }}>{fail}</span>}
      {items.map(c => (
        <button key={c.id} type="button" onClick={() => onPick(c)}
          style={{ display: 'flex', gap: 12, alignItems: 'baseline', padding: '6px 8px', border: '1px solid var(--border-inner)', borderRadius: 8, background: 'var(--bg-card)', cursor: 'pointer', textAlign: 'left', fontFamily: SANS }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{c.name}</span>
          <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>ИНН {c.inn || '—'} · договоров {c.contracts ?? 0}</span>
        </button>
      ))}
    </div>
  );
}
function OnboardingView({ data, onCreate, onCancel, onLookupInn, onRequestClient, onUploadSignerScan, onOpen, onValidate, onSearchCounterparty }) {
  const [saving, setSaving] = useState(false);
  const [kind, setKind] = useState(data.kinds?.[0] || 'contractor');
  const [v, setV] = useState({});
  const [dups, setDups] = useState({ counterparties: [], advertisers: [] });
  const [reqOpen, setReqOpen] = useState(false);
  const set = (k, val) => setV(o => ({ ...o, [k]: val }));
  const mode = v['cp.mode'] || 'new';
  const modes = CP_MODES.filter(m => m.id !== 'none' || kind !== 'contractor');
  const attach = c => setV(o => ({ ...o, 'cp.mode': 'attach', 'cp.attach_id': c?.id ?? null, 'cp.attach_name': c?.name ?? null, 'cp.attach_inn': c?.inn ?? null }));
  const lookup = (inn, kpp) => { if (/^\d{10}$|^\d{12}$/.test(inn || '')) onLookupInn?.(inn, kpp).then(r => setDups(d => ({ ...d, ...r }))); };
  useEffect(() => { lookup(v['cp.inn'], v['cp.kpp']); }, [v['cp.inn'], v['cp.kpp']]);              // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { lookup(v['ad.inn']); }, [v['ad.inn']]);                                          // eslint-disable-line react-hooks/exhaustive-deps
  const cpSame = (dups.counterparties || []).filter(x => x.inn === v['cp.inn']);
  const cpExact = mode === 'new' ? cpSame.find(x => (x.kpp || '') === (v['cp.kpp'] || '')) : null;
  // у прямого рекламодателя ИНН — это ИНН юрлица: поле рекламодателя в заведении скрыто (ревью 05.11)
  const advInn = v['ad.inn'] || (kind === 'direct' ? v['cp.inn'] : null);
  const advSame = advInn ? (dups.advertisers || []).filter(x => x.inn === advInn) : [];
  const dupOf = id => {
    if (id === 'cp' && cpExact) return { tone: 'bad', title: 'Такой контрагент уже есть', text: `${cpExact.name} · ИНН ${cpExact.inn} · КПП ${cpExact.kpp} · ${cpExact.info}. Второй карточки на то же юрлицо быть не должно.`, acts: [{ label: 'прикрепить его', act: () => attach(cpExact) }, { label: 'открыть проверку ↗', act: () => onOpen(checkUrl(cpExact.id)) }] };
    if (id === 'cp' && cpSame.length) return { tone: 'warn', title: `С этим ИНН уже есть ${plural(cpSame.length, 'карточка', 'карточки', 'карточек')}`, text: `${cpSame.map(x => `${x.name} (КПП ${x.kpp})`).join(' · ')}. Если заводите обособленное подразделение — укажите его КПП; иначе откройте существующую.`, acts: [{ label: 'открыть ↗', act: () => onOpen(checkUrl(cpSame[0].id)) }] };
    if (id === 'ad' && advSame.length) return { tone: 'warn', title: 'Рекламодатель с этим ИНН уже заведён', text: `${advSame[0].name} · ${advSame[0].info}. Лучше привязать существующего, чем заводить второго.`, acts: [{ label: 'привязать существующего', act: () => set('ad.existing_id', advSame[0].id) }] };
    return null;
  };

  const blocks = useMemo(() => {
    const asked = it => it.sys == null && !it.fixed && !it.noNew;
    const g = (groups, pre) => groups.map(([title, items]) => [title, items.filter(asked).map(it => ({ ...it, key: pre + it.k }))]);
    const row = (title, cols, pre, extra) => [[title, cols.filter(asked).map(c => ({ ...c, key: pre + c.k, ...extra }))]];
    const out = [
      mode === 'new'
        ? { id: 'cp', groups: [...g(SCH.cp.slice(0, 2), 'cp.'), ...row('Банковские реквизиты · основной счёт', SCH.bank, 'bank.', { from: 'клиент: карточка организации', need: 'ops' }), ...g(SCH.cp.slice(2), 'cp.')] }
        : { id: 'cp', groups: [], pick: mode === 'attach' },
      mode === 'new' && { id: 'sg', groups: row('Подписант по умолчанию', SCH.signer, 'sg.', { from: 'клиент: устав или доверенность' }), scan: !!onUploadSignerScan },
      // без юрлица договора нет; у площадки от блока остаётся её часть (домен, CPM, НДС)
      mode === 'none'
        ? (kind === 'publisher' && { id: 'ct', groups: g(SCH.publisher, 'pub.'), pubOnly: true })
        : { id: 'ct', groups: [...g(SCH.ct, 'ct.'), ...(kind === 'publisher' ? g(SCH.publisher, 'pub.') : [])], doc: true },
      { id: 'ag', groups: g(SCH.ag, 'ag.') },
      { id: 'ad', groups: [...g(kind === 'direct' ? SCH.adv.map(([t, it]) => [t, it.filter(x => !['legal_name', 'inn'].includes(x.k))]) : SCH.adv, 'ad.'), ...row('Бренд', SCH.brand, 'br.', {})] },
      { id: 'sk', groups: row('Основное правило', SCH.sk, 'sk.', { from: 'сейлз: условия', need: 'ops' }) },
      { id: 'ord', groups: row('Изначальный договор рекламодателя', SCH.ordInit, 'ordi.', { from: 'клиент или агентство', need: 'erid' }) },
    ];
    const allowed = blocksForKind(kind).map(b => b.id).filter(id => mode !== 'none' || !['sk', 'ord'].includes(id));   // СК и ОРД — на договор
    return out.filter(b => b && allowed.includes(b.id));
  }, [kind, mode, onUploadSignerScan]);

  const extraItems = b => (b.doc ? [{ key: 'ct.document', l: 'ссылка на договор или файл', need: 'none', from: 'юрист: скан или ЭДО' }] : []).concat(b.scan ? [{ key: 'sg.scan', l: 'скан устава или доверенности', need: 'none', from: 'клиент: устав или доверенность' }] : []);
  const items = blocks.flatMap(b => b.groups.flatMap(([, it]) => it).concat(extraItems(b)));
  const reqItems = !onRequestClient ? [] : items.filter(it => isEmpty(v[it.key]) && /^клиент/.test(it.from || '')).map(it => ({ id: it.key, title: it.l, why: (it.from || '').replace(/^клиент:?\s*/, ''), block: blockLabelOf(it.key.split('.')[0].replace('bank', 'cp').replace('br', 'ad').replace('ordi', 'ord')) }));
  const have = items.filter(it => !isEmpty(v[it.key])).length;
  const left = it => isEmpty(v[it.key]);
  const dsLeft = items.filter(it => left(it) && (it.need || 'ds') === 'ds').length;
  const eridLeft = items.filter(it => left(it) && ['erid', 'ord'].includes(it.need)).length;
  const title = id => BLOCKS.find(b => b.id === id).title;
  // Права и формат ввода — до первой записи (ревью 05.11.2026): иначе роль без права на справочник получала
  // полусозданного контрагента, а неверная дата падала на последнем шаге после созданного договора.
  const problems = onValidate ? onValidate(kind, v) : [];

  return (
    <>
      <div style={{ ...card, padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 12, ...rise(0) }}>
        <Cap>новый контрагент · что мы должны получить</Cap>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.025em' }}>Новый контрагент · {KINDS.find(k => k.id === kind).label}</span>
          <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap', marginLeft: 'auto' }}>
            {KINDS.map(k => (
              <span key={k.id} onClick={() => setKind(k.id)} style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', borderRadius: 12, fontSize: 12, fontWeight: 700, cursor: 'pointer',
                background: kind === k.id ? 'var(--accent-tint)' : 'var(--bg-card)', color: kind === k.id ? 'var(--accent-fg)' : 'var(--text-secondary)', border: `1px solid ${kind === k.id ? 'var(--accent-border)' : 'var(--border-card)'}` }}>{k.label}</span>
            ))}
          </span>
        </div>
        <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>Блоки те же, что при проверке; чего не хватает — справа в «нужно получить». Сохранить можно и не всё: недостающее останется алертом в режиме проверки.</span>
      </div>

      <div style={{ ...card, padding: '16px 22px', display: 'grid', gridTemplateColumns: '260px minmax(0,1fr)', gap: 22, alignItems: 'center', ...rise(0.07) }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Cap>прогресс</Cap>
          <span style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
            <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--accent-fg)' }}>{have}</span>
            <span style={{ fontFamily: MONO, fontSize: 14, color: 'var(--text-faint)' }}>из {items.length}</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>есть</span>
          </span>
          <div style={{ display: 'flex', gap: 2, height: 8 }}>
            <span style={{ flex: `${have} 0 0`, background: 'var(--accent)', borderRadius: 2 }} />
            <span style={{ flex: `${items.length - have} 0 0`, background: 'var(--border-inner)', borderRadius: 2 }} />
          </div>
          <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)' }}>{have === items.length ? 'всё получено — можно сохранять' : `до первого ДС не хватает ${dsLeft} · до ЕРИД ещё ${eridLeft}`}</span>
          {reqItems.length > 0 && <a href="#" onClick={e => { e.preventDefault(); setReqOpen(true); }} style={{ fontSize: 12, fontWeight: 700, alignSelf: 'flex-start' }}>запросить у клиента недостающее · {reqItems.length}</a>}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 10 }}>
          {[['Первый ДС', dsLeft ? `не хватает ${dsLeft}` : 'можно собирать', !dsLeft], ['ЕРИД и ОРД', eridLeft ? `ещё ${eridLeft}` : 'цепочка соберётся', !eridLeft]].map(([t, s, ok]) => (
            <div key={t} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', borderRadius: 12, background: ok ? 'var(--income-tint)' : 'var(--bg-subtle)', border: `1px solid ${ok ? 'var(--income-border)' : 'var(--border-inner)'}` }}>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: ok ? 'var(--income-fg)' : 'var(--text-primary)' }}>{t}</span><span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s}</span>
            </div>
          ))}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', borderRadius: 12, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)' }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)' }}>Сохранить можно</span><span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>недостающее станет алертами в режиме проверки</span>
          </div>
        </div>
      </div>

      {blocks.map((b, bi) => {
        const its = b.groups.flatMap(([, it]) => it).concat(extraItems(b));
        const done = its.filter(it => !left(it)).length;
        const dup = dupOf(b.id), dt = dup ? TONE[dup.tone] : null;
        return (
          <div key={b.id} className="cr-pair" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 440px', gap: 14, ...rise(Math.min(0.14 + bi * 0.07, 0.42)) }}>
            <div style={{ ...card, padding: '16px 20px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Dot color={done === its.length ? 'var(--income)' : done ? 'var(--accent)' : 'var(--text-disabled)'} size={9} />
                <span style={{ fontSize: 15, fontWeight: 700 }}>{b.pubOnly ? 'Площадка' : kind === 'publisher' && b.id === 'ct' ? 'Договор площадки' : title(b.id)}</span>
                {b.id === 'cp' && (
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                    {modes.map(m => (
                      <span key={m.id} onClick={() => set('cp.mode', m.id)} title={m.hint} style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', borderRadius: 9, fontSize: 11.5, fontWeight: 700, cursor: 'pointer',
                        background: mode === m.id ? 'var(--accent-tint)' : 'var(--bg-card)', color: mode === m.id ? 'var(--accent-fg)' : 'var(--text-secondary)', border: `1px solid ${mode === m.id ? 'var(--accent-border)' : 'var(--border-card)'}` }}>{m.label}</span>
                    ))}
                  </span>
                )}
              </div>
              {b.pick && <CpPick picked={v['cp.attach_id'] ? { id: v['cp.attach_id'], name: v['cp.attach_name'], inn: v['cp.attach_inn'] } : null} onPick={attach} onSearch={onSearchCounterparty} />}
              {b.id === 'cp' && mode === 'none' && <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{CP_MODES[2].hint}.</span>}
              {dup && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 12, background: dt.bg, border: `1px solid ${dt.border}` }}>
                  <Dot color={dt.dot} />
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: dt.fg }}>{dup.title}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{dup.text}</span>
                  </span>
                  <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>{dup.acts.map(x => <Btn key={x.label} onClick={x.act}>{x.label}</Btn>)}</span>
                </div>
              )}
              <div className="cr-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '10px 16px' }}>
                {b.groups.map(([g, it], gi) => (
                  <React.Fragment key={g}>
                    <GroupHead label={g} first={gi === 0} />
                    {it.map(x => (
                      <div key={x.key} style={{ gridColumn: spanOf(x), display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                        <Cap>{x.l}</Cap>
                        {resolveOpts(x.opts, data) ? <Choice value={v[x.key]} opts={resolveOpts(x.opts, data)} onChange={val => set(x.key, val)} title={x.l} /> : <Input value={v[x.key]} onChange={val => set(x.key, val)} mono={x.mono} ph={x.ph} />}
                        {x.hint && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{x.hint}</span>}
                      </div>
                    ))}
                  </React.Fragment>
                ))}
                {b.doc && (
                  <DocumentRow ct={{ document_url: v['ct.document_url'] ?? null, document_file: v['ct.document_file'] ?? null }} editing canChange
                    set={(k, val) => setV(o => ({ ...o, [`ct.${k}`]: val, 'ct.document': val || o[k === 'document_url' ? 'ct.document_file' : 'ct.document_url'] || null }))}
                    onUpload={f => setV(o => ({ ...o, 'ct.document_file': { name: f.name, size: `${Math.round(f.size / 1024)} КБ`, uploaded_at: 'сейчас', _file: f }, 'ct.document': f.name }))} onOpen={() => {}} />
                )}
                {b.scan && (
                  <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: 3 }}>
                    <Cap>скан устава или доверенности</Cap>
                    <ScanCell signer={{ basis: v['sg.basis'] || 'доверенность', scan: v['sg.scan_file'] || null }} canChange onOpen={() => {}}
                      onUpload={f => setV(o => ({ ...o, 'sg.scan_file': { name: f.name, url: '#', _file: f }, 'sg.scan': f.name }))} />
                  </div>
                )}
              </div>
            </div>
            <div style={{ ...card, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}><Cap>нужно получить</Cap><span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{done} из {its.length}</span></div>
              {its.map(x => {
                const ok = !left(x), tag = NEED_TAG[x.need || 'ds'];
                return (
                  <div key={x.key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', borderRadius: 8, background: ok ? 'transparent' : 'var(--bg-subtle)' }}>
                    <Dot color={ok ? 'var(--income)' : 'var(--text-disabled)'} size={7} />
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: ok ? 'var(--text-faint)' : 'var(--text-primary)', textDecoration: ok ? 'line-through' : 'none' }}>{x.l}</span>
                    <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{x.from || 'клиент'}</span>
                    <span style={{ padding: '1px 6px', borderRadius: 6, fontSize: 9.5, fontWeight: 700, background: tag.bg, color: tag.fg, whiteSpace: 'nowrap' }}>{tag.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
        <span style={{ marginRight: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>Правки уходят в существующие ручки: реквизиты, подписанты, договор, бренды, СК. Своих таблиц окно не заводит.</span>
        <Btn onClick={onCancel}>Отмена</Btn>
        <Btn kind="primary" onClick={async () => {
          if (cpExact) return onOpen(checkUrl(cpExact.id));
          if (saving || problems.length) return;
          setSaving(true);
          try { await onCreate(kind, v); } finally { setSaving(false); }
        }} style={{ opacity: !cpExact && (saving || problems.length) ? 0.5 : 1 }}>
          {cpExact ? 'Такой контрагент уже есть — открыть' : saving ? 'Сохраняю…' : 'Сохранить · недостающее останется алертами'}
        </Btn>
      </div>
      {!cpExact && problems.length > 0 && (
        <div style={{ ...card, padding: '12px 18px', display: 'flex', flexDirection: 'column', gap: 4, borderColor: 'var(--danger-border)' }}>
          <Cap>до сохранения · ничего не создано</Cap>
          {problems.map(p => <span key={p} style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--danger-fg)' }}>{p}</span>)}
        </div>
      )}
      {reqOpen && <RequestModal items={reqItems} defaultTo={v['cp.email']} intro="Чтобы начать работу и оформить документы" onClose={() => setReqOpen(false)}
        onSend={payload => onRequestClient?.(payload) ?? Promise.resolve()} onCopy={t => { try { navigator.clipboard.writeText(t); } catch (e) { /* нет доступа к буферу */ } }} />}
    </>
  );
}

/* ═════════ страница ═════════ */
export default function CounterpartyReadiness({ data, onSaveBlock, onUploadDocument, onOpen, onCreate, onModeChange,
  onConfirmBank, onUploadSignerScan, onAcceptCheck, onUnacceptCheck, onRequestClient, onLookupInn, onValidateNew, onSearchCounterparty }) {
  const mode = data.mode || 'check';
  const seg = on => ({ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 12px', borderRadius: 9, fontSize: 12, fontWeight: 700, cursor: 'pointer',
    background: on ? 'var(--bg-card)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-muted)', boxShadow: on ? 'var(--shadow-card)' : 'none' });
  return (
    <div style={{ minHeight: '100vh', boxSizing: 'border-box', padding: '22px 30px 60px', display: 'flex', justifyContent: 'center', background: 'var(--bg-canvas)', fontFamily: SANS, color: 'var(--text-primary)' }}>
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(12px) } to { opacity: 1; transform: none } }
        .cr-sitem:hover { background: var(--bg-subtle) }
        @media (max-width: 1023px) { .cr-pair { grid-template-columns: minmax(0,1fr) !important } .cr-slist { grid-template-columns: minmax(0,1fr) !important } .cr-grid { grid-template-columns: repeat(2, minmax(0,1fr)) !important } }
        @media (prefers-reduced-motion: reduce) { .cr-root * { animation-duration: 1ms !important; animation-delay: 0s !important; transition: none !important } }
      `}</style>
      <div className="cr-root" style={{ width: '100%', maxWidth: 1860, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--text-muted)' }}>
          <Link href="/directory" style={{ color: 'var(--text-muted)' }}>← Справочники</Link><span style={{ color: 'var(--text-disabled)' }}>/</span>
          <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{mode === 'check' ? `${data.counterparty.name} · проверка` : 'Новый контрагент'}</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 12, padding: 3 }}>
            <span style={seg(mode === 'check')} onClick={() => onModeChange?.('check')}>Проверка</span>
            <span style={seg(mode === 'new')} onClick={() => onModeChange?.('new')}>Заведение</span>
          </span>
        </div>
        {mode === 'check'
          ? <CheckView data={data} onSaveBlock={onSaveBlock} onUploadDocument={onUploadDocument} onOpen={onOpen} onConfirmBank={onConfirmBank}
              onUploadSignerScan={onUploadSignerScan} onAcceptCheck={onAcceptCheck} onUnacceptCheck={onUnacceptCheck} onRequestClient={onRequestClient} />
          : <OnboardingView data={data} onCreate={onCreate} onCancel={() => onModeChange?.('check')} onLookupInn={onLookupInn} onRequestClient={onRequestClient} onUploadSignerScan={onUploadSignerScan} onOpen={onOpen} onValidate={onValidateNew} onSearchCounterparty={onSearchCounterparty} />}
      </div>
    </div>
  );
}
