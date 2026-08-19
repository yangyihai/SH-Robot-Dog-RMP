# -*- coding: utf-8 -*-
"""
上海-研测-资源管理平台 —— 后端服务
- 提供静态页面（html/css/js）
- 提供 JSON API，数据持久化到 SQLite 单文件数据库（devices.db）
- 自动清理：超过 RETENTION_DAYS 天的数据（使用记录 / 过期预约 / 过期待领取）会被删除

运行：
    python3 server.py
    # 自定义端口： PORT=9000 python3 server.py
同事访问： http://<本机内网IP>:8080
"""
import os
import io
import csv
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, Response
import feishu_notify

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "devices.db")
RETENTION_DAYS = 3  # 仅保留最近 N 天的数据，更早的自动清理

lock = threading.Lock()

# 设备静态清单（首次启动写入数据库，之后以数据库为准）
DEVS = [
    ("d1", "小狗点L1", "L1", "XG01-589357"),
    ("d2", "小狗点L1", "L1", "XG01-66E037"),
    ("d3", "小狗点L1", "L1", "XG01-66E037"),
    ("d4", "小狗点L1", "L1", "维修中"),
    ("d5", "小狗轮L1", "LW1", "XG03-5B9030"),
    ("d6", "小狗轮L1", "LW1", "未达"),  # 申请中
    ("d7", "中狗M1", "中狗激光版M1", "M1-5c5010"),
    ("d8", "中狗M1", "中狗激光版M1", "M1-64F0005"),
    ("d9", "中狗Ultra", "中狗环视版Ultra", "CMCC-Ultra"),
]

app = Flask(__name__)


