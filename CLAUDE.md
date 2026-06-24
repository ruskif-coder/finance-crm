# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Internal financial management system for a single company (cash flow / P&L / balance / receivables / счетоводство). Russian-language UI and Russian identifiers throughout the codebase (variable names, DB enum values, comments) — preserve Russian strings exactly when editing; they are compared/matched literally in many places (statuses, group names, bank names).

Stack: FastAPI 0.111 + SQLAlchemy 2.0.30 + PostgreSQL 16 (backend), Next.js 14.2.3 + React 18.3.1 + Recharts (frontend), Docker Compose (`finance_db` / `finance_backend` / `finance_frontend` containers). Runs locally on Windows 11 with Rancher Desktop; not yet deployed to a server.

## Running and deploying — read this before touching anything

```
docker compose up -d
```
Frontend: http://localhost:3000, Backend: http://localhost:8000, Postgres: localhost:5432.

There is **no test suite and no lint script** — `frontend/package.json` only defines `dev`/`build`/`start`, and `backend/requirements.txt` has no test framework. Don't go looking for `npm test` or `pytest`; they don't exist. There is also **no git repository** — there is no commit history, branches, or diff tooling to rely on; treat the working tree as the only source of truth.

There is no live Alembic usage despite it being a dependency — schema changes are applied as hand-written raw SQL run via `docker exec -i finance_db psql -U finance_user -d finance < script.sql`, and one-off data fixes are plain `.py` scripts (see `backend/app/fix_periods.py`, `backend/resort_articles_pl.py` for examples of the pattern) run via `docker exec finance_backend python <script>.py`. Back up before any destructive change: `docker exec -t finance_db pg_dump -U finance_user finance > backup_name.sql` (the `backups/` folder holds prior examples).

**The single most important gotcha in this repo:** the frontend container builds with `next build` and serves with `next start` (production mode, see `frontend/Dockerfile`) — it does **not** run `next dev`. Editing a frontend file and restarting the container changes nothing; the stale compiled `.next` output keeps being served. Any frontend change requires, inside the container, `rm -rf .next && npm run build` before `docker restart finance_frontend`. The backend, by contrast, runs `uvicorn --reload` (see `backend/Dockerfile`), so a backend change only needs `docker restart finance_backend` — no rebuild.

Files are pushed into the running containers rather than rebuilt from source, e.g.:
```
docker exec -i finance_backend sh -c "cat > /app/app/routers/operations.py" < "F:\finance\backend\app\routers\operations.py"
docker exec -i finance_frontend sh -c "cat > /app/pages/operations.js" < "F:\finance\frontend\pages\operations.js"
```
This must be run from `cmd`, not PowerShell — PowerShell mangles the Cyrillic strings inside these files on redirect. Any `.bat` deploy script must stay pure ASCII (no Cyrillic, no `chcp`) for the same reason.

## Backend architecture

Routers are mounted in `app/main.py` under `/api/<name>` (auth, operations, reports, counterparties, articles, settings, users, roles). `Base.metadata.create_all()` runs on every startup, but **`bank_balances` is not an ORM model** — it only exists via raw `sqlalchemy.text()` SQL in `settings.py`/`reports.py`, so it must have been created out-of-band; don't expect `create_all` to provision it on a fresh DB.

**Permissions** (`app/permissions.py`) are driven by the `SECTIONS` list — the canonical registry of gateable areas (`dashboard`, `pl`, `balance`, `planfact`, `receivables`, `operations`, `import`, `settings_balances`, `counterparties`, `articles`), each with its own allowed actions (subset of view/create/edit/delete). `require_permission(section, action)` is the FastAPI dependency used to gate endpoints; the `admin` role bypasses every check unconditionally and is never represented by rows in `role_permissions` (its permissions are synthesized as all-true). "Пользователи" and "Журнал действий" are deliberately **not** in `SECTIONS` — they're gated by the separate hardcoded `require_admin` dependency in `app/audit.py` instead, so adding a new permission section there won't affect them.

**Auth**: JWT via `python-jose`, 8-hour expiry. `SECRET_KEY` defaults to the literal `"supersecretkey2024"` in `auth.py` but is also set directly in `docker-compose.yml`'s `environment:` block — if you ever need to rotate it, both places exist but only the compose env var takes effect at runtime via `os.getenv`. `auth.py`'s `/login` does local (function-scope) imports of `log_action` and `get_permissions_for_user` to avoid a circular import, since both `audit.py` and `permissions.py` import from `auth.py`.

**Audit logging** (`app/audit.py`): `log_action(db, user, action, entity_type, entity_id, details)` is called after most mutating endpoints. The Russian-language label map (`ACTION_LABELS` in `users.py`) is partial — some newer bulk-action strings aren't in it and fall back to displaying the raw action string in the Журнал действий UI.

