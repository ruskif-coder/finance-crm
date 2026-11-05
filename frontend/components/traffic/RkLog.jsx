/**
 * Лог РК — журнал заметок по рекламной кампании (дашборд трафика → раскрытая РК → «Управление РК»).
 *
 * Экспорт:
 *   <RkLogTile count open onToggle />   — плитка 44×44 «Лог РК» с бейджем; ставится ПЕРЕД «Отчёт» и «Задачи»
 *   <RkLog ... />                        — окно (Modal кита, как «Задачи РК», владелец 05.11.2026): форма + фильтр + список
 *
 * Правила (не менять):
 *   • каждая заметка — отдельная запись; только добавление: ни правки, ни удаления (журнал);
 *   • новые сверху; пустую не добавить; Ctrl/⌘ + Enter — добавить;
 *   • время записи ставит сервер (todayMsk), не клиент;
 *   • лог никогда не уходит площадке (кабинет, письма, бот).
 *
 * Пропы RkLog:
 *   rkCode      — код РК, '37ZTY3'
 *   notes       — RkNote[] с сервера (см. sampleData.js), новые сверху
 *   canWrite    — право писать (трафик или аккаунт этой РК)
 *   onAdd({ kind, text }) → Promise<RkNote>  — POST; ошибка → запись остаётся в форме, показываем причину
 *   onClose()
 *
 * Перенесено из хендоффа `docs/design_handoff_rk_log.zip` (05.11.2026): шрифты и склонения — общие (`salesTableKit`,
 * `notify/kit`), белый на синем — `var(--on-accent)`. Права, время и запрет правки — на сервере (`app/ad/notes.py`).
 */
import React, { useMemo, useRef, useState } from 'react';
import { MONO, Modal, UI as SANS } from '@/components/salesTableKit';
import { plural as pluralWord } from '@/components/notify/kit';
import { TileBadge } from '@/components/traffic/dashboardKit';

export const MAX_LEN = 2000;

/** Типы записей. Цвет = смысл: серый — нейтрально, синий — договорённость (действие), красный — проблема. */
export const KINDS = {
  note:      { label: 'заметка',        dot: 'var(--text-faint)', fg: 'var(--text-muted)' },
  agreement: { label: 'договорённость', dot: 'var(--accent)',     fg: 'var(--accent-fg)' },
  problem:   { label: 'проблема',       dot: 'var(--danger)',     fg: 'var(--danger-fg)' },
};

const Dot = ({ color, size = 7 }) => <span style={{ width: size, height: size, borderRadius: 2, background: color, flex: `0 0 ${size}px`, display: 'inline-block' }} />;
const plural = (n, a, b, c) => `${n} ${pluralWord(n, a, b, c)}`;

const LogIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 3h11l3 3v15H5z" /><path d="M9 9h7M9 13h7M9 17h4" />
  </svg>
);

/* ═════════ плитка ═════════ */
export function RkLogTile({ count = 0, open = false, onToggle }) {
  return (
    <span role="button" tabIndex={0} onClick={onToggle} onKeyDown={e => e.key === 'Enter' && onToggle?.()} title="Лог РК — заметки по кампании"
      style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 5, cursor: 'pointer', userSelect: 'none' }}>
      {/* Вид — как у плиток «Отчёт» и «Задачи» (dashboardKit); открытый лог — заливкой */}
      <span style={{ position: 'relative', display: 'grid', placeItems: 'center', width: 40, height: 40, boxSizing: 'border-box', borderRadius: 10,
        background: open ? 'var(--accent)' : 'var(--accent-tint)', border: `1px solid ${open ? 'var(--accent)' : 'var(--accent-border)'}`, color: open ? 'var(--on-accent)' : 'var(--accent)',
        transition: 'background-color 150ms ease, color 150ms ease, border-color 150ms ease' }}>
        <LogIcon />
        <TileBadge n={count} />
      </span>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', whiteSpace: 'nowrap' }}>лог рк</span>
    </span>
  );
}

