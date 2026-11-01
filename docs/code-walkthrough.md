# A guided tour of Family Medical Records

Start with the main flow, then open the architecture map. The remaining views zoom into one responsibility at a time. Every block has an ID such as `B6`; search for `#B6` in the source to find comments explaining the corresponding code. Paths in comments are relative to the repository root.

The diagrams describe the current implementation: processing starts when a file is submitted or a text draft is saved, all AI requests use the configured primary service, and ordinary chat is read-only. They do not imply a processing confirmation prompt, automatic backup-provider switching, or a permanent chat archive.

## Choose a zoom level

| View | Open the diagram | What this view explains | Start reading here |
| --- | --- | --- | --- |
| 00 | [Main flow](../AGENTS.svg) · [繁體中文](../AGENTS.zh-TW.svg) | Add → process → review → browse → ask → verify. This is the demonstration route. | [App.tsx](../src/App.tsx) |
| 01 | [Component architecture](../implementation-architecture.svg) | Which components own browser state, HTTP, workflow, storage, evidence conversation and AI calls. | [api.py](../backend/api.py), [types.ts](../src/import/types.ts) |
| 02 | [UI and editing](../src/import/ui-flow.svg) | Drafts, uploads, receipts, polling, source viewing, correction, recheck, retry and deletion. | [ImportPanel.tsx](../src/import/ImportPanel.tsx), [Viewer.tsx](../src/import/Viewer.tsx) |
| 03 | [Import processing](../backend/import-pipeline.svg) | How one stored original becomes text, concerns, classifications and an index; what survives failure. | [filing.py](../backend/filing.py), [processing.py](../backend/processing.py) |
| 04 | [Storage procedures](../backend/library-storage.svg) | Atomic writes, idempotency, ownership, revisions, member links, derived indexes and deletion. | [storage.py](../backend/storage.py) |
| 05 | [Data relationships](../backend/database-schema.svg) | Patient → organizational archive → documents, plus immutable source, editable text and separate processing/index state. | [schema.sql](../backend/schema.sql), [departments.py](../backend/departments.py) |
| 06 | [Browsing and dates](../src/library/browsing-flow.svg) | How saved facts become member/department/date folders, and where unresolved values go. | [browsing.ts](../src/library/browsing.ts), [dates.ts](../src/dates.ts) |
| 07 | [Evidence conversation](../backend/chat-flow.svg) | Scope → catalog → constrained tools → current text → citation validation → final review → source links. | [chat.py](../backend/chat.py), [ChatPanel.tsx](../src/chat/ChatPanel.tsx) |

Blue arrows show the main sequence or a direct dependency. Amber cards explain a related safeguard; their dashed connectors do not add another stage to the main path. The data diagram lists ownership and derived tables, not a clinical sequence. The architecture map shows calls rather than requiring every user action to pass through every component.

## Follow one report through the code

**Begin with the demo notice (`U16`).** `DemoNotice` explains synthetic data, paid Gemini processing and server retention. The checkbox enables Continue; only the content body scrolls, while controls remain visible. Acceptance lasts for one page load and is separate from submitting an individual report. A persistent footer repeats the demo-only limits.

**First, establish what was saved.** `ImportPanel.submit` sends one operation key per file (`U3/U4`). `api.upload` validates size/type, then `Library.create` commits the original, identity and pending state before the executor runs (`S2/S3`). The response means the original exists. It does not mean AI processing is complete.

**Then follow the background stages.** `FilingWorkflow.run` claims that identity using an attempt token (`B1/B10`). It calls `processing.extract`, saves initial/current text, asks for suspected errors, requests structured filing arguments, validates their supporting quotes, and commits the filed state (`B2–B7`). A text-check failure can remain visible even when filing succeeds (`B11`). Missing or conflicting dates and names are retained as data.

**Next, inspect and correct it.** `App.refresh` polls stored snapshots and ignores reads older than a local mutation (`U5`). `Viewer` opens the saved document and `/original`; `PdfSource` renders PDFs without relying on a browser plugin (`U9`). Editing captures a baseline revision. A save changes current text/details, preserves original/initial text, invalidates the old worker, and makes old text-check results stale (`U7/S5`). Recheck compares revisions before and after the AI call (`U12`).

