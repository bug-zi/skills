# Anti-Patterns

Use this file when the user asks to remove AI taste, make an interface less generic, or improve a design that looks like a default AI-generated frontend.

## Overloaded Hero

Tell:

- Badge, eyebrow, giant headline, long subheadline, two CTAs, logo wall, trust text, scroll cue, and decorative background all appear in the first viewport.

Fix:

- Keep the product or object visible.
- Keep one primary CTA and one quieter secondary action at most.
- Move trust proof, logos, or details below the first decision point.
- Replace vague headline copy with a concrete product, object, offer, or task.

## Repeated Rounded Card Grid

Tell:

- Every section becomes rounded cards with icon, title, paragraph, and soft shadow.

Fix:

- Vary structure by content: comparison table, timeline, workflow, split detail, checklist, annotated screenshot, dense list, or inline controls.
- Use cards only for repeated entities, selectable items, modals, or genuinely framed tools.
- Reduce radius and shadow unless the existing design system uses them.

## Decorative Product Signals

Tell:

- Status dots, uptime labels, global node counts, weather/time/location strips, command-palette hints, terminal snippets, or keyboard shortcuts appear as decoration.

Fix:

- Keep only signals that are real product functions.
- Replace fake operational signals with actual product state, screenshot, workflow step, object photo, or user task.
- If the product has no such signal, use layout, typography, and real content instead of fake chrome.

## Fake Dashboard

Tell:

- Metrics have no units, time range, source, empty state, loading state, or plausible scale.
- Charts are decorative and do not answer a question.

Fix:

- Add unit, timeframe, and source label to every metric.
- Make charts answer a specific comparison, trend, distribution, or status question.
- Add loading, empty, and error states where data can be missing.
- If real data is unavailable, label sample data clearly or avoid pretending it is live.

## Generic CTA Copy

Tell:

- Buttons say only "Get started", "Learn more", "Explore", or "Start now" while the page context is still vague.

Fix:

- Use action-specific copy: "Create report", "Import CSV", "Compare plans", "Open dashboard", "Book demo", "Generate preview".
- Keep CTA verbs aligned with the user's actual next step.

## Abstract Value Without Object

Tell:

- The page talks about speed, clarity, automation, insight, or transformation but never shows a product, workflow, screenshot, data, artifact, object, or concrete user task.

Fix:

- Show the thing: interface, document, product photo, data view, workflow, before/after, output artifact, or operating state.
- Make visual hierarchy explain the user's actual work.

## Dark Tech Glow

Tell:

- Dark page relies on blue-purple glow, grid backgrounds, neon borders, and floating panels to feel technical.

Fix:

- Use structure first: hierarchy, spacing, restrained surfaces, clear controls, real content.
- Reserve glow or neon for a meaningful highlight, not the whole identity.
- Use neutral dark surfaces with one purposeful accent when no brand palette exists.

## Centered Tool Or Admin Layout

Tell:

- Tool, dashboard, admin, or data-heavy interface is laid out like a centered landing page.

Fix:

- Put navigation, filters, controls, canvas, table, or primary workspace where repeated use expects them.
- Use left/right panels, top toolbars, tab bars, split panes, or dense grids when the workflow needs them.
- Keep primary actions near the work they affect.
