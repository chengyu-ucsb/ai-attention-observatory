"""Non-publishing, first-chunk comparison; never a whole-document review.

Uses an already provisioned Qwen GGUF. No downloads, source persistence, library
updates, or publication. CLI runs all retrieval/inference in a killable worker.
"""
from __future__ import annotations

import argparse
import copy
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import queue
import time

import comprehensive_readings as reading
import full_document_access as access

DOIS = ('10.3389/fpsyg.2026.1955418', '10.3389/fpsyg.2026.1906199')
VARIANTS = ('baseline', 'evidence_first')
SEED = 7
MODEL = 'Qwen/Qwen2.5-1.5B-Instruct-GGUF/qwen2.5-1.5b-instruct-q4_k_m.gguf'
LIMITATION = ('First chunk only of two fixed records, not whole-document synthesis or '
              'independent review. Same model verifies its claims; figures, tables and '
              'supplements are not visually checked. Fixed seeds do not guarantee '
              'bitwise reproducibility across inference backends or hardware. A gate pass '
              'is not proof of source accuracy; zero claims are not a substantive pass. '
              'Baseline runs first under a shared deadline; a timed-out or unstarted '
              'candidate is not evidence of inferior quality. The model name is expected, '
              'not verified from the weights; the workflow records the downloaded SHA-256.')
INSTRUCTION = ('Choose relevant supporting evidence before drafting each claim. '
               'Write a concise, single-proposition original paraphrase. '
               'Do not copy any sequence of 13 or more source words.\n')
# Never stringify arbitrary exceptions: backend errors can contain source/prompts.
SAFE_FAILURES = frozenset('''claim_verification_failed unknown_source_span
copied_source_passage claim_length_invalid claim_anchor_invalid claim_anchor_absent
unsupported_numeric_claim unsupported_claim_field claim_not_object
model_schema_invalid model_json_invalid model_output_truncated model_output_incomplete
unexplained_empty_segment invalid_claim_list deferred_chunk_without_evidence_span
evidence_span_coverage_gap deferred_model_context_budget unverified_model_chat_format
deferred_document_time_budget'''.split())


class DeadlineExceeded(Exception):
    pass


def check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise DeadlineExceeded()


class ComparisonModel:
    """Change generation ordering/instruction only; preserve verifier verbatim."""
    def __init__(self, model, variant, deadline):
        if variant not in VARIANTS:
            raise ValueError('invalid_variant')
        self.model, self.variant, self.deadline = model, variant, deadline

    def __getattr__(self, name):
        return getattr(self.model, name)

    def create_chat_completion(self, **kwargs):
        check_deadline(self.deadline)
        kwargs = copy.deepcopy(kwargs)
        schema = kwargs.get('response_format', {}).get('schema', {})
        if self.variant == 'evidence_first' and 'claims' in schema.get('properties', {}):
            claim = schema['properties']['claims']['items']
            properties = claim['properties']
            claim['properties'] = {key: properties[key] for key in ('source_span', 'field', 'text')}
            # The schema requirements and all evidence/format gates stay unchanged.
            kwargs['messages'][-1]['content'] = INSTRUCTION + kwargs['messages'][-1]['content']
        kwargs['seed'] = SEED  # Every generation, retry and verification call.
        reading.check_context_budget(self.model, kwargs['messages'], kwargs['max_tokens'])
        answer = self.model.create_chat_completion(**kwargs)
        check_deadline(self.deadline)
        return answer


def initial_rows():
    return [dict(doi=doi, variant=variant, chunk_id=None, source_sha256=None,
                 chunk_sha256=None, source_coverage='not_retrieved',
                 code='not_started', accepted_claim_count=0)
            for doi in DOIS for variant in VARIANTS]


