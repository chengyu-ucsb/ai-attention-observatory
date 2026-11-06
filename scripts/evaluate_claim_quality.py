"""Non-publishing, controlled claim validator/verifier evaluation.

The first generation is a prescribed fixture, not a model-written summary.
All production gates and the production verifier prompt remain unchanged.
Only an already provisioned local GGUF is used; this script never downloads,
retrieves source text, reads/writes the library, or publishes anything.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import queue
import re
import time
from urllib.parse import urlsplit

import comprehensive_readings as reading

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/claim_quality_sources.json'
MODEL = 'Qwen/Qwen2.5-1.5B-Instruct-GGUF/qwen2.5-1.5b-instruct-q4_k_m.gguf'
SEED = 7
VARIANTS = ('baseline', 'exact_partition')
MAX_SECONDS = 720
REVIEW_STATUS = 'assistant_source_reviewed_not_independent_expert_review'
LICENSES = {
    'CC-BY-4.0': 'https://creativecommons.org/licenses/by/4.0/',
    'CC-BY-3.0': 'https://creativecommons.org/licenses/by/3.0/',
    'CC-BY-2.5': 'https://creativecommons.org/licenses/by/2.5/',
    'CC-BY-2.0': 'https://creativecommons.org/licenses/by/2.0/',
    'CC0-1.0': 'https://creativecommons.org/publicdomain/zero/1.0/',
}
CATEGORIES = frozenset('''supported numeric direction causality omitted_caveat
attribution unrelated_anchor copied_text interpretation_as_result unsupported_transfer_attention'''.split())
REJECTION_CODES = frozenset('''claim_verification_failed unknown_source_span
copied_source_passage claim_length_invalid claim_anchor_invalid claim_anchor_absent
unsupported_numeric_claim unsupported_claim_field claim_not_object'''.split())
FORMAT_CODES = frozenset('''model_schema_invalid model_json_invalid
model_output_truncated model_output_incomplete invalid_claim_list
unexplained_empty_segment model_verdict_indices_invalid'''.split())
CONTEXT_CODES = frozenset(('deferred_model_context_budget', 'unverified_model_chat_format'))
UNAVAILABLE_CODES = frozenset(('deferred_document_time_budget', 'deadline_exceeded',
                             'worker_failed', 'unfinished'))
QUALITY_OUTCOMES = ('true_acceptance', 'false_acceptance', 'true_rejection', 'false_rejection')
STATUSES = frozenset(('not_started', 'in_progress', 'accepted', 'rejected',
                      'unavailable', 'format_error', 'context_error', 'evaluation_error'))
STAGES = frozenset(('not_started', 'generation', 'generation_retry', 'verifier', 'validator', 'worker'))
SAFE_CODES = REJECTION_CODES | FORMAT_CODES | CONTEXT_CODES | UNAVAILABLE_CODES | {
    'not_started', 'in_progress', 'gate_pass', 'evaluation_error', 'fixture_proposal_changed'}
LIMITATION = (
    'Controlled source-reviewed fixture claims test the existing validator and verifier, '
    'not model-generated summary quality, whole-document accuracy, or independent expert review. '
    'Labels and source/license evidence were reviewed by an assistant, not independently '
    'expert adjudicated. Offline validation checks metadata and exact anchors, not live '
    'license pages or the truth of labels. A gate pass is not proof of source accuracy. '
    'Errors, unavailable cases and deferred context are excluded from quality outcomes. '
    'Short licensed source excerpts are repository fixture inputs; no source or claim text '
    'is included in the report and no additional source text is saved. '
    'The model identifier is expected, not verified from weights; its SHA-256 identifies '
    'the supplied file. A fixed seed does not guarantee identical results across backends.'
)


class FixtureError(ValueError):
    """Messages are fixed codes, never fixture/source contents."""


class DeadlineExceeded(Exception):
    pass


def check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise DeadlineExceeded()


def digest(value):
    return sha256(value.encode('utf-8')).hexdigest()


def fixture_digest(fixtures):
    return digest(json.dumps(fixtures, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


def _require(condition, code):
    if not condition:
        raise FixtureError(code)


def _https_url(value):
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and bool(url.hostname) and '.' in url.hostname
                and not url.username and not url.password and url.port in (None, 443))
    except ValueError:
        return False


def validate_fixtures(fixtures):
    """Offline structural/rights-evidence checks, not semantic adjudication.

    Negative cases can deliberately fail an existing gate. Positive claims must
    pass the deterministic production checks, including the 13-word copy gate.
    Neither a URL nor a license field alone verifies rights to an excerpt.
    """
    root_fields = {'version', 'review_status', 'sources'}
    _require(type(fixtures) is dict and root_fields <= set(fixtures)
             and set(fixtures) <= root_fields | {'review_scope', 'label_definition'},
             'fixture_root_invalid')
    for key in ('review_scope', 'label_definition'):
        if key in fixtures:
            _require(isinstance(fixtures[key], str) and fixtures[key].strip(), 'fixture_review_metadata_missing')
    _require(type(fixtures['version']) is int and fixtures['version'] == 1, 'fixture_version_invalid')
    _require(fixtures['review_status'] == REVIEW_STATUS, 'fixture_review_status_invalid')
    sources = fixtures['sources']
    _require(type(sources) is list and 1 <= len(sources) <= 32, 'fixture_sources_invalid')
    source_ids, case_ids = set(), set()
    positives = negatives = 0
    source_fields = {'id', 'title', 'doi', 'url', 'license', 'license_url',
                     'license_verified_at', 'section', 'text', 'cases',
                     'license_verification_basis', 'excerpt_locations'}
    optional_fields = {'authors', 'published', 'year', 'library_match', 'kind', 'source_verified_at',
                       'review_status', 'review_note', 'reuse_note', 'excerpt_note'}
    case_fields = {'id', 'field', 'text', 'quote', 'source_span',
                   'expected_supported', 'category', 'rationale'}
    for source in sources:
        _require(type(source) is dict and source_fields <= set(source)
                 and set(source) <= source_fields | optional_fields, 'fixture_source_metadata_invalid')
        _require(all(isinstance(source[key], str) and source[key].strip()
                     for key in source_fields - {'cases', 'excerpt_locations'}), 'fixture_source_metadata_missing')
        for key in (optional_fields & set(source)) - {'authors', 'year'}:
            _require(isinstance(source[key], str) and source[key].strip(), 'fixture_source_metadata_missing')
        if 'authors' in source:
            _require(type(source['authors']) is list and bool(source['authors'])
                     and all(isinstance(author, str) and author.strip() for author in source['authors']),
                     'fixture_source_metadata_missing')
        if 'review_status' in source:
            _require(source['review_status'] == REVIEW_STATUS, 'fixture_review_status_invalid')
        if 'kind' in source:
            _require(source['kind'] == 'scholarly', 'fixture_source_kind_invalid')
        if 'year' in source:
            _require(type(source['year']) is int and 1900 <= source['year'] <= datetime.now(timezone.utc).year,
                     'fixture_source_metadata_invalid')
        _require(re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,63}', source['id']) is not None
                 and source['id'] not in source_ids, 'fixture_source_id_invalid')
        source_ids.add(source['id'])
        _require(re.fullmatch(r'10\.\d{4,9}/\S+', source['doi']) is not None
                 and _https_url(source['url']), 'fixture_source_provenance_invalid')
        _require(source['license'] in LICENSES
                 and source['license_url'] == LICENSES[source['license']], 'fixture_license_evidence_invalid')
        try:
            reviewed = date.fromisoformat(source['license_verified_at'])
        except ValueError:
            raise FixtureError('fixture_license_date_invalid') from None
        _require(reviewed.isoformat() == source['license_verified_at'] and reviewed <= datetime.now(timezone.utc).date(),
                 'fixture_license_date_invalid')
        _require(5 <= len(source['text'].split()) <= 300 and len(source['text']) <= 10000,
                 'fixture_excerpt_length_invalid')
        locations = source['excerpt_locations']
        _require(type(locations) is list and 1 <= len(locations) <= 32, 'fixture_excerpt_evidence_missing')
        end = 0
        for location in locations:
            _require(type(location) is dict and set(location) == {'section', 'locator', 'start', 'end'},
                     'fixture_excerpt_evidence_invalid')
            _require(all(isinstance(location[key], str) and location[key].strip() for key in ('section', 'locator'))
                     and type(location['start']) is int and type(location['end']) is int
                     and end <= location['start'] < location['end'] <= len(source['text'])
                     and not source['text'][end:location['start']].strip(), 'fixture_excerpt_evidence_invalid')
            end = location['end']
        _require(not source['text'][end:].strip(), 'fixture_excerpt_evidence_invalid')
        chunk = {'id': 'C0001', 'text': source['text']}
        spans = {span['id']: ' '.join(span['text'].split()) for span in reading.source_spans(chunk)}
        cases = source['cases']
        _require(type(cases) is list and 1 <= len(cases) <= 32, 'fixture_cases_invalid')
        for case in cases:
            _require(type(case) is dict and set(case) == case_fields, 'fixture_case_metadata_invalid')
            _require(all(isinstance(case[key], str) and case[key].strip()
                         for key in case_fields - {'expected_supported'}), 'fixture_case_metadata_missing')
            _require(re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,79}', case['id']) is not None
                     and case['id'] not in case_ids, 'fixture_case_id_invalid')
            case_ids.add(case['id'])
            _require(type(case['expected_supported']) is bool, 'fixture_label_invalid')
            _require(case['field'] in reading.FIELDS['scholarly'], 'fixture_field_invalid')
            _require(case['category'] in CATEGORIES, 'fixture_category_invalid')
            _require(6 <= len(case['text'].split()) <= 90, 'fixture_claim_length_invalid')
            _require(case['source_span'] in spans, 'fixture_source_span_invalid')
            _require(case['quote'] == spans[case['source_span']], 'fixture_anchor_mismatch')
            if case['expected_supported']:
                try:
                    reading.validate_claim(case, chunk, 'scholarly')
                except ValueError:
                    raise FixtureError('fixture_positive_fails_production_gate') from None
                positives += 1
            else:
                negatives += 1
    _require(positives > 0 and negatives > 0, 'fixture_both_labels_required')
    _require(len(case_ids) <= 128, 'fixture_too_many_cases')
    return {'sources': len(source_ids), 'cases': len(case_ids),
            'expected_supported': positives, 'expected_unsupported': negatives}


class FixtureModel:
    """Inject exactly one generation; delegate all subsequent calls unchanged.

    Verifier prompts, retries and generation parameters are production-owned.
    Baseline adds only the fixed seed; exact_partition additionally constrains
    the verifier schema to every valid singleton partition. The injected
    proposal always contains exactly one claim, irrespective of its label.
    """
    def __init__(self, model, case, deadline, variant='baseline'):
        if variant not in VARIANTS:
            raise ValueError('invalid_variant')
        self.model, self.deadline = model, deadline
        self.variant = variant
        self.proposal = {key: copy.deepcopy(case[key]) for key in ('field', 'text', 'source_span')}
        self.claim_count = 1  # This harness injects a single prescribed claim.
        self.injected = False
        self.stage = 'generation'
        self.verifier_format_error = None

    def __getattr__(self, name):
        return getattr(self.model, name)

    def create_chat_completion(self, **kwargs):
        check_deadline(self.deadline)
        schema = kwargs.get('response_format', {}).get('schema', {})
        generation = 'claims' in schema.get('properties', {})
        self.stage = 'generation_retry' if generation and self.injected else 'generation' if generation else 'verifier'
        if generation and not self.injected:
            self.injected = True
            value = {'claims': [copy.deepcopy(self.proposal)], 'no_claim_reason': ''}
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}
        kwargs = copy.deepcopy(kwargs)
        if not generation and self.variant == 'exact_partition':
            # This controlled diagnostic changes only the verifier grammar.
            # Every acceptance/rejection decision remains possible; fixture
            # generation, prompts, production validation and retries are intact.
            kwargs['response_format']['schema'] = exact_partition_schema(self.claim_count)
        kwargs['seed'] = SEED
        answer = self.model.create_chat_completion(**kwargs)
        if not generation:
            # Diagnostics only: return the original response to production intact.
            # Production deliberately fails closed on a discernible negative
            # before schema/finish checks; malformed negatives are not quality data.
            self.verifier_format_error = verifier_format_error(answer)
        check_deadline(self.deadline)
        return answer


def exact_partition_schema(claim_count):
    """Enumerate every complete disjoint verdict for 1–6 proposed claims.

    Root object enum is supported by llama.cpp's JSON-schema grammar converter.
    This constrains output indices, never the semantic support decision.
    """
    if type(claim_count) is not int or not 1 <= claim_count <= 6:
        raise ValueError('claim_count_must_be_between_one_and_six')
    schema = copy.deepcopy(reading.verification_schema())
    schema['enum'] = [
        {'supported': [index for index in range(claim_count) if mask & (1 << index)],
         'rejected': [index for index in range(claim_count) if not mask & (1 << index)]}
        for mask in range(1 << claim_count)
    ]
    return schema


def verifier_format_error(response):
    """Diagnose a complete, exact singleton verdict without changing any gate."""
    try:
        choice = response['choices'][0]
        if choice.get('finish_reason') == 'length':
            return 'model_output_truncated'
        if choice.get('finish_reason') != 'stop':
            return 'model_output_incomplete'
        content = choice['message'].get('content')
        if not isinstance(content, str):
            return 'model_json_invalid'
        try:
            answer = json.loads(content)
        except json.JSONDecodeError:
            return 'model_json_invalid'
        try:
            reading.validate_response_shape(answer, reading.verification_schema())
        except reading.ModelFormatError:
            return 'model_schema_invalid'
        supported, rejected = answer['supported'], answer['rejected']
        if (len(set(supported)) != len(supported) or len(set(rejected)) != len(rejected)
                or set(supported) & set(rejected) or set(supported) | set(rejected) != {0}):
            return 'model_verdict_indices_invalid'
        return None
    except (KeyError, IndexError, TypeError, AttributeError):
        return 'model_json_invalid'


def diagnostic_code(code, wrapper):
    if (wrapper.verifier_format_error is not None
            and code in FORMAT_CODES | {'gate_pass', 'claim_verification_failed'}):
        return wrapper.verifier_format_error
    return code


def initial_rows(fixtures):
    return [dict(source_id=source['id'], case_id=case['id'], category=case['category'],
                 expected_supported=case['expected_supported'], source_sha256=digest(source['text']),
                 claim_sha256=digest(case['text']), anchor_sha256=digest(case['quote']),
                 status='not_started', code='not_started', stage='not_started', outcome=None)
            for source in fixtures['sources'] for case in source['cases']]


def set_result(row, code, stage):
    row.update(code=code if code in SAFE_CODES else 'evaluation_error', stage=stage, outcome=None)
    if code == 'gate_pass':
        row.update(status='accepted', outcome='true_acceptance' if row['expected_supported'] else 'false_acceptance')
    elif code in REJECTION_CODES:
        row.update(status='rejected', stage='verifier' if code == 'claim_verification_failed' else 'validator',
                   outcome='false_rejection' if row['expected_supported'] else 'true_rejection')
    elif code in FORMAT_CODES:
        row['status'] = 'format_error'
    elif code in CONTEXT_CODES:
        row['status'] = 'context_error'
    elif code in UNAVAILABLE_CODES:
        row['status'] = 'unavailable'
    else:
        row['status'] = 'evaluation_error'


def evaluate(fixtures, model, *, deadline, emit=None, variant='baseline'):
    """Evaluate in memory; the CLI additionally contains native hangs in a worker."""
    validate_fixtures(fixtures)
    rows = initial_rows(fixtures)
    index = 0
    for source in fixtures['sources']:
        for case in source['cases']:
            row = rows[index]
            index += 1
            wrapper = FixtureModel(model, case, deadline, variant=variant)
            try:
                check_deadline(deadline)
                row.update(status='in_progress', code='in_progress', stage='generation')
                if emit:
                    emit(copy.deepcopy(row))
                claims = reading.read_chunk(wrapper, {'id': 'C0001', 'text': source['text']},
                                            'scholarly', source['title'], deadline=deadline)
                expected = [{key: case[key] for key in ('field', 'text', 'quote')}]
                code = 'gate_pass' if claims == expected else 'fixture_proposal_changed'
                set_result(row, diagnostic_code(code, wrapper), wrapper.stage)
            except DeadlineExceeded:
                set_result(row, 'deadline_exceeded', wrapper.stage)
            except ValueError as exc:
                set_result(row, diagnostic_code(str(exc), wrapper), wrapper.stage)
            except Exception:
                set_result(row, 'evaluation_error', wrapper.stage)
            if emit:
                emit(copy.deepcopy(row))
    return rows


def metrics(rows):
    confusion = {key: sum(row['outcome'] == key for row in rows) for key in QUALITY_OUTCOMES}
    positive = confusion['true_acceptance'] + confusion['false_rejection']
    negative = confusion['true_rejection'] + confusion['false_acceptance']
    return {
        'confusion_matrix': confusion,
        'quality_evaluated': positive + negative,
        'positive_quality_evaluated': positive,
        'negative_quality_evaluated': negative,
        'false_acceptance_rate': confusion['false_acceptance'] / negative if negative else None,
        'false_rejection_rate': confusion['false_rejection'] / positive if positive else None,
        'excluded_from_quality': {status: sum(row['status'] == status for row in rows)
                                  for status in ('unavailable', 'format_error', 'context_error', 'evaluation_error',
                                                 'not_started', 'in_progress')},
    }


def _model_hash(path, deadline):
    result = sha256()
    with path.open('rb') as stream:
        while True:
            check_deadline(deadline)
            block = stream.read(1024 * 1024)
            if not block:
                return result.hexdigest()
            result.update(block)


def _worker(out, fixtures, model_path, deadline, *, variant='baseline'):
    # Redirect Python and native logging before importing/loading any backend.
    with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        try:
            check_deadline(deadline)
            path = Path(model_path)
            if not path.is_file():
                out.put({'worker_failed': True})
                return
            out.put({'model_sha256': _model_hash(path, deadline)})
            from llama_cpp import Llama
            model = Llama(model_path=str(path), n_ctx=6144, chat_format='chatml',
                          n_threads=min(os.cpu_count() or 2, 4), seed=SEED, verbose=False)
            evaluate(fixtures, model, deadline=deadline, emit=out.put, variant=variant)
            out.put({'done': True})
        except DeadlineExceeded:
            out.put({'deadline_exceeded': True})
        except Exception:
            out.put({'worker_failed': True})


def _accept_row(value, rows):
    """IPC reports cannot introduce arbitrary fields, identifiers or prose."""
    if type(value) is not dict:
        return
    for index, row in enumerate(rows):
        if (value.get('source_id'), value.get('case_id')) != (row['source_id'], row['case_id']):
            continue
        immutable = set(row) - {'status', 'code', 'stage', 'outcome'}
        if (set(value) != set(row) or any(value[key] != row[key] for key in immutable)
                or value['status'] not in STATUSES or value['code'] not in SAFE_CODES
                or value['stage'] not in STAGES or value['outcome'] not in (*QUALITY_OUTCOMES, None)):
            return
        if value['code'] == 'in_progress':
            if value['status'] != 'in_progress' or value['outcome'] is not None:
                return
        else:
            expected = copy.deepcopy(value)
            set_result(expected, value['code'], value['stage'])
            if expected != value:
                return
        rows[index] = copy.deepcopy(value)
        return


def run_bounded(fixtures, model_path, seconds=MAX_SECONDS, *, context=None, variant='baseline'):
    """Bound model hashing/loading and all inference, including native hangs.

    Reserve a small portion of the total for terminate/kill, rather than adding
    cleanup time to the configured maximum. Completed per-case results survive.
    """
    if not 0 < seconds <= MAX_SECONDS:
        raise ValueError('deadline_must_be_between_zero_and_720_seconds')
    if variant not in VARIANTS:
        raise ValueError('invalid_variant')
    started = time.monotonic()
    counts = validate_fixtures(fixtures)
    total_deadline = started + seconds
    cleanup_reserve = min(1.0, seconds / 10)
    deadline = total_deadline - cleanup_reserve
    ctx = context or multiprocessing.get_context('spawn')
    out = ctx.Queue()
    rows = initial_rows(fixtures)
    process = ctx.Process(target=_worker, args=(out, copy.deepcopy(fixtures), str(model_path), deadline),
                          kwargs={'variant': variant})
    status, model_hash, process_started = 'deadline_exceeded', None, False
    try:
        check_deadline(deadline)
        process.start()
        process_started = True
        while time.monotonic() < deadline:
            try:
                value = out.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                if not process.is_alive():
                    status = 'worker_failed'
                    break
                continue
            if type(value) is not dict:
                continue
            if value == {'done': True}:
                status = 'completed'
                break
            if value == {'worker_failed': True}:
                status = 'worker_failed'
                break
            if value == {'deadline_exceeded': True}:
                break
            if (set(value) == {'model_sha256'} and isinstance(value['model_sha256'], str)
                    and re.fullmatch(r'[0-9a-f]{64}', value['model_sha256'])):
                model_hash = value['model_sha256']
                continue
            _accept_row(value, rows)
    except DeadlineExceeded:
        pass
    except Exception:
        status = 'worker_failed'
    finally:
        if process_started:
            if process.is_alive():
                process.terminate()
            process.join(timeout=max(0, min(cleanup_reserve / 2, total_deadline - time.monotonic())))
            if process.is_alive():
                process.kill()
                process.join(timeout=max(0, total_deadline - time.monotonic()))
        out.close()
    for row in rows:
        if row['status'] in ('not_started', 'in_progress'):
            set_result(row, status if status != 'completed' else 'unfinished', 'worker')
    if status == 'completed' and any(row['code'] == 'unfinished' for row in rows):
        status = 'worker_failed'
    return {
        'status': status, 'variant': variant, 'review_status': REVIEW_STATUS, 'fixture_sha256': fixture_digest(fixtures),
        'fixture_counts': counts, 'results': rows, 'metrics': metrics(rows),
        'expected_model': MODEL, 'model_sha256': model_hash,
        'settings': {'seed': SEED, 'n_ctx': 6144, 'chat_format': 'chatml', 'temperature': 0.1,
                     'generation': 'prescribed_fixture_no_model_generation', 'verification_max_tokens': 500,
                     'n_threads': min(os.cpu_count() or 2, 4), 'deadline_seconds': seconds},
        'limitation': LIMITATION, 'source_text_in_report': False,
        'additional_source_text_saved': False, 'library_modified': False,
    }


def report_path(value):
    path = Path(value).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('report_output_must_be_outside_repository')
    return path


def load_fixtures(path):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        _require(len(raw) <= 1024 * 1024, 'fixture_file_too_large')
        value = json.loads(raw)
    except (OSError, ValueError, UnicodeError):
        raise FixtureError('fixture_file_invalid') from None
    validate_fixtures(value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', default=str(FIXTURES))
    parser.add_argument('--validate-only', action='store_true', help='Offline metadata/anchor validation; no model load')
    parser.add_argument('--variant', choices=VARIANTS, default='baseline',
                        help='Diagnostic verifier grammar; exact_partition retains every possible support decision')
    parser.add_argument('--time-budget-seconds', '--deadline-seconds', dest='seconds', type=float, default=MAX_SECONDS)
    parser.add_argument('--report', '--output', dest='output', help='Also save safe JSON to a new file outside the repository')
    args = parser.parse_args(argv)
    try:
        output = report_path(args.output) if args.output else None
        if not 0 < args.seconds <= MAX_SECONDS:
            parser.error('deadline must be greater than zero and at most 720 seconds')
        if output and output.exists():
            parser.error('output already exists; choose a new path')
    except ValueError:
        parser.error('report output must be outside the repository')
    try:
        fixtures = load_fixtures(args.fixtures)
        if args.validate_only:
            report = {'status': 'validated', 'variant': args.variant, 'review_status': REVIEW_STATUS,
                      'fixture_sha256': fixture_digest(fixtures), 'fixture_counts': validate_fixtures(fixtures),
                      'model_loaded': False, 'limitation': LIMITATION}
        else:
            report = run_bounded(fixtures, os.getenv('LOCAL_READING_MODEL', '/tmp/attention-model.gguf'), args.seconds,
                                 variant=args.variant)
    except FixtureError as exc:
        report = {'status': 'fixture_invalid', 'variant': args.variant, 'code': str(exc), 'model_loaded': False}
    encoded = json.dumps(report, indent=2) + '\n'
    if output:
        try:
            with output.open('x', encoding='utf-8') as stream:
                stream.write(encoded)
        except OSError:
            print(json.dumps({'status': 'report_write_failed'}))
            return 1
    print(encoded, end='')
    return int(report['status'] in ('worker_failed', 'fixture_invalid') or
               any(row['status'] == 'evaluation_error' for row in report.get('results', [])))


if __name__ == '__main__':
    raise SystemExit(main())
