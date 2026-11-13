"""One-time, reversible consolidation of the launch archive into Monday editions.

Original snapshots remain byte-for-byte in edition-revisions. This is an explicit
calendar/content correction, not a routine rewrite of published research.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://chengyu-ucsb.github.io/ai-attention-observatory/issues/'
MAPPING = {'2026-10-18': '2026-10-19', '2026-10-26': '2026-10-26',
           '2026-11-02': '2026-10-26', '2026-11-07': '2026-11-02',
           '2026-11-13': '2026-11-09'}


def supplement():
    ids = ['10.3390/educsci16081291', '10.1016/j.chbr.2026.101340',
           '10.3389/fpsyg.2026.1974520', '10.3389/fpsyg.2026.1955418']
    labels = ['The staged-use essay', 'The higher-education study',
              'The theory-building review', 'the technostress survey']
    return {
        'title': 'When and how to rely on AI',
        'text': 'The staged-use essay proposes introducing substantive AI assistance after learners demonstrate readiness. Our reading is abstract-based: this is an instructional proposal, not a test showing that a particular sequence improves learning.\n\n'
                'The higher-education study examines course work and students’ accounts of AI use. Its authors interpret the pattern as gradual normalization alongside continuing concerns about authentic learning. The study used naturally occurring data without experimental control, so this does not show that normalization caused better outcomes.\n\n'
                'The theory-building review organizes evidence around learners monitoring their work, deciding when to trust AI, and sharing responsibility for regulation. Its varied studies and single-author synthesis limit common conclusions. Separately, the technostress survey links greater reported AI-related strain with lower engagement and adaptability. Its cross-sectional, self-report design cannot establish cause and effect.\n\n'
                'These readings sharpen three questions to test: when assistance becomes available, how learners evaluate it, and how demanding it feels.',
        'source_ids': ids,
        'citations': [{'text': label, 'source_id': ident} for label, ident in zip(labels, ids)],
        'consolidation_note': 'Consolidated from the earlier November 2 collection and checked against stored source notes. No new original-paper review is claimed.'}


def migrate(root=ROOT, now=None):
    root = Path(root)
    data = root / 'data'
    registry = data / 'edition-lineage.json'
    if registry.exists():
        return {'changed': False, 'status': 'already_consolidated'}
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    approved = data / 'approved-issues'
    originals = {day: (approved / (day + '.json')).read_bytes() for day in MAPPING}
    issues = {day: json.loads(raw) for day, raw in originals.items()}
    earlier_ids = {s['id'] for s in issues['2026-10-26']['sources']}
    assert {s['id'] for s in issues['2026-11-02']['sources']} <= earlier_ids
    revisions = data / 'edition-revisions'
    revisions.mkdir(exist_ok=True)
    for day, raw in originals.items():
        dest = revisions / (day + '.json')
        if dest.exists() and dest.read_bytes() != raw:
            raise ValueError('An immutable revision already differs: ' + day)
        dest.write_bytes(raw)
    raw_drafts = (data / 'issue-editorial.json').read_bytes()
    draft_revision = revisions / 'issue-editorial-before-consolidation.json'
    if draft_revision.exists() and draft_revision.read_bytes() != raw_drafts:
        raise ValueError('An immutable editorial revision already differs')
    draft_revision.write_bytes(raw_drafts)
    drafts = json.loads(raw_drafts)
    canonical = {}
    new_drafts = {}
    bases = [('2026-10-19', '2026-10-18'), ('2026-10-26', '2026-10-26'),
             ('2026-11-02', '2026-11-07'), ('2026-11-09', '2026-11-13')]
    for number, (day, original) in enumerate(bases, 1):
        issue = deepcopy(issues[original])
        issue.update(edition_date=day, number=f'{number:02d}',
                     first_published_date=original, updated_at=stamp,
                     feed_id=BASE + original + '.html',
                     feed_published_at=original + 'T12:00:00+00:00')
        issue['subject'] = re.sub(r'#\d+', '#' + issue['number'], issue['subject'])
        related = [old for old, target in MAPPING.items() if target == day]
        issue['edition_history'] = [{'original_date': old, 'url': 'history/' + old + '.html',
                                    'note': 'Original published version; consolidated into this Monday edition.'}
                                   for old in related]
        if day == '2026-11-02':
            issue['edition_history'].append({'original_date': '2026-11-02',
                'url': 'history/2026-11-02.html',
                'note': 'Earlier contents of this address used older material, now consolidated into the October 26 collection.'})
        if day in ('2026-10-19', '2026-10-26'):
            issue['scope_kind'] = 'legacy_collection'
        if day == '2026-10-19':
            for key in ('deck', 'letter', 'editorial_note'):
                issue[key] = issue[key].replace("this week's", 'the opening collection’s').replace("This week's reading set", 'This opening reading set').replace('weekly reading set', 'opening reading collection')
            for signal in issue['signals']:
                signal['text'] = signal['text'].replace("This week's material", 'The opening collection')
        if day == '2026-10-26':
            issue['supplements'] = [supplement()]
        canonical[day] = issue
        draft = deepcopy(drafts[original])
        for key in ('number', 'subject', 'deck', 'letter', 'editorial_note', 'supplements'):
            if key in issue:
                draft[key] = deepcopy(issue[key])
        if day == '2026-10-19':
            draft['signals'] = deepcopy(issue['signals'])
        new_drafts[day] = draft
    from build_issue import validate_issue_citations
    for issue in canonical.values():
        validate_issue_citations(issue)
    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    for day, issue in canonical.items():
        save(approved / (day + '.json'), issue)
    for day in set(MAPPING) - set(canonical):
        (approved / (day + '.json')).unlink()
    save(data / 'issue-editorial.json', new_drafts)
    save(registry, {'schema_version': 1, 'consolidated_at': stamp,
        'calendar': {'edition_day': 'Monday', 'release_timezone': 'America/New_York',
                     'target': '12:05', 'source_window_timezone': 'UTC'},
        'aliases': {old: new for old, new in MAPPING.items() if old != new and old not in canonical},
        'revisions': {old: {'canonical_date': new,
                           'sha256': sha256(originals[old]).hexdigest(),
                           'note': ('Older collection material was incorporated into October 26; the November 2 edition now covers October 26–November 1.'
                                    if old == '2026-11-02' else 'The edition is filed under its fixed Monday date.')}
                      for old, new in MAPPING.items()}})
    return {'changed': True, 'editions': list(canonical), 'retained_revisions': len(originals)}


if __name__ == '__main__':
    print(json.dumps(migrate()))