**Finally, retrieve it.** `LibraryBrowser` uses `browsing.ts` and `dates.ts` to derive folders without an AI call (`R1–R7`). Chat receives the shared member scope and an optional saved viewer document. The backend supplies the full scoped catalog, reads relevant saved text, validates the proposed citations, and asks for a final evidence review (`C1–C8`). A Sources link returns through `App.select` to the same document ID (`C9/F6`).

## Why the extra branches exist

| Situation | Defensive procedure | Why it matters |
| --- | --- | --- |
| A response disappears after an upload was saved | Same operation key and fingerprint, `S2/U4` | Retry must not create a second report. |
| An old poll returns after a save or deletion | Local mutation counter, `U5` | Stale reads must not undo a confirmed visible action. |
| A worker finishes after a human correction | Attempt-token comparison, `B10` | Late AI output must not overwrite the correction or resurrect deleted evidence. |
| Two editors save different versions | Revision comparison inside a transaction, `S5` | Reject the stale save instead of silently losing newer work. |
| A recheck finishes after text changed | Second revision comparison, `U12` | Old concerns must not be attached to new text. |
| Checking or the provider fails | Independent check/filing state, explicit errors and Retry, `B8/B9/B11/C11` | Available evidence remains accessible; incomplete work is not presented as complete. |
| A patient name or date is unclear | Exact matching, explicit unknown/tentative placement, `S8/R3/R6` | A tidy tree is not worth merging people or inventing visit dates. |
| Indexing stops halfway through | Durable target revision and job state, `D10/S10` | Retrieval can report an outdated/failed derivative and rebuild it from saved evidence. |
| A report contains instructions or AI invents a quote | Treat text as untrusted; validate tool shape, source quote, identity and revision, `O7/B6/C7` | Documents provide evidence, not permission to run arbitrary actions. |
| A question needs too much context | Explicit character/step limits, `C11` | Fail visibly rather than silently omit history and claim the search was complete. |
| Someone resets the shared demo | Explicit confirmation, atomic cascade and client remount, `U15/S12` | Clear all library evidence/members together; retain current UI state if the reset fails. Old workers and canceled uploads must not repopulate deleted records. |

These guards establish consistency and traceability. They do not prove that a report is medically correct or that the AI has interpreted every passage correctly. Prompts and a final model review remain fallible; the original is available for the patient and clinician to check.

## Responsibilities that are easy to confuse

- **A managed family member is not a login.** `MemberForm`, `members.py` and `patients` manage matching/organization; the app does not implement account authentication.
- **An archive is not an inferred clinical episode.** `medical_records` can organize multiple documents, while ambiguity and explicit ownership remain visible. The API supports creating/moving archives; the current Library tree is primarily a document view.
- **`record_abstracts` is not an AI-written summary.** `index_pending` deterministically collects evidence and revision state. Chat currently constructs its scoped catalog from document snapshots rather than treating an archive abstract as verified patient prose.
- **A chat proposal is not a save.** The backend supports gated metadata proposals and an explicit mutation endpoint (`C10`). Normal `ChatPanel` messages do not enable that tool or supply an Apply workflow.
- **The main viewer has editable saved text and a raw-data toggle.** Initial extraction is retained by storage/API, but is not a separate current viewer tab.
- **Decorative graphics do not capture reports.** `Workspace`, `Dropdown`, CSS and `GlassScene` handle layout/accessibility. Only decorative surfaces enter the WebGL capture (`U14`).

## Use this for a demonstration

1. Use a sample report without real patient information. Upload a photo directly to demonstrate the primary input.
2. Show the queued receipt, then the completed stages. Open the original and compare the extracted text.
3. If the sample has a suspected transcription error, correct it, save, and explicitly recheck. Explain why original and edited text are separate.
4. Browse by member and date. Show incomplete dates or unassigned names if the prepared sample includes them; do not manufacture certainty to fill the tree.
5. Ask a question whose answer can be checked against the report. Expand Sources and return to the original. Also show a question the available records cannot answer.

## Regenerate and verify the diagrams

`tools/render_architecture.py` is the diagram source. It writes SVGs to the existing diagram paths and checks that every block has a matching source comment. With Playwright and Chrome available, `--render` also updates PNG previews and checks text bounds, card separation and connector endpoints:

```powershell
.\.venv\Scripts\python.exe tools/render_architecture.py --render
```

These checks verify the diagrams' geometry and references. The application build and backend tests separately verify compilation and behavioral contracts; mocked tests are not real-provider medical-quality evidence.
