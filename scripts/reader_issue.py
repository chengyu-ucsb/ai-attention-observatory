"""Reader-facing projection shared by edition feeds, Pages data and release verification."""
from reading_headlines import reader_genre, reader_headline


def feed_snapshot(issue):
    """Structured copy for readers. Keep complete approval receipts in the archive."""
    fields = ('edition_date', 'number', 'status', 'edition_format', 'headline', 'subject',
              'deck', 'letter', 'closer', 'publication_window', 'scope_kind', 'source_count',
              'published_at', 'updated_at', 'first_published_date', 'feed_published_at', 'feed_id',
              'glossary', 'experiment')
    snapshot = {key: issue[key] for key in fields if key in issue}
    if 'edition_history' in issue:
        snapshot['edition_history'] = [
            {k: entry[k] for k in ('original_date', 'url') if k in entry}
            for entry in issue['edition_history']]
    def public_section(section):
        result = {k: section[k] for k in ('short', 'title', 'text', 'source_ids') if k in section}
        if 'citations' in section:
            result['citations'] = [{k: entry[k] for k in ('text', 'source_id', 'source', 'page') if k in entry}
                                   for entry in section['citations']]
        return result
    for key in ('signals', 'supplements'):
        if key in issue:
            snapshot[key] = [public_section(section) for section in issue[key]]
    if 'tension' in issue:
        snapshot['tension'] = public_section(issue['tension'])
    if 'sources' in issue:
        reference_fields = ('id', 'title', 'url', 'source_url', 'kind', 'research_type', 'venue',
                            'published', 'genre', 'attributed_to', 'reading_level', 'source_version',
                            'source_doi', 'related_journal_doi')
        snapshot['sources'] = [{**{k: src[k] for k in reference_fields if k in src},
                                'display_headline': reader_headline(src), 'reader_genre': reader_genre(src)}
                               for src in issue['sources']]
    return snapshot
