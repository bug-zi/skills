---
name: 翻墙管理
description: Use when operating or extending the 翻墙 application for Zhejiang Conservatory: maintain date-filtered query logic and filters for 239 SFTP 翻墙设备 logs, 172.16.15.20 上网行为管理 logs, and firewall syslog directories 172.16.15.6/7/8; run online analysis, classify evidence strength, remove false positives, and produce deliverable处置清单.
---

# 翻墙管理

Use this skill for the `翻墙` application: 浙江音乐学院翻墙治理、翻墙记录复核、SFTP 主数据查询、20 上网行为管理账号/MAC 关联、防火墙日志查证、涉政访问、国外网站访问、挖矿线索、处置清单复核。

## Application Model

`翻墙` is an analysis application, not a one-off report. It should maintain reusable query logic and filters by data source.

Core capabilities:

- Date-filtered query: users can request `today`, `yesterday`, an absolute date such as `2026-06-04`, or a time range such as `2026-06-04 16:30` to `2026-06-04 23:59`.
- Relative range query: phrases such as `昨天到今天` mean the concrete Asia/Shanghai range from yesterday `00:00:00` through the current day/time unless the user gives a different end time.
- Source-specific filters:
  - `翻墙设备` / SFTP 239 filters.
  - `上网行为管理` / 172.16.15.20 filters.
  - `国外访问主要网站` maintained site/domain filters.
  - `涉政敏感信息` maintained category/domain/keyword filters.
  - `防火墙` / 172.16.15.6/7/8 filters when logs exist.
- Menu-based analysis:
  - `翻墙记录`: SFTP `tw_act` main evidence plus 20 MAC/account/access enrichment.
  - `国外访问`: maintained major foreign-site list matched against 20 logs.
  - `涉政敏感`: SFTP `web_act` and 20 web/ssl/app sensitive-site/category matching.
  - `挖矿线索`: mining/protocol/domain keyword matching with false-positive filters.
  - `复核剔除`: weak/false-positive records and reasons.
- Analysis mode:
  - run source-specific queries online;
  - aggregate by IP or account as requested;
  - enrich MAC/account/user/name from 20 auth logs and same-IP behavior logs;
  - summarize 20 access records for the SFTP IP set;
  - identify 翻墙应用/协议 when logs provide enough evidence, and explicitly mark unknown when they do not;
  - match maintained foreign-site lists and report whether each major site has access records;
  - query涉政敏感 site/category records and keep them separate from proxy confirmation;
  - classify as `确认翻墙`, `高疑似代理/需复核`, `国外网站访问线索`, `涉政访问线索`, `挖矿线索`, or `误判剔除`;
  - output compact deliverables only.

Date handling:

- Always convert relative dates to concrete Asia/Shanghai dates in the analysis plan and output.
- For SFTP file selection, use filename date pattern such as `tw_act_YYYYMMDD*.txt` and `web_act_YYYYMMDD*.txt`.
- For 20 logs, select current `.log`, previous `.log.1`, and date-rotated `.log.N.gz` according to the requested date; verify with sampled `tstamp/create_time`.
- For large 20 logs, prefer grep prefilter and tail/date-window probes on the log host; do not copy raw logs locally.

Default query output for `昨天到今天的翻墙日志`:

- Query SFTP `tw_act` for the whole date range.
- Extract SFTP internal IPs.
- Enrich each IP from 20 with `MAC`, `账号/学号`, `用户`, `姓名`, `认证来源/认证类型` when available.
- Summarize 20 access records for the same IPs: top app labels, top domains/SNI/URLs, destination IP/port samples, log sources, time range, and short evidence samples.
- Identify `翻墙应用/协议` from SFTP and 20 logs using the application-identification rules below.
- If the user asks for foreign-site access, match the maintained major-site list and output site-level hit/no-hit status.
- If the user asks for 涉政敏感信息, treat it as the `涉政敏感` menu: query SFTP `web_act` and 20 web/ssl/app logs with the sensitive-site filters below, and output a separate table/menu result.
- Leave unavailable fields blank; do not invent names.

## Access Pattern

Support both host/direct filesystem access and DOOPS container-escape access. Prefer `auto` behavior:

