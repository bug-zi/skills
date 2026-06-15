---
name: server-health-monitor
description: Use when users provide server inventories, host lists, operations assets, credential references, or ask to inspect/monitor server running status for Zhejiang Conservatory of Music (浙音), Hangzhou Dianzi University (杭电), zheyin, hdu, or doops targets.
---

# Server Health Monitor

Use this skill to produce read-only, Chinese, management-ready server health reports from supplied inventories or authorized doops environments. The skill is inventory-first, explicit about evidence boundaries, and must deliver HTML, PDF, Markdown, JSON, quality audit, and manifest artifacts.

Current default for 浙音/zheyin and 杭电/hdu requests: run a doops 自身节点健康巡检 for the resolved managed target (`zheyin` or `hdu`). This monitors the doops node itself through doops workspace execution and collects CPU, memory, disk, load, uptime, main running processes, doops channel status, and key service states. This default path must not use SSH, WinRM, SNMPv3, Excel passwords, or target business-server credentials. Excel batch probing and SSH/WinRM/SNMPv3 host metrics remain optional extension paths only when the user explicitly provides an ordinary server inventory and asks for deeper per-server collection.

## Core Rules

- Treat checks as read-only unless the user explicitly asks for another mode.
- For 浙音/Zhejiang Conservatory of Music requests, automatically monitor the `zheyin` doops node itself first.
- For 杭电/Hangzhou Dianzi University requests, automatically monitor the `hdu` doops node itself first.
- For managed environment checks of `zheyin` and `hdu`, use doops `targets`/`info`/workspace `exec` evidence only; do not call SSH, WinRM, or SNMPv3.
- Do not ask for server IPs, SSH credentials, WinRM credentials, or SNMPv3 secrets for those managed self-node checks unless doops is unavailable and the user explicitly wants a recovery path.
- For the zheyin/hdu self-node path, do not ask for SSH/WinRM/SNMPv3 credentials; doops already provides the execution channel for that node.
- Never print, save, or report real passwords, tokens, cookies, private keys, API keys, gateway secrets, or doops credentials.
- All formal report content must be Chinese, including HTML, PDF, Markdown, quality audit, navigation, table headers, management conclusions, and evidence explanations.
- If host metrics or main process lists are missing, report the evidence boundary instead of implying full host health.
- 认证安全巡检必须采用“日志证据 + 防护配置 + 本地密码强度评分”的只读口径；禁止在线爆破、禁止弱口令登录尝试、禁止导出 hash、禁止 hash 破解。
- `--auth-security` 只采集认证日志和登录防护配置；`--password-strength-audit` 必须由用户明确授权后才可读取本次采集授权凭证并在内存中评分，未开启时不得读取或分析明文密码字段。
- 认证安全报告只展示统计、脱敏账号标签、命中规则和处置建议；不得展示明文密码、hash、token、私钥、完整原始日志或认证头。
- 生成导览图必须优先由 Codex/助手自主使用 GPT 生图能力。若自主 GPT 生图失败，再询问用户是否提供 API Key 继续生图；用户不提供 API Key 或明确不使用 AI 导览图时，必须先询问并取得用户确认，再使用内置中文 HTML/CSS 导览图。导览图必须始终存在，运行原因只写入 `guide-image-status.json`。
- HTML 总报告和单机报告必须使用统一的 compact/AI cover 视觉体系：AI 导览图放在首页 `ai-guide-stage`，右侧只保留管理结论和关键计数；多服务器报告不得回退到旧式密集首页。
- 多服务器批次不得让用户直接打开 `delivery-batch/servers/` 原生文件夹目录；必须生成 `delivery-batch/servers/index.html` 作为正式单机报告索引页，并在 `delivery-batch/index.html` 提供“打开单机报告索引”入口。
- 正式报告不展示负责人、业务部门、系统等级三类长期缺失字段；矩阵只保留服务器、地址、业务角色、状态、优先级、建议处理时限和证据边界。
- 多服务器总报告正文必须做内容减法：只保留管理摘要、核心指标、关键服务、doops 通道、清单分层、运行矩阵、问题与建议、趋势与证据边界；核心指标要汇总 CPU、内存、磁盘、负载和进程覆盖，关键服务没有明细时必须明确写“未采集”，不要展示空白卡片；不要展示旧模板里的管理简报、风险队列、覆盖缺口、处置行动板、升级分析模块、逐服务器长技术证据或 Markdown 原文附录。
- Before final handoff, run the report quality audit and the text integrity check.

