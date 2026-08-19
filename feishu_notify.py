# -*- coding: utf-8 -*-
"""
飞书自建应用 —— 群聊推送（无需通讯录权限）
============================================
依赖环境变量（在 dog-server.service 的 Environment 中配置，切勿硬编码）：
  FEISHU_APP_ID          自建应用 App ID
  FEISHU_APP_SECRET      自建应用 App Secret
  FEISHU_ENABLED         是否启用推送，取值 "1" / "0"，默认 "0"
  FEISHU_GROUP_CHAT_ID   目标群聊 chat_id（必填）

工作流程：
  1) 用 App ID/Secret 换取 tenant_access_token（内存缓存，过期自动刷新）
  2) 直接向群聊（chat_id）发送消息，无需按姓名搜索用户

优点：
  - 不需要 contact:user.base:readonly 等通讯录权限
  - 所有成员在群里都能看到通知，不会遗漏
"""
import os
import json
import time
import sqlite3
import threading
import urllib.request

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
ENABLED = os.environ.get("FEISHU_ENABLED", "0") == "1"

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
# 群消息：接收者 ID 类型为 chat_id（群 ID）
GROUP_SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
# 默认通知群（在 dog-server.service 的 Environment 中配置，可通过 FEISHU_GROUP_CHAT_ID 覆盖）
GROUP_CHAT_ID = os.environ.get("FEISHU_GROUP_CHAT_ID", "")

_token = {"value": None, "exp": 0}
_token_lock = threading.Lock()


def _http(url, method="GET", data=None, headers=None, timeout=8):
    headers = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_token():
    """获取 tenant_access_token，带内存缓存与过期刷新。"""
    if not (APP_ID and APP_SECRET):
        return None
    now = time.time()
    with _token_lock:
        if _token["value"] and now < _token["exp"] - 60:
            return _token["value"]
        try:
            r = _http(TOKEN_URL, method="POST",
                      data={"app_id": APP_ID, "app_secret": APP_SECRET})
        except Exception as e:
            print("[飞书] 获取 token 失败:", e)
            return None
        if r.get("code") != 0:
            print("[飞书] 获取 token 返回错误:", r)
            return None
        _token["value"] = r.get("tenant_access_token")
        _token["exp"] = now + int(r.get("expire", 7200))
        return _token["value"]


def send_group(chat_id, msg_type, content_dict):
    """给群聊（chat_id）发送消息。content_dict 为对应 msg_type 的内容字典（会自动 JSON 序列化）。
    返回 (success:bool, resp:dict)。"""
    token = get_token()
    if not token:
        return False, {"err": "no token"}
    try:
        r = _http(GROUP_SEND_URL, method="POST",
                  data={"receive_id": chat_id, "msg_type": msg_type,
                        "content": json.dumps(content_dict)},
                  headers={"Authorization": "Bearer " + token})
    except Exception as e:
        print("[飞书] 群发送失败:", e)
        return False, {"err": str(e)}
    if r.get("code") != 0:
        print("[飞书] 群发送返回错误:", r)
        return False, r
    return True, r


def send_group_text(chat_id, text):
    """给群聊发送文本消息。"""
    return send_group(chat_id, "text", {"text": text})


def notify_group(text, chat_id=None):
    """推送到默认配置群（FEISHU_GROUP_CHAT_ID）。返回 (success:bool, resp:dict)。"""
    if not ENABLED:
        return False, {"err": "disabled"}
    cid = chat_id or GROUP_CHAT_ID
    if not cid:
        print("[飞书] 未配置群 chat_id（FEISHU_GROUP_CHAT_ID），无法发送群消息")
        return False, {"err": "no group chat id"}
    return send_group_text(cid, text)


def notify_group_async(text, chat_id=None):
    """异步推送群消息，避免阻塞 HTTP 接口响应。"""
    if not ENABLED:
        return
    threading.Thread(target=notify_group, args=(text, chat_id), daemon=True).start()


# ===== 通知去重（保证每条提醒只发送一次）=====
# 用本地 SQLite 记录已发送的 dedup_key，进程重启也不会重复推送。
_NOTIF_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feishu_notify.db")
_notif_lock = threading.Lock()


def _notif_conn():
    conn = sqlite3.connect(_NOTIF_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notif_log("
        "dedup_key TEXT PRIMARY KEY, sent_at TEXT)")
    return conn


def reset_notif(dedup_key):
    """清除某 key 的发送记录，使将来同 key 的提醒可再次发送（用于状态恢复后）。"""
    if not ENABLED:
        return
    with _notif_lock:
        conn = _notif_conn()
        try:
            conn.execute("DELETE FROM notif_log WHERE dedup_key=?", (dedup_key,))
            conn.commit()
        finally:
            conn.close()


def notify_group_once(dedup_key, text, chat_id=None):
    """同一 dedup_key 仅推送一次（持久化去重）。返回 (success, resp)。
    适用于"状态类提醒"（报修/修复/超时/下线等），避免同一状态被反复推送。"""
    if not ENABLED:
        return False, {"err": "disabled"}
    with _notif_lock:
        conn = _notif_conn()
        try:
            if conn.execute("SELECT 1 FROM notif_log WHERE dedup_key=?", (dedup_key,)).fetchone():
                return False, {"err": "already sent", "dup": True}
            ok, resp = notify_group(text, chat_id)
            if ok:
                conn.execute(
                    "INSERT OR IGNORE INTO notif_log(dedup_key, sent_at) VALUES(?, ?)",
                    (dedup_key, time.strftime("%Y-%m-%dT%H:%M:%SZ")))
                conn.commit()
            return ok, resp
        finally:
            conn.close()


def notify_group_once_async(dedup_key, text, chat_id=None):
    """异步版 notify_group_once。"""
    if not ENABLED:
        return
    threading.Thread(target=notify_group_once, args=(dedup_key, text, chat_id), daemon=True).start()



