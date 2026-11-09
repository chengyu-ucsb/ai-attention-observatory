# Contextual article illustrations

Every eligible public reading receives an `editorial_art` object, but not every reading receives an image. Artwork is a downstream presentation layer. Reading depth, publication eligibility, article counts, citations, source provenance and `build_visuals.visual_spec` remain unchanged, including when artwork needs review.

## Publication and review states

Run the ordinary publication build:

```sh
python scripts/build_public.py
```

The existing build attaches art only after its source-quality and reading-depth gates. No source acquisition, external image service, paid API, new schedule or graphics dependency is added. The caller must use `attach_art` on the complete admitted collection: `create_art` constructs one candidate and cannot independently enforce collection-wide uniqueness.

An accepted image has `status: "ready"`, a local `src`, descriptive `alt`, `concept`, provenance and content fingerprints. If source context is insufficient or a candidate duplicates already accepted artwork, it has `status: "needs_review"`, explicit `review_reasons`, and **no `src` or `thumbnail_src`**. The article remains published with its evidence intact. Consumers must not replace missing editorial art with a shared topic cover or repurpose an evidence graphic as decoration.

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

The publication build tries the preferred concept first. If it collides with an accepted cover, it can try up to five further concepts, for **at most six candidates per article**. Alternatives use different subject pairs explicitly supported by the article's title or substantive source context. Every candidate must pass the same context, semantic, geometry, byte and visual-similarity checks. A new color, rotation, filename or tiny decoration is not a new concept.

A successful alternative produces a new illustration in the same build. If all supported alternatives fail, the article stays visible without a cover. A curated illustration rejected for duplication is held for editorial review rather than silently replaced with procedural art. Missing context cannot be repaired by inventing a setting or a finding.

`data/article-art-state.json` retains accepted allocations and unresolved attempts using identifiers, fingerprints and bounded attempt metadata, without copying source prose. An accepted alternative is revalidated and kept on later builds. An exhausted unchanged candidate pool and collection are not retried indefinitely or reported as new progress. Changes to source context, the rendering/candidate policy, overrides or the admitted collection allow reconsideration. Removed or no-longer-eligible articles are pruned from this state; state cannot admit a paper for publication.

The existing refresh, full-text backfill, discovery-resume and weekly-edition workflows commit this state with their other data outputs. The read-only publication workflow also archives its exact state for 90 days as an Actions artifact; it does not commit that artifact back or automatically restore artifacts into future builds. The queue is excluded from the website's public data allowlist. There is no new timer, paid image API or unlimited generation loop: replacement attempts happen during existing publication builds. Some articles will still require more source context or a reviewed original cover.

## Context and geometry

The renderer selects a theme and two concrete subjects from source-related editorial text. `source_grounding` retains the matched phrase and the input field that licensed each subject. `visual_subjects` records the visible pair. Generic tags alone cannot qualify an image as contextual. A broad fallback theme may still be described in review metadata, but it is not rendered as a generic fallback image.

The two source-grounded subjects dominate the illustration. A primary metaphor relates them through a crane, lens, mirror, threshold, shared table or another conceptual frame. Subjects include settings and tasks such as doctoral work, undergraduate mathematics, programming, language instruction, clinical work, music, governance, phones and writing. These are editorial metaphors, never representations of measured study results. Numerical findings do not choose shapes, proportions, quantities or effect directions.

Identity hashes no longer change the scene, colors, rotation or small marks. Identical concepts produce identical geometry instead of an artificially unique image. The acceptance guard checks the semantic signature, the unordered dominant noun pair, the actual foreground glyph pair at canonical coordinates, and the full generated composition independently. It writes generated files only for accepted candidates.

`scripts/art_similarity.py` adds a dependency-free coarse raster screen for generated SVGs. It approximates the renderer's closed vector vocabulary on an 80 × 50 RGB grid, stores a compact signature, and checks every candidate against accepted generated scenes. Near-twin decisions combine full-scene color difference, color difference over the foreground union, and foreground overlap. Tiny extra marks cannot count as a new illustration merely because the SVG bytes change. The report records the method, thresholds and suspect pair scores.