## Quick Commands

zheyin 自身节点健康巡检（默认主路径）：

```bash
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
python scripts/collect_doops_inventory.py --environment zheyin --out reports/zheyin-self-node/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-self-node/inventory.json --out reports/zheyin-self-node
```

If the render stops because `auto` lacks an AI guide image decision, ask the user whether to use an AI guide image first. Only rerun with `--guide-mode html-guide` after the user explicitly confirms HTML/CSS is acceptable.

This reports `doops-self-collected` host metrics, main process, and service coverage. It proves the health of the zheyin doops node itself, not every ordinary server listed in an Excel asset sheet.

杭电 hdu 自身节点健康巡检（同样默认 doops-only，不走 SSH/WinRM/SNMPv3）：

```bash
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
python scripts/collect_doops_inventory.py --environment hdu --out reports/hdu-self-node/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/hdu-self-node/inventory.json --out reports/hdu-self-node
```

This reports `doops-self-collected` host metrics, main process, and service coverage for the `hdu` doops node itself.

Dry-run the desensitized sample:

```bash
python scripts/run_server_health_monitor.py --inventory assets/samples/zheyin-inventory.example.json --out reports/zheyin-sample --offline
```

Preflight 浙音 doops access:

```bash
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
python scripts/collect_doops_inventory.py --preflight --environment zheyin
```

Preflight 杭电 doops access:

```bash
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
python scripts/collect_doops_inventory.py --preflight --environment hdu
```

Collect a managed environment through doops, then render the formal report:

```bash
python scripts/collect_doops_inventory.py --environment zheyin --out reports/zheyin-live/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-live/inventory.json --out reports/zheyin-live
```

Force workspace transport for a doops batch collection:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --doops-workspace-mode workspace --out reports/zheyin-workspace/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-workspace/inventory.json --out reports/zheyin-workspace
```

Use a managed doops node as an internal network probe for an Excel inventory sample:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --limit 30 --out reports/zheyin-excel/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-excel/inventory.json --out reports/zheyin-excel
```

Collect host-internal metrics from an Excel inventory through read-only SSH/WinRM launched from a managed doops node:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --host-metrics-profile zheyin-monitor --limit 30 --out reports/zheyin-excel-hostmetrics/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-excel-hostmetrics/inventory.json --out reports/zheyin-excel-hostmetrics
```

Collect authentication-security evidence with logs and protection configuration:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --host-metrics-profile zheyin-monitor --auth-security --auth-log-window-days 7 --limit 30 --out reports/zheyin-auth-security/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-auth-security/inventory.json --out reports/zheyin-auth-security
```

Add local password-strength scoring only after explicit user authorization:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --use-excel-runtime-credentials --auth-security --password-strength-audit --password-strength-source runtime-auth --limit 30 --out reports/zheyin-auth-strength/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-auth-strength/inventory.json --out reports/zheyin-auth-strength
```

This never performs online password guessing and never writes plaintext passwords. If logs or Security Event Log permissions are missing, the report must say “认证安全证据未覆盖” instead of calling the host safe.

Classify a server run-status inventory, then monitor only servers that are still in use and can produce CPU/memory host metrics:

```bash
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --host-metrics-profile excel-runtime-credentials --use-excel-runtime-credentials --classify-inventory --doops-workspace-mode inline --out reports/zheyin-inventory-classified/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-inventory-classified/inventory.json --out reports/zheyin-inventory-classified --guide-mode ai-image
```

This writes four CSV files beside `inventory.json`: `inventory-active-servers.csv`, `inventory-inactive-servers.csv`, `inventory-monitorable-servers.csv`, and `inventory-unmonitorable-servers.csv`. The final report contains the full inventory rollup, while `delivery-batch/servers/index.html` is the designed entrypoint for individual reports whose CPU/memory host metrics were successfully collected. When SSH or WinRM metrics succeed, the report also shows the main running processes and flags high CPU, high memory, or abnormal process states.

Collect host-internal metrics from an Excel inventory through read-only SNMPv3 launched from a managed doops node:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --snmp-metrics --snmp-target zheyin --snmp-profile zheyin-snmpv3-monitor --limit 30 --out reports/zheyin-excel-snmp/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-excel-snmp/inventory.json --out reports/zheyin-excel-snmp
```