/* ═════════ панель ═════════ */
export default function RkLog({ rkCode, notes = [], canWrite = false, onAdd, onClose }) {
  const [text, setText] = useState('');
  const [kind, setKind] = useState('note');
  const [filter, setFilter] = useState('all');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [freshId, setFreshId] = useState(null);   // только что добавленная — подсветка --bg-tint
  const areaRef = useRef(null);

  const trimmed = text.trim();
  const tooLong = trimmed.length > MAX_LEN;
  const canSend = canWrite && !!trimmed && !tooLong && !sending;

  const shown = useMemo(() => (filter === 'all' ? notes : notes.filter(n => n.kind === filter)), [notes, filter]);
  const counts = useMemo(() => Object.fromEntries(Object.keys(KINDS).map(k => [k, notes.filter(n => n.kind === k).length])), [notes]);

  const submit = async () => {
    if (!canSend) return;
    setSending(true); setError(null);
    try {
      const saved = await onAdd({ kind, text: trimmed });
      setText(''); setKind('note'); setFilter('all'); setFreshId(saved?.id ?? null);
      areaRef.current?.focus();
    } catch (e) {
      setError(e?.message || 'Не сохранилось — текст остался в поле, попробуйте ещё раз');   // текст не теряем
    } finally { setSending(false); }
  };

  // Окно кита — как «Задачи РК»: заголовок и крестик у окна, в шапке — код сделки, число записей и правило журнала
  const summary = (
    <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
      <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{rkCode} · {plural(notes.length, 'запись', 'записи', 'записей')}</span>
      <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>записи не правятся и не удаляются — ошибку исправляют новой записью</span>
    </span>
  );
  return (
    <Modal title="Лог РК" width={820} onClose={onClose} summary={summary}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '6px 0 10px' }}>

      {/* форма */}
      {canWrite ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 12px', background: 'var(--bg-card)', borderRadius: 12,
          border: `1px solid ${error || tooLong ? 'var(--danger-border)' : 'var(--border-card)'}` }}>
          <textarea ref={areaRef} value={text} rows={2} maxLength={MAX_LEN + 200}
            onChange={e => { setText(e.target.value); if (error) setError(null); }}
            onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); } }}
            placeholder="Заметка по РК: что сделали, с кем договорились, чего ждём…"
            style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', minHeight: 52, border: 0, outline: 'none', padding: 0, background: 'transparent',
              fontFamily: SANS, fontSize: 13, lineHeight: 1.45, color: 'var(--text-primary)' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(KINDS).map(([k, v]) => {
              const on = kind === k;
              return (
                <span key={k} role="button" tabIndex={0} onClick={() => setKind(k)} onKeyDown={e => e.key === 'Enter' && setKind(k)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: 'pointer',
                    background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
                  <Dot color={v.dot} />{v.label}
                </span>
              );
            })}
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, color: tooLong ? 'var(--danger-fg)' : 'var(--text-faint)' }}>
              {tooLong ? `${trimmed.length} / ${MAX_LEN}` : 'Ctrl + Enter'}
            </span>
            <span role="button" tabIndex={0} onClick={submit} onKeyDown={e => e.key === 'Enter' && submit()}
              style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 14px', borderRadius: 12, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap',
                background: 'var(--accent)', color: 'var(--on-accent)', cursor: canSend ? 'pointer' : 'default', opacity: canSend ? 1 : 0.5 }}>
              {sending ? 'Сохраняю…' : 'Добавить запись'}
            </span>
          </div>
          {error && <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--danger-fg)' }}>{error}</span>}
        </div>
      ) : (
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Писать в лог могут трафик и аккаунт этой РК.</span>
      )}

      {/* фильтр */}
      {notes.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {[['all', 'все', notes.length], ...Object.entries(KINDS).map(([k, v]) => [k, v.label, counts[k]])].map(([k, label, n]) => {
            const on = filter === k;
            return (
              <span key={k} role="button" tabIndex={0} onClick={() => setFilter(k)} onKeyDown={e => e.key === 'Enter' && setFilter(k)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 24, padding: '0 9px', borderRadius: 8, fontSize: 11, fontWeight: on ? 700 : 600, cursor: 'pointer',
                  background: on ? 'var(--bg-card)' : 'transparent', color: on ? 'var(--text-primary)' : 'var(--text-muted)', border: `1px solid ${on ? 'var(--border-card)' : 'transparent'}` }}>
                {label}<span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span>
              </span>
            );
          })}
        </div>
      )}

      {/* список */}
      <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 420, overflow: 'auto', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12 }}>
        {shown.map(n => {
          const k = KINDS[n.kind] || KINDS.note;
          return (
            <div key={n.id} style={{ display: 'grid', gridTemplateColumns: '96px 130px minmax(0,1fr)', gap: '0 14px', alignItems: 'start', padding: '10px 14px',
              borderBottom: '1px solid var(--border-row)', background: n.id === freshId ? 'var(--bg-tint)' : 'transparent' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 1, fontFamily: MONO }}>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-primary)' }}>{n.date}</span>
                <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{n.time}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                <span title={n.author} style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.author}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600, color: k.fg }}><Dot color={k.dot} size={6} />{k.label}</span>
              </span>
              <span style={{ fontSize: 12.5, lineHeight: 1.5, color: 'var(--text-primary)', whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{n.text}</span>
            </div>
          );
        })}
        {shown.length === 0 && (
          <span style={{ padding: '18px 14px', fontSize: 12.5, color: 'var(--text-muted)' }}>
            {notes.length ? 'Под фильтр записей нет.' : 'Записей пока нет — первая заметка появится здесь.'}
          </span>
        )}
      </div>
    </div>
    </Modal>
  );
}
