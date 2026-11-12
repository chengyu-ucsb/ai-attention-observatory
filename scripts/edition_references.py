"""Bound local-model references to supplied text before applying editorial gates.

Choosing a real passage prevents transcription errors; it does not establish
that the passage supports a claim. The normal fidelity review still applies.
"""
from __future__ import annotations

import re


def strict_object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def source_options(source, limit=20):
    """Offer short exact spans spread across findings, design and limitations."""
    if limit < 2:
        raise ValueError('At least two evidence options must be allowed')
    candidates, seen = [], set()
    for sentence in re.split(r'\n+|(?<=[.!?])\s+', source['evidence']):
        words = list(re.finditer(r'\w+', sentence))
        for start in range(0, len(words) - 4, 8):
            end = min(start + 10, len(words))
            quote = sentence[words[start].start():words[end - 1].end()]
            normalized = ' '.join(re.findall(r'\w+', quote.casefold()))
            if 5 <= len(normalized.split()) <= 12 and normalized not in seen:
                seen.add(normalized)
                candidates.append(quote)
    if not candidates:
        raise ValueError('Source has no usable evidence passages: ' + source['key'])
    if len(candidates) > limit:
        candidates = [candidates[round(i * (len(candidates) - 1) / (limit - 1))]
                      for i in range(limit)]
    return {f"{source['key']}-A{i:02d}": quote for i, quote in enumerate(candidates, 1)}


def with_evidence_options(sources):
    return [{**source, 'evidence_options': source_options(source)} for source in sources]


def section_response_schema(sources):
    return strict_object({
        'source_notes': strict_object({source['key']: {'type': 'string'} for source in sources}),
        'comparison': {'type': 'string'},
        'evidence': strict_object({source['key']: {'type': 'string', 'enum': list(source_options(source))}
                                   for source in sources}),
    })


def source_labels(sources):
    labels = {}
    for source in sources:
        authors = source.get('authors') or []
        labels[source['key']] = (authors[0] + (' and colleagues' if len(authors) > 1 else '')
                                 if authors and isinstance(authors[0], str) else source['title'])
    for source in sources:
        if list(labels.values()).count(labels[source['key']]) > 1:
            labels[source['key']] = source['title']
    return labels


def exact_keys(value, keys, label):
    if set(value) != set(keys):
        raise ValueError(label + ' must cover exactly the supplied sources or criteria')


def select(options, choice, label):
    if not isinstance(choice, str) or choice not in options:
        raise ValueError('Unknown ' + label + ': ' + str(choice))
    return options[choice]


def resolve_section_references(section, sources):
    """Resolve only explicit choices; never add a missing source or anchor.

    Existing array-shaped drafts remain subject to the original validators.
    """
    result = dict(section)
    keys = [source['key'] for source in sources]
    notes = result.get('source_notes')
    if notes is not None:
        if not isinstance(notes, dict) or 'text' in result or 'citations' in result:
            raise ValueError('Supply source_notes and comparison, without a separate text or citations field')
        exact_keys(notes, keys, 'Source notes')
        if any(not isinstance(note, str) or len(note.split()) < 30 for note in notes.values()):
            raise ValueError('Each supplied source needs its own substantive paragraph of at least 30 words')
        comparison = result.get('comparison')
        if not isinstance(comparison, str) or len(comparison.split()) < 25:
            raise ValueError('Explain the connection or open question in at least 25 words')
        labels = source_labels(sources)
        # The model explicitly assigns each paragraph to a required source key.
        # Render that assignment as a named link; never infer a missing citation
        # from the prose or invent a missing source's contribution.
        result['text'] = '\n\n'.join(labels[key] + ': ' + notes[key].strip() for key in keys)
        result['text'] += '\n\n' + comparison.strip()
        # Link the explicit paragraph label, including its delimiter. Repeated
        # author names elsewhere in the prose are not duplicate citation links.
        result['citations'] = [{'key': key, 'text': labels[key] + ':'} for key in keys]
        result.pop('source_notes'); result.pop('comparison')
    citations = result.get('citations')
    if isinstance(citations, dict):
        exact_keys(citations, keys, 'Citations')
        if any(not isinstance(text, str) for text in citations.values()):
            raise ValueError('Citation phrases must be strings')
        result['citations'] = [{'key': key, 'text': citations[key]} for key in keys]
    anchors = result.get('evidence')
    if isinstance(anchors, dict):
        exact_keys(anchors, keys, 'Evidence')
        result['evidence'] = [
            {'key': source['key'], 'quote': select(source_options(source), anchors[source['key']],
                                                  'evidence option for ' + source['key'])}
            for source in sources]
    return result


