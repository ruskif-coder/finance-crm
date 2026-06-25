# Инструкция по интеграции дизайна Silab-AD

Этот документ описывает, как перенести макет из `Silab-AD Cool.dc.html`
в существующий Next.js-проект. Все требования взяты из `claude_design_brief.md`.

---

## 1. Какой файл что заменяет

| Экран в макете | Заменяет страницу | Файл |
|---|---|---|
| ДДС — Дашборд | dashboard | `frontend/pages/dashboard.js` |
| Операции | operations | `frontend/pages/operations.js` |
| Дебиторка | receivables | `frontend/pages/receivables.js` |
| Навигация (верхняя панель) | Navbar | `frontend/components/Navbar.js` |

P&L, Баланс, План/Факт — в макете не представлены, трогать не нужно.

---

## 2. Цвета — полностью заменить `globals.css`

Дизайн вводит свою палитру — **старые переменные заменяются**, не дополняются.
Страницы, не затронутые редизайном (settings, import, login), переносятся на новые токены:
там нужно заменить `var(--primary)` → `var(--accent)`, `var(--bg)` → `var(--bg-canvas)` и т.д.

```css
/* frontend/styles/globals.css — полная замена :root */
:root {
  /* ── Акцент ─────────────────────────────────────── */
  --accent:           #4F6CE6;   /* основной синий, кнопки, активная вкладка */
  --accent-hover:     #3A50BE;
  --accent-tint:      #ECEFFD;   /* фон активной вкладки / бейджа */

  /* ── Фоны ───────────────────────────────────────── */
  --bg-canvas:        #EBEEF6;   /* внешний фон всех страниц */
  --bg-card:          #FFFFFF;   /* карточки */
  --bg-subtle:        #F6F7FB;   /* вторичный фон, строки hover */
  --bg-header:        #FFFFFF;   /* топ-навбар */

  /* ── Текст ──────────────────────────────────────── */
  --text-primary:     #1C2433;   /* заголовки, основной текст */
  --text-secondary:   #525C70;   /* второстепенный текст */
  --text-muted:       #79839A;   /* подписи, метки */
  --text-faint:       #A3ABBD;   /* заголовки колонок, плейсхолдеры */

  /* ── Разделители ────────────────────────────────── */
  --border-card:      #E3E7F1;
  --border-inner:     #EDF0F7;
  --border-row:       #F2F4FA;

  /* ── Семантика данных ───────────────────────────── */
  --income:           #2FA37C;   /* поступления — зелёный */
  --expense:          #DB5C6E;   /* расходы — красноватый */

  /* ── Статусы (точка-индикатор) ──────────────────── */
  --dot-income:       #2FA37C;
  --dot-expense:      #5B7CF0;
  --dot-overdue:      #E5484D;   /* просрочка дебиторки */
  --dot-current-dz:   #E89020;   /* текущая дебиторка */

  /* ── Риббон-график ──────────────────────────────── */
  --ribbon-income-from: #FF4D6A;
  --ribbon-income-mid:  #F046B0;
  --ribbon-income-to:   #D94BDC;
  --ribbon-expense-from:#8A53E4;
  --ribbon-expense-to:  #4F6CE6;

  /* ── Банки ──────────────────────────────────────── */
  --bank-alfa:        #5B7CF0;
  --bank-opt:         #2FB8A8;
  --bank-sovком:      #4A90C2;
  --bank-cash:        #8B7BE8;

  /* ── Совместимость со старыми именами ───────────── */
  /* (чтобы settings/import/login не ломались до переноса) */
  --primary:   var(--accent);
  --success:   var(--income);
  --danger:    var(--dot-overdue);
  --warning:   var(--dot-current-dz);
  --bg:        var(--bg-canvas);
  --card:      var(--bg-card);
  --border:    var(--border-card);
  --text:      var(--text-primary);
  --muted:     var(--text-muted);
}

body {
  background-color: var(--bg-canvas);
  color: var(--text-primary);
}
```

> Алиасы совместимости внизу (`--primary`, `--bg` и т.д.) позволяют не трогать
> settings/import/login сразу — они продолжат работать через цепочку `var()`.
> После переноса этих страниц алиасы можно удалить.