These checks do **not** establish perceptual pixel uniqueness. The coarse renderer approximates curves, strokes and rasterization; it is not the browser's rendering engine. Different scenes can still look similar at card size. Curated raster overrides receive the byte-level checks, not this SVG approximation; different raster encodings can contain the same pixels. A successful automated report means the stated automated checks passed, not that a person has reviewed every cover.

Generated SVGs use a closed vocabulary of paths, groups, circles and rectangles with no embedded text, script, fonts, external references or source figures. The hard per-file limit is 32 KB. Generated files under `assets/article-art/` are not checked in and must be copied with the other assets at deployment.

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
      "provenance": "Original editorial illustration; not a source figure."
    }
  }
}
```

Required fields are `src`, `alt`, `concept` and `provenance`. Keys must use the canonical `doi:`, `url:` or title-hash identity. Optional dimensions must match the actual raster. Thumbnails must preserve aspect ratio and be no larger than the cover.

Overrides are explicitly editor-declared concepts, not automatically verified source interpretations. Their metadata preserves the declared concept and provenance rather than claiming that a procedural noun pair produced their pixels. A valid override can supply specific art when keyword matching is insufficient. Different original overrides are not rejected merely because their articles would have selected the same procedural pair.

Paths must be flat lowercase letters, digits and hyphens under `assets/editorial-covers/` or `assets/article-art/`, ending in `.webp`, `.png` or `.jpg`. URLs, traversal, nested folders, SVG overrides and external symlinks are forbidden. Assets must exist, have supported raster headers and fit the 2 MB limit. The loader calculates hashes from actual bytes, including thumbnails. Reusing a path or renaming identical bytes cannot bypass the collection collision gate. A duplicate candidate becomes review-needed; malformed manifests and invalid assets still raise before publication.

Use only original or appropriately licensed artwork. A provenance declaration is not proof of permission and grants no rights to publisher figures or copyrighted research content.

## Audit and tests

Review an already-public collection without rewriting it or running acquisition:

```sh
python scripts/article_art.py --report /tmp/article-art-report.json \
  --contact-sheet /tmp/article-art-contact.html
python -m unittest discover -s tests -p test_article_art.py -v
```

The standalone command rechecks publication eligibility and refuses an internal `library.json` input. `--root` selects another checkout. The contact sheet shows accepted images and explicit review notices without broken image tags. The report lists ready/review counts, reasons, source-grounding phrases, collision groups and accepted asset bytes. `distinct_generated_compositions` counts accepted generated compositions; collision groups also retain held candidates so rejection is visible rather than hidden by a success counter.

Tests cover real public records, realistic repeated research concepts, repeated foreground pairs with different frames, independent geometry checks, tiny-decoration visual twins, changed dominant scenes, unsupported coarse-renderer handling, insufficient context, renamed identical rasters, repeated thumbnails, canonical-paper reuse, stable ordering, retained acceptance, content-addressed caching, safe SVG/path handling and honest review reports. Publication tests compare the full build with art disabled and verify that evidence, provenance, weekly membership and quarantine are unchanged. Run `python -m unittest discover -s tests -p test_art_similarity.py -v` for the coarse rasterizer's own geometry and metric tests.

### Production visual checks

Run visual QA after the normal build, on the exact deployment payload and image URLs. Include library cards, featured stories, weekly cards and reading pages at desktop and mobile sizes. Confirm that review-needed records have no rendered editorial `<img>` or shared fallback, and that accepted images load with nonzero natural dimensions. Check stale cached payloads and broken asset paths separately from artistic similarity.

`tests/validate_observatory_browser.py` also decodes every actual served cover in Chromium, Firefox and WebKit at the two card sizes, 120 × 76 and 76 × 58. It compares all pairs, including curated raster covers, using full-image and foreground-union color differences. This catches near twins missed by filename, motif or SVG-byte comparisons. A failed pixel screen requires inspection of the suspect covers and their source context; it must not be fixed by loosening a threshold just to make the build green. These checks are regression tripwires, not a reliable declaration of contextual or artistic uniqueness. Re-run the image audit whenever renderer rules, curated assets or the published corpus change.
