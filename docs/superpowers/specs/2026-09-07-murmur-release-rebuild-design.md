# Murmur Release Rebuild Design

**Date:** 2026-09-07

## Goal

Turn the existing Murmur prototype into a credible local-first release candidate without changing its core job: capture a thought by voice or text, turn it into an organized record, and make it easy to find later.

This is the first repo in the broader portfolio completion program and uses both approved modes: finish the current product and strengthen the weak parts that would otherwise make release premature.

## Current product truth

The repository already contains:

- React 19 + Vite client
- voice capture with explicit browser microphone permission
- typed capture
- FastAPI backend
- SQLite/SQLModel persistence
- Faster-Whisper local transcription dependency
- deterministic skill/processing module
- spaces such as Memory, Work, Records, Care, and Bug report
- search/filtering in the client
- Docker backend configuration
- frontend build CI and backend pytest CI

The rebuild must extend this implementation rather than replacing it with a generic AI notes app.

## Product promise

> **Say it once. Find it when it matters.**
>
> Murmur is a private voice inbox for facts, reminders, work notes, bug reports, care notes, and everyday memory. Capture naturally, let local processing organize the record, then search, review, export, or delete it whenever you need it.

## Scope

### 1. Capture

Voice and typed capture remain first-class.

Voice capture requirements:

- microphone starts only after explicit user action;
- recording stops immediately when the user stops capture or closes the composer;
- empty recordings are rejected cleanly;
- unsupported browser/runtime states fall back to typed capture;
- transcription errors never destroy the original unsaved text state;
- audio is treated as transient by default and is not retained after successful transcription unless a future explicit recording-retention feature is separately designed.

Typed capture requirements:

- usable while the transcription backend is unavailable;
- deterministic organization must not require an LLM;
- save errors keep the draft visible and retryable.

### 2. Organization

Every saved Murmur receives:

- stable ID
- title
- transcript/body
- space
- source (`voice` or `text`)
- created timestamp
- updated timestamp
- optional tags
- optional pinned state

The deterministic organizer is the source of truth. Optional model enrichment may suggest a better title, tags, or space, but invalid/model-failed output must fall back to deterministic results.

The system must never imply that model inference is required for basic use.

### 3. Library and retrieval

The release client needs:

- full-text search across title/body/space/tags;
- space filtering;
- sort newest/oldest/title;
- pin/unpin;
- open detail/edit flow;
- delete with confirmation;
- empty states that do not seed or mix fake demo records with user data;
- timeline/list view that remains usable on narrow mobile widths.

### 4. Data ownership

Users must be able to:

- export all records as versioned JSON;
- export a readable CSV;
- import/restore a validated versioned JSON backup;
- reject malformed or unsupported backups without partially mutating current data;
- erase all records through a deliberate confirmation flow;
- delete individual records.

Backup restore should be transactional at the application level: validate the complete envelope before replacing or merging records.

### 5. Privacy and security

Murmur remains local/self-hosted by default.

- no analytics SDK;
- no advertising SDK;
- no silent cloud transcription;
- no third-party network call in the default local path other than the user-configured frontend-to-backend origin;
- CORS must be explicit and configurable rather than wildcard production access;
- uploaded audio must have a bounded size and accepted content types;
- filenames supplied by browsers are not trusted for filesystem paths;
- generated exports must avoid spreadsheet formula injection in CSV fields;
- destructive actions require explicit confirmation;
- README/privacy documentation must distinguish application privacy from full-disk encryption.

The product should not claim end-to-end encryption when local transcription/backend processing requires plaintext in memory.

### 6. Backend reliability

The FastAPI service should provide stable versioned behavior for:

- health
- list/create/update/delete Murmurs
- transcribe
- process/organize
- stats
- JSON backup/export
- JSON restore/import
- CSV export

Errors should use bounded, user-safe messages and must not expose local filesystem paths or secret configuration.

### 7. Direct verification

GitHub Actions may remain as convenience automation, but the source acceptance contract must run locally from one documented command.

The direct gate must cover:

- frontend deterministic install when lockfile is present
- frontend production build
- backend dependency install guidance
- backend pytest
- Python compile check
- JSON/schema/backup roundtrip tests
- deterministic organization tests
- CSV safety tests
- API CRUD tests

A later real browser acceptance pass covers microphone permission, record/stop, typed fallback, narrow layout, search, edit/delete, backup/export/restore, and backend-offline copy.

## Open-source use

Existing open-source foundations should be kept where they fit:

- FastAPI (MIT)
- SQLModel (MIT)
- Faster-Whisper (MIT)
- React (MIT)
- Vite (MIT)
- lucide-react (ISC)

Additional dependencies should be added only if they remove substantial risk or implementation complexity. Prefer small local helpers over new packages for backup schema validation, CSV escaping, and deterministic organization.

Do not copy GPL/AGPL code into Murmur. Architecture or UX concepts from copyleft projects may be studied, but implementation remains clean-room.

## UI direction

Keep the current dark/private workspace identity, but reduce demo-dashboard behavior.

Primary hierarchy:

1. Capture
2. Search/library
3. Record detail
4. Spaces/tags
5. Data/privacy/settings

The microphone is important but must not dominate every screen once records exist. The library should feel like a private searchable archive rather than a marketing dashboard.

## Error handling

- Backend unavailable: keep local draft, show typed capture, do not claim save succeeded.
- Microphone denied: typed capture remains immediately available.
- Transcription failure: show retry state; no fake transcript.
- Import invalid: reject before mutation and explain which validation class failed.
- Restore conflict: default to explicit replace or merge choice, never silent destructive replacement.
- Export failure: keep data untouched and show retryable error.

## Testing strategy

Backend tests should use a disposable SQLite database and HTTP test client. Deterministic organizer tests should avoid model/provider dependencies. Backup tests must cover malformed versions, duplicate IDs, invalid timestamps, oversized payloads, and successful roundtrip. CSV tests must cover cells beginning with `=`, `+`, `-`, and `@`.

Frontend source/build checks should verify that demo data is not inserted into the real library path, destructive flows require confirmation, and offline/backend-unavailable copy remains truthful.

## Release boundary

Repository work can produce a **release candidate**. A public hosted deployment still requires the owner to choose a host, configure the allowed frontend origin, decide whether the backend is local-only or remotely self-hosted, provision TLS when remote, and perform final privacy/security review for that deployment.

No hosted production deployment is implied by source completion.

## Non-goals

- no social feed;
- no public sharing network;
- no generic chatbot;
- no always-listening microphone;
- no surveillance/ambient recording;
- no automatic cloud backup;
- no paid subscription until the core release proves useful;
- no mobile-native rewrite in this pass.

## Acceptance criteria

Murmur is ready to merge as a release candidate when:

1. exact branch head passes the direct verification contract;
2. CRUD, deterministic organization, transcription boundary, backup/restore, CSV safety, and erase/delete tests pass;
3. demo records are not persisted or mixed with real records;
4. README/privacy/security/release docs match implemented behavior;
5. frontend build and backend tests run from a clean checkout;
6. a real browser smoke verifies voice capture, typed fallback, search, edit/delete, export/restore, narrow layout, and backend-offline states;
7. remaining deployment-only gates are listed explicitly rather than hidden behind a "100% complete" claim.