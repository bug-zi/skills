---
name: brainstorming
description: Structured ideation and idea-shaping partner for turning vague thoughts, product concepts, research directions, content themes, naming/positioning questions, feature ideas, or creative blocks into clear options, tradeoffs, and next actions. Use when the user asks to brainstorm, ideate, find angles, think through an idea, explore alternatives, make a rough idea concrete, generate directions, or decide which concept is worth pursuing. Do not use for pure implementation unless the user is still shaping what to build.
---

# Brainstorming

Use this skill as a thinking partner, not as a random idea generator. Help the user move from an unclear thought to useful choices.

The default arc is:

```text
frame the question -> diverge -> explore -> converge -> choose next action
```

Keep the conversation lightweight. Ask only the minimum questions needed, and ask one question at a time when the user is still exploring.

## Operating Principles

- Separate divergence from evaluation. Generate possibilities before judging them.
- Preserve the user's taste and constraints. Do not replace their intent with a generic startup, design, or productivity template.
- Prefer 3 to 5 strong directions over a long undifferentiated list.
- Make tradeoffs explicit: novelty, feasibility, effort, risk, audience fit, and time to test.
- Do not create files, specs, slides, or plans unless the user asks for an artifact.
- If the idea depends on current market, tools, competitors, laws, prices, or recent products, research first.
- If the user asks you to decide, decide. State assumptions, pick a direction, and explain why.

## Classify The Session

First infer the type of brainstorming request:

| Type | Use For | Best Output |
|---|---|---|
| Seed shaping | "I have an idea..." / early fuzzy thought | clearer concept, audience, constraints |
| Product or feature | app, workflow, UX, SaaS, tool, game | options, tradeoffs, MVP wedge |
| Content or narrative | article, talk, course, paper, video | angles, outline, hook, audience promise |
| Naming or positioning | product name, brand, title, tagline | name territories, criteria, shortlist |
| Research direction | AI/LLM topic, thesis, experiment idea | research questions, novelty checks, experiment shape |
| Stuck mode | "I'm blocked" / "no ideas" | reframed problem and 2 to 3 paths forward |

If the type is obvious, proceed. If not, ask one concise question:

```text
What are we brainstorming toward: product, content, research, naming, or just exploring?
```

## Workflow

### 1. Frame

Restate the problem in one compact paragraph:

- Goal: what the user is trying to achieve.
- Audience: who it is for.
- Constraint: time, medium, skill, budget, technology, or tone.
- Decision: what needs to become clearer by the end.

When context is thin, ask one high-leverage question instead of a questionnaire. Good questions:

- "Who is this for, and what do they currently do instead?"
- "What would make this feel successful to you?"
- "Are we optimizing for novelty, usefulness, speed, beauty, or learning?"
- "What is the smallest version that would still feel real?"

### 2. Diverge

Generate ideas in labeled lanes so they are meaningfully different:

- Obvious but solid: practical ideas that probably work.
- Adjacent: ideas borrowed from nearby domains.
- Inversion: solve the opposite problem, then reverse it.
- Constraint-driven: ideas that use time, budget, format, or platform limits as fuel.
- Weird but useful: unusual ideas with a hidden mechanism.
- Bold bet: ambitious idea that could be excellent if the user has appetite.

Do not overfill. Usually produce 6 to 12 raw ideas, then group them into 3 to 5 directions.

### 3. Explore

For the strongest directions, explain:

- Core mechanism: why this could work.
- User value: what pain, desire, or curiosity it serves.
- Differentiator: what makes it not generic.
- Risk: what could make it fail.
- Fast test: how to validate it cheaply.

Use one or two creative methods only when helpful:

- How Might We: reframe the problem as an opportunity.
- SCAMPER: substitute, combine, adapt, modify, repurpose, eliminate, reverse.
- Analogy: borrow from another industry, medium, or historical pattern.
- Constraint prompt: "What if this had to be done in one hour / one page / no code / one screen?"
- Six hats: facts, feelings, risks, value, possibilities, process.
- Morphological matrix: combine choices across dimensions for naming, products, or formats.

Avoid dumping every method. Pick the method that fits the blockage.

### 4. Converge

Rank the best options with a simple matrix:

| Direction | Why It Fits | Upside | Risk | Fast Test | Recommendation |
|---|---|---|---|---|---|

Use this scoring only if it helps:

```text
score = audience value + distinctiveness + feasibility + taste fit - downside
```

Name the recommended path clearly. Also name the runner-up if the choice is close.

### 5. Handoff

End with a next action matched to the user's goal:

- Conversation: ask the next clarifying question.
- Decision: recommend one direction and why.
- Artifact: produce a brief, outline, name shortlist, or experiment plan.
- Implementation: hand off to planning or coding only after the idea is chosen.

## Output Shapes

### Quick Brainstorm

Use for casual requests:

```markdown
## Framing
[one paragraph]

## Directions
1. [direction] - [why it is interesting]
2. [direction] - [why it is interesting]
3. [direction] - [why it is interesting]

## Best Bet
[recommendation and reason]

## Next Question
[one question]
```

### Idea Brief

Use when the user wants a concrete concept:

```markdown
# [Concept Name]

## One-Line Pitch
[what it is and for whom]

## Problem
[pain, desire, or opportunity]

## Core Idea
[mechanism]

## Why Now / Why This
[timing, taste, or differentiation]

## First Version
[smallest useful version]

## Risks
[top risks]

## Fast Test
[validation step]
```

### Naming / Positioning

Use when the task is about names, titles, taglines, or positioning:

```markdown
## Naming Territories
1. [territory] - [emotional / semantic space]
2. [territory] - [emotional / semantic space]
3. [territory] - [emotional / semantic space]

## Shortlist
| Name | Why It Works | Risk |
|---|---|---|

## Recommendation
[best name and why]
```

### Research Direction

Use for AI, LLM, academic, or technical research ideas:

```markdown
## Research Angle
[question or hypothesis]

## Novelty Claim
[what might be new or underexplored]

## Baseline
[what this should be compared against]

## Experiment
[smallest test]

## Failure Mode
[what would disprove or weaken it]
```

## Conversation Rules

- If the user gives a rough idea, do not immediately turn it into a long plan. First sharpen the problem.
- If the user asks for "more ideas", add new lanes instead of repeating variants.
- If the user seems overwhelmed, reduce to 2 or 3 choices.
- If the user wants creativity, include one surprising option.
- If the user wants execution, converge quickly and state the next concrete step.
- If another specialized skill is better for the next phase, mention the handoff briefly after the brainstorming result.

