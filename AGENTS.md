# AGENTS.md

## Project Purpose

This repository is the user's central skill library.

It is used to collect, maintain, inspect, install, and synchronize the skills the
user actively uses across Codex and Claude Code.

Treat `D:\Code\skills` as the central source of truth unless the user explicitly
names another source.

## Core Policy

Do only the task explicitly requested by the user.

Do not install, delete, rewrite, refactor, rename, or synchronize skills unless
the user explicitly asks for that action or confirms an installation.

Prefer the smallest viable change.
Touch only files directly needed for the requested task.
Prefer editing existing files over creating new files, except when adding a new
skill folder or this project-level instruction file is the requested task.

## Skill Repository Layout

Each skill must live in one top-level folder under `D:\Code\skills`.

A valid skill folder should contain:

- `SKILL.md`
- optional supporting folders such as `scripts`, `assets`, `references`,
  templates, or examples

When copying or installing a skill, preserve the entire skill folder so all
supporting files remain with `SKILL.md`.

Do not split one skill across multiple locations.
Do not merge multiple skills into one folder unless the user explicitly asks.

## Known Skill Locations

Use these locations when they exist:

- Central repository: `D:\Code\skills`
- Codex skills: `$CODEX_HOME\skills`, or `%USERPROFILE%\.codex\skills` if
  `CODEX_HOME` is not set
- Claude Code skills: `$CLAUDE_HOME\skills`, or `%USERPROFILE%\.claude\skills`
  if `CLAUDE_HOME` is not set

If a target directory does not exist, stop and ask for the minimum missing path.
Do not create substitute locations unless the user explicitly requests that.

## New Skill Intake Workflow

When the user sends or links a new skill, do not install it immediately.

First, understand it carefully:

1. Inspect the provided source, repository, archive, or files.
2. Read the skill's `SKILL.md` and any directly relevant supporting files.
3. If the skill references an external project, library, tool, API, or public
   repository, use network sources to understand what that skill does and how it
   should be used.
4. Identify what the skill is for, what tasks should trigger it, what tools or
   dependencies it expects, and any setup or security-sensitive behavior.

Then explain it to the user in plain language:

Please study this skill in detail, then answer the following questions:

1. What is this skill for, and what functions does it provide?
2. What is this skill's structure? What files does it contain? How does it work
   when its prompt is injected, and what is the process flow?
3. What strengths does this skill have? What weaknesses, shortcomings, or
   limitations does it have?
4. Who is this skill suitable for? Who is it not suitable for?
5. What practical scenarios is this skill suited to? What needs and pain points
   does it mainly solve?
6. Does this skill risk polluting the prompt library, reducing AI efficiency, or
   creating security issues?

After explaining, ask the user whether they want to install the skill.

Only if the user confirms installation:

1. Download or copy the full skill folder into `D:\Code\skills`.
2. Verify that the installed folder contains `SKILL.md`.
3. Preserve all supporting files and folders.
4. Integrate the skill into Codex by copying it to the Codex skills directory.
5. Integrate the skill into Claude Code by copying it to the Claude Code skills
   directory.
6. Report what was installed, where it was installed, and anything that was
   skipped or blocked.

If the user does not confirm installation, do not download, copy, or synchronize
the skill.

For skills that are already installed locally, when the user asks for information
about a skill, use the same method above. Study the skill in detail, then answer
the following questions:

1. What is this skill for, and what functions does it provide?
2. What is this skill's structure? What files does it contain? How does it work
   when its prompt is injected, and what is the process flow?
3. What strengths does this skill have? What weaknesses, shortcomings, or
   limitations does it have?
4. Who is this skill suitable for? Who is it not suitable for?
5. What practical scenarios is this skill suited to? What needs and pain points
   does it mainly solve?
6. Does this skill risk polluting the prompt library, reducing AI efficiency, or
   creating security issues?

Save the answer as `help.md` in that skill's folder.

## Conflict Handling

A conflict exists when the same skill folder exists in more than one location
and the contents are not identical.

When there is a conflict:

1. Report the conflicting skill name.
2. Report the conflicting locations.
3. State that overwriting is blocked because the winning copy is unclear.
4. Ask the user to choose one direction:
   - central repository wins
   - Codex wins
   - Claude Code wins

Do not silently overwrite conflicts.

## Safe Copy Rules

Before copying:

- verify the source directory exists
- verify the source contains `SKILL.md`
- verify the destination parent directory exists
- compare an existing destination skill before replacing it

When copying:

- preserve the folder name
- preserve all nested files and folders
- avoid symlinks unless the user explicitly asks for symlinks
- use ordinary directory copies by default

After copying:

- summarize what was copied
- summarize what was skipped
- summarize any conflicts or missing paths

## Reserved Content

The `.system` directory contains system-provided skills.

Do not migrate, edit, overwrite, or synchronize `.system` content unless the user
explicitly asks for system skill work.

## No Fallback Behavior

If the requested task is blocked, do not switch to another task.

When blocked, only state:

1. what is blocked
2. why it is blocked
3. the minimum missing input needed

Do not perform helpful extras, preparatory work, cleanup, tests, documentation,
or adjacent fixes unless explicitly requested.
