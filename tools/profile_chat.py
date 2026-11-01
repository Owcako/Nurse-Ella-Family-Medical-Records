"""Time real demo chat calls without changing the app or production library.

Run on the application host from its repository root:
  .venv/bin/python tools/profile_chat.py --env /etc/family-medical-records/environment
Only source-hash-verified fictional John Smith PDFs are exposed to this process.
Output contains timings/counts/token usage, never report text or model answers.
"""

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import time
from contextlib import contextmanager
from types import SimpleNamespace

ROOT = Path(os.getenv('FMR_APP_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from backend import chat, demo, processing
from backend.storage import Library


class ReadOnlyLibrary(Library):
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        try:
            yield db
        finally:
            db.close()


def run(args):
    load_dotenv(args.env)
    # Suppress the application's normal content-bearing response diagnostics here.
    processing.logger.disabled = True
    logging.getLogger('httpx').setLevel(logging.WARNING)
    library = ReadOnlyLibrary(Path(args.library or os.getenv('LIBRARY_PATH', ROOT / 'data/library.sqlite3')))
    kit = demo.manifest()
    prepared = json.loads((demo.KIT / 'prepared.json').read_text(encoding='utf-8'))
    files = []
    for file in library.list():
        preset = prepared.get(file['original_filename'])
        if preset and hashlib.sha256(library.source(file['id'])).hexdigest() == preset['source_sha256']:
            files.append(file)
    if len(files) != len(prepared):
        raise RuntimeError('Expected all ten source-verified fictional John Smith reports; no AI calls made.')
    profiles = library.profiles()
    john = next(profile for profile in profiles if profile['name'].lower() in ('john smith', 'smith, john'))
    ids = {file['id'] for file in files}
    # The exact production snapshots are read, but only verified demo files can be retrieved.
    def get(file_id):
        if file_id not in ids:
            raise KeyError(file_id)
        return library.get(file_id)

    def source(file_id):
        if file_id not in ids:
            raise KeyError(file_id)
        return library.source(file_id)

    scoped = SimpleNamespace(list=lambda: files, profiles=lambda: [john], get=get, source=source)
    original_client = processing.client
    results = []
    active = None

    class TimedClient:
        def __init__(self):
            self.client = original_client()
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def __enter__(self):
            self.client.__enter__()
            return self

        def __exit__(self, *error):
            return self.client.__exit__(*error)

        def create(self, **kwargs):
            messages = kwargs.get('messages', [])
            row = dict(round=len(active['calls']) + 1,
                       input_message_chars=sum(len(json.dumps(item, ensure_ascii=False)) for item in messages),
                       request_json_bytes=len(json.dumps(kwargs, ensure_ascii=False).encode()))
            started = time.perf_counter()
            try:
                response = self.client.chat.completions.create(**kwargs)
            except Exception as error:
                row.update(seconds=round(time.perf_counter() - started, 3), error_type=type(error).__name__)
                active['calls'].append(row)
                raise
            row['seconds'] = round(time.perf_counter() - started, 3)
            calls = response.choices[0].message.tool_calls or []
            row['actions'] = [call.function.name for call in calls]
            row['requested_document_counts'] = [len(json.loads(call.function.arguments).get('file_ids', []))
                                                for call in calls if call.function.name == 'read_documents']
            row['phase'] = ('final_review' if any('finish_answer' in item.get('actions', []) for item in active['calls'])
                            else 'draft' if 'finish_answer' in row['actions'] else 'retrieval_selection')
            if response.usage:
                row['tokens'] = response.usage.model_dump(exclude_none=True)
            active['calls'].append(row)
            print(json.dumps(dict(question=active['question_id'], **row), ensure_ascii=False), flush=True)
            return response

    processing.client = TimedClient
    # Keep only structural validation-error counts; never write model response contents.
    processing.log_response = lambda *_: None
    try:
        for question_id in args.questions.split(','):
            question = next(item for item in kit['questions'] if item['id'] == question_id)
            active = dict(question_id=question_id, question=question['question'], history_turns=0, viewer_selected=False, calls=[])
            started = time.perf_counter()
            try:
                answer = chat.chat(scoped, chat.Question(message=question['question'], member='profile:' + john['id'], language='en'))
                active.update(success=True, search=answer['search'], answer_chars=len(answer['message']))
            except Exception as error:
                active.update(success=False, error_type=type(error).__name__)
            active['total_seconds'] = round(time.perf_counter() - started, 3)
            active['ai_seconds'] = round(sum(item['seconds'] for item in active['calls']), 3)
            active['non_ai_seconds'] = round(active['total_seconds'] - active['ai_seconds'], 3)
            results.append(active)
            report = dict(service=processing.service_name(), execution='GCP process; production chat function; no HTTP/tunnel/browser',
                          dataset='10 source-hash-verified fictional John Smith PDFs', results=results)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({key: value for key, value in active.items() if key != 'calls'}, ensure_ascii=False), flush=True)
    finally:
        processing.client = original_client


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', default=str(ROOT / '.env'))
    parser.add_argument('--library')
    parser.add_argument('--questions', default='1.1,2.2,4.1')
    parser.add_argument('--output', type=Path, default=ROOT / 'tmp/chat-profile.json')
    run(parser.parse_args())