1. Try direct host path access first when the log root is mounted directly, usually `/raid5/...`.
2. If running through DOOPS/container context, use `/proc/1/root/raid5/...`; this is the container PID 1 root view exposing the host filesystem, not a normal local workstation path.
3. If local/direct host paths do not exist or permission fails, use DOOPS target `zy`.
4. In final reports, state which transport was used when it matters for coverage or troubleshooting.

Core execution rule: analyze where the logs live. Run grep/parsing/aggregation on the log host or DOOPS target; only pull back compact results such as CSV/XLSX/JSON summaries, metadata, counts, and short evidence samples. Never download raw large logs to the local workspace for analysis.

Direct check:

```bash
test -d /raid5/sftp/huashu/upload && echo host-direct-sftp-ok
test -d /raid5/syslog-remote/172.16.15.20 && echo host-direct-20-ok
```

DOOPS remote target:

```bash
doops -session <name> exec --target zy -- '<command>'
```

Key roots on the 239/syslog node:

- Host/direct SFTP receiver: `/raid5/sftp/huashu/upload`
- DOOPS/container SFTP receiver: `/proc/1/root/raid5/sftp/huashu/upload`
- Host/direct 上网行为管理 20: `/raid5/syslog-remote/172.16.15.20`
- DOOPS/container 上网行为管理 20: `/proc/1/root/raid5/syslog-remote/172.16.15.20`
- 防火墙 syslog directories:
  - host/direct: `/raid5/syslog-remote/172.16.15.6`, `/raid5/syslog-remote/172.16.15.7`, `/raid5/syslog-remote/172.16.15.8`
  - DOOPS/container: `/proc/1/root/raid5/syslog-remote/172.16.15.6`, `/proc/1/root/raid5/syslog-remote/172.16.15.7`, `/proc/1/root/raid5/syslog-remote/172.16.15.8`

Always verify file existence and latest timestamps before claiming coverage. Path prefix changes by transport: host/direct uses `/raid5/...`; DOOPS/container uses `/proc/1/root/raid5/...`.

Transport examples:

```bash
# Direct
ls -lh /raid5/sftp/huashu/upload | tail

# DOOPS
doops -session log_probe exec --target zy -- 'ls -lh /proc/1/root/raid5/sftp/huashu/upload | tail'
```

For DOOPS mode, write remote analysis outputs under `/tmp`, compress and base64 them, then retrieve with `doops read -path ...`; avoid streaming huge logs directly into the chat.

When creating helper scripts, expose or emulate these transport modes:

- `direct`: read host/direct absolute paths under `/raid5/...`.
- `doops`: upload/run the script on target `zy`, using `/proc/1/root/raid5/...`, then pull back compact outputs.
- `auto`: try `/raid5/...`; if missing, fall back to DOOPS `/proc/1/root/raid5/...`.

Do not assume the same machine always has the logs mounted locally.

Output retrieval pattern:

```bash
# On log host / DOOPS target
python3 /tmp/analyze_logs.py --out /tmp/result_dir
cd /tmp/result_dir && tar -czf /tmp/result.tar.gz .
base64 /tmp/result.tar.gz > /tmp/result.tar.gz.b64

# Local
doops read -target zy -path /tmp/result.tar.gz.b64 > result.tar.gz.b64
```

After retrieval, decode/extract locally and build the final deliverable workbook from the compact result files.

## Evidence Hierarchy

Use strict evidence labels:

- `确认翻墙`: SFTP `tw_act_*` main log hit, or a firewall/device log with explicit strong proxy/VPN protocol evidence and matching terminal context.
- `高疑似代理/需复核`: 20 logs show proxy tunnel labels or proxy-like destinations, but no SFTP main hit; requires terminal/process/time-window review.
- `国外网站访问线索`: Google/Facebook/OpenAI/YouTube/X etc. in 20 logs without SFTP; not equal to 翻墙.
- `涉政访问线索`: SFTP `web_act_*` or 20 web/category logs show 涉政 category; not automatically proxy.
- `挖矿线索`: mining domain/protocol keyword or pool/stratum/xmr evidence; separate strong mining domains from keyword accidents.
- `误判剔除`: no SFTP, zero MAC, update/safebrowsing/白名单/ordinary app telemetry, or weak keyword-only evidence.

Never say “Google = 翻墙”. Google/Chrome update, Safe Browsing, Android/Chrome services, DNS/SNI-only records, and public DNS records are weak unless supported by SFTP or stronger proxy-node behavior.

## Application Filters

The `翻墙` application must apply filters before final aggregation. Keep filters source-specific.