Collect a user-supplied multi-server doops inventory:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/server-inventory.json --out reports/run-001/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/run-001/inventory.json --out reports/run-001
```

Create a CSV template:

```bash
python scripts/create_inventory_template.py --out assets/server-inventory-template.csv
```

## Workflow

1. Normalize the user's request into an inventory or a managed doops environment.
2. If the request names 浙音 or `zheyin`, run the zheyin self-node path first unless the user explicitly asks for Excel batch probing or another server list.
3. If the request names 杭电 or `hdu`, run the hdu self-node path first unless the user explicitly asks for Excel batch probing or another server list.
4. For zheyin/hdu self-node checks, do not enable `--host-metrics`, `--snmp-metrics`, SSH, WinRM, or SNMPv3. Use direct doops workspace execution to collect CPU, memory, disk, load, uptime, and service state from the doops node itself.
5. If the request names another doops target, read `references/doops-monitoring.md` and run doops preflight first.
6. When the user supplies a server run-status inventory, enable `--classify-inventory`: first split all records into still-in-use and inactive CSVs, then split still-in-use servers into monitorable and unmonitorable CSVs after CPU/memory collection. Do not run host metrics against inactive records.
7. If the user asks to check password brute-force or authentication security, add `--auth-security`. Add `--password-strength-audit` only when the user explicitly authorizes local scoring of the supplied runtime credentials; do not enable it silently.
8. Collect doops evidence with `scripts/collect_doops_inventory.py`. Managed self-node paths default to workspace transport (`push -> exec -> read -> clean`) and record `doops-self-collected` evidence. Batch and explicit metrics extension modes also use read-only workspace transport with inline `exec` fallback.
9. Render the report with `scripts/run_server_health_monitor.py`.
10. Inspect `delivery/quality-audit.md` and run `python scripts/check_text_integrity.py`.
11. When inventory classification is enabled, return the N+1 `delivery-batch/` entrypoint first even if there is only one monitorable server. The overall report summarizes total, still-in-use, inactive, monitorable, and unmonitorable counts; `delivery-batch/servers/index.html` is the designed single-server report index; each monitorable server has a detailed report under `delivery-batch/servers/<slug>/delivery/final-report.html`.
12. For unmanaged single-server runs without inventory classification, return the `delivery/` entrypoints, led by HTML and PDF.

## References

- `references/doops-monitoring.md`: doops target aliases, CLI/config discovery, preflight, collection, failure handling, and sanitization rules.
- `references/inventory-schema.md`: JSON/CSV/Excel inventory fields, doops target precedence, network observations, metrics, services, authentication-security evidence, and sensitive-data rules.
- `references/report-quality.md`: formal delivery requirements, Chinese text rules, guide-image rules, and quality gates.
- Report generation must follow `references/report-quality.md` strictly: keep the 10 management-layout upgrade markers, keep all 20 advanced report modules in JSON, render only high-signal advanced modules as readable HTML components, hide low-signal modules in `advanced-hidden-summary`, and keep `checks.layout_upgrade_markers`, `checks.advanced_upgrade_markers`, and `checks.advanced_visible_signal` passing before handoff.

## Output Contract

The final handoff set must include:

- `delivery/final-report.html`
- `delivery/final-report.pdf`
- `delivery/final-report.md`
- `delivery/final-report.json`
- `delivery/guide-image-status.json`
- `delivery/quality-audit.json`
- `delivery/quality-audit.md`
- `delivery/delivery-manifest.json`
- `delivery/delivery-manifest.md`

`delivery/html-assets/guide-image.png` is present only when GPT image generation succeeds or an existing guide image is reused. When no image file is available, `delivery/final-report.html` must contain the `html-guide-visual` HTML/CSS guide visual.

For multiple servers, the runner must also create an N+1 handoff package:

- `delivery-batch/index.html`
- `delivery-batch/batch-summary.json`
- `delivery-batch/overall/final-report.html`
- `delivery-batch/overall/final-report.pdf`
- `delivery-batch/servers/index.html`
- `delivery-batch/servers/<slug>/delivery/final-report.html`
- `delivery-batch/servers/<slug>/delivery/final-report.pdf`

The overall report is the batch management summary. `delivery-batch/servers/index.html` is the designed navigation page for single-server reports. Each server report is the detailed single-server diagnosis.

## Common Mistakes

- Do not write English section headings in formal report content.
- Do not treat offline sample data or TCP reachability as proof of CPU, memory, disk, database, or service health; doops network probes prove only ICMP/TCP reachability from the managed environment.
- Do not describe zheyin self-node metrics as coverage for all Excel-listed servers. `doops-self-collected` means the doops node itself was measured directly.
- Do not use SSH/WinRM/SNMPv3 for zheyin or hdu managed self-node tests. The correct default evidence path is doops direct execution on the resolved target.
- Do not treat `doops ask` output as fault fact evidence. It may appear only as an auxiliary review section and must not change status, severity, priority, due time, or evidence strength.
- Do not use doops `install`, `upgrade`, `login`, or `logout` in default monitoring; those are change or credential-management actions, not read-only inspection evidence.
- Do not read Excel passwords for SSH/WinRM host metrics by default; use the read-only `monitor` profile prepared on the doops collector node.
- Do not copy SNMPv3 auth/priv keys. SNMPv3 credentials must stay on the doops collector node under `/opt/server-health-monitor/secrets/snmp_zheyin_monitor.json`.
- Do not treat SSH/WinRM failures as healthy. Report them as `主机指标无法监测` with sanitized error types only.
- Do not test password strength by online brute force, SSH/RDP/WinRM login guessing, hash export, or hash cracking. Use authentication logs, lockout/protection configuration, and optional local in-memory scoring only.
- Do not enable `--password-strength-audit` unless the user explicitly authorizes it for the supplied runtime credentials; never show plaintext passwords or reversible fingerprints in reports.
- Do not treat missing authentication logs as proof of no brute-force risk. Mark it as `认证安全证据未覆盖` and recommend adding event-log/auth-log read permission.
- Do not include setup secrets, missing-key instructions, guide-image failure/skip notices, command stderr with tokens, or raw doops config content in the report body.
- Do not hand off only the PDF; the audit, manifest, JSON, Markdown, HTML, guide status, and N+1 batch package when present are part of the evidence package.

## Guide Visual Rules

- 生成导览图必须优先由 Codex/助手自主使用 GPT 生图能力，不要先要求用户提供 API Key，也不要先选择 HTML/CSS 导览图。
- 若自主 GPT 生图失败，再询问用户是否提供 API Key；用户提供后，只将 API Key 放在本地 shell 环境或本地 `.env`，再运行 `--guide-mode ai-image`。
- 用户不提供 API Key 或明确不使用 AI 导览图时，必须先询问并取得用户确认，再使用内置中文 HTML/CSS 导览图，并运行 `--guide-mode html-guide`。
- Never write the API Key into report content, logs, Markdown, JSON delivery artifacts, or public docs.
- `--skip-guide-image` is kept for compatibility and means `--guide-mode html-guide`; it must not create an empty cover or display "skipped GPT" text in the report.
- If image generation fails after a key is provided, the runner must fall back to the HTML/CSS guide visual and record `fallback_reason` in `guide-image-status.json`.
