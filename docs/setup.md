# ORCA Setup & Local Development Guide

## 1. Prerequisites
- **Operating System**: Linux / macOS compatible
- **Node.js**: v22+
- **Python**: 3.12+
- **PostgreSQL**: 15+ (with PostGIS optional if available)
- **Git**

## 2. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure database credentials and at least one LLM key (`GROQ_API_KEY` or `GEMINI_API_KEY`) are populated.

## 3. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Verify backend health at: `http://localhost:8000/health`

## 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open Vite development server at: `http://localhost:5173`

## 5. Verification
Run the verification script from the root:
```bash
python scripts/check_environment.py
```
