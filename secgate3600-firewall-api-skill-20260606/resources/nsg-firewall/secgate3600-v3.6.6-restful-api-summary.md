# SecGate 3600 V3.6.6.0 RESTful API Summary

Source PDF: `secgate3600-v3.6.6-restful-api-guide-20241220.pdf`

## URL Model

```text
POST /v1.0/login
POST /v1.0/rest/
POST /v1.0/out
```

## Request Rules

- Header must include `Content-Type: application/json`.
- Login body is plaintext JSON with `username` and `password`.
- After login, preserve `PHPSESSID` and set lowercase cookie `token=<returned-token>`.
- `/v1.0/rest/` body is a JSON array containing objects with `head` and `body`.
- Typical head fields: `module`, `function`, `page_index`, `page_size`.

## Functions Extracted From Examples

```text
 
clear_decrypt_bypass_sni_domain_hitnum_one
 
get_snat_trans_ip_state_by_filter
 
set_move_sec_policy_group_member_pri
 
set_sec_policy_task_generate_policy 
 add_sec_policy_learn_task
 del_pnf_group
 del_sec_policy_learn_task 
 del_service_custom
 del_service_grp
 set_sec_policy_group_state 
 set_sec_policy_learn_task_state 

 set_snat_conf
 set_vlan_conf
add_admin_host_addr
add_admin_mac
add_admin_user
add_batch_blacklist
add_batch_domain_blacklist
add_blacklist_ip
add_blacklist_mac
add_bridge
add_decrypt_bypass_sni_domain
add_decrypt_policy
add_dnat_conf
add_dns_domain_blacklist
add_dns_domain_whitelist
add_dns_honeypot_domain_one
add_honeypot_policy
add_inf_phy
add_ips_profile
add_ips_profile 
add_ips_profile_scene
add_ips_sig
add_obj_addr_conf
add_obj_addr_group
add_obj_area_custom
add_obj_lkdt
add_pnf_group
add_profile_group
add_qos_class_conf
add_qos_line_conf
add_qos_policy_conf
add_qos_root_class_conf
add_route_policy
add_route_static
add_schedule_conf
add_sec_policy
add_sec_policy_group
add_sec_policy_learn_task
add_server_conf
add_service_custom
add_service_grp
add_sfc
add_sfc_policy
add_snat_conf
add_snmpv3usr
add_ssl_decrypt_profile
add_ssl_ins_profile
add_syslog_server_config
add_threat_disposal
add_trap_server
add_vlan_conf
add_whitelist_ip
add_zone
clear_batch_blacklist_hitnum
clear_batch_domain_blacklist_hitnum
clear_batch_domain_blacklist_hitnum_all
clear_blacklist_hitnum
clear_blacklist_hitnum_one
clear_decrypt_bypass_sni_domain_hitnum_all
clear_decrypt_bypass_sni_domain_hitnum_one
clear_dnat_hitnum
clear_dns_domain_hit_num
clear_snat_hitnum
clear_whitelist_hitnum
clear_whitelist_hitnum_one
del_admin_host_addr
del_admin_mac
del_admin_user
del_batch_blacklist
del_batch_blacklist_all
del_batch_domain_blacklist
del_batch_domain_blacklist_all
del_blacklist_by_id
del_bridge
del_cloud_basic_intelligence_info
del_decrypt_bypass_sni_domain
del_decrypt_cert_signer
del_decrypt_policy
del_dnat_conf
del_dns_domain
del_dns_honeypot_domain_one
del_ha_group_conf
del_honeypot_policy
del_honeypot_policy_hitnum
del_inf_phy
del_ips_profile
del_ips_profile_scene
del_ips_sig
del_ips_sig 

del_obj_addr_conf
del_obj_addr_conf 
del_obj_addr_group
del_obj_area_custom
del_obj_lkdt
del_pnf_group
del_profile_group
del_qos_class_tree_conf
del_qos_line_conf
del_qos_policy_conf
del_route_policy
del_route_policy_hitnum
del_route_static
del_schedule_conf
del_sec_policy
del_sec_policy_group
del_sec_policy_hitnum
del_server
del_service_custom
del_service_grp
del_sfc
del_sfc_policy
del_sfc_policy_hitnum
del_snat_conf
del_snmpv3usr
del_ssl_decrypt_profile
del_ssl_ins_profile
del_syslog_server_config
del_threat_disposal
del_trap_server
del_vlan_conf
del_whitelist_by_id
del_zone
export_area_custom
export_sysconfig_ftp
get_admin_host
get_admin_mac
get_admin_port
get_admin_user
get_admin_user_detail
get_alg_list
get_app_ctl
get_app_proto_scene
get_area_list
get_authsrv_list
get_authsrv_member_group
get_authsrv_member_role
get_authsrv_member_user
get_batch_domain_blacklist_commit_status
get_blacklist_config
get_bridge_conf_list
get_channel_inf_conf
get_cloud_notice_msg_num
get_connection_monitor
get_cpu_usage
get_decrypt_cert_issue_addr_list
get_decrypt_certlearn_info
get_defence_scene_class
get_defence_type_info
get_disk_usage
get_dnat_conf
get_dnat_list
get_dnat_list_by_filter
get_dns_domain_list
get_focus_focus
get_ha_compare_cfg
get_ha_global_config
get_ha_group_id_list
get_ha_group_list
get_ha_track_bfd_list
get_ha_track_if_list
get_ha_track_ip_list
get_ha_track_pnf_list
get_honeypot_policy
get_honeypot_policy_filter
get_honeypot_policy_name
get_interface_conf
get_interface_info
get_interface_select_list
get_ips_sig
get_ips_sig_all
get_log_send_template_list
get_log_syslog_config
get_memory_usage
get_nat64_conf
get_network_monitor
get_notice_info
get_notice_num_day
get_obj_addr_group
get_obj_addr_list
get_obj_lkdt
get_obj_lkdt_list
get_obj_lkdt_ref_list
get_obj_lkdt_textvalue_list
get_obj_sche_list
get_pki_gwcert
get_pnf_group_list
get_profile_detail
get_profile_group
get_profile_info
get_profile_info_scene
get_qos_class_quota_use
get_qos_policy_list
get_route_all_list
get_route_policy_list
get_route_single_static
get_scene_class_rules
get_search_app_list_for_rule
get_sec_learn_policy_name
get_sec_policy
get_sec_policy_adjacent_merged_info
get_sec_policy_export
get_sec_policy_group
get_sec_policy_group_filter
get_sec_policy_group_name
get_sec_policy_hitinfo_filter
get_sec_policy_include
get_sec_policy_name
get_sec_policy_part_include
get_sec_policy_part_useless
get_sec_policy_region_merged_info
get_sec_policy_task
get_sec_policy_useless
get_server_conf
get_server_list
get_server_search
get_service_chain_monitor
get_service_custom
get_service_grp
get_service_predef
get_sfc_name_list_bypass
get_sfc_policy
get_sfc_policy_filter
get_sfc_policy_name
get_smac_conf
get_snat_conf
get_snat_list
get_snat_list_by_filter
get_snat_trans_ip_state
get_snat_trans_ip_state_by_filter
get_snmp_agent
get_snmpv3usr
get_ssl_decrypt_profile
get_ssl_ins_cert
get_ssl_ins_profile
get_sys_advanced_status
get_syslog_server_config_all
get_syslog_server_config_one
get_syslog_server_list
get_system_hostname
get_system_info
get_system_resource
get_threat_disposal
get_threat_disposal_statitics
get_threat_monitor
get_threat_threats
get_trap_server
get_vlan_conf
get_vlan_conf_list
get_vlan_ref_modle
get_vsys_info
get_vsys_info_specify
get_whitelist_config
get_whitelist_config_by_id
get_zone_list
import_area_custom
import_batch_blacklist_ip
import_sysconfig_ftp
set_add_nat64_prefix
set_admin_port
set_admin_user
set_alg_conf
set_app_ctl_proto
set_auto_upgrade_conf
set_auto_upgrade_immediately
set_av_add_profile
set_av_custom_add
set_av_custom_del
set_av_del_profile
set_av_edit_profile
set_batch_blacklist_match_mod
el
set_batch_blacklist_match_model
set_batch_domain_blacklist_commit
set_blacklist_match_model
set_bridge_conf
set_decrypt_bypass_sni_domain
set_decrypt_cert_issue
set_decrypt_cert_trustCA_default
set_decrypt_mirror_dport_offset
set_decrypt_policy
set_decrypt_policy_pri
set_del_nat64_prefix
set_dnat_conf
set_dnat_move
set_dnat_status
set_dns_domain_blacklist
set_dns_domain_whitelist
set_dns_honeypot_addr
set_ha_global_config
set_ha_group_conf
set_ha_group_conf 
set_ha_group_demotion_force
set_ha_group_trackbfd
set_ha_group_trackif
set_ha_group_trackip
set_ha_group_trackpnf
set_ha_sync_cfg_force
set_honeypot_policy
set_if_config_web
set_ips_profile
set_ips_profile_scene
set_ips_sig
set_ips_sig_commit
set_log_syslog_config
set_move_honeypot_policy_pri
set_move_sec_policy_group_member_pri
set_move_sec_policy_pri
set_move_sfc_policy_pri
set_ntp_conf
set_obj_addr_conf
set_obj_addr_conf 
set_obj_addr_group
set_obj_area_custom
set_obj_lkdt
set_obj_schedule
set_pnf_group
set_pnf_group_bypass
set_profile_group
set_qos_class
set_qos_line_interface
set_qos_policy_conf
set_reset_vsys
set_reset_vsys 
set_route_policy_move
set_route_static
set_save_sysconfig
set_sec_policy
set_sec_policy_group
set_sec_policy_group_state
set_sec_policy_import
set_sec_policy_learn_task
set_sec_policy_state
set_server_conf
set_service_custom
set_service_grp
set_sfc
set_sfc_bypass
set_sfc_policy
set_sfc_policy_state
set_smac_conf
set_snat_conf
set_snat_move
set_snat_status
set_snmp_agent
set_snmpv3usr
set_ssl_decrypt_profile
set_ssl_ins_profile
set_sys_advanced_status
set_syslog_server_config
set_system_time
set_threat_disposal
set_trap_server
set_vlan_conf
set_vlan_igmp_snooping
set_vsys
set_zone
show_all_interface_web
show_av_md5_custom
show_av_profile
show_batch_blacklist
show_batch_blacklist_match_
model
show_batch_blacklist_match_mo
del
show_batch_domain_blacklist
show_blacklist_match_model
show_cld_cloud_basic_abnormal_host_statistics
show_cld_cloud_basic_intelligence_statistics
show_cloud_basic_intelligence_info
show_decrypt_bypass_sni
show_decrypt_cert_issue
show_decrypt_cert_signer
show_decrypt_cert_trustCA
show_decrypt_mirror_config
show_decrypt_policy
show_dns_honeypot_addr
show_dns_honeypot_domain
show_sfc
show_web_qos_class_one
show_web_qos_class_tree
show_web_qos_line_tree
```

