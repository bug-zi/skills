---
name: secgate3600-firewall-api
description: "Use when working with SecGate 3600 / NSG firewall RESTful APIs only: `/v1.0/login`, `/v1.0/rest/`, and `/v1.0/out`, including API setup, token/cookie login, read-only inspection, snapshots, address objects, security policies, blacklist objects, and CLI-assisted changes using the bundled SecGate 3600 V3.6.6.0 firewall API guide."
---

# SecGate 3600 Firewall API

This skill is only for SecGate 3600 / NSG firewall RESTful APIs.

## Version

- Current version: `1.1`

## Version 1.1 Operating Rules

- Default firewall API username is `sysapi`.
- Default connection mode is DOOPS through target `zy`; use direct firewall access only when the user explicitly asks.
- Default operation mode is read-only. Read-only means login, logout, snapshots, and safe `get_*` / `show_*` / read-classified API calls.
- Do not modify firewall data unless the user explicitly approves the exact write action in the current conversation.
- Never add `--apply` unless the user has explicitly approved the proposed change plan.
- Before any write, explain in plain language what will change, which object or policy is affected, the expected result, and the rollback idea.
- During operations, explain key firewall/API concepts in beginner-friendly language so a new user can learn what is happening.
- Always report executed commands and outcomes. Redact passwords, tokens, cookies, and other secrets.

## Bundled Firewall References

- Current full manual: `resources/nsg-firewall/secgate3600-v3.6.6-restful-api-guide-20241220.pdf`
- Extracted text for search: `resources/nsg-firewall/secgate3600-v3.6.6-restful-api-guide-20241220.txt`
- Compact summary: `resources/nsg-firewall/secgate3600-v3.6.6-restful-api-summary.md`
- Search index: `resources/nsg-firewall/secgate3600-v3.6.6-restful-api-index.md`
- Older NSG guide retained for fallback comparison: `resources/nsg-firewall/nsg-restful-api-guide-6.1.12.72317_01.pdf`
- Local SecGate validation notes: `references/api-summary.md`
- Stable operation guide: `references/operation-guide.md`
- API coverage matrix: `references/api-coverage-matrix.md` and `references/api-coverage-matrix.csv`
- CLI: `scripts/netentsecctl.py`

When identifying an API module/function, search the extracted text or index first, then use the PDF as the authoritative source if wording or tables are ambiguous.

For account setup, transport fallback, testing sequence, and troubleshooting, read `references/operation-guide.md`.

## First-time Setup

1. Open the firewall web UI and log in with the system admin account.
2. Enable `RESTful API`.
3. Add an API operator account.
   - Role: `RESTful API管理员`
   - Login type: `RESTAPI`
   - Keep the password only in local config or an interactive secret path.

## Local Connection Rules

- The scripts include built-in local defaults for `base_url`, `username`, `password`, `insecure_tls`, and `doops_target`; no config file is required for normal local use.
- For this local environment, use `username=sysapi` and DOOPS target `zy` by default.
- Use `config/connection.local.json` only when overriding the built-in defaults for a different device or account.
- Optional fields:
  - `insecure_tls`: set `true` for self-signed firewall HTTPS certificates.
  - `doops_target`: DOOPS jump target name, defaulting to `zy` when omitted.
  - `doops_cwd`: local workspace containing `.agent/skills/doops/config.json`; keep `/Users/wwyz/Documents/网络安全智能体` for the current setup.
- Do not copy credentials into `SKILL.md`, scripts, notes, final reports, examples, or generated artifacts.
- Unless the user explicitly asks for another host, only connect to `base_url`; do not fan out to sibling HA/peer addresses.

Optional override config shape:

```json
{
  "nsg_firewall": {
    "base_url": "https://172.16.15.6:8080",
    "username": "sysapi",
    "password": "<keep-local-only>",
    "insecure_tls": true,
    "doops_target": "zy",
    "doops_cwd": "/Users/wwyz/Documents/网络安全智能体"
  }
}
```

## Supported Workflows

- Search and interpret the bundled SecGate 3600 V3.6.6.0 RESTful API guide.
- Track extracted module/function coverage across the API guide.
- Log in to the firewall API and call raw or module/function REST requests.
- Run read-only batch tests from the API coverage matrix.
- Build read-only snapshots of system info, security policies, address objects, address groups, blacklist config, batch domain blacklist, and syslog config.
- Inspect local `翻墙` control objects and their same-named policies.
- Publish a complete source-IP list into `翻墙禁止上网`.
- Publish workbook sheets `翻墙风险IP` and `翻墙风险域名` into same-named destination address objects.
- Run write workflows as dry-run plans first; apply only with `--apply` after explicit user approval.

## Transport Modes

Use `--transport doops` by default for firewall workflows that support it. Use `--transport auto` or `--transport direct` only when the user explicitly asks. Auto mode tries direct REST first and falls back to DOOPS when the local network cannot reach the firewall.

- `direct`: call `base_url` from the current machine only.
- `doops`: run the DOOPS CLI from `doops_cwd`, push the same script, temporary config, and input payload to `doops_target`, execute there, read the result back, then clean the remote workspace.
- `auto`: direct first; if direct fails, use DOOPS and include `direct_error` in the returned report.

Recommended local commands:

- `python3 scripts/nsg_snapshot.py --transport doops --pretty`
- `python3 scripts/netentsecctl.py nsg-address-ips --transport doops --object 翻墙禁止上网 --mode replace --ips-file <txt>`
- `python3 scripts/publish_block_objects.py <xlsx> --transport doops`

## API Shape

- Login: `POST /v1.0/login`
- Data: `POST /v1.0/rest/`
- Logout: `POST /v1.0/out`
- Request headers must include `Content-Type: application/json`.
- Login payload uses plaintext JSON: `{"username":"...","password":"..."}`.
- Login succeeds only when both cookies are preserved for later `/v1.0/rest/` calls:
  - `PHPSESSID=<Set-Cookie from /v1.0/login>`
  - `token=<result.token from /v1.0/login>`
- `/v1.0/rest/` payload is a JSON array containing:
  - `head.module`
  - `head.function`
  - optional `head.page_index`
  - optional `head.page_size`
  - `body`

## CLI Commands

Prefer the provided CLI for repeatable work:

- `python3 scripts/netentsecctl.py nsg-login`
- `python3 scripts/netentsecctl.py nsg-call`
- `python3 scripts/netentsecctl.py nsg-rest`
- `python3 scripts/netentsecctl.py nsg-batch-test --limit 20`
- Backward-compatible aliases may exist: `v10-login`, `v10-rest`.
- For connectivity-sensitive workflows, use the `--transport doops` commands above.

## Verified Local Notes

- Address objects and address object groups use module `obj_address`, not `obj_addr`.
- `page_size=500` can fail with `error_code=5` / `每页条数非法`; use `page_size=20` and paginate when reading object lists.
- Error `2531 无权限` means the API account lacks permission for that module/function; re-check the manual module name before assuming a real permission issue.

## Useful Read-only Calls

- System info: `dashboard / get_system_info` with `{}`
- System resources: `dashboard / get_system_resource` with `{}`
- Security policies: `sec_policy / get_sec_policy` with `{"sec_policy":[{"name":"","is_detail":true}]}`
- Address objects: `obj_address / get_obj_addr_list` with `{"obj_addr":[{"is_detail":false}]}`
- Address object groups: `obj_address / get_obj_addr_group` with `{"obj_addr":[{"is_detail":false}]}`
- Address blacklist: `addr_blacklist / get_blacklist_config` with `{"addr_blacklist_cp":{"search_key":""}}`
- Batch domain blacklist: `addr_blacklist / show_batch_domain_blacklist` with `{"addr_blacklist_cp":{"search_key":"","type":"hit_num"}}`
- Syslog server config: `syslog / get_syslog_server_config_all` with `{}`

## Local Proxy-control Objects

When asked about the current `翻墙` control objects, query `sec_policy / get_sec_policy` first to confirm policy references, then query `obj_address / get_obj_addr_list` and filter records by name:

- `翻墙禁止上网`: source address object used by policy `翻墙禁止上网`.
- `翻墙风险IP`: destination address object used by policy `翻墙风险IP`.
- `翻墙风险域名`: destination address object used by policy `翻墙风险域名`.

As of the latest local read-only verification, these are address objects, not nested address groups; their `obj_addr_group` fields were empty.

## Snapshot-first Change Workflow

- Before analyzing or changing firewall objects/policies, run a read-only local snapshot:
  `python3 scripts/nsg_snapshot.py --transport doops --pretty`
- The snapshot script reads `config/connection.local.json`, logs in directly or through DOOPS, paginates safe read-only calls, writes `snapshots/nsg_snapshot_<timestamp>.json`, and logs out.
- Use the snapshot as the source of truth for local reasoning: inspect `sections.security_policies`, `sections.address_objects`, `sections.address_object_groups`, blacklist sections, and the generated `indexes`.
- For requested writes, first produce a logical change plan from the snapshot: target object/policy, existing members, proposed additions/removals, expected final state, and rollback idea.
- Immediately before publishing any write, re-read the specific target objects from the device and compare with the snapshot-derived assumptions. If the target changed, stop and re-plan.
- After a successful write, run a new snapshot and verify the final state from the device.

## Local Proxy Blocklist Publishing

- Use fixed CLI commands for changes. Do not create one-off scripts when an existing CLI command can express the operation.
- For manually supplied source IPs that should become the complete internet-block source list, replace `翻墙禁止上网` with:
  `python3 scripts/netentsecctl.py nsg-address-ips --object 翻墙禁止上网 --mode replace --transport doops --ips-file <txt>`
- Add `--apply` only after reviewing the printed plan. In `replace` mode, old host members not present in the input are removed.
- The publisher reads workbook sheets `翻墙风险IP` and `翻墙风险域名`, normalizes domain URLs to hostnames, and updates only these destination address objects:
  - `翻墙风险IP`
  - `翻墙风险域名`
- Before any write, the publisher must re-read the live device and verify:
  - both target address objects exist exactly once;
  - `翻墙风险IP` contains only host IP members;
  - `翻墙风险域名` contains only domain members;
  - security policies named `翻墙风险IP` and `翻墙风险域名` still reference their same-named destination objects.
- If any verification fails, stop instead of writing.
- For `nsg-address-ips`, perform the same live verification for the named object and same-named security policy before writing; the target object must contain host IP members only.
- For workbook publishing, use:
  `python3 scripts/publish_block_objects.py <xlsx> --transport doops`
  and add `--apply` only after reviewing the plan.

## Workflow

1. Confirm the task is for SecGate 3600 / NSG firewall.
2. Search `resources/nsg-firewall/secgate3600-v3.6.6-restful-api-index.md` or the extracted `.txt` for the relevant module/function.
3. Check `references/api-coverage-matrix.csv` for whether the module/function has been extracted and classified.
4. Use `sysapi` and DOOPS target `zy` unless the user explicitly asks otherwise.
5. Run read-only queries before attempting writes.
6. For writes, stop after the dry-run plan and ask for explicit approval.
7. Only after approval, confirm the exact manual section and use the snapshot-first workflow.
8. Verify final state from the device after any successful write.
