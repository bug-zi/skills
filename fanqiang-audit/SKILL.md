---
name: fanqiang-audit
description: "Use when auditing Zhejiang Conservatory proxy/VPN activity, querying 翻墙/SFTP and 172.16.15.20 logs, generating 快速审计 or 行为评估 CSVs, checking SecGate 3600 control objects, or preparing approved firewall remediation."
---

# 翻墙审核

Use this skill for the Zhejiang Conservatory proxy/VPN audit workflow. It is self-contained for log evidence, identity enrichment, behavior evaluation, SecGate 3600 read-only verification, remediation planning, and explicitly approved firewall publishing.

## Core Rules

- Keep the workflow complete: `tw_act` evidence, identity enrichment, optional behavior context, firewall read-only verification, remediation plan, approval gate, and post-write verification when a write is approved.
- Default firewall behavior is read-only. Do not modify firewall objects, policies, logs, or raw evidence unless the user explicitly approves the exact write action in the current conversation.
- Never add `--apply` before user approval.
- Analyze large logs where they live. Do not download large raw logs locally; run grep/parsing on the log host or DOOPS target and retrieve only compact CSV/JSON summaries.
- Use UTF-8 explicitly for Chinese files and reports. Terminal mojibake alone is not evidence that the stored file is corrupt.
- Record executed commands and outcomes; redact passwords, tokens, cookies, and secrets.

## Local Structure

- `scripts/build_quick_audit.py`: build 快速审计 CSV from `tw_act` evidence plus authentication enrichment and optional control JSON.
- `scripts/query_access_windows.py`: build 行为评估 CSV from quick-audit events and narrow access-log windows.
- `scripts/build_auth_index.py`: build/reuse daily lightweight SQLite authentication indexes from 172.16.15.20 `authlog`.
- `scripts/nsg_control_check.py`: read-only SecGate 3600 control-object verification.
- `scripts/nsg_snapshot.py`: read-only SecGate 3600 snapshot collection.
- `scripts/netentsecctl.py`: SecGate 3600 CLI for read-only calls and approved address-object publishing.
- `scripts/publish_block_objects.py`: approved publishing helper for workbook sheets `翻墙风险IP` and `翻墙风险域名`.
- `references/`: local SecGate operation notes and API coverage matrix.
- `resources/nsg-firewall/`: searchable SecGate/NSG extracted text, summaries, and indexes. Large PDF manuals are intentionally not bundled here.

## Audit Modes

### 快速审计模式

Use this as the default mode when the user asks which account/student ID used proxy/VPN, when it happened, what internal IP was involved, what proxy protocol/object appeared, and whether the source is already controlled.

Default evidence:

- SFTP `tw_act`: confirmed proxy/VPN evidence.
- 172.16.15.20 `authlog`: MAC and `账号/学号` enrichment.
- SecGate 3600 read-only object inspection: optional control status used for downstream remediation, not proof that proxy/VPN happened.

Default CSV columns:

- `学号/账号`
- `翻墙时间`
- `内网IP`
- `翻墙协议/类型`
- `访问IP/对象`
- `身份时间匹配`
- `学号匹配`
- `备注`

Do not output `窗口开始`, `窗口结束`, or `管控情况` in 快速审计 CSV. Keep identity timing separate from account availability:

- `身份时间匹配`: `覆盖`, `同日IP`, or `未匹配`.
- `学号匹配`: `已匹配` or `未匹配`.

### 行为评估模式

Use this mode when the user asks for visited sites/domains, what the user did, risk interpretation, or behavior evaluation.

Run 快速审计 first, then query access context from the quick-audit event rows:

- Use each row as one event: `学号/账号 + 翻墙时间 + 内网IP + 翻墙协议/类型 + 访问IP/对象`.
- Start with a narrow window around each event, normally `±10 minutes`; expand unmatched events to `±30 minutes` at most.
- Query heavy families only with candidate `内网IP` prefilter plus event-time filtering.
- Output one behavior summary per proxy/VPN event, not one mixed whole-day summary per IP.
- Default human-review output is CSV only; JSON is optional evidence and should not be placed on the user's desktop unless requested.

Behavior CSV must include:

- `翻墙行为评估`
- `管控情况`
- compact access context such as top domains/SNI/URLs, app labels, destination IP/ports, source counts, and short samples.

Allowed `管控情况` values:

