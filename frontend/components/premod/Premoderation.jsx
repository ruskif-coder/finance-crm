/**
 * «Трафики → Премодерация» (/traffic/premoderation). Эталон вида и поведения — reference/Премодерация.dc.html
 * в docs/design_handoff_premoderation.zip. Перенесено дословно, кроме правок владельца 08.11.2026:
 * проверки — от сервера; у статики (и HTML5 без текста в разметке) вместо распознанного текста —
 * увеличенная нижняя полоса; веса, длительности анимации и снимка PNG при решении нет (отдельный этап).
 * Режим демо: решения сохраняются только у нас, в SSP не отправляются (README §1).
 *
 * Пропы:
 *   data                                — ответ GET /api/traffic/premod (контракт — sampleData.js)
 *   onDecide(pkgId, decision)           — { verdict: 'approved'|'declined', request_ids, reason_code?, comment?, repeat } → Promise<Decision>
 *   onBulkApprove(pkgIds)               — массовое одобрение пакетов без нарушений → Promise<Decision[]>
 *   onOpenSnapshot(url)                 — открыть сохранённый PNG решения
 *   onSetCategory(inn, category|null)   — категория заказчика (владелец 09.11.2026: выбор в карточке пакета)
 *   renderCreative(pkg, { w, h, replayKey })  — превью креатива; по умолчанию iframe песочницы pkg.snapshot_url
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ageOf, msk, plural, parseLanding, requestError, defaultChecked, checksOf, verdictOf, isClean, trustOf, sspWaits, placeName, sortQueue, groupQueue, matches, FILTERS, SUGGEST_BY_CHECK } from './premodLogic';
import { STYLE, MONO, TONE, Cap, Card, Dot, Btn, Chip, Pip, Check, Segmented, CHECK_MARK } from './premodParts';
import { card, Z, PickValue } from '@/components/salesTableKit';
import ValuePopover from '@/components/ValuePopover';
import { overlayClose } from '@/lib/overlay';

const LIMIT = 6;   // заявок видно сразу, остальные — «показать ещё»
const FG = { warning: 'var(--warning)', accent: 'var(--accent)', income: 'var(--income)', danger: 'var(--danger)' };
const AGE_FG = { ok: ['var(--text-muted)', 'var(--text-faint)'], warn: ['var(--warning-fg)', 'var(--warning)'], bad: ['var(--danger-fg)', 'var(--danger)'] };

export default function Premoderation({ data, onDecide, onBulkApprove, onOpenSnapshot, onSetCategory, renderCreative }) {
  const A = data.advertisers, P = data.places;
  const [pkgs, setPkgs] = useState(data.packages);           // локально применяем решения до перезагрузки
  useEffect(() => setPkgs(data.packages), [data.packages]);
  const [filter, setFilter] = useState('wait');
  const [ssp, setSsp] = useState('all');
  const [q, setQ] = useState('');
  const [groupBy, setGroupBy] = useState('adv');
  const [sel, setSel] = useState(null);
  const [checked, setChecked] = useState({});                // pkgId → { uuid: bool }
  const [urlOpen, setUrlOpen] = useState({});
  const [more, setMore] = useState({});
  const [multi, setMulti] = useState({});
  const [rej, setRej] = useState({ open: false, code: '', comment: '' });
  const [replay, setReplay] = useState(0);
  const [toast, setToast] = useState('');
  const tT = useRef(); const say = t => { setToast(t); clearTimeout(tT.current); tT.current = setTimeout(() => setToast(''), 2000); };

  const inFilter = (p, f) => p.status === f;
  const passSsp = p => ssp === 'all' || sspWaits(p);
  const list = useMemo(() => sortQueue(pkgs.filter(p => inFilter(p, filter) && passSsp(p) && (!q.trim() || matches(p, A[p.advertiser], q)))), [pkgs, filter, ssp, q]); // eslint-disable-line
  const groups = useMemo(() => groupQueue(list, groupBy), [list, groupBy]);
  const nav = useMemo(() => [...new Set(groups.flatMap(g => g.items.map(p => p.id)))], [groups]);
  const p = list.find(x => x.id === sel) || list[0];
  const canAct = !!p && (p.status === 'wait' || p.status === 'changed');
  const decidable = data.can_decide && canAct;

  /* ── выбранный пакет ── */
  const adv = p && A[p.advertiser];
  const checks = p ? checksOf(p, adv) : [];
  const ck = p ? (checked[p.id] || defaultChecked(p)) : {};
  const v = p ? verdictOf(p, checks, ck) : null;
  const setCk = (fn) => setChecked(s => ({ ...s, [p.id]: Object.fromEntries(p.requests.map(r => [r.uuid, fn(r)])) }));
  const nextAfter = id => nav.filter(x => x !== id).find(x => { const pk = pkgs.find(y => y.id === x); return pk && pk.status === 'wait'; });
  const apply = (id, status, decision) => setPkgs(s => s.map(x => x.id === id ? { ...x, status, decisions: [decision, ...x.decisions] } : x));

  const approve = async () => { if (!decidable || !v.nChecked) return;
    const body = { verdict: 'approved', request_ids: p.requests.filter(r => ck[r.uuid]).map(r => r.uuid), repeat: !!(p.same_creative || p.prev) };
    let d; try { d = await onDecide(p.id, body); } catch (e) { say(e.message); return; } apply(p.id, 'approved', d); const nx = nextAfter(p.id); setSel(nx || p.id);
    say(`Одобрено ${v.nChecked} из ${p.requests.length} · ${adv.short} ${p.size || p.size_guess}${nx ? ' — открыт следующий' : ''}`); };
  const decline = async () => { if (!rej.code) return;
    const reason = data.reasons.flatMap(g => g.items).find(x => x.code === rej.code);
    const body = { verdict: 'declined', request_ids: p.requests.filter(r => ck[r.uuid]).map(r => r.uuid), reason_code: rej.code, comment: rej.comment.trim(), repeat: !!(p.same_creative || p.prev) };
    let d; try { d = await onDecide(p.id, body); } catch (e) { say(e.message); return; }
    apply(p.id, 'declined', { ...d, reason: reason.label }); setRej({ open: false, code: '', comment: '' }); const nx = nextAfter(p.id); setSel(nx || p.id);
    say(`Отклонено · ${adv.short} ${p.size || p.size_guess}${nx ? ' — открыт следующий' : ''}`); };
  const groupClean = p ? pkgs.filter(x => x.advertiser === p.advertiser && x.status === 'wait' && isClean(x, A[x.advertiser])) : [];
  const bulk = async ids => { if (!ids.length || !data.can_decide) return 0;
    let ds; try { ds = await onBulkApprove(ids); } catch (e) { say(e.message); return 0; }
    setPkgs(s => s.map(x => { const i = ids.indexOf(x.id); return i < 0 ? x : { ...x, status: 'approved', decisions: [ds[i], ...x.decisions] }; })); return ids.length; };

  const setCategory = async (inn, category) => {
    try { await onSetCategory(inn, category); say('Категория сохранена — проверки пересчитаны'); } catch (e) { say(e.message); } };

  /* п.15: клавиши */
  const keys = useRef(); keys.current = { approve, openRej: () => decidable && setRej({ open: true, code: '', comment: '' }), nav, sel: p && p.id, rejOpen: rej.open };
  useEffect(() => { const h = e => { const k = keys.current, inField = /INPUT|TEXTAREA|SELECT/.test(e.target.tagName);
      if (e.key === 'Escape') { setRej(s => ({ ...s, open: false })); return; }
      if (inField || k.rejOpen || e.ctrlKey || e.metaKey || e.altKey) return; const key = e.key.toLowerCase();
      if (key === 'a' || key === 'ф') { e.preventDefault(); k.approve(); }
      else if (key === 'r' || key === 'к') { e.preventDefault(); k.openRej(); }
      else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && k.nav.length) { e.preventDefault(); const i = k.nav.indexOf(k.sel);
        setSel(k.nav[Math.max(0, Math.min(k.nav.length - 1, i < 0 ? 0 : i + (e.key === 'ArrowDown' ? 1 : -1)))]); } };
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);

  /* ── подписи ── */
  const mSel = pkgs.filter(x => multi[x.id] && (x.status === 'wait' || x.status === 'changed')), mClean = mSel.filter(x => isClean(x, A[x.advertiser]));
  const sy = data.sync;

  return (
    <div className="pm-root" style={{ minHeight: '100vh', boxSizing: 'border-box', padding: '20px 26px', background: 'var(--bg-canvas)', display: 'flex', justifyContent: 'center' }}>
      <style>{STYLE}</style>
      <div style={{ width: '100%', maxWidth: 2500, display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', animation: 'pmRise 0.4s cubic-bezier(0.22,1,0.36,1) both' }}>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em' }}>Премодерация</span>
              <Chip tone="warn" title="Решения сохраняются только у нас, в SSP не отправляются" style={{ fontSize: 12, padding: '3px 9px' }}>демо</Chip>
              <span title={sy.error ? `Крон app.premod.sync: ${sy.error.message}. Очередь может быть неполной.` : `Последний запуск: забрано ${sy.fetched}, новых ${sy.new}`}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 9px', borderRadius: 8, background: sy.error ? 'var(--danger-tint)' : 'var(--bg-card)', color: sy.error ? 'var(--danger-fg)' : 'var(--text-muted)', fontFamily: MONO, fontSize: 11.5, fontWeight: 700 }}>
                <Dot c={sy.error ? 'var(--danger)' : 'var(--income)'} />{sy.error ? `синхронизация не прошла ${msk(sy.error.at).hm} · повтор ${msk(sy.error.retry_at).hm} · данные на ${msk(sy.last_at).hm}` : `синхронизация ${msk(sy.last_at).hm} · следующая ${msk(sy.next_at).hm}`}</span>
            </span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>креативы SSP пакетами · синхронизация раз в 10 мин · решения в SSP не отправляются</span>
          </span>
          <span role="tablist" style={{ display: 'inline-flex', gap: 6, marginLeft: 18 }}>
            {FILTERS.map(([k, label, tone]) => { const on = filter === k, n = pkgs.filter(x => inFilter(x, k) && passSsp(x)).length;
              return <span key={k} role="tab" aria-selected={on} tabIndex={0} onClick={() => setFilter(k)} onKeyDown={e => e.key === 'Enter' && setFilter(k)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, boxSizing: 'border-box', padding: '0 14px', borderRadius: 12, fontSize: 13, fontWeight: on ? 700 : 600, cursor: 'pointer', background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
                <Dot c={FG[tone]} s={7} />{label}<span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: on ? 'var(--accent-fg)' : n ? 'var(--text-muted)' : 'var(--text-disabled)' }}>{n}</span></span>; })}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}><Cap>у SSP</Cap>
            <Segmented value={ssp} onChange={setSsp} options={[['all', 'все', pkgs.filter(x => inFilter(x, filter)).length], ['wait', 'у SSP ждут', pkgs.filter(x => inFilter(x, filter) && sspWaits(x)).length]]} /></span>
          <span style={{ marginLeft: 'auto', width: 340 }}><input className="pm-in" value={q} onChange={e => setQ(e.target.value)} placeholder="⌕  Заказчик, ИНН, ЕРИД или crid" aria-label="Поиск" /></span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '500px minmax(0,1fr)', gap: 14, alignItems: 'start', animation: 'pmRise 0.4s cubic-bezier(0.22,1,0.36,1) 0.07s both' }}>
          {/* ═════ очередь ═════ */}
          <Card style={{ padding: '12px 12px 10px', display: 'flex', flexDirection: 'column', gap: 6, position: 'sticky', top: 14, maxHeight: 'calc(100vh - 110px)', boxSizing: 'border-box' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '2px 6px 4px' }}>
              <span style={{ fontSize: 14, fontWeight: 700 }}>{FILTERS.find(f => f[0] === filter)[1]}{ssp === 'wait' ? ' · у SSP ждут' : ''}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{list.length} пакет. · {list.reduce((s, x) => s + x.requests.length, 0)} заяв. · {new Set(list.map(x => x.advertiser)).size} заказч.</span>
            </div>
            <div style={{ padding: '0 4px 2px' }}><Segmented inCard value={groupBy} onChange={setGroupBy} options={[['adv', 'по рекламодателям'], ['place', 'по площадкам']]} /></div>
            {mSel.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 4px', padding: '7px 10px', borderRadius: 10, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', animation: 'pmPop 0.16s cubic-bezier(0.22,1,0.36,1) both' }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)' }}>Отмечено {mSel.length}{mSel.length > mClean.length ? ' · с нарушениями ' + (mSel.length - mClean.length) : ''}</span>
                <span role="button" tabIndex={0} onClick={() => setMulti({})} style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', cursor: 'pointer' }}>снять</span>
                <Btn kind="p" disabled={!mClean.length || !data.can_decide} title={mSel.length > mClean.length ? 'С нарушениями останутся в очереди: ' + mSel.filter(x => !mClean.includes(x)).map(x => A[x.advertiser].short + ' ' + (x.size || x.size_guess)).join(', ') : 'Все отмеченные без нарушений'}
                  onClick={async () => { const n = await bulk(mClean.map(x => x.id)); if (!n) return; setMulti({}); say(`Одобрено пакетов: ${n}${mSel.length > mClean.length ? ' · с нарушениями оставлены: ' + (mSel.length - mClean.length) : ''}`); }}
                  style={{ marginLeft: 'auto', height: 28, fontSize: 12 }}>Одобрить чистые · {mClean.length}</Btn>
              </div>)}
            <div style={{ display: 'flex', flexDirection: 'column', overflow: 'auto', minHeight: 0 }}>
              {groups.map(g => <QueueGroup key={g.kind + g.key} g={g} A={A} P={P} now={data.now} selId={p && p.id} multi={multi} setMulti={setMulti} onPick={setSel} />)}
              {!list.length && <div style={{ padding: '40px 16px', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>{filter === 'wait' && !q ? 'Всё разобрано — новые пакеты появятся после синхронизации' : 'Нет пакетов под фильтр'}</div>}
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-faint)', padding: '4px 6px 0', lineHeight: 1.45 }}>Ожидание — с момента, как заявку создали в SSP. Жёлтое — больше 4 ч, красное — больше суток. <b>SSP ждёт</b> — у SSP не решено, <b>!</b> — нарушение в проверках.</span>
          </Card>

          {/* ═════ карточка пакета ═════ */}
          {!p ? <Card style={{ padding: '60px 20px', textAlign: 'center', fontSize: 14, color: 'var(--text-muted)' }}>Выберите пакет слева</Card> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0, minHeight: 'calc(100vh - 110px)' }}>
              <PackageHead p={p} adv={adv} now={data.now} canEdit={data.can_decide && !!onSetCategory} categories={data.categories || []} onSetCategory={setCategory} />
              {p.same_creative && (
                <Card style={{ padding: '11px 22px', display: 'flex', alignItems: 'center', gap: 10, background: 'var(--accent-tint)', borderColor: 'var(--accent-border)' }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-fg)' }}>Этот креатив уже решён</span>
                  <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>тот же баннер одобрил {p.same_creative.by} {msk(p.same_creative.at).dm} по заявке {p.same_creative.request} ({p.same_creative.note})</span>
                </Card>)}
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,3fr) minmax(0,2fr)', gap: 14, alignItems: 'stretch' }}>
                <CreativeCard p={p} adv={adv} checks={checks} pkgs={pkgs} A={A} onPick={setSel} replay={replay} onReplay={() => setReplay(x => x + 1)} renderCreative={renderCreative} onOpenSnapshot={onOpenSnapshot} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
                  <ChecksCard checks={checks} n={p.requests.length} />
                  <RequestsCard p={p} P={P} ck={ck} setCk={setCk} toggle={uuid => setChecked(s => ({ ...s, [p.id]: { ...ck, [uuid]: !ck[uuid] } }))} urlOpen={urlOpen} setUrlOpen={setUrlOpen} showAll={!!more[p.id]} toggleMore={() => setMore(s => ({ ...s, [p.id]: !s[p.id] }))} />
                  <HistoryCard p={p} onOpenSnapshot={onOpenSnapshot} />
                </div>
              </div>

              {/* решение */}
              <Card style={{ position: 'sticky', bottom: 12, marginTop: 'auto', padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', boxShadow: 'var(--shadow-float)', zIndex: 5 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px 8px', flexWrap: 'wrap', flex: '1 1 0', minWidth: 0 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', color: !canAct ? 'var(--text-secondary)' : v.risky ? 'var(--danger-fg)' : v.nWarn ? 'var(--warning-fg)' : 'var(--income-fg)' }}>
                    {!canAct ? (p.status === 'approved' ? 'Одобрено' : 'Отклонено') + (p.decisions[0] ? ` · ${p.decisions[0].by} · ${msk(p.decisions[0].at).dm}` : '')
                      : v.risky ? 'Нарушения — лучше отклонить:' : v.nBad ? 'Заявки с нарушениями не выбраны · посмотрите:' : v.nWarn ? 'Посмотрите:' : 'Проверки в порядке'}</span>
                  {canAct && checks.filter(c => (c.state === 'bad' && (c.key !== 'erid' || v.badChecked)) || c.state === 'warn').map(c =>
                    <span key={c.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 26, padding: '0 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, background: TONE[c.state].bg, color: TONE[c.state].fg, whiteSpace: 'nowrap' }}><Dot c={TONE[c.state].dot} />{c.title}</span>)}
                </span>
                <span style={{ fontSize: 11.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{data.can_decide ? 'решение сохраняется только у нас' : 'нет права на решения — только просмотр'}</span>
                {canAct && <>
                  {groupClean.length > 1 && <Btn disabled={!data.can_decide} title={'Одобрить пакеты заказчика без нарушений: ' + groupClean.map(x => x.size || x.size_guess).join(', ')} onClick={async () => { const n = await bulk(groupClean.map(x => x.id)); if (!n) return; say(`Одобрено пакетов: ${n} · ${adv.short}`); }}>Одобрить чистые размеры кампании · {groupClean.length}</Btn>}
                  <Btn kind={v.risky ? 'd' : undefined} disabled={!decidable} onClick={() => setRej({ open: true, code: '', comment: '' })}>Отклонить… <span className="pm-kbd">R</span></Btn>
                  <Btn kind={v.risky ? undefined : 'p'} disabled={!decidable || !v.nChecked} onClick={approve}>{v.risky ? 'Одобрить несмотря на нарушения' : `Одобрить ${v.nChecked} из ${p.requests.length} и к следующему`} <span className="pm-kbd">A</span></Btn>
                </>}
              </Card>
            </div>)}
        </div>
      </div>

      {rej.open && p && <RejectModal data={data} p={p} adv={adv} checks={checks} v={v} rej={rej} setRej={setRej} onSubmit={decline} />}
      {toast && <div role="status" style={{ position: 'fixed', right: 24, bottom: 150, background: 'var(--text-primary)', color: 'var(--bg-card)', padding: '11px 16px', borderRadius: 12, fontSize: 13, fontWeight: 600, boxShadow: 'var(--shadow-float)', animation: 'pmRise 0.24s cubic-bezier(0.22,1,0.36,1) both', zIndex: Z.toast }}>{toast}</div>}
    </div>
  );
}

/* ───────── очередь ───────── */
function QueueGroup({ g, A, P, now, selId, multi, setMulti, onPick }) {
  const isPlace = g.kind === 'place', ps = g.items;
  const nBad = ps.filter(x => !isClean(x, A[x.advertiser])).length, nSsp = ps.filter(x => sspWaits(x, isPlace ? g.key : null)).length;
  const nReq = ps.reduce((s, x) => s + (isPlace ? x.requests.filter(r => String(r.acc) === g.key).length : x.requests.length), 0);
  const head = isPlace ? placeName(P, g.key) : A[g.key].short;
  const sub = isPlace ? `учётка SSP ${g.key} · ${P[g.key] && P[g.key].name ? 'черновик' : 'не сопоставлена'} · ${ps.length} ${plural(ps.length, 'пакет', 'пакета', 'пакетов')} · ${nReq} заяв.`
    : `ИНН ${A[g.key].inn} · ${A[g.key].category || 'категория не задана'} · ${ps.length} ${plural(ps.length, 'пакет', 'пакета', 'пакетов')} · ${nReq} заяв.`;
  return (<>
    <div role="button" tabIndex={0} className="pm-row" onClick={() => onPick(ps[0].id)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 8px 6px', borderRadius: 10, cursor: 'pointer' }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, flex: '1 1 auto' }}>
        <span style={{ fontSize: 13, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{head}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sub}</span>
      </span>
      {nSsp > 0 && <Pip kind="flag" title="Пакетов, где у SSP заявки ещё не решены">SSP ждёт {nSsp}</Pip>}
      {nBad > 0 && <Pip kind="bad" title="Пакетов с нарушениями">! {nBad}</Pip>}
    </div>
    {ps.map(x => <QueueRow key={x.id} p={x} adv={A[x.advertiser]} P={P} acc={isPlace ? g.key : null} now={now} sel={x.id === selId} marked={!!multi[x.id]}
      onMark={e => { e.stopPropagation(); if (x.status === 'wait' || x.status === 'changed') setMulti(s => ({ ...s, [x.id]: !s[x.id] })); }} onPick={() => onPick(x.id)} />)}
  </>);
}
function QueueRow({ p, adv, P, acc, now, sel, marked, onMark, onPick }) {
  const ag = ageOf(p, now), checks = checksOf(p, adv), nb = checks.filter(c => c.state === 'bad').length;
  const rq = acc == null ? p.requests : p.requests.filter(r => String(r.acc) === acc);
  const names = p.requests.map(r => placeName(P, r.acc)), n = p.requests.length;
  const line = acc == null ? `${n} ${plural(n, 'заявка', 'заявки', 'заявок')} · ${n <= 2 ? names.join(', ') : names.slice(0, 2).join(', ') + ' +' + (n - 2)}`
    : `${adv.short} · ${rq.length} ${plural(rq.length, 'заявка', 'заявки', 'заявок')}${n > rq.length ? ' из ' + n : ''}`;
  const pickable = p.status === 'wait' || p.status === 'changed';
  return (
    <div role="button" tabIndex={0} className="pm-row" aria-current={sel || undefined} onClick={onPick} onKeyDown={e => e.key === 'Enter' && onPick()}
      style={{ display: 'grid', gridTemplateColumns: '16px 72px minmax(0,1fr) 96px', gap: '0 10px', alignItems: 'center', padding: '7px 10px', borderRadius: 11, cursor: 'pointer', marginBottom: 2,
        background: sel ? 'var(--bg-tint)' : marked ? 'var(--accent-tint)' : 'transparent', border: `1px solid ${sel ? 'var(--accent-border)' : 'transparent'}` }}>
      <Check size={16} on={marked} dim={!pickable} title={pickable ? 'Отметить для массового решения' : 'Уже решён'} onClick={onMark} />
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: p.size ? 'var(--text-primary)' : 'var(--warning-fg)' }}>{p.size || p.size_guess}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{p.type}</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
        <span title={names.join(', ')} style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{line}</span>
        <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {rq.some(r => r.ssp_status === 'ждёт') && <Pip kind="flag" title="У SSP не решено — это реальная работа">SSP ждёт</Pip>}
          {nb > 0 && <Pip kind="bad" title={'Нарушений: ' + nb}>! {nb}</Pip>}
          {!p.size && <Pip kind="warn" title="В разметке нет ad.size">размер не объявлен</Pip>}
          {p.status === 'changed' && <Pip kind="info" title="SSP поменял креатив после нашего решения">изменился</Pip>}
        </span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'flex-end' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: MONO, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', color: AGE_FG[ag.tone][0] }}><Dot c={AGE_FG[ag.tone][1]} />{ag.label}</span>
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>в SSP с {msk(ag.since).dm}</span>
      </span>
    </div>
  );
}

/* ───────── карточка ───────── */
/** Категория заказчика: от неё зависит проверка предупреждения (лекарства, БАД). Список накопительный. */
function CategoryPick({ adv, canEdit, categories, onSetCategory }) {
  const [pop, setPop] = useState(null);
  const editable = canEdit && adv.inn && adv.inn !== '—';
  return (
    <span title="От категории зависит проверка предупреждения: «лекарства», «БАД»" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <Cap>категория</Cap>
      {editable ? <PickValue size={12.5} value={adv.category} placeholder="не задана" onOpen={e => setPop(e.currentTarget.getBoundingClientRect())} />
        : <span style={{ fontSize: 12.5, color: adv.category ? 'var(--text-primary)' : 'var(--text-faint)' }}>{adv.category || 'не задана'}</span>}
      {!!pop && <ValuePopover anchor={pop} title="Категория заказчика" value={adv.category} clearLabel="— не задана —"
        options={categories.map(c => ({ value: c, label: c }))} onClose={() => setPop(null)}
        onPick={v => { setPop(null); onSetCategory(adv.inn, v); }} onAddNew={name => { setPop(null); onSetCategory(adv.inn, name); }} />}
    </span>
  );
}

function PackageHead({ p, adv, now, canEdit, categories, onSetCategory }) {
  const ag = ageOf(p, now), t = trustOf(adv), canAct = p.status === 'wait' || p.status === 'changed';
  const st = { wait: ['ждёт решения', 'warn'], changed: ['креатив изменился — снова ждёт', 'info'], approved: ['одобрено', 'ok'], declined: ['отклонено', 'bad'] }[p.status];
  return (
    <Card style={{ padding: '16px 22px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: '-0.01em' }}>{adv.short}</span>
      <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{adv.name} · ИНН {adv.inn} · {p.type} · {p.size || 'размер не объявлен'} · пакет {p.id}</span>
      <CategoryPick adv={adv} canEdit={canEdit} categories={categories} onSetCategory={onSetCategory} />
      <Chip tone={st[1]}>{st[0]}</Chip>
      {canAct && <span style={{ fontFamily: MONO, fontSize: 12, color: AGE_FG[ag.tone][0] }}>ждёт {ag.label} · в SSP с {msk(ag.since).dm} · {sspWaits(p) ? 'у SSP не решено' : 'у SSP уже одобрено'}</span>}
      <span title="Сколько раз человек повторил прежнее решение по креативам этого рекламодателя. Копится для будущего автоодобрения; само автоодобрение выключено."
        style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, fontSize: 12, fontWeight: 700, background: t.candidate ? 'var(--income-tint)' : 'var(--bg-card)', color: t.candidate ? 'var(--income-fg)' : 'var(--text-secondary)', border: `1px solid ${t.candidate ? 'var(--income-border)' : 'var(--border-card)'}` }}>
        <span style={{ fontFamily: MONO }}>{t.total ? `${t.same} из ${t.total}` : '—'}</span>{t.total ? 'повторных решений совпали' + (t.candidate ? ' · кандидат на автоодобрение' : '') : 'повторных решений ещё не было'}</span>
    </Card>
  );
}

const FALLBACK = [300, 250];   // размер не объявлен или адаптивный — показываем в типовом
const dims = s => { const m = /^(\d+)×(\d+)$/.exec(s || ''); return m ? [Number(m[1]), Number(m[2])] : FALLBACK; };

/** Нижняя полоса баннера крупно: юридическая строка («Реклама», наименование, ИНН) обычно там и мелкая.
 *  Распознавания текста нет (замер 07.11: мелкую строку не читает) — сверяет человек. */
function LegalStrip({ p, w, h, replay }) {
  const k = Math.max(1, Math.min(2, 680 / w)), sh = Math.min(h, Math.max(30, Math.round(h * 0.3)));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)' }}>Нижняя полоса{k > 1 ? ` ×${Math.round(k * 10) / 10}` : ''}</span>
        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{p.text_source === 'html' ? 'в тексте разметки нашлось не всё — сверьте глазами' : 'картинка: текст не распознаём — сверьте «Реклама», наименование и ИНН глазами'}</span></span>
      <div style={{ overflow: 'auto', borderRadius: 12, border: '1px solid var(--border-inner)', background: 'var(--bg-subtle)' }}>
        <div style={{ width: w * k, height: sh * k, overflow: 'hidden' }}>
          <iframe key={'strip' + replay} title={'нижняя полоса ' + p.id} src={p.snapshot_url} width={w} height={h} sandbox="allow-scripts"
            style={{ border: 0, display: 'block', transformOrigin: '0 0', transform: `scale(${k}) translateY(${sh - h}px)` }} />
        </div>
      </div>
    </div>
  );
}

function CreativeCard({ p, adv, checks, pkgs, A, onPick, replay, onReplay, renderCreative, onOpenSnapshot }) {
  const [w, h] = dims(p.size || p.size_guess);
  const sizes = pkgs.filter(x => x.advertiser === p.advertiser);
  const marks = [/Реклама/, new RegExp(adv.inn), /Имеются противопоказания\.[^.]*\.?/, /Не является лекарственным средством\.?/i];
  let parts = [{ s: p.text || '' }];
  marks.forEach(re => { parts = parts.flatMap(x => { if (x.hit) return [x]; const m = re.exec(x.s); if (!m) return [x]; return [{ s: x.s.slice(0, m.index) }, { s: m[0], hit: true }, { s: x.s.slice(m.index + m[0].length) }]; }); });
  const frame = renderCreative ? renderCreative(p, { w, h, replayKey: replay }) : !p.snapshot_url
    ? <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Песочница не настроена — снимок не показать</span> :
    <iframe key={replay} title={'креатив ' + p.id} src={p.snapshot_url} width={w} height={h} sandbox="allow-scripts" style={{ border: 0, display: 'block', flex: '0 0 auto' }} />;
  const tile = (l, val, note, warn) => <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '8px 11px', borderRadius: 11, background: 'var(--bg-subtle)', border: `1px solid ${warn ? 'var(--warning-border)' : 'var(--border-inner)'}` }}>
    <Cap>{l}</Cap><span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: warn ? 'var(--warning-fg)' : 'var(--text-primary)' }}>{val}</span><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{note}</span></span>;
  return (
    <Card style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12, boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>Креатив</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>в натуральную величину · пиксели и счётчики вырезаны, клик выключен</span>
        {p.type === 'HTML5' && <Btn onClick={onReplay} style={{ marginLeft: 'auto', height: 28, fontSize: 12 }}>↻ проиграть заново</Btn>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <Cap style={{ marginRight: 2 }}>размеры</Cap>
        {sizes.map(x => { const on = x.id === p.id, dot = x.status === 'approved' ? 'var(--income)' : x.status === 'declined' ? 'var(--danger)' : x.status === 'changed' ? 'var(--accent)' : isClean(x, A[x.advertiser]) ? 'var(--warning)' : 'var(--danger)';
          return <span key={x.id} role="button" tabIndex={0} onClick={() => onPick(x.id)} title={x.requests.length + ' ' + plural(x.requests.length, 'заявка', 'заявки', 'заявок')}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 26, padding: '0 8px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 700, background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
            <Dot c={dot} /><span style={{ fontFamily: MONO }}>{x.size || x.size_guess}</span><span style={{ fontFamily: MONO, fontWeight: 600, fontSize: 11, color: 'var(--text-muted)' }}>×{x.requests.length}</span></span>; })}
      </div>
      {p.status === 'changed' && p.prev && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 12px', borderRadius: 12, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)' }}>
          <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)' }}>Что изменилось с прежней версии</span>
          <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{p.prev.changes.map(c => (
            <span key={c.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--accent-border)', fontSize: 12 }}>
              <b>{c.label}</b>{c.from && <span style={{ fontFamily: MONO, color: 'var(--text-faint)', textDecoration: 'line-through' }}>{c.from}</span>}{c.from && '→'}
              <span style={{ fontFamily: MONO, fontWeight: 700, color: c.kind === 'same' ? 'var(--text-muted)' : c.kind === 'added' ? 'var(--warning-fg)' : 'var(--income-fg)' }}>{c.to}</span></span>))}</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Cap>было · решено {p.prev.decided_by} {msk(p.prev.decided_at).dm}</Cap>
            {!!p.prev.snapshot_png_url && <span role="button" tabIndex={0} onClick={() => onOpenSnapshot && onOpenSnapshot(p.prev.snapshot_png_url)} style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', cursor: 'pointer' }}>снимок PNG прежней версии</span>}</span>
        </div>)}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 18, borderRadius: 12, background: 'repeating-conic-gradient(var(--bg-subtle) 0% 25%, var(--bg-card) 0% 50%) 0 0 / 16px 16px', border: '1px solid var(--border-inner)', minHeight: 140, flex: '1 1 auto', overflow: 'auto' }}>{frame}</div>
      {!!p.snapshot_url && !renderCreative && checks.some(c => ['mark', 'adv', 'warning'].includes(c.key) && c.state === 'warn') && <LegalStrip p={p} w={w} h={h} replay={replay} />}
      {!!p.text && <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)' }}>Текст на креативе</span><span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{p.text_source === 'html' ? 'из разметки HTML5' : 'распознано с картинки'}</span></span>
        <div style={{ padding: '10px 12px', borderRadius: 12, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', fontSize: 13, lineHeight: 1.55, color: 'var(--text-secondary)' }}>
          {parts.filter(x => x.s).map((x, i) => <span key={i} style={x.hit ? { background: 'var(--income-tint)', color: 'var(--income-fg)', fontWeight: 700, borderRadius: 4, padding: '0 3px' } : undefined}>{x.s}</span>)}</div>
      </div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>
        {p.weight_kb != null && tile('вес', p.weight_kb + ' КБ', p.weight_kb > 150 ? 'тяжёлый для мобильных' : 'в норме', p.weight_kb > 150)}
        {p.type === 'HTML5' && p.anim_s != null ? tile('анимация', p.anim_s + ' с', p.anim_s > 30 ? 'дольше 30 с' : 'до 30 с', p.anim_s > 30)
          : tile('тип', p.type, p.type === 'статика' ? 'картинка' : p.type === 'HTML5' ? 'анимация — длительность не меряем' : 'разметка', false)}
        {tile('снимок', p.id, 'песочница 60 дней', false)}
      </div>
    </Card>
  );
}

