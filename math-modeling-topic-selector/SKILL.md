---
name: math-modeling-topic-selector
description: Use when Codex needs to interpret mathematical modeling contest problems, compare A/B/C topics, recommend a problem or track, or judge data, modeling, coding, paper-writing, time, and team-fit risk.
---

# Math Modeling Topic Selector

## Overview

Use this skill to turn mathematical modeling contest problem statements and attachment inventories into a Chinese topic-selection decision report. Keep the work limited to problem interpretation and topic choice; do not continue into full modeling, coding, or paper drafting unless the user explicitly asks.

## Required Inputs

- Problem statements for each candidate problem, from PDF, DOCX, image, text, or pasted content.
- Attachment inventory: data files, result templates, tables, images, CAD/STP files, rules, and submission requirements.
- Team profile if available: modeling, programming, domain knowledge, writing, time budget, and preferred tools.

If the team profile is missing, use the default profile below, give an initial ranking, and explicitly ask for team details needed to recheck the recommendation.

## Workflow

1. Read the problem statements and attachment list. If only filenames are available, mark any uncertainty caused by missing problem text.
2. Summarize each problem: core task, required outputs, constraints, data dependencies, and final deliverables.
3. Classify each problem type: forecasting, optimization, simulation, evaluation, mechanism modeling, statistics/ML, geometric/CAD, operations research, or mixed.
4. Score each candidate with `references/scoring-rubric.md`. Use 1-5 for every dimension; higher is always better for selection.
5. Compare practical routes: for each problem, list a feasible v1 modeling route, minimum implementation path, likely figures/tables, and hard blockers.
6. Recommend one primary problem or track, then rank the rest. Explain why the runner-up is weaker.
7. If defaults were used for team fit, end with the specific team information needed to revise the ranking.

## Defaults

- Output language: Chinese.
- Output shape: decision report, not casual advice.
- Team profile: undergraduate team; limited time; medium Python/Excel ability; medium paper-writing ability; no strong domain background.
- Selection preference: explainable, reproducible, contest-finishable work over opaque or overly complex methods.
- Risk handling: penalize unavailable data, hard-to-parse proprietary geometry, weak validation paths, and vague deliverables.
- Integrity rule: do not invent data, official rules, literature, experiments, or results. Mark assumptions explicitly.

## References

- Load `references/scoring-rubric.md` before scoring or recommending.
- Load `references/report-template.md` before writing the final decision report.

## Common Mistakes

- Do not choose the most technically interesting problem unless it is also feasible within contest time.
- Do not overrate a data-rich problem if the output cannot be validated or explained clearly in a paper.
- Do not ignore result templates, submission formats, or official AI/tool-use rules.
- Do not continue into full solution design after selection unless the user asks.