- `已管控`: the internal IP or relevant risk object member is present in the expected firewall object.
- `未管控`: the internal IP or relevant risk object member is not present in the expected firewall object.
- `对象不存在`: the expected firewall object does not exist.
- `核验失败`: firewall read-only verification failed or returned an unusable response.
- `不适用`: the row has no firewall-control target.

## Log Access and Transport

Support both direct host paths and DOOPS container-escape paths. Prefer `auto` behavior:

1. Try direct host paths under `/raid5/...` when mounted.
2. If direct paths are unavailable or permissions fail, use DOOPS target `zy`.
3. In DOOPS/container context, use `/proc/1/root/raid5/...`.
4. In reports, state the transport when it affects coverage or troubleshooting.

Key roots:

- SFTP receiver:
  - direct: `/raid5/sftp/huashu/upload`
  - DOOPS: `/proc/1/root/raid5/sftp/huashu/upload`
- 172.16.15.20 上网行为管理:
  - direct: `/raid5/syslog-remote/172.16.15.20`
  - DOOPS: `/proc/1/root/raid5/syslog-remote/172.16.15.20`
- Firewall syslog directories:
  - direct: `/raid5/syslog-remote/172.16.15.6`, `/raid5/syslog-remote/172.16.15.7`, `/raid5/syslog-remote/172.16.15.8`
  - DOOPS: `/proc/1/root/raid5/syslog-remote/172.16.15.6`, `/proc/1/root/raid5/syslog-remote/172.16.15.7`, `/proc/1/root/raid5/syslog-remote/172.16.15.8`

Always verify file existence and timestamps before claiming coverage.

DOOPS examples:

```bash
doops -session sftp_probe exec --target zy -- 'ls -lh /proc/1/root/raid5/sftp/huashu/upload | tail'
doops -session log_probe exec --target zy -- 'ls -lh /proc/1/root/raid5/syslog-remote/172.16.15.20 | tail'
```

For large remote work, write compact outputs under `/tmp`, compress/base64 them if needed, retrieve them with byte-safe methods, and build final local CSV/XLSX deliverables from the compact result files.

## DOOPS Execution Rules

Use these rules when running this skill through DOOPS:

- If DOOPS rejects the `zy` gateway with `insecure gateway URL ... is not allowed`, set `DOOPS_ALLOW_INSECURE_GATEWAY=1` only for the current command/process and retry. Do not persist this setting globally unless the user explicitly asks.
- On macOS/Linux, normal POSIX paths and shell quoting are preferred. Use paths such as `~/skills/fanqiang-audit/scripts` or run from the skill directory with `--src scripts`.
- On Windows, prefer relative paths or WSL-style paths for `doops push`. From `D:\Code\skills\fanqiang-audit`, use `doops ... push --src scripts`; do not pass `D:\...` Windows absolute paths to the wrapper because they can be mis-joined as relative paths.
- After every `doops push`, verify the remote workspace layout before executing scripts:
  ```bash
  doops -session <session> exec --target zy -- 'find /root/ws/<session> -maxdepth 2 -type f | sort | head'
  ```
  Do not assume pushed files are under `/root/ws/<session>/scripts`; depending on `--src`, they may be placed directly under `/root/ws/<session>/`.
- Avoid remote command arguments containing spaces when the same behavior can be expressed safely. For full-day audits, pass `--date YYYY-MM-DD` and let scripts use their default `00:00:00` to `23:59:59` range instead of passing `--start "YYYY-MM-DD 00:00:00"` through nested shells.
- When time arguments with spaces are unavoidable, macOS/Linux shells can usually pass single-quoted values safely; on Windows or any nested shell path, prefer a small remote shell script or argument file in `/tmp`.
- Treat mojibake in DOOPS terminal output as display-layer evidence only. Verify stored files by explicit bytes/UTF-8 decoding before reporting encoding problems.

## Remote Output Retrieval

CSV and archive retrieval from DOOPS must be byte-safe.

On macOS/Linux, plain shell redirection is acceptable only after confirming this local `doops read` emits raw file bytes without banners:

```bash
doops -session fetch read --target zy --path /tmp/result.csv > ~/Desktop/result.csv
```

Some DOOPS builds print targeting/status banners to stdout before file bytes. If the retrieved file does not start with the expected UTF-8 BOM/header, strip everything before the CSV BOM/header or use an explicit payload method. Still verify the retrieved file locally before reporting success.

On Windows PowerShell, do not use:

```powershell
doops read --target zy --path /tmp/result.csv > C:\Users\Administrator\Desktop\result.csv
```

