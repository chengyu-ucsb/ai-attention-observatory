# Concise reading headings

Public reading headings use at most 55 characters and ten words. Prefer a specific short phrase or question, usually four to eight words. The public
builder calls `reading_headlines.headline_decision` after source and reading-depth
checks. The policy accepts, in order:

1. A source-checked entry in `data/reading-headlines.json`, keyed by DOI or the
   canonical source URL.
2. The complete original publication title when it already fits.
3. The complete main idea from an accepted original summary whose source-review
   and publication receipts remain valid.

Statistical fragments, clipped text and raw automatic digest sentences cannot
supply headings. The full bibliographic title remains unchanged and appears in
the article's Source panel. Cached display headings are not review receipts.

If none of these options is available, hold only that source and place its ID,
title and original URL in `data/headline-review-queue.json`. Continue publishing other
eligible readings. A later source review can add a concise topic, question or
qualified finding to the registry, then rebuild the public collection. Do not
shorten a claim by cutting off its qualification merely to meet the limit.
A verified companion with a pending headline retains a short source link on its
parent article while its title is in review.

The app, weekly source shelves, archives and feeds use these same display
headings. The register includes source IDs for older editions whose articles
have since left the reading collection. Preserve original publication titles
when citing the work.

`reader_genre` describes the item itself. Source-linked overrides in
`data/reading-genres.json` distinguish journal opinions and editorials from
studies, reviews and conceptual papers and preserve checked genres in older
editions. News coverage of a paper remains reporting. Attach its original
paper by verified source lineage. Vendor documentation is a product guide.
New sources use publisher or checked reading metadata, never the study
described in a news headline.

This gate prevents a new long title from silently returning to the public cards.
It does not itself establish that an edited heading accurately describes its
source; that remains part of source review, including review of changed versions.

`tests/test_reading_headlines.py` checks the current public corpus, unknown future
records, invalid headings, revoked summary receipts and preservation of the
original title. Run it with public-projection and article-UI checks after changes.
