# Contextual article illustrations

Every separately published Observatory reading, including companion and manually added articles, needs its own reviewed original illustration. A build first screens the source and written reading. It then puts each otherwise eligible canonical article without approved art in a commissioning queue. An item can enter the current library, article pages and current-week list only after both checks pass. Frozen edition citations continue to point to their published sources.

## Preparing artwork for new readings

Read the checked article notes and choose a particular action, object or setting a reader would recognize from the article. A student turning an exam card beside a timer fits a reading about starting and completing practice sessions. Use OpenAI image generation for a fresh composition with a clear focal point, a considered color palette and enough space for its subject to remain readable at mobile sizes. Treat the illustration as editorial art. Use separately verified factual displays for measured results.

Export the approved composition as a 1200 × 800 WebP cover and a 320 × 213 WebP thumbnail. Save both in `assets/editorial-covers/`. Register the canonical article ID, paths, actual dimensions, descriptive alt text, concept and OpenAI creation provenance in `data/article-art-overrides.json`. Use fresh filenames for replacements so the last approved pair remains available. Inspect both images alongside neighboring covers at full size and at card size. After checking the source match, composition and thumbnail, run the following, substituting the actual ID. The sign-off command uses Pillow to decode both files and compare their composition.

```sh
python scripts/article_art_queue.py --approve-reviewed 'doi:10.1234/example'
python scripts/build_public.py
```

The command records `commission_review` in the manifest. It binds the article ID, both files, their paths, alt text, concept and provenance to the review. Re-run the check after any of those inputs changes. Pure text corrections to the article keep its already reviewed cover. Build and review the change through the normal publication route.

## Publication and commissioning

`data/article-art-state.json` contains the current approved receipt by canonical ID and the `commissioning.pending` mapping of IDs to reason codes. A fresh build derives the queue from all otherwise eligible source records, including companions. Articles with a missing original, invalid file, missing or wrong-size thumbnail, unreviewed edit, missing generation provenance, or a rejected duplicate wait here. The website exports only the pending IDs in `data/art-commissions.json`. The artist can look up source evidence by ID in the repository's screened inputs. The public endpoint is also refreshed by a Pages-only rebuild.

Source screening still determines whether an article may be considered at all. Past art receipts cannot restore ineligible readings. A previously published, eligible reading can serve its previous signed cover while a proposed replacement awaits review. If that pair was removed or corrupted too, restore it or provide a fully reviewed replacement before deploying a new build. Unrelated valid additions can publish while new commissions wait. A normal build uses no image-service credentials.

## Procedural artwork tools

The standalone artwork allocator can still evaluate source-based sketches for editorial development. Its candidate status describes a sketch; a generated SVG or a generic `ready` flag cannot satisfy the public commission gate.

Review reasons include:

- `insufficient_specific_context`: fewer than two grounded subjects are available.
- `duplicate_semantic_concept`: an accepted article already uses the concept signature.
- `duplicate_foreground_subjects`: the same dominant subject pair is already used, even if reordered or given a different frame.
- `duplicate_foreground_geometry`: the actual foreground pair repeats, including equivalent glyphs with different subject names.
- `duplicate_composition`: actual generated SVG composition bytes match.
- `duplicate_asset_bytes` or `duplicate_thumbnail_bytes`: actual validated asset bytes match another accepted article, including renamed files.
- `near_visual_twin`: a generated scene is too similar under the conservative coarse visual screen, despite having different labels or bytes.
- `visual_similarity_unavailable`: the generated SVG cannot be assessed by the supported coarse renderer. It is held rather than bypassing the check.

Collision metadata identifies the accepted article responsible for each conflict. The same canonical paper can appear in multiple projections without being treated as a different article. An unchanged, already accepted `editorial_art` allocation supplied in the input keeps priority, including a previously accepted alternative. When no current allocation is supplied, canonical identity order determines acceptance, independent of input order. The publication build hydrates these allocations from the separate artwork state file.

## Bounded replacement attempts

The procedural allocator tries the preferred concept first. If it collides with an accepted cover, it can try up to five further concepts, for **at most six candidates per article**. Alternatives use different subject pairs explicitly supported by the article's title or substantive source context. Every candidate must pass the same context, semantic, geometry, byte and visual-similarity checks. A new color, rotation, filename or tiny decoration is not a new concept.

A successful alternative produces a source-grounded sketch. If all supported alternatives fail, an editor can return to the checked article for a new concept. A curated illustration rejected for duplication is held for editorial review rather than silently replaced with procedural art. Missing context cannot be repaired by inventing a setting or a finding.

