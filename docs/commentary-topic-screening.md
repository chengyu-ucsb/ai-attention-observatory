# Commentary topic screening

The article's central argument must concern a specific human use of AI or a
mechanism of human attention. A feed category, a topical headline, an incidental
example, or an editor's proposed application does not establish this connection.

`scripts/news_quality.py::commentary_topic` checks the approved original
reading's thesis, falling back to the source-reviewed longform thesis. The public
projection and the edition evidence packet both run this check. Product guides
and linked research explainers may also use their checked overview.

- **Direct:** the argument identifies AI and a human practice, choice, or attention
  mechanism. When the headline names AI but the argument uses a narrower alias,
  such as an automated agent, both must be present.
- **Adjacent:** the argument identifies a human attention mechanism, but does not
  establish AI's role in it. An AI headline alone cannot change this label.
- **Held:** no qualifying central connection is established. Technical attention
  architectures, figurative uses of attention, and model-only evaluations do not
  establish human attention relevance.

These checks are conservative triage, not semantic proof. Source review remains
necessary. A source-specific decision in `data/editorial-topic-decisions.json`
records its locator and rationale and is valid only for the checked source hash.
Novel terminology can receive a documented review rather than weakening the
general gate to match unrelated material.

## November 18, 2026 audit

The internal index contained 914 records, including 32 nonacademic records.
Applying the retained source reviews produced 16 nonacademic readings with
sufficient article analysis or documentation. Of those, 11 passed as direct AI
readings (including one companion explainer) and four as adjacent product guides.
The remaining source-ready article, EFF's family safety plan, was excluded because
its central recommendation concerns general privacy and safety. The other 16
nonacademic records still lacked an accepted substantive reading and remained
outside the public collection.

This audit examined the stored source-reviewed arguments and their publication
eligibility; it was not a fresh independent rereading of every original article.
The November 16 correction passed a fresh public projection with all 13 checked
sources, preserving its publication dates and reading/copy fingerprints.

`tests/test_commentary_quality.py` covers the real EFF exclusion, stale edition
input, all correction additions, incidental examples, unrelated AI headlines,
technical meanings of attention, human practice and consent, and legitimate
adjacent attention material. Run it together with the public projection and
edition citation checks after changing topic rules.
