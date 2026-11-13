# Observatory typography

The Observatory is a research publication with interactive experiments. Its type should help readers distinguish an editorial idea, the evidence supporting it, and an action they can take. Keep the red publication identity; use size, spacing, and weight to establish hierarchy before introducing another font.

## One type system, three roles

`assets/typography.css` owns font loading, family stacks, and the type scale. Page styles own layout and assign those roles. Use the same system on the homepage, research library, article reader, Evidence Atlas, Lab, weekly issue, permanent editions, archive, subscription page, and browser presentation of RSS.

| Role token | Family | Where it belongs | Preferred weights |
| --- | --- | --- | --- |
| `--font-reading` | Open Sans | Research explanations, paragraphs, lists, evidence tables, source details, form input | 400 regular; 600 emphasis; 700 strong |
| `--font-editorial` | Gentium Book Plus | Editorial headlines, section headings, card titles, short pull quotes | 400 regular/italic; 700 bold/bold italic |
| `--font-interface` | Jost | Masthead, navigation, buttons, short section labels, compact controls | 400 regular; 600 emphasis; 700 strong |

`--font-code` uses the reader's system monospace only for code, keyboard keys, or literal technical notation; it does not download a fourth family. Open Sans includes real italics; Jost is upright only, so do not italicize interface text. The variable sans-serif files cover weights 400–700, with 400/600/700 preferred for a simple hierarchy.

The two sans-serif families have different jobs. Keep Jost out of sustained research prose; keep Open Sans in explanations. A research idea remains the primary heading, with the publication title and citation beneath it. A long source title is metadata, not a competing display headline.

Older `--sans`, `--display`, `--brand`, `--reading-font`, and `--heading-font` names are compatibility aliases. New components should use the semantic role names above. Do not introduce another literal family stack inside a component or template.

## Scale and reading rhythm

Values below describe the default 16px root size. Keep `rem` units and allow the reader's browser settings to enlarge them.

| Token | Default range | Use |
| --- | --- | --- |
| `--type-caption` | 13px | Dates, source metadata, chart captions, short overlines |
| `--type-small` | 14px | Secondary explanations, compact source lists, disclosure labels |
| `--type-body` | 16px | Normal reading, instructions, inputs |
| `--type-lead` | 18–20px | Introductory paragraph or standfirst |
| `--type-card` | 24px | Story/card headings and short pull quotes |
| `--type-section` | 28–36px | Section headings |
| `--type-title` | 34–64px | Page and issue headlines |
| `--leading-reading` | 1.75 | Sustained prose |
| `--leading-heading` | 1.15 | Multiline headings |
| `--measure-reading` | 70ch | Maximum normal prose measure |

Caption size is not a way to fit a paragraph into a crowded card. Use body size for substantive explanations and reduce density or change the layout instead. Do not shrink body copy on phones. Inputs use at least the body size; controls also need sufficient padding and a minimum 44px target.

Use normal tracking in prose and sentence-case controls. Short uppercase labels may use modest positive tracking; avoid long uppercase sentences. Editorial headings need restrained negative tracking, around `-.015em`, rather than compressing glyphs to fit. Never request an unavailable weight and rely on browser-synthesized bold or italics. Use the supplied faces and supported weights.

Numbers in the Lab's timed stimuli are a deliberate exception to the normal heading scale: their large size communicates the task itself. Keep task numerals stable and use tabular figures where alignment matters. Inline SVG coordinates use viewBox units, so a global HTML font-size replacement is inappropriate; give diagrams the appropriate family and inspect their rendered size.

## Applying the rules

Reuse a component's existing role before creating a new selector. For example, an article card uses the editorial role for its idea, the reading role for its explanation, and caption size for the citation. Its button uses the interface role.

```css
.research-card h3 {
  font: 700 var(--type-card)/var(--leading-heading) var(--font-editorial);
  letter-spacing: -.015em;
}
.research-card p {
  font: 400 var(--type-body)/var(--leading-reading) var(--font-reading);
  max-width: var(--measure-reading);
}
.research-card .citation {
  font-size: var(--type-caption);
  overflow-wrap: anywhere;
}
.research-card button {
  font: 600 var(--type-body)/1.5 var(--font-interface);
  min-height: 44px;
}
```

