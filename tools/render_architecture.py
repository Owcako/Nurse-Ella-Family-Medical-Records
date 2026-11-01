"""Generate the layered code walkthrough; optionally render and inspect every SVG.

Run from the repository root: python tools/render_architecture.py --render
SVGs use the standard library. PNG export/visual checks require Playwright and
an installed Chrome. Application services and API credentials are not needed.
"""

import argparse
import os
import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
VIEWS = []


class Diagram:
    def __init__(self, path, level, title, subtitle, width=1440):
        self.path = ROOT / path
        self.width = width
        self.nodes = []
        self.bounds = {}
        self.parts = []
        self.level, self.title, self.subtitle = level, title, subtitle
        VIEWS.append(self)

    def text(self, x, y, value, size=16, color='#233646', weight='400'):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(value)}</text>')

    def card(self, node, x, y, width, title, source, lines, guard=False):
        titles = textwrap.wrap(title, max(18, int((width - 44) / 11)))
        sources = textwrap.wrap(source, max(22, int((width - 44) / 7.8)), break_long_words=False)
        body = [line for value in lines for line in textwrap.wrap(value, max(24, int((width - 44) / 8.7)), break_long_words=False)]
        height = 48 + len(titles) * 27 + len(sources) * 19 + len(body) * 24 + 18
        self.bounds[node] = (x, y, width, height)
        self.nodes.append(node)
        fill, stroke, accent = ('#fff6e9', '#dcbb83', '#98621e') if guard else ('#ffffff', '#bfccd8', '#245f81')
        self.parts.append(f'<g id="{node}" data-node="{node}" data-x="{x}" data-y="{y}" data-width="{width}" data-height="{height}">')
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="14" fill="{fill}" stroke="{stroke}"/>')
        self.text(x + 22, y + 27, node, 13, accent, '700')
        cursor = y + 57
        for line in titles:
            self.text(x + 22, cursor, line, 21, weight='600')
            cursor += 27
        for line in sources:
            self.text(x + 22, cursor, line, 13, '#5c6d7c')
            cursor += 19
        cursor += 8
        for line in body:
            self.text(x + 22, cursor, line)
            cursor += 24
        self.parts.append('</g>')
        return height

    def edge(self, points, guard=False, dashed=False):
        color = '#98621e' if guard else '#245f81'
        dash = ' stroke-dasharray="6 5"' if dashed else ''
        coords = ' '.join(f'{x},{y}' for x, y in points)
        self.parts.append(f'<polyline data-edge="true" points="{coords}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#arrow)"{dash}/>')

    def write(self, height):
        header = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{height}" viewBox="0 0 {self.width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(self.title)}</title><desc id="desc">{escape(self.subtitle)} Blue cards describe the main flow; amber cards explain safeguards. Source comments use the same node IDs.</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="context-stroke"/></marker></defs>
