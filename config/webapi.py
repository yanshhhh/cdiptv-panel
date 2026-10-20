# -*- coding: utf-8 -*-
from flask import Flask, request, session, redirect, send_from_directory, abort, Response, render_template
import subprocess
import os
import threading
import time
import json
import datetime
import secrets
from croniter import croniter, CroniterBadCronError

app = Flask(__name__, template_folder="/app/templates")
app.secret_key = "cdiptv-panel-auto-origin"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ---------- 面板版本号（升级时更新；与 docker 镜像 tag 对应，如 0.2.0 → :0.2） ----------
PANEL_VERSION = "0.2.0"

@app.context_processor
def inject_panel_version():
    """把版本号注入所有模板，base.html 通过 {{ panel_version }} 引用"""
    return {"panel_version": PANEL_VERSION}

CONFIG_DIR = "/app/config"  # 脚本目录：iptv.py / static（镜像内置，升级自动更新）
DATA_DIR = os.environ.get("CDIPTV_PANEL_DATA_DIR", "/app/data")  # 数据目录：config.json 等持久化（可单独挂载）
PANEL_ROOT = "/app/output"  # 输出目录：抓取的 m3u（可单独挂载）
SCRIPT_PATH = os.path.join(CONFIG_DIR, "iptv.py")
CRON_CONF_PATH = os.path.join(DATA_DIR, "cron_config.json")
TASK_LOG_PATH = os.path.join(DATA_DIR, "task_run_log.json")
IPTV_CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
MAX_LOG_COUNT = 50

# 登录口令：强制从环境变量读取；未设置时每次启动生成随机口令（拒绝公开固定默认值）
PANEL_USER = os.environ.get("PANEL_USER") or "admin"
PANEL_PASS = os.environ.get("PANEL_PASS") or secrets.token_hex(8)

DEFAULT_CRONTAB = {
    "iptv_cron": "1 0,12 * * *",
    "auto_run_on_start": True
}

reload_cron_signal = threading.Event()