### 1. 翻墙设备 / SFTP Filters

Input source:

- `/raid5/sftp/huashu/upload` in direct mode.
- `/proc/1/root/raid5/sftp/huashu/upload` in DOOPS/container mode.

Date filter:

- Include only files whose names match the requested date:
  - `tw_act_YYYYMMDD*.txt`
  - `web_act_YYYYMMDD*.txt`
- Also parse the event timestamp inside each line and discard rows outside the requested time range.

Keep filters:

- `tw_act_*` rows: keep as 翻墙主数据 when the internal IP field is valid and the event time is in range.
- `web_act_*` rows: keep as 涉政/网站访问主数据 when category/domain/time/IP fields are valid.
- Tool/protocol values such as `SS`, `VLESS`, `TROJAN`, `SSL`, `IPSEC` are preserved exactly as source labels; do not rewrite them unless adding a separate normalized column.

Exclude/repair filters:

- Drop blank lines, malformed rows, or rows without a valid internal IP.
- Drop rows outside the requested date/time even if the filename matches.
- Do not merge `tw_act` and `web_act` into one proof type:
  - `tw_act` = proxy/VPN confirmation candidate.
  - `web_act` = website/涉政 category evidence.
- Do not overwrite SFTP event time with file modification time.

SFTP output fields:

- `时间`, `内网IP`, `访问IP`, `翻墙工具/协议` or `平台/站点`, `访问对象/地区`, `源文件`, `原始证据`.
- For deliverables, aggregate into `最新时间`, `首次时间`, `内网IP`, `MAC`, `账号/学号`, `用户`, `姓名`, `访问次数`, `翻墙工具/协议`, `访问IP/对象`, `访问记录摘要`, `可信度`, `研判依据`, `佐证证据`.
- Include application-identification columns when available: `翻墙协议/类型`, `设备应用分类`, `具体翻墙应用`, `应用识别依据`.

### 2. 上网行为管理 / 20 Filters

Input source:

- `/raid5/syslog-remote/172.16.15.20` in direct mode.
- `/proc/1/root/raid5/syslog-remote/172.16.15.20` in DOOPS/container mode.

Date filter:

- Use JSON fields `tstamp` and `create_time`.
- For date-range analysis, a row is included only when parsed event time is within range.
- Use file names only to choose likely files; event time is authoritative.

Keep filters:

- `authlog`: keep `client_ip`, `mac`, `fullpath`, `tstamp`, and extract `账号/学号` from `fullpath=/第三方用户/<id>`.
- If present, keep explicit user/name fields such as `user`, `username`, `user_name`, `name`, `realname`, `real_name`, `display_name`, `姓名`, `用户`, `认证用户`. Do not treat `fullpath` as a human name.
- `app_conn` and `proxy_identify`: keep rows with:
  - explicit proxy app labels, but classify as high-suspicion only unless SFTP confirms;
  - destination/SNI/domain matching foreign platforms requested by the user;
  - mining/proxy keywords after false-positive filtering.
- `ssl_log`: keep SNI/domain evidence for foreign-site supplement only.
- `web`: keep URL/category evidence for foreign-site or 涉政 supplement only.

Foreign platform keyword filters:

- Google family: `google`, `gstatic`, `googleapis`, `googlevideo`, `ytimg`, `youtube`
- Facebook/Meta: `facebook`, `fbcdn`, `instagram`, `whatsapp`
- OpenAI: `openai`, `chatgpt`, `chat.openai.com`, `chatgpt.com`
- X/Twitter: `twitter`, `x.com`, `twimg`, `t.co`

Mining keyword filters:

- Stronger: `stratum`, `xmrig`, `monero`, `cryptonight`, known mining pool domains.
- Weak: `pool`, `xmr` as substring. Use weak keywords only with supporting context; otherwise downgrade or exclude.

Exclude/downgrade filters:

- Exclude Google/Chrome background update and telemetry from risk counts:
  - `update.googleapis.com`
  - `clientservices.googleapis.com`
  - `safebrowsing.googleapis.com`
  - `optimizationguide-pa.googleapis.com`
  - `connectivitycheck.gstatic.com`
  - `gvt1.com`, `gvt2.com`
  - `firebaselogging-pa.googleapis.com`
  - `content-autofill.googleapis.com`
  - Android/Chrome update, Google Safe Browsing, connectivity checks, public DNS, telemetry.