# ===== 时间工具 =====
def iso_now():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_exp(hours):
    return (datetime.utcnow() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def threshold():
    return (datetime.utcnow() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===== 数据库 =====
def get_db():
    conn = __import__("sqlite3").connect(DB)
    conn.row_factory = __import__("sqlite3").Row
    return conn


def init_db():
    with lock:
        conn = get_db()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices(
                id TEXT PRIMARY KEY, name TEXT, series TEXT, sn TEXT);
            CREATE TABLE IF NOT EXISTS checkouts(
                device_id TEXT PRIMARY KEY, user TEXT, dept TEXT,
                purpose TEXT, checkout_time TEXT, expected_return TEXT);
            CREATE TABLE IF NOT EXISTS reserves(
                id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT,
                user TEXT, dept TEXT, purpose TEXT, timestamp TEXT);
            CREATE TABLE IF NOT EXISTS pendings(
                device_id TEXT PRIMARY KEY, user TEXT, dept TEXT,
                purpose TEXT, timestamp TEXT);
            CREATE TABLE IF NOT EXISTS history(
                id INTEGER PRIMARY KEY AUTOINCREMENT, device_name TEXT,
                series TEXT, user TEXT, dept TEXT, purpose TEXT,
                checkout_time TEXT, return_time TEXT, note TEXT);
            """
        )
        # 列迁移：为老数据库补充 status / broken_note 字段
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(devices)")]
        if "status" not in cols:
            conn.execute("ALTER TABLE devices ADD COLUMN status TEXT DEFAULT 'ok'")
        if "broken_note" not in cols:
            conn.execute("ALTER TABLE devices ADD COLUMN broken_note TEXT DEFAULT ''")
        ccols = [r["name"] for r in conn.execute("PRAGMA table_info(checkouts)")]
        if "overdue_notified" not in ccols:
            conn.execute("ALTER TABLE checkouts ADD COLUMN overdue_notified INTEGER DEFAULT 0")
        if conn.execute("SELECT COUNT(*) c FROM devices").fetchone()["c"] == 0:
            conn.executemany(
                "INSERT INTO devices(id,name,series,sn) VALUES(?,?,?,?)", DEVS
            )
        conn.commit()
        conn.close()


def cleanup():
    """删除超过保留期的数据：使用记录 / 过期预约 / 过期待领取"""
    with lock:
        conn = get_db()
        th = threshold()
        conn.execute("DELETE FROM history WHERE return_time < ?", (th,))
        conn.execute("DELETE FROM reserves WHERE timestamp < ?", (th,))
        conn.execute("DELETE FROM pendings WHERE timestamp < ?", (th,))
        conn.commit()
        conn.close()


def build_state():
    """读取当前全量状态（调用方需持有 lock）"""
    conn = get_db()
    devices = [
        dict(
            id=r["id"], name=r["name"], series=r["series"], sn=r["sn"],
            status=(r["status"] or "ok"),
            brokenNote=(r["broken_note"] or ""),
        )
        for r in conn.execute("SELECT * FROM devices")
    ]
    checkouts = {}
    for r in conn.execute("SELECT * FROM checkouts"):
        checkouts[r["device_id"]] = {
            "user": r["user"], "dept": r["dept"], "purpose": r["purpose"],
            "checkoutTime": r["checkout_time"], "expectedReturn": r["expected_return"],
        }
    reserves = {}
    for r in conn.execute("SELECT * FROM reserves ORDER BY id"):
        reserves.setdefault(r["device_id"], []).append(
            {"user": r["user"], "dept": r["dept"],
             "purpose": r["purpose"], "timestamp": r["timestamp"]}
        )
    pendings = {}
    for r in conn.execute("SELECT * FROM pendings"):
        pendings[r["device_id"]] = {
            "user": r["user"], "dept": r["dept"],
            "purpose": r["purpose"], "timestamp": r["timestamp"],
        }
    hist = []
    for r in conn.execute("SELECT * FROM history ORDER BY id"):
        hist.append(
            {"deviceName": r["device_name"], "series": r["series"], "user": r["user"],
             "dept": r["dept"], "purpose": r["purpose"], "checkoutTime": r["checkout_time"],
             "returnTime": r["return_time"], "note": r["note"]}
        )
    conn.close()
    return {
        "devices": devices, "checkouts": checkouts,
        "reserves": reserves, "pendings": pendings, "hist": hist,
    }


# ===== 静态页面 =====
@app.route("/")
def index():
    return send_from_directory(BASE, "SH_Dog_zskj.html")


@app.route("/SH_Dog_zskj.html")
def page_html():
    return send_from_directory(BASE, "SH_Dog_zskj.html")


@app.route("/SH_Dog_zskj.js")
def page_js():
    return send_from_directory(BASE, "SH_Dog_zskj.js")


@app.route("/SH_Dog_zskj.css")
def page_css():
    return send_from_directory(BASE, "SH_Dog_zskj.css")


# ===== API =====
@app.route("/api/state")
def api_state():
    with lock:
        s = build_state()
    return jsonify(s)


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    d = request.get_json(force=True)
    dev = d["deviceId"]
    user = d.get("user")
    dept = d.get("dept", "")
    purpose = d.get("purpose", "")
    hours = int(d.get("hours", 4))
    with lock:
        conn = get_db()
        drow = conn.execute("SELECT status FROM devices WHERE id=?", (dev,)).fetchone()
        if drow and (drow["status"] or "ok") == "broken":
            conn.close()
            return jsonify({"error": "设备处于故障/维修中，暂不可领用"}), 400
        if conn.execute("SELECT 1 FROM checkouts WHERE device_id=?", (dev,)).fetchone():
            conn.close()
            return jsonify({"error": "设备已被领用"}), 400
        if conn.execute("SELECT 1 FROM pendings WHERE device_id=?", (dev,)).fetchone():
            conn.close()
            return jsonify({"error": "设备待领取中"}), 400
        devrow = conn.execute("SELECT name,sn FROM devices WHERE id=?", (dev,)).fetchone()
        conn.execute(
            "INSERT INTO checkouts(device_id,user,dept,purpose,checkout_time,expected_return) "
            "VALUES(?,?,?,?,?,?)",
            (dev, user, dept, purpose, iso_now(), iso_exp(hours)),
        )
        conn.commit()
        conn.close()
        s = build_state()
    feishu_notify.notify_group_async(
        f"【资源管理平台·群动态】{user}（{dept}）领用了 {devrow['name']}（{devrow['sn']}），用途：{purpose or '未填写'}，预计 {hours} 小时后归还。")
    return jsonify({"msg": f"{devrow['name']} 已领用", "state": s})


@app.route("/api/return", methods=["POST"])
def api_return():
    d = request.get_json(force=True)
    dev = d["deviceId"]
    note = d.get("note", "")
    user = d.get("user")
    dept = d.get("dept", "")
    with lock:
        conn = get_db()
        row = conn.execute("SELECT * FROM checkouts WHERE device_id=?", (dev,)).fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "设备未处于领用状态"}), 400
        # 必须姓名+部门同时匹配，防止同名不同部门误归还
        if row["user"] != user or row["dept"] != dept:
            conn.close()
            return jsonify({"error": "仅领用人本人（姓名+部门一致）可归还"}), 400
        devrow = conn.execute(
            "SELECT name,series,sn FROM devices WHERE id=?", (dev,)
        ).fetchone()
        now = iso_now()
        conn.execute(
            "INSERT INTO history(device_name,series,user,dept,purpose,checkout_time,return_time,note) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (devrow["name"], devrow["series"], row["user"], row["dept"],
             row["purpose"], row["checkout_time"], now, note),
        )
        conn.execute("DELETE FROM checkouts WHERE device_id=?", (dev,))
        nxt = conn.execute(
            "SELECT * FROM reserves WHERE device_id=? ORDER BY id LIMIT 1", (dev,)
        ).fetchone()
        notify = None
        if nxt:
            conn.execute("DELETE FROM reserves WHERE id=?", (nxt["id"],))
            conn.execute(
                "INSERT INTO pendings(device_id,user,dept,purpose,timestamp) VALUES(?,?,?,?,?)",
                (dev, nxt["user"], nxt["dept"], nxt["purpose"], nxt["timestamp"]),
            )
            msg = f"{devrow['name']} 已归还，已为 {nxt['user']} 保留"
            if nxt["user"] == row["user"]:
                notify = "有一台设备为您准备好了，请前往领取"
        else:
            msg = f"{devrow['name']} 已归还"
        conn.commit()
        conn.close()
        s = build_state()
    if nxt and nxt["user"] != row["user"]:
        feishu_notify.notify_group_async(
            f"【资源管理平台·群提醒】{nxt['user']} 预约的 {devrow['name']}（{devrow['sn']}）已归还，已为其保留，请尽快前往领取。")
    return jsonify({"msg": msg, "notify": notify, "state": s})


@app.route("/api/reserve", methods=["POST"])
def api_reserve():
    d = request.get_json(force=True)
    dev = d["deviceId"]
    user = d.get("user")
    dept = d.get("dept", "")
    purpose = d.get("purpose", "")
    with lock:
        conn = get_db()
        drow = conn.execute("SELECT status FROM devices WHERE id=?", (dev,)).fetchone()
        if drow and (drow["status"] or "ok") == "broken":
            conn.close()
            return jsonify({"error": "设备处于故障/维修中，暂不可预约"}), 400
        in_use = conn.execute(
            "SELECT 1 FROM checkouts WHERE device_id=?", (dev,)
        ).fetchone()
        pending = conn.execute(
            "SELECT 1 FROM pendings WHERE device_id=?", (dev,)
        ).fetchone()
        if not in_use and not pending:
            conn.close()
            return jsonify({"error": "设备当前空闲，可直接领用"}), 400
        if conn.execute(
            "SELECT 1 FROM reserves WHERE device_id=? AND user=? AND dept=?", (dev, user, dept)
        ).fetchone():
            conn.close()
            return jsonify({"error": "您已在此设备的预约队列中"}), 400
        cnt = conn.execute(
            "SELECT COUNT(*) c FROM reserves WHERE device_id=?", (dev,)
        ).fetchone()["c"]
        conn.execute(
            "INSERT INTO reserves(device_id,user,dept,purpose,timestamp) VALUES(?,?,?,?,?)",
            (dev, user, dept, purpose, iso_now()),
        )
        pos = cnt + 1
        dr = conn.execute("SELECT name,sn FROM devices WHERE id=?", (dev,)).fetchone()
        devname = dr["name"]
        devsn = dr["sn"]
        conn.commit()
        conn.close()
        s = build_state()
    feishu_notify.notify_group_async(
        f"【资源管理平台·群动态】{user}（{dept}）预约了 {devname}（{devsn}），当前排第 {pos} 位。")
    return jsonify({"msg": f"预约成功，排在第 {pos} 位", "state": s})


@app.route("/api/cancel_reserve", methods=["POST"])
def api_cancel_reserve():
    d = request.get_json(force=True)
    dev = d["deviceId"]
    user = d.get("user")
    dept = d.get("dept", "")
    with lock:
        conn = get_db()
        conn.execute(
            "DELETE FROM reserves WHERE device_id=? AND user=? AND dept=?", (dev, user, dept)
        )
        conn.commit()
        conn.close()
        s = build_state()
    return jsonify({"msg": "已取消预约", "state": s})


@app.route("/api/claim", methods=["POST"])
def api_claim():
    d = request.get_json(force=True)
    dev = d["deviceId"]
    user = d.get("user")
    dept = d.get("dept", "")
    hours = int(d.get("hours", 4))
    with lock:
        conn = get_db()
        p = conn.execute("SELECT * FROM pendings WHERE device_id=?", (dev,)).fetchone()
        if not p:
            conn.close()
            return jsonify({"error": "设备未处于待领取状态"}), 400
        # 必须姓名+部门同时匹配，防止他人误领
        if p["user"] != user or p["dept"] != dept:
            conn.close()
            return jsonify({"error": "仅待领取人本人（姓名+部门一致）可领取"}), 400
        devrow = conn.execute("SELECT name,sn FROM devices WHERE id=?", (dev,)).fetchone()
        conn.execute(
            "INSERT INTO checkouts(device_id,user,dept,purpose,checkout_time,expected_return) "
            "VALUES(?,?,?,?,?,?)",
            (dev, p["user"], p["dept"], p["purpose"], iso_now(), iso_exp(hours)),
        )
        conn.execute("DELETE FROM pendings WHERE device_id=?", (dev,))
        conn.commit()
        conn.close()
        s = build_state()
    feishu_notify.notify_group_async(
        f"【资源管理平台·群动态】{user}（{dept}）领取了 {devrow['name']}（{devrow['sn']}）。")
    return jsonify({"msg": f"{devrow['name']} 已领取", "state": s})


@app.route("/api/decline_claim", methods=["POST"])
def api_decline_claim():
    d = request.get_json(force=True)
    dev = d["deviceId"]
    with lock:
        conn = get_db()
        devrow = conn.execute("SELECT name,sn FROM devices WHERE id=?", (dev,)).fetchone()
        conn.execute("DELETE FROM pendings WHERE device_id=?", (dev,))
        nxt = conn.execute(
            "SELECT * FROM reserves WHERE device_id=? ORDER BY id LIMIT 1", (dev,)
        ).fetchone()
        if nxt:
            conn.execute("DELETE FROM reserves WHERE id=?", (nxt["id"],))
            conn.execute(
                "INSERT INTO pendings(device_id,user,dept,purpose,timestamp) VALUES(?,?,?,?,?)",
                (dev, nxt["user"], nxt["dept"], nxt["purpose"], nxt["timestamp"]),
            )
            msg = f"已跳过，设备已为 {nxt['user']} 保留"
        else:
            msg = f"{devrow['name']} 已释放"
        conn.commit()
        conn.close()
        s = build_state()
    if nxt:
        feishu_notify.notify_group_async(
            f"【资源管理平台·群提醒】{devrow['name']}（{devrow['sn']}）已为 {nxt['user']} 保留，请尽快前往领取。")
    return jsonify({"msg": msg, "state": s})


@app.route("/api/add_device", methods=["POST"])
def api_add_device():
    d = request.get_json(force=True)
    name = d.get("name", "").strip()
    series = d.get("series", "").strip()
    sn = d.get("sn", "").strip()
    if not name:
        return jsonify({"error": "设备名称不能为空"}), 400
    if not series:
        return jsonify({"error": "产品线不能为空"}), 400
    if not sn:
        return jsonify({"error": "序列号不能为空"}), 400
    with lock:
        conn = get_db()
        # 检查序列号是否已存在
        if conn.execute("SELECT 1 FROM devices WHERE sn=?", (sn,)).fetchone():
            conn.close()
            return jsonify({"error": f"序列号 {sn} 已存在"}), 400
        # 生成唯一 ID
        import uuid
        dev_id = "d" + uuid.uuid4().hex[:8]
        conn.execute(
            "INSERT INTO devices(id,name,series,sn) VALUES(?,?,?,?)",
            (dev_id, name, series, sn),
        )
        conn.commit()
        conn.close()
        s = build_state()
    feishu_notify.notify_group_async(
        f"【资源管理平台·群动态】新增设备：{name}（{series} · {sn}）。")
    return jsonify({"msg": f"{name} 已添加到设备列表", "state": s})


def _broken_notify(dev, devname, devsn, user, note):
    """发送报修的群通知（首次报修与"重新通知"复用）。
    先清掉旧的去重记录，确保本次一定能重新推送。"""
    tail = f"（{note}）" if note else ""
    feishu_notify.reset_notif(f"broken:{dev}")   # 清除旧记录，确保本次能重新推送
    feishu_notify.notify_group_once_async(
        f"broken:{dev}",
        f"【资源管理平台·群提醒】{devname}（{devsn}）报修：{user} 提交{tail}，请安排维修。")
    feishu_notify.reset_notif(f"repaired:{dev}")   # 允许修复后再次报修时重新提醒


@app.route("/api/report_broken", methods=["POST"])
def api_report_broken():
    """标记设备为故障/维修中（仅限非领用、非待领取的设备）。
    若设备已处于故障状态，则视为"重新通知"，重新推送群消息而不报错
    （用于补发之前静默失败的推送）。"""
    d = request.get_json(force=True)
    dev = d["deviceId"]
    user = d.get("user")
    note = d.get("note", "").strip()
    with lock:
        conn = get_db()
        devrow = conn.execute("SELECT name,sn,status FROM devices WHERE id=?", (dev,)).fetchone()
        if not devrow:
            conn.close()
            return jsonify({"error": "设备不存在"}), 400
        already = (devrow["status"] or "ok") == "broken"
        if not already:
            if conn.execute("SELECT 1 FROM checkouts WHERE device_id=?", (dev,)).fetchone():
                conn.close()
                return jsonify({"error": "设备使用中，请先归还后再报修"}), 400
            if conn.execute("SELECT 1 FROM pendings WHERE device_id=?", (dev,)).fetchone():
                conn.close()
                return jsonify({"error": "设备待领取中，无法报修"}), 400
            conn.execute(
                "UPDATE devices SET status='broken', broken_note=? WHERE id=?", (note, dev)
            )
            conn.commit()
        conn.close()
        s = build_state()
    _broken_notify(dev, devrow["name"], devrow["sn"], user, note)
    msg = (f"{devrow['name']} 已标记为故障/维修中"
           if not already else f"{devrow['name']} 已是故障状态，已重新推送群通知")
    return jsonify({"msg": msg, "state": s})


@app.route("/api/repair", methods=["POST"])
def api_repair():
    """将故障设备恢复为空闲可用"""
    d = request.get_json(force=True)
    dev = d["deviceId"]
    with lock:
        conn = get_db()
        devrow = conn.execute("SELECT name,sn,status FROM devices WHERE id=?", (dev,)).fetchone()
        if not devrow:
            conn.close()
            return jsonify({"error": "设备不存在"}), 400
        if (devrow["status"] or "ok") != "broken":
            conn.close()
            return jsonify({"error": "设备当前不处于故障状态"}), 400
        conn.execute(
            "UPDATE devices SET status='ok', broken_note='' WHERE id=?", (dev,)
        )
        pend = conn.execute("SELECT user FROM pendings WHERE device_id=?", (dev,)).fetchone()
        conn.commit()
        conn.close()
        s = build_state()
    if pend:
        feishu_notify.notify_group_async(
            f"【资源管理平台·群提醒】{devrow['name']}（{devrow['sn']}）已修复完成，{pend['user']} 请前往领取。")
    feishu_notify.notify_group_once_async(
        f"repaired:{dev}",
        f"【资源管理平台·群提醒】{devrow['name']}（{devrow['sn']}）已修复完成，恢复可用。")
    feishu_notify.reset_notif(f"broken:{dev}")   # 允许再次报修时重新提醒
    return jsonify({"msg": f"{devrow['name']} 已恢复为可用", "state": s})


@app.route("/api/edit_device", methods=["POST"])
def api_edit_device():
    """编辑设备的名称 / 产品线 / 序列号"""
    d = request.get_json(force=True)
    dev = d["deviceId"]
    name = d.get("name", "").strip()
    series = d.get("series", "").strip()
    sn = d.get("sn", "").strip()
    if d.get("dept", "") != "测试":
        return jsonify({"error": "仅测试部门可编辑设备信息"}), 403
    if not name:
        return jsonify({"error": "设备名称不能为空"}), 400
    if not series:
        return jsonify({"error": "产品线不能为空"}), 400
    if not sn:
        return jsonify({"error": "序列号不能为空"}), 400
    with lock:
        conn = get_db()
        if not conn.execute("SELECT 1 FROM devices WHERE id=?", (dev,)).fetchone():
            conn.close()
            return jsonify({"error": "设备不存在"}), 400
        # 序列号唯一性校验（排除自己）
        if conn.execute(
            "SELECT 1 FROM devices WHERE sn=? AND id<>?", (sn, dev)
        ).fetchone():
            conn.close()
            return jsonify({"error": f"序列号 {sn} 已被其他设备占用"}), 400
        conn.execute(
            "UPDATE devices SET name=?, series=?, sn=? WHERE id=?", (name, series, sn, dev)
        )
        conn.commit()
        conn.close()
        s = build_state()
    return jsonify({"msg": f"{name} 信息已更新", "state": s})


@app.route("/api/delete_device", methods=["POST"])
def api_delete_device():
    """删除/下线设备（仅限无进行中领用/待领取/预约的设备）"""
    d = request.get_json(force=True)
    dev = d["deviceId"]
    if d.get("dept", "") != "测试":
        return jsonify({"error": "仅测试部门可删除设备"}), 403
    with lock:
        conn = get_db()
        devrow = conn.execute("SELECT name,sn FROM devices WHERE id=?", (dev,)).fetchone()
        if not devrow:
            conn.close()
            return jsonify({"error": "设备不存在"}), 400
        if conn.execute("SELECT 1 FROM checkouts WHERE device_id=?", (dev,)).fetchone():
            conn.close()
            return jsonify({"error": "设备正在使用中，请先归还后再删除"}), 400
        if conn.execute("SELECT 1 FROM pendings WHERE device_id=?", (dev,)).fetchone():
            conn.close()
            return jsonify({"error": "设备待领取中，无法删除"}), 400
        if conn.execute("SELECT 1 FROM reserves WHERE device_id=?", (dev,)).fetchone():
            conn.close()
            return jsonify({"error": "设备存在预约排队，请先清空预约后再删除"}), 400
        conn.execute("DELETE FROM devices WHERE id=?", (dev,))
        conn.commit()
        conn.close()
        s = build_state()
    feishu_notify.notify_group_once_async(
        f"deleted:{dev}",
        f"【资源管理平台·群提醒】{devrow['name']}（{devrow['sn']}）已从设备列表下线。")
    return jsonify({"msg": f"{devrow['name']} 已从设备列表删除", "state": s})


@app.route("/api/export")
def api_export():
    with lock:
        conn = get_db()
        rows = conn.execute("SELECT * FROM history ORDER BY id").fetchall()
        conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["设备名称", "产品线", "使用人", "部门", "用途", "领用时间", "归还时间", "备注"])
    for r in rows:
        w.writerow([r["device_name"], r["series"], r["user"], r["dept"],
                    r["purpose"] or "", r["checkout_time"], r["return_time"], r["note"] or ""])
    out = "﻿" + buf.getvalue()
    return Response(
        out,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=设备记录.csv"},
    )


@app.route("/api/notify_group", methods=["POST"])
def api_notify_group():
    """向飞书群发送一条提醒消息（群 ID 取 FEISHU_GROUP_CHAT_ID，可在请求体用 chatId 覆盖）。"""
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    chat_id = (d.get("chatId") or "").strip() or None
    if not text:
        return jsonify({"error": "消息内容不能为空"}), 400
    ok, resp = feishu_notify.notify_group(text, chat_id)
    if not ok:
        return jsonify({"error": "群消息发送失败", "detail": resp}), 500
    return jsonify({"msg": "已发送到飞书群", "resp": resp})


# ===== 自动清理后台线程 =====
def cleanup_loop():
    while True:
        time.sleep(3600)
        try:
            cleanup()
        except Exception:
            pass


def overdue_check():
    """扫描已超期未归还的设备，推送到群聊（每设备仅催一次）。"""
    with lock:
        conn = get_db()
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = conn.execute(
            "SELECT c.device_id, c.user, c.dept, d.name, d.sn FROM checkouts c "
            "JOIN devices d ON d.id=c.device_id "
            "WHERE c.expected_return < ? AND COALESCE(c.overdue_notified,0)=0", (now,)
        ).fetchall()
        for r in rows:
            conn.execute("UPDATE checkouts SET overdue_notified=1 WHERE device_id=?",
                         (r["device_id"],))
        conn.commit()
        conn.close()
    for r in rows:
        feishu_notify.notify_group_async(
            f"【资源管理平台·群提醒】超时提醒：{r['user']}（{r['dept']}）领用的 {r['name']}（{r['sn']}）已超时未归还，请尽快归还或续期。")


def overdue_loop():
    while True:
        time.sleep(600)
        try:
            overdue_check()
        except Exception:
            pass


if __name__ == "__main__":
    init_db()
    cleanup()  # 启动时先清理一次
    threading.Thread(target=cleanup_loop, daemon=True).start()
    threading.Thread(target=overdue_loop, daemon=True).start()
    try:
        overdue_check()  # 启动即检查一次超期
    except Exception:
        pass
    port = int(os.environ.get("PORT", 8080))
    print(f"资源管理平台已启动: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