def load_task_log():
    if os.path.exists(TASK_LOG_PATH):
        try:
            with open(TASK_LOG_PATH,"r",encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_task_log(log_list):
    with open(TASK_LOG_PATH,"w",encoding="utf-8") as f:
        json.dump(log_list, f, ensure_ascii=False, indent=2)

def append_task_log(status, source, msg=""):
    log_list = load_task_log()
    item = {
        "ts": time.time(),
        "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "source": source,
        "msg": msg
    }
    log_list.append(item)
    if len(log_list) > MAX_LOG_COUNT:
        log_list = log_list[-MAX_LOG_COUNT:]
    save_task_log(log_list)

def load_panel_config():
    """读取 config.json（iptv 可配置项）；不存在则尝试由 iptv.py 自动生成"""
    if os.path.exists(IPTV_CONFIG_PATH):
        try:
            with open(IPTV_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_panel_config(cfg):
    with open(IPTV_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def load_cron_config():
    """定时配置并入 config.json 统一管理；无则回退旧 cron_config.json 并自动迁移"""
    cfg = load_panel_config()
    if cfg.get("cron"):
        return cfg["cron"]
    old = None
    if os.path.exists(CRON_CONF_PATH):
        try:
            with open(CRON_CONF_PATH, "r", encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = None
    if old:
        merged = load_panel_config()
        merged["cron"] = old
        save_panel_config(merged)
        return old
    return DEFAULT_CRONTAB.copy()

def save_cron_config(cfg):
    """把 cron 写入 config.json 的 cron 区（保留其它配置），并触发热加载"""
    cur = load_panel_config()
    if not cur:
        cur = {}
    cur["cron"] = cfg
    save_panel_config(cur)
    reload_cron_signal.set()

def run_iptv_task(source="cron"):
    print(f"[CRON-IPTV] {time.strftime('%Y-%m-%d %H:%M:%S')} 开始执行iptv抓取, source={source}")
    proc = subprocess.Popen(["python3", SCRIPT_PATH], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = proc.communicate()
    ret_code = proc.returncode
    print(out)
    print(f"[CRON-IPTV] {time.strftime('%Y-%m-%d %H:%M:%S')} iptv抓取完成 ret={ret_code}\n")
    if ret_code == 0:
        append_task_log("success", source, out)
    else:
        append_task_log("fail", source, out)
    return out, ret_code

def cron_daemon():
    cfg = load_cron_config()
    if cfg.get("auto_run_on_start", True):
        print("[CRON-DAEMON] 容器启动，立即执行一次iptv抓取任务")
        # 子线程运行，不阻塞调度主循环
        threading.Thread(target=run_iptv_task, args=("cron",), daemon=True).start()

    iter_iptv = None
    next_iptv = 0

    def rebuild():
        nonlocal iter_iptv, next_iptv
        cfg_now = load_cron_config()
        try:
            croniter(cfg_now["iptv_cron"])
            print(f"[CRON-DAEMON] 热加载cron表达式: {cfg_now['iptv_cron']}")
        except CroniterBadCronError as e:
            print(f"[CRON-DAEMON] ❌ cron表达式解析错误：{e}，定时暂停，请在网页修正配置")
            iter_iptv = None
            return
        local_now = datetime.datetime.now()
        iter_iptv = croniter(cfg_now["iptv_cron"], local_now)
        next_dt = iter_iptv.get_next(datetime.datetime)
        next_iptv = next_dt.timestamp()
        print(f"[CRON-DAEMON] iptv下次执行时间: {next_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    rebuild()
    while True:
        if reload_cron_signal.is_set():
            print("[CRON-DAEMON] 收到配置更新信号，重新加载crontab")
            rebuild()
            reload_cron_signal.clear()
        now = time.time()
        if iter_iptv is not None and now >= next_iptv:
            run_iptv_task(source="cron")
            next_dt = iter_iptv.get_next(datetime.datetime)
            next_iptv = next_dt.timestamp()
            print(f"[CRON-DAEMON] iptv下次执行时间: {next_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(1)

threading.Thread(target=cron_daemon, daemon=True).start()

def login_required(f):
    def wrap(*args,**kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args,**kwargs)
    wrap.__name__ = f.__name__
    return wrap

@app.route('/login',methods=["GET","POST"])
def login():
    err_msg = ""
    if request.method == "POST":
        u = request.form.get("user","")
        p = request.form.get("pwd","")
        if u == PANEL_USER and p == PANEL_PASS:
            session["logged_in"] = True
            return redirect("/")
        else:
            err_msg = "用户名或密码错误"
    return render_template("login.html", err_msg=err_msg)

@app.route('/logout')
def logout():
    session.clear()
    return redirect("/login")

@app.route('/')
@login_required
def index():
    """控制面板：统计总频道数 / M3U 文件数 / 成功抓取次数 / 最近抓取时间 + 最近任务日志"""
    # 输出 M3U 文件
    m3u_files = []
    if os.path.isdir(PANEL_ROOT):
        m3u_files = sorted([fn for fn in os.listdir(PANEL_ROOT) if fn.endswith(".m3u")])
    # 总频道数：取最近生成的一个 M3U 的 #EXTINF 行数
    total_channels = 0
    if m3u_files:
        try:
            with open(os.path.join(PANEL_ROOT, m3u_files[0]), encoding="utf-8") as f:
                total_channels = sum(1 for line in f if line.startswith("#EXTINF"))
        except Exception:
            total_channels = 0
    # 抓取成功次数 + 最近抓取时间
    logs = load_task_log()
    ok_count = sum(1 for it in logs if it.get("status") == "success")
    last_time = logs[-1]["time_str"] if logs else "暂无记录"
    stats = {
        "total_channels": total_channels,
        "m3u_files": m3u_files,
        "file_count": len(m3u_files),
        "ok_count": ok_count,
        "last_time": last_time,
    }
    return render_template("index.html", stats=stats, recent_logs=logs[-6:][::-1])

@app.route('/logtask')
@login_required
def page_logtask():
    log_list = load_task_log()
    log_list = list(reversed(log_list))
    return render_template("tasklog.html", log_list=log_list)

@app.route('/logtask/clear',methods=["POST"])
@login_required
def logtask_clear():
    try:
        save_task_log([])
        return json.dumps({"ok":True})
    except Exception as e:
        return json.dumps({"ok":False,"msg":str(e)})

@app.route('/editor', methods=["GET","POST"])
@login_required
def editor_page():
    """专用配置页：读写 config.json（服务器/输出/鉴权/频道分组/自动分类/排序/定时）"""
    if request.method == "POST":
        try:
            req = request.get_json(silent=True) or {}
            cfg = {}
            for sec in ("server", "output", "auth", "channel_map", "auto_group", "group_order", "cron"):
                if sec in req and req[sec] is not None:
                    cfg[sec] = req[sec]
            if not cfg:
                return json.dumps({"ok": False, "msg": "❌没有接收到可保存的配置"})
            # 若本次未编辑 cron 且已有 cron，保留原值，避免丢配置
            existing = load_panel_config()
            if "cron" not in cfg and existing.get("cron"):
                cfg["cron"] = existing["cron"]
            save_panel_config(cfg)
            # 定时规则有变更则热加载
            if "cron" in req:
                reload_cron_signal.set()
            return json.dumps({"ok": True, "msg": "✅配置已保存到 config.json，请回首页手动执行抓取验证"})
        except Exception as e:
            return json.dumps({"ok": False, "msg": f"❌保存失败：{str(e)}"})
    cfg = load_panel_config()
    if not cfg:
        # 首次进入且 config.json 尚未生成：由 iptv.py 生成默认配置
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("iptvmod", SCRIPT_PATH)
            mm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mm)
            cfg = load_panel_config()
        except Exception:
            cfg = {}
    return render_template("editor.html", cfg=cfg)

@app.route('/cron', methods=["GET","POST"])
@login_required
def cron_page():
    global reload_cron_signal
    msg = ""
    msgcls = ""
    cfg = load_cron_config()
    if request.method == "POST":
        iptv_cron = request.form.get("iptv_cron","").strip()
        auto_start = bool(request.form.get("auto_run_on_start"))
        try:
            croniter(iptv_cron)
        except CroniterBadCronError as e:
            msg = f"❌ cron表达式无效：{e}"
            msgcls = "msg-err"
        else:
            newcfg = {
                "iptv_cron": iptv_cron,
                "auto_run_on_start": auto_start
            }
            save_cron_config(newcfg)
            reload_cron_signal.set()
            msg = "✅ 配置已保存，定时规则已自动热加载，立即生效！"
            msgcls = "msg-ok"
            cfg = newcfg
    return render_template("cron.html", cron_val=cfg["iptv_cron"], auto_check=cfg["auto_run_on_start"], msg=msg, msgcls=msgcls)

@app.route('/run', methods=["POST"])
@login_required
def run_task():
    try:
        if not os.path.exists(SCRIPT_PATH):
            append_task_log("fail","manual","脚本文件不存在 "+SCRIPT_PATH)
            return f"❌ 错误：脚本不存在 {SCRIPT_PATH}\n请把 iptv.py 放到 config 目录"
        out, ret_code = run_iptv_task(source="manual")
        return out
    except Exception as e:
        append_task_log("fail","manual","执行异常:"+str(e))
        return f"❌ 执行异常：{str(e)}"

@app.route('/direct/m3u/<path:fullpath>')
def direct_m3u(fullpath):
    abs_target = os.path.abspath(os.path.join(PANEL_ROOT, fullpath))
    abs_base = os.path.abspath(PANEL_ROOT)
    if not abs_target.startswith(abs_base):
        abort(403)
    if not os.path.isfile(abs_target):
        abort(404)
    dir_part = os.path.dirname(abs_target)
    fname_part = os.path.basename(abs_target)
    return send_from_directory(dir_part, fname_part, mimetype="application/x-mpegurl", as_attachment=False)

@app.route('/output/upload',methods=["POST"])
@login_required
def output_upload():
    f = request.files.get("m3ufile")
    if not f or f.filename=="":
        return redirect(request.referrer or "/output")
    orig_name = f.filename
    ext = os.path.splitext(orig_name)[1].lower()
    if ext != ".m3u":
        return redirect(request.referrer or "/output")
    clean_name = orig_name.replace("../","").replace("/","").replace("\\","")
    save_path = os.path.join(PANEL_ROOT, clean_name)
    f.save(save_path)
    return redirect(request.referrer or "/output")

@app.route('/output/delete',methods=["POST"])
@login_required
def output_delete():
    import json
    req = request.get_json(silent=True)
    if not req or "fullpath" not in req:
        return json.dumps({"ok":False,"msg":"参数错误"})
    fp = req["fullpath"]
    abs_target = os.path.abspath(os.path.join(PANEL_ROOT, fp))
    abs_base = os.path.abspath(PANEL_ROOT)
    if not abs_target.startswith(abs_base):
        return json.dumps({"ok":False,"msg":"禁止越权操作"})
    if not os.path.isfile(abs_target):
        return json.dumps({"ok":False,"msg":"文件不存在"})
    try:
        os.remove(abs_target)
        return json.dumps({"ok":True,"msg":"ok"})
    except Exception as e:
        return json.dumps({"ok":False,"msg":str(e)})

@app.route('/output', defaults={'subpath': ''})
@app.route('/output/<path:subpath>')
@login_required
def output_handler(subpath):
    target = os.path.join(PANEL_ROOT, subpath)
    if not os.path.abspath(target).startswith(os.path.abspath(PANEL_ROOT)):
        abort(403)
    if not os.path.exists(target):
        abort(404)
    if os.path.isdir(target):
        up_link = ""
        if subpath:
            parts = subpath.split('/')
            parts.pop()
            parent_sub = '/'.join(parts)
            if parent_sub:
                up_link = f"/output/{parent_sub}"
            else:
                up_link = "/output"
        items = []
        for name in sorted(os.listdir(target)):
            full_rel = os.path.join(subpath, name) if subpath else name
            full_abs = os.path.join(target, name)
            link = f"/output/{full_rel}"
            is_dir = os.path.isdir(full_abs)
            is_m3u = name.lower().endswith(".m3u")
            items.append({"name":name,"link":link,"relpath":full_rel,"is_dir":is_dir,"is_m3u":is_m3u})
        return render_template("filelist.html", up_link=up_link, items=items)
    else:
        return send_from_directory(os.path.dirname(target), os.path.basename(target))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8999, debug=False)
