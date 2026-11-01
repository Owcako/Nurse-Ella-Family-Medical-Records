# Family Medical Records

Family Medical Records helps individuals and families find and understand their past medical reports before or during a doctor visit. Add a photo of a report, a PDF, or text; review what was extracted; then browse your history or ask a question in everyday language. You can return to the original document to check what it actually says.

The basic workflow is **add a report → review it → find it again when you need it**. Photos can be uploaded directly, without converting them to PDFs. The interface is available in English and Simplified Chinese.

To show tap locations in screen recordings, open `/?rec=true#records` (or put `?rec=true` before the current page hash). Each primary press shows a ring that expands and fades over one second throughout the app, including menus and dialogs. Remove the parameter or use `?rec=false` and reload to disable it. This works independently of Demo mode and does not start or detect screen recording. Reduced-motion settings use a stationary fading ring.

## Demo notice

We switched this medical-records demo from Gemini's free tier to **paid API Tier 1** because Google's unpaid-service terms allow submitted content to be used to improve its products. Under the [paid-service terms](https://ai.google.dev/gemini-api/terms#paid-services), prompts and responses are not used for product improvement, although limited safety logging can still occur.

Please **do not abuse or spam the demo, or upload real medical records, ID cards, or personal information**. Use synthetic sample files or your own fictional records. This is a shared demonstration, not a private medical-records vault. **Reset to demo**, available only in Demo mode at the bottom left of the Library, asks for confirmation before restoring the shared demo records and family members. Normal mode has no library reset button.

On opening the app, read the demo notice and check its acknowledgement before continuing. Uploaded files remain on the server until deleted or the shared library is reset. The app does not use tracking or analytics cookies; browser storage remembers language, layout, and browsing preferences.

## The three sections

### Demo and normal modes

Use the **Normal mode / Demo mode** switch in the header. Demo mode uses a red accent and loads the 13 prepared John and Mary Smith PDFs directly from the server. You do not need to find files on your device. Switching modes is local to each browser tab; the records remain shared. Switching back to normal mode keeps the records and restores manual uploads and the free-text chat composer.

The demo kit includes the two fictional member profiles and 20 question prompts from the John Smith test README. John's 10 reports load immediately with prepared extraction, filing, check results, and evidence indexes. They are labeled **Prepared demo result** and retain their original PDFs. Mary's 3 PDFs go through real AI extraction, checking, and filing. The question picker scopes chat to John's already available history; every answer and evidence lookup still runs through the normal live chat flow. No chat answers are scripted. Normal mode retains ordinary AI processing for every upload, including uploads of these same PDFs.

**Reset to demo**, in the Library's lower corner, asks for confirmation before replacing the shared library with 10 immediately ready reports, 3 live AI jobs, and the two member profiles. Merely enabling demo mode adds missing kit files without duplicating earlier kit imports or overwriting edits. After upgrading an existing all-live demo library, use Reset to demo once to install the prepared mix. The server bundles original PDFs and source-hash-bound processing fixtures in `backend/demo-kit/`; the manifest exposes question prompts without expected chat answers. Prepared fixtures were captured from completed, unedited processing of these fictional PDFs; their source text, clinical evidence quotes, check locations, profile relinking, and original bytes are covered by tests.

Open the root website address to start at **Records / 病历**. Phones have two bottom tabs: **Records / 病历** and **Chat**. On desktop, the record browser, report viewer and Chat remain visible side by side, with no bottom tabs. Click the nurse avatar or title to return to Records. The member filter carries into normal Chat.

Member management is a secondary **Manage members… / 管理成员…** action at the end of the Records member dropdown. It opens a dialog for adding, editing and removing profiles, without changing the current member filter. With no members, Records shows an **Add your first family member** prompt; uploading remains available before creating a profile.

Each page has a shareable hash (`#records`, `#chat`), and reports retain their `#/files/{id}` links. Switching pages writes browser history, so Back and Forward work. Refresh keeps the current URL/page; entering the root address starts at Records. Page switches preserve in-memory chat and editor drafts; replacing an edited report still requires Save/Discard/Stay. Refresh continues to warn about unsaved drafts and does not persist unsaved edits or conversation history. Old `#members` links return to Records.

| Section | What you do there |
| --- | --- |
| **Manage members…** | Add, edit, and remove family members in a secondary dialog. |
| **Records** | Add reports and browse saved records. |
| **Document viewer** | Read a report's saved text, inspect the original, and correct mistakes. |
| **Chat — Nurse Ella** | Ask about the saved history and open the reports supporting an answer. |

### Library: add and find reports

The Library is your starting point. It groups documents by **Member**, **Department**, or **Date**, and the member filter lets you focus on one person's records. **Needs attention** brings together documents with unresolved details, suspected text errors, or processing issues.

To add your first report:

1. Press **＋** and choose **Photo**, **PDF**, **Text file**, or **New text**. For New text, enter a title and the document text, then choose **Save and file**.
2. The selected files are uploaded and processing starts automatically. For New text, processing starts when you choose **Save and file**.
3. Watch the document's status. The original is stored first, then the app extracts text, checks for suspected errors, and files the document. **Filed** means that processing has finished; it does not mean the medical content has been validated.
4. Open the report to review its text and details in the middle section.

Use **Add member** to create a family member and include alternative names as printed in their reports. If a detected patient name does not match a member, the app asks whether it is a text mistake or a new family member. You can correct it, create the member, or leave it for later.

To find a report later, select a member if needed, choose a browsing tab, and expand the folders. Missing or unclear dates remain visible rather than being replaced with guessed dates. Sharing a department or category does not establish a clinical connection between reports.

Supported uploads are JPEG, PNG, WebP, PDF, and UTF-8 text files, up to **20 MiB per file**. PDFs can contain up to **50 pages**.

### Document viewer: check and correct the record

Opening a report shows its saved text and extracted details. Use **Go to raw data** to inspect the original photo, PDF, or text file, then **Saved text** to return. The original and initial extracted text remain preserved when you make corrections.

To review a suspected error:

1. Read the quoted passage under **Text to review** and compare it with the original. AI may flag an implausible age or a transcription mistake; a flag is a request to check, not proof that the report is wrong.
2. Choose **Edit / resolve details** to correct the saved text, member, date, department, or condition details. Leave information unknown when the source does not establish it.
3. Choose **Save**. Your changes are labeled as user supplied.
4. Choose **Recheck saved text** to check the revised text. Previous warnings can remain visible as stale until the new check finishes.

If processing fails, the stored original is still available. Use **Retry processing**, or enter the text yourself. Check the displayed status before assuming that extraction, checking, or filing succeeded.

**Delete record** removes that document's original, saved text, and search index. Removing a family member profile is a different action: its reports remain available for reassignment.

### Chat: ask about the history and follow the evidence

Nurse Ella lets you ask questions such as “What treatment was recorded for my previous knee pain?” or “What did the doctor say about follow-up at that visit?” It searches the saved records and explains what they document.

1. Check the selected family member before sending a question. The member selection is shared with the Library.
2. Ask in your own words. When a document is shown as chat context, its **saved text** is included if it belongs to the selected member scope. Unsaved edits are not sent.
3. Read the answer and any limitations, then follow a report link or expand **Sources** to inspect the supporting saved text. From the viewer, open the original to verify it.

You can ask follow-up questions in the same conversation. Conversations are kept separately for each member selection while the page is open; they are not a permanent chat archive.

An unsuccessful search does not mean an event never happened. Missing information, conflicting reports, and uncertainty should remain visible. The app helps you understand documented care; it does not diagnose, choose treatments, provide emergency triage, or replace a clinician. Proactive care reminders are future work.

## What happens to your records

Originals, saved text, family members, and the search index are stored in the backend library. By default, the database is `data/library.sqlite3` on the computer running the backend.

AI processing sends content to the configured primary service. This includes document content for extraction and checking; chat sends your question, conversation history, and the selected member's record metadata, with relevant document text supplied as needed. Uploading, rechecking, or sending a message starts that action without an additional processing confirmation.

The app currently has no account login or per-user access controls. Run it locally or on a trusted private network. Public hosting needs authentication and HTTPS. Keep `.env`, library databases, and AI diagnostic logs private; logs may contain report content.

## Run it on your computer

There are two running parts: the **React frontend** draws the interface in your browser, and the **Python/FastAPI backend** stores records and talks to the AI service. Start both to use the app locally. Docker is optional.

You need Node.js **22.12 or newer**, npm, and Python **3.11 or newer**. Run the following commands from the project folder.

### 1. Install the packages

Install the JavaScript packages used by the interface:

```sh
npm install
```

For an installation that follows `package-lock.json` exactly, use `npm ci` instead. You do not need to run both.

Create a Python virtual environment, which keeps this app's packages separate from other Python programs. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
```

On Linux or macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
```

`backend/requirements.lock` lists exact versions for a repeatable installation. `backend/requirements.txt` lists the direct dependencies and their allowed version ranges; use `-r backend/requirements.txt` instead when deliberately resolving a new set of versions. Keep `backend/catalogs/` with the backend source: its department catalog is required to start the app.

### 2. Choose the AI service

Copy `.env.example` to a file named `.env` in the project root, and fill in:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your-model-name
```

These settings select the API key, service address, and model. The service must support OpenAI-compatible Chat Completions, image inputs, and strict function calling. Provider charges depend on the service you choose.

The app uses this primary API key, address, and model for all AI requests. It does not switch to a backup provider when the primary is unavailable or out of quota. The example file also documents `LIBRARY_PATH` for changing where the database is stored. Without an AI key, originals can be stored, but AI processing and chat will not complete. Restart the backend after changing `.env`.

### 3. Start the backend and frontend

In one terminal, start the backend. On Windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

On Linux or macOS:

```sh
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Leave it running. In a second terminal, also in the project folder, start the frontend:

```sh
npm run dev
```

Open the address printed by Vite, normally `http://localhost:5173`. Start with a sample report, review the extracted text, and ask a question you can verify against the original.

During development, Vite forwards browser requests beginning with `/api` to the backend at `127.0.0.1:8000`. If that port is occupied, change both the backend command and the proxy target in `vite.config.ts` to the same available port. The browser should continue to use `/api` through the frontend address.

### 4. Build or check changes

```sh
npm run build
```

This checks TypeScript and writes the compiled frontend to `dist/`. It does not start or package the Python backend. A hosted installation must serve those files and forward `/api` to FastAPI, just as Vite does during development.

The PDF preview uses a `.mjs` JavaScript worker. The web server must serve `.mjs` files with `Content-Type: application/javascript`; `application/octet-stream` makes browsers reject the worker. For nginx installations whose MIME table omits `.mjs`, add this inside the app's server block, then validate with `nginx -t` and reload nginx:

```nginx
location ~ \.mjs$ {
    types { application/javascript mjs; }
    try_files $uri =404;
}
```

Run backend checks with the virtual environment's Python:

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q
```

On Linux or macOS, replace the Python path with `.venv/bin/python`.

## Understand the code

Follow the [layered code walkthrough](docs/code-walkthrough.md) for diagrams, file relationships, and the reasons behind the workflow safeguards.
