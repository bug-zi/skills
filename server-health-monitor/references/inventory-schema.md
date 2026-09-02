# Server Inventory Schema

> `<REPORT_HOME>` = `D:\Code\vibe实验室\巡检报告report\server-health-monitor`（默认报告根目录；用户另有指定时以其为准）。

Use JSON for the most complete server inventory. CSV/TSV is supported for simple network checks. Excel `.xlsx` inventories are supported for operations sheets with columns such as `业务系统名称`, `IP地址`, `操作系统`, `服务器初始帐户/密码`, and `服务器描述`; credentials are converted to redacted references and are never written to output.

## JSON

Top-level fields:

- `environment`: object with `name`, `owner`, `inspection_window`, and optional `notes`.
- `servers`: required array.
- `thresholds`: optional object overriding default health thresholds.
- `doops_channel`: optional object written by the collector with target, session, transport mode, preflight status, collector info status, and cleanup status.
- `ai_review`: optional object written by the runner when `--doops-ai-review` is enabled; advisory only.
- `inventory_groups`: optional object written by `--classify-inventory` with total, active, inactive, monitorable, and unmonitorable counts plus CSV file paths.

Server fields:

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Stable server display name. |
| `address` | yes for live checks | IP address or hostname. |
| `doops_target` | yes for doops collection | doops target used by `collect_doops_inventory.py --inventory`. |
| `os_type` | no | `linux`, `windows`, or `unknown`. |
| `role` | no | Business role such as `web`, `database`, `file service`. |
| `owner` | no | Backward-compatible input only; formal reports do not display this field. |
| `department` | no | Backward-compatible input only; formal reports do not display this field. |
| `business_system` | no | Business system name used for impact statements. |
| `business_domain` | no | Business domain such as teaching, office, identity, finance, or research. |
| `user_group` | no | Affected users such as students, faculty, administrators, or public visitors. |
| `criticality` | no | Backward-compatible input only; formal reports do not display this field. |
| `has_redundancy` | no | Boolean indicating whether a substitute node or failover path exists. |
| `impact_note` | no | Free-text business impact explanation. |
| `lifecycle_status` | no | `active` or `inactive`. Excel/CSV fields such as usage status, asset status, or whether the server is alive are normalized here. |
| `lifecycle_reason` | no | Human-readable reason for classifying the row as still in use or inactive. |
| `ports` | no | Expected TCP ports, e.g. `[22, 443]`. |
| `port_obligations` | no | Preferred structured port list with `port`, `usage`, `source`, `required`, and optional `label`. |
| `auth_ref` | no | Use `env:VARIABLE_NAME` or `doops:TARGET`; never put real credentials in inventory. |
| `collect` | no | Capability hints such as `{"network": true, "ssh": false}` or `{"doops": true, "target": "web-01"}`. |
| `network_observation` | no | Observed doops-side network probe result from `--probe-target`; consumed by the report runner. |
| `application_checks` | no | Optional explicit application consistency checks such as Kubernetes deployment image validation. |
| `application_observation` | no | Observed result of `doops check`; written by the collector and consumed by the report runner. |
| `collection_trace` | no | Collector trace containing `doops_target`, `session`, `transport_mode`, `remote_result_path`, and `cleanup_status`. |
| `metrics` | no | Optional observed metrics if already collected elsewhere. |
| `services` | no | Optional expected service states. |
| `processes` | no | Optional observed main running processes, usually written by doops self-node, SSH, or WinRM host-metrics collection. Command-line arguments are intentionally not stored. |
| `auth_security` | no | Optional authentication-security evidence written by `--auth-security` and optional `--password-strength-audit`; contains only statistics, protection configuration, and redacted findings. |
| `collection_errors` | no | Sanitized collection failures such as `{"stage":"host-metrics","type":"ssh-auth-or-command-failed"}`; never store credentials or raw stderr. |

Supported `metrics` keys:

- `cpu_percent`
- `memory_percent`
- `load_per_core`
- `uptime_days`
- `disks`: array of `{ "mount": "/", "used_percent": 68 }`

For the zheyin self-node path, the collector writes:

```json
{
  "address": "zheyin",
  "collect": {
    "doops": true,
    "network": false,
    "self_node_metrics": true,
    "doops_target": "zheyin"
  }
}
```

The report runner labels this coverage as `doops-self-collected`. It means CPU, memory, disk, load, uptime, main processes, and services were collected from the doops node itself through doops workspace execution. It does not mean that other asset-sheet servers were accessed or measured.

Inventory classification for run-status sheets:

```bash
python scripts/collect_doops_inventory.py --inventory servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --use-excel-runtime-credentials --classify-inventory --doops-workspace-mode inline --out <REPORT_HOME>/run/inventory.json
```

With `--classify-inventory`, the collector first reads all records and writes:

- `inventory-active-servers.csv`
- `inventory-inactive-servers.csv`
- `inventory-monitorable-servers.csv`
- `inventory-unmonitorable-servers.csv`

