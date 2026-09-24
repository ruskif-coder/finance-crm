/**
 * Экран «Кампании» в кабинете паблишера.
 * Список размещений, сгруппированный по месяцам: от текущего к старым.
 * В шапке месяца — биллинг, факт показов и число запусков; внутри — таблица РК.
 *
 * Зависимость только React. Правая колонка (уведомления, команда, договора, медиакит)
 * переиспользуется с дашборда — здесь не дублируется.
 */
import React, { useMemo, useRef, useState } from 'react';
import Pop from '../lib/pop';
/* Размеры плиток — из общего кита, одни на оба экрана. В хендоффе они вписаны по месту,
   и для макета это верно; в работающем кабинете два набора чисел разъезжаются, и виджет
   «прыгает» при переходе между разделами (владелец 15.09.2026). */
import { KPI_SIZE } from '../lib/ui';

/* ── токены ──────────────────────────────────────────────────────────

   ПЕРЕВЕДЕНЫ НА ПЕРЕМЕННЫЕ. В хендоффе палитра задана хексами; в проекте цвета живут
   в `styles/globals.css`, и прибор `check-tokens` отвергает сборку с хексом в JS. Он
   прав: тёмная тема переключает переменные, а хекс остаётся светлым — экран выглядел бы
   вырезанным из другого приложения. Значения те же, сверено по `design-language.md`. */
export const T = {
  canvas: 'var(--bg-canvas)', card: 'var(--bg-card)', subtle: 'var(--bg-subtle)',
  tint: 'var(--bg-tint)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)',
  hover: 'var(--border-hover)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)',
  t4: 'var(--text-faint)', t5: 'var(--text-ghost)',
  accent: 'var(--accent)', accentHover: 'var(--accent-hover)',
  accentTint: 'var(--accent-tint)', accentBorder: 'var(--accent-border)',
  income: 'var(--income)', incomeFg: 'var(--income-fg)', incomeTint: 'var(--income-tint)',
  incomeBorder: 'var(--income-border)',
  warning: 'var(--warning)', warnFg: 'var(--warning-fg)', warnTint: 'var(--warning-tint)',
  warnBorder: 'var(--warning-border)',
  danger: 'var(--danger)', dangerTint: 'var(--danger-tint)',
  dangerBorder: 'var(--danger-border)',
  teal: 'var(--teal)', violet: 'var(--violet)',
  shadow: 'var(--shadow-card)',
  mono: "'JetBrains Mono', ui-monospace, monospace",
  sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};

/** Текущий месяц кабинета — от него список идёт к старым; будущие не показываются.

    В хендоффе он вписан строкой `'2026-09'`: для макета это верно, для работающего
    кабинета — бомба с часовым механизмом. Первого октября экран молча спрятал бы
    сентябрь вместе с будущим, и выглядело бы это как «кампании пропали».

    Берём настоящий месяц. Значение считается ОДИН РАЗ при загрузке модуля: вкладку
    держат открытой сутками, но пересчёт в рендере дал бы разные значения на сервере и
    клиенте и ошибку гидрации — ту же, из-за которой `today` в дашборде берётся в
    `useEffect`. */
export const NOW = (() => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
})();
export const MONTH_RU = {
  '01': 'Январь', '02': 'Февраль', '03': 'Март', '04': 'Апрель', '05': 'Май', '06': 'Июнь',
  '07': 'Июль', '08': 'Август', '09': 'Сентябрь', '10': 'Октябрь', '11': 'Ноябрь', '12': 'Декабрь',
};

/* ── статусы РК: тот же справочник, что в блоке дашборда ────────────── */
export const RK_STATUS = {
  'ждёт согласования': [T.accentTint, T.accent, T.accentBorder],
  'ждёт старта':       [T.subtle, T.t3, T.border],
  'в размещении':      [T.accentTint, T.accent, T.accentBorder],
  'пауза':             [T.warnTint, T.warnFg, T.warnBorder],
  'завершён':          [T.incomeTint, T.incomeFg, T.incomeBorder],
  'отказ':             [T.dangerTint, T.danger, T.dangerBorder],
};
/* состояние месяца выводится из статусов его РК */
export const MONTH_STATE = {
  'идёт':     [T.accentTint, T.accent, T.accentBorder, T.accent],
  'сверен':   [T.incomeTint, T.incomeFg, T.incomeBorder, T.income],
  'в работе': [T.warnTint, T.warnFg, T.warnBorder, T.warning],
};
export const SERVICE_DOT = { 'еФарм': T.accent, 'Альфарм-Таргет': T.teal, 'Приоритезация': T.violet, 'Ретаргет': T.violet };