`data/article-art-state.json` retains accepted allocations and unresolved attempts using identifiers, fingerprints and bounded attempt metadata, without copying source prose. An accepted alternative is revalidated and kept on later builds. An exhausted unchanged candidate pool and collection are not retried indefinitely or reported as new progress. Changes to source context, the rendering/candidate policy, overrides or the admitted collection allow reconsideration. Removed or no-longer-eligible articles are pruned from this state; state cannot admit a paper for publication.

The existing refresh, full-text backfill, discovery-resume and weekly-edition workflows commit this state with their other data outputs. The read-only publication workflow also archives its exact state for 90 days as an Actions artifact; it does not commit that artifact back or automatically restore artifacts into future builds. The full state stays outside the website's public data. The Pages export contains a separate ID-only commissioning list.

## Context and geometry

The renderer selects a theme and two concrete subjects from source-related editorial text. `source_grounding` retains the matched phrase and the input field that licensed each subject. `visual_subjects` records the visible pair. Generic tags alone cannot qualify an image as contextual. A broad fallback theme may still be described in review metadata, but it is not rendered as a generic fallback image.

The two source-grounded subjects dominate the illustration. A primary metaphor relates them through a crane, lens, mirror, threshold, shared table or another conceptual frame. Subjects include settings and tasks such as doctoral work, undergraduate mathematics, programming, language instruction, clinical work, music, governance, phones and writing. These are editorial metaphors, never representations of measured study results. Numerical findings do not choose shapes, proportions, quantities or effect directions.

Identity hashes no longer change the scene, colors, rotation or small marks. Identical concepts produce identical geometry instead of an artificially unique image. The acceptance guard checks the semantic signature, the unordered dominant noun pair, the actual foreground glyph pair at canonical coordinates, and the full generated composition independently. It writes generated files only for accepted candidates.

`scripts/art_similarity.py` adds a dependency-free coarse raster screen for generated SVGs. It approximates the renderer's closed vector vocabulary on an 80 × 50 RGB grid, stores a compact signature, and checks every candidate against accepted generated scenes. Near-twin decisions combine full-scene color difference, color difference over the foreground union, and foreground overlap. Tiny extra marks cannot count as a new illustration merely because the SVG bytes change. The report records the method, thresholds and suspect pair scores.

These checks do **not** establish perceptual pixel uniqueness. The coarse renderer approximates curves, strokes and rasterization; it is not the browser's rendering engine. Different scenes can still look similar at card size. Curated raster overrides receive the byte-level checks, not this SVG approximation; different raster encodings can contain the same pixels. A successful automated report means the stated automated checks passed, not that a person has reviewed every cover.

Generated SVGs use a closed vocabulary of paths, groups, circles and rectangles with no embedded text, script, fonts, external references or source figures. The hard per-file limit is 32 KB. The build creates `assets/article-art/` when it writes procedural covers. Pages stages each available cover directory and checks the published cover and thumbnail paths. A collection made entirely from curated covers needs only `assets/editorial-covers/`.

## Determinism and caching

DOIs are case-normalized, including DOI URLs. Source URLs retain meaningful query parameters and case-sensitive paths but omit tracking parameters and fragments. A title hash is the explicit last-resort identity.

Filenames contain identity and rendered-content hashes, never raw identifiers or titles. Input fingerprints include canonical identity, public editorial input and renderer version. A digest revision updates the input fingerprint. If the drawing has not changed, its content-addressed asset stays unchanged; adding a reported finding must not invent a different image. Dates, citation counts and unrelated acquisition metadata do not churn art. The renderer uses no timestamps and does not rewrite unchanged files.

Increment `RENDERER_VERSION` when changing the design contract. Old generated assets are not deleted automatically, so an older payload remains usable during deployment transitions. Curated assets live separately and are never pruned by the renderer.

## Curated overrides

For individually reviewed original artwork, create `data/article-art-overrides.json`:

```json
{
  "version": 1,
  "overrides": {
    "doi:10.1234/example": {
      "src": "assets/editorial-covers/example.webp",
      "thumbnail_src": "assets/editorial-covers/example-320.webp",
      "width": 1200,
      "height": 800,
      "alt": "A hand rebuilding a bridge beside a closed screen.",
      "concept": "Reconstructing a skill after assistance is removed.",
      "provenance": "Original editorial illustration created with OpenAI image generation."
    }
  }
}
```

Public commissions require both WebPs, alt text, concept, generation provenance and the receipt created after visual review. Keys use canonical `doi:`, `url:` or title-hash identity. Any declared dimensions must match the actual files.