function ChecksCard({ checks, n }) {
  const shown = checks.filter(c => c.state !== 'off'), off = checks.filter(c => c.state === 'off');
  const nBad = shown.filter(c => c.state === 'bad').length, nWarn = shown.filter(c => c.state === 'warn').length;
  return (
    <Card style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 3, borderColor: nBad ? 'var(--danger-border)' : 'var(--border-card)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 6 }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>Проверки</span>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: nBad ? 'var(--danger-fg)' : nWarn ? 'var(--warning-fg)' : 'var(--income-fg)' }}>{nBad ? `нарушений: ${nBad}${nWarn ? ' · посмотреть: ' + nWarn : ''}` : nWarn ? 'посмотреть: ' + nWarn : `всё в порядке у всех ${n} ${plural(n, 'заявки', 'заявок', 'заявок')}`}</span>
      </div>
      {shown.map(c => { const m = CHECK_MARK[c.state]; return (
        <div key={c.key} title={c.title + ': ' + c.full + (c.note ? ' · ' + c.note : '')} style={{ display: 'grid', gridTemplateColumns: '16px 190px minmax(0,1fr)', gap: '0 8px', alignItems: 'center', padding: '4px 8px', margin: '0 -8px', borderRadius: 8, background: m[2] }}>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: m[1], textAlign: 'center' }}>{m[0]}</span>
          <span style={{ fontSize: 12.5, fontWeight: 700, color: m[3], whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.title}</span>
          <span style={{ fontSize: 12.5, color: m[4], whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.short}</span></div>); })}
      {off.length > 0 && <span style={{ fontSize: 11.5, color: 'var(--text-faint)', paddingTop: 4, borderTop: '1px solid var(--border-row)' }}>○ позже: {off.map(c => c.title + ' (' + c.short.replace('подключим ', '') + ')').join(' · ')}. Подробности — по наведению на строку.</span>}
    </Card>
  );
}