/* ── формат и расчёты ───────────────────────────────────────────────── */
const nf = v => v.toLocaleString('ru-RU');
const rub = v => nf(v) + ' ₽';
export const billing = (fact, cpm) => Math.round(fact / 1000 * cpm);
/** Месяц кампании выводится из флайта — пара «период ↔ срок» не расходится. */
export const periodOf = c => {
  const m = /^(\d{2})\.(\d{2})/.exec(c.flight || '');
  return m ? String(c.year) + '-' + m[2] : NOW;
};
/** Месяц сверен, когда все РК терминальны; идёт — если есть активные. */
export const stateOf = list => {
  const live = list.filter(c => c.status === 'в размещении' || c.status === 'пауза').length;
  if (live) return 'идёт';
  return list.every(c => c.status === 'завершён' || c.status === 'отказ') ? 'сверен' : 'в работе';
};

/* ДВЕ СЕТКИ, а не одна с условной колонкой. У кабинета с одной площадкой столбец
   «Площадка» повторял бы один и тот же домен в каждой строке — это не данные, а шум,
   и он отъедает ширину у названия кампании. У кабинета с несколькими площадками без
   него нельзя понять, чей инвентарь открутился.

   Сетка одна на шапку, строки и итог внутри своего случая: две копии расползлись бы,
   и заголовок встал бы не над своим столбцом. */
const COLS_1 = 'minmax(190px,1.35fr) minmax(112px,0.8fr) 124px 116px 128px 108px 130px';
const COLS_N = 'minmax(180px,1.2fr) 116px minmax(108px,0.7fr) 116px 112px 124px 104px 126px';
const colHead = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН
   ══════════════════════════════════════════════════════════════════════ */