- Exclude or downgrade rows where:
  - `MAC=00:00:00:00:00:00`;
  - no SFTP hit;
  - only Google/X/foreign-site supplement exists;
  - evidence is ordinary app update, 白名单, DNS-only, or telemetry.
- `/代理隧道/其他翻墙软件` in 20 logs is a weak label unless supported by:
  - SFTP `tw_act`;
  - repeated unusual proxy-node destinations/ports;
  - strong protocol/domain evidence;
  - same IP and same time window.
- Never attach evidence from one IP to another IP just because `fullpath` account is the same.

20 output fields:

- `时间`, `内网IP`, `MAC`, `账号/学号`, `用户`, `姓名`, `日志来源`, `访问对象`, `应用标签`, `命中类型`, `过滤状态`, `证据`.

### 3. 翻墙应用识别 Filters

The application must distinguish three concepts:

- `翻墙协议/类型`: protocol or tunnel family, often from SFTP `tw_act`, e.g. `SS`, `VLESS`, `VMESS`, `TROJAN`, `SSL`, `IPSEC`, `IKEV2`, `PROXY`.
- `设备应用分类`: device-side category label, often from 20 `app_mark`, e.g. `/代理隧道/其他翻墙软件`.
- `具体客户端应用`: software name on the terminal, e.g. `Clash`, `Mihomo`, `V2RayN`, `Shadowrocket`, `Sing-box`, `WireGuard`, `OpenVPN`, `ToDesk`, etc. This is only available when logs expose a client/app/process/name field or strong domain/signature evidence.

Do not report `其他翻墙软件` as the concrete application. It is a category label.

Application-identification sources:

- SFTP `tw_act`:
  - use field 6 as `翻墙协议/类型`;
  - does not usually reveal concrete client software.
- 20 `app_conn` / `proxy_identify`:
  - `app_mark`, `appname`, `app_name`, `policy_name`, `uri_category_id` may reveal category or software;
  - if only `/代理隧道/其他翻墙软件` appears, set concrete application to `未识别具体客户端`.
- 20 `web` / `ssl_log`:
  - use URL/SNI/domain to infer only when it contains explicit client/service names such as `clash`, `mihomo`, `v2ray`, `sing-box`, `wireguard`, `openvpn`, `tailscale`, `zerotier`, `trojan`, `vless`, `vmess`, `hysteria`, `tuic`, `shadowsocks`.
- Firewall logs:
  - use app/threat/protocol fields when present; otherwise do not infer.

Concrete application keyword map:

- `Clash/Mihomo`: `clash`, `mihomo`, `clash-verge`, `clash.meta`, `clashmeta`, `proxy-provider`
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

Output columns for application identification:

- `翻墙协议/类型`: from SFTP or strong protocol evidence.
- `设备应用分类`: from 20/firewall app category.
- `具体翻墙应用`: concrete client if identified; otherwise `未识别具体客户端`.
- `应用识别依据`: source field and sample evidence.

Confidence rules:

- `高`: explicit concrete client/software name in logs, same IP/time as SFTP or proxy event.
- `中`: strong protocol family plus repeated proxy-node behavior, but no concrete client name.
- `低`: only device category such as `/代理隧道/其他翻墙软件`.
- `未知`: no application evidence beyond SFTP protocol label.

### 4. 国外访问主要网站 Filters

The application should maintain a configurable major foreign-site list. Use it to answer: “这些主要网站有没有访问记录”.

Default maintained site groups:

- `Google`: `www.google.com`, `google.com`, `google.com.hk`, `google.ru`, `accounts.google.com`, `mail.google.com`, `drive.google.com`, `docs.google.com`, `translate.google.com`, `gemini.google.com`
- `YouTube`: `youtube.com`, `www.youtube.com`, `youtu.be`, `googlevideo.com`, `ytimg.com`
- `Facebook`: `facebook.com`, `www.facebook.com`, `graph.facebook.com`, `fbcdn.net`, `static.xx.fbcdn.net`
- `Instagram`: `instagram.com`, `cdninstagram.com`
- `WhatsApp`: `whatsapp.com`, `whatsapp.net`
- `X/Twitter`: `x.com`, `twitter.com`, `t.co`, `twimg.com`
- `OpenAI/ChatGPT`: `openai.com`, `chat.openai.com`, `chatgpt.com`, `api.openai.com`
- `Telegram`: `telegram.org`, `t.me`, `telegram.me`, `tdesktop.com`
- `GitHub`: `github.com`, `githubusercontent.com`, `githubassets.com`
- `Wikipedia`: `wikipedia.org`, `wikimedia.org`
- `BBC`: `bbc.com`, `bbc.co.uk`
- `NYTimes`: `nytimes.com`
- `Bloomberg`: `bloomberg.com`
- `Reuters`: `reuters.com`
- `Discord`: `discord.com`, `discord.gg`, `discordapp.com`
- `Reddit`: `reddit.com`, `redd.it`, `redditmedia.com`

