# Article illustration pipeline

Every eligible public reading receives an `editorial_art` object. This is a presentation layer, not research evidence. `build_visuals.visual_spec`, reading depth, publication gates, source citations, and source provenance are unchanged.

## Automatic generation

Run the normal publication build:

```sh
python scripts/build_public.py
```

The existing weekly and deployment workflows already run that build. After source-quality and reading-depth gates, it creates missing/changed covers under `assets/article-art/` and attaches their metadata to the public library and weekly projections. Deployment must copy the generated directory with the other assets. There is no new schedule, API key, paid service, network call, or external graphics dependency.

Generated SVGs are intentionally not checked in. The renderer is standard-library Python. A normal image is approximately 3–4 KB, with a hard 32 KB limit. Each contains only a closed vocabulary of SVG paths, groups, circles and rectangles: no scripts, fonts, external resources, source figures, or embedded text.

For a standalone review of the already-public collection:

```sh
python scripts/article_art.py --report /tmp/article-art-report.json \
  --contact-sheet /tmp/article-art-contact.html
```

This command creates assets and review files, but does not rewrite public JSON or run source acquisition. It rechecks publication eligibility and refuses an internal `library.json` input. `--root` selects another checkout. A contact sheet is a local HTML file; the report lists every asset, its concept, evidence-independent semantic cues, byte budget and collision audit.

## What is unique, and what is shared

These are procedural, source-theme illustrations, not individually art-directed covers. Twenty primary metaphor families include offloading cranes, reconstruction bridges, verification lenses, reflection mirrors, shared puzzle pieces, interruption envelopes, attention apertures and adjustable shutters. A separate subject vocabulary adds concrete objects for writing, mathematics, language, music, governance, sleep, games, teaching, cognitive effort and other source topics.

Public titles and digest prose choose the primary metaphor, a second subject, a spatial relationship and a setting. Ten settings replace a repeated universal background: studio, library, workbench, classroom, folded paper, quiet room, night window, digital window, threshold and reading room. Six arrangements express inspecting, sharing, separation, comparison, protection or pairing. No numerical study findings determine shapes, quantities, proportions, or directional effects.

The identity hash changes only small print/layout details. It does **not** choose the meaning. Each record has a `semantic_signature` and a `composition_fingerprint`. The latter is calculated with all identity-based microvariation disabled, so the report cannot claim semantic uniqueness merely because filenames or pixels differ. Repeated compositions are reported explicitly in `semantic_collision_groups`. Similar future articles may legitimately reuse a metaphor and need editorial review rather than arbitrary extra shapes.

The initial 88-record collection has 85 generated covers plus three curated covers. Review the current report for the exact geometry count and collisions after any corpus change. `semantic_basis` distinguishes `title`, `digest`, `title_and_digest`, `topic_fallback`, and `editor_selected`. A topic fallback is labeled as such; it is never described as source-specific art.

Prefer curated, individually reviewed overrides for featured stories, nuanced claims, weak keyword matches, or repeated concepts. A meaningful concept sentence and a visibly different composition matter more than a uniqueness counter.

## Determinism and cache behavior

DOIs are normalized case-insensitively, including DOI URLs. Source URLs retain case-sensitive paths and meaningful query parameters, while tracking parameters and fragments are removed. A title hash is an explicit last-resort identity for records without a DOI or URL.

Filenames contain an identity digest and an SVG content digest, never raw titles or identifiers. Input fingerprints cover the canonical identity, public editorial text and renderer version. A change to the digest invalidates the cache, even though numerical findings never become drawing instructions. Collection dates and unrelated acquisition metadata do not churn art. Generation has no timestamps and writes a file only if its content differs. Increment `RENDERER_VERSION` when changing the design contract.

Old generated files are not deleted automatically. This prevents breaking older payloads or deployment races. A clean deployment checkout generates only the assets it needs. Curated assets live in a separate folder and are never pruned by the renderer.

## Curated overrides

Create `data/article-art-overrides.json`:

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

Keys must use the exact canonical `doi:` or `url:` identity. Required fields are `src`, `alt`, `concept`, and `provenance`. Thumbnails and dimensions are optional; dimensions, when supplied, must match the actual raster. Thumbnail dimensions must not exceed the cover and must preserve its aspect ratio.

Paths must be flat lowercase letters/digits/hyphens under `assets/editorial-covers/` or `assets/article-art/`, ending in `.webp`, `.png`, or `.jpg`. No URLs, nested folders, traversal, SVG overrides, or external symlinks are allowed. Images must exist, have supported raster headers, and be at most 2 MB each. Two articles cannot share the same override cover. Missing manifests use procedural art; malformed manifests stop validation before publication rather than publishing a broken image. Overrides do not make ineligible articles public.

The public record retains explicit per-asset provenance and checksums. Use only original or appropriately licensed art. A provenance field is not proof of permission and does not grant rights to publisher figures or copyrighted source images. This feature adds no license to research content. The three initial curated covers are original generated editorial work, with their specific provenance recorded in the manifest.

## Review and tests

```sh
python -m unittest discover -s tests -p test_article_art.py -v
```

Tests cover actual and synthetic records, meaningful topic families, geometry/semantic audits, deterministic bytes and write-if-unchanged behavior, canonical identities and path collisions, source changes, SVG safety, override validation, size budgets, contact-sheet escaping, and publication quarantine. Compare the full public projection with the art attachment disabled to verify that the only new information is `editorial_art`.

Inspect a contact sheet after modifying selection rules or object drawing. Keyword rules can misread a title, miss a qualification, or overemphasize a secondary topic. Art does not verify an article's findings and must never stand in for the evidence layer. Card images can use empty alt text when redundant with the adjacent title; a reading-page illustration can use its descriptive metaphor alt text.