Inactive records are not probed for host metrics. After CPU/memory collection, the final `servers` array keeps only monitorable servers so that N+1 delivery generates individual reports only for servers with successful host metrics. The total report still includes `summary.inventory_groups`, for example:

```json
{
  "inventory_groups": {
    "total_servers": 196,
    "active_servers": 141,
    "inactive_servers": 55,
    "monitorable_servers": 11,
    "unmonitorable_servers": 130
  }
}
```

Supported `services` entries:

```json
{ "name": "nginx", "status": "running", "expected": "running" }
```

Supported `processes` entries:

```json
{
  "pid": 1234,
  "name": "java",
  "user": "app",
  "state": "R",
  "cpu_percent": 86.5,
  "memory_percent": 18.2
}
```

Linux SSH and doops self-node collection keep top CPU and memory processes. Windows WinRM collection keeps process name, PID, state, `cpu_seconds`, and `memory_mb`. Reports flag zombie/defunct states and high per-process CPU or memory as warnings; they become severe only when paired with severe host-level CPU or memory evidence.

Supported `auth_security` structure:

```json
{
  "status": "collected",
  "window_days": 7,
  "method": "ssh",
  "log_evidence": {
    "failed_login_count": 18,
    "successful_login_count": 2,
    "unique_source_count": 3,
    "top_sources": [{"source": "10.0.0.8", "count": 12}],
    "top_users": [{"user": "adm***", "count": 9}],
    "patterns": [{"type": "failed-then-success", "source": "10.0.0.8", "user": "adm***"}]
  },
  "protection_config": {
    "password_login_enabled": true,
    "root_login_enabled": false,
    "max_auth_tries": 6,
    "account_lockout_enabled": false,
    "fail2ban_enabled": false,
    "rdp_nla_enabled": null,
    "winrm_basic_enabled": null,
    "audit_policy_enabled": null
  },
  "password_strength": {
    "status": "not_enabled",
    "weak_count": 0,
    "medium_count": 0,
    "strong_count": 0,
    "reuse_group_count": 0,
    "findings": []
  }
}
```

Authentication-security status values:

- `collected`: logs or protection configuration were collected from doops self-node, SSH, or WinRM evidence.
- `partial`: only part of the requested authentication evidence was collected.
- `unavailable`: the user enabled `--auth-security`, but logs or permissions were unavailable.
- `not_enabled`: authentication-security collection was not requested.

Authentication-security safety rules:

- Do not store plaintext passwords, hashes, private keys, tokens, full Authorization headers, or full raw authentication logs.
- User names may appear only in masked form such as `adm***`; use row numbers or account labels for follow-up when needed.
- `--password-strength-audit` reads only the current runtime credential fields in memory. It writes counts, reuse group count, and rule names such as “长度不足” or “包含用户名”, never the password value or a reversible fingerprint.
- SNMP-only and network-only rows cannot produce authentication-log evidence; reports must show “认证安全证据未覆盖”.

Supported `application_checks` entries:

```json
{
  "type": "k8s-deployment-image",
  "doops_target": "zheyin",
  "namespace": "identity",
  "deployment": "sso-api",
  "expected_image": "repo.example.com/sso-api:20260513"
}
```

The collector runs `doops check` only for explicit `application_checks`. A matched image is retained as evidence only. A mismatch creates an application finding; it is warning by itself and critical only when paired with a confirmed business-port or service outage.

Supported `port_obligations` entries:

```json
{ "port": 443, "usage": "business", "source": "explicit", "required": true, "label": "HTTPS" }
```

Port `usage` values:

- `business`: user-facing or system-facing business dependency.
- `service`: service dependency such as database or middleware access.
- `management`: administration access such as SSH, RDP, or WinRM.
- `unknown`: use only when the purpose is not known.

Port `source` values:

- `explicit`: declared by the inventory owner. Unreachable business/service ports are treated as confirmed severe evidence.
- `excel-inferred`: inferred from an Excel operations sheet, usually SSH for Linux or RDP for Windows.
- `os-inferred`: inferred from operating system metadata.
- `role-inferred`: inferred from role text, such as FTP.
- `legacy`: old `ports` array without structured metadata.

Severity guidance:

- Explicit business/service port unreachable: severe.
- Inferred or legacy management port unreachable: warning and review-required, because it may be intentionally restricted by firewall or bastion policy.
- Missing address, missing port, or unclear port purpose: inventory warning; do not present it as confirmed host failure.
- Host metrics and service state findings keep their threshold-based severity.

Doops collection target precedence:

1. `doops_target`
2. `target`
3. `collect.doops_target`
4. `collect.target`
5. `auth_ref` in `doops:TARGET` form
6. `address`, only when `collect.doops` is true

Doops internal network probing:

```bash
python scripts/collect_doops_inventory.py --inventory servers.xlsx --probe-target zheyin --limit 30 --out <REPORT_HOME>/run/inventory.json
```

This writes servers with `collect.doops_probe=true` and `network_observation` containing `mode`, `probe_target`, `reachable`, `ping`, and `ports`. This is network reachability evidence from the doops environment, not host CPU/memory/disk evidence.
For Excel rows, the collector also preserves `port_obligations` so the report can show whether a checked port came from OS inference or role inference.