Maintenance rules:

- Keep the list as site group -> domain patterns. Add new groups when users mention new platforms.
- Prefer host/domain matching against parsed URL host or SNI; fall back to substring matching only when structured host is unavailable.
- Do not count Chrome/Android/Google background services as `Google` risk access unless the site is explicitly user-facing.
- Keep update/noise exclusions from the 20 filters.

Fields to search in 20 logs:

- `ssl_log`: `ssl_server_name`, `server_ip`
- `web`: `url`, `title`, `url_category`, `server_ip`
- `app_conn` / `proxy_identify`: `ssl_server_name`, `app_mark`, `server_ip`, `dst_port`

Foreign-site matching output:

- `站点组`
- `是否命中`
- `命中次数`
- `内网IP数`
- `账号/学号数`
- `样例内网IP`
- `样例账号/学号`
- `样例访问对象`
- `日志来源`
- `首次时间`
- `最新时间`
- `过滤说明`

When producing an IP/account report, add a compact column:

- `主要国外网站命中`: e.g. `OpenAI(3) / YouTube(2) / Facebook(1)`

### 5. 涉政敏感 Menu / Filters

`涉政敏感` is a separate application menu. It is a content/category risk, not automatically a proxy/VPN confirmation. Keep it separate from `翻墙记录` / `tw_act` confirmation.

Primary source:

- SFTP `web_act_YYYYMMDD*.txt`
  - category field can be `涉政`.
  - observed fields include platform/site label, domain, category, internal IP, destination IP, app/category, vendor.

Supplemental 20 sources:

- `{"web".log`: `url`, `title`, `url_category`, `policy_name`, `client_ip`, `fullpath`, `mac`
- `{"ssl_log".log`: `ssl_server_name`, `server_ip`, `client_ip`, `fullpath`
- `{"app_conn".log` / `{"proxy_identify".log`: `ssl_server_name`, `app_mark`, `server_ip`, `client_ip`, `fullpath`

Keep filters:

- SFTP `web_act` rows where category is `涉政`.
- Rows matching maintained sensitive site/domain groups.
- Rows whose URL/category/title explicitly indicate political sensitive content.

Default sensitive site/domain groups:

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

Optional keyword hints:

- `涉政`, `政治`, `敏感`, `新闻`, `民主`, `人权`

Use keyword hints only as secondary evidence; prefer category/domain fields. Avoid broad keyword-only false positives.

Exclude/downgrade filters:

- Ordinary CDN/vendor names alone are not涉政.
- News sites that are accessible through CDN should be judged by requested host/domain, not CDN IP alone.
- Search result pages or browser suggestion domains are weak unless the visited target domain/content category is clear.
- If evidence is only 20 SSL SNI without category and no SFTP `web_act`, classify as `涉政敏感线索/需复核`, not confirmed涉政访问.

Output fields:

- `时间`
- `内网IP`
- `MAC`
- `账号/学号`
- `用户`
- `姓名`
- `敏感类型`: e.g. `涉政`
- `站点/平台`
- `域名/URL`
- `目的IP`
- `数据源`: `SFTP web_act` or 20 log source
- `命中次数`
- `研判结论`
- `佐证证据`

When producing a combined IP/account report, add:

- `涉政敏感命中`: e.g. `BBC(2) / NYTimes(1)`
- `涉政敏感依据`: short source-separated evidence.

Preferred menu outputs:

- `涉政敏感汇总`: aggregate by IP/account/site.
- `涉政敏感明细`: compact evidence rows from `web_act` and 20 logs.
- `口径说明`: explain that涉政 is not proxy confirmation.

## Log Reference: SFTP 翻墙设备

Path:

```bash
# host/direct
/raid5/sftp/huashu/upload

# DOOPS/container
/proc/1/root/raid5/sftp/huashu/upload
```

Important file families:

- `tw_act_YYYYMMDDHHMMSS*.txt`: 翻墙/代理 main data. This is the preferred source of truth for “确认翻墙”.
- `web_act_YYYYMMDDHHMMSS*.txt`: 网站/涉政 category main data, e.g. `涉政`, platform, domain, client IP, destination IP, vendor.
- Other `*_act_*` files may exist; inspect sample lines before using.

Observed `tw_act` format:

```text
2026-06-06 08:58:47,null,null,10.30.2.45,27.19.77.78,IPSEC,中国 湖北
```

Interpret as:

1. event time
2. unused/null
3. unused/null
4. internal IP
5. destination IP
6. tool/protocol, e.g. `SS`, `VLESS`, `TROJAN`, `SSL`, `IPSEC`
7. destination region/object

Observed `web_act` format:

```text
2026-06-05 23:12:09,null,null,BBC,www.bbc.com,涉政,10.140.12.54,199.232.160.81,其他,FASTLY.COM FASTLY.COM
```

Interpret as:

1. event time
2. unused/null
3. unused/null
4. platform/site label
5. domain
6. category, e.g. `涉政`
7. internal IP
8. destination IP
9. app/category
10. vendor/ASN/org

SFTP query workflow:

1. List files for target date:
   ```bash
   # direct
   ls -lh /raid5/sftp/huashu/upload/*_act_YYYYMMDD*.txt

   # doops
   doops -session sftp_probe exec --target zy -- 'ls -lh /proc/1/root/raid5/sftp/huashu/upload/*_act_YYYYMMDD*.txt'
   ```
2. Parse all matching `tw_act` records for the time range.
3. Aggregate by internal IP:
   - latest time, first time
   - count
   - tool/protocol counts
   - destination IP counts
   - destination region/object
   - source files and sample evidence
4. Treat `tw_act` hits as main evidence. Do not require 20 to confirm the event; 20 is for MAC/account enrichment.
5. Parse `web_act` separately for 涉政/website access. Do not mix it with proxy confirmation unless the user asks for a combined table.

## Log Reference: 上网行为管理 172.16.15.20

Path:

```bash
# host/direct
/raid5/syslog-remote/172.16.15.20

# DOOPS/container
/proc/1/root/raid5/syslog-remote/172.16.15.20
```

Common files:

- `{"authlog".log`, `.log.1`, `.log.N.gz`: user/MAC/IP online and authentication mapping.
- `{"app_conn".log`: application connection records; huge.
- `{"proxy_identify".log`: proxy identification records; huge.
- `{"ssl_log".log`: SSL/SNI records.
- `{"web".log`: URL/web browsing records.
- `{"app".log`, `{"se".log`, `{"spider".log`: auxiliary categories.

Lines are syslog header + JSON, not raw JSON:

```text
Jun  4 08:17:29 NS {"authlog": [{"client_ip":"10.130.7.45","mac":"F8:6F:B0:16:9E:3C","tstamp":"2026-06-04 08:17:29","fullpath":"10.130.7.45"}]}
```

Parsing rule:

- Strip everything before the first `{`.
- The top-level key is the log name and value is usually a one-item array.
- Use the first object inside that array.

Important fields:

- time: `tstamp`, fallback `create_time`
- internal IP: `client_ip`, fallback `user_ip`
- destination: `server_ip`, `dst_port`, `ssl_server_name`, `url`
- app/category: `app_mark`, `appname`, `policy_name`, `uri_category_id`
- MAC: `mac`
- account/student id: usually in `fullpath`, e.g. `/第三方用户/202351005005`; sometimes explicit account-like fields exist.
- user/name candidates: `user`, `username`, `user_name`, `name`, `realname`, `real_name`, `display_name`, `姓名`, `用户`, `认证用户`; if absent, leave blank.

Account/MAC enrichment:

1. Prefer `authlog` for `client_ip -> mac/account` mapping.
2. Extract account from `fullpath=/第三方用户/<id>`.
3. Extract user/name only from explicit name-like fields; `fullpath` is account path, not a human name.
4. Treat `00:00:00:00:00:00` as an unreliable placeholder MAC, not a terminal MAC.
5. If one account appears on multiple IPs, do not merge behaviors by account unless the output explicitly asks for account-level aggregation. For IP-level reports, evidence must match the same IP.
6. If no match, leave MAC/account/name blank instead of filling with historical or nearby values.