---

## 3. Шрифт

Макет использует **Onest** (Google Fonts). В проекте разрешён только системный стек.

**Вариант A — заменить на системный** (нулевой риск):
```jsx
// В компонентах убираем fontFamily:'Onest,...'
// Добавляем в globals.css:
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
}
```

**Вариант B — добавить Onest через next/font** (рекомендуется, если хотите сохранить типографику):
```js
// frontend/pages/_app.js
import { Onest } from 'next/font/google';
const onest = Onest({ subsets: ['latin', 'cyrillic'], weight: ['300','400','500','600','700','800'] });

export default function App({ Component, pageProps }) {
  return (
    <main className={onest.className}>
      <Component {...pageProps} />
    </main>
  );
}
```
При варианте B шрифт грузится только при `next build` — нет лишнего запроса в runtime.

---

## 4. Навигация — изменения в `Navbar.js`

Переход с **боковой** на **горизонтальную верхнюю** панель.

### Ключевые изменения структуры:
```jsx
// Было: aside с flex-direction:column
// Стало: header с flex-direction:row

<header style={{
  background: 'var(--bg-header)',
  borderBottom: '1px solid var(--border-card)',
  height: 66,
  padding: '0 30px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  position: 'sticky',
  top: 0,
  zIndex: 100,
}}>
  <div style={{ display:'flex', alignItems:'center', gap: 36 }}>
    <img src="/logo.png" alt="Silab-AD" style={{ height: 24 }} />
    <nav style={{ display:'flex', gap: 3 }}>
      {NAV_ITEMS.filter(i => can(i.section)).map(item => (
        <a key={item.href} href={item.href} style={{
          padding: '8px 16px',
          borderRadius: 10,
          background: router.pathname === item.href ? 'var(--accent-tint)' : 'transparent',
          color: router.pathname === item.href ? 'var(--accent)' : 'var(--text-secondary)',
          fontWeight: router.pathname === item.href ? 600 : 500,
          fontSize: 14,
          textDecoration: 'none',
          transition: 'background .15s',
        }}>{item.label}</a>
      ))}
    </nav>
  </div>
  <div style={{ display:'flex', alignItems:'center', gap: 8 }}>
    {/* Операции, Импорт, Настройки — кнопки-утилиты */}
    {/* Аватар пользователя */}
  </div>
</header>
```

### Изменение отступов страниц:
Так как Navbar теперь сверху, а не слева — убрать `marginLeft`/`paddingLeft` у `<main>`,
добавить `paddingTop: 66` (высота хедера) или использовать `position: sticky` хедера.

---

## 5. Dashboard (`dashboard.js`)

### Структура экрана (сверху вниз):
1. **Строка фильтров** — переключатель Период/Дата + дропдаун банков
2. **KPI-полоса** — 4 карточки: Актуальный, Прогноз, Приход, Расход
3. **Ряд:** Риббон-график слева + Банки (плашки) справа
4. **Накопительный остаток** — area SVG

### Риббон-график — замена Recharts-компонента:

Recharts не поддерживает «риббон из капсул». График рисуется чистым `<div>`-ом —
подходит без новых зависимостей:

```jsx
// Расчёт данных (в компоненте):
const CENTER = 200, ARM = 182, MAXV = 42, SUB = 48;
const rawData = [ /* 12 месяцев */ ];
// Catmull-Rom интерполяция → SUB точек → divBars[]
// Каждый bar: { incTop, incH, expTop, expH }

// Рендер:
<div style={{ position:'relative', height: 400, paddingLeft: 54 }}>
  {yLabels.map(l => (
    <div key={l.v} style={{ position:'absolute', left:0, top: l.y, ... }}>{l.v}</div>
  ))}
  <div style={{ position:'relative', height:'100%', borderLeft:'1px solid var(--border-inner)' }}>
    {/* горизонтальные линии сетки */}
    <div style={{ position:'absolute', left:0, right:0, top: CENTER, height:2, background:'#D7DCEA' }} />
    <div style={{ position:'absolute', inset:0, display:'flex', gap:2, padding:'0 10px' }}>
      {divBars.map((bar, i) => (
        <div key={i} style={{ flex:1, position:'relative', height:'100%' }}>
          <div style={{ position:'absolute', left:'50%', transform:'translateX(-50%)',
            width:11, top:bar.incTop, height:bar.incH, borderRadius:6,
            background:`linear-gradient(180deg, var(--ribbon-income-from), var(--ribbon-income-mid), var(--ribbon-income-to))`}} />
          <div style={{ position:'absolute', left:'50%', transform:'translateX(-50%)',
            width:11, top:bar.expTop, height:bar.expH, borderRadius:6,
            background:`linear-gradient(180deg, var(--ribbon-expense-from), var(--ribbon-expense-to))`}} />
        </div>
      ))}
    </div>
  </div>
</div>
```

### Накопительный остаток — оставить Recharts `<AreaChart>`:
Это тот случай, где Recharts уместен — замените только цвета:
```jsx
<Area dataKey="balance" stroke="var(--accent)" fill="url(#areaGrad)" />
<defs>
  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.2} />
    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.01} />
  </linearGradient>
</defs>
```

### Карточки банков:
```jsx
// BANK_STYLES — существующая константа, добавить border-left:
const BANK_STYLES = {
  'АльфаБанк':   { color: 'var(--bank-alfa)' },
  'ОПТ Банк':    { color: 'var(--bank-opt)' },
  'Совкомбанк':  { color: 'var(--bank-sovком)' },
  'Наличные':    { color: 'var(--bank-cash)' },
};

// Плашка банка:
<div style={{ background:'var(--bg-card)', borderRadius:18, padding:'16px 20px',
  borderLeft: `3px solid ${BANK_STYLES[bank.name].color}` }}>
```

---

## 6. Operations (`operations.js`)

### Статусы операций — новый стиль бейджа (вариант 4):

```jsx
// Было: цветной бейдж (bg + fg)
// Стало: нейтральная плашка + цветная точка

const STATUS_DOT = {
  'ПЛАН ПРИХОДА': 'var(--dot-income)',
  'ПЛАН ОПЛАТ':   'var(--dot-expense)',
  'ФАКТ ПРИХОДА': 'var(--dot-income)',
  'ФАКТ ОПЛАТ':   'var(--dot-expense)',
};

// JSX бейджа:
<span style={{ display:'inline-flex', alignItems:'center', gap:6,
  padding:'4px 10px', borderRadius:7,
  background:'var(--bg-subtle)', color:'var(--text-secondary)',
  fontSize:10.5, fontWeight:600, whiteSpace:'nowrap' }}>
  <span style={{ width:7, height:7, borderRadius:'50%',
    background: STATUS_DOT[op.status] ?? '#ccc' }} />
  {op.status}
</span>
```

### Таблица — изменить только цвета, структуру не трогать:
- Строки: `background: i % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-subtle)'`
- Заголовок: `background: 'var(--bg-subtle)'`, цвет `var(--text-faint)`
- Поступление: `color: 'var(--income)'`
- Списание: `color: 'var(--expense)'`

---

## 7. Receivables (`receivables.js`)

### Три карточки статуса (верхний ряд):

```jsx
const AGING_CARDS = [
  { key:'overdue', label:'Просрочено',           dot:'var(--dot-overdue)',    field:'overdue_sum' },
  { key:'current', label:'Текущая задолженность', dot:'var(--dot-current-dz)', field:'current_sum' },
  { key:'plan',    label:'План',                  dot:'var(--accent)',          field:'plan_sum' },
];

// Карточка:
<div style={{ flex:1, background:'var(--bg-subtle)', borderRadius:18, padding:'18px 22px' }}>
  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
    <span style={{ width:9, height:9, borderRadius:'50%', background: card.dot }} />
    <span style={{ fontSize:13, color:'var(--text-secondary)', fontWeight:600 }}>{card.label}</span>
  </div>
  <div style={{ fontSize:26, fontWeight:700, color:'var(--text-primary)', marginTop:8,
    fontVariantNumeric:'tabular-nums' }}>{formatMoney(data[card.field])}</div>
</div>
```

