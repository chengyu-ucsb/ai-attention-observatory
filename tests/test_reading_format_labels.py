"""Offline process regressions with document fixtures and mocked synthesis.

All fixture prose is synthetic. Core PDF cases mock only the optional reader;
HTML/XML parsing and all coverage/label assertions run without dependencies.
Real-byte PDF integration also runs when pypdf is installed. No source retrieval,
external provider, model, or canonical data write is needed.
"""
from copy import deepcopy
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import comprehensive_readings as reading
import full_document_access as access
from structured_article_access import document_from_xml

TITLE = 'Generative AI and human attention in learning'
DOI = '10.5555/format-fixture'
VERSION = 'acceptedVersion'
TODAY = date(2026, 11, 9)
PROSE = 'Synthetic source text describes an argument and its qualifications for testing. '
PREFIX = ('Every retrieved text chunk processed; claim-level machine checks. '
          'Not independently reviewed. Figures, tables and supplements not visually verified. ')
PARTIAL = 'Partial source coverage; not a whole-article review.'
XML_BASIS = ('All supplied article XML text retrieved; '
             'equivalence to the original PDF is not verified.')


def record(kind='scholarly'):
    # Exercise the real scholarly screening gate, not an unconditional mock.
    return {'kind': kind, 'title': TITLE, 'doi': DOI,
            'venue': 'Computers in Human Behavior',
            'url': 'https://www.econstor.eu/source.pdf'}


def pdf_document(blank_page=False):
    # Match the dependency-free PDF-reader fixture in test_article_retrieval_routes.
    # The production parser still derives complete/partial coverage from pages.
    pages = [SimpleNamespace(extract_text=Mock(return_value=TITLE + '\n' + PROSE * 24)),
             SimpleNamespace(extract_text=Mock(return_value='' if blank_page else PROSE * 24))]
    reader = SimpleNamespace(PdfReader=Mock(return_value=SimpleNamespace(pages=pages)))
    with patch.dict(sys.modules, {'pypdf': reader}):
        return access.document_from_pdf(b'%PDF-1.7 SYNTHETIC_READER_FIXTURE', record(),
                                        'https://www.econstor.eu/source.html', VERSION)