Overrides are explicitly editor-declared concepts, not automatically verified source interpretations. Their metadata preserves the declared concept and provenance rather than claiming that a procedural noun pair produced their pixels. A valid override can supply specific art when keyword matching is insufficient. Different original overrides are not rejected merely because their articles would have selected the same procedural pair.

Paths must be flat lowercase letters, digits and hyphens under `assets/editorial-covers/` or `assets/article-art/`, ending in `.webp`, `.png` or `.jpg`. URLs, traversal, nested folders, SVG overrides and external symlinks are forbidden. Assets must exist, have supported raster headers and fit the 2 MB limit. The loader calculates hashes from actual bytes, including thumbnails. Reusing a path or renaming identical bytes cannot bypass the collection collision gate. The publication gate queues an invalid individual registration and continues with other articles. A malformed manifest as a whole must be repaired before rebuilding.

Use only original or appropriately licensed artwork. A provenance declaration is not proof of permission and grants no rights to publisher figures or copyrighted research content.

## Audit and tests

Review an already-public collection without rewriting it or running acquisition:

```sh
python scripts/article_art.py --report /tmp/article-art-report.json \
  --contact-sheet /tmp/article-art-contact.html
python -m unittest discover -s tests -p test_article_art.py -v
```

The standalone command rechecks publication eligibility and refuses an internal `library.json` input. `--root` selects another checkout. The contact sheet shows accepted images and explicit review notices without broken image tags. The report lists ready/review counts, reasons, source-grounding phrases, collision groups and accepted asset bytes. `distinct_generated_compositions` counts accepted generated compositions; collision groups also retain held candidates so rejection is visible rather than hidden by a success counter.

Tests cover real public records, realistic repeated research concepts, repeated foreground pairs with different frames, independent geometry checks, tiny-decoration visual twins, changed dominant scenes, unsupported coarse-renderer handling, insufficient context, renamed identical rasters, repeated thumbnails, canonical-paper reuse, stable ordering, retained acceptance, content-addressed caching, safe SVG/path handling and honest review reports. Publication tests exercise a pending article through approval, weekly inclusion, replacement and source quarantine. Run `python -m unittest discover -s tests -p test_art_similarity.py -v` for the coarse rasterizer's own geometry and metric tests.

### Source tables and figure candidates

An audit on November 18, 2026 found 45 figure-caption entries across 19 indexed
articles, but no verified image URLs in those records. A caption alone cannot
be displayed as a source image or used to reconstruct statistical geometry.

`data/reviewed-visuals.json` now holds individually source-checked factual
comparisons. The first simplifies Ennion and McLellan's tutoring study, Table 2
(DOI `10.1111/bjet.70100`), as an accessible comparison table with the first and
second task sets kept separate. Every direction was checked against the Wiley
table. The display retains the exploratory-analysis, multiple-comparison and
measurement limits; it makes no claim about answer accuracy or lasting learning.
The paper's Figure 1 is interpretive, so it is not rendered as a measured effect.

These are original factual displays, not redistributed source images. Each
entry records its source URL, version, content hash, locator, attribution and
AI-assisted check. `build_visuals.py` requires the exact approved reading and
source identity, and rejects a changed visual until its content-bound check is
renewed. The UI repeats the version check and uses real table headings, a text
alternative and a direct source link. Other original summaries continue to
suppress older indexed graphics. Source-image reuse still requires checking the
actual image, its license and any third-party exception before adding it.

Run `python -m unittest discover -s tests -p test_reviewed_visuals.py -v`,
`node tests/validate_article_ui.cjs`, and the browser validator after the normal
public build. Hashes prevent stale reuse; they do not prove review quality.

### Production visual checks

Run visual QA after the normal build, on the exact deployment payload and image URLs. Include library cards, featured stories, weekly cards and reading pages at desktop and mobile sizes. Confirm that review-needed records have no rendered editorial `<img>` or shared fallback, and that accepted images load with nonzero natural dimensions. Check stale cached payloads and broken asset paths separately from artistic similarity.

`tests/validate_observatory_browser.py` also decodes every actual served cover in Chromium, Firefox and WebKit at the two card sizes, 120 × 76 and 76 × 58. It compares all pairs, including curated raster covers, using full-image and foreground-union color differences. This catches near twins missed by filename, motif or SVG-byte comparisons. A failed pixel screen requires inspection of the suspect covers and their source context; it must not be fixed by loosening a threshold just to make the build green. These checks are regression tripwires, not a reliable declaration of contextual or artistic uniqueness. Re-run the image audit whenever renderer rules, curated assets or the published corpus change.