### Бейджи «возраст долга» в таблице:

```jsx
const AGING_DOT = { 'Просрочка': 'var(--dot-overdue)', 'Текущая': 'var(--dot-current-dz)' };

{aging.map(a => (
  <span key={a.type} style={{ display:'inline-flex', alignItems:'center', gap:6,
    padding:'4px 10px', borderRadius:8, background:'var(--bg-subtle)',
    color:'var(--text-secondary)', fontSize:11, fontWeight:500,
    whiteSpace:'nowrap', fontVariantNumeric:'tabular-nums' }}>
    <span style={{ width:7, height:7, borderRadius:'50%', background: AGING_DOT[a.type] }} />
    {a.type}: {formatMoney(a.sum)} ₽
  </span>
))}
```

---

## 8. Фон страниц

Текущий `--bg: #f5f6fa` — заменить глобально или только на нужных страницах:
```css
/* globals.css */
body {
  background-color: var(--bg-canvas); /* #EBEEF6 */
}
```

Или точечно в каждой странице:
```jsx
// В getServerSideProps или через useEffect:
document.body.style.background = 'var(--bg-canvas)';
```

---

## 9. Порядок работы (рекомендуемый)

1. **globals.css** — добавить новые CSS-переменные (шаг 2)
2. **_app.js** — подключить Onest через `next/font` (шаг 3, вариант B)
3. **Navbar.js** — переверстать на горизонтальный (шаг 4)
4. **dashboard.js** — заменить только layout/стили, данные не трогать (шаг 5)
5. **operations.js** — обновить бейджи статусов и цвета таблицы (шаг 6)
6. **receivables.js** — обновить карточки и бейджи дебиторки (шаг 7)

Каждый шаг независим и тестируется отдельно — риска поломки соседних страниц нет.

---

## 10. Что НЕ меняется

- API-запросы (`axios.baseURL`, все эндпоинты)
- Логика прав доступа (`getPermissions`, `can()`, `SECTIONS`)
- Страницы: login, settings, import, pl, balance, planfact
- BANK_COLORS/BANK_STYLES как константы — только обновляются значения
- Структура `localStorage` (token, role, permissions…)


---

## 11. P&L, Баланс, План / Факт — миграция стилей

Эти страницы **не перерисовываются** — только обновляются цвета и типографика.
Структура таблиц и логика не меняются.

### Общий шаблон для каждой страницы

```jsx
// Обновить в каждой из страниц: pl.js, balance.js, planfact.js

// 1. Фон страницы
<div style={{ minHeight:'100vh', background:'var(--bg-canvas)' }}>

// 2. Заголовок — облегчённый вес + жирный акцент
<h1 style={{ fontSize:28, fontWeight:300, color:'var(--text-primary)', letterSpacing:'-.02em' }}>
  P&L <b style={{ fontWeight:800 }}>отчёт</b>
</h1>

// 3. Карточки-KPI — те же, что в dashboard.js (скопировать паттерн)
// background:'var(--bg-card)', borderRadius:'var(--radius-card)', boxShadow:'var(--shadow-card)'

// 4. Таблица: строки чередуются bg-card / bg-subtle
<tr style={{ background: i % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-subtle)' }}>

// 5. Заголовки колонок
<th style={{ fontSize:10.5, fontWeight:700, color:'var(--text-faint)',
  letterSpacing:'.04em', textTransform:'uppercase', background:'var(--bg-subtle)' }}>

// 6. Числа — положительные / отрицательные
<td style={{ color: val >= 0 ? 'var(--income)' : 'var(--expense)',
  fontWeight:600, fontVariantNumeric:'tabular-nums', textAlign:'right' }}>
```

### Специфика P&L (`pl.js`)

