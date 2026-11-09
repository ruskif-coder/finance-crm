// «Ещё не дошли» (владелец 09.11.2026: «все что после итоговой сверки»): сделки закрываемого месяца со стадии «Итоговая сверка»
// и дальше, чьи документы до бухгалтера ещё не дошли. Объём оставшейся работы по закрытию; только чтение. Данные — `board.upstream`
// (`backend/app/onec_desk/upstream.py`).
import React from 'react';
import { createPortal } from 'react-dom';
import { Modal, th, td, MONO } from '../salesTableKit';
import { plural } from '@/lib/publisherRecon.mjs';

const BUCKETS = [['recon', 'на итоговой сверке', 'сверка не отправлена в ДО'], ['draft', 'пакет в черновике', 'собирают документы'],
  ['agree', 'на согласовании', 'ДС у клиента']];
const deals = n => `${n} ${plural(n, 'сделка', 'сделки', 'сделок')}`;

/** Строка под плашкой срока: «ещё не дошли: 28 сделок · на сверке 13 · …». Пусто — ничего не рисуем. */
export function UpstreamLine({ up, onOpen }) {
  if (!up || !up.total) return null;
  const parts = BUCKETS.filter(([k]) => up.counts[k]).map(([k, l]) => `${l.replace('на итоговой сверке', 'сверка')} ${up.counts[k]}`);
  return (
    <div role="button" tabIndex={0} onClick={onOpen} onKeyDown={e => e.key === 'Enter' && onOpen()} title="Ещё не дошли до бухгалтерии — список"
      style={{ display: 'flex', alignItems: 'baseline', gap: 6, margin: '6px 4px 0', padding: '5px 11px', borderRadius: 10, cursor: 'pointer', border: '1px dashed var(--border-card)', fontSize: 12, color: 'var(--text-muted)' }}>
      <span style={{ fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>ещё не дошли: {deals(up.total)}</span>
      <span style={{ fontFamily: MONO, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{parts.join(' · ')}</span>
    </div>
  );
}

/** Окно со списком: по группам, кто ведёт и где застряло. */
// В портал: окно рисуется из колонки очереди, а её слой ниже нижней панели заявки — панель ложилась поверх окна.
export function UpstreamModal({ up, month, onClose }) {
  return createPortal(
    <Modal title={`Ещё не дошли за ${month || up.month}: ${deals(up.total)}`} width={820} onClose={onClose}
      summary="Сделки со стадии «Итоговая сверка» и дальше, документы которых ещё не пришли в очередь. Появятся, когда пакет дойдёт до «ждём 1С».">
      {BUCKETS.filter(([k]) => up.counts[k]).map(([k, label, hint]) => (
        <div key={k} style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '8px 0 6px' }}>
            <span style={{ fontSize: 13.5, fontWeight: 800 }}>{label}</span>
            <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{deals(up.counts[k])}{up.packages && up.packages[k] ? ` · пакетов ${up.packages[k]}` : ''} · {hint}</span>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr><th style={{ ...th, width: 70 }}>код</th><th style={th}>сделка</th><th style={{ ...th, width: 90 }}>пакет</th><th style={{ ...th, width: 170 }}>стадия</th><th style={{ ...th, width: 150 }}>аккаунт</th></tr></thead>
            <tbody>{up.deals.filter(x => x.bucket === k).map(x => (
              <tr key={x.deal_id}>
                <td style={{ ...td, fontFamily: MONO, fontSize: 12 }}>{x.code || '—'}</td>
                <td style={td}>{x.title || x.client || '—'}</td>
                <td style={{ ...td, fontFamily: MONO, fontSize: 12 }}>{x.package || '—'}</td>
                <td style={{ ...td, color: 'var(--text-secondary)' }}>{x.stage}</td>
                <td style={{ ...td, color: 'var(--text-secondary)' }}>{x.account || '—'}</td>
              </tr>))}</tbody>
          </table>
        </div>))}
    </Modal>, document.body);
}