def parsed_pdf_document(blank_page=False):
    try:
        from pypdf import PdfWriter
    except ModuleNotFoundError as exc:
        if exc.name != 'pypdf':
            raise
        raise unittest.SkipTest('Optional pypdf integration; core PDF assertions run without it') from exc
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica')}))
    for number in range(2):
        page = writer.add_blank_page(width=612, height=792)
        if blank_page and number == 1:
            continue
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        lines = [TITLE] + [PROSE] * 24 + [f'Fixture page {number + 1} ends here.']
        stream.set_data(('BT /F1 9 Tf 12 TL 40 750 Td ' +
                         ' '.join(f'({line}) Tj T*' for line in lines) + ' ET').encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    # The URL deliberately has the wrong suffix. The actual parser establishes
    # PDF page coverage; neither the URL nor the record kind establishes format.
    return access.document_from_pdf(output.getvalue(), record(),
                                    'https://www.econstor.eu/source.html', VERSION)


def html_document():
    raw = (f'<html><head><title>{TITLE}</title></head><body><article>'
           '<div class="entry-content">' + ''.join(f'<p>{PROSE * 4}</p>' for _ in range(8)) +
           '</div></article></body></html>').encode()
    return access.document_from_html(raw, record(), record()['url'], VERSION)


def xml_document(format):
    if format == 'jats':
        raw = (f'<article><front><article-meta><article-id pub-id-type="doi">{DOI}</article-id>'
               f'<title-group><article-title>{TITLE}</article-title></title-group>'
               '<permissions><license href="https://creativecommons.org/licenses/by/4.0/">'
               'CC BY 4.0</license></permissions></article-meta></front>'
               f'<body><sec><title>Argument</title><p>{PROSE * 30}</p></sec></body>'
               '<back><ref-list><ref>Fixture reference.</ref></ref-list></back></article>')
    else:
        raw = (f'<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>'
               f'<titleStmt><title>{TITLE}</title></titleStmt><sourceDesc><biblStruct>'
               f'<idno type="DOI">{DOI}</idno></biblStruct></sourceDesc></fileDesc></teiHeader>'
               f'<text><body><div><head>Argument</head><p>{PROSE * 30}</p></div></body>'
               '<back>Fixture reference.</back></text></TEI>')
    return document_from_xml(raw.encode(), record(), record()['url'], version=VERSION, format=format)


class ReadingFormatLabelTests(unittest.TestCase):
    def process_document(self, document, kind, expected, previous=None):
        row = record(kind)
        if previous is not None:
            row['deep_analysis'] = deepcopy(previous)
        coverage = deepcopy(document.coverage)
        units = deepcopy(document.units)
        model = Mock()
        diagnostics = [{'stage': 'article', 'status': coverage['evidence_status']}]
        result = {'coverage': {**document.manifest(), 'all_retrieved_text_processed': True},
                  'claim_evidence': [], **{field: '' for field in reading.FIELDS[kind]}}
        with patch.object(reading, 'synthesize', return_value=result) as synthesize:
            stats = reading.process([row], model, retriever=lambda _: (document, diagnostics),
                                    run_date=TODAY)
        synthesize.assert_called_once()
        self.assertIs(synthesize.call_args.args[0], document)
        self.assertEqual(synthesize.call_args.args[2], kind)
        model.create_chat_completion.assert_not_called()
        self.assertEqual(stats['summaries_completed'], 1, stats)
        self.assertEqual(stats['failed'], 0)
        complete = coverage['evidence_status'] == 'full_document_retrieved'
        self.assertEqual(stats['partial_inputs'], int(not complete))
        saved = row.get('partial_reading_candidate', row['deep_analysis'])
        self.assertEqual(saved['basis'], PREFIX + expected)
        self.assertEqual(saved['version'], 3)
        self.assertEqual(saved['coverage']['document_version'], VERSION)
        self.assertEqual(saved['source_hash'], sha256('\n'.join(u['text'] for u in units).encode()).hexdigest())
        self.assertEqual(saved['source_hash'], saved['coverage']['source_sha256'])
        self.assertEqual(saved['source_url'], access.diagnostic_url(document.url))
        self.assertEqual(saved['review_status'], 'machine_checked_not_independently_reviewed')
        self.assertFalse(saved['coverage']['source_text_saved'])
        self.assertFalse(saved['coverage']['tables_figures_visually_checked'])
        self.assertFalse(saved['coverage']['supplements_checked'])
        depth = (('full_text' if complete else 'partial_full_text') if kind == 'scholarly'
                 else ('source_html' if complete else 'partial_source_html'))
        self.assertEqual(saved['source_depth'], depth)
        self.assertEqual(row['complete_reading_attempt']['status'], 'summarized' if complete else 'partial_summary')
        self.assertEqual(row['complete_reading_attempt']['next_at'], '2026-12-09' if complete else '2026-11-16')
        self.assertEqual(row['complete_reading_attempt']['provider_diagnostics'], diagnostics)
        self.assertEqual(document.coverage, coverage)
        self.assertEqual(document.units, units)
        self.assertNotIn(PROSE.strip(), json.dumps(row))
        for key in ('source_review', 'original_reading', 'approved'):
            self.assertNotIn(key, row)
        return row

    def test_pdf_page_coverage_is_not_guessed_from_url_or_kind(self):
        document = pdf_document()
        self.assertNotIn('document_format', document.coverage)
        for kind in reading.FIELDS:
            with self.subTest(kind=kind):
                row = self.process_document(document, kind, 'Whole PDF text retrieved.')
                self.assertEqual(row['deep_analysis']['coverage']['source_bytes_sha256'],
                                 sha256(document.source_bytes).hexdigest())

    def test_installed_pdf_reader_preserves_full_and_partial_format_labels(self):
        for blank_page in (False, True):
            document = parsed_pdf_document(blank_page)
            expected = PARTIAL if blank_page else 'Whole PDF text retrieved.'
            for kind in reading.FIELDS:
                with self.subTest(blank_page=blank_page, kind=kind):
                    self.process_document(document, kind, expected)

    def test_real_jats_and_tei_keep_pdf_equivalence_caveat(self):
        for format in ('jats', 'tei'):
            document = xml_document(format)
            for kind in reading.FIELDS:
                with self.subTest(format=format, kind=kind):
                    self.process_document(document, kind, XML_BASIS)

    def test_real_html_stays_partial_and_retains_existing_gates(self):
        document = html_document()
        self.assertEqual(document.coverage['evidence_status'], 'partial_full_text')
        self.assertEqual(document.coverage['html_completeness'], 'not_verified')
        for kind in reading.FIELDS:
            with self.subTest(kind=kind):
                self.process_document(document, kind, PARTIAL)

    def test_complete_html_fixture_is_not_mislabeled_as_pdf(self):
        # Test a retriever-supplied complete HTML result without upgrading the
        # real HTML parser's incomplete evidence or changing source approvals.
        for format in (None, 'html', 'xhtml'):
            document = html_document()
            document.coverage.update(evidence_status='full_document_retrieved',
                                     html_completeness='fixture_complete')
            if format:
                document.coverage['document_format'] = format
            for kind in reading.FIELDS:
                with self.subTest(format=format, kind=kind):
                    self.process_document(document, kind, 'All supplied article HTML text retrieved.')

    def test_explicit_and_unknown_formats_never_default_to_pdf(self):
        for format, expected in (
                ('pdf', 'Whole PDF text retrieved.'), ('xml', XML_BASIS),
                ('text', 'All supplied plain text retrieved.'),
                ('plain_text', 'All supplied plain text retrieved.'),
                ('txt', 'All supplied plain text retrieved.'),
                ('markdown', 'All supplied source text retrieved; document format is not verified.'),
                (None, 'All supplied source text retrieved; document format is not verified.')):
            coverage = {'evidence_status': 'full_document_retrieved'}
            if format:
                coverage['document_format'] = format
            document = access.Document([{'location': 'source:1', 'text': PROSE * 30}],
                                       record()['url'], VERSION, coverage)
            for kind in reading.FIELDS:
                with self.subTest(format=format, kind=kind):
                    self.process_document(document, kind, expected)

    def test_explicit_format_takes_precedence_over_legacy_page_metadata(self):
        document = pdf_document()
        document.coverage['document_format'] = 'text'
        self.process_document(document, 'scholarly', 'All supplied plain text retrieved.')

    def test_partial_format_never_claims_whole_source_or_replaces_full_reading(self):
        documents = [pdf_document(blank_page=True), html_document()]
        for format in ('jats', 'tei'):
            document = xml_document(format)
            document.coverage['evidence_status'] = 'partial_full_text'
            documents.append(document)
        documents.append(access.Document([{'location': 'source:1', 'text': PROSE * 30}],
            record()['url'], VERSION, {'evidence_status': 'partial_full_text', 'document_format': 'text'}))
        for kind in reading.FIELDS:
            previous = {'version': 2, 'source_depth': 'full_text' if kind == 'scholarly' else 'source_html',
                        'basis': 'Existing full source reading.'}
            for document in documents:
                with self.subTest(kind=kind, coverage=document.coverage):
                    row = self.process_document(document, kind, PARTIAL, previous=previous)
                    self.assertEqual(row['deep_analysis'], previous)
                    self.assertIn('partial_reading_candidate', row)


if __name__ == '__main__':
    unittest.main()