PowerShell `>` is text redirection. It can re-encode bytes, preserve terminal status banners, or leave a file that is not valid UTF-8 even when the remote CSV is correct.

Use one of these safer patterns instead:

- On macOS/Linux, use ordinary shell redirection only after confirming `doops read` emits raw file bytes without status banners. If banners can appear, use an explicit payload method or cleanly strip everything before the CSV BOM/header.
- On Windows, prefer a byte-safe local retrieval helper or script that captures only file bytes and writes with `[System.IO.File]::WriteAllBytes`.
- On Windows with WSL, run `doops read` inside WSL and redirect to a `/mnt/c/...` path so the shell writes raw bytes:
  ```bash
  DOOPS_ALLOW_INSECURE_GATEWAY=1 ~/.local/bin/doops -session fetch read --target zy --path /tmp/result.csv > /mnt/c/Users/Administrator/Desktop/result.csv
  ```
- On any OS, if command output may include banners, retrieve a compressed/base64 artifact with explicit start/end markers, extract only the payload, decode bytes locally, then write bytes with an OS-appropriate byte writer.
- After retrieval, verify locally with explicit UTF-8 decoding and CSV parsing before reporting success.

Required local verification:

- Decode CSV as `utf-8-sig`.
- Confirm the header exactly matches the expected columns.
- Check that no DOOPS banner or WSL warning text appears before the UTF-8 BOM/header.
- If a banner is present before a valid CSV BOM/header, rewrite the local file from the BOM/header forward before delivery.
- Check that every CSV row has the same field count as the header.
- Remove trailing empty rows from final CSV deliverables when they are artifacts of transport or rewriting.
- Check common mojibake markers such as `锟`, `�`, `Ã`, and `Â`; if present, inspect raw bytes before concluding file corruption.

## Date Handling

- Convert relative dates to concrete Asia/Shanghai ranges before querying.
- For SFTP, select files by filename date such as `tw_act_YYYYMMDD*.txt` and `web_act_YYYYMMDD*.txt`, then parse event timestamps inside lines and discard out-of-range rows.
- For 172.16.15.20 logs, select current `.log`, previous `.log.1`, and rotated `.log.N.gz` files by date, but treat parsed `tstamp` or `create_time` as authoritative.
- Do not overwrite event time with file modification time.

## Evidence Hierarchy

Use strict labels:

- `确认翻墙`: SFTP `tw_act_*` hit, or firewall/device log with explicit strong proxy/VPN protocol evidence and matching terminal context.
- `高疑似代理/需复核`: 172.16.15.20 logs show proxy tunnel labels or proxy-like destinations, but no SFTP main hit.
- `国外网站访问线索`: Google/Facebook/OpenAI/YouTube/X etc. in access logs without SFTP; not equal to 翻墙.
- `涉政访问线索`: SFTP `web_act_*` or 20 web/category logs show 涉政 category; not automatically proxy.
- `挖矿线索`: mining domain/protocol keyword or pool/stratum/xmr evidence after false-positive filtering.
- `误判剔除`: no SFTP, zero MAC, update/safebrowsing/white-list/ordinary telemetry, or weak keyword-only evidence.

Never say “Google = 翻墙”. Google/Chrome update, Safe Browsing, Android/Chrome services, DNS/SNI-only records, and public DNS records are weak unless supported by SFTP or stronger proxy-node behavior.

## SFTP 翻墙设备 Logs

Input source:

- direct: `/raid5/sftp/huashu/upload`
- DOOPS: `/proc/1/root/raid5/sftp/huashu/upload`

Important families:

- `tw_act_YYYYMMDDHHMMSS*.txt`: proxy/VPN main data and preferred source of truth for `确认翻墙`.
- `web_act_YYYYMMDDHHMMSS*.txt`: website/content-category evidence such as `涉政`; keep separate from proxy confirmation.

Observed `tw_act` format:

```text
2026-06-06 08:58:47,null,null,10.30.2.45,27.19.77.78,IPSEC,中国 湖北
```

Interpret as event time, unused, unused, internal IP, destination IP, tool/protocol, and destination region/object.

Observed `web_act` format:

```text
2026-06-05 23:12:09,null,null,BBC,www.bbc.com,涉政,10.140.12.54,199.232.160.81,其他,FASTLY.COM FASTLY.COM
```

Interpret as event time, unused, unused, platform/site, domain, category, internal IP, destination IP, app/category, and vendor/ASN/org.

