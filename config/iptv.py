# -*- coding: utf-8 -*-
import re
import time
import datetime
import requests
import gzip
import os
import sys
import json
import copy
# =====================================================================
#  配置加载：可自定义项集中在 config.json。
#  数据目录默认与本文件同目录；容器内通过 CDIPTV_PANEL_DATA_DIR 指向 /app/data（独立挂载持久化）
#  首次运行若不存在 config.json，会自动按内置 DEFAULTS 生成一份
# =====================================================================
CONFIG_PATH = os.path.join(
    os.environ.get("CDIPTV_PANEL_DATA_DIR") or os.path.dirname(os.path.abspath(__file__)),
    "config.json",
)

DEFAULTS = {
    # ---------- 服务器 / 鉴权网关（以下地址/端口需抓包获取，请勿随意填写） ----------
    "server": {
        # 电信 IPTV 鉴权网关根地址（须以 http(s):// 开头、斜杠结尾），改错会导致鉴权失败
        "IPTVServer": "http://192.168.1.100:33200/",
        # EPG / 节目单服务器地址与端口（机顶盒所在内网）
        "PLServer": "192.168.2.2",
        "PLServerPort": "8080",
        # 内网 UDP 组播源地址与端口（同局域网播放时使用）
        "UdpServer": "192.168.2.2",
        "UdpPort": "8888",
        # 内网 HTTP 回看代理地址与端口
        "HttpServer": "192.168.2.2",
        "HttpPort": "8888",
        # 外网网关根地址（供不在同一局域网的外部播放器访问 M3U）
        "GATE_BASE": "https://tvgate.example.com:4443",
        # 请求 User-Agent（抓包获取：抓取机顶盒/APP 请求时携带的 UA，一般无需改动）
        "UserAgent": "Mozilla/5.0 (X11; U; Linux i686; en-US) AppleWebKit/534.0 (KHTML, like Gecko)",
    },
    # ---------- 输出 ----------
    "output": {
        # 内网 UDP 播放 M3U 文件名
        "Lan_name": "cdiptvnw.m3u",
        # 内网 HTTP 回看 M3U 文件名
        "LanHttp_name": "cdiptvrstpnw.m3u",
        # 外网网关 UDP 播放 M3U 文件名
        "GateLan_name": "cdiptv.m3u",
        # 外网网关 HTTP 回看 M3U 文件名
        "GateLanHttp_name": "cdiptvrstp.m3u",
        # M3U 输出目录（容器内路径，末尾带斜杠）
        "web_path": "/app/output/",
        # STRM 输出目录（容器内路径，末尾带斜杠）
        "strm_path": "/app/output/strm/",
    },
    # ---------- 鉴权参数（华为机顶盒两步鉴权，均需抓包获取你的真实身份值，请勿外泄） ----------
    "auth": {
        # ---- 第一步：登录鉴权 authLoginHWCTC ----
        "login": {
            # 电信 IPTV 账号（格式：CD + 数字 + @ITV）
            "UserID": "CD12345678@ITV",
            # 预留字段，一般留空
            "VIP": ""
        },
        # ---- 第二步：有效鉴权 ValidAuthenticationHWCTC ----
        "valid": {
            # 电信账号，与 login 的 UserID 一致
            "UserID": "CD12345678@ITV",
            # 语言代码（1 = 中文）
            "Lang": "1",
            # 是否支持高清（0 / 1）
            "SupportHD": "1",
            # 网络用户 ID，一般留空
            "NetUserID": "",
            # 鉴权密钥，登录流程返回，改动会导致鉴权失败，一般无需手动修改
            "Authenticator": "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
            # 机顶盒型号标识（固定，勿改）
            "STBType": "EC6108V9U_ca_sccdx",
            # 机顶盒软件版本标识
            "STBVersion": "HWVxxxxxxxx",
            # 连接类型编号（通常 4）
            "conntype": "4",
            # 机顶盒唯一序列号 STBID（对应机顶盒身份，勿改）
            "STBID": "00ABCDEF1234567890ABCDEF12345678",
            # EPG 节目单模板名
            "templateName": "epg30",
            # 区域 ID（账号所属地区）
            "areaId": "10106",
            # 鉴权令牌，登录流程返回
            "userToken": "ABCDEF0123456789ABCDEF0123456789",
            # 用户分组 ID
            "userGroupId": "1",
            # 产品套餐 ID
            "productPackageId": "-1",
            # 机顶盒 MAC 地址（英文冒号分隔）
            "mac": "00:11:22:33:44:55",
            # 用户字段
            "UserField": "2",
            # 机顶盒软件版本号
            "SoftwareVersion": "V100R005C00LSCD00SPC000B000",
            # 是否智能机顶盒（0 / 1）
            "IsSmartStb": "0",
            # 以下为预留字段，一般留空
            "desktopId": "",
            "stbmaker": "",
            "XMPPCapability": "",
            "ChipID": "",
            "VIP": ""
        },
        # ---- 第三步：拉取频道列表 getchannellist ----
        "channellist": {
            # 连接类型编号，与有效鉴权一致
            "conntype": "4",
            # 鉴权令牌，登录流程返回
            "UserToken": "ABCDEF0123456789ABCDEF0123456789",
            # 临时密钥，登录流程返回
            "tempKey": "ABCDEF0123456789ABCDEF0123456789",
            # 机顶盒序列号，与有效鉴权一致
            "stbid": "00ABCDEF1234567890ABCDEF12345678",
            # 是否支持高清（0 / 1）
            "SupportHD": "1",
            # 电信账号，与登录鉴权一致
            "UserID": "CD12345678@ITV",
            # 语言代码
            "Lang": "1"
        }
    },
    # ---------- 频道精确映射表：【电信原始频道名】 -> (tvg-id, tvg-name, tvg-logo, group-title) ----------
    "channel_map": {
        # CCTV系列【央视分组】
        "CCTV-1高清": ("1", "CCTV1", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV1.png", "央视"),
        "CCTV-2高清": ("2", "CCTV2", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV2.png", "央视"),
        "CCTV-3高清": ("3", "CCTV3", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV3.png", "央视"),
        "CCTV-4高清": ("4", "CCTV4", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV4.png", "央视"),
        "CCTV-5高清": ("5", "CCTV5", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV5.png", "央视"),
        "CCTV-5+高清": ("6", "CCTV5+", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV5+.png", "央视"),
        "CCTV-5＋高清": ("6", "CCTV5+", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV5+.png", "央视"),
        "CCTV-6高清": ("7", "CCTV6", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV6.png", "央视"),
        "CCTV-7高清": ("8", "CCTV7", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV7.png", "央视"),
        "CCTV-8高清": ("9", "CCTV8", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV8.png", "央视"),
        "CCTV-9高清": ("10", "CCTV9", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV9.png", "央视"),
        "CCTV-10高清": ("11", "CCTV10", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV10.png", "央视"),
        "CCTV-11高清": ("12", "CCTV11", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV11.png", "央视"),
        "CCTV-12高清": ("13", "CCTV12", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV12.png", "央视"),
        "CCTV-13高清": ("14", "CCTV13", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV13.png", "央视"),
        "CCTV-少儿高清": ("15", "CCTV14", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV14.png", "央视"),
        "CCTV-15高清": ("16", "CCTV15", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV15.png", "央视"),
        "CCTV-16高清": ("1864", "CCTV16", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV16.png", "央视"),
        "CCTV-16 4K": ("1864", "CCTV16", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV16.png", "央视"),
        "CCTV-17高清": ("17", "CCTV17", "http://epg.51zmt.top:8000/tb1/CCTV/CCTV17.png", "央视"),
        "CCTV-4K": ("106", "CCTV4K", "https://iptv.zsdc.eu.org/logo/CCTV4K.png", "央视"),
        # ==========4K卫视频道，独立分组【卫视4K】==========
        "四川卫视4K": ("56", "四川卫视", "https://iptv.zsdc.eu.org/logo/四川卫视4K.png", "卫视4K"),
        "湖南卫视4K": ("27", "湖南卫视", "https://iptv.zsdc.eu.org/logo/湖南卫视4K.png", "卫视4K"),
        "江苏卫视4K": ("29", "江苏卫视", "https://iptv.zsdc.eu.org/logo/江苏卫视4K.png", "卫视4K"),
        "浙江卫视4K": ("28", "浙江卫视", "https://iptv.zsdc.eu.org/logo/浙江卫视4K.png", "卫视4K"),
        "东方卫视4K": ("31", "东方卫视", "https://iptv.zsdc.eu.org/logo/东方卫视4K.png", "卫视4K"),
        "北京卫视4K": ("30", "北京卫视", "https://iptv.zsdc.eu.org/logo/北京卫视4K.png", "卫视4K"),
        "深圳卫视4K": ("34", "深圳卫视", "https://iptv.zsdc.eu.org/logo/深圳卫视4K.png", "卫视4K"),
        "广东卫视4K": ("33", "广东卫视", "https://iptv.zsdc.eu.org/logo/广东卫视4K.png", "卫视4K"),
        "山东卫视4K": ("38", "山东卫视", "https://iptv.zsdc.eu.org/logo/山东卫视4K.png", "卫视4K"),
        # 【卫视高清】：频道名称带“高清”后缀的卫视频道
        "四川卫视高清": ("56", "四川卫视", "http://epg.51zmt.top:8000/tb1/ws/sichuan.png", "卫视高清"),
        "湖南卫视高清": ("27", "湖南卫视", "http://epg.51zmt.top:8000/tb1/ws/hunan.png", "卫视高清"),
        "江苏卫视高清": ("29", "江苏卫视", "http://epg.51zmt.top:8000/tb1/ws/jiangsu.png", "卫视高清"),
        "浙江卫视高清": ("28", "浙江卫视", "http://epg.51zmt.top:8000/tb1/ws/zhejiang.png", "卫视高清"),
        "东方卫视高清": ("31", "东方卫视", "http://epg.51zmt.top:8000/tb1/ws/dongfang.png", "卫视高清"),
        "北京卫视高清": ("30", "北京卫视", "http://epg.51zmt.top:8000/tb1/ws/beijing.png", "卫视高清"),
        "深圳卫视高清": ("34", "深圳卫视", "http://epg.51zmt.top:8000/tb1/ws/shenzhen.png", "卫视高清"),
        "广东卫视高清": ("33", "广东卫视", "http://epg.51zmt.top:8000/tb1/ws/guangdong.png", "卫视高清"),
        "山东卫视高清": ("38", "山东卫视", "http://epg.51zmt.top:8000/tb1/ws/shandong.png", "卫视高清"),
        "山西卫视高清": ("54", "山西卫视", "http://epg.51zmt.top:8000/tb1/ws/shanxi.png", "卫视高清"),
        "安徽卫视高清": ("32", "安徽卫视", "http://epg.51zmt.top:8000/tb1/ws/anhui.png", "卫视高清"),
        "重庆卫视高清": ("40", "重庆卫视", "http://epg.51zmt.top:8000/tb1/ws/chongqing.png", "卫视高清"),
        "天津卫视高清": ("39", "天津卫视", "http://epg.51zmt.top:8000/tb1/ws/tianjin.png", "卫视高清"),
        "辽宁卫视高清": ("36", "辽宁卫视", "http://epg.51zmt.top:8000/tb1/ws/liaoning.png", "卫视高清"),
        "黑龙江卫视高清": ("46", "黑龙江卫视", "http://epg.51zmt.top:8000/tb1/ws/heilongjiang.png", "卫视高清"),
        "吉林卫视高清": ("51", "吉林卫视", "http://epg.51zmt.top:8000/tb1/ws/jilin.png", "卫视高清"),
        "河北卫视高清": ("45", "河北卫视", "http://epg.51zmt.top:8000/tb1/ws/hebei.png", "卫视高清"),
        "河南卫视高清": ("47", "河南卫视", "http://epg.51zmt.top:8000/tb1/ws/henan.png", "卫视高清"),
        "湖北卫视高清": ("48", "湖北卫视", "http://epg.51zmt.top:8000/tb1/ws/hubei.png", "卫视高清"),
        "江西卫视高清": ("50", "江西卫视", "http://epg.51zmt.top:8000/tb1/ws/jiangxi.png", "卫视高清"),
        "广西卫视高清": ("43", "广西卫视", "http://epg.51zmt.top:8000/tb1/ws/guangxi.png", "卫视高清"),
        "贵州卫视高清": ("44", "贵州卫视", "http://epg.51zmt.top:8000/tb1/ws/guizhou.png", "卫视高清"),
        "云南卫视高清": ("58", "云南卫视", "http://epg.51zmt.top:8000/tb1/ws/yunnan.png", "卫视高清"),
        "陕西卫视高清": ("55", "陕西卫视", "http://epg.51zmt.top:8000/tb1/ws/shanxi.png", "卫视高清"),
        "甘肃卫视高清": ("42", "甘肃卫视", "http://epg.51zmt.top:8000/tb1/ws/gansu.png", "卫视高清"),
        "新疆卫视高清": ("57", "新疆卫视", "http://epg.51zmt.top:8000/tb1/ws/xinjiang.png", "卫视高清"),
        "内蒙古卫视高清": ("52", "内蒙古卫视", "http://epg.51zmt.top:8000/tb1/ws/neimeng.png", "卫视高清"),
        "东南卫视高清": ("41", "东南卫视", "http://epg.51zmt.top:8000/tb1/ws/dongnan.png", "卫视高清"),
        "海峡卫视高清": ("21", "海峡卫视", "http://epg.51zmt.top:8000/tb1/ws/haixia.png", "卫视高清"),
        "康巴卫视高清": ("70", "康巴卫视", "http://epg.51zmt.top:8000/tb1/ws/kangba.png", "卫视高清"),
        "西藏卫视高清": ("71", "西藏卫视", "http://epg.51zmt.top:8000/tb1/ws/xizang.png", "卫视高清"),
        "兵团卫视高清": ("61", "兵团卫视", "http://epg.51zmt.top:8000/tb1/ws/bingtuan.png", "卫视高清"),
        "中国教育-1高清": ("73", "中国教育1台", "http://epg.51zmt.top:8000/tb1/qt/cetv1.png", "卫视高清"),
        "中国教育-2高清": ("74", "中国教育2台", "http://epg.51zmt.top:8000/tb1/qt/cetv2.png", "卫视高清"),
        "凤凰中文高清": ("141", "凤凰中文", "http://epg.51zmt.top:8000/tb1/qt/fenghuangzw.png", "卫视高清"),
        "凤凰资讯高清": ("142", "凤凰资讯", "http://epg.51zmt.top:8000/tb1/qt/fenghuangzx.png", "卫视高清"),
        # 【卫视】无高清后缀频道
        "青海卫视": ("59", "青海卫视", "http://epg.51zmt.top:8000/tb1/ws/qinghai.png", "卫视"),
        "厦门卫视": ("68", "厦门卫视", "http://epg.51zmt.top:8000/tb1/ws/xiamen.png", "卫视"),
        "三沙卫视": ("72", "三沙卫视", "http://epg.51zmt.top:8000/tb1/ws/sansha.png", "卫视"),
        "海南卫视": ("242", "海南卫视", "https://epg.112114.xyz/logo/海南卫视.png", "卫视"),
        "山东教育卫视": ("243", "山东教育卫视", "https://epg.112114.xyz/logo/山东教育卫视.png", "卫视"),
        "延边卫视": ("244", "延边卫视", "https://epg.112114.xyz/logo/延边卫视.png", "卫视"),
        "安多卫视": ("245", "安多卫视", "https://epg.112114.xyz/logo/安多卫视.png", "卫视"),
        # 纪实
        "北京纪实高清": ("1173", "BRTV纪实科教", "http://epg.51zmt.top:8000/tb1/ws/beijingjishi.png", "纪实"),
        "金鹰纪实高清": ("1324", "金鹰纪实", "http://epg.51zmt.top:8000/tb1/ws/jinyingjishi.png", "纪实"),
        # 四川本地
        "SCTV-2高清": ("1353", "SCTV2", "http://epg.51zmt.top:8000/tb1/sheng/sctv2.png", "四川"),
        "SCTV-3高清": ("1354", "SCTV3", "http://epg.51zmt.top:8000/tb1/sheng/sctv3.png", "四川"),
        "SCTV-4高清": ("1355", "SCTV4", "http://epg.51zmt.top:8000/tb1/sheng/sctv4.png", "四川"),
        "SCTV-5高清": ("1356", "SCTV5", "http://epg.51zmt.top:8000/tb1/sheng/sctv5.png", "四川"),
        "SCTV-7高清": ("1358", "SCTV7", "http://epg.51zmt.top:8000/tb1/sheng/sctv7.png", "四川"),
        "SCTV-8高清": ("1361", "SCTV8", "http://epg.51zmt.top:8000/tb1/sheng/sctv8.png", "四川"),
        "四川乡村高清": ("1984", "四川乡村", "http://epg.51zmt.top:8000/tb1/sheng/sctv9.png", "四川"),
        "峨眉电影高清": ("1359", "峨眉电影", "https://epg.51zmt.top:8001/tb1/qt/emeidianying.png", "四川"),
        # 成都本地
        "CDTV-1高清": ("1363", "CDTV1", "http://epg.51zmt.top:8000/tb1/sheng/cdtv1.png", "成都"),
        "CDTV-2高清": ("1364", "CDTV2", "http://epg.51zmt.top:8000/tb1/sheng/cdtv2.png", "成都"),
        "CDTV-3高清": ("1365", "CDTV3", "http://epg.51zmt.top:8000/tb1/sheng/cdtv3.png", "成都"),
        "CDTV-4高清": ("1366", "CDTV4", "http://epg.51zmt.top:8000/tb1/sheng/cdtv4.png", "成都"),
        "CDTV-5高清": ("1367", "CDTV5", "http://epg.51zmt.top:8000/tb1/sheng/cdtv5.png", "成都"),
        "CDTV-6高清": ("1368", "CDTV6", "http://epg.51zmt.top:8000/tb1/sheng/cdtv6.png", "成都"),
        # 体育
        "五星体育高清": ("1287", "五星体育频道", "https://s.102031.xyz/tb1/qt/wuxingtiyu.png", "体育"),
        # 少儿（原动漫并入）
        "金鹰卡通高清": ("69", "金鹰卡通", "http://epg.51zmt.top:8000/tb1/qt/jinyingkatong.png", "少儿"),
        "哈哈炫动高清": ("62", "哈哈炫动", "http://epg.51zmt.top:8000/tb1/qt/haha.png", "少儿"),
        "卡酷动画高清": ("67", "卡酷动画", "http://epg.51zmt.top:8000/tb1/qt/kaku.png", "少儿"),
        "优漫卡通高清": ("348", "优漫卡通", "http://epg.51zmt.top:8000/tb1/qt/youman.png", "少儿"),
        # ===== 国际（CGTN 系列） =====
        "CGTN英语": ("CGTN", "CGTN", "https://live.fanmingming.cn/tv/CGTN.png", "国际"),
        "CGTN纪录": ("CGTN纪录", "CGTN纪录", "https://live.fanmingming.cn/tv/CGTN纪录.png", "国际"),
        "CGTN西班牙语": ("CGTN西语", "CGTN西语", "https://live.fanmingming.cn/tv/CGTN西语.png", "国际"),
        "CGTN法语": ("CGTN法语", "CGTN法语", "https://live.fanmingming.cn/tv/CGTN法语.png", "国际"),
        "CGTN阿拉伯语": ("CGTN阿语", "CGTN阿语", "https://live.fanmingming.cn/tv/CGTN阿语.png", "国际"),
        "CGTN俄语": ("CGTN俄语", "CGTN俄语", "https://live.fanmingming.cn/tv/CGTN俄语.png", "国际"),
        # ===== 教育（中国教育 CETV / 书画 / 学堂） =====
        "CETV-1高清": ("CETV1", "中国教育1台", "https://live.fanmingming.cn/tv/中国教育1台.png", "教育"),
        "CETV-2": ("CETV2", "中国教育2台", "https://live.fanmingming.cn/tv/中国教育2台.png", "教育"),
        "CETV-4高清": ("CETV4", "中国教育4台", "https://live.fanmingming.cn/tv/中国教育4台.png", "教育"),
        "书画频道": ("", "书画频道", "", "教育"),
        "金色学堂": ("", "金色学堂", "", "教育"),
        "百变课堂专区": ("", "百变课堂", "", "教育"),
        "墨宝高清专区": ("", "墨宝高清", "", "教育"),
        # ===== 卫视补充 =====
        "山西卫视": ("54", "山西卫视", "", "卫视"),
        "宁夏卫视高清": ("60", "宁夏卫视", "", "卫视高清"),
        # ===== 四川本地（SCTV / 熊猫 / 大爱 / 地方） =====
        "SCTV-6高清": ("SCTV6", "SCTV6", "", "四川"),
        "SCTV-科教高清": ("SCTV科教", "SCTV科教", "", "四川"),
        "熊猫新闻高清专区": ("", "熊猫新闻", "", "四川"),
        "熊猫体娱高清专区": ("", "熊猫体娱", "", "四川"),
        "熊猫少儿高清专区": ("", "熊猫少儿", "", "四川"),
        "云看熊猫专区": ("", "云看熊猫", "", "四川"),
        "熊猫爱生活高清专区": ("", "熊猫爱生活", "", "四川"),
        "大爱四川高清专区": ("", "大爱四川", "", "四川"),
        "大爱旅游高清专区": ("", "大爱旅游", "", "四川"),
        "大爱生活高清专区": ("", "大爱生活", "", "四川"),
        "大爱时尚高清专区": ("", "大爱时尚", "", "四川"),
        "爱乐山": ("", "爱乐山", "", "四川"),
        "红原日干乔": ("", "红原日干乔", "", "四川"),
        "红原月亮湾": ("", "红原月亮湾", "", "四川"),
        # ===== 成都本地 =====
        "CDTV-8高清": ("CDTV8", "CDTV8", "", "成都"),
        "蓉城先锋专区": ("", "蓉城先锋", "", "成都"),
        "i成都": ("", "i成都", "", "成都"),
        # ===== 纪实（军事 / 解密 / 求索 / 法治 / 看天下） =====
        "军事高清专区": ("", "军事高清", "", "纪实"),
        "解密高清专区": ("", "解密高清", "", "纪实"),
        "求索频道高清": ("", "求索频道", "", "纪实"),
        "法治天地": ("", "法治天地", "", "纪实"),
        "中国交通": ("", "中国交通", "", "纪实"),
        "看天下精选专区": ("", "看天下精选", "", "纪实"),
        # ===== 体育（围棋 / 钓鱼） =====
        "天元围棋": ("", "天元围棋", "", "体育"),
        "快乐垂钓": ("", "快乐垂钓", "", "体育"),
        "四海钓鱼": ("", "四海钓鱼", "", "体育"),
        "来钓鱼吧专区": ("", "来钓鱼吧", "", "体育"),
        # ===== 电竞 =====
        "电竞天堂高清专区": ("", "电竞天堂", "", "电竞"),
        "游戏风云": ("", "游戏风云", "", "电竞"),
        # ===== 电影 =====
        "星光院线专区": ("", "星光院线", "", "电影"),
        "爱院线专区": ("", "爱院线", "", "电影"),
        "爱科幻专区": ("", "爱科幻", "", "电影"),
        "绚影4K专区": ("", "绚影4K", "", "电影"),
        "爱上4K专区": ("", "爱上4K", "", "电影"),
        "4K视界专区": ("", "4K视界", "", "电影"),
        "4K乐享超清专区": ("", "4K乐享超清", "", "电影"),
        # ===== 电视剧 =====
        "爱谍战专区": ("", "爱谍战", "", "电视剧"),
        "爱悬疑专区": ("", "爱悬疑", "", "电视剧"),
        "爱浪漫专区": ("", "爱浪漫", "", "电视剧"),
        "爱喜剧专区": ("", "爱喜剧", "", "电视剧"),
        # ===== 综艺（综艺 / 音乐 / 戏曲 / 文体） =====
        "热门综艺高清专区": ("", "热门综艺", "", "综艺"),
        "爱奇谈专区": ("", "爱奇谈", "", "综艺"),
        "戏曲精选专区": ("", "戏曲精选", "", "综艺"),
        "戏曲专区": ("", "戏曲", "", "综艺"),
        "音乐现场高清专区": ("", "音乐现场", "", "综艺"),
        "多彩文体4K": ("", "多彩文体4K", "", "综艺"),
        # ===== 少儿 =====
        "青春动漫专区": ("", "青春动漫", "", "少儿"),
        "动漫秀场": ("", "动漫秀场", "", "少儿"),
        "爱动漫专区": ("", "爱动漫", "", "少儿"),
        "4K少儿专区": ("", "4K少儿", "", "少儿"),
        "少儿天地专区": ("", "少儿天地", "", "少儿"),
        "爱幼教专区": ("", "爱幼教", "", "少儿"),
        "爱玩具专区": ("", "爱玩具", "", "少儿"),
        "亲子趣学4k专区": ("", "亲子趣学4K", "", "少儿"),
        "卡酷少儿": ("", "卡酷少儿", "", "少儿"),
        # ===== 财经 =====
        "东方财经高清": ("", "东方财经", "", "财经"),
        "华西证券": ("", "华西证券", "", "财经"),
        "家庭理财": ("", "家庭理财", "", "财经"),
        # ===== 生活 =====
        "家政频道高清": ("", "家政频道", "", "生活"),
        "魅力时尚高清专区": ("", "魅力时尚", "", "生活"),
        "生活时尚": ("", "生活时尚", "", "生活"),
        "爱生活高清专区": ("", "爱生活", "", "生活"),
        "健康养生专区": ("", "健康养生", "", "生活"),
        "中国天气": ("", "中国天气", "", "生活"),
        "爱宠宠物专区": ("", "爱宠宠物", "", "生活"),
        # ===== 旅游 =====
        "环球旅游": ("", "环球旅游", "", "旅游"),
        "乐游": ("", "乐游", "", "旅游"),
        "爱旅行专区": ("", "爱旅行", "", "旅游"),
        # ===== 导视（导视 / 指南 / 直播室 / 组播 / 宣传） =====
        "精彩导视": ("", "精彩导视", "", "导视"),
        "导视专区": ("", "导视", "", "导视"),
        "收视指南专区": ("", "收视指南", "", "导视"),
        "电信导视3": ("", "电信导视", "", "导视"),
        "精彩推荐专区": ("", "精彩推荐", "", "导视"),
        "直播室1": ("", "直播室1", "", "导视"),
        "直播室2": ("", "直播室2", "", "导视"),
        "直播室3": ("", "直播室3", "", "导视"),
        "直播室4": ("", "直播室4", "", "导视"),
        "直播室5": ("", "直播室5", "", "导视"),
        "直播室6": ("", "直播室6", "", "导视"),
        "直播室7": ("", "直播室7", "", "导视"),
        "直播室8": ("", "直播室8", "", "导视"),
        "920-全网组播": ("", "920-全网组播", "", "导视"),
        "921-全网组播": ("", "921-全网组播", "", "导视"),
        "922-全网组播": ("", "922-全网组播", "", "导视"),
        "923-全网组播": ("", "923-全网组播", "", "导视"),
        "924-全网组播": ("", "924-全网组播", "", "导视"),
        "925-全网组播": ("", "925-全网组播", "", "导视"),
        "926-全网组播": ("", "926-全网组播", "", "导视"),
        "927-全网组播": ("", "927-全网组播", "", "导视"),
        "雅克音乐节直播": ("", "雅克音乐节", "", "导视"),
        "雅克音乐节宣传": ("", "雅克音乐节宣传", "", "导视"),
        "云演艺宣传": ("", "云演艺宣传", "", "导视"),
    },
    # ---------- 自动分类关键词：分组 -> [关键词]（未命中精确映射时按此匹配） ----------
    "auto_group": {
        "国际": ["cgtn", "国际"],
        "少儿": ["少儿", "幼教", "玩具", "亲子", "卡通", "动画", "动漫"],
        "体育": ["体育", "足球", "篮球", "高尔夫", "搏击", "赛车", "钓鱼", "围棋", "垂钓", "棋牌", "体娱"],
        "电竞": ["电竞", "游戏"],
        "财经": ["财经", "理财", "证券", "金融"],
        "综艺": ["综艺", "音乐", "戏曲", "奇谈", "文体", "现场"],
        "电影": ["电影", "chc", "影院", "大片", "院线", "科幻", "视界", "乐享"],
        "电视剧": ["剧场", "影视", "剧集", "谍战", "悬疑", "浪漫", "喜剧"],
        "纪实": ["纪实", "记录", "地理", "探索", "历史", "人文", "军事", "解密", "求索", "法治"],
        "教育": ["教育", "课堂", "学堂", "书画", "墨宝", "cetv"],
        "旅游": ["旅游", "旅行", "乐游", "环球", "景区"],
        "生活": ["生活", "家政", "时尚", "养生", "健康", "天气", "宠物"],
        "导视": ["导视", "指南", "推荐", "直播室", "组播", "宣传", "演艺", "音乐节"]
    },
    # ---------- 分组排序 ----------
    "group_order": ["央视", "卫视4K", "卫视高清", "卫视", "四川", "成都", "纪实", "体育", "电竞", "电影", "电视剧", "综艺", "少儿", "财经", "生活", "教育", "旅游", "国际", "导视", "其他"],
    # ---------- 定时任务（由面板 cron_daemon 调度使用） ----------
    "cron": {
        "iptv_cron": "1 1 * * *",
        "auto_run_on_start": True
    }
}

def load_config():
    """加载 config.json；不存在则按 DEFAULTS 生成一份"""
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for sec in ("server", "output", "auth", "channel_map", "auto_group", "group_order", "cron"):
                if sec in user and user[sec] and isinstance(user[sec], type(DEFAULTS[sec])):
                    cfg[sec] = user[sec]
            print("[配置] 已加载 config.json")
        except Exception as e:
            print(f"[配置] 读取 config.json 失败，使用内置默认：{e}")
    else:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
            print(f"[配置] 未发现 config.json，已生成默认配置：{CONFIG_PATH}")
        except Exception as e:
            print(f"[配置] 生成默认配置文件失败：{e}")
    # channel_map 值由 JSON list 转回 tuple，兼容解包
    cfg["channel_map"] = {k: tuple(v) for k, v in cfg["channel_map"].items()}
    return cfg

CONFIG = load_config()

# ---------- 请求头：User-Agent 取自 config.json（可在网页「服务器/网关」修改） ----------
HEADERS = {
    "User-Agent": CONFIG["server"].get("UserAgent", "Mozilla/5.0 (X11; U; Linux i686; en-US) AppleWebKit/534.0 (KHTML, like Gecko)")
}

# ---------- 导出为全局变量（兼容现有逻辑） ----------
IPTVServer = CONFIG["server"]["IPTVServer"]
PLServer = CONFIG["server"]["PLServer"]
PLServerPort = CONFIG["server"]["PLServerPort"]
UdpServer = CONFIG["server"]["UdpServer"]
UdpPort = CONFIG["server"]["UdpPort"]
HttpServer = CONFIG["server"]["HttpServer"]
HttpPort = CONFIG["server"]["HttpPort"]
GATE_BASE = CONFIG["server"]["GATE_BASE"]

Lan_name = CONFIG["output"]["Lan_name"]
LanHttp_name = CONFIG["output"]["LanHttp_name"]
GateLan_name = CONFIG["output"]["GateLan_name"]
GateLanHttp_name = CONFIG["output"]["GateLanHttp_name"]
web_path = CONFIG["output"]["web_path"]
strm_path = CONFIG["output"]["strm_path"]

CHANNEL_MAP = CONFIG["channel_map"]
AUTO_GROUP = CONFIG["auto_group"]
GROUP_ORDER = CONFIG["group_order"]
# =====================================================================
def auto_get_group(channel_name: str) -> str:
    """自动分类：字典未命中的频道，按 config 里的关键词自动匹配分组"""
    c = channel_name.lower()
    for group, keys in AUTO_GROUP.items():
        if any(k in c for k in keys):
            return group
    return "其他"

def getValidAuthenticationHWCTC():
    session = requests.Session()
    auth_login_form = CONFIG["auth"]["login"]
    try:
        session.post(
            IPTVServer + 'EPG/jsp/authLoginHWCTC.jsp',
            data=auth_login_form,
            headers=HEADERS,
            timeout=15
        )
        form_data = CONFIG["auth"]["valid"]
        resp = session.post(
            IPTVServer + 'EPG/jsp/ValidAuthenticationHWCTC.jsp',
            data=form_data,
            headers=HEADERS,
            timeout=15
        )
        print(f"[session] 当前Cookie: {session.cookies.get_dict()}")
        return session
    except Exception as e:
        print(f"鉴权请求异常：{e}")
        return session

def ReValidAuthentication(index):
    Frequency = 60
    return (index - 1) % Frequency == 0

def getgrouptitle(NOs, channelname):
    return auto_get_group(channelname)

def sort_channel_by_group(channel_list):
    # 分组顺序来自 config（group_order）
    group_order = GROUP_ORDER
    bucket = {g: [] for g in group_order}
    other_bucket = []
    for item in channel_list:
        _, _, cname, _, gtitle, _, _, _, _, _ = item
        if cname in CHANNEL_MAP:
            _, _, _, g = CHANNEL_MAP[cname]
        else:
            g = auto_get_group(cname)
        if g in bucket:
            bucket[g].append(item)
        else:
            other_bucket.append(item)
    out = []
    for g in group_order:
        out.extend(bucket[g])
    out.extend(other_bucket)
    return out

def getchannellist():
    channeldata = []
    session = getValidAuthenticationHWCTC()
    form_data = CONFIG["auth"]["channellist"]
    try:
        resp = session.post(
            IPTVServer + '/EPG/jsp/getchannellistHWCTC.jsp',
            data=form_data,
            headers=HEADERS,
            timeout=20
        )
        html_text = resp.text
        pat_all = re.compile(r"Authentication\.CTCSetConfig\('Channel'\s*,\s*(.*?)\);", re.S)
        channel_fragments = pat_all.findall(html_text)
        print(f"\n解析到JS频道片段数量：{len(channel_fragments)}")
        index = 1
        for frag in channel_fragments:
            m_cid = re.search(r'ChannelID="(.*?)"', frag)
            m_cname = re.search(r'ChannelName="(.*?)"', frag)
            m_uid = re.search(r'UserChannelID="(.*?)"', frag)
            m_sdp = re.search(r'ChannelSDP="(.*?)"', frag)
            m_timeshift = re.search(r'TimeShiftURL="(.*?smil[^"]*)"', frag)
            m_fccip = re.search(r'ChannelFCCIP="(.*?)"', frag)
            m_fccport = re.search(r'ChannelFCCPort="(.*?)"', frag)
            m_fecport = re.search(r'ChannelFECPort="(.*?)"', frag)
            if not (m_cid and m_cname and m_uid and m_sdp):
                continue
            cid = m_cid.group(1)
            cname = m_cname.group(1)
            uid = m_uid.group(1)
            sdp = m_sdp.group(1)
            igmp_match = re.search(r'igmp://([^\s|]+)', sdp)
            if not igmp_match:
                continue
            igmp_url = igmp_match.group(1)
            rtsp_url = ""
            if m_timeshift:
                rtsp_url = m_timeshift.group(1)
            fccip = m_fccip.group(1) if m_fccip else ""
            fccport = m_fccport.group(1) if m_fccport else ""
            fecport = m_fecport.group(1) if m_fecport else ""
            gtitle = getgrouptitle(uid, cname)
            channeldata.append((
                index, cid, cname, uid, gtitle,
                rtsp_url,
                igmp_url,
                fccip, fccport, fecport
            ))
            index += 1
        print(f"\n✅ 解析完成，有效频道总数：{len(channeldata)}")
        seen_chname = set()
        new_channeldata = []
        for item in channeldata:
            idx, cid, cname, uid, gtitle, rtsp_url, igmp_url, fccip, fccport, fecport = item
            if "画中画" in cname:
                continue
            if cname not in seen_chname:
                seen_chname.add(cname)
                new_channeldata.append(item)
        channeldata = new_channeldata
        print(f"\n✅过滤画中画+去重完成，剩余有效频道：{len(channeldata)}")
        channeldata = sort_channel_by_group(channeldata)
        print(f"\n✅已按指定分组顺序重排完成")
        return channeldata
    except Exception as e:
        print(f"获取频道列表请求异常: {e}")
        return channeldata

def generate_Lanm3u(channeldata, out_filename, base_url):
    out_path = web_path + out_filename
    epg_url = f'http://epg.51zmt.top:8000/e.xml.gz'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U name="成都电信IPTV" x-tvg-url="{epg_url}"\n')
        for idx, cid, cname, uid, gtitle, rtsp_full, igmpurl, fccip, fccport, fecport in channeldata:
            if cname in CHANNEL_MAP:
                tvg_id, tvg_name, tvg_logo, real_group = CHANNEL_MAP[cname]
            else:
                tvg_id = ""
                tvg_name = cname
                tvg_logo = ""
                real_group = auto_get_group(cname)
            catchup_part = ""
            if rtsp_full:
                pure_rtsp = rtsp_full.replace("rtsp://", "")
                if "?" in pure_rtsp:
                    pure_rtsp = pure_rtsp.split("?")[0]
                catchup_http = f'{base_url}/rtsp/{pure_rtsp}'
                catchup_part = f'catchup="default" catchup-source="{catchup_http}?playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"'
            lanudp = f"{base_url}/udp/{igmpurl}"
            f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-logo="{tvg_logo}" group-title="{real_group}" {catchup_part}, {cname}\n')
            f.write(f'{lanudp}\n')
    print(f'M3U文件已生成：{out_path}')

def generate_LanHttpm3u(channeldata, out_filename, base_url):
    out_path = web_path + out_filename
    epg_url = f'http://epg.51zmt.top:8000/e.xml.gz'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U name="成都电信IPTV" x-tvg-url="{epg_url}"\n')
        for idx, cid, cname, uid, gtitle, rtsp_full, igmpurl, fccip, fccport, fecport in channeldata:
            if cname in CHANNEL_MAP:
                tvg_id, tvg_name, tvg_logo, real_group = CHANNEL_MAP[cname]
            else:
                tvg_id = ""
                tvg_name = cname
                tvg_logo = ""
                real_group = auto_get_group(cname)
            catchup_part = ""
            play_http_url = ""
            if rtsp_full:
                pure_rtsp = rtsp_full.replace("rtsp://", "")
                if "?" in pure_rtsp:
                    pure_rtsp = pure_rtsp.split("?")[0]
                play_http_url = f'{base_url}/rtsp/{pure_rtsp}'
                catchup_part = f'catchup="default" catchup-source="{play_http_url}?playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"'
            if play_http_url:
                output_url = play_http_url
            else:
                output_url = f"{base_url}/udp/{igmpurl}"
            f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-logo="{tvg_logo}" group-title="{real_group}" {catchup_part}, {cname}\n')
            f.write(f'{output_url}\n')
    print(f'M3U文件已生成：{out_path}')

def run_full_task():
    print("\n==================== 开始执行任务 ====================")
    os.makedirs(web_path, exist_ok=True)
    os.makedirs(strm_path, exist_ok=True)
    channeldata = getchannellist()
    local_base = f"http://{UdpServer}:{UdpPort}"
    generate_Lanm3u(channeldata, Lan_name, local_base)
    generate_LanHttpm3u(channeldata, LanHttp_name, local_base)
    generate_Lanm3u(channeldata, GateLan_name, GATE_BASE)
    generate_LanHttpm3u(channeldata, GateLanHttp_name, GATE_BASE)
    if len(channeldata) > 0:
        print("✅已跳过本地PL.xml生成，M3U使用老张远程EPG源")
    else:
        print("⚠️ 警告：没有抓到任何频道，检查专网/鉴权参数")
    print(f"==================== 任务执行完毕 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====================\n")

if __name__ == '__main__':
    print("========== IPTV脚本启动 ==========")
    run_full_task()
