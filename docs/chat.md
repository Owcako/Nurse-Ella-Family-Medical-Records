# Chat implementation

Implemented against `Features.clarified.drawio`, especially pages 01, 02, 03 and 07. The clarified diagrams take precedence over the earlier deck.

## Experience

Desktop shows Browser, Viewer and Chat together. Phone has Chat / Browser navigation and the existing full-screen viewer. Replies use connected conversational paragraphs rather than record or diagnosis inventories. Broad questions get a brief description of documented care; detailed history and measurements appear when asked. The companion can also respond naturally to greetings and concerns without an unnecessary search. It does not offer suggestions, conclusions, health judgments, calculations or data analysis. A clinician's recorded assessment or instruction is attributed to its record, never adopted as the bot's own judgment or advice.

The user-facing `message` is separate from the internal claims/evidence ledger. Final review checks its patient facts against the cited current text. Material limitations remain visible in conversational language, with sources available on demand.

Evidence is checked internally. A single collapsed Sources section holds supporting quotes, unique report links, provenance, warnings and processing details. The model normally chooses no prominent references; it can invite the user to open up to two cited reports when the user asks to see them or a specific discrepancy or documented instruction merits attention. Visible references are validated against cited, retrieved evidence. The viewer exposes the original, initial extraction, corrections and warnings. Back preserves the prior tab and library filter.

The member filter is shared between Browser and Chat. Every turn automatically supplies the complete member-scoped metadata catalog and conversation history, including prior source references. Switching members restores that member's conversation without mixing histories. All-members scope exposes the entire catalog; answers about multiple people must keep each person's facts in separate named claims. Conversation history exists in page memory; reload clears it, while archived reports remain in SQLite.

Chat contains a member selector, conversation and message composer with Send. Add photos, PDFs or text through the existing Browser importer; saved records become available automatically. The current viewer is an optional focus hint, never a restriction on retrieval. There are no attachment, context-selection or metadata-action controls in Chat. A failed answer preserves the draft. The revised first-submission disclosure covers the complete scoped metadata and conversation history, plus relevant saved text read by the AI.

Use the existing Viewer to correct text or classifications. The legacy revision-checked metadata proposal API remains available for compatibility but is not exposed by the ordinary chat UI. Chat has no text-edit or delete tool.

## Retrieval and trust boundaries

While waiting, a high-contrast card shows elapsed seconds, gently pulsing stage text and animated dots. `POST /api/chat` with `Accept: application/x-ndjson` streams actual backend stage receipts (preparing, searching, reading, answering, reviewing) and then a single fully reviewed result, or an explicit error. Original transcription has a separate reading-original status. No unreviewed answer text is streamed. Heartbeats keep quiet model waits connected, and proxy buffering is disabled. Existing JSON clients retain their response contract. Interrupted streams preserve the draft without automatically repeating an AI call; reduced-motion preferences disable the visual animations. Elapsed time is local waiting time, not an estimated completion percentage.