## Headings

```text
1 前  言 ................................................................................................................... 53
2 RESTful API 概述 ................................................................................................. 54
3 RESTful API JSON 结构 ....................................................................................... 58
4 认证和注销 API..................................................................................................... 61
5 首页 API ............................................................................................................... 66
6 非状态检测 API................................................................................................... 119
7 虚拟系统管理 API ............................................................................................... 123
8 配置文件 API ...................................................................................................... 141
9 VLAN 配置 API ................................................................................................... 146
10 桥配置 API ........................................................................................................ 160
11 网络接口 API .................................................................................................... 170
12 QoS 管理 API .................................................................................................... 204
13 安全策略 API .................................................................................................... 259
14 NAT 策略 API .................................................................................................... 420
15 蜜罐策略 API .................................................................................................... 528
16 威胁引流 API .................................................................................................... 550
17 检测解密对象 API ............................................................................................. 562
18 SSL 代理自定义白名单 API ............................................................................... 573
19 解密全局配置 API ............................................................................................. 587
20 SSL 服务器证书 API.......................................................................................... 590
21 SSL 解密证书 API ............................................................................................. 602
22 SSL 解密策略 API ............................................................................................. 619
23 引流策略 API .................................................................................................... 636
24 服务链管理 API................................................................................................. 662
25 服务链监控 API................................................................................................. 672
26 网元管理 API .................................................................................................... 677
27 静态路由 API .................................................................................................... 688
28 策略路由 API .................................................................................................... 702
29 链路探测 API .................................................................................................... 715
30 高可用性 API .................................................................................................... 734
31 对象配置 API .................................................................................................... 776
32 安全域 API ........................................................................................................ 881
33 入侵防御 API .................................................................................................... 889
34 入侵防御自定义签名 API .................................................................................. 980
35 反病毒 API ...................................................................................................... 1009
36 反病毒自定义签名 API .................................................................................... 1038
37 安全配置文件组 API ....................................................................................... 1044
38 特征库升级 API............................................................................................... 1054
39 管理员用户 API............................................................................................... 1075
40 SNMP API ....................................................................................................... 1089
41 集中管理 API .................................................................................................. 1109
42 时间配置 API ................................................................................................... 1114
43 NTP API ........................................................................................................... 1116
44 管理主机 API .................................................................................................. 1120
45 系统日志 API .................................................................................................. 1135
46 日志统计 API .................................................................................................. 1156
47 配置保存 API .................................................................................................. 1183
48 管理证书 API .................................................................................................. 1185
49 黑白名单 API .................................................................................................. 1188
50 失陷主机 API .................................................................................................. 1263
51 人工处置 API .................................................................................................. 1290
52 ALG 配置 API .................................................................................................. 1357
1 前  言
2 RESTful API 概述
0 0
3 RESTful API JSON 结构
4 认证和注销 API
0 认证成功 - 创建
1 管理员初始密码 防火墙管理员的初始密码 创建
2 管理员弱密码 防火墙管理员密码不符合规范 创建
3 远程管理员弱密码 防火墙管理员密码不符合规范 创建
4 管理员地址锁定 - 不创建
5 管理员用户名锁定 - 不创建
6 管理员密码超有限期 - 创建
7 管理员会话到达上限 - 不创建
475 管理员不存在 - 不创建
226 管理员密码错误 - 不创建
0 下线成功 - 删除
8 下线失败 - 不删除
5 首页 API
20 20
20 20
2000 - string
2000 - number
2000 numbe
2000 - number
2000 numbe
6 非状态检测 API
7 虚拟系统管理 API
100 20
100 20
8 配置文件 API
9 VLAN 配置 API
10 桥配置 API
11 网络接口 API
50 Int
50 Int
50 Int
12 QoS 管理 API
100 20
1 - int
100 - int
63 或者
63 或者
1 - int
20 - int
13 安全策略 API
14 NAT 策略 API
0 0 disable
1 enable
0 1024-65535 int
0 1024-65535 int
1 enable
20 - -
0 0 disable
1 enable
0 1024-65535 int
0 1024-65535 int
0 64-64512 int
20 - -
0 0 disable
1 enable
0 1024-65535 int
0 1024-65535 int
0 0 disable int
0 1024-65535 int
0 1024-65535 int
0 0 disable
1 enable
0 1024-65535 int
0 1024-65535 int
20 - -
0 0 disable
1 enable
0 1024-65535 int
0 1024-65535 int
0 0 disable
1 enable
0 1024-65535 int
0 1024-65535 int
20 - -
0 0 disable
1 enable
06 17:39:12"
06 17:39:12"
06 17:39:12"
06 17:39:12"
06 17:39:12"
20 - -
0 0 disable
1 enable
0 1024-65535 int
0 1024-65535 int
0 64-64512 int
06 17:39:12"
06 17:39:12"
06 17:39:12"
06 17:39:12"
06 17:39:12"
20 -
20 -
20 -
20 -
15 蜜罐策略 API
16 威胁引流 API
20 - int
17 检测解密对象 API
18 SSL 代理自定义白名单 API
0 - string
1 - string
19 解密全局配置 API
20 SSL 服务器证书 API
21 SSL 解密证书 API
22 SSL 解密策略 API
23 引流策略 API
24 服务链管理 API
200 number
25 服务链监控 API
26 网元管理 API
27 静态路由 API
0.0.0.0 1-63 字符 string
28 策略路由 API
20 - number
29 链路探测 API
30 高可用性 API
6260 1-6260 和
1 1-60 number
0 0-60 number
31 对象配置 API
20 1-65535 numb
20 20
20 20
6 0-60 int
3 0-10 int
1 0-59 int
20 number
20 number
20 number
20 - string
32 安全域 API
20 - -
33 入侵防御 API
20 - -
200 - -
20 - -
200 - -
200 - -
200 - -
200 - -
200 - -
34 入侵防御自定义签名 API
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
20 - -
20 - -
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
0 0-65535 int
20 - -
20 - -
35 反病毒 API
36 反病毒自定义签名 API
1 - intger
37 安全配置文件组 API
0 0-1 integer
0 0-1 integer
0 0-1 integer
0 0-1 integer
38 特征库升级 API
39 管理员用户 API
40 SNMP API
41 集中管理 API
42 时间配置 API
43 NTP API
44 管理主机 API
23 1-65535 integer
443 1-65535 integer
45 系统日志 API
46 日志统计 API
100 int
47 配置保存 API
48 管理证书 API
49 黑白名单 API
50 失陷主机 API
20 20
20 20
7 天(604800)
30 天
90 天
20 20
20 20
51 人工处置 API
20 20
20 20
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
7 天(604800)
30 天
90 天
52 ALG 配置 API
0 Success 执行成功
1 Pending 挂起
2 Admin user session timeout 管理用户超时
3 Not enough parameters 参数不够
4 Too many parameters 参数太多
5 Invalid parameters 参数错误
6 Memory malloc err 内存分配失败
7 Common error 通用错误
8 System error 系统错误
9 System call error 系统调用错误
10 Password encryption failed 密码加密失败
11 Read config info error 读取配置信息错误
12 The  port is already being used. 该端口已经被占用
13 Modify  configure error. 修改配置错误
14 The input content contains invalid character `| 输入的内容中包含非法字符 `|
15 Open file error 打开文件失败
16 Lock file error 锁定文件失败
17 Del file error 删除文件失败
18 Create socket error 创建网络连接失败
19 Database error 数据库错误
20 Open database error 打开数据库失败
21 Database trigger  error 数据库触发器错误
22 Open database trigger  error 打开数据库触发器失败
23 Commit database trigger  error 执行数据库触发器失败
24 Rollback database trigger  error 回滚数据库触发器失败
25 rz not only one file 上传的文件个数不是一个
26 The operation was cancelled 该操作被取消
27 Upload file error or Upload timeout 上传文件错误或者上传超时
28 Config file not exist 配置文件不存在
29 Config file already exists 备份文件已经存在
30 Invalid config file 配置文件不合法
31 Password error or Invalid config file 密码错误或配置文件不合法
32 Root-vsys not save current vsys 根 vSYS 没有保存当前vSYS
33 Config file encryption failed 配置文件加密失败
34 Config file decryption failed 配置文件解密失败
35 Invalid log file 日志文件不合法
36 No log info 没有日志信息
37 Exceed max import num 超过导入最大数量
38 Ftp error FTP 错误
39 Cannot connect to ftp 无法连接到FTP
40 Cannot connect to ftp Or not allowed to
41 Cannot connect to ftp Or file not exist 无法连接到FTP 服务器或文件不
42 Permission denied 没有权限
43 Tftp error TFTP 错误
44 Cannot connect to tftp Or file not exist 无法连接到 TFTP 服务器或文件
45 Cannot connect to tftp Or not allowed to
46 File name invalid 文件名称不合法
47 File not exist 文件不存在
48 File not utf8 文件不是UTF-8 编码
49 The file format is illegal 文件格式不合法
50 Name invalid 名称不合法
51 file size too large 文件太大，请重新选择
52 Patch not exist 补丁包不存在
53 Patch already exist 补丁包已经存在
54 System package not exist 版本文件不存在
55 System package already exist 版本文件已经存在
56 Invalid patch package 补丁包不合法
57 Not enough space to upgrade 升级空间不足
58 No such system package to delete 要删除的版本不存在
59 Invalid system package 版本文件不合法
60 Patch version err 补丁包版本错误
61 Duplicate patch 补丁包重复
62 The system has patch with newer version 当前系统存在更新版本的补丁包
63 Patch not based on this system version 非当前系统版本的补丁包
64 System needs restart 设备重启后生效
65 System upgrade success 设备升级成功
66 User not exist 用户不存在
67 User already exist 用户已经存在
68 Password and username don't match 用户名或密码错误
69 Interface not exist 接口不存在
70 Interface is already exist 接口已经存在
71 layer3 interface not exist 无三层接口
72 Interface can not delete 接口不能删除
73 Interface is already exist in other vsys 接口在其它vSYS 中接口已经存
74 Set interface error 设置接口失败
75 Set bridge device error 设置桥设备失败
76 Del bridge device error 删除桥设备失败
77 Bridge id invalid 桥 ID 无效
78 Interface is in used 接口已经被引用
79 Vlan interface is in used VLAN 接口已经被引用
80 Bridge interface is in used 桥接口已经被引用
81 Zone is in used 安全域已经被引用
82 Vlan is in used VLAN 已经被引用
83 Object is in used 对象已经被引用
84 Bridge is in used 桥已经被引用
85 The bridge consists of the physical interface is in
86 IP conflict IP 地址冲突
87 MAC conflict MAC 地址冲突
88 Port conflict 端口冲突
89 The interface can not be held by other interface 该接口不能被其他接口包含
90 The interface is already be held by other
91 This interface is ADSL interface binding can not
92 ADSL interface can not be set IP ADSL 接口不能设置 IP 地址
93 This type of interface does not support ADSL 该接口类型不支持ADSL
94 The interface configuration DHCP client can not
95 The interface includes IP can not bind 该接口包含 IP 无法绑定
96 Layer2 interface can not be set IP 二层接口不能设置IP 地址
97 Layer2 interface can not be set arp probe 二层接口不能设置ARP 探测
98 Channel mode can not be set arp probe Channel 模式不支持设置 ARP 探
99 Can not config access, trunk,bridge or channel
100 Interface should under access mode 必须在 access 模式下才能设置
101 Interface should under trunk mode 必须在 trunk 模式下才能设置
102 Interface should under bridge mode 必须在bridge 模式下才能设置
103 Interface should under channel mode 必须在 channel 模式下才能设置
104 Interface should under 802.3ad mode 必须在 802.3ad 模式下才能设置
105 Interface name error 接口名字错误
106 Interface params error 接口参数错误
107 Single physical interface configuration sub- 单个物理接口配置的子接口数量
108 Bridge interface number has reached the
109 Tunnel interface number has reached the
110 Mirror monitoring interface is not a physical
111 Mirror monitoring interface is not itself 镜像监控接口不能是自身
112 Mirror monitor interface can not config 镜像监控接口不允许配置
113 Mirror interface can't do the mirror monitoring
114 Slave interface can not config 成员接口不允许设置
115 Cpu not exist CPU 不存在
116 Virtual wire can only be referenced by two
117 Bridge virtual wire cannot set 桥的虚拟线路属性不能修改
118 Virtual wire bridge cannot add bridge interface 虚拟线路桥不能添加桥接口
119 Virtual wire bridge cannot add static mac 虚拟线路桥不能添加静态MAC
120 Virtual Switch is not exist Virtual Switch 不存在
121 Virtual Switch is already exist Virtual Switch 已经存在
122 Virtual system doesn't permit the operation 虚系统不允许此操作
123 VLAN is not exist VLAN 不存在
124 Bridge is already exist Bridge 已经存在
125 Bridge is not exist Bridge 不存在
126 The bridge does not exist in this vsys 在该vSYS 里此 Bridge 不存在
127 The bridge is already exist in other vsys 在其他vSYS 里此 Bridge 已存在
128 Please delete slave interface 请删除成员接口
129 Please stop the connection 请停止连接
130 Please bind interface 请绑定接口
131 There is no bind interface 没有绑定接口
132 Please set user name and password 请配置用户名及密码
133 automatic connecting please stop the automatic
138 The interface contains sub-interface 该接口包含子接口
139 Virtual Router is not exist Virtual Router 不存在
140 Static route is not exist 静态路由不存在
141 Static route has exist 静态路由已存在
142 Link route or host route is confilct with static
143 The number of nexthop has been max in the
144 Gateway conflict with other static router. 网关与其它静态路由冲突.
145 Default route gateway can only be configured
146 Link route or host route is confilct with admin
147 Admin route is exist 管理路由已存在
148 Admin route is not exist 管理路由不存在
149 Admin route gw must be reachable 管理路由网关必须可达
150 Static route set kernel err 静态路由设置内核错误
151 Layer2 interface can not config router 二层接口不能设置路由
152 Layer3 interface can not config switch 三层接口不能设置交换
153 ha interface can not config 高可用性心跳口不能设置
154 ha track interface can not delete 高可用性监控接口不能删除
155 ha ip can not delete 高可用性心跳口IP 地址不能删除
156 This interface includes the IP address is not set
157 Rule has exist 策略已经存在
158 Rule not exist 策略不存在
159 Source zone not exist 源安全域不存在
160 Destination zone not exist 目的安全域不存在
161 Rule can only hold area obj 策略只能添加区域对象
162 The Rule is ipv4 rule, and can only hold ipv4 obj 安全策略只能添加IPv4 地址
163 The Rule is ipv6 rule, and can only hold ipv6 obj 安全策略只能添加IPv6 地址
164 The Rule not allow add this type address obj 安全策略不支持添加此类型IP 地
165 Rule repeat 策略重复
166 Rule id error ID 错误
167 ipv6 rule not allow add tunnel 安全策略 IPv6 不允许添加隧道
168 ipv6 rule not allow add to-tunnel 安全策略 IPv6 不允许添加安全隧
169 rule vlan invalid format 安全策略 VLAN 格式不正确
170 rule redundancy not done， please try later 安全策略冗余正在分析，请稍后
171 rule profile type not allow 安全策略配置文件类型不符合要
172 Source NAT policy already exist 源 NAT 策略存在
173 Source NAT policy not exist 源 NAT 策略不存在
174 Source NAT params error 源 NAT 的参数错误
175 Source NAT count over max 源 NAT 数超过最大
176 Only dynamic SYMMETRIC NAT configuration
177 No-trans configuration is not supported when
178 Cannot change to static or dynamic-ip when by-
179 Destination NAT policy already exist 目的 NAT 策略存在
180 Destination NAT policy not exist 目的 NAT 策略不存在
181 Destination NAT params error 目的 NAT 的参数错误
182 Destination NAT count over max 目的 NAT 数超过最大
183 NAT trans-ip set error NAT 转换后IP 设置错误
184 NAT dip set error NAT 目的IP 设置错误
185 Snat trans-ip can not set NULL SNAT 转换后IP 不能设置为空
186 Snat trans-ip can not set any SNAT 转换后IP 不能设置为 any
187 Dnat dip and ingress-interface can not set any in
188 Dnat trans-ip can not set NULL DNAT 转换后IP 不能设置为空
189 Dnat trans-ip can not set any DNAT 转换后IP 不能设置为any
190 Nat sip format err NAT 策略源地址格式错误
191 Nat dip format err NAT 策略目的地址格式错误
192 Nat transip format err NAT 策略转换后地址格式错误
193 Nat transip must be server object NAT 转换后IP 必须是服务器地
194 Nat service count over max NAT 服务数目超过最大值
195 Nat service exist NAT 服务存在
196 Nat trans ip err NAT 策略转换后地址不合法
197 Format of Expire is wrong, pattern:
198 Local user is not exist 本地用户不存在
199 Local group is not exist 本地用户组不存在
200 Local user is exist 本地用户已存在
201 Local group is exist 本地用户组已存在
202 Local user belongs to groups which have
203 The number of existed Local users are came up
204 The number of existed Local groups are came 本地用户组数已达最大限制
205 The number of existed Local roles are came up
206 The item have been referred so it can not be
207 Role is exist 角色已经存在
208 Role is not exist 角色不存在
209 Local user belongs to roles which have reached
210 Authsrv is exist 账号服务器已存在
211 default local Authsrv can not be deleted 默认本地账号服务器不能被删除
```