function RequestsCard({ p, P, ck, setCk, toggle, urlOpen, setUrlOpen, showAll, toggleMore }) {
  const rows = p.requests.map(r => ({ r, err: requestError(r), land: parseLanding(r.landing) })).sort((x, y) => (y.err.bad - x.err.bad) || ((y.r.ssp_status === 'ждёт') - (x.r.ssp_status === 'ждёт')));
  const shown = showAll ? rows : rows.slice(0, LIMIT), nBad = rows.filter(x => x.err.bad).length, nW = rows.filter(x => x.r.ssp_status === 'ждёт').length, nC = p.requests.filter(r => ck[r.uuid]).length;
  const COLS = '20px minmax(0,1fr) 92px 62px 14px';
  return (
    <Card style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 8, flex: '1 1 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>Заявки SSP</span>
        <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{p.requests.length} {plural(p.requests.length, 'заявка', 'заявки', 'заявок')}</span>
        {nBad > 0 && <Pip kind="bad">нарушения {nBad}</Pip>}{nW > 0 && <Pip kind="flag">у SSP ждут {nW}</Pip>}<Pip kind="need">выбрано {nC}</Pip>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 10, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' }}>
          <span role="button" tabIndex={0} onClick={() => setCk(() => true)} style={{ color: 'var(--accent)', cursor: 'pointer' }}>выбрать все</span>
          <span role="button" tabIndex={0} onClick={() => setCk(r => !requestError(r).bad)} style={{ color: 'var(--accent)', cursor: 'pointer' }}>только без нарушений</span>
          <span role="button" tabIndex={0} onClick={() => setCk(() => false)} style={{ color: 'var(--text-muted)', cursor: 'pointer' }}>снять</span>
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '0 8px', padding: '4px 8px', borderBottom: '1px solid var(--border-inner)' }}>
        <span /><Cap>ЕРИД · площадка · ведёт на</Cap><Cap>у SSP</Cap><Cap title="ЕРИД в ссылке клика">в ссылке</Cap><span />
      </div>
      {shown.map(({ r, err, land }) => { const pl = P[r.acc], open = !!urlOpen[r.uuid];
        const sspT = r.ssp_status === 'одобрено' ? ['var(--income-tint)', 'var(--income-fg)'] : r.ssp_status === 'ждёт' ? ['var(--accent)', 'var(--on-accent)'] : ['var(--danger-tint)', 'var(--danger-fg)'];
        return (
          <div key={r.uuid} style={{ display: 'flex', flexDirection: 'column', borderRadius: 10, background: err.bad ? 'var(--danger-tint)' : 'var(--bg-subtle)', border: `1px solid ${err.bad ? 'var(--danger-border)' : 'var(--border-inner)'}` }}>
            <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '0 8px', alignItems: 'center', padding: '7px 8px' }}>
              <Check on={!!ck[r.uuid]} onClick={() => toggle(r.uuid)} title="Одобрить эту заявку" />
              <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                <span style={{ display: 'flex', gap: 8, alignItems: 'baseline', minWidth: 0, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                  <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>{r.erid}</span><span style={{ fontSize: 12.5, fontWeight: 600 }}>{placeName(P, r.acc)}</span>
                  <span title="Сопоставление учёток SSP с нашими паблишерами — черновое" style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{pl && pl.name ? 'уч. ' + r.acc : 'не сопост.'}</span></span>
                <span title={r.dest || land.dest || ''} style={{ fontFamily: MONO, fontSize: 11, color: land.dest ? 'var(--text-primary)' : 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{land.host} → {r.dest || land.dest || 'не раскрыто — адрес внутри трекера'}</span>
              </span>
              <span style={{ justifySelf: 'start', padding: '2px 7px', borderRadius: 6, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', background: sspT[0], color: sspT[1] }}>{r.ssp_status}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: err.bad ? 'var(--danger-fg)' : 'var(--income-fg)' }}>{err.bad ? '≠ ' + (err.linkErid || '—').slice(-4) : '✓'}</span>
              <span role="button" tabIndex={0} title="Полная ссылка текстом" onClick={() => setUrlOpen(s => ({ ...s, [r.uuid]: !s[r.uuid] }))} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 11, textAlign: 'center' }}>{open ? '▾' : '▸'}</span>
            </div>
            {err.bad && <span style={{ padding: '0 8px 7px 36px', fontSize: 12, color: 'var(--danger-fg)', fontWeight: 600 }}><span style={{ fontFamily: MONO }}>✗</span> {err.text}</span>}
            {open && <span style={{ margin: '0 8px 8px 36px', fontFamily: MONO, fontSize: 11.5, lineHeight: 1.5, color: 'var(--text-secondary)', overflowWrap: 'anywhere', padding: '8px 10px', borderRadius: 9, background: 'var(--bg-card)', border: '1px solid var(--border-inner)' }}>
              {land.parts.map((x, i) => <span key={i} style={x.kind === 'erid' ? { background: err.bad ? 'var(--danger-tint)' : 'var(--income-tint)', color: err.bad ? 'var(--danger-fg)' : 'var(--income-fg)', fontWeight: 700 } : x.kind === 'dest' ? { background: 'var(--accent-tint)', color: 'var(--accent-fg)', fontWeight: 700 } : undefined}>{x.s}</span>)}</span>}
          </div>); })}
      {rows.length > LIMIT && <span role="button" tabIndex={0} onClick={toggleMore} style={{ alignSelf: 'flex-start', fontSize: 12.5, fontWeight: 700, color: 'var(--accent)', cursor: 'pointer', padding: '4px 10px' }}>{showAll ? 'свернуть' : `показать ещё ${rows.length - LIMIT} — без нарушений`}</span>}
    </Card>
  );
}