```jsx
// Группировки статей — выделение уровней
const rowStyle = (level) => ({
  fontWeight:  level === 0 ? 700 : level === 1 ? 600 : 400,
  fontSize:    level === 0 ? 14  : 13.5,
  color:       level === 0 ? 'var(--text-primary)' : 'var(--text-secondary)',
  background:  level === 0 ? 'var(--bg-subtle)' : 'var(--bg-card)',
  borderBottom:'1px solid var(--border-row)',
  padding:     '12px 22px',
  paddingLeft: 22 + level * 20 + 'px',
});

// Итоговые строки
const totalStyle = {
  fontWeight:700, fontSize:14, color:'var(--text-primary)',
  background:'var(--accent-tint)', borderTop:'2px solid var(--border-card)',
};
```

### Специфика Баланс (`balance.js`)

```jsx
// Активы / Пассивы — два столбца
const sectionHeader = {
  fontSize:13, fontWeight:700, color:'var(--accent)',
  background:'var(--accent-tint)', padding:'10px 22px',
  borderBottom:'1px solid var(--border-inner)',
  letterSpacing:'.03em', textTransform:'uppercase',
};

// Разница (актив - пассив) — цветная
const diffStyle = (diff) => ({
  color:      diff >= 0 ? 'var(--income)' : 'var(--expense)',
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
});
```

### Специфика План / Факт (`planfact.js`)

```jsx
// Прогресс-бар выполнения плана
const ProgressBar = ({ plan, fact }) => {
  const pct = plan > 0 ? Math.min(100, Math.round(fact / plan * 100)) : 0;
  const color = pct >= 100 ? 'var(--income)' : pct >= 75 ? 'var(--accent)' : 'var(--dot-current-dz)';
  return (
    <div style={{ display:'flex', alignItems:'center', gap:10 }}>
      <div style={{ flex:1, height:6, borderRadius:3, background:'var(--border-inner)', overflow:'hidden' }}>
        <div style={{ width: pct + '%', height:'100%', borderRadius:3, background: color,
          transition:'width .3s ease' }} />
      </div>
      <span style={{ fontSize:11.5, fontWeight:600, color, minWidth:38,
        textAlign:'right', fontVariantNumeric:'tabular-nums' }}>{pct}%</span>
    </div>
  );
};

// Отклонение план/факт
const deviationStyle = (plan, fact) => {
  const diff = fact - plan;
  return { color: diff >= 0 ? 'var(--income)' : 'var(--expense)', fontWeight:600,
    fontVariantNumeric:'tabular-nums' };
};
```

---

## 12. Готовые файлы

| Файл | Описание | Статус |
|---|---|---|
| `frontend/styles/globals.css` | Все токены + совместимость | ✅ готов |
| `frontend/components/Navbar.js` | Горизонтальный навбар | ✅ готов |
| `frontend/helpers/ribbonChart.js` | Catmull-Rom + buildDivBars | ✅ готов |
| `frontend/pages/dashboard.js` | ДДС — полная страница | ✅ готов |
| `frontend/pages/operations.js` | Операции — полная страница | ✅ готов |
| `frontend/pages/receivables.js` | Дебиторка — полная страница | ✅ готов |
| `frontend/pages/pl.js` | P&L — только стили (раздел 11) | 🔧 патч |
| `frontend/pages/balance.js` | Баланс — только стили (раздел 11) | 🔧 патч |
| `frontend/pages/planfact.js` | План/Факт — только стили (раздел 11) | 🔧 патч |

Значок 🔧 означает, что файл не переписывается целиком — нужно применить
фрагменты кода из раздела 11 к существующему файлу.

---

## 13. Чеклист запуска

```
□ globals.css заменён
□ _app.js подключает Onest через next/font (или Google Fonts в <Head>)
□ Navbar.js заменён — проверить что logout работает
□ dashboard.js заменён — проверить /api/dashboard/summary, /monthly, /banks, /cumulative
□ operations.js заменён — проверить /api/operations и /api/operations/filter-options
□ receivables.js заменён — проверить /api/receivables/summary, /debtors, /filter-options
□ pl.js — применить стили из раздела 11
□ balance.js — применить стили из раздела 11
□ planfact.js — применить стили из раздела 11
□ /public/logo.png — убедиться что файл есть (Navbar читает /logo.png)
□ next build → проверить нет ошибок типизации
```
