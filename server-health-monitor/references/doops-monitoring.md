# Doops Monitoring Reference

Use doops for managed live checks when the user asks to monitor 浙音, 杭电, `zheyin`, `hdu`, or a supplied doops target. All commands are read-only and must avoid printing secrets.

For current 浙音/zheyin and 杭电/hdu server-health work, the default monitoring target is the resolved doops 节点自身: `zheyin` for 浙音 and `hdu` for 杭电. This path collects CPU, memory, disk, load, uptime, main process status, key service status, and doops channel status from the doops node itself. It is doops-only: 无需 SSH/WinRM/SNMPv3，也无需 Excel credentials. It must not call SSH, WinRM, or SNMPv3 unless the user explicitly switches from managed self-node monitoring to an ordinary server inventory deep-collection mode. It does not prove CPU, memory, disk, process, or service state for ordinary business servers that merely appear in an asset sheet.

## Managed Environments

| User wording | Resolved target | Notes |
| --- | --- | --- |
| `浙音`, `浙江音乐学院`, `Zhejiang Conservatory of Music`, `zheyin`, `zy`, `zjcm` | `zheyin` | Use this target for Zhejiang Conservatory of Music server-status requests. |
| `杭电`, `杭州电子科技大学`, `Hangzhou Dianzi University`, `hdu`, `hangdian` | `hdu` | Use this target for Hangzhou Dianzi University server-status requests. |

## Discovery Order

The collector resolves the doops CLI in this order:

1. `--doops`
2. `DOOPS_BIN`
3. PATH entries for `doops` or `doops.exe`
4. `~/.local/bin/doops` or `~/.local/bin/doops.exe`

The collector resolves an optional doops config path in this order:

1. `DOOPS_CONFIG`
2. Current project `.agent/skills/doops/config.json`
3. `~/.config/doops/config.json`

The config is used only for sanitized diagnostics. Do not paste config contents into reports or chat.

## Preflight

Run preflight before live managed monitoring:

```bash
python scripts/collect_doops_inventory.py --preflight --environment zheyin
python scripts/collect_doops_inventory.py --preflight --environment hdu
```

Preflight prints sanitized JSON with the resolved CLI path, config path, target name, `doops targets` return code, and redacted stdout/stderr excerpts. It must not run `doops exec`.

If preflight fails, explain the evidence boundary and stop. Do not invent host metrics.

Current zheyin/hdu gateways may use an internal HTTP doops gateway. The collector injects `DOOPS_ALLOW_INSECURE_GATEWAY=1` into doops subprocesses by default unless the user has already set a different value. When running commands manually in PowerShell, set it explicitly:

```powershell
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
```

## doops Capability Matrix

| Capability | Default policy | Monitoring use |
| --- | --- | --- |
| `targets` | Default | Preflight gateway status. Parse cluster, instance, busy, last_seen, online state, and redacted excerpt. If the target is unavailable, stop before collection. |
| `info` | Default best effort | Captures collector-node system perspective. Failure lowers evidence confidence but does not mark inspected servers unhealthy. |
| `push` | Default for workspace mode | Sends the sanitized collector package and manifest to `/root/ws/<session>/server-health/`. |
| `exec` | Default | Runs either the workspace entry script or the inline compatibility collector. |
| `read` | Default for workspace mode | Recovers `result.json`, `evidence.json`, and `collector-log.txt`. |
| `clean` | Default after workspace collection | Cleans the remote workspace unless `--keep-remote-workspace` is passed. |
| `write` | Conditional fallback | Used only when `push` is unavailable. |
| `check` | Conditional | Runs only when inventory explicitly provides `application_checks`; currently for Kubernetes deployment image consistency. |
| `ask` | Optional | Enabled only by `--doops-ai-review`; advice only, never fact evidence. |
| `install`, `upgrade` | Not used by default | Change actions; excluded from read-only monitoring. |
| `login`, `logout` | Not used by default | Credential/session management; excluded from inspection flow. |

## Collection

Collect the zheyin doops node itself:

```bash
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
python scripts/collect_doops_inventory.py --environment zheyin --out reports/zheyin-self-node/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-self-node/inventory.json --out reports/zheyin-self-node
```

If report rendering stops because `auto` lacks an AI guide image decision, ask the user whether to use an AI guide image first. Rerun with `--guide-mode html-guide` only after the user explicitly confirms the HTML/CSS guide visual.

The collector writes one server with `collect.self_node_metrics=true`, `collect.doops=true`, plus metrics, main processes, and services from the doops workspace execution. Reports label this as `doops-self-collected`. This is the preferred default because the doops agent is already on the inspected node, so no separate host credentials are needed.

Collect the hdu doops node itself:

```bash
$env:DOOPS_ALLOW_INSECURE_GATEWAY='1'
python scripts/collect_doops_inventory.py --environment hdu --out reports/hdu-self-node/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/hdu-self-node/inventory.json --out reports/hdu-self-node
```