<style>text {{font-family:'Segoe UI','Microsoft JhengHei',Arial,sans-serif}} text,polyline {{pointer-events:none}}</style>
<rect width="100%" height="100%" fill="#f4f7fa"/>
<text x="48" y="38" font-family="Segoe UI,Arial" font-size="13" font-weight="700" fill="#245f81">FAMILY MEDICAL RECORDS · VIEW {self.level}</text>
<text x="48" y="80" font-family="Segoe UI,Arial" font-size="30" font-weight="600" fill="#233646">{escape(self.title)}</text>
<text x="48" y="111" font-family="Segoe UI,Arial" font-size="16" fill="#5c6d7c">{escape(self.subtitle)}</text>
<text x="48" y="143" font-family="Segoe UI,Arial" font-size="13" fill="#5c6d7c">Read top to bottom. Solid blue = sequence/call; dashed amber = related safeguard, not an extra processing stage.</text>'''
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(header + '\n' + '\n'.join(self.parts) + '\n</svg>\n', encoding='utf-8')


def flow(path, level, title, subtitle, rows, loops=()):
    diagram = Diagram(path, level, title, subtitle)
    y = 180
    previous = None
    for main, side in rows:
        node, heading, source, *lines = main
        height = diagram.card(node, 48, y, 740, heading, source, lines)
        if previous is not None:
            diagram.edge([(418, previous), (418, y)])
        if side:
            guard_id, guard_title, guard_source, *reasons = side
            side_height = diagram.card(guard_id, 876, y, 516, guard_title, guard_source, reasons, guard=True)
            diagram.edge([(788, y + 65), (876, y + 65)], guard=True, dashed=True)
        else:
            side_height = 0
        previous = y + height
        y += max(height, side_height) + 48
    for index, (source, target, label, guard) in enumerate(loops):
        sx, sy, sw, sh = diagram.bounds[source]
        tx, ty, tw, _ = diagram.bounds[target]
        lane = 812 + index * 23
        target_y = ty + 120 + index * 22
        diagram.edge([(sx + sw, sy + sh / 2), (lane, sy + sh / 2), (lane, target_y), (tx + tw, target_y)], guard=guard, dashed=guard)
        for line_index, line in enumerate(textwrap.wrap(label, 47)):
            diagram.text(900, sy + 80 + line_index * 23, line, 15, '#98621e' if guard else '#245f81')
    diagram.text(48, y, 'Zoom index: docs/code-walkthrough.md · Search a node ID such as #B6 in the source.', 14, '#5c6d7c')
    diagram.write(y + 35)


def main_flow():
    flow('AGENTS.svg', '00', 'From a report to an answer you can verify',
         'A demonstration follows this route. Later views open each step and show the responsible files.', [
        (('F1', 'Add the report you already have', 'ImportPanel.tsx → POST /api/imports or /api/texts',
          'Choose a photo, PDF, UTF-8 file, or write a text draft. Upload/save starts processing without another confirmation.'),
         ('F1G', 'Why store before asking AI?', 'api.py → Library.create', 'A slow or unavailable AI service must not lose the original. A queued receipt is not a completed extraction.')),
        (('F2', 'Extract, check, and file', 'filing.py → processing.py → Library.change',
          'Read text, preserve its first extraction, flag suspected text errors, and propose categories with source quotes. See import-pipeline.svg.'),
         ('F2G', 'Why separate the outcomes?', 'document_processing + document_metadata', 'A failed text check can coexist with filed metadata. Missing facts remain unknown; the app does not invent them.')),
        (('F3', 'Review the report and correct mistakes', 'Viewer.tsx → api.manual / api.recheck',
          'Compare saved text with the original. Save your corrections, then explicitly recheck the saved version. See ui-flow.svg.'),
         ('F3G', 'Why keep the original?', 'document_sources + document_texts', 'Human corrections must not overwrite the original bytes or first extraction. Edits make old checks stale.')),
        (('F4', 'Find relevant records', 'LibraryBrowser.tsx → browsing.ts + dates.ts',
          'Filter a family member and expand Member, Department, or Date groups. Browse without an AI call. See browsing-flow.svg.'),
         ('F4G', 'Why display unresolved groups?', 'memberIdentity / fileBranches', 'Ambiguous people and incomplete dates must not silently become confirmed ownership or a fabricated chronology.')),
        (('F5', 'Ask a question in everyday language', 'ChatPanel.tsx → api.ask → chat.py',
          'The backend supplies a scoped catalog; the model reads relevant saved reports using constrained tools. See chat-flow.svg.'),
         ('F5G', 'Why retrieve each time?', 'chat.scope_files + revision checks', 'Conversation history is context, not fresh evidence. New answers must use the selected member and current saved records.')),
        (('F6', 'Open the evidence behind the answer', 'ChatPanel Sources → App.select → Viewer',
          'Read an answer and its limits, follow its source link, then compare the original report during your visit.'),
         ('F6G', 'What the demonstration does not prove', 'chat claim validation + visible limitations', 'Exact quotes improve traceability, not medical truth. Missing records do not prove an event never happened.')),
    ])
    flow('AGENTS.zh-TW.svg', '00 · 繁體中文', '從一份報告，到可以核對的回答',
         '依序示範主要操作；英文圖使用相同節點 ID，可以在程式註解中搜尋。', [
        (('F1', '加入現有報告', 'ImportPanel.tsx → backend/api.py', '直接加入照片、PDF 或文字。選擇檔案或儲存草稿後即開始處理，不再要求額外確認。'), None),
        (('F2', '擷取、檢查與歸檔', 'filing.py → processing.py → storage.py', '先保存原件，再擷取文字、標示疑點，並以原文引句支持分類。失敗狀態與不確定資訊會保留。'), None),
        (('F3', '核對原件並修正', 'Viewer.tsx → manual / recheck', '人工修改只改目前文字；原件與首次擷取保留。儲存後再要求重新檢查，避免將舊結果當作新結果。'), None),
        (('F4', '依成員、科別或日期找報告', 'LibraryBrowser.tsx → browsing.ts / dates.ts', '這是讀取既有資料，不需要呼叫 AI。缺少月份或不明成員維持可見，不替使用者猜測。'), None),
        (('F5', '用日常語言詢問紀錄', 'ChatPanel.tsx → backend/chat.py', '先提供選定成員的索引，再讓模型讀取相關文字。每次問答都重新檢索，並驗證引句與資料版本。'), None),
        (('F6', '回到來源查證', 'Sources → App.select → Viewer', '從回答開啟來源與原件。引句能追溯來源，但不代表醫療結論一定正確；找不到也不代表從未發生。'), None),
    ])


def architecture():
    d = Diagram('implementation-architecture.svg', '01', 'Which component owns each responsibility?',
                'This is a dependency map. The workflow and chat coordinate storage; the AI client cannot save records itself.')
    d.card('O1', 48, 180, 340, 'Workspace and user actions', 'src/App.tsx + Workspace.tsx',
           ['Own member selection, snapshots, open document, dirty-state guards and panel layout.',
            'Children: LibraryBrowser, ImportPanel, Viewer, ChatPanel.'])
    d.card('O2', 48, 650, 340, 'Browser HTTP client', 'src/import/api.ts',
           ['Use relative /api URLs. Decode confirmed receipts or display an error; keep drafts on failure.'])
    d.card('O3', 448, 180, 620, 'FastAPI boundary', 'backend/api.py + models.py',
           ['Validate requests; save uploads before scheduling one worker.',
            'Serve reads, explicit human mutations, rechecks, and synchronous chat calls.'])
    d.card('O4', 448, 490, 280, 'Filing workflow', 'backend/filing.py',
           ['Claim → extract → check → classify → validate → commit.', 'Only guarded writes can establish filed status.'])
    d.card('O9', 768, 490, 300, 'Evidence conversation', 'backend/chat.py',
           ['Scope → catalog → read reports → validate claims → review → answer.', 'Chat reads evidence; normal questions cannot mutate it.'])
    d.card('O6', 448, 900, 620, 'Authoritative library', 'backend/storage.py + schema.sql',
           ['SQLite stores original bytes, text revisions, members, archives, metadata and indexes.', 'Transactions, source immutability and durable index jobs protect saved work.'])
    d.card('O5', 448, 1250, 620, 'Document and AI operations', 'backend/processing.py + debug_log.py',
           ['Decode text, render PDF pages, request extraction/check/classification, validate tool output.', 'Functions return results or errors; they do not own library transactions.'])
    d.card('O8', 1128, 1250, 264, 'Primary AI service', 'processing.client / model',
           ['Server-only OPENAI settings.', 'One configured primary provider; no quota fallback.'], guard=True)
    d.card('O7', 448, 1595, 620, 'Shared boundary contracts', 'models.py · chat.py contracts · src/import/types.ts',
           ['Strict runtime validation for HTTP and tool inputs; TypeScript shapes for UI data.', 'These constrain every boundary above; they do not make unsupported medical claims true.'])
    bottom = lambda node: d.bounds[node][1] + d.bounds[node][3]
    d.edge([(218, bottom('O1')), (218, 650)])
    d.edge([(388, 730), (418, 730), (418, 275), (448, 275)])
    d.edge([(720, bottom('O3')), (720, 445), (588, 445), (588, 490)])
    d.edge([(800, bottom('O3')), (800, 445), (918, 445), (918, 490)])
    d.edge([(588, bottom('O4')), (588, 900)])
    d.edge([(918, bottom('O9')), (918, 900)])
    d.edge([(1068, 275), (1100, 275), (1100, 1000), (1068, 1000)])
    d.edge([(448, 650), (434, 650), (434, 1360), (448, 1360)])
    d.edge([(1068, 650), (1084, 650), (1084, 1218), (980, 1218), (980, 1250)])
    d.edge([(1068, 1360), (1128, 1360)])
    d.text(48, 1890, 'Open the numbered detail views in docs/code-walkthrough.md. Browser presentation is separate from persistent medical evidence.', 15, '#5c6d7c')
    d.write(1930)


def import_flow():
    flow('backend/import-pipeline.svg', '03', 'How one upload becomes a filed document',
         'Start after source bytes are committed. The right column explains failure paths and concurrency guards.', [
        (('B1', 'Claim one pending document', 'api.schedule → FilingWorkflow.run / claim', 'One executor processes filings serially. A fresh attempt token identifies this particular run.'),
         ('B10', 'Why an attempt token?', 'FilingWorkflow.run.update → Library.change', 'A human save clears the token; deletion removes the row. Every stage checks it before writing, so an old worker cannot overwrite or resurrect a document.')),
        (('B2', 'Decode text or transcribe images', 'processing.extract', 'UTF-8 text is read locally. Validate photo contents; reject encrypted/oversized PDFs; render PDF pages for primary-provider image transcription.'),
         ('B8', 'Why keep a failed-stage result?', 'FilingWorkflow.run exception handlers', 'Record which stage failed. Preserve source and any committed text, then expose Retry instead of pretending that extraction or filing finished.')),
        (('B3', 'Save initial and current text', 'run.update → Library._write_document', 'Store the first extraction separately from editable text. Retrying with existing text skips another transcription.'),
         ('B12', 'Why recover after a restart?', 'api.lifespan → Library.recover', 'The queue lives in one process. Interrupted pending/processing rows become failed with explicit Retry; the app does not claim they are still running.')),
        (('B4', 'Check suspected text errors', 'processing.check → report_concerns', 'A strict tool returns quoted passages and reasons, never replacement text. locate_quote records exact character offsets.'),
         ('B11', 'Why can filing continue?', 'run checking exception handler', 'Checking and filing answer different questions. A failed check remains visible while independently valid classification can still be saved.')),
        (('B5', 'Propose categories and clinical index', 'processing.classify → save_current_content', 'Ask for member/date/department/condition plus documented symptoms, history, diagnoses and treatments. Initial extraction is used separately for lab-report type.'), None),
        (('B6', 'Verify every proposed fact', 'validate_filing + source_evidence + locate_quote', 'Quotes must occur in saved text and values must occur in those quotes. Distinct people/dates stay ambiguous; exact aliases can identify a family profile.'), None),
        (('B7', 'Commit the filed result', 'run.update → Library.change → index_pending', 'Commit metadata and document index with filed status. Resolve catalog department codes and deterministically refresh the archive evidence index.'),
         ('B9', 'Why Retry uses the same ID', 'api.retry → FilingWorkflow.retry', 'Only a failed row returns to pending. Reusing its identity preserves evidence links and avoids duplicate documents; available text is retained.')),
    ])


def ui_flow():
    flow('src/import/ui-flow.svg', '02', 'Browser actions, saved receipts, and safe editing',
         'The UI keeps drafts locally. Backend receipts, rather than button clicks, establish what is saved.', [
        (('U16', 'Acknowledge the demo-only notice', 'DemoNotice.tsx → App.demoAcknowledged', 'At each page opening, explain synthetic data, paid Gemini processing, server retention and medical limitations. Require a checked acknowledgement before Continue; keep controls fixed while only the content area scrolls.'), None),
        (('U1', 'Choose existing files', 'ImportPanel.pick + browser file input', 'Photo, PDF and text options set accepted extensions. Each selected file has its own operation key and upload request.'),
         ('U4', 'Why stable upload keys?', 'ImportPanel.submit → Library.create', 'A response may be lost after saving. Retrying the same operation key retrieves the existing row instead of storing another copy.')),
        (('U2', 'Or compose a text draft', 'ImportPanel new-draft state', 'Title and text stay in browser state until Save and file. Failed submission retains the draft.'), None),
        (('U3', 'Submit immediately and receive a saved identity', 'ImportPanel.submit → /imports or /texts', 'There is no processing-confirmation gate. A successful upload receipt opens the saved document while background stages continue.'),
         ('U5', 'Why poll with a mutation counter?', 'App.refresh + refresh timer', 'Refresh roughly every 1.8 seconds. Ignore an older read that began before a local save/delete, preventing stale snapshots from undoing the visible result.')),
        (('U6', 'Browse and select the same document', 'App.select + LibraryBrowser + browsing.ts', 'Keep a stable document ID in the hash, preserve member filters, and restore focus/scroll when returning to the tree.'),
         ('U13', 'Why review an unmatched name?', 'MemberReview → MemberForm / Viewer', 'A printed patient name is not an account. Ask whether to correct it, create a member with aliases, or defer; do not merge people by similarity.')),
        (('U9', 'Inspect source beside saved text', 'Viewer + PdfSource', 'Images support zoom; PDFs support pages, selectable text and resize-aware rendering. Raw-data links remain available if preview fails.'),
         ('U14', 'Why isolate presentation?', 'Workspace + GlassScene + Dropdown', 'Persist panel sizes, support keyboard controls and reduced motion, and keep report/chat text out of the decorative WebGL capture.')),
        (('U7', 'Edit and save explicit corrections', 'Viewer.beginEdit / save → api.manual', 'Send the revision originally opened for editing. Save current text and details, preserve initial/original data, and mark changed-text checks stale.'),
         ('U11', 'Why guard dirty drafts?', 'Viewer.beforeAction / leave + App navigation guards', 'Changing documents, checking, browser navigation and reload can discard a draft. Resolve Save/Discard/Stay and retain the draft if saving fails.')),
        (('U12', 'Recheck the saved text', 'Viewer.recheck → api.recheck', 'Save edits first. Run checking outside the write transaction; compare the revision again before attaching results.'),
         ('U8', 'Why expose Retry separately?', 'Viewer.retry → /files/{id}/retry', 'A processing failure is different from a suspected text error. Retry resumes the same stored document instead of creating a new upload.')),
        (('U10', 'Delete only after explicit confirmation', 'Viewer.remove → api.delete → Library.delete', 'Delete this document and its derivatives. Return to the tree only after the server confirms; archive siblings remain intact.'), None),
        (('U15', 'Reset the shared demo library', 'Library footer → App.resetLibrary → /library/reset', 'Ask for confirmation, then atomically remove all reports, original bytes, saved text, indexes and members. Clear local chat/drafts only after success; canceling or failure retains them. Stop old uploads and ignore late callbacks.'), None),
    ])


def storage_flow():
    flow('backend/library-storage.svg', '04', 'How saved evidence stays consistent',
         'Each mutation is a transaction. Indexes are rebuildable derivatives of stored reports, not another source of truth.', [
        (('S1', 'Open and initialize the library', 'Library.__init__ / connect / _initialize', 'Enable foreign keys, apply schema/catalogs, and migrate legacy records inside a transaction. Reject newer schema versions.'),
         ('S6', 'Why backup and recover?', '_initialize + Library.recover', 'Migration preserves and verifies source/text before dropping legacy tables. Restart recovery invalidates interrupted attempts but retains all available evidence.')),
        (('S2', 'Recognize an upload retry', 'Library.create', 'Hash source/media/origin/title and look up its unique operation key. Identical replay returns its existing document.'),
         ('S3', 'Why an atomic first save?', '_new_record + _insert_document', 'Archive ownership, source BLOB, pending processing state and operation identity commit together. Reject reuse of a key with different content.')),
        (('S4', 'Reconstruct a public document', '_read_document / get / source / list', 'Join normalized tables into the /api/files shape. Source reads return preserved bytes without rewriting temporary files.'), None),
        (('S5', 'Apply guarded document changes', 'Library.change → _write_document', 'BEGIN IMMEDIATE serializes writers. Run the caller revision/attempt guard before committing; track document and text revisions separately.'),
         ('S11', 'Why a dedicated move operation?', 'move_document', 'Generic changes cannot alter document ownership. Explicit moves check revision, processing status and patient compatibility, then invalidate both archives.')),
        (('S9', 'Recompute archive labels', '_touch_record / _record_summary', 'Aggregate only supported patient/date/department/condition facts. Preserve missing, partial, ambiguous and conflicting states.'),
         ('S8', 'Why exact member aliases?', 'save_profile / _link_member / _relink_members', 'Reject overlapping names/aliases. Relink confirmed names when profiles change; removing a profile detaches reports rather than deleting evidence.')),
        (('S10', 'Refresh the evidence index', 'index_pending + index_jobs', 'A durable job targets an archive revision. Build deterministic record_abstracts from committed documents; expose partial or failed indexing.'), None),
        (('S7', 'Remove one selected document', 'Library.delete / _remove_or_touch', 'Foreign-key cascades remove its source/text/state/index. Recompute a remaining archive, or remove an archive that has no documents.'), None),
        (('S12', 'Reset all shared demo data atomically', 'Library.reset → DELETE medical_records / patients', 'One transaction cascades every archive/document derivative, then removes profiles. Keep the controlled department catalog. A failed reset rolls back; queued workers find deleted identities and stop.'), None),
    ])


def database_view():
    schema_cards = [
        ('D1', 'Family identity', 'patients', ['One managed family member can own many medical_records. Names and aliases help match documented patient names; these are not login accounts.']),
        ('D2', 'Organizational archive', 'medical_records + record_departments / record_diseases', ['One archive owns many documents. A patient link may be absent; labels keep their provenance and uncertainty. Department/condition link tables provide lookups.']),
        ('D3', 'Stable document identity', 'documents', ['Every document references one archive. Unique operation keys protect retries; fingerprints detect conflicting content; revisions guard edits.']),
        ('D9', 'Archive evidence summary', 'record_abstracts', ['One deterministic evidence index per archive, at based_on_revision. Despite its name, this is not an AI-written visit narrative.']),
        ('D10', 'Durable invalidation', 'index_jobs', ['One target/indexed revision and pending/failed/current job per archive. Interrupted rebuilds remain visible and retryable.']),
        ('D11', 'Controlled department catalog', 'departments + backend/catalogs/departments.json', ['record_departments links to registered department codes. Exact normalized aliases resolve labels; unsupported text cannot invent a code.']),
    ]
    children = [
        ('D4', 'Immutable original', 'document_sources', ['SHA-256 plus original BLOB; a database trigger rejects overwriting the preserved source.']),
        ('D5', 'Initial and current text', 'document_texts', ['First extraction is write-once. Current text is editable; text_revision changes only when that text changes.']),
        ('D6', 'Independent processing outcomes', 'document_processing', ['Attempt, stage, extraction/check states, concerns, checked text revision and errors can differ.']),
        ('D7', 'Supported classifications', 'document_metadata', ['Values, candidates, source quotes, provenance and catalog version. Ambiguity is stored data.']),
        ('D8', 'Document retrieval material', 'document_indexes', ['Clinical terms/classifications refer to a saved text revision. Human edits drop stale AI terms.']),
    ]
    d = Diagram('backend/database-schema.svg', '05', 'Data ownership and derived evidence',
                'Read the relationship arrows, not a clinical timeline. Each document owns its five independent 1:1 components.')
    y = 180
    for node, title, source, lines in schema_cards:
        height = d.card(node, 48, y, 650, title, source, lines, guard=node in ('D10', 'D11'))
        y += height + 65
    right_y = 180
    for node, title, source, lines in children:
        height = d.card(node, 900, right_y, 492, title, source, lines, guard=node in ('D4', 'D6'))
        right_y += height + 55
    for parent, child in [('D1', 'D2'), ('D2', 'D3')]:
        px, py, pw, ph = d.bounds[parent]
        cx, cy, cw, _ = d.bounds[child]
        d.edge([(px + pw/2, py + ph), (cx + cw/2, cy)])
        d.text(px + pw/2 + 14, py + ph + 38, '1 → many', 14, '#245f81')
    dx, dy, dw, dh = d.bounds['D3']
    for node, *_ in children:
        cx, cy, _, ch = d.bounds[node]
        d.edge([(dx + dw, dy + dh/2), (812, dy + dh/2), (812, cy + ch/2), (cx, cy + ch/2)])
    d.text(900, 164, 'EACH DOCUMENT → ONE ROW IN EACH TABLE', 13, '#245f81', '700')
    ax, ay, _, ah = d.bounds['D2']
    for child in ('D9', 'D10'):
        cx, cy, _, ch = d.bounds[child]
        d.edge([(ax, ay + ah/2), (24, ay + ah/2), (24, cy + ch/2), (cx, cy + ch/2)])
    d.text(48, y, 'Source and initial-text immutability are database constraints. Cascades follow ownership; indexes can be rebuilt from evidence.', 14, '#5c6d7c')
    d.write(max(y, right_y) + 40)


def chat_flow():
    flow('backend/chat-flow.svg', '07', 'How Nurse Ella answers from current reports',
         'The main UI sends read-only questions. Tool constraints and source checks surround the model; they cannot guarantee medical truth.', [
        (('C1', 'Send the question and conversation context', 'ChatPanel.send → /api/chat → Question', 'Send message, member filter, full history, language and optional viewed document ID. Retain an unsent draft on failure.'),
         ('C11', 'Why bounded errors instead of a guessed answer?', 'chat context / tool loop + processing.service_error', 'Reject oversized context instead of silently truncating it. Limit tool steps/reads; surface rate limits and provider failures while saved records remain unchanged.')),
        (('C2', 'Resolve the selected member scope', 'scope_files + linked_profile', 'Use confirmed member links and exact aliases. Assign unresolved documents separate identities so claims cannot mix them with a named person.'), None),
        (('C3', 'Supply the complete scoped catalog', 'chat.read_index(0)', 'The backend adds metadata, document IDs, statuses and clinical terms before the first model call. Upload timestamps are not medical dates.'),
         ('C4', 'Why attach only server-saved viewer text?', 'chat context / selected viewer document', 'An open report is a focus hint, not a restriction on search. Include it only inside member scope; never accept browser drafts as saved patient evidence.')),
        (('C5', 'Request a constrained next tool', 'chat tool loop + CONTRACTS + INSTRUCTIONS', 'Use the primary provider and strict schemas. Read documents, optionally re-transcribe an original, or propose a finished answer; report text is untrusted data.'),
         ('C10', 'Why proposals are not saves?', 'propose_metadata + metadata_save', 'Backend-only metadata proposal support is gated by metadata_action. Normal UI questions do not enable it; a separate explicit, revision-checked request is required to apply changes.')),
        (('C6', 'Read current text by known IDs', 'read_documents / read_original → Library.get', 'Only scoped catalog IDs can be read. Check revision, enforce character budget, and acknowledge every batched read call. Original re-transcription is request-local, not a stored correction.'), None),
        (('C7', 'Validate the proposed evidence', 'finish_answer branch + locate_quote', 'Each patient claim cites retrieved reports, a quote that occurs in their text, and supported years. Check member identities, visible references and source revisions.'), None),
        (('C8', 'Review evidence, then finalize', 'reviewed flag → second finish_answer', 'For sourced answers, send the validated draft through one final evidence review. Add missing-documentation limits where needed; return sources and provenance only after validation.'), None),
        (('C9', 'Render the answer and evidence links', 'ChatPanel + AnswerText → App.select → Viewer', 'Display plain-language answers, explanations and limitations. Allow a small Markdown subset; open supporting saved text and original data. Mark sources changed since the answer.'), None),
    ], loops=[
        ('C6', 'C5', 'Tool result → request the next action. Read more reports as needed.', False),
        ('C7', 'C5', 'Invalid arguments or unsupported quote → send a tool error so the model can correct it within the same bounded loop.', True),
        ('C8', 'C5', 'First valid sourced draft → request final evidence review; only finish_answer is offered. Valid reviewed output continues to C9.', False),
    ])


def browsing_flow():
    flow('src/library/browsing-flow.svg', '06', 'Browse saved records without asking AI',
         'A tree is a view of existing documents. It does not create clinical relationships or new patient facts.', [
        (('R1', 'Apply the shared family-member filter', 'LibraryBrowser → memberIdentity → profiles', 'Only confirmed names that identify one profile enter that member scope. Library and Chat share this selection in App.'),
         ('R5', 'Why review unfamiliar names?', 'needsMemberReview / memberReviewKey / MemberReview', 'A documented name may be correct but not managed yet. Offer correction, a new profile, or defer; key deferral by document and detected name so a changed name is reviewed again.')),
        (('R2', 'Optionally show Needs attention', 'needsAttention / unresolvedFields', 'Include missing required details, incomplete stages, failed extraction/checking, concerns and noncurrent archive indexes.'), None),
        (('R3', 'Group documented categories', 'groupFiles → FileGroup', 'Group known values as confirmed. Missing/ambiguous values stay unknown; candidate labels can appear tentatively. Deduplicate each group by document ID.'), None),
        (('R4', 'Build year and month branches', 'fileBranches → dates.parseDate', 'Sort recognized dates chronologically, preserve year-only precision in Month not recorded, and retain unparseable dates in a review group.'),
         ('R6', 'Why preserve date precision?', 'dates.ts + DateFields.tsx', 'Read supported printed date forms, validate calendar days and allow missing month/day. Do not turn an upload date or an incomplete report date into an invented visit day.')),
        (('R7', 'Expand a branch and open evidence', 'LibraryBrowser.branch → App.select', 'Open the stable document ID. Keyboard tabs, branch expansion, restored focus and scroll support consultation use without losing the chosen scope.'), None),
    ])


def verify_references():
    sources = [*ROOT.glob('backend/*.py'), ROOT / 'backend/schema.sql', *ROOT.glob('src/**/*.ts'), *ROOT.glob('src/**/*.tsx'), *ROOT.glob('src/**/*.css')]
    source = '\n'.join(path.read_text(encoding='utf-8') for path in sources)
    for view in VIEWS:
        for node in view.nodes:
            if not re.search(r'#' + re.escape(node) + r'\b', source):
                raise ValueError(f'No source comment maps node {view.path.relative_to(ROOT)}#{node}')
    print(f'Checked {sum(len(view.nodes) for view in VIEWS)} diagram nodes against source comments.')


def render_pngs():
    from playwright.sync_api import sync_playwright
    executable = os.getenv('PLAYWRIGHT_CHROMIUM_EXECUTABLE', 'C:/Program Files/Google/Chrome/Application/chrome.exe')
    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=executable, headless=True)
        for view in VIEWS:
            page = browser.new_page()
            page.goto(view.path.as_uri())
            overflow = page.evaluate('''() => [...document.querySelectorAll('[data-node]')].flatMap(node => {
                const x=+node.dataset.x, y=+node.dataset.y, w=+node.dataset.width, h=+node.dataset.height;
                return [...node.querySelectorAll('text')].filter(text => {
                    const b=text.getBBox(); return b.x<x || b.x+b.width>x+w-12 || b.y+b.height>y+h-7;
                }).map(text=>node.id+': '+text.textContent);
            })''')
            if overflow:
                raise ValueError(f'Text overflows {view.path.name}: {overflow}')
            # Separate cards must never collide, even as explanatory text grows.
            overlaps = page.evaluate('''() => {const a=[...document.querySelectorAll('[data-node]')];const out=[];
                for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++){
                    const x=a[i].getBBox(),y=a[j].getBBox();
                    if(x.x<y.x+y.width&&x.x+x.width>y.x&&x.y<y.y+y.height&&x.y+x.height>y.y)out.push(a[i].id+'/'+a[j].id);
                }return out;}''')
            if overlaps:
                raise ValueError(f'Overlapping cards: {view.path.name}: {overlaps}')
            detached = page.evaluate('''() => {
                const cards=[...document.querySelectorAll('[data-node]')].map(n=>({
                    x:+n.dataset.x,y:+n.dataset.y,w:+n.dataset.width,h:+n.dataset.height}));
                const onCard=p=>cards.some(c=>((p.x===c.x||p.x===c.x+c.w)&&p.y>=c.y&&p.y<=c.y+c.h)||
                    ((p.y===c.y||p.y===c.y+c.h)&&p.x>=c.x&&p.x<=c.x+c.w));
                return [...document.querySelectorAll('[data-edge]')].filter(e=>
                    !onCard(e.points.getItem(0))||!onCard(e.points.getItem(e.points.numberOfItems-1)))
                    .map(e=>e.getAttribute('points'));
            }''')
            if detached:
                raise ValueError(f'Connectors detached from cards: {view.path.name}: {detached}')
            page.locator('svg').screenshot(path=str(view.path.with_suffix('.png')))
            page.close()
        browser.close()
    print('Rendered every SVG; text fits, cards are separated, and connectors touch their cards.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    main_flow()
    architecture()
    ui_flow()
    import_flow()
    storage_flow()
    database_view()
    browsing_flow()
    chat_flow()
    verify_references()
    if args.render:
        render_pngs()
