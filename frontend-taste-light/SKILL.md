---
name: frontend-taste-light
description: Use when creating, redesigning, beautifying, or reviewing frontend web pages, React components, landing pages, dashboards, portfolios, product pages, or web app UI where the user wants the interface to look less generic, less AI-generated, more polished, more product-appropriate, or more visually intentional. Do not use for backend-only work, small non-visual bug fixes, documents, PPTs, HTML reports, or static editorial deliverables handled by other skills.
---

# Frontend Taste Light

Use this skill as a compact design judgment layer for frontend pages. Keep scope narrow: improve the visual and UX quality of the requested UI without turning a small task into a full design-system project.

## Reference Loading

Use progressive disclosure:

- Always follow this `SKILL.md`.
- Read `references/page-types.md` before creating or substantially redesigning a page.
- Read `references/anti-patterns.md` when the user explicitly asks to remove AI taste, make the UI feel less generic, or when the current design shows obvious AI-generated patterns.
- Read `references/checklist.md` before final delivery after frontend UI code or visual layout changes.

## Static Taste Lint

After editing frontend UI files, run the static scanner when feasible:

```bash
python frontend-taste-light/scripts/taste_lint.py <project-or-files>
```

Use it for HTML, CSS, JSX, TSX, Vue, Svelte, and Astro files. Add `--include-docs` when scanning Markdown or MDX-backed UI. Treat `FAIL` findings as blockers to fix before delivery. Treat `WARN` findings as prompts for design judgment; fix them when they match the actual UI.

## First Read

Before designing or editing, identify:

- Page type: landing, product page, dashboard, admin, tool, portfolio, content site, game, or app shell.
- User intent: browse, compare, decide, operate, configure, monitor, create, or recover from an error.
- Density: sparse marketing, balanced product, dense operational, or data-heavy.
- Brand signal: formal, playful, technical, editorial, luxury, utilitarian, consumer, institutional, or developer-facing.

Then choose one visual direction that fits the subject. Do not default to a generic startup aesthetic.

## Hard Anti-AI Rules

Avoid these unless the existing brand or source design explicitly requires them:

- Purple or blue gradient hero as the default visual identity.
- Floating gradient blobs, bokeh orbs, decorative glows, or abstract mesh backgrounds with no product meaning.
- Glassmorphism cards stacked over gradients as the main layout.
- Three generic feature cards under a vague hero as the default page structure.
- Fake analytics dashboards, fake charts, fake user avatars, or decorative data.
- Oversized rounded cards nested inside more cards.
- Huge centered slogans that do not say what the product, page, or task actually is.
- Emojis as structural icons.
- Stock-like images that do not reveal the real product, object, workflow, person, or place.
- Motion that only makes the page feel busy.

## Page-Type Rules

Use the page type to decide the composition. A landing page, dashboard, admin screen, tool workspace, portfolio, and content site should not share the same default structure.

For detailed page-type rules, read `references/page-types.md`.

## Design Moves

Typography:

- Choose fonts for the subject, not novelty alone.
- Avoid using one default sans font for everything when the page needs personality.
- Keep hierarchy clear: title, section heading, body, label, metadata, button.
- Do not use viewport-scaled font sizes for normal UI text.

Color:

- Pick a small palette with semantic roles.
- Avoid one-hue domination unless it is a deliberate brand constraint.
- Use accent color for action or meaning, not random decoration.
- Check contrast in both light and dark surfaces if both exist.

Layout:

- Use stable dimensions for repeated UI, boards, cards, buttons, charts, and toolbars.
- Avoid layout shift on hover, loading, or dynamic text.
- Use spacing to group related items and separate decisions.
- Never let text overlap or spill out of its component.

Motion:

- Use one or two meaningful motion moments per view.
- Prefer transform and opacity.
- Respect reduced motion.
- Motion should explain state change, hierarchy, navigation, or feedback.

Icons and media:

- Use a consistent icon family such as lucide when available.
- Add accessible labels for icon-only buttons.
- Use real visuals when the subject must be inspected.
- Do not invent logos, product screenshots, metrics, or brand assets.

## Implementation Guardrails

For every meaningful UI state, account for:

- Default, hover, focus, active, disabled.
- Loading, empty, error, and success states where relevant.
- Mobile layout at narrow widths.
- Keyboard access for interactive controls.
- Touch target size for mobile controls.
- Text wrapping for long labels and real content.
- No horizontal overflow on mobile.
- No hidden content behind sticky headers or footers.

## Final Taste Check

Before delivery, inspect the result against this quick check:

- Does the page look specific to this product or task, or could it belong to any AI-generated startup?
- Is the primary action obvious without competing CTAs?
- Are visual flourishes tied to meaning, brand, or workflow?
- Would the UI still work with real data, long labels, missing images, and loading states?
- Does the mobile version preserve hierarchy and avoid cramped text?
- Are colors, radius, shadows, borders, and icon styles consistent?
- Is anything decorative enough that removing it would improve the page?

For a stricter delivery gate, read `references/checklist.md`.

If the answer reveals a problem, fix the UI before handing it off.