For a new component, first decide whether each piece is reading, editorial, or interface text. Select a scale token and allow wrapping. Adjust spacing or columns before changing the type scale. Decorative initials and task stimuli can have explicitly scoped sizes, but do not turn an exception into a new default.

Newsletter presentation comes from `scripts/build_newsletter.py`, not hand edits to generated HTML. Root `newsletter.html` loads `assets/typography.css`; `issues/*.html` loads `../assets/typography.css`. Regenerate the presentation without altering frozen issue JSON, source claims, feed identifiers, or publication dates. RSS article content remains independent of the subscriber's chosen fonts; only the website's browser feed view adopts this system.

## Font delivery and future additions

Fonts are served from this repository as WOFF2 files with `font-display: swap`. They do not depend on an external font API, a paid plan, or a font subscription. The [font manifest](../assets/fonts/manifest.json) records every original Google Fonts asset URL, family, style, weight range, byte size, and SHA-256 digest. Seven Latin WOFF2 assets total **217,432 bytes (about 212 KiB)**; browsers fetch only the faces needed by the page and can cache them across editions. This is the baseline transfer budget for future changes, not a claim that every visit transfers every file. Gentium has separate regular/bold and italic faces; Open Sans has upright and italic variable files; Jost has one upright variable file.

Retain the supplied SIL Open Font License files for [Gentium Book Plus](../assets/fonts/gentiumbookplus-OFL.txt), [Jost](../assets/fonts/jost-OFL.txt), and [Open Sans](../assets/fonts/opensans-OFL.txt). Keep licenses and source provenance alongside the assets. Family stacks retain system sans-serif or serif fallbacks when a face cannot load. The distributed web files are Latin subsets; characters outside their coverage use the reader's system fallback, including non-Latin names. Do not claim that the subset contains every language or mathematical symbol.

Reuse the three roles by default. An additional font must have a specific purpose the existing roles cannot meet. Record its role, permitted weights/styles, source, redistribution license, and transfer size; update the central stylesheet and font manifest together. Keep the smallest useful set of files and avoid downloading every weight. Check the same pages with the new face and with fallback fonts. A new family should not create a second competing body or editorial system.

## Review checklist

- Check the homepage, library, an article with long source metadata, Atlas charts, each Lab activity, the weekly issue, a permanent edition, archive, subscription page, and browser RSS view.
- Check 320px and 390px phone widths, tablet, and desktop; check 200% browser zoom. Text must reflow without page-wide horizontal scrolling, overlapping controls, missing labels, or clipped headings. Keep meaningful text available when a preview is shortened.
- Check paragraphs at a comfortable measure, including a long title, a DOI/URL, accented names, italics, bold, and numerical results. Confirm glyphs and the intended faces actually load.
- Check keyboard focus, expanded disclosures, form labels, error/status messages, and longer Lab answers. Larger type must not hide controls or the next action.
- Check a failed-font/fallback state. Layout and content must remain usable before or without font downloads.
- Run the repository's existing validation suite, including typography checks. When adding an asset, verify it is included in the Pages package and that relative paths resolve on root and archived pages.

## Audit and change record · November 13, 2026

The audit found three intended families but several inconsistent implementations: obsolete DM Sans/Newsreader definitions remained in the main stylesheet; permanent editions named fonts they never loaded; the subscription page duplicated a separate font request; and the browser RSS view used an unrelated system-font treatment. Numerous historical overrides made roles and sizes hard to follow. Some Lab notes and mobile labels were only 8–11px, and a 10px `!important` rule defeated a later readability adjustment. Legacy serif declarations requested weight 500 despite the supplied regular/bold faces.

The typography update establishes the shared stylesheet and role tokens, consistent font delivery across website surfaces, a readable scale, and explicit maintenance guidance. Presentation changes leave the newsletter's research content, canonical source records, and stable issue links intact.

This is a typography audit, not a reconstruction of historical artwork. Text baked into existing raster illustrations cannot inherit CSS; those images are not redrawn or recolored by this change. The Lab's large numeric stimuli remain contextual exceptions. Browser checks and automated checks provide evidence for the tested pages and sizes, not a guarantee for every device, operating system, language, or future component.
