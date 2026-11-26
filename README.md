# Planora

**An AI-powered goal planner that turns a goal into a realistic, day-by-day plan, and keeps it
realistic as life happens.**

🔗 **Live site:** https://planora-chi-ebon.vercel.app

Describe a goal, say how many hours you have and on which days, and Planora:

1. **Breaks the goal into milestones and tasks** with Google Gemini. The AI's output is validated
   and repaired before anything is saved, and a generic plan is used if the AI is unavailable.
2. **Predicts how long each task will take you**, once you've finished enough tasks for it to learn
   your pace.
3. **Fits the work into your available hours.** It never goes over your daily limit and never uses
   your days off.
4. **Replans every evening** from a short end-of-day review. Unfinished work is spread across the
   remaining days. If the plan no longer fits before the deadline, you get a warning and options to
   fix it. Your hours and deadline only change if you choose to.

## Features

- Goal → AI breakdown with validation checks → schedule, in three steps
- Dashboard with today's plan, the week, goal health, a progress snapshot and plan updates
- Week and day schedule views; work past the deadline is shaded, never squeezed in
- End-of-day review (done / partly / not done), including missed days within a 3-day window
- Fix options: extend the deadline, add hours (only with consent), add a day, or drop optional tasks
- Progress: completion, estimated vs. actual time, review history
- In-app notifications, profile and plan preferences
- Responsive (phone tab bar, full-screen desktop dashboard), keyboard-accessible, contrast-checked

## How it works

| Part | Decides | Code |
|---|---|---|
| **LLM** (Google Gemini) | *what* work is needed | `backend/app/services/llm.py`, `validation.py` |
| **ML model** (scikit-learn) | *how long* a task will take *you* | `backend/app/ml/` |
| **Scheduler** (pure, deterministic Python) | *when* each task happens | `backend/app/services/scheduler.py` |

`planner.py` is the only place that combines them with the database.

**About the ML model:**
- It's trained on **synthetic** data, because there's no real user history yet.
- It switches on only after a user has 20 finished tasks with logged time.
- It was saved only because it beat both simple baselines in cross-validation: MAE 1.067 h, against
  1.084 h for "estimate × the user's usual ratio" and 1.549 h for the AI's estimate alone. On
  held-out users, it and the ratio rule are about equally good (1.155 h vs 1.147 h).
- The training code is in `backend/ml/`.

## Tech stack

- **Frontend:** plain HTML, CSS and JavaScript (ES modules). No framework and no build step.
- **Backend:** Python, FastAPI, SQLAlchemy 2, PostgreSQL (psycopg 3), JWT + bcrypt.
- **AI / ML:** Google Gemini API, scikit-learn, pandas, numpy.
- **Hosting:** Vercel (website + API) and Neon (PostgreSQL).

## Project layout

```
├── backend/
│   ├── app/          FastAPI app: routers, services (LLM, scheduler, planner), models, ML predictor
│   ├── ml/           Training scripts and the saved model (synthetic data)
│   ├── scripts/      seed_demo.py: creates a demo account
│   └── tests/        pytest suite
├── frontend/         The website (served by the backend at /app/)
├── index.py          Vercel entry point
└── vercel.json       Vercel settings
```