Access-record enrichment for SFTP IPs:

- Use only records whose `client_ip` or `user_ip` equals the SFTP internal IP.
- Candidate logs: `app_conn`, `proxy_identify`, `ssl_log`, `web`, `app`.
- Summarize instead of dumping raw rows:
  - first/latest time
  - row count
  - top `app_mark/appname/policy_name`
  - top `ssl_server_name/url/server_ip:dst_port`
  - source log counts
  - 3-5 evidence samples.
- Keep access summaries separate from SFTP confirmation. Access records explain activity context; SFTP still decides confirmed proxy.

20 query use cases:

- Correlate SFTP internal IP to MAC/account.
- Supplement foreign platform access:
  - Google: `google`, `gstatic`, `googleapis`, `googlevideo`, `ytimg`, `youtube`
  - Facebook/Meta: `facebook`, `fbcdn`, `instagram`, `whatsapp`
  - OpenAI: `openai`, `chatgpt`, `chat.openai.com`, `chatgpt.com`
  - X/Twitter: `twitter`, `x.com`, `twimg`, `t.co`
- Supplement mining:
  - `stratum`, `xmrig`, `xmr`, `monero`, `cryptonight`, `nicehash`, `nanopool`, `ethermine`, `2miners`, `f2pool`, `antpool`, `poolin`, `viabtc`, `slushpool`, `minexmr`, `supportxmr`, `hashvault`
- Inspect proxy labels:
  - `/代理隧道/其他翻墙软件`
  - app/proxy identification in `app_conn` and `proxy_identify`

20 false-positive rules:

- Do not treat these as proxy evidence by themselves:
  - `update.googleapis.com`
  - `clientservices.googleapis.com`
  - `safebrowsing.googleapis.com`
  - `optimizationguide-pa.googleapis.com`
  - `connectivitycheck.gstatic.com`
  - `gvt1.com`, `gvt2.com`
  - `firebaselogging-pa.googleapis.com`
  - `content-autofill.googleapis.com`
  - Android/Chrome update, Google Safe Browsing, connectivity checks, telemetry, public DNS.
- `/代理隧道/其他翻墙软件` in 20 logs can be noisy on ordinary app/update/white-list traffic. Do not use it alone for “确认翻墙”.
- DNS-only traffic to public DNS, or SNI/domain names in DNS fields, is auxiliary only.
- A row with `MAC=00:00:00:00:00:00`, no SFTP hit, and only Google/X/foreign website supplement should be excluded from deliverable处置清单 unless stronger evidence exists.
- Keyword `pool` alone is not mining; e.g. benign domains containing `pool` must be downgraded unless paired with mining context.
- Random URL parameters containing `xmr` are not XMR mining evidence.

## Log Reference: 防火墙 172.16.15.6 / 7 / 8

Syslog directories:

```bash
# host/direct
/raid5/syslog-remote/172.16.15.6
/raid5/syslog-remote/172.16.15.7
/raid5/syslog-remote/172.16.15.8

# DOOPS/container
/proc/1/root/raid5/syslog-remote/172.16.15.6
/proc/1/root/raid5/syslog-remote/172.16.15.7
/proc/1/root/raid5/syslog-remote/172.16.15.8
```

Current operational rule:

- Always `ls -lh` these directories first.
- If a directory is empty, report “directory exists but no local syslog files currently present”; do not claim firewall evidence was checked from logs.
- If files appear later, inspect names and sample lines before deciding parser fields. Firewall logs may differ from 20 JSON logs.

What to check when firewall logs exist:

- Source/internal IP, destination IP, destination port, protocol, action, policy, NAT/source zone/destination zone, threat/app name, URL/domain if present.
- Proxy/VPN indicators:
  - protocol/app names: `SS`, `SSR`, `VLESS`, `VMESS`, `TROJAN`, `Hysteria`, `WireGuard`, `OpenVPN`, `IPSEC`, `Clash`, `Mihomo`, `proxy`, `VPN`
  - unusual fixed ports to repeated external destinations
  - known proxy-node families from local cases, but do not overgeneralize.
- Confirm whether firewall logs support or contradict SFTP/20 findings:
  - same internal IP
  - overlapping time window
  - same destination IP/port/domain
  - deny/allow action and policy name