export default function CampaignsScreen({ campaigns = DEMO, onOpen }) {
  /* ПЕРИОД — ДИАПАЗОН «от … до», как в реестре сделок (владелец 15.09.2026).
     Одиночный месяц отвечал только на вопрос «что в сентябре»; за квартал или за
     полгода его пришлось бы складывать в уме. Пустые границы означают «без края»:
     заполнен только «от» — всё начиная с него, только «до» — всё по него. */
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  /* Фильтр площадок. Умолчание — «все» (владелец 15.09.2026). Появляется, только если
     площадок в кабинете больше одной: выбор из одного варианта — это не выбор. */
  const [site, setSite] = useState('все');
  const [siteOpen, setSiteOpen] = useState(false);
  const [calOpen, setCalOpen] = useState(false);
  const calRef = useRef(null);
  const siteRef = useRef(null);
  const [opened, setOpened] = useState({});          /* переопределения раскрытия */
  const [expandAll, setExpandAll] = useState(false);

  /* Сверенные и текущие — и СОГЛАСОВАННОЕ БУДУЩЕЕ (владелец 15.09.2026).

     ТЗ хендоффа прячет будущее целиком (`periodOf(c) <= NOW`), и для несогласованного
     это верно: месяц, по которому ещё идут креативы, — намерение, которое может и не
     состояться, и закрывать им ответ на «что у меня сейчас и раньше» незачем.

     Согласованный будущий месяц — другое дело: креатив принят, остаётся дождаться
     флайта. Это обязательство, площадка на него рассчитывает, и прятать его значит
     скрывать от неё подтверждённые деньги. Такие месяцы возвращаются и идут наверх.

     Согласованность считается ПО МЕСЯЦУ ЦЕЛИКОМ, а не по строке: если в нём есть хоть
     одно размещение на согласовании, месяц ещё не решён, и показывать его как
     обязательство нельзя. */
  const futureOk = useMemo(() => {
    const byMonth = new Map();
    for (const c of campaigns) {
      const k = periodOf(c);
      if (k <= NOW) continue;
      if (!byMonth.has(k)) byMonth.set(k, []);
      byMonth.get(k).push(c);
    }
    return new Set([...byMonth.entries()]
      .filter(([, list]) => !list.some(c => c.status === 'ждёт согласования'))
      .map(([k]) => k));
  }, [campaigns]);

  const all = useMemo(
    () => campaigns.filter(c => periodOf(c) <= NOW || futureOk.has(periodOf(c))),
    [campaigns, futureOk]);

  /* Площадки кабинета — из самих данных, а не отдельным запросом: список площадок и
     список кампаний обязаны сходиться, а два источника однажды разойдутся. */
  const sites = useMemo(
    () => [...new Set(all.map(c => c.site).filter(Boolean))].sort(), [all]);
  const multi = sites.length > 1;

  /* ОТБОР ПО ДВУМ ОСЯМ СРАЗУ. KPI, группы и календарь считаются из `scope`, поэтому
     фильтр площадки пересчитывает всё разом — иначе шапка говорила бы про весь кабинет,
     а таблица под ней про одну площадку, и числа на экране спорили бы друг с другом. */
  /* Сравнение строк «YYYY-MM» — лексикографическое, и оно же хронологическое: разбор
     даты здесь не нужен и только добавил бы место для ошибки. */
  const scope = useMemo(() => all.filter(c => {
    const k = periodOf(c);
    return (!from || k >= from) && (!to || k <= to)
      && (!multi || site === 'все' || c.site === site);
  }), [all, from, to, site, multi]);

  /* месяцы, в которых есть кампании — только они доступны в календаре */
  const have = useMemo(() => [...new Set(all.map(periodOf))], [all]);
  /* Порядок: согласованное будущее сверху (ближайшее первым), дальше текущий месяц и
     прошлые по убыванию. Простой `.sort().reverse()` поставил бы декабрь выше октября —
     то есть дальнее обязательство выше ближнего, а спрашивают всегда про ближайшее. */
  const keys = useMemo(() => {
    const ks = [...new Set(scope.map(periodOf))];
    const fut = ks.filter(k => k > NOW).sort();
    const past = ks.filter(k => k <= NOW).sort().reverse();
    return [...fut, ...past];
  }, [scope]);

  const months = keys.map((key, i) => {
    const list = scope.filter(c => periodOf(c) === key);
    const fact = list.reduce((a, c) => a + c.fact, 0);
    const sum = list.reduce((a, c) => a + (c.fact ? billing(c.fact, c.cpm) : 0), 0);
    const st = stateOf(list);
    /* по умолчанию раскрыт первый (текущий) месяц, остальные свёрнуты */
    const open = expandAll || (opened[key] != null ? opened[key] : i === 0);
    return { key, i, list, fact, sum, st, open, eridN: list.filter(c => c.erid).length };
  });

  const total = {
    fact: scope.reduce((a, c) => a + c.fact, 0),
    plan: scope.reduce((a, c) => a + c.plan, 0),
    sum: scope.reduce((a, c) => a + (c.fact ? billing(c.fact, c.cpm) : 0), 0),
    closed: scope.filter(c => c.status === 'завершён').reduce((a, c) => a + billing(c.fact, c.cpm), 0),
    live: scope.filter(c => c.status === 'в размещении').length,
  };

  /* Сетка под текущий случай — одна на шапку, строки и итог. */
  const cols = multi ? COLS_N : COLS_1;

  /* Смена границ сбрасывает раскрытие: список под шапкой становится другим, и
     оставленное раскрытие относилось бы к чужим месяцам. Панель при этом НЕ
     закрывается — вторую границу выбирают следующим движением. */
  const setRange = (a, b) => { setFrom(a); setTo(b); setOpened({}); setExpandAll(false); };
  /* Смена площадки сбрасывает раскрытие так же, как смена периода: список под шапкой
     становится другим, и оставленное раскрытие относилось бы к чужим месяцам. */
  const setS = key => { setSite(key); setSiteOpen(false); setOpened({}); setExpandAll(false); };

  /* ТОЛЬКО ЦЕНТРАЛЬНАЯ ЧАСТЬ (владелец 15.09.2026): шапка приложения и обе колонки —
     наши, кабинетные. В хендоффе компонент владел всей страницей: своя подложка на
     100vh, своя ширина 1600 и слот `sidebar` под правую колонку. Взяв его целиком, мы
     получили бы вторую разметку страницы рядом с первой — и два места, где чинить
     отступы. Поэтому внешняя обёртка и слот сайдбара сняты, остальное дословно. */
  return (
    <>
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes popIn { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important } }
        .cs-row:hover { background:${T.subtle} }
        .cs-ghost:hover { border-color:${T.hover}; color:${T.accent} }
      `}</style>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>

            {/* KPI: внутри левой колонки — иначе сайдбар уезжает вниз */}
            <section style={{ background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow, borderRadius: 18, padding: '18px 24px 16px', display: 'flex', flexDirection: 'column', gap: 14, animation: `riseIn .4s ${T.ease} .07s both` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.025em' }}>Кампании</span>
                <span style={{ ...colHead, fontSize: 11 }}>
                  {/* Границы диапазона — МИНИМУМ и МАКСИМУМ, а не края списка. Порядок
                      групп больше не хронологический (согласованное будущее стоит
                      первым), и `keys[0]` перестал быть самым поздним месяцем: подпись
                      читалась бы как «2026-12 — 2026-08». */}
                  {keys.length} {keys.length === 1 ? 'месяц' : 'месяцев'}
                  {' · '}{[...keys].sort()[0]} — {[...keys].sort()[keys.length - 1]}
                </span>

                <span className="cs-ghost" onClick={() => { setExpandAll(v => !v); setOpened({}); }}
                  style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 12px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: T.t2, whiteSpace: 'nowrap', cursor: 'pointer' }}>
                  {expandAll ? 'Свернуть все' : 'Развернуть все'}
                </span>

                {/* выбор площадки — только когда их больше одной */}
                {multi && (
                  <span style={{ position: 'relative', flex: '0 0 auto' }}>
                    <span ref={siteRef} onClick={() => setSiteOpen(o => !o)} style={{ display: 'inline-flex', alignItems: 'center', gap: 9, height: 34, padding: '0 12px', background: T.card, border: `1px solid ${siteOpen ? T.accent : T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: siteOpen ? T.accent : T.t2, whiteSpace: 'nowrap', cursor: 'pointer' }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.6 2.5 14.4 0 17M12 3.5c-2.5 2.6-2.5 14.4 0 17" /></svg>
                      {site === 'все' ? 'Все площадки' : site}
                      <span style={{ fontSize: 10, color: T.t4 }}>{siteOpen ? '▴' : '▾'}</span>
                    </span>

                    <Pop open={siteOpen} anchor={siteRef} onClose={() => setSiteOpen(false)}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 4 }}>
                        <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Площадка</span>
                        <span onClick={() => setS('все')} style={{ marginLeft: 'auto', fontSize: 11.5, fontWeight: 700, color: T.accent, cursor: 'pointer' }}>все площадки</span>
                      </span>
                      <span style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 300, overflowY: 'auto' }}>
                        {sites.map(x => (
                          <span key={x} onClick={() => setS(x)}
                            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px', borderRadius: 8, fontSize: 12.5, cursor: 'pointer', background: site === x ? T.accentTint : 'transparent', color: site === x ? T.accent : T.t1, fontWeight: site === x ? 700 : 500 }}>
                            {x}
                            <span style={{ marginLeft: 'auto', ...colHead, fontSize: 9 }}>
                              {all.filter(c => c.site === x).length}
                            </span>
                          </span>
                        ))}
                      </span>
                    </Pop>
                  </span>
                )}

                {/* выбор периода — календарь месяцев, по умолчанию «все» */}
                <span style={{ position: 'relative', flex: '0 0 auto' }}>
                  <span ref={calRef} onClick={() => setCalOpen(o => !o)} style={{ display: 'inline-flex', alignItems: 'center', gap: 9, height: 34, padding: '0 12px', background: T.card, border: `1px solid ${calOpen ? T.accent : T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: calOpen ? T.accent : T.t2, whiteSpace: 'nowrap', cursor: 'pointer' }}>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><rect x="3.5" y="5" width="17" height="15.5" rx="2.5" /><path d="M3.5 10h17M8 3.5v3M16 3.5v3" /></svg>
                    {!from && !to ? 'Все месяцы'
                      : (from && to && from === to) ? MONTH_RU[from.slice(5)] + ' ' + from.slice(0, 4)
                      : `${from ? from : '…'} — ${to ? to : '…'}`}
                    <span style={{ fontSize: 10, color: T.t4 }}>{calOpen ? '▴' : '▾'}</span>
                  </span>

                  <Pop open={calOpen} anchor={calRef} onClose={() => setCalOpen(false)}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Период</span>
                      <span onClick={() => setRange('', '')} style={{ marginLeft: 'auto', fontSize: 11.5, fontWeight: 700, color: T.accent, cursor: 'pointer' }}>все месяцы</span>
                    </span>
                    {/* Два поля «от — до», как в реестре сделок: там же тип `month`, и
                        браузер сам рисует выбор месяца — свой календарь был бы третьей
                        его копией в проекте. */}
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <input type="month" value={from} max={to || undefined}
                        onChange={e => setRange(e.target.value, to)}
                        style={{ flex: 1, minWidth: 0, padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, background: T.card, color: T.t1, fontSize: 12, fontFamily: T.sans, outline: 'none' }} />
                      <span style={{ color: T.t4 }}>—</span>
                      <input type="month" value={to} min={from || undefined}
                        onChange={e => setRange(from, e.target.value)}
                        style={{ flex: 1, minWidth: 0, padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, background: T.card, color: T.t1, fontSize: 12, fontFamily: T.sans, outline: 'none' }} />
                    </span>
                    <span style={{ ...colHead, fontSize: 8.5, lineHeight: 1.4 }}>
                      пусто = без края: только «от» — всё начиная с него
                    </span>
                    {have.length > 0 && (
                      <span style={{ ...colHead, fontSize: 8.5, lineHeight: 1.4 }}>
                        есть кампании: {[...have].sort()[0]} — {[...have].sort()[have.length - 1]}
                      </span>
                    )}
                  </Pop>
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'stretch', gap: 24, flexWrap: 'wrap' }}>
                {[
                  [(!from && !to) ? 'Биллинг за всё время' : 'Биллинг за период', nf(total.sum), '₽', T.t1, 'до НДС · по завершённым флайтам ' + rub(total.closed)],
                  ['Факт показов', nf(total.fact), '', T.accent, 'план ' + nf(total.plan) + ' · ' + Math.round(total.plan ? total.fact / total.plan * 100 : 0) + ' %'],
                  ['Запусков', String(scope.length), 'РК', T.t1, keys.length + ' периодов'],
                  ['Идёт сейчас', String(total.live), 'РК', T.income, 'в текущем месяце'],
                ].map(([label, value, unit, color, hint], i) => (
                  <span key={label} style={{ flex: '1 1 auto', minWidth: 0, padding: '0 24px 0 0', display: 'flex', flexDirection: 'column', gap: 8, borderRight: `1px solid ${i === 3 ? 'transparent' : T.inner}` }}>
                    <span style={{ ...colHead, fontSize: KPI_SIZE.label, color: T.t3 }}>{label}</span>
                    <span style={{ display: 'flex', alignItems: 'baseline', gap: 7, flexWrap: 'wrap' }}>
                      <span style={{ fontFamily: T.mono, fontSize: KPI_SIZE.value, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color, whiteSpace: 'nowrap' }}>{value}</span>
                      <span style={{ fontSize: KPI_SIZE.unit, fontWeight: 600, color: T.t3 }}>{unit}</span>
                    </span>
                    <span style={{ fontSize: KPI_SIZE.hint, color: T.t4 }}>{hint}</span>
                  </span>
                ))}
              </div>
            </section>

            {/* группы по месяцам */}
            {months.map(m => {
              const [sBg, sFg, sBorder, sDot] = MONTH_STATE[m.st];
              return (
                <section key={m.key} style={{ background: T.card, border: `1px solid ${m.key === NOW ? T.accentBorder : T.border}`, boxShadow: T.shadow, borderRadius: 18, padding: '16px 24px 14px', display: 'flex', flexDirection: 'column', gap: 10, overflowX: 'auto', animation: `riseIn .4s ${T.ease} ${(0.12 + m.i * 0.05).toFixed(2)}s both` }}>

                  {/* шапка месяца: фиксированные колонки — иначе цифры прыгают */}
                  <div onClick={() => { setExpandAll(false); setOpened(o => ({ ...o, [m.key]: !m.open })); }}
                    style={{ display: 'grid', gridTemplateColumns: '196px 76px 106px minmax(0,1fr)', gap: 14, alignItems: 'center', minWidth: 920, cursor: 'pointer' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9, minWidth: 0 }}>
                      <span style={{ fontSize: 10, color: T.t4, flex: '0 0 8px' }}>{m.open ? '▾' : '▸'}</span>
                      <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>{MONTH_RU[m.key.slice(5)]} {m.key.slice(0, 4)}</span>
                    </span>
                    <span style={{ ...colHead, fontSize: 10 }}>{m.key}</span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, background: sBg, color: sFg, border: `1px solid ${sBorder}`, borderRadius: 7, padding: '4px 0', fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
                      <span style={{ width: 6, height: 6, borderRadius: 2, background: sDot }} />{m.st}
                    </span>

                    {/* три числа месяца: фиксированные колонки, без переноса */}
                    <span style={{ display: 'grid', gridTemplateColumns: '150px 140px 84px', gap: 22, justifyContent: 'end', whiteSpace: 'nowrap' }}>
                      {[['биллинг', nf(m.sum), '₽', T.t1], ['факт показов', nf(m.fact), '', T.t1], ['запусков', String(m.list.length), 'РК', m.st === 'идёт' ? T.accent : T.t2]].map(([label, value, unit, color]) => (
                        <span key={label} style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end', minWidth: 0 }}>
                          <span style={{ ...colHead, fontSize: 8.5 }}>{label}</span>
                          <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 5 }}>
                            <span style={{ fontFamily: T.mono, fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1, color }}>{value}</span>
                            <span style={{ fontSize: 10, fontWeight: 600, color: T.t4 }}>{unit}</span>
                          </span>
                        </span>
                      ))}
                    </span>
                  </div>

                  {m.open && (
                    <div style={{ minWidth: 920, display: 'flex', flexDirection: 'column', animation: `popIn .2s ${T.ease} both` }}>
                      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, padding: '0 6px 9px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
                        <span>Кампания</span>
                        {multi && <span>Площадка</span>}
                        <span>Услуга</span><span>Срок РК</span>
                        <span style={{ textAlign: 'right' }}>Факт показов</span><span style={{ textAlign: 'right' }}>Биллинг</span>
                        <span>ЕРИД</span><span style={{ textAlign: 'center' }}>Статус</span>
                      </div>

                      {m.list.map(c => {
                        const [stBg, stFg, stBorder] = RK_STATUS[c.status];
                        return (
                          <div key={c.brand + c.flight} className="cs-row" onClick={() => onOpen?.(c)}
                            style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, alignItems: 'center', padding: '9px 6px', borderRadius: 10, borderBottom: `1px solid ${T.row}`, minWidth: 0, cursor: 'pointer' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 8, minWidth: 0 }}>
                              <span style={{ width: 7, height: 7, borderRadius: 2, background: SERVICE_DOT[c.service] || T.t5, flex: '0 0 7px', marginTop: 3 }} />
                              <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.brand}</span>
                            </span>
                            {multi && (
                              <span style={{ fontSize: 12, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.site}>{c.site}</span>
                            )}
                            {/* поверхность — под услугой */}
                            <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                              <span style={{ fontSize: 12, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.service}</span>
                              <span style={{ ...colHead, fontSize: 9 }}>{c.surface}</span>
                            </span>
                            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3, whiteSpace: 'nowrap' }}>{c.flight}</span>
                            <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, textAlign: 'right' }}>{c.fact ? nf(c.fact) : '—'}</span>
                            <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap' }}>{c.fact ? rub(billing(c.fact, c.cpm)) : '—'}</span>
                            <span title={c.erid ? 'ЕРИД выпущен нашей стороной' : 'ЕРИД появится после сборки цепочки ОРД'}
                              style={{ fontFamily: T.mono, fontSize: 10.5, fontWeight: c.erid ? 700 : 400, color: c.erid ? T.accent : T.t5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {c.erid || 'не выпущен'}
                            </span>
                            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: stBg, color: stFg, border: `1px solid ${stBorder}`, borderRadius: 7, padding: '4px 0', fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{c.status}</span>
                          </div>
                        );
                      })}

                      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, alignItems: 'center', padding: '12px 6px 0' }}>
                        <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого за месяц</span>
                        {/* Пустых ячеек столько же, сколько колонок перед фактом: при
                            включённой колонке площадки их три, иначе две. Разойдись
                            счёт — итог встал бы под чужим столбцом, а это ровно то
                            место, где число читают не глядя. */}
                        <span /><span />{multi && <span />}
                        <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{nf(m.fact)}</span>
                        <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{rub(m.sum)}</span>
                        <span style={{ ...colHead, fontSize: 10 }}>{m.eridN} из {m.list.length} ЕРИД</span>
                        <span />
                      </div>
                    </div>
                  )}
                </section>
              );
            })}

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '0 6px' }}>
              <span style={{ ...colHead, fontSize: 9.5 }}>суммы до НДС · биллинг по факту показов · окончательная сумма — после сверки за период</span>
              <span style={{ marginLeft: 'auto', ...colHead, fontSize: 9.5 }}>{scope.length} РК в списке · {keys.length} периодов</span>
            </div>
      </div>
    </>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   ДЕМО-ДАННЫЕ — контракт с API
   ══════════════════════════════════════════════════════════════════════ */
const c = (brand, service, surface, flight, plan, fact, cpm, status, erid = '') =>
  ({ brand, service, surface, flight, plan, fact, cpm, status, erid, year: 2026 });

export const DEMO = [
  c('AB-BIOTICS · Бифистим', 'еФарм', 'web', '05.09 — 30.09', 540000, 318400, 450, 'в размещении', 'Kra251bQm'),
  c('Замбон · Анауран', 'Альфарм-Таргет', 'web', '12.09 — 30.09', 300000, 96200, 380, 'в размещении', 'Kra263kWs'),
  c('Ферон · Виферон', 'еФарм', 'app', '01.09 — 25.09', 360000, 214800, 420, 'в размещении', 'Kra271dFy'),
  c("Dr. Reddy's · Найз", 'Приоритезация', 'web', '08.09 — 30.09', 180000, 41300, 520, 'пауза', 'Kra266mZc'),
  c('Belle you · Кросс-сеть', 'Альфарм-Таргет', 'web', '01.09 — 30.09', 200000, 0, 380, 'отказ'),

  c('Sanofi · Маалокс', 'еФарм', 'web', '01.08 — 31.08', 720000, 706400, 450, 'завершён', 'Kra174pLd'),
  c('BINNO · Кагоцел', 'Альфарм-Таргет', 'web', '01.08 — 31.08', 480000, 492100, 380, 'завершён', 'Kra198xTf'),
  c('Ферон · Виферон', 'еФарм', 'app', '01.08 — 25.08', 360000, 351800, 420, 'завершён', 'Kra240nHv'),
  c('Woerwag · Мильгамма', 'еФарм', 'web', '10.08 — 31.08', 260000, 254900, 450, 'завершён', 'Kra233tQe'),

  c('Sanofi · Эссенциале', 'еФарм', 'app', '05.07 — 31.07', 240000, 231600, 420, 'завершён', 'Kra152rBn'),
  c('BINNO · Слабипрокт', 'Ретаргет', 'web', '01.07 — 31.07', 320000, 298700, 400, 'завершён', 'Kra148yVu'),

  c('Замбон · Флуимуцил', 'Альфарм-Таргет', 'web', '01.06 — 30.06', 180000, 176400, 380, 'завершён', 'Kra119aPk'),
  c('Sanofi · Но-шпа', 'еФарм', 'web', '12.06 — 30.06', 210000, 205100, 450, 'завершён', 'Kra124sLm'),
];
