# Weekly research coverage

The website owns the edition. Rolling APIs and RSS are discovery inputs, not a
complete research process. Scheduled research sessions supplement them on
Wednesday, Friday and Sunday at 6 p.m. Eastern; Monday supervision checks the
remaining gaps before the noon release. Read `release-schedule.md` as well.

## Window and scope

Each Monday edition covers original publications from the preceding Monday
through Sunday, inclusive, in UTC. For November 16, that means November 9–15.
November 16 publications belong to November 23. During the week, search only
through the current date and save work in the existing preparation namespace.
Never infer publication day from indexing, modified timestamps or a search
engine's relative-date label. Explicitly resolve missing dates at the publisher.

Start with the question of how technology shapes what people notice, sustain,
miss or return to. AI and cognition, fragmentation, interventions, and technology
and society are starting points. Follow observations in education, work, media
and everyday life wherever relevant evidence leads. Keep a source that crosses
themes or raises a different question. Name an emerging topic in the record or
leave its theme open until the reading supports a more specific label.

## Complementary searches

1. Inspect the actual academic query matrix, provider completion and deferred
   cursors. Supplement registry queries with publisher and preprint searches.
   Search simple alternatives separately, such as AI + learning, ChatGPT +
   memory, AI + deskilling, AI + work intensity, AI + interruptions, chatbot +
   autonomy. Also run a broad search, then use unfamiliar vocabulary in titles
   and abstracts for a follow-up. Trace references and related reporting.
   Record the search and what it added. Give a nominated lead an apt theme
   label, or omit the lane to queue it under Emerging topics.
2. Run independent date-bounded web searches, then outlet-specific searches.
   Include general news (Guardian, BBC, Reuters, AP, NPR), technology reporting
   (MIT Technology Review, Wired, Ars Technica, Verge, 404 Media), education
   reporting (Education Week, Inside Higher Ed, EdSurge, Chalkbeat, Hechinger
   Report), and policy/analysis (Conversation, Tech Policy Press, Brookings,
   EFF). This is a search checklist, not a claim every outlet has a working feed
   or accessible article. Add other relevant outlets found through searching.
3. Open canonical articles and verify original date, genre and the central claim.
   Identify the specific decision, activity or human attention outcome at stake.
   A passing example of notifications, a publisher label or a technology topic
   does not establish relevance.
   Follow reported studies to original papers/reports and retain explicit
   source lineage. Do not double-count the paper and its news explanation.
4. Resolve relevant pending sources while time remains. Distinguish failed
   discovery, missing dates, access blocks, partial extraction, unread full
   text and failed synthesis. A machine HTTP failure does not prove the
   article cannot be read through another permitted source. Preserve access
   restrictions and free-provider budgets; do not bypass paywalls or fabricate
   readings. Abstract-based evidence must remain clearly labeled.

## Audit trail and completion

Save an original, concise research log in this repository under
`data/research-audits/<edition-date>.json`, using the November 16 audit as an
example. Record queries actually executed, observed dates, canonical URLs,
whether each candidate was already indexed, inclusion/exclusion reasons and
remaining work. Do not copy full articles. Search hits are leads until checked.
Merge successive sessions into that edition's log, not separate unsynced files.

Use the existing scholarly brief intake and manual source-checked editorial
paths to incorporate verified discoveries into the preparation packet and
readings. Adding a lead to the audit is not publication or completed reading.
Verify the saved remote commit and, when publishing, the real website/feeds.

Before calling the research ready, inspect both academic and nonacademic
streams. Review the open search, emerging questions and cross-theme sources.
Build issue themes around findings and disagreements in the material read that
week. Explain a sparse stream using searches actually
performed and candidate outcomes. A large metadata count, a green RSS run or a
two-source synthesis does not establish sufficient coverage. Neither impose a
quota of weak material nor claim there were few publications because retrieval
failed. A short edition remains a contingency with disclosed coverage gaps.

At the Sunday audit, prioritize unresolved relevant articles and draft from
reviewed material. Monday's 7 a.m. compact option preserves the release deadline;
it does not excuse omitting the earlier research. Carry genuine late-indexed
discoveries into a dated revision of the same issue after verification.


## Repairing existing reading pages

Each public build records the actual basis of scholarly findings and flags open
links with abstract-only readings, abstract findings on partially extracted
articles, and uncategorized papers without a finding in
`data/source-quality-audit.json`. Check those records against the original
body and distinguish an unreported result, a conceptual article, a published
conference abstract, and a failed retrieval. Revisit the oldest eligible gaps
during ordinary research sessions. The scheduled historical reader reserves
one place in each multi-paper batch for a public gap and keeps its existing
retry and source checks. A public URL alone cannot certify that a particular
finding came from the full paper.
