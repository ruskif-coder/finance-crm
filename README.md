# Finance CRM

Internal financial management system — cash flow, P&L, balance sheet, receivables, and counterparty registry.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.111 · SQLAlchemy 2.0 · PostgreSQL 16 |
| Frontend | Next.js 14 · React 18 · Recharts |
| Proxy | Caddy (automatic HTTPS) |
| Runtime | Docker Compose on Windows 11 / Docker Desktop |

## Features

- DDS (cash flow) with bank breakdown and charts
- P&L by article group (ВЫРУЧКА / СЕБЕСТОИМОСТЬ / ОПЕРАЦИОННЫЕ / МАРКЕТИНГ / НАЛОГИ)
- Balance sheet with bank balances
- Plan-fact comparison
- Receivables aging report
- Operations journal with bulk edit and Excel import/export
- Counterparty registry with requisites and contract cards
- Contract registry (linked to counterparties, file attachments, EDO status)
- Role-based access control (RBAC) with audit log
- JWT authentication with login lockout

## Quick start

```bash
# Copy .env.example to .env and fill in secrets
cp .env.example .env

# Start all services
docker compose up -d
```

Open **http://localhost** (through Caddy on port 80).  
Do **not** use http://localhost:3000 directly — API calls will fail.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full runbook: domain, DNS, router port-forwarding, and going live on the public internet.

## Development notes

- Frontend runs in **production mode** (`next build` + `next start`). Any frontend change requires a rebuild inside the container:
  ```bash
  docker exec finance_frontend sh -c "rm -rf /app/.next && npm run build"
  docker restart finance_frontend
  ```
- Backend runs `uvicorn --reload` — a `docker restart finance_backend` is enough after backend changes.
- Push files into containers from `cmd.exe` (not PowerShell) to avoid Cyrillic encoding issues.
- Run `deploy_finance.bat` for a full backup → rebuild → redeploy cycle.

## License

Private and confidential. See [LICENSE](LICENSE).