**Period normalization** is a cross-cutting concern duplicated rather than centralized: periods are stored either as `YYYY-MM` or as a quarter string (`"Q1 2026"`, produced from the frontend's quarter-entry mode). `_normalize_period()`-style logic and the quarter→3-equal-months expansion are reimplemented separately in `operations.py` and inline in each of `reports.py`'s `/dds`, `/pl`, and `/plan-fact` endpoints (`expand_quarter_rows` / inline regex). In `/pl` and `/plan-fact`, date-range filtering happens **after** this quarter expansion — changing that order silently breaks partial-quarter filtering. `app/fix_periods.py` is a historical one-off normalization script, already run; it's not part of any live flow.

**P&L grouping** is entirely data-driven by each `Article`'s `group`/`subgroup` columns, not hardcoded per-article logic. `PL_GROUPS_ORDER` in `reports.py` defines both the section ordering and the formulas: `gross_profit = revenue(ВЫРУЧКА) − cogs(СЕБЕСТОИМОСТЬ)`, `ebitda = gross_profit − opex(ОПЕРАЦИОННЫЕ) − marketing(МАРКЕТИНГ)`, `net_profit = ebitda − taxes(НАЛОГИ)`. Articles grouped `НЕ В P&L` (ТРАНЗИТ, ДИВИДЕНТЫ, ПРОЧЕЕ) are excluded from every report. Article display order (in dropdowns and the Статьи registry) comes from `Article.sort_order`, edited via drag-equivalent up/down moves in `articles.py`, not from name or id.

**Receivables aging** (`reports.py`): due date = first day of the month after the operation's period, plus a per-counterparty term (`DEFAULT_TERM_DAYS=60`, overridden by `TERM_OVERRIDES_BY_INN` for two specific ИНН, e.g. 90/120 days) — there's no general contract-term field yet, only this hardcoded override map. `GRACE_DAYS=30` buffers "current" vs "overdue". This logic (`_due_date`, `_aging_bucket`, `_term_days_for_inn`) is imported directly into `operations.py` to compute a per-row `receivable_status`, which is a real coupling between the two routers — changing the aging rules in `reports.py` changes what `/operations` displays too.

**Bulk-edit pattern**, used identically in `operations.py` and `counterparties.py`: a Pydantic model with `ids: List[int]` plus `Optional[...] = None` fields, then `payload.dict(exclude={"ids"}, exclude_unset=True)` so only explicitly-sent fields are touched, then a per-row `setattr` loop. For operations, touching `vat_rate` also triggers `vat_fact` recomputation as a special case — don't add a new derived field without checking whether bulk-edit needs the same special-case handling.

**Excel import** (`operations.py`) has two independent paths: a one-shot `/import` (always inserts, creates duplicates on re-run — used only for the very first load) and a two-phase `/import/preview` + `/import/apply` sync flow that matches existing rows by № ДС + № Счёта (falling back to a natural-key match for rows missing those) and only writes back fields the user explicitly confirms. The downloadable template (`/import/template`) enforces Статья and НДС% as hard dropdowns (`DataValidation(type="list", ..., errorStyle="stop")` — free text is rejected by Excel itself, not just validated server-side); the Статья list is long enough that it's routed through a hidden "Справочники" worksheet rather than an inline list formula (inline `formula1` lists are capped at ~255 chars in Excel).

## Frontend architecture

There is no shared API client, no `lib/` or `utils/` folder, and no env-based config: every page file (`login.js`, `dashboard.js`, `operations.js`, `settings.js`, `pl.js`, `balance.js`, `planfact.js`, `receivables.js`, `import.js`) independently hardcodes `http://localhost:8000/api` as its axios `baseURL`. Likewise, `getPermissions()`/`can(perms, section, action)` are redefined identically in most page files rather than imported from the one place that exports them (`components/Navbar.js`) — if you change permission-checking behavior, you likely need to change it in every page, not just one. `main.py`'s CORS `allow_origins` is hardcoded to `http://localhost:3000` the same way.

All client auth/session state lives in `localStorage` (`token`, `role`, `role_label`, `is_admin`, `permissions`, `name`), written once at login and read inside `useEffect` (never during render/SSR, since `localStorage` doesn't exist server-side). Permissions are a snapshot from login time — if an admin changes a user's role or a role's permissions, that user's UI won't reflect it until they log out and back in.

`Navbar.js` is shared by `dashboard`, `pl`, `balance`, `planfact`, `receivables`, and `operations` — its `NAV_ITEMS` list (filtered through `can()`) is the actual source of truth for which report tabs exist and what permission section gates each one. `settings.js` and `import.js` intentionally do **not** use `Navbar` — they have their own bespoke header bar instead, reached via separate buttons in Navbar's top row ("⚙️ Настройки", "Импорт") rather than the tab row. Don't assume every page shares the same chrome.

`dashboard.js` still contains `pl`/`balance`/`planfact` tab bodies (rendering "в разработке" placeholders) from before those became standalone pages (`pl.js`, `balance.js`, `planfact.js`). That code is unreachable in normal use since `Navbar` now links straight to the dedicated pages — it's dead code, not a sign that those reports are unfinished.

`settings.js` is one large component covering every "Настройки" tab (Остатки по банкам, Пользователи, Роли, Контрагенты, Статьи, Журнал действий) gated tab-by-tab through `can()`/role checks inside a single file, rather than being split into separate page components.

Styling is inline `style={{...}}` objects throughout, no CSS modules/Tailwind/styled-components; the only shared styling surface is the CSS custom properties defined in `styles/globals.css` (`--primary`, `--success`, `--danger`, `--warning`, `--bg`, `--card`, `--border`, `--text`, `--muted`). Bank-specific colors (`АльфаБанк`/`ОПТ Банк`/`Совкомбанк`/`Наличные`) are redefined as local `BANK_STYLES`/`BANK_COLORS` constants per file rather than shared.

## Data model notes

`Counterparty.group_override` lets a user manually pin the "Группа" shown in the Контрагенты registry; when unset, the registry computes it as the counterparty's single most-frequent Статья (not the Статья's `group` category) — these are two different notions of "group" living side by side. `Counterparty.status` (`действующий` / `виртуальный`) exists in the schema and is enforced in `counterparties.py`, but has no dedicated UI filter affordance beyond the registry's status filter — don't assume "виртуальный" rows are excluded elsewhere unless you check each query.

`Operation.vat_fact` is a derived field (from `income`/`expense` and `vat_rate`) recomputed server-side wherever `vat_rate` changes (single edit, bulk edit) — never trust a client-supplied `vat_fact`.