Doops workspace collection also writes:

```json
{
  "doops_channel": {
    "target": "zheyin",
    "session": "server-health-20260513-180000",
    "transport_mode": "workspace-push",
    "target_online": true,
    "target_busy": false,
    "last_seen": "2026-05-13T18:00:00+08:00",
    "collector_info_status": "collected",
    "cleanup_status": "cleaned"
  },
  "collection_trace": {
    "doops_target": "zheyin",
    "session": "server-health-20260513-180000",
    "transport_mode": "workspace-push",
    "remote_result_path": "/root/ws/server-health-20260513-180000/server-health/result.json",
    "cleanup_status": "cleaned"
  }
}
```

`transport_mode` values are `workspace-push`, `file-write`, and `inline-exec`.

Coverage labels relevant to doops:

- `doops-self-collected`: direct self-node metrics from the doops target itself; no SSH/WinRM/SNMP credentials are needed.
- `doops-collected`: direct doops target collection for a supplied doops target.
- `doops-network-probe`: network reachability evidence from a doops vantage point only.
- `ssh-collected`, `winrm-collected`, `ssh-winrm-collected`: host metrics collected from ordinary servers through a read-only profile on the doops collector node.
- `snmp-collected`: host metrics collected through SNMPv3.

Formal report JSON also mirrors the top-level management conclusion into `summary.management_summary`. For `doops-self-collected` reports, this summary must explicitly say the measured object is the zheyin doops node itself and must not imply that ordinary asset-sheet servers were measured.

Doops internal host-metrics collection:

```bash
python scripts/collect_doops_inventory.py --inventory servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --host-metrics-profile zheyin-monitor --limit 30 --out <REPORT_HOME>/run/inventory.json
```

This first preserves any doops network observations, then attempts read-only host metrics from the doops target. Linux rows use SSH as `monitor@<ip>` with the collector-node key `/opt/server-health-monitor/secrets/zheyin_monitor_ed25519`. Windows rows use WinRM credentials from `/opt/server-health-monitor/secrets/winrm_zheyin_monitor.json` on the collector node. Credential values are used only inside the remote collection process and are not written to inventory, evidence, or reports.

Doops internal SNMPv3 host-metrics collection:

```bash
python scripts/collect_doops_inventory.py --inventory servers.xlsx --probe-target zheyin --snmp-metrics --snmp-target zheyin --snmp-profile zheyin-snmpv3-monitor --limit 30 --out <REPORT_HOME>/run/inventory.json
```

This uses `snmpget` and `snmpwalk` on the doops collector node and reads SNMPv3 credentials only from `/opt/server-health-monitor/secrets/snmp_zheyin_monitor.json` on that node. The config file is used only in the remote process memory and must not be written to inventory, evidence, or reports.

Host-metrics collection writes:

- `collect.host_metrics=true`
- `collect.metrics_method`: `ssh`, `winrm`, `snmpv3`, or `not-supported`
- `collect.metrics_probe_target`: the doops collector target, normally `zheyin`
- `collect.host_metrics_status`: `collected` or `failed`
- `metrics`, `processes`, and `services` when SSH/WinRM collection succeeds
- `collection_errors` with sanitized `stage` and `type` when collection fails

SNMPv3 collection writes the same `metrics` schema for `cpu_percent`, `memory_percent`, `uptime_days`, and `disks`. It normally leaves `services` and `processes` empty because SNMP host resources do not provide service/process state with the same reliability as SSH/WinRM. Sanitized SNMP failure types include `snmp-tool-missing`, `snmp-credential-missing`, `snmp-auth-failed`, `snmp-timeout`, `snmp-no-response`, `snmp-invalid-payload`, and `invalid-address`.

## CSV/TSV

Supported columns:

- `name`
- `address`
- `doops_target`
- `os_type`
- `role`
- `owner`
- `ports` as comma-separated values
- `auth_ref`
- `department`
- `business_system`
- `business_domain`
- `user_group`
- `criticality`
- `has_redundancy`
- `impact_note`

## Trend Comparison

The report runner accepts an optional previous report:

```bash
python scripts/run_server_health_monitor.py --inventory <REPORT_HOME>/current/inventory.json --previous-report <REPORT_HOME>/previous/delivery/final-report.json --out <REPORT_HOME>/current
```

Trend comparison uses the previous `final-report.json` and reports new, resolved, and persistent findings plus status changes for servers present in both reports. When no previous report is supplied, the report states that the current run is a baseline inspection.

## Sensitive Data

The runner strips keys containing `password`, `secret`, `token`, `cookie`, `private_key`, `api_key`, or related variants from report artifacts. Still, do not place real secrets in inventory files. Use environment variable references such as `env:ZHEYIN_WEB01_SSH_PASSWORD`. Do not store SNMPv3 `auth_key`, `priv_key`, v1/v2c `community`, or monitor passwords in inventory or evidence.
