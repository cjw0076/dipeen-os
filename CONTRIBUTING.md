# Contributing to dipeen

## Prerequisites

- Node.js 22+
- Python 3.11+
- Docker + Docker Compose
- Redis (or use Docker Compose which includes it)

## Local Setup

```bash
git clone https://github.com/your-org/dipeen.git
cd dipeen

# Backend
cd api
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and DIPEEN_SECRET_KEY

# Frontend
cd ../web
npm install

# Agent client
cd ../agent-client
pip install -e .
cp .env.example .env   # fill in API_URL, AGENT_ID, ANTHROPIC_API_KEY
```

Run everything:

```bash
# Option A — Docker (recommended)
docker compose up

# Option B — separate terminals
cd api   && uvicorn app.main:app --reload --port 8000
cd web   && npm run dev
cd api   && python pm_loop.py
cd agent-client && python -m dipeen_agent start
```

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | When to use |
|--------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change with no feature or fix |
| `test` | Adding or fixing tests |
| `chore` | Build process or tooling changes |

Examples:
```
feat(office): add proximity bubble animation
fix(pm-loop): handle empty task list in PLANNING state
docs: update agent setup instructions in README
```

## Pull Request Guide

1. Create a branch from `main`: `git checkout -b feat/your-feature`
2. Keep PRs focused — one feature or fix per PR
3. Make sure `docker compose up` still builds without errors
4. Add a brief description of what changed and why
5. Reference any related issue: `Closes #42`

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI backend — routers, models, pm_loop.py |
| `agent-client/` | Agent runtime (BYOK, task polling, Claude subprocess) |
| `web/` | Next.js frontend — chat, office canvas, sidebar |
| `docs/` | Design specs and roadmap |
