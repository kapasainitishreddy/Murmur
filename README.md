# Murmur

**Say it once. Find it when it matters.**

Murmur is a private voice inbox for facts, reminders, work notes, bug reports, care notes, and everyday memory. Capture by voice or text, organize the result locally, and keep it searchable without turning your personal archive into an advertising or analytics feed.

## Current product

Murmur has two parts:

- a React/Vite client for capture, search, spaces, and review;
- a FastAPI backend using SQLite/SQLModel and Faster-Whisper for local transcription.

The default product path does not require an LLM. Deterministic organization is the baseline behavior. The project is being hardened toward a release candidate; it should not be described as a hosted production service yet.

## Privacy boundary

- Microphone access starts only after explicit user action in the browser.
- Uploaded audio is processed as a temporary file and deleted after transcription completes or fails.
- The default transcription engine is Faster-Whisper running on the configured backend.
- No analytics or advertising SDK is required by the product.
- The frontend talks only to the configured Murmur API origin by default.
- Local/self-hosted does **not** mean end-to-end encrypted: text and audio must exist in plaintext in process memory while being handled.
- Device/full-disk encryption remains the responsibility of the operating system or deployment environment.

See `docs/superpowers/specs/2026-09-07-murmur-release-rebuild-design.md` for the release boundary and accepted scope.

## Run locally

### Frontend

```bash
npm install
npm run dev
```

The frontend uses `VITE_API_URL` when present and otherwise expects the API at `http://localhost:8000`.

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Useful backend environment variables:

```text
DATABASE_URL=sqlite:///./murmur.db
CORS_ORIGINS=http://localhost:5173
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
MAX_UPLOAD_MB=40
```

Use an explicit `CORS_ORIGINS` value for any remote deployment.

## Existing API surface

- `GET /health`
- `GET /api/skills`
- `POST /api/process`
- `GET /api/murmurs`
- `POST /api/murmurs`
- `DELETE /api/murmurs/{id}`
- `GET /api/stats`
- `GET /api/export.csv`
- `POST /api/transcribe`

The release-completion branch is adding validated backup/restore, safer exports, richer record management, and a direct verification contract. Do not advertise those items as available on `main` until their implementation PR is merged.

## Verification policy

The portfolio is currently in **zero-CI completion mode**. GitHub Actions is deliberately manual so repository work can be prepared and reviewed without repeatedly consuming hosted minutes.

The rule is:

1. prepare the complete candidate;
2. run local/direct checks;
3. inspect the final diff;
4. invoke GitHub Actions manually only for a frozen release candidate.

The portability helper tests are dependency-light and can be run directly:

```bash
cd backend
PYTHONPATH=. pytest -q tests/test_portability.py
```

The complete backend suite is:

```bash
cd backend
pytest -q
```

The frontend production check is:

```bash
npm run build
```

## Release status vocabulary

- **Code-complete:** repository-controlled implementation and deterministic checks pass.
- **Release-candidate:** code-complete plus recovery, privacy, export/delete, packaging, and applicable acceptance checks pass.
- **Released:** the actual production/device/deployment path has been exercised successfully.

Murmur should not be called released merely because source code exists.