def draft_passages(draft):
    sections = draft.get('signals', []) + [draft.get('tension', {})]
    fields = [draft.get(key, '') for key in ('headline', 'deck', 'letter', 'closer')]
    fields += [section.get(key, '') for section in sections for key in ('title', 'text')]
    passages = list(dict.fromkeys(
        sentence.strip() for field in fields
        for sentence in re.split(r'\n+|(?<=[.!?])\s+', field)
        if len(sentence.strip()) >= 12))
    return {f'D{i:03d}': passage for i, passage in enumerate(passages, 1)}


def cited_sources(draft, packet):
    keys = {anchor['key'] for section in draft['signals'] + [draft['tension']]
            for anchor in section['evidence']}
    sources = [source for source in packet if source['key'] in keys]
    if {source['key'] for source in sources} != keys:
        raise ValueError('Draft cites unknown sources')
    return sources


def review_response_schema(draft, packet, criteria):
    passages = list(draft_passages(draft))
    return strict_object({
        'decision': {'type': 'string', 'enum': ['pass', 'revise']},
        'checks': strict_object({criterion: strict_object({
            'pass': {'type': 'boolean'}, 'reason': {'type': 'string'},
            'example_id': {'type': 'string', 'enum': passages},
        }) for criterion in criteria}),
        'source_checks': strict_object({source['key']: strict_object({
            'anchor_id': {'type': 'string', 'enum': list(source_options(source))},
            'claim_id': {'type': 'string', 'enum': passages},
            'supported': {'type': 'boolean'},
        }) for source in cited_sources(draft, packet)}),
        'issues': {'type': 'array', 'items': {'type': 'string'}},
    })


def resolve_review_references(review, draft, packet, criteria):
    result = dict(review)
    passages = draft_passages(draft)
    checks = result.get('checks')
    if isinstance(checks, dict):
        exact_keys(checks, criteria, 'Review checks')
        result['checks'] = [{
            'criterion': criterion, 'pass': checks[criterion]['pass'],
            'reason': checks[criterion]['reason'],
            'example': select(passages, checks[criterion]['example_id'], 'draft passage'),
        } for criterion in criteria]
    checks = result.get('source_checks')
    if isinstance(checks, dict):
        sources = cited_sources(draft, packet)
        exact_keys(checks, [source['key'] for source in sources], 'Source checks')
        result['source_checks'] = [{
            'key': source['key'],
            'quote': select(source_options(source), checks[source['key']]['anchor_id'],
                            'evidence option for ' + source['key']),
            'claim': select(passages, checks[source['key']]['claim_id'], 'draft claim'),
            'supported': checks[source['key']]['supported'],
        } for source in sources]
    return result


def frame_response_schema(sources):
    prose = {'type':'string', 'pattern':'^[^0-9]*$'}
    keys = [p['key'] for p in sources]
    return strict_object({
        'headline': prose, 'deck': prose, 'letter': prose,
        'tension': strict_object({'title':prose, 'text':{'type':'string'},
            'citations':{'type':'array', 'minItems':1, 'maxItems':len(keys),
                'items':strict_object({'key':{'type':'string','enum':keys},
                                       'text':{'type':'string','enum':keys}})}}),
        'closer':prose,
        'glossary':{'type':'array', 'maxItems':5,
                    'items':strict_object({'term':prose,'definition':prose})},
    })


def resolve_frame_references(frame, sources):
    """Expand explicitly cited keys only; never infer attribution from prose."""
    from copy import deepcopy
    result = deepcopy(frame)
    tension = result.get('tension', {})
    labels = source_labels(sources)
    text = tension.get('text', '')
    selected = {}
    for citation in tension.get('citations', []):
        phrase, key = citation.get('text'), citation.get('key')
        if re.fullmatch(r'S\d+', str(phrase)):
            if phrase != key or key not in labels or key in selected:
                raise ValueError('Invalid explicit frame source key')
            if len(re.findall(r'\b' + re.escape(key) + r'\b', text)) != 1:
                raise ValueError('Frame source key must occur exactly once')
            selected[key] = labels[key]
            citation['text'] = labels[key]
    unknown = set(re.findall(r'\bS\d+\b', text)) - selected.keys()
    if unknown:
        raise ValueError('Unknown or uncited frame source key')
    tension['text'] = re.sub(r'\bS\d+\b', lambda m: selected[m.group()], text)
    return result