SFTP rules:

- Keep `tw_act` rows with valid internal IP and in-range event time.
- Preserve source tool/protocol labels such as `SS`, `VLESS`, `VMESS`, `TROJAN`, `SSL`, `IPSEC`; add normalized columns only if needed.
- Parse `web_act` separately for 涉政/website access.
- Drop blank, malformed, invalid-IP, and out-of-range rows.

## 172.16.15.20 上网行为管理 Logs

Input source:

- direct: `/raid5/syslog-remote/172.16.15.20`
- DOOPS: `/proc/1/root/raid5/syslog-remote/172.16.15.20`

Common files:

- `{"authlog".log`, `.log.1`, `.log.N.gz`: user/MAC/IP online and authentication mapping.
- `{"ssl_log".log`: SSL/SNI context.
- `{"web".log`: URL/web context.
- `{"app_conn".log`, `{"proxy_identify".log`, `{"app".log`: heavy application/proxy context.

Lines are syslog header plus JSON. Strip everything before the first `{`; the top-level key is the log family and the value is usually a one-item array.

Important fields:

- event time: `tstamp`, fallback `create_time`
- internal IP: `client_ip`, fallback `user_ip`
- destination: `server_ip`, `dst_port`, `ssl_server_name`, `url`
- app/category: `app_mark`, `appname`, `app_name`, `policy_name`, `uri_category_id`
- MAC: `mac`
- account/student ID: usually `fullpath=/第三方用户/<id>`
- user/name candidates: `user`, `username`, `user_name`, `name`, `realname`, `real_name`, `display_name`, `姓名`, `用户`, `认证用户`

Identity enrichment rules:

- Prefer `authlog` for `client_ip -> MAC/account` mapping.
- Use `scripts/build_auth_index.py` to build/reuse a daily SQLite index under `/tmp/fanqiang_indexes` by default.
- Match by internal IP plus `tw_act` hit time. Strongest match is when the hit time falls inside the authentication session interval.
- If the same IP maps to different accounts or MACs in the range, mark `需复核`; do not guess.
- Treat `00:00:00:00:00:00` as an unreliable placeholder MAC.
- Leave unavailable account/name fields blank; do not fill them from unrelated IPs or historical values.

Access enrichment rules:

- Do not use 172.16.15.20 access logs as the source for confirmed proxy/VPN behavior; use them for context.
- Match only records whose `client_ip` or `user_ip` equals the SFTP internal IP.
- Start with `ssl_log` when lightweight context is enough.
- Treat `app_conn`, `proxy_identify`, `web`, and `app` as heavy families; query them only by event window and candidate IP.
- Summarize first/latest time, row count, top apps, top SNI/URL/server IP:port, source family counts, and short evidence samples.

False-positive rules:

- Exclude or downgrade Google/Chrome background update and telemetry:
  - `update.googleapis.com`
  - `clientservices.googleapis.com`
  - `safebrowsing.googleapis.com`
  - `optimizationguide-pa.googleapis.com`
  - `connectivitycheck.gstatic.com`
  - `gvt1.com`, `gvt2.com`
  - `firebaselogging-pa.googleapis.com`
  - `content-autofill.googleapis.com`
- `/代理隧道/其他翻墙软件` in 20 logs is weak unless supported by SFTP, repeated unusual proxy-node destinations/ports, strong protocol/domain evidence, or same-IP same-window corroboration.
- Keyword `pool` alone is not mining; `xmr` inside random URL parameters is not enough for XMR mining.
- Never attach evidence from one IP to another just because the account is the same.

## Application and Site Classification

Distinguish these fields:

- `翻墙协议/类型`: protocol or tunnel family, usually from SFTP `tw_act`, such as `SS`, `VLESS`, `VMESS`, `TROJAN`, `SSL`, `IPSEC`, `IKEV2`, `PROXY`.
- `设备应用分类`: device-side category from 20/firewall app fields, such as `/代理隧道/其他翻墙软件`.
- `具体翻墙应用`: concrete client if logs expose it, such as `Clash`, `Mihomo`, `V2RayN`, `Shadowrocket`, `Sing-box`, `WireGuard`, `OpenVPN`.

Do not report `其他翻墙软件` as the concrete client. Use `未识别具体客户端` when only a category label exists.

Common concrete-client hints:

- `Clash/Mihomo`: `clash`, `mihomo`, `clash-verge`, `clash.meta`, `proxy-provider`
- `V2Ray/Xray`: `v2ray`, `v2rayn`, `xray`, `vless`, `vmess`
- `Shadowsocks`: `shadowsocks`, `ss-local`, `ssr`, `shadowsocksr`
- `Trojan`: `trojan`
- `Sing-box`: `sing-box`, `singbox`
- `Hysteria`: `hysteria`, `hy2`
- `TUIC`: `tuic`
- `WireGuard`: `wireguard`, `wgcf`
- `OpenVPN`: `openvpn`
- `Tailscale`: `tailscale`
- `ZeroTier`: `zerotier`

Default major foreign-site groups:

- `Google`: `google.com`, `google.com.hk`, `accounts.google.com`, `mail.google.com`, `drive.google.com`, `docs.google.com`, `translate.google.com`, `gemini.google.com`
- `YouTube`: `youtube.com`, `youtu.be`, `googlevideo.com`, `ytimg.com`
- `Facebook`: `facebook.com`, `fbcdn.net`, `instagram.com`, `whatsapp.com`, `whatsapp.net`
- `OpenAI/ChatGPT`: `openai.com`, `chat.openai.com`, `chatgpt.com`, `api.openai.com`
- `X/Twitter`: `x.com`, `twitter.com`, `t.co`, `twimg.com`
- `Telegram`: `telegram.org`, `t.me`, `telegram.me`, `tdesktop.com`
- `GitHub`: `github.com`, `githubusercontent.com`, `githubassets.com`
- `Wikipedia`: `wikipedia.org`, `wikimedia.org`
- `BBC`: `bbc.com`, `bbc.co.uk`
- `NYTimes`: `nytimes.com`
- `Bloomberg`: `bloomberg.com`
- `Reuters`: `reuters.com`
- `Discord`: `discord.com`, `discord.gg`, `discordapp.com`
- `Reddit`: `reddit.com`, `redd.it`, `redditmedia.com`

Default sensitive-site groups:

- `BBC`: `bbc.com`, `bbc.co.uk`
- `NYTimes`: `nytimes.com`
- `Bloomberg`: `bloomberg.com`
- `Reuters`: `reuters.com`
- `VOA`: `voanews.com`
- `RFA`: `rfa.org`
- `DW`: `dw.com`
- `The Guardian`: `theguardian.com`
- `The Economist`: `economist.com`
- `Wikipedia`: `wikipedia.org`, `wikimedia.org`

涉政敏感 is a separate content/category risk and does not automatically confirm proxy/VPN. Prefer SFTP `web_act` category/domain evidence; classify weak SSL/SNI-only evidence as `涉政敏感线索/需复核`.

## Firewall Syslog Reference

Firewall syslog directories are 172.16.15.6, 172.16.15.7, and 172.16.15.8 under the direct or DOOPS roots listed above.

Always `ls -lh` these directories first. If a directory exists but has no local syslog files, report that explicitly and do not claim firewall-log evidence was checked.

When files exist, inspect sample lines before deciding parser fields. Look for source IP, destination IP/port, protocol, action, policy, NAT/source/destination zone, threat/app name, URL/domain, and proxy/VPN indicators.

## SecGate 3600 Read-only Verification

Use local scripts and bundled references in this skill. Search `resources/nsg-firewall/secgate3600-v3.6.6-restful-api-index.md` or the extracted `.txt` when an API module/function is unclear.

Default local firewall assumptions:

- REST API shape:
  - login: `POST /v1.0/login`
  - data: `POST /v1.0/rest/`
  - logout: `POST /v1.0/out`
- Login response must preserve both `PHPSESSID` and `token`.
- Address objects use module `obj_address`, not `obj_addr`.
- `page_size=500` can fail; use `page_size=20` and paginate when reading object lists.
- Use DOOPS target `zy` by default when firewall access is needed.
- The scripts intentionally do not bundle real passwords. Provide credentials through a local `config/connection.local.json`, command-line arguments, or an approved interactive secret path; never write real credentials into reports, prompts, examples, or generated artifacts.

Useful read-only calls:

- `dashboard / get_system_info`
- `dashboard / get_system_resource`
- `sec_policy / get_sec_policy`
- `obj_address / get_obj_addr_list`
- `obj_address / get_obj_addr_group`
- `addr_blacklist / get_blacklist_config`
- `addr_blacklist / show_batch_domain_blacklist`
- `syslog / get_syslog_server_config_all`

Local control objects:

