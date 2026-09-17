# AI Resume Screening System — Frontend

React (Vite) + TypeScript, custom hand-written CSS (no Tailwind/UI framework), matching the
project doc's tech stack decision. Talks to the FastAPI backend built earlier.

## Structure

```
src/
  api/            Axios client + one file per backend resource (auth, resumes, jobs)
  components/     Navbar, RecommendationBadge, ProtectedRoute
  context/        AuthContext — holds the JWT + current user, wraps the whole app
  pages/          Login, Register, Dashboard (candidates+upload), JobsList, JobDetail (matching+shortlist)
  styles/         variables.css (design tokens) + global.css (custom CSS, no framework)
  types/          Shared TypeScript interfaces matching the backend's Pydantic schemas
```

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

Runs on http://localhost:5173. The Vite dev server proxies `/api/*` straight to
`http://localhost:8000` (see `vite.config.ts`), so the FastAPI backend must be running
first — same two terminals (`uvicorn` + `celery`) from the backend setup.

## What's implemented

- Register / login (JWT stored in localStorage, attached to every request automatically)
- Protected routes — redirects to /login if not authenticated, and on any 401 response
- Resume upload (multi-file) + candidate list, **polls automatically** while any candidate
  is still processing (queued/extracting/embedding), stops polling once all are ready/failed
- Job posting creation (paste a JD, create it)
- Trigger matching for a job, with a configurable top-K
- Shortlist view — score, recommendation badge (Shortlist/Review/Pass), matched/missing
  skills, polls a few times after triggering matching since it runs async via Celery

## What's deliberately NOT built yet (next steps)

- No strengths/gaps detail view (currently only matched/missing skills shown in the table;
  the API already returns strengths/gaps, just needs a per-candidate detail panel/modal)
- No pagination on candidate list or shortlist (fine at current dev scale, not at 1,000+ resumes)
- No file drag-and-drop, just a standard file input
- No loading skeletons — plain "Loading..." text
- No responsive/mobile layout pass yet
- No tests

## Design notes

- All styling is custom CSS using design tokens in `styles/variables.css` (colors, spacing,
  radius) — deliberately no Tailwind/component library, per the project's stack decision.
- Recommendation badges (Shortlist/Review/Pass) use distinct colors defined as tokens, not
  hardcoded per-component, so the palette stays consistent and easy to change globally.

## Important note on verification

This code was written and manually reviewed for consistency (imports, types, API contracts
matching the backend), but **could not be installed or compiled in the environment it was
built in** (no network access to npm's registry there). Run `npm install` and `npm run dev`
on your own machine as the real first test — if anything doesn't compile, it hasn't been
caught yet the way the backend's Python code was (which was syntax-checked and, separately,
actually run).