Collect any single managed environment with the same doops-only self-node path:

```bash
python scripts/collect_doops_inventory.py --environment zheyin --out reports/zheyin-live/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-live/inventory.json --out reports/zheyin-live
```

For 杭电, replace `zheyin` with `hdu`. Do not add `--host-metrics`, `--snmp-metrics`, SSH, WinRM, or SNMPv3 flags for this managed self-node path.

The collector supports `--doops-workspace-mode auto|inline|workspace`. `auto` uses workspace transport for doops live/self-node metrics, network probe, host metrics, and SNMP metrics. Workspace transport is `push -> exec -> read -> clean`; fallback order is `push + exec + read + clean`, then `write + exec + read + clean`, then inline `exec`. Evidence records `transport_mode` as `workspace-push`, `file-write`, or `inline-exec`.

Collect a user-supplied multi-server inventory:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/server-inventory.json --out reports/run-001/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/run-001/inventory.json --out reports/run-001
```

Each listed server may provide its target through `doops_target`, `target`, `collect.doops_target`, `collect.target`, `auth_ref` in `doops:TARGET` form, or `address` when `collect.doops` is true.

If the inventory includes `application_checks`, the collector runs `doops check` after base collection and stores results as `application_observation`:

```json
{
  "name": "统一身份认证",
  "address": "10.0.0.10",
  "application_checks": [
    {
      "type": "k8s-deployment-image",
      "doops_target": "zheyin",
      "namespace": "identity",
      "deployment": "sso-api",
      "expected_image": "repo.example.com/sso-api:20260513"
    }
  ]
}
```

Image mismatch is a warning by itself, and becomes critical when the same server also has a confirmed critical business-port or service finding.

Use one managed doops node as an internal network probe for many inventory servers, including Excel operations sheets:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --limit 30 --out reports/zheyin-excel/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-excel/inventory.json --out reports/zheyin-excel
```

The collector imports Excel rows, redacts credential values, infers conservative default ports (`22` for Linux, `3389` for Windows, plus `21` for FTP roles), and stores both legacy `ports` and structured `port_obligations`. Linux SSH and Windows RDP inferred from Excel are management ports with source `excel-inferred`; FTP inferred from role text is source `role-inferred`. The collector chunks large probe batches to avoid command-line limits and stores doops-side TCP observations as `network_observation`. Reports must label this as `doops-network-probe`; it is not CPU, memory, disk, database, or service-state proof.

When only inferred management ports are unreachable, reports must mark them as warning/review-required rather than confirmed severe business outages. To make a port outage severe, provide an explicit business/service port obligation in the inventory.

Collect host-internal CPU, memory, disk, uptime, main process, and service evidence from the same internal doops vantage point:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --host-metrics-profile zheyin-monitor --limit 30 --out reports/zheyin-excel-hostmetrics/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-excel-hostmetrics/inventory.json --out reports/zheyin-excel-hostmetrics
```

Optionally collect authentication-security evidence from logs and protection configuration:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --host-metrics-profile zheyin-monitor --auth-security --auth-log-window-days 7 --limit 30 --out reports/zheyin-auth-security/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-auth-security/inventory.json --out reports/zheyin-auth-security
```

Authentication-security collection remains read-only. Linux SSH and doops self-node paths collect recent `sshd`/PAM-style authentication evidence plus SSH protection configuration when readable. Windows/WinRM targets require Security Event Log and policy read permission; if that evidence is unavailable, the report must mark `认证安全证据未覆盖` instead of presenting the server as safe. SNMP-only and network-only rows cannot collect authentication logs or lockout configuration.

Local password-strength scoring is a separate explicit opt-in:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --host-metrics --host-metrics-target zheyin --use-excel-runtime-credentials --auth-security --password-strength-audit --password-strength-source runtime-auth --limit 30 --out reports/zheyin-auth-strength/inventory.json
```

This uses only the currently authorized runtime credentials in memory and writes only counts, masked account labels, reuse group count, and rule names. It must never try online password guesses, export system hashes, run hash cracking, or write plaintext passwords to inventory, evidence, reports, logs, or chat.

To include trend comparison, pass the previous `final-report.json` to the runner:

```bash
python scripts/run_server_health_monitor.py --inventory reports/zheyin-excel-hostmetrics/inventory.json --previous-report reports/zheyin-previous/delivery/final-report.json --out reports/zheyin-excel-hostmetrics
```

This mode does not read Excel passwords. It assumes a read-only `monitor` account has already been prepared on target servers.

Optional AI review can be added after deterministic report generation:

```bash
python scripts/run_server_health_monitor.py --inventory reports/current/inventory.json --out reports/current --doops-ai-review --doops-ai-review-target zheyin --doops-ai-review-scope summary
```

This sends only a redacted findings summary to `doops ask`. The output is rendered in the "AI 辅助复核" section and never changes server status, severity, priority, due time, or evidence strength.

### zheyin/hdu self-node evidence boundary

- Directly collected: resolved doops node CPU, memory, disk usage, load per core, uptime, main running processes, and service states discovered on that node (`zheyin` or `hdu`).
- Directly collected: doops channel status, target online/busy status, last_seen, session, transport mode, collector info status, and cleanup status.
- Not collected by this default path: CPU, memory, disk, process, database, or business service state for Excel-listed ordinary servers.
- 无需 SSH/WinRM/SNMPv3 credentials for the zheyin/hdu self-node path.
- Do not run SSH/WinRM/SNMPv3 when the user asks to test zheyin or 杭电 managed node CPU/memory/disk health. Use doops direct execution only.
- If `doops clean` is unsupported by the gateway, mark `cleanup_status=failed`; this affects workspace hygiene evidence, not the already collected host metrics.

### Explicit inventory deep-collection extension

The following SSH/WinRM and SNMPv3 modes are not the managed zheyin/hdu default. Use them only when the user explicitly provides an ordinary server inventory and asks to collect host-internal metrics for those listed servers.

- Linux collection uses SSH with `monitor@<ip>` and `/opt/server-health-monitor/secrets/zheyin_monitor_ed25519` on the doops collector node.
- Windows collection uses WinRM and `/opt/server-health-monitor/secrets/winrm_zheyin_monitor.json` on the doops collector node.
- Missing account deployment, SSH/WinRM closure, invalid IPs, missing tools, and authentication failures become sanitized `collection_errors` and do not block other servers.
- Reports label full SSH coverage as `ssh-collected`, full WinRM coverage as `winrm-collected`, mixed coverage as `ssh-winrm-collected`, and partial or failed host evidence as `partial-host-metrics`.

Collect host-internal CPU, memory, disk, and uptime evidence through read-only SNMPv3 from the same internal doops vantage point:

```bash
python scripts/collect_doops_inventory.py --inventory path/to/servers.xlsx --probe-target zheyin --snmp-metrics --snmp-target zheyin --snmp-profile zheyin-snmpv3-monitor --limit 30 --out reports/zheyin-excel-snmp/inventory.json
python scripts/run_server_health_monitor.py --inventory reports/zheyin-excel-snmp/inventory.json --out reports/zheyin-excel-snmp
```

This mode does not read Excel passwords and does not implement SNMPv1/v2c community by default. It assumes each target server has an SNMPv3 read-only user and that the doops collector node can reach UDP 161. The collector node must have `snmpget`, `snmpwalk`, and `/opt/server-health-monitor/secrets/snmp_zheyin_monitor.json`.

The SNMPv3 secret file format is:

```json
{
  "version": "3",
  "username": "monitor",
  "auth_protocol": "SHA",
  "auth_key": "<redacted>",
  "priv_protocol": "AES",
  "priv_key": "<redacted>",
  "security_level": "authPriv"
}
```

SNMPv3 successes write `collect.metrics_method=snmpv3`, `collect.host_metrics_status=collected`, and the existing `metrics` fields. SNMP failures write sanitized types such as `snmp-tool-missing`, `snmp-credential-missing`, `snmp-auth-failed`, `snmp-timeout`, `snmp-no-response`, `snmp-invalid-payload`, or `invalid-address`. Reports label full SNMP coverage as `snmp-collected` and failed or partial SNMP coverage as `partial-snmp-metrics`.

## Failure Handling

- Always run `doops targets --target <target>` before `doops exec`.
- If `targets` fails, stop and report a sanitized diagnostic. Do not run `exec`.
- If `exec` fails, keep only redacted stdout/stderr excerpts in the evidence JSON.
- If `info` fails, continue collection and mark collector info status as failed.
- If `read` fails in workspace mode, parse the JSON payload from `exec` stdout markers as a fallback.
- If `clean` fails, mark `cleanup_status=failed` but keep report generation running.
- Store collection evidence in the sibling `.evidence.json` file, not in the formal report body.
- The report runner must mark doops host evidence as `doops-collected`, not as TCP-only probing.
- The report runner must mark doops-side inventory network probes as `doops-network-probe`.
- The report runner must not treat a host-metrics failure as healthy. It should show `主机指标无法监测` with sanitized error types only.
- SSH/WinRM process evidence must not include full command-line arguments; store process name, PID, user, state, CPU, and memory fields only.

## Secret Safety

The collector redacts token, password, secret, cookie, API key, authorization, and bearer-token patterns before writing diagnostics. Still, do not copy raw doops output or raw config into prompts, reports, or examples.
Do not write Excel passwords, monitor passwords, private keys, SNMPv3 auth/priv keys, SNMP community strings, WinRM secret JSON contents, or raw SSH/WinRM/SNMP stderr into inventory, evidence, formal reports, or chat.
Remote workspace files must contain only sanitized inventory snapshots, collector scripts, manifests, and result artifacts. Secrets for SSH, WinRM, and SNMPv3 remain on the doops collector node and are read only by the remote collector process.