def evaluate(records, model, *, deadline, retriever=None, emit=None):
    """Core testable in memory; CLI adds hard termination around blocking calls."""
    retriever = retriever or access.retrieve
    rows = initial_rows()
    def send(row):
        if emit:
            emit(copy.deepcopy(row))
    for index, doi in enumerate(DOIS):
        pair = rows[index * 2:index * 2 + 2]
        matches = [r for r in records if access.doi(r.get('doi')) == doi]
        if len(matches) != 1 or matches[0].get('kind') != 'scholarly':
            for row in pair:
                row['code'] = 'record_selection_failed'
                send(row)
            continue
        try:
            check_deadline(deadline)
            document, _ = retriever(copy.deepcopy(matches[0]))
            check_deadline(deadline)
            if document is None or document.coverage.get('evidence_status') != 'full_document_retrieved':
                for row in pair:
                    row.update(code='full_document_required', source_coverage='not_full_document_retrieved')
                    send(row)
                continue
            chunks = reading.chunk_document(document)
            if not chunks or not reading.coverage_is_complete(document, chunks):
                for row in pair:
                    row['code'] = 'source_chunking_failed'
                    send(row)
                continue
            chunk = chunks[0]
            for row in pair:
                row.update(chunk_id=chunk['id'], source_sha256=sha256(
                    '\n'.join(u['text'] for u in document.units).encode()).hexdigest(),
                    chunk_sha256=sha256(chunk['text'].encode()).hexdigest(),
                    source_coverage='full_document_retrieved_first_chunk_only',
                    chunks_total=len(chunks), chunk_characters=len(chunk['text']))
                send(row)
            for row in pair:
                check_deadline(deadline)
                row['code'] = 'in_progress'
                send(row)
                try:
                    claims = reading.read_chunk(ComparisonModel(model, row['variant'], deadline),
                        copy.deepcopy(chunk), 'scholarly', matches[0].get('title', ''), deadline=deadline)
                    row.update(code='gate_pass' if claims else 'no_substantive_claims', accepted_claim_count=len(claims))
                except ValueError as exc:
                    row['code'] = str(exc) if str(exc) in SAFE_FAILURES else 'evaluation_error'
                send(row)
        except DeadlineExceeded:
            break
        except Exception:
            for row in pair:
                if row['code'] in ('not_started', 'in_progress'):
                    row['code'] = 'evaluation_error'
                    send(row)
    if time.monotonic() >= deadline:
        for row in rows:
            if row['code'] in ('not_started', 'in_progress'):
                row['code'] = 'deadline_exceeded'
                send(row)
    return rows


def _worker(out, model_path, deadline):
    # Suppress third-party diagnostics, including native stderr, to prevent a
    # backend exception/log from leaking source text or raw model output.
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        try:
            check_deadline(deadline)
            if not Path(model_path).is_file():
                out.put({'worker_failed': True})
                return
            from llama_cpp import Llama
            model = Llama(model_path=model_path, n_ctx=6144, chat_format='chatml',
                          n_threads=min(os.cpu_count() or 2, 4), seed=SEED, verbose=False)
            records = json.loads(reading.LIB.read_text(encoding='utf-8'))
            evaluate(records, model, deadline=deadline, emit=out.put)
            out.put({'done': True})
        except Exception:
            out.put({'worker_failed': True})


def run_bounded(model_path, seconds=720, *, context=None):
    """Hard overall bound includes model load, retrieval, generation and checks."""
    if not 0 < seconds <= 720:
        raise ValueError('deadline_must_be_between_zero_and_720_seconds')
    ctx = context or multiprocessing.get_context('spawn')
    out = ctx.Queue()
    rows = initial_rows()
    deadline = time.monotonic() + seconds
    process = ctx.Process(target=_worker, args=(out, str(model_path), deadline))
    process.start()
    status = 'deadline_exceeded'
    try:
        while time.monotonic() < deadline:
            try:
                value = out.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                if not process.is_alive():
                    status = 'worker_failed'
                    break
                continue
            if value.get('done'):
                status = 'completed'
                break
            if value.get('worker_failed'):
                status = 'worker_failed'
                break
            for index, row in enumerate(rows):
                if (row['doi'], row['variant']) == (value['doi'], value['variant']):
                    rows[index] = value
                    break
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        out.close()
    for row in rows:
        if row['code'] in ('not_started', 'in_progress'):
            row['code'] = status if status != 'completed' else 'unfinished'
    return dict(status=status, results=rows, expected_model=MODEL,
                settings=dict(seed=SEED, n_ctx=6144, chat_format='chatml', temperature=0.1,
                              generation_max_tokens=2200, verification_max_tokens=500,
                              n_threads=min(os.cpu_count() or 2, 4), deadline_seconds=seconds),
                limitation=LIMITATION, source_text_saved=False)


def report_path(value):
    path = Path(value).expanduser().resolve()
    if path == reading.ROOT or reading.ROOT in path.parents:
        raise ValueError('report_output_must_be_outside_repository')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=os.getenv('LOCAL_READING_MODEL', '/tmp/attention-model.gguf'))
    parser.add_argument('--time-budget-seconds', '--deadline-seconds', dest='deadline_seconds', type=float, default=720)
    parser.add_argument('--report', '--output', dest='output', help='Also save the stdout JSON report to a new file outside repository')
    args = parser.parse_args(argv)
    try:
        output = report_path(args.output) if args.output else None
        if not 0 < args.deadline_seconds <= 720:
            parser.error('deadline must be greater than zero and at most 720 seconds')
        if output and output.exists():
            parser.error('output already exists; choose a new path')
    except ValueError:
        parser.error('report output must be outside the repository')
    report = run_bounded(args.model, args.deadline_seconds)
    encoded = json.dumps(report, indent=2) + '\n'
    if output:
        with output.open('x', encoding='utf-8') as stream:
            stream.write(encoded)
    print(encoded, end='')
    infrastructure_errors = {'evaluation_error', 'record_selection_failed', 'source_chunking_failed'}
    return int(report['status'] == 'worker_failed' or
               any(row['code'] in infrastructure_errors for row in report['results']))


if __name__ == '__main__':
    raise SystemExit(main())
