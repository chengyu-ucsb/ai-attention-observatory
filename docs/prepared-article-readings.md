# Preparing source readings before the publication window closes

The early lane processes actual current-week candidates in
`data/weekly-preparation/<Monday>/`. It does not change the date to next Monday
or place open-week material in the current public issue. These files are
unpublished staging, not confidential storage: the repository is public. The
Pages build uses an explicit public-data allowlist and does not copy staging.
No full article text or document bytes are saved by this lane.

## Reused source and review machinery

- `collect_weekly_sources.run` and its ordinary CLI still require the previous
  completed UTC week. A separate validated preparation wrapper calls the same
  bounded retrieval engine with the actual open-week window.
- Exact article identities, publication evidence, source versions, rights,
  host restrictions and acquisition receipts stay bound. All provider/host
  cooldowns and saved denials are shared across normal and preparation runs,
  including spawned workers and summary retrievals.
- Completed unchanged acquisition receipts are not reset by another schedule.
  The reader re-fetches their exact source through ordinary guards before
  using it. Newly observed summary/revalidation denials are saved immediately,
  even if later model or source-validation steps fail.
- `comprehensive_readings.process` is reused with its chunk coverage, claim,
  numeric/copy and second-model checks. Its output remains
  `machine_checked_not_independently_reviewed`. Model failure, unavailable
  source and partial source coverage remain distinct. There is no new approval.

## Closed-week handoff

After Sunday ends, the metadata closeout must have actually run. Merely
changing a packet's phase or date is insufficient. Complete machine readings
are re-fetched and their source hash, URL, version and coverage must still
match. Changed or inaccessible sources are held, without changing public data.
A complete pass over partial text is not a full-document reading.

Only a current closed-week record selected by the canonical weekly payload can
receive an unchanged, revalidated machine analysis. Duplicate identities are
held. Existing independently reviewed readings and differing full-source
analyses are preserved. Approval fields, source bodies and packet-supplied
reading fields are stripped or rejected. The generated analysis, provenance,
claim and revalidation schemas are closed and checked before reuse and save.

An operational `publication_date_provenance.checked_at` refresh alone is not
a new article or source. Reuse requires the old record still reconstruct its
original acquisition fingerprint, all substantive identity and source-route
inputs to match, and the exact source receipt to remain unchanged. A changed
basis, date, URL, version, registry route or source hash invalidates reuse.
Final revalidation binds the new receipt and cannot be future-dated.

## Commands

Run only within the separately authorized repository workflow:

- `prepared_article_readings.py acquire --week YYYY-MM-DD --limit 12`
- `prepared_article_readings.py review --week YYYY-MM-DD --limit 2`
- `prepared_article_readings.py revalidate --week YYYY-MM-DD --limit 12`
- `prepared_article_readings.py apply --week YYYY-MM-DD`

`review` requires the existing runner-local model and never substitutes a fake
summary if it is missing. `apply` is a closed-week operation; it merges only
validated machine-reading fields into matching canonical records. Public
projection and editorial publication still use their existing independent
boundaries. Abstract-backed evidence remains explicitly labelled under the
existing editorial policy, never reported as a successful full-source review.

The publication scheduler must record actual stage results and distinguish
metadata candidates, full/partial retrieval, machine checks, source
revalidation and independent approval. A fast green job can be a skip; it is
not an end-to-end success. Model acceptance throughput and reliable hosted
Monday delivery remain to be measured after deployment.