function HistoryCard({ p, onOpenSnapshot }) {
  const items = [...p.decisions.map(d => ({ who: d.by, what: d.verdict === 'approved' ? `одобрил ${d.request_ids.length} из ${p.requests.length}` : 'отклонил', tone: d.verdict === 'approved' ? 'ok' : 'bad', at: d.at,
      note: [d.reason ? 'причина: ' + d.reason : '', d.comment ? `«${d.comment}»` : '', 'по версии ' + (d.version || p.id), 'повтор прежнего решения: ' + (d.repeat ? 'да' : 'нет'), d.bulk ? 'массовое решение' : ''].filter(Boolean).join(' · '), snap: d.snapshot_png_url })),
    ...(p.prev ? [{ who: 'SSP', what: 'изменил креатив', tone: 'info', at: p.requests[0].created_at, note: `новая версия ${p.id} · снова ждёт решения` },
      { who: p.prev.decided_by, what: 'одобрил', tone: 'ok', at: p.prev.decided_at, note: 'по прежней версии креатива ' + p.prev.version, snap: p.prev.snapshot_png_url }] : []),
    ...(p.same_creative ? [{ who: p.same_creative.by, what: 'одобрил', tone: 'ok', at: p.same_creative.at, note: `тот же креатив · заявка ${p.same_creative.request} · ${p.same_creative.note}`, snap: null }] : [])];
  return (
    <Card style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={{ fontSize: 14, fontWeight: 700 }}>История решений</span><span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{items.length || ''}</span></div>
      {items.map((h, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '8px minmax(0,1fr) auto', gap: '0 10px', alignItems: 'start', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
          <Dot c={TONE[h.tone].dot} s={8} style={{ marginTop: 5 }} />
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            <span style={{ fontSize: 12.5 }}><b>{h.who}</b> <span style={{ color: TONE[h.tone].fg, fontWeight: 700 }}>{h.what}</span></span>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', overflowWrap: 'anywhere' }}>{h.note}</span>
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{msk(h.at).dm}</span>
            {h.snap && <span role="button" tabIndex={0} title="Снимок креатива на момент решения — не удаляется вместе с песочницей" onClick={() => onOpenSnapshot && onOpenSnapshot(h.snap)} style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', cursor: 'pointer', whiteSpace: 'nowrap' }}>снимок PNG</span>}
          </span>
        </div>))}
      {!items.length && <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>Решений по этому креативу ещё не было</span>}
    </Card>
  );
}

function RejectModal({ data, p, adv, checks, v, rej, setRej, onSubmit }) {
  const all = data.reasons.flatMap(g => g.items), byCode = Object.fromEntries(all.map(x => [x.code, x]));
  const suggest = [...new Set(checks.filter(c => c.state === 'bad' && SUGGEST_BY_CHECK[c.key]).map(c => SUGGEST_BY_CHECK[c.key]))].filter(c => byCode[c]);
  const chip = code => { const on = rej.code === code;
    return <span key={code} role="button" tabIndex={0} onClick={() => setRej(s => ({ ...s, code }))} style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', borderRadius: 9, cursor: 'pointer', fontSize: 12.5, fontWeight: 700, background: on ? 'var(--danger-tint)' : 'var(--bg-card)', color: on ? 'var(--danger-fg)' : 'var(--text-secondary)', border: `1px solid ${on ? 'var(--danger-border)' : 'var(--border-card)'}` }}>{byCode[code].label}</span>; };
  return (<>
    <div {...overlayClose(() => setRej(s => ({ ...s, open: false })))} style={{ position: 'fixed', inset: 0, background: 'var(--scrim)', zIndex: Z.overlay }} />
    <div role="dialog" aria-modal="true" style={{ ...card, position: 'fixed', left: 'calc(50% - 340px)', top: '9vh', width: 680, /* не transform: его затирает анимация pmPop */ maxHeight: '82vh', overflow: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 12, zIndex: Z.overlay + 1, boxShadow: 'var(--shadow-float)', animation: 'pmPop 0.18s cubic-bezier(0.22,1,0.36,1) both' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={{ fontSize: 17, fontWeight: 800 }}>Отклонить {v.nChecked} из {p.requests.length}</span><span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{adv.short} · {p.size || p.size_guess}</span>
        <span role="button" tabIndex={0} aria-label="Закрыть" onClick={() => setRej(s => ({ ...s, open: false }))} style={{ marginLeft: 'auto', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 18 }}>×</span></div>
      {suggest.length > 0 && <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}><Cap>по найденным нарушениям</Cap><span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{suggest.map(chip)}</span></div>}
      {data.frequent.some(c => byCode[c]) && <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}><Cap>частые</Cap><span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{data.frequent.filter(c => byCode[c]).map(chip)}</span></div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><Cap>все причины SSP</Cap>
        {data.reasons.map(g => <div key={g.group} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
          <span style={{ fontSize: 12.5, fontWeight: 800, color: 'var(--text-secondary)' }}>{g.group}</span><span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{g.items.map(x => chip(x.code))}</span></div>)}</div>
      <textarea className="pm-ta" rows={3} value={rej.comment} onChange={e => setRej(s => ({ ...s, comment: e.target.value }))} placeholder="Комментарий — что именно не так (увидят в истории решений)" />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 12.5, color: rej.code ? 'var(--text-secondary)' : 'var(--danger-fg)' }}>{rej.code ? 'Причина: ' + byCode[rej.code].label : 'Выберите причину — без неё отклонить нельзя'}</span>
        <Btn onClick={() => setRej(s => ({ ...s, open: false }))} style={{ marginLeft: 'auto' }}>Отмена</Btn>
        <Btn kind="d" disabled={!rej.code} onClick={onSubmit}>Отклонить {v.nChecked} из {p.requests.length}</Btn>
      </div>
    </div>
  </>);
}