Firewall API note:

- For SecGate 3600 REST/API object and policy inspection, use the separate `secgate3600-firewall-api` skill.
- This skill is for log investigation and evidence classification, not firewall object publishing.

## Recommended Investigation Workflow

1. Define date/time range precisely.
2. Resolve transport:
   - direct host `/raid5/...` when available;
   - otherwise DOOPS `zy` with `/proc/1/root/raid5/...`.
3. Run the analysis script or grep pipeline on the log host/DOOPS target, not locally against copied raw logs.
4. Apply source filters:
   - SFTP filters for `tw_act` and `web_act`.
   - 20 filters for `authlog`, foreign platform supplement, proxy labels, and mining.
   - firewall filters only if 15.6/7/8 logs exist.
5. Query SFTP first:
   - `tw_act` for confirmed proxy.
   - `web_act` for 涉政/site category.
6. Extract internal IPs from SFTP.
7. Query 20 `authlog` for same-day MAC/account. Use `fullpath=/第三方用户/<id>`.
8. Optionally query 20 app/web/ssl/proxy logs for supplement, but keep them separate from SFTP confirmation.
9. If the request includes foreign-site access, match the maintained `国外访问主要网站` list and produce a site-level hit/no-hit summary.
10. Query firewall directories 15.6/7/8 only after confirming files exist.
11. Aggregate by the requested unit:
   - IP-level reports: never merge evidence from a different IP just because account is the same.
   - account-level reports: show all IPs separately under the account.
12. Apply false-positive filters before delivery.
13. Pull back only compact result files and produce a simple table:
   - `研判结论`
   - `问题类型`
   - `内网IP`
   - `MAC`
   - `账号/学号`
   - `用户`
   - `姓名`
   - `命中次数`
   - `工具/平台/类型`
   - `翻墙协议/类型`
   - `具体翻墙应用`
   - `访问对象`
   - `访问记录摘要`
   - `应用识别依据`
   - `研判依据`
   - `佐证证据`
   - `最近命中时间`

## Deliverable Standards

- Put final deliverables in a clearly named Excel file.
- Always sort deliverable sheets automatically before saving.
- Keep only necessary sheets for handoff. Sheet names should follow menu context:
  - `翻墙记录` or `翻墙处置清单`
  - `国外访问汇总`
  - `涉政敏感汇总`
  - `涉政敏感明细`
  - `挖矿线索`
  - optional `复核剔除记录`
  - `口径说明`
- Include the source-of-truth statement:
  - `确认翻墙以 SFTP tw_act 主日志为准；20 上网行为管理用于 MAC/账号关联和补充线索；防火墙日志如目录为空则无本地日志证据。`
- For the `涉政敏感` menu, include:
  - `涉政敏感以 SFTP web_act 和网站/分类字段为主；不等同于确认翻墙。`
- If rows are removed as false positives, keep them in `复核剔除记录` with a concise reason.
- Never hide uncertainty. Use `需复核`, `辅助线索`, or `误判剔除` when evidence is weak.

Default sorting:

- `翻墙记录` / `翻墙处置清单`:
  1. `研判结论`: `确认翻墙` first, then `高疑似代理/需复核`, then `国外网站访问线索`, then `误判剔除`.
  2. `最新时间` or `最近命中时间` descending.
  3. `命中次数` / `访问次数` descending.
  4. `账号/学号` ascending, then `内网IP` ascending.
- `国外访问汇总`:
  1. `是否命中=是` first.
  2. `命中次数` descending.
  3. `内网IP数` descending.
  4. `最新时间` descending.
  5. `站点组` ascending.
- `涉政敏感汇总`:
  1. `研判结论`: confirmed/category evidence first, then `涉政敏感线索/需复核`.
  2. `命中次数` descending.
  3. `最新时间` descending.
  4. `账号/学号` ascending, then `内网IP` ascending.
- `涉政敏感明细`:
  1. `时间` descending.
  2. `敏感类型`, `站点/平台`, `内网IP`.
- `挖矿线索`:
  1. strong mining evidence first, weak keyword-only last.
  2. `命中次数` descending.
  3. `最新时间` descending.
- `复核剔除记录`:
  1. `剔除原因` / `复核结论`.
  2. `账号/学号`, `内网IP`.

For Excel outputs, freeze the header row, enable filters, and keep the first sheet as the primary menu result requested by the user.
