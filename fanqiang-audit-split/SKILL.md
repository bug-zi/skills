---
name: fanqiang-audit-split
description: "Use when running the split/orchestrator version of the Zhejiang Conservatory proxy/VPN audit workflow that coordinates 翻墙管理_skill for log investigation and secgate3600-firewall-api-skill for SecGate 3600 verification or approved remediation."
---

# 翻墙审核（分工版）

Use this skill when the user wants the non-cohesive, split/orchestrator version of the Zhejiang Conservatory proxy/VPN audit workflow.

This skill coordinates two sibling skills instead of embedding their full knowledge:

- `翻墙管理_skill`: log investigation, SFTP `tw_act/web_act`, 172.16.15.20 authentication/access logs, firewall syslog evidence, false-positive filtering, and evidence classification.
- `secgate3600-firewall-api-skill-20260606`: SecGate 3600 object/policy inspection, candidate-vs-firewall comparison, remediation planning, approved writes, and post-write verification.

Keep both sibling skills installed and available. If either sibling skill is missing, stop and state the missing dependency; do not silently fall back to the cohesive `fanqiang-audit` skill unless the user explicitly asks.

## Core Rules

- This is an orchestration skill. Do not duplicate the sibling skills' full API manuals or log investigation rules here.
- Use `翻墙管理_skill` for all source-log interpretation and evidence classification.
- Use `secgate3600-firewall-api-skill-20260606` for SecGate 3600 read-only verification and any approved firewall writes.
- Default firewall behavior is read-only.
- Do not modify firewall objects, policies, logs, or raw evidence unless the user explicitly approves the exact write action in the current conversation.
- Never add `--apply` before user approval.
- Analyze large logs on the log host or DOOPS target and retrieve only compact CSV/JSON outputs.
- Use UTF-8 explicitly for Chinese files and reports. Terminal mojibake alone is not evidence that stored files are corrupt.
- Record executed commands and outcomes; redact passwords, tokens, cookies, and secrets.

## Local Structure

- `scripts/build_quick_audit.py`: helper to build 快速审计 CSV from compact `tw_act` evidence plus authentication index.
- `scripts/query_access_windows.py`: helper to build 行为评估 CSV from quick-audit events and narrow 172.16.15.20 access windows.
- `scripts/build_auth_index.py`: helper to build/reuse daily lightweight 172.16.15.20 authentication SQLite indexes.
- `agents/openai.yaml`: metadata for this split version.

This split version intentionally does not bundle SecGate 3600 API references or publishing scripts. Use `secgate3600-firewall-api-skill-20260606` for those.

## Skill Relationship

```text
翻墙管理_skill = evidence producer
secgate3600-firewall-api-skill-20260606 = firewall verifier/executor
待处置候选清单 = interface between them
fanqiang-audit-split = workflow orchestrator
```

Normal handoff:

```text
翻墙管理_skill investigates logs
  -> produces compact candidate evidence
  -> fanqiang-audit-split builds 快速审计 / 行为评估 CSVs when useful
  -> secgate3600-firewall-api-skill verifies firewall objects/policies
  -> fanqiang-audit-split produces the remediation plan
  -> user approves exact write
  -> secgate3600-firewall-api-skill writes and verifies
  -> fanqiang-audit-split produces final disposition
```

## Audit Modes

### 快速审计模式

Use this as the default mode when the user asks which account/student ID used proxy/VPN, when it happened, what internal IP was involved, and what protocol/object appeared.

Default evidence:

- SFTP `tw_act` from `翻墙管理_skill`: confirmed proxy/VPN evidence.
- 172.16.15.20 `authlog` from `翻墙管理_skill`: MAC and `账号/学号` enrichment.
- Optional SecGate 3600 read-only verification from `secgate3600-firewall-api-skill-20260606`: control status for remediation planning, not proof that proxy/VPN happened.

Default CSV columns:

- `学号/账号`
- `翻墙时间`
- `内网IP`
- `翻墙协议/类型`
- `访问IP/对象`
- `身份时间匹配`
- `学号匹配`
- `备注`

Do not output `窗口开始`, `窗口结束`, or `管控情况` in 快速审计 CSV.

### 行为评估模式

Use this mode when the user asks for visited sites/domains, what the user did, risk interpretation, or behavior evaluation.

Run 快速审计 first, then use `翻墙管理_skill` and `scripts/query_access_windows.py` to query access context from event windows:

- Use each quick-audit row as one event.
- Start with `±10 minutes`; expand unmatched events to `±30 minutes` at most.
- Query heavy families only with candidate `内网IP` prefilter plus event-time filtering.
- Output one behavior summary per proxy/VPN event.

Behavior CSV must include:

- `翻墙行为评估`
- `管控情况`

`管控情况` must come from `secgate3600-firewall-api-skill-20260606` read-only verification when available. If not verified, leave blank or mark `未核验`; do not infer it from logs.

## Workflow

1. Convert the user's requested date/range into concrete Asia/Shanghai start and end times.
2. Use `翻墙管理_skill` to resolve log transport and query SFTP `tw_act_YYYYMMDD*.txt`.
3. Extract proxy/VPN event evidence: time, internal IP, destination IP, protocol/type, access object, source file, and sample evidence.
4. Use `翻墙管理_skill` or `scripts/build_auth_index.py` to build/reuse the daily 172.16.15.20 authentication index.
5. Enrich MAC and account/student ID by matching internal IP and event time.
6. Generate 快速审计 CSV. Keep `身份时间匹配` and `学号匹配` separate; do not include `管控情况`.
7. When behavior evaluation is requested, use `翻墙管理_skill` and `scripts/query_access_windows.py` to query event-window access context and output behavior CSV.
8. When control status or remediation planning is needed, use `secgate3600-firewall-api-skill-20260606` in read-only mode to verify objects and policies.
9. Generate candidate action list and remediation plan.
10. Stop for explicit user approval before any write.
11. After approval, use `secgate3600-firewall-api-skill-20260606` to perform the exact approved write and post-write verification.
12. Generate final disposition result.

## DOOPS and Output Safety

- If DOOPS rejects `zy` with `insecure gateway URL ... is not allowed`, set `DOOPS_ALLOW_INSECURE_GATEWAY=1` only for the current command/process.
- Prefer relative paths or POSIX/WSL paths for `doops push`; avoid Windows `D:\...` absolute paths through the wrapper.
- After `doops push`, verify remote workspace layout with `find /root/ws/<session> -maxdepth 2 -type f`.
- For full-day audits, pass `--date YYYY-MM-DD` and let scripts use default full-day time ranges rather than passing nested shell time strings with spaces.
- Treat DOOPS terminal mojibake as display-layer evidence only.
- Do not trust `doops read` output until the local file is verified. Some DOOPS builds print targeting/status banners to stdout before file bytes.
- After retrieval, decode CSV as `utf-8-sig`, verify the header, remove anything before the CSV BOM/header, remove trailing empty rows, confirm row widths, and check mojibake markers such as `锟`, `�`, `Ã`, and `Â`.

## Output Standards

Before approval, generate compact audit outputs:

- 快速审计 CSV.
- 行为评估 CSV when requested.
- Identity coverage summary.
- Access context coverage summary when requested.
- Firewall read-only verification and failures when requested.
- Remediation plan and review-required items when remediation is requested.

Include the口径:

- `确认翻墙以 SFTP tw_act 主日志为准；20 上网行为管理用于 MAC/账号关联和补充线索。`
- `防火墙管控情况来自 SecGate 3600 只读对象/策略核验，不是翻墙行为本身的证据。`
