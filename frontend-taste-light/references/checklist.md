# Delivery Checklist

Use this file before final delivery after frontend UI code or visual layout changes. Treat P0 items as blockers.

## P0 Blockers

- No horizontal overflow on mobile.
- No text overlap, clipped labels, or content spilling out of buttons/cards/panels.
- Primary action is visible and unambiguous.
- Interactive controls have hover/focus/active/disabled states where relevant.
- Keyboard users can reach and operate core controls.
- Icon-only buttons have accessible labels.
- Loading, empty, and error states exist for the primary data or async workflow.
- Dashboard metrics include units and time ranges, or are clearly marked as sample data.
- The UI does not invent logos, screenshots, user avatars, metrics, or brand claims.
- Mobile layout preserves core hierarchy and does not hide content behind sticky headers or footers.

## P1 Major Quality Checks

- The page type matches the composition: tool pages start with tools; dashboards support scanning; landing pages show the product or offer.
- Visual flourishes serve meaning, workflow, brand, or hierarchy.
- The palette uses semantic roles and does not collapse into one-hue decoration.
- Contrast is readable on all major surfaces.
- Repeated components use stable dimensions and do not shift on hover/loading/dynamic text.
- Charts have labels, units, legends or direct labels, and do not rely on color alone.
- Forms use visible labels and place errors near the affected field.
- Touch targets are comfortable on mobile.
- Motion respects reduced motion and uses transform/opacity where possible.

## P2 Polish Checks

- CTA copy is specific to the next action.
- Font choices match the subject and remain readable.
- Radius, borders, shadows, icons, and spacing feel consistent.
- Empty states explain what happened and what the user can do next.
- Secondary actions are visually subordinate to primary actions.
- Long labels and real data wrap gracefully.
- Real visuals, screenshots, or artifacts are used when the subject needs inspection.
- Removing any decorative element would not make the page clearer; if it would, remove it.

## Final Question

Ask: "Does this look specific to this product and workflow, or could it belong to any generic AI-generated startup?"

If it still feels generic, revise before handoff.
