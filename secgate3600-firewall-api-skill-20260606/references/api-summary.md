# SecGate 3600 Firewall API Summary

## Local SecGate 3600 REST observations

- The live web UI identifies the device as `网神SecGate3600防火墙.../V3.6.6.0`.
- The UI RESTful API setting is enabled on `HTTPS:8080`.
- The service advertises `/v1.0/login`, `/v1.0/rest`, and `/v1.0/out`.
- `POST /v1.0/login` with JSON `{"username":"...","password":"..."}` succeeds when the API account is valid and returns `success: true` plus a token.
- `/v1.0/rest/` requires both cookies:
  - `PHPSESSID=<Set-Cookie from /v1.0/login>`
  - `token=<result.token from /v1.0/login>`

## Verified module notes

- Address objects and address object groups use module `obj_address`, not `obj_addr`.
- `page_size=500` can fail with `error_code=5` / `每页条数非法`; use `page_size=20` and paginate.
- Error `2531 无权限` usually means the API account lacks permission for the module/function, but first re-check the manual module name.

## Useful read-only calls

- `dashboard / get_system_info`
- `dashboard / get_system_resource`
- `sec_policy / get_sec_policy`
- `obj_address / get_obj_addr_list`
- `obj_address / get_obj_addr_group`
- `addr_blacklist / get_blacklist_config`
- `addr_blacklist / show_batch_domain_blacklist`
- `syslog / get_syslog_server_config_all`

## Local control object notes

- `翻墙禁止上网`: source address object used by same-named security policy.
- `翻墙风险IP`: destination address object used by same-named security policy.
- `翻墙风险域名`: destination address object used by same-named security policy.
- These were verified as address objects, not nested address groups; their `obj_addr_group` fields were empty at the time of verification.