- `翻墙禁止上网`: source address object used by same-named security policy.
- `翻墙风险IP`: destination address object used by same-named security policy.
- `翻墙风险域名`: destination address object used by same-named security policy.

Routine read-only commands:

```bash
python3 scripts/nsg_control_check.py --help
python3 scripts/nsg_snapshot.py --transport doops --pretty
python3 scripts/netentsecctl.py nsg-batch-test --limit 20
```

If firewall read-only verification fails, record the failed API section, error text, and whether any partial section succeeded. Do not infer object or policy status from a failed API response.

## Approved Firewall Publishing

Publishing scripts are bundled for approved remediation only. They are not part of the default audit path.

Before any write:

1. Generate a candidate action list and remediation plan.
2. Explain target object, additions/removals, existing items, skipped items and reasons, affected policy, expected result, and rollback idea.
3. Stop for explicit user approval in the current conversation.
4. Re-read the live target object and policy immediately before writing. If live state changed, stop and re-plan.
5. Add `--apply` only when the approved command exactly matches the user's approval.
6. Run post-write verification and report final state.

Approved write helpers:

```bash
# Dry-run only until explicit approval.
python3 scripts/netentsecctl.py nsg-address-ips --transport doops --object 翻墙禁止上网 --mode replace --ips-file <txt>

# Dry-run only until explicit approval.
python3 scripts/publish_block_objects.py <xlsx> --transport doops
```

`publish_block_objects.py` expects workbook sheets `翻墙风险IP` and `翻墙风险域名`, normalizes domain URLs to hostnames, and updates only those same-named destination address objects when approved.

## Candidate Action List

For remediation planning, build a candidate list with at least:

- `学号/账号`
- `翻墙时间`
- `内网IP`
- `MAC`
- `身份匹配状态`
- `管控情况`
- `研判结论`
- `问题类型`
- `翻墙协议/类型`
- `访问对象`
- `最近命中时间`
- `证据来源`
- `证据摘要`
- `处置建议`
- `建议目标对象`

Allowed `建议目标对象` values:

- `翻墙禁止上网`
- `翻墙风险IP`
- `翻墙风险域名`
- `无需处置`
- `需复核`

## Default Workflow

1. Convert the requested date/range into concrete Asia/Shanghai start and end times.
2. Resolve log transport: direct `/raid5/...` or DOOPS `zy` with `/proc/1/root/raid5/...`.
3. Query SFTP `tw_act_YYYYMMDD*.txt` for the requested range.
4. Extract time, internal IP, destination IP, protocol/type, access object, source file, and short sample evidence.
5. Build or reuse the daily 172.16.15.20 authentication index and enrich MAC/account/student ID by internal IP and hit time.
6. Generate 快速审计 CSV. Keep `身份时间匹配` and `学号匹配` separate; do not include `管控情况`.
7. When behavior evaluation is requested, run `scripts/query_access_windows.py` from the quick-audit events and output behavior CSV with `翻墙行为评估` and `管控情况`.
8. When control status or remediation planning is needed, use local SecGate scripts in read-only mode to verify control objects and policies.
9. Apply false-positive filtering and classify evidence.
10. Generate candidate action list and remediation plan when needed.
11. Stop for explicit approval before any write.
12. After approved execution, verify object members and policy references from the live device and generate the final disposition result.

## Performance Requirements

- Query `tw_act` first to shrink the internal IP set.
- Build authentication indexes once per day and reuse them.
- Query access logs only when context is requested or needed.
- Prefer `ssl_log` as the first lightweight behavior pass.
- For heavy families, use deduplicated fast-audit events with `内网IP + 翻墙时间` windows.
- Use streaming line-by-line parsing and system prefilters such as `grep` / `zgrep`.
- Keep raw logs on the log host and retrieve compact outputs only.

## Output Standards

Before approval, deliver compact audit outputs:

- 快速审计 CSV.
- 行为评估 CSV when requested.
- Identity coverage summary.
- Access context coverage summary when requested.
- Firewall read-only verification and failures.
- Remediation plan and review-required items when remediation is requested.

If producing Excel workbooks, keep only necessary sheets, freeze header rows, enable filters, and sort primary sheets consistently. Include口径说明:

- `确认翻墙以 SFTP tw_act 主日志为准；20 上网行为管理用于 MAC/账号关联和补充线索；防火墙日志如目录为空则无本地日志证据。`
- `涉政敏感以 SFTP web_act 和网站/分类字段为主；不等同于确认翻墙。`
