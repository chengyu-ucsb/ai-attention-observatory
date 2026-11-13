# Monday editions

An Observatory edition belongs to one Monday. Its identity does not depend on the day a worker finishes, a retry runs, or an editor revises the text. The website remains the authority for the edition, source shelf, permanent link, archive, and feeds.

## The calendar contract

For normal weekly editions, discovery covers the previous complete **Monday–Sunday UTC** publication week. The edition date is the Monday immediately after that source window. For example, sources originally published November 2–8 belong to the **November 9 edition**, including when review finishes on November 13.

`edition_schedule.py` calculates this Monday from the explicit source window, or from the completed week associated with a run date. Do not select an edition date from the newest archive filename or the current wall-clock date. Keep the source-publication window distinct from the edition label and the time processing happened.

| Field or identifier | Meaning |
| --- | --- |
| `edition_date` | Fixed Monday identity and canonical `/issues/YYYY-MM-DD.html` address |
| `publication_window` | Original source-publication dates, not retrieval or review dates |
| `first_published_date` / `published_at` | When the edition actually became available; never manufacture a Monday release time for late work |
| `updated_at` | A later editorial or consolidation update; it does not create another issue |
| `feed_id` | Stable subscriber identity, retained when an older edition receives its Monday address |
| `feed_published_at` | Preserved feed publication timestamp where supplied |

Historical feeds already used a date-at-noon timestamp. Retaining that value preserves feed behavior; it is not a newly verified exact publication time. The original release date and immutable original snapshot remain available separately.

The publication target is **Monday at 12:05 p.m. America/New_York**. Full synthesis can publish during Monday, starting at midnight Eastern; the UTC source-week rollover on Sunday evening does not open the release window early. A separate deadline job can publish a clearly labeled coverage update when a full synthesis has not passed review. A later approved synthesis upgrades the same Monday edition and link. Scheduled infrastructure can be delayed, and successful full synthesis is not guaranteed by the deadline; neither delay changes the edition's identity. Keep the free-service limits and bounded retry policy.

## Consolidated launch archive

The first releases mixed collection digests with strict weekly editions. The November 13 consolidation assigns one Monday per edition without pretending that older background material was newly published.

| Monday edition | Retained content | Source scope |
| --- | --- | --- |
| October 19, 2026 | Original October 18 opening collection | 28 sources; historical collection |
| October 26, 2026 | Original October 26 collection, plus useful additional analysis from the earlier November 2 issue | 18 sources; historical collection |
| November 2, 2026 | Source-checked edition originally released November 7 | Five sources published October 26–November 1 |
| November 9, 2026 | Edition originally released November 13 | Eight sources published November 2–8 |

All eight sources in the earlier November 2 issue were already in the October 26 collection. Its distinct, supportable discussion of readiness, trust, and technology-related strain is consolidated there. The clearer existing October 26 analysis remains intact. Older causal or performance wording is not simply copied into the merged account.

The first two editions are marked `scope_kind: legacy_collection`. Do not assign them a strict previous-week source window: their materials include earlier publications. The two normal weekly editions retain their verified publication windows. Consolidation reduces repeated source references without discarding unique source IDs; it does not claim that every differently identified historical link represents a distinct article.

## Links, history, and feeds

`data/edition-lineage.json` records the calendar correction, old-to-new relationships, and SHA-256 hashes of original snapshots. `data/edition-revisions/` retains the original JSON bytes, including the pre-consolidation editorial source. These are immutable historical evidence, not a second active edition catalog.

Retired October 18, November 7, and November 13 page links lead to their Monday editions. Original versions remain accessible under `/issues/history/` through the edition's history disclosure. The existing `/issues/2026-11-02.html` address is the canonical November 2 edition; its earlier collection content is retained in history and incorporated into October 26. It cannot also redirect to October 26 without colliding with the canonical week.

The archive and feeds list one active item per Monday. Retain existing feed identities for the surviving editions, while item URLs point to their canonical Monday pages. A revision updates the existing item; it should not create a second notification identity. RSS readers control their own notification behavior, so this is a deduplication contract, not a guarantee about every reader.

## Maintenance rules

- Use the shared edition-date helper for drafting, coverage publication, retries, and upgrades. An explicit source window determines its Monday even when processing resumes later.
- Preserve research text, source provenance, and source-date qualifications when changing calendar metadata. Consolidating content requires explicit source-linked decisions.
- Keep original release and revision information separate from the Monday label. A Friday completion must not claim it was published the previous Monday.
- Keep one active canonical file per Monday, and keep original versions in revision history rather than listing them as extra weekly editions.
- Never replace an existing immutable revision with different bytes. Run the one-time migration idempotently; a repeated run must not rename editions or refresh timestamps.
- Preserve stable feed IDs and canonical URLs across retries and later revisions. Check old links, archive counts, RSS/JSON identities, and both strict and legacy source scopes.
- Run the edition scheduling, consolidation, newsletter, and publication tests. Verify the completed deployment and live archive/feed output before reporting publication success.

The design uses the existing static website, scheduled workflows, and free infrastructure. It does not add paid services or change the site's opt-in/email-delivery status.
