# AGENTS.md

## Project Quick Start

- chemssh is a FastAPI + Vue 3 workspace app for computational chemistry workflows.
- Backend code lives in `backend/app`; frontend code lives in `frontend/src`; tests live in `tests`; API and interaction notes live in `docs/API.md`.
- Read `docs/API.md` before adding a new window/module. It documents backend endpoints, frontend API wrappers, and window-to-window file drag behavior.

## Encoding And Editing

- Always read and write documents, configuration files, and source files as UTF-8.
- Do not rely on the system default encoding; this project contains Chinese text and previously had mojibake issues.
- Preserve existing formatting, indentation, and line endings unless the task requires a broader cleanup.
- Keep changes scoped. Do not revert unrelated local edits.

## Backend

- Framework: FastAPI.
- API routers: `backend/app/api`.
- Pydantic models: `backend/app/models`.
- Business logic: `backend/app/services`.
- Filesystem safety is enforced through `WorkspaceSecurity`; all file paths must stay inside `workspace.root`.
- File type detection is in `backend/app/services/file_types.py`.

Common verification:

```powershell
.\.venv\Scripts\python -m pytest tests\test_api.py
```

Run a narrower test file when the change is focused. Use the full test suite for cross-cutting backend changes:

```powershell
.\.venv\Scripts\python -m pytest
```

## Frontend

- Framework: Vue 3 with `<script setup lang="ts">`.
- UI library: Element Plus.
- Main workspace: `frontend/src/views/Workspace.vue`.
- File manager: `frontend/src/components/FileTree.vue`, `FileToolbar.vue`, `FilePreview.vue`.
- Terminal: `frontend/src/components/terminal/TerminalPanel.vue`.
- API wrappers: `frontend/src/api`.
- Global styles: `frontend/src/styles.css`.
- i18n strings: `frontend/src/i18n.ts`.

After modifying frontend code, you usually do not need to start the backend/server. Verify with:

```powershell
cd frontend
npm.cmd run build
```

If sandboxed `npm` fails on Windows, rerun the same command with approval outside the sandbox.

## Window Interaction Conventions

- The file manager supports normal drag selection and long-press file drag.
- Long-press file drag protocol is implemented in `frontend/src/api/fileDrag.ts`.
- Internal file drag MIME: `application/x-chemssh-files`.
- Terminal drops insert selected absolute paths as text, prefixed by one space and joined by spaces.
- Preview drops open only the first selected path.
- External browser drops use download URLs; multiple files or directories download as `chemssh-selection.zip`.
- New modules that accept dragged files should use `hasChemSSHFileDrag` and `readChemSSHFileDrag` from `frontend/src/api/fileDrag.ts`.

## Documentation Expectations

- Update `docs/API.md` when adding or changing backend endpoints, frontend API wrappers, or window interaction behavior.
- Document enough for a future agent to implement compatible features without reading the whole codebase.
- Include request/response shapes and the preferred frontend wrapper when practical.

## Practical Notes

- Prefer existing helpers in `frontend/src/api` instead of ad hoc `fetch`.
- Prefer existing backend services/providers instead of putting business logic in routers.
- Large file previews should ask for confirmation before using `force=true`.
- Do not start a dev server unless the user explicitly needs to try the running UI.
