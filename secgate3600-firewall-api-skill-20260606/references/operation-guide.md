# SecGate 3600 Firewall API Operation Guide

## Purpose

Use this guide to operate the SecGate 3600 / NSG firewall RESTful API skill safely and repeatably. Prefer read-only checks first, then dry-run plans, then writes with `--apply`.

## Account and Device Setup

On the firewall web UI:

1. Enable `RESTful API`.
2. Create or verify an API operator account.
   - Role: `RESTful API管理员`
   - Login type: `RESTAPI`
   - Password must be final, not an initial/expired/weak password.
3. Add the caller as a trusted management host if the firewall requires trusted REST API hosts.
   - For direct mode, add the current machine/source IP.
   - For DOOPS mode, add the DOOPS node source IP or the address segment used by the jump node.
4. Confirm the RESTful API management port and protocol, then use that value as `base_url`.

The scripts include built-in local defaults for the current firewall API account. No local config file is required for normal use.

Optional override config:

```bash
cd /Users/wwyz/.codex/skills/secgate3600-firewall-api
cp config/connection.example.json config/connection.local.json
```

Edit `config/connection.local.json` only when using a different firewall or account:

```json
{
  "nsg_firewall": {
    "base_url": "https://<firewall-management-ip>:<restful-api-port>",
    "username": "<restapi-username>",
    "password": "<restapi-password>",
    "insecure_tls": true,
    "doops_target": "zy",
    "doops_cwd": "/Users/wwyz/Documents/网络安全智能体"
  }
}
```

Never place real credentials in reports, prompts, examples, or generated artifacts.

## Stable Test Sequence

Run from the installed skill directory:

```bash
cd /Users/wwyz/.codex/skills/secgate3600-firewall-api
```

1. Validate the skill structure:

```bash
python3 /Users/wwyz/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

2. Check CLI surfaces:

```bash
python3 scripts/nsg_snapshot.py --help
python3 scripts/netentsecctl.py --help
python3 scripts/publish_block_objects.py --help
```

3. Test direct login:

```bash
python3 scripts/netentsecctl.py nsg-login --output json
```

4. Test read-only snapshot with automatic fallback:

```bash
python3 scripts/nsg_snapshot.py --transport auto --pretty
```

5. Test the extracted read-only API matrix:

```bash
python3 scripts/netentsecctl.py nsg-batch-test --limit 20 --output snapshots/nsg_batch_read_test.json
```

6. Test source-IP object publishing as a dry-run plan:

```bash
python3 scripts/netentsecctl.py nsg-address-ips \
  --transport auto \
  --object 翻墙禁止上网 \
  --mode replace \
  --ips-file payloads/fanqiang_forbid_internet_ips_20260601.txt
```

7. Test workbook IP/domain publishing as a dry-run plan:

```bash
python3 scripts/publish_block_objects.py <xlsx> --transport auto
```

Add `--apply` only after reviewing the dry-run plan and confirming the target object/policy names.

## Transport Behavior

- `--transport direct`: current machine calls `base_url`.
- `--transport doops`: run DOOPS from `doops_cwd`, push a temporary script/config/input bundle to `doops_target`, execute from the jump node, read the JSON result back, and clean the remote workspace.
- `--transport auto`: try direct first; if direct fails, use DOOPS. Reports include `direct_error` when fallback happens.

Use `auto` for routine work so local network or external access problems do not stop the operation path.

## Expected Success Signals

Direct login success includes:

- `success: true`
- `result.token`
- server `PHPSESSID` cookie

Snapshot success includes:

- `transport`: `direct` or `doops`
- `snapshot`: local JSON file path
- `summary.*.ok`: true for readable sections

Dry-run publishing success includes:

- `applied: false`
- `plan.input_count`
- `plan.add_count`
- `plan.remove_count`
- target object and same-named policy preflight checks are true

Write success includes:

- `applied: true`
- `verification.missing_ips` empty for IP object publishing
- `verification.missing_domains` empty for domain publishing

## Troubleshooting

### Direct mode returns TLS EOF

Observed example:

```text
<urlopen error EOF occurred in violation of protocol (_ssl.c:1129)>
```

Meaning: the current machine could not complete TLS/HTTP communication with `base_url`. Use `--transport auto` or `--transport doops`. If DOOPS also fails, the problem is not just local external access.

### DOOPS mode reaches firewall but login returns `error_code: 372`

Observed example:

```json
{"success": false, "error_code": 372}
```

The SecGate V3.6.6.0 guide maps error code `372` to `Config not exist / 配置不存在`.

Action checklist:

1. Re-check that RESTful API is enabled on the firewall.
2. Re-check the API account is a RESTAPI login user with role `RESTful API管理员`.
3. Re-save or recreate the API operator account if it was converted from a normal admin.
4. Confirm `base_url` uses the RESTful API management port, not only the web UI port.
5. Confirm the DOOPS node source IP is allowed as a trusted RESTful API management host.
6. Confirm `doops_cwd` points to a workspace that contains `.agent/skills/doops/config.json` with the target name, for example `zy`.
7. Retry:

```bash
python3 scripts/nsg_snapshot.py --transport doops --pretty
```

### Login returns password or username errors

Common manual codes:

- `226`: 管理员密码错误
- `227`: 用户名或密码错误
- `68`: 用户名或密码错误

Action: update the built-in defaults or use `config/connection.local.json` as an override, then rerun login. Do not paste passwords into prompts or reports.

### REST calls return permission errors

Common local note:

- `2531 无权限`

Action: verify the module/function name in the SecGate V3.6.6.0 guide first. If correct, grant the API account permission for that module or use a RESTful API administrator account.

## Current Verification Notes

Last local test in this workspace:

- Skill structure validation passed.
- CLI help for snapshot, netentsecctl, and workbook publisher passed.
- API coverage matrix generated from the SecGate V3.6.6.0 guide.
- Generic batch read-only test CLI added: `python3 scripts/netentsecctl.py nsg-batch-test --transport auto --limit 20`.
- Batch test auto mode reached DOOPS, then stopped at firewall login `error_code: 372`.
- Direct snapshot/login failed with TLS EOF.
- `--transport auto` successfully fell back to DOOPS.
- DOOPS execution reached the target path but firewall login returned `error_code: 372`, so the remaining blocker is firewall REST API configuration/account/trusted-host setup, not the local auto-switch control flow.