`backend/chat.py` reuses `processing.client()` and `processing.model()`: the OpenAI Python SDK reads the existing `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `OPENAI_MODEL` loaded from `.env` by the backend. No credentials enter frontend code. A primary HTTP 429 uses the optional `BACKUP_API_KEY`, `BACKUP_BASE_URL` and `BACKUP_MODEL` together. All three must be present; credentials and models are never mixed. Other HTTP errors do not trigger quota fallback.

Fallback restarts the entire read-only AI operation, including a chat's retrieval and final evidence review, with fresh provider-specific tool history. It never repeats an archive save or commits a metadata proposal. A process-wide primary cooldown lasts at least 60 seconds, extended by `Retry-After`, before new operations probe primary again. Backup errors produce a visible failure without cycling between providers. The disclosure lists both services and answer receipts identify the service used. Extraction, checking, filing and chat share the routing. For the configured DeepSeek endpoint, forced tool calls use its documented [non-thinking mode](https://api-docs.deepseek.com/api/create-chat-completion/) while retaining the configured model.

Each turn starts with the complete server-read metadata index, without a first-page cap. Entries contain classifications, provenance, clinical terms, processing status, warnings and lab-report hints, without full document text. The model first inspects metadata, then explicitly chooses record IDs to retrieve their current saved text; no companion reports are silently appended. It can request a fresh original transcription when needed. Prompts require all relevant dates for broad comparisons and all plausible records before absence claims. The tools enforce member scope, a 300,000-character context/read budget and at most 18 model steps. Oversized context fails visibly rather than silently clipping the catalog or conversation.

The model returns conversational paragraphs with internal citations, useful explanations, material limitations and optional prominent references using strict function schemas validated by Pydantic. Patient claims require retrieved file IDs and quotes that occur in the fetched saved text or explicitly read original transcription. Invalid IDs/quotes and years absent from cited reports return tool errors for correction. A mandatory final model review checks dates, units, direct comparisons and missing-evidence limits before delivery. Deletion or revision changes during a request prevent a stale answer. Source links use validated identities; old links resolve through the existing unavailable-file state. Later source changes remain visible; other source and retrieval details stay inside Sources. Markdown uses `react-markdown` with a restricted element list; model output cannot create links or load external images.

The prompt distinguishes documented facts from general explanations, temporary/inpatient medicines from the latest documented list, random from fasting glucose, narrative resolution from imaging confirmation, and absence of documentation from absence of an event. It rejects treatment/dose decisions and instructions embedded in reports. Quote validation proves that quoted wording exists; it cannot independently prove that every model paraphrase is clinically correct, so live acceptance remains necessary.

## Running and verification

Run the backend and frontend from the repository root:

```powershell
.venv/Scripts/python.exe -m uvicorn backend.api:app --reload
npm run dev
```

Routine checks use isolated data and mocked provider/network responses:

```powershell
.venv/Scripts/python.exe -m pytest backend -q
npm run lint
npm run build
npx playwright test --reporter=line
```

Playwright is configured for installed Microsoft Edge (`channel: 'msedge'`), at desktop and phone sizes. The live test is skipped unless explicitly enabled. UI checks cover disclosure acceptance/cancellation, evidence → saved text → original → Back, complete follow-up history, separate member conversations, shared member scope, Chinese controls, failure recovery and the simplified composer.

To repeat real-provider acceptance against the fictional PDFs, first import all ten `test/*.pdf` reports into the app, then start the isolated fixture server:

```powershell
.venv/Scripts/python.exe -m uvicorn tools.chat_acceptance:app --port 8011
```

It copies only originals whose SHA-256 matches the fictional PDF fixtures and their existing saved extraction. It creates independent all-files, omitted-discharge, omitted-follow-up, duplicate-document and shuffled-order libraries beneath `data/chat-acceptance/`. Production reports are never deleted or modified by this harness.

In another terminal:

```powershell
$env:CHAT_LIVE = '1'
npx playwright test tests/chat.live.spec.ts --project=desktop --reporter=line
Remove-Item Env:CHAT_LIVE
```

The opt-in suite asks all 22 Level 1–4 questions, including both omitted-document cases, plus duplicate-document, shuffled-order and two-page-content checks (25 scenarios). It writes each response to a unique JSON report in `data/chat-acceptance/` and attaches the completed report. It paces requests and retries temporary 429/503 failures. Regex checks are a factual smoke check, not a replacement for reviewing explanations and sources against `Chat test questions.md`. Do not treat a provider outage as a passing medical answer. Results from the implementation session are recorded in `docs/chat-acceptance.md`.

For targeted reruns, set `CHAT_LIVE_CASES` to comma-separated IDs such as `3.1,4.3,4.4,4.5`. To run the separate real image pipeline and responsive evidence-viewer check:

```powershell
$env:CHAT_PHOTO_LIVE = '1'
npx playwright test tests/chat.live.spec.ts --project=desktop --grep 'image input' --reporter=line
Remove-Item Env:CHAT_PHOTO_LIVE
```

That test renders one prepared lab PDF page into a PNG and uploads it through Browser in Edge. Chat automatically reads the new record without attachment or context controls. It exercises real OCR, checking, filing, answering, evidence navigation and the original-image viewer. It does not simulate a physical camera capture.
