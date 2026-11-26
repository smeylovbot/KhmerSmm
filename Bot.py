# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║     Kairozen Deposit Bot — カイロゼン                          ║
║     Auto Payment (Bakong KHQR) + Safe Store & Order History  ║
║     Compatible: Python 3.10+ · Termux / Pydroid 3 / Render   ║
╚══════════════════════════════════════════════════════════════╝
"""

import json, logging, time, threading, hashlib, io, os, sys, subprocess
import requests as http_req
import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from flask import Flask, request as flask_request, jsonify, send_from_directory
from flask_cors import CORS
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CLR_RESET   = "\033[0m"
CLR_BOLD    = "\033[1m"
CLR_RED     = "\033[91m"
CLR_GREEN   = "\033[92m"
CLR_YELLOW  = "\033[93m"
CLR_BLUE    = "\033[94m"
CLR_CYAN    = "\033[96m"
CLR_WHITE   = "\033[97m"

class ColoredFormatter(logging.Formatter):
    FORMATS = {
        logging.DEBUG:    f"{CLR_CYAN}%(asctime)s{CLR_RESET} [{CLR_BLUE}%(levelname)s{CLR_RESET}] %(message)s",
        logging.INFO:     f"{CLR_CYAN}%(asctime)s{CLR_RESET} [{CLR_GREEN}%(levelname)s{CLR_RESET}] %(message)s",
        logging.WARNING:  f"{CLR_CYAN}%(asctime)s{CLR_RESET} [{CLR_YELLOW}%(levelname)s{CLR_RESET}] %(message)s",
        logging.ERROR:    f"{CLR_CYAN}%(asctime)s{CLR_RESET} [{CLR_RED}%(levelname)s{CLR_RESET}] %(message)s",
        logging.CRITICAL: f"{CLR_CYAN}%(asctime)s{CLR_RESET} [{CLR_BOLD}{CLR_RED}%(levelname)s{CLR_RESET}] %(message)s"
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter())
logger.addHandler(console_handler)

def _ensure_deps():
    pkgs = {"PIL": "pillow", "qrcode": "qrcode", "flask_cors": "flask-cors"}
    for mod, pkg in pkgs.items():
        try:
            __import__(mod)
        except ImportError:
            logger.info(f"{CLR_YELLOW}Installing missing package: {pkg}...{CLR_RESET}")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "--break-system-packages", "-q"],
                check=False
            )
_ensure_deps()

# ═══════════════════════════════════════════════════════════
#  CONFIG (Bakong Open API Token & Merchant Info)
# ═══════════════════════════════════════════════════════════
BOT_TOKEN          = "9185336041:AAHyrGRDnIrSzT9tqDWKMZIGjqmVNU4X2HM"
ADMIN_ID           = 8807182741

BAKONG_TOKEN       = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiMjI2YTQ5YmJkNWY5NDRhMyJ9LCJpYXQiOjE3OTQxOTIzOTgsImV4cCI6MTgwMTk2ODM5OH0.PggPYpRIIZJA7GzXWWpWnCXcI7VX9-3T3wuy2Pn1e1Y"
BANK_ACCOUNT       = "mon_samnang@bkrt"
MERCHANT_NAME      = "KhmerSmm"
MERCHANT_CITY      = "Phnom Penh"

DEPOSIT_EXPIRE_SEC = 300

# ═══════════════════════════════════════════════════════════
#  FILES & THREAD LOCK
# ═══════════════════════════════════════════════════════════
DATA_LOCK      = threading.RLock()
WALLETS_FILE   = "aio_wallets.json"
USERS_FILE     = "aio_users.json"
STORE_DEP_FILE = "aio_store_deposits.json"
ACCOUNTS_FILE  = "aio_accounts.json"
ORDERS_FILE    = "aio_orders.json"

def _load(path, default):
    with DATA_LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

def _save(path, data):
    with DATA_LOCK:
        try:
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            logger.error(f"{CLR_RED}Save {path}: {e}{CLR_RESET}")

wallets    = _load(WALLETS_FILE, {})
users_db   = _load(USERS_FILE, {})
store_deps = _load(STORE_DEP_FILE, {})
orders_db  = _load(ORDERS_FILE, {})
waiting    = {}

default_accounts = [
    {
        "id": "acc_chatgpt_pro_1",
        "key": "chatgpt_pro",
        "title": "ChatGPT Pro",
        "price": 10.00,
        "duration": "1ខែ",
        "category": "ai",
        "desc": "គណនី ChatGPT Pro កម្រិតខ្ពស់ សម្រាប់ការងារ AI និង Coding រហ័សរលូន។",
        "data": "Email: chatgpt.pro01@mail.com | Pass: ProPass#2026",
        "sold": False,
        "buyer": None
    },
    {
        "id": "acc_surfshark_1",
        "key": "surfshark_vpn",
        "title": "VPN Surfshark",
        "price": 8.99,
        "duration": "1ខែ",
        "category": "vpn",
        "desc": "ការពារភាពឯកជន លឿនលឿន ប្តូរ Server បានច្រើនប្រទេសដោយគ្មានដែនកំណត់។",
        "data": "Email: surfshark01@mail.com | Pass: VpnSafe#2026",
        "sold": False,
        "buyer": None
    },
    {
        "id": "acc_super_grok_1",
        "key": "super_grok",
        "title": "Supper Grok",
        "price": 10.00,
        "duration": "1ខែ",
        "category": "ai",
        "desc": "មុខងារ AI ឆ្លើយតបរហ័ស វិភាគទិន្នន័យ និងបង្កើតមាតិកាពេញលេញ។",
        "data": "Email: supergrok01@mail.com | Pass: GrokAI#2026",
        "sold": False,
        "buyer": None
    },
    {
        "id": "acc_yt_premium_1",
        "key": "youtube_premium",
        "title": "YouTube Premium",
        "price": 3.00,
        "duration": "1ខែ",
        "category": "media",
        "desc": "មើលវីដេអូគ្មានការរំខានដោយផ្សាយពាណិជ្ជកម្ម និងចាក់ Background បាន។",
        "data": "Email: ytprem01@mail.com | Pass: MediaTube#2026",
        "sold": False,
        "buyer": None
    },
    {
        "id": "acc_canva_pro_1",
        "key": "canva_pro",
        "title": "Canva Pro",
        "price": 12.99,
        "duration": "1ខែ",
        "category": "design",
        "desc": "រចនាក្រាហ្វិក Template Pro, Background Remover និង Font ពេញលេញ។",
        "data": "Email: canvapros01@mail.com | Pass: DesignPro#2026",
        "sold": False,
        "buyer": None
    },
    {
        "id": "acc_gemini_pro_18",
        "key": "gemini_pro",
        "title": "Gemini Pro",
        "price": 5.00,
        "duration": "18ខែ",
        "category": "ai",
        "desc": "ប្រើប្រាស់ Gemini Pro រយៈពេល 18 ខែពេញ ជំនួយការ AI ដ៏មានថាមពល។",
        "data": "Email: geminipro01@mail.com | Pass: Gemini18M#2026",
        "sold": False,
        "buyer": None
    },
    {
        "id": "acc_capcut_pro_1",
        "key": "capcut_pro",
        "title": "CapCut Pro",
        "price": 3.99,
        "duration": "1ខែ",
        "category": "design",
        "desc": "កាត់តវីដេអូប្រើ Effect, Transitions និង Export គុណភាពខ្ពស់គ្មាន Watermark។",
        "data": "Email: capcutpro01@mail.com | Pass: CapEdit#2026",
        "sold": False,
        "buyer": None
    }
]

if not os.path.exists(ACCOUNTS_FILE):
    _save(ACCOUNTS_FILE, default_accounts)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

def _make_session():
    s = http_req.Session()
    r = Retry(total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    a = HTTPAdapter(max_retries=r)
    s.mount("http://", a)
    s.mount("https://", a)
    return s

http = _make_session()

def bal(uid):
    with DATA_LOCK:
        return round(float(wallets.get(str(uid), 0.0)), 2)

def add_bal(uid, amt):
    with DATA_LOCK:
        wallets[str(uid)] = round(bal(uid) + float(amt), 2)
        _save(WALLETS_FILE, wallets)

def record_order(mid, acc):
    with DATA_LOCK:
        mid_str = str(mid)
        orders_db.setdefault(mid_str, [])
        orders_db[mid_str].insert(0, {
            "order_id": f"ORD-{int(time.time())}-{len(orders_db[mid_str]) + 1}",
            "acc_id": acc["id"],
            "title": acc["title"],
            "duration": acc.get("duration", "1ខែ"),
            "price": round(float(acc["price"]), 2),
            "account_data": acc["data"],
            "purchased_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        _save(ORDERS_FILE, orders_db)

def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("💳 ដាក់ប្រាក់")
    return kb

def admin_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👥 អ្នកប្រើប្រាស់", "📊 ស្ថិតិ")
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("✕ Cancel")
    return kb

def deposit_amt_kb():
    amts = [1, 2, 5, 10, 20, 50]
    btns = []
    row = []
    for a in amts:
        row.append(InlineKeyboardButton(f"${a}", callback_data=f"dep:{a}"))
        if len(row) == 3:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    btns.append([InlineKeyboardButton("✏️ ផ្ទាល់ខ្លួន", callback_data="dep:custom")])
    return InlineKeyboardMarkup(btns)

def _admin_deposit_kb(dep_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ដាក់ប្រាក់ឱ្យគេ", callback_data=f"manual_dep:approve:{dep_id}"),
        InlineKeyboardButton("❌ កុំដាក់ប្រាក់ឱ្យគេ", callback_data=f"manual_dep:reject:{dep_id}")
    ]])

def _generate_khqr(uid, amount, note=""):
    try:
        from bakong_khqr import KHQR
        k = KHQR(BAKONG_TOKEN)
        qr_str = k.create_qr(
            bank_account  = BANK_ACCOUNT,
            merchant_name = MERCHANT_NAME,
            merchant_city = MERCHANT_CITY,
            amount        = round(float(amount), 2),
            currency      = "USD",
            bill_number   = (str(note) or f"uid{uid}")[:25],
            static        = False,
        )
        return qr_str or ""
    except Exception as e:
        logger.error(f"{CLR_RED}[_generate_khqr] ❌ {e}{CLR_RESET}")
    return ""

def _check_bakong(md5):
    if not md5:
        return False
    # 1) Try bakong-khqr SDK
    try:
        from bakong_khqr import KHQR as _BK
        k = _BK(BAKONG_TOKEN)
        res = k.check_payment(str(md5))
        logger.info(f"[Bakong SDK] md5={md5} -> {res}")
        if res == "PAID":
            return True
        if isinstance(res, dict):
            if str(res.get("responseCode")) == "0" and res.get("data"):
                return True
            if str(res.get("status", "")).upper() == "PAID":
                return True
    except Exception as e:
        logger.warning(f"[Bakong SDK Error] {e}")

    # 2) Direct Bakong Open API check_transaction_by_md5
    try:
        r = http.post(
            "https://api-bakong.nbc.gov.kh/v1/check_transaction_by_md5",
            json={"md5": str(md5)},
            headers={
                "Authorization": f"Bearer {BAKONG_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        logger.info(f"[Bakong API] status={r.status_code} body={r.text[:300]}")
        if r.ok:
            data_json = r.json()
            if str(data_json.get("responseCode")) == "0" and data_json.get("data"):
                return True
    except Exception as e:
        logger.warning(f"[Bakong API Error] {e}")

    return False

def _confirm_deposit_if_pending(dep_id, source="Auto"):
    with DATA_LOCK:
        dep = store_deps.get(dep_id)
        if not dep:
            return False, 0.0
        if dep.get("status") == "confirmed":
            return True, bal(dep["uid"])
        if dep.get("status") == "rejected":
            return False, bal(dep["uid"])

        uid_str = str(dep["uid"])
        amount = round(float(dep["amount"]), 2)
        add_bal(uid_str, amount)
        dep["status"] = "confirmed"
        dep["confirmed_via"] = source
        _save(STORE_DEP_FILE, store_deps)
        new_b = bal(uid_str)

    try:
        bot.send_message(
            ADMIN_ID,
            f"✅ <b>Auto Payment ជោគជ័យ ({source})!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 User/Member: <code>{uid_str}</code>\n"
            f"💰 បញ្ញើ: <b>${amount:.2f}</b>\n"
            f"💳 សមតុល្យថ្មី: <b>${new_b:.2f}</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    return True, new_b

def _watch_deposit(uid, uid_str, dep_id, amount, sent_msg_id=None):
    deadline = time.time() + DEPOSIT_EXPIRE_SEC
    last_update_min = -1

    while time.time() < deadline:
        with DATA_LOCK:
            dep = store_deps.get(dep_id)
            if not dep or dep.get("status") != "pending":
                return
            md5 = dep.get("md5", "")

        if md5 and _check_bakong(md5):
            ok, new_b = _confirm_deposit_if_pending(dep_id, source="Bakong Auto")
            if ok:
                msg = (
                    f"✅ <b>ដាក់លុយបានជោគជ័យ (Auto)!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💰 បញ្ញើ: <b>${amount:.2f}</b>\n"
                    f"💳 សាច់ប្រាក់: <b>${new_b:.2f}</b>"
                )
                if uid is not None:
                    try:
                        bot.send_message(uid, msg, parse_mode="HTML", reply_markup=main_kb())
                    except Exception:
                        pass
                    if sent_msg_id:
                        try:
                            bot.edit_message_caption(
                                chat_id=uid, message_id=sent_msg_id,
                                caption=f"💳 <b>ដាក់ប្រាក់ (បានទូទាត់រួចរាល់ ✅)</b>\n━━━━━━━━━━━━━━━━━━\n💰 ចំនួន: <b>${amount:.2f}</b>",
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass
            return

        rem_sec = int(deadline - time.time())
        current_min = rem_sec // 60
        if uid is not None and current_min != last_update_min and sent_msg_id and rem_sec > 0:
            last_update_min = current_min
            mins_left = rem_sec // 60
            secs_left = rem_sec % 60
            timer_str = f"{mins_left:02d}:{secs_left:02d}"
            try:
                updated_cap = (
                    f"💳 <b>ដាក់ប្រាក់ (Auto Check Bakong)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💰 ចំនួន: <b>${amount:.2f}</b>\n"
                    f"⏱ រាប់ថយក្រោយ: <b>{timer_str} នាទី</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📱 <b>Bakong KHQR សម្រាប់ទូទាត់</b>"
                )
                bot.edit_message_caption(chat_id=uid, message_id=sent_msg_id, caption=updated_cap, parse_mode="HTML")
            except Exception:
                pass

        time.sleep(3)

    with DATA_LOCK:
        dep = store_deps.get(dep_id)
        if dep and dep.get("status") == "pending":
            dep["status"] = "expired"
            _save(STORE_DEP_FILE, store_deps)
            if uid is not None:
                try:
                    bot.send_message(uid, "⏰ <b>QR ផុតកំណត់!</b> សូមចុច <b>💳 ដាក់ប្រាក់</b> ម្ដងទៀត", parse_mode="HTML", reply_markup=main_kb())
                except Exception:
                    pass
                if sent_msg_id:
                    try:
                        bot.edit_message_caption(
                            chat_id=uid, message_id=sent_msg_id,
                            caption=f"💳 <b>ដាក់ប្រាក់ (ផុតកំណត់ ⏰)</b>\n━━━━━━━━━━━━━━━━━━\n💰 ចំនួន: <b>${amount:.2f}</b>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

def _send_deposit_qr(uid, amount):
    uid_str = str(uid)
    qr_str = _generate_khqr(uid, amount, f"uid{uid}_{int(time.time())}")
    if not qr_str:
        bot.send_message(uid, "⚠️ មានបញ្ហា Generate QR! ទំនាក់ Admin", parse_mode="HTML", reply_markup=main_kb())
        return

    try:
        from bakong_khqr import KHQR as _BK
        k = _BK(BAKONG_TOKEN)
        md5_hash = k.generate_md5(qr_str)
    except Exception:
        md5_hash = hashlib.md5(qr_str.encode()).hexdigest()

    dep_id = f"dep_{uid}_{int(time.time())}"
    with DATA_LOCK:
        store_deps[dep_id] = {
            "uid": uid_str,
            "amount": amount,
            "status": "pending",
            "md5": md5_hash,
            "qr_str": qr_str,
        }
        _save(STORE_DEP_FILE, store_deps)

    cap = (
        f"💳 <b>ដាក់ប្រាក់ (Auto Check Bakong)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 ចំនួន: <b>${amount:.2f}</b>\n"
        f"⏱ រាប់ថយក្រោយ: <b>05:00 នាទី</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>Bakong KHQR សម្រាប់ទូទាត់</b>"
    )

    try:
        admin_txt = (
            f"📥 <b>ការស្នើដាក់លុយថ្មី (Auto Watch)!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 User ID: <code>{uid_str}</code>\n"
            f"💰 ទឹកប្រាក់ស្នើ: <b>${amount:.2f}</b>"
        )
        bot.send_message(ADMIN_ID, admin_txt, parse_mode="HTML", reply_markup=_admin_deposit_kb(dep_id))
    except Exception as e:
        logger.error(f"{CLR_RED}[deposit] Admin notification error: {e}{CLR_RESET}")

    img_buf = None
    try:
        import qrcode as _qrc
        qr = _qrc.QRCode(box_size=6, border=2)
        qr.add_data(qr_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        img_buf.seek(0)
    except Exception:
        pass

    sent_msg_id = None
    if img_buf:
        try:
            img_buf.seek(0)
            sent_msg = bot.send_photo(uid, img_buf, caption=cap, parse_mode="HTML")
            sent_msg_id = sent_msg.message_id
        except Exception:
            sent_msg = bot.send_message(uid, f"{cap}\n\n<code>{qr_str}</code>", parse_mode="HTML")
            sent_msg_id = sent_msg.message_id
    else:
        sent_msg = bot.send_message(uid, f"{cap}\n\n<code>{qr_str}</code>", parse_mode="HTML")
        sent_msg_id = sent_msg.message_id

    threading.Thread(
        target=_watch_deposit,
        args=(uid, uid_str, dep_id, amount, sent_msg_id),
        daemon=True
    ).start()

def _track_user(message):
    with DATA_LOCK:
        uid = message.chat.id
        uid_str = str(uid)
        u = message.from_user
        users_db[uid_str] = {
            "name":     u.first_name or "",
            "username": u.username or "",
            "last":     int(time.time()),
        }
        _save(USERS_FILE, users_db)
        wallets.setdefault(uid_str, 0.0)

def _show_welcome(uid, name="User"):
    caption = (
        f"👋 សួស្តី <b>{name}</b> ស្វាគមន៍មកកាន់ <b>Kairozen カイロゼン</b>!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💳 ចុច <b>💳 ដាក់ប្រាក់</b> ដើម្បីបញ្ចូលលុយតាម Bakong KHQR (Auto)"
    )
    bot.send_message(uid, caption, parse_mode="HTML", reply_markup=main_kb())

@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.chat.id
    waiting.pop(uid, None)
    _track_user(message)
    if uid == ADMIN_ID:
        bot.send_message(
            uid,
            f"🤖 <b>Panel Admin — Kairozen Deposit</b>\n━━━━━━━━━━━━━━━━━━\n🆔 <code>{ADMIN_ID}</code>",
            parse_mode="HTML",
            reply_markup=admin_kb()
        )
        return
    _show_welcome(uid, message.from_user.first_name or "User")

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep:"))
def cb_dep(call):
    uid = call.message.chat.id
    val = call.data[4:]
    bot.answer_callback_query(call.id)

    if val == "custom":
        waiting[uid] = "dep_custom"
        bot.send_message(
            uid,
            "✏️ <b>ផ្ញើចំនួន $ ដែលចង់ដាក់ប្រាក់ (ចាប់ពី 0.10$ ឡើងទៅ):</b>",
            parse_mode="HTML",
            reply_markup=cancel_kb()
        )
        return

    amount = float(val)
    waiting.pop(uid, None)
    _send_deposit_qr(uid, amount)

@bot.callback_query_handler(func=lambda c: c.data.startswith("manual_dep:"))
def cb_manual_dep(call):
    uid = call.message.chat.id
    if uid != ADMIN_ID:
        bot.answer_callback_query(call.id)
        return

    _, action, dep_id = call.data.split(":", 2)
    with DATA_LOCK:
        dep = store_deps.get(dep_id)
        if not dep:
            bot.answer_callback_query(call.id, "❌ សំណើនេះរកមិនឃើញ!", show_alert=True)
            return
        target_uid = str(dep["uid"])
        amount = round(float(dep["amount"]), 2)
        status = dep.get("status")

    if action == "approve":
        if status == "confirmed":
            bot.answer_callback_query(call.id, "⚠️ បានបញ្ជាក់រួចរាល់ហើយ!", show_alert=True)
            return
        _, new_b = _confirm_deposit_if_pending(dep_id, source="Admin Manual")
        bot.answer_callback_query(call.id, "✅ បានដាក់ប្រាក់ឱ្យគេរួចរាល់!")
        try:
            bot.edit_message_text(
                f"✅ <b>បានដាក់ប្រាក់ឱ្យគេរួចរាល់!</b>\n━━━━━━━━━━━━━━━━━━\n👤 User: <code>{target_uid}</code>\n💰 ចំនួន: <b>${amount:.2f}</b>\n💳 សមតុល្យថ្មី: <b>${new_b:.2f}</b>",
                chat_id=uid, message_id=call.message.message_id, parse_mode="HTML"
            )
        except Exception:
            pass
        if target_uid.isdigit():
            try:
                bot.send_message(
                    int(target_uid),
                    f"✅ <b>ដាក់លុយបានជោគជ័យ!</b>\n━━━━━━━━━━━━━━━━━━\n💰 បញ្ញើ: <b>${amount:.2f}</b>\n💳 សាច់ប្រាក់: <b>${new_b:.2f}</b>",
                    parse_mode="HTML",
                    reply_markup=main_kb()
                )
            except Exception:
                pass

    elif action == "reject":
        with DATA_LOCK:
            dep["status"] = "rejected"
            _save(STORE_DEP_FILE, store_deps)
        bot.answer_callback_query(call.id, "❌ បានបដិសេធសំណើ!")
        try:
            bot.edit_message_text(
                f"❌ <b>បានបដិសេធ (កុំដាក់ប្រាក់ឱ្យគេ)!</b>\n━━━━━━━━━━━━━━━━━━\n👤 User: <code>{target_uid}</code>\n💰 ចំនួន: <b>${amount:.2f}</b>",
                chat_id=uid, message_id=call.message.message_id, parse_mode="HTML"
            )
        except Exception:
            pass

@bot.message_handler(func=lambda m: True)
def handle(message):
    uid     = message.chat.id
    text    = message.text.strip() if message.text else ""
    step    = waiting.get(uid)

    _track_user(message)

    if text in ("✕ Cancel", "❌ Cancel", "❌ បោះបង់"):
        waiting.pop(uid, None)
        kb = admin_kb() if uid == ADMIN_ID else main_kb()
        bot.send_message(uid, "🏠 Menu", reply_markup=kb)
        return

    if uid == ADMIN_ID:
        if text == "👥 អ្នកប្រើប្រាស់":
            with DATA_LOCK:
                if not users_db and not wallets:
                    bot.send_message(uid, "❌ គ្មានអ្នកប្រើប្រាស់", parse_mode="HTML", reply_markup=admin_kb())
                    return
                lines = ["<b>👥 អ្នកប្រើប្រាស់ & Member</b>\n━━━━━━━━━━━━━━━━━━"]
                for u_id, u_info in sorted(users_db.items(), key=lambda x: x[1].get("last", 0), reverse=True)[:30]:
                    name = u_info.get("name") or "?"
                    uname = f"@{u_info['username']}" if u_info.get("username") else ""
                    b = bal(u_id)
                    lines.append(f"👤 <b>{name}</b> {uname}\n🆔 <code>{u_id}</code> · 💰 <b>${b:.2f}</b>")
                for m_id, m_bal in wallets.items():
                    if m_id not in users_db:
                        lines.append(f"🌐 Member <code>{m_id}</code> · 💰 <b>${float(m_bal):.2f}</b>")
            bot.send_message(uid, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=admin_kb())
            return

        if text == "📊 ស្ថិតិ":
            with DATA_LOCK:
                total_users = max(len(users_db), len(wallets))
                total_deps  = sum(float(d.get("amount", 0)) for d in store_deps.values() if d.get("status") == "confirmed")
                total_bal   = sum(float(v) for v in wallets.values())
            bot.send_message(
                uid,
                f"📊 <b>ស្ថិតិ</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👥 អ្នកប្រើប្រាស់សរុប: <b>{total_users}</b>\n"
                f"💰 ប្រាក់ដាក់ជោគជ័យសរុប: <b>${total_deps:.2f}</b>\n"
                f"💳 សាច់ប្រាក់ក្នុងប្រព័ន្ធ: <b>${total_bal:.2f}</b>",
                parse_mode="HTML",
                reply_markup=admin_kb()
            )
            return

        bot.send_message(uid, "👇 ជ្រើសប៊ូតុង <b>👥 អ្នកប្រើប្រាស់</b> ឬ <b>📊 ស្ថិតិ</b>", parse_mode="HTML", reply_markup=admin_kb())
        return

    if step == "dep_custom":
        try:
            amount = float(text.replace("$", ""))
            if amount < 0.1:
                raise ValueError
            waiting.pop(uid, None)
            _send_deposit_qr(uid, amount)
        except Exception:
            bot.send_message(uid, "❌ ចំនួនខុស! សូមបញ្ចូលចាប់ពី 0.10$ ឡើងទៅ", parse_mode="HTML", reply_markup=cancel_kb())
        return

    if text in ("💳 ដាក់ប្រាក់", "💰 ដាក់ប្រាក់", "💰 Top Up", "💳 Top Up", "💸 បញ្ចូលលុយ"):
        waiting.pop(uid, None)
        bot.send_message(
            uid,
            "💳 <b>ដាក់ប្រាក់</b>\n━━━━━━━━━━━━━━━━━━\nជ្រើសចំនួនដែលចង់ដាក់ប្រាក់៖",
            parse_mode="HTML",
            reply_markup=deposit_amt_kb()
        )
        return

    bot.send_message(uid, "💳 ចុចប៊ូតុង <b>💳 ដាក់ប្រាក់</b> ខាងក្រោម", parse_mode="HTML", reply_markup=main_kb())

# ═══════════════════════════════════════════════════════════
#  FLASK WEB API & WEBSITE SERVE
# ═══════════════════════════════════════════════════════════
flask_app = Flask(__name__)
CORS(flask_app)
CONTROL_KEY = "kairozen_secret_2025"

@flask_app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")

def _check_key():
    key = flask_request.args.get("key") or (flask_request.get_json(silent=True) or {}).get("key")
    return key == CONTROL_KEY

@flask_app.route("/health")
def health():
    return jsonify({"status": "running", "bot": "Kairozen Deposit"})

@flask_app.route("/status")
def status():
    if not _check_key():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({"status": "running", "users": len(users_db), "wallets": len(wallets)})

@flask_app.route("/shutdown", methods=["GET", "POST"])
def shutdown():
    if not _check_key():
        return jsonify({"error": "Unauthorized"}), 403
    def _stop():
        time.sleep(0.5)
        bot.stop_polling()
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=_stop, daemon=True).start()
    return jsonify({"status": "shutting_down"})

@flask_app.route("/restart", methods=["GET", "POST"])
def restart():
    if not _check_key():
        return jsonify({"error": "Unauthorized"}), 403
    def _restart():
        time.sleep(0.5)
        bot.stop_polling()
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=_restart, daemon=True).start()
    return jsonify({"status": "restarting"})

@flask_app.route("/api/user/<member_id>", methods=["GET"])
def api_get_user(member_id):
    mid = str(member_id).strip()
    if not mid:
        return jsonify({"ok": False, "error": "Member ID មិនត្រឹមត្រូវ!"}), 400
    with DATA_LOCK:
        wallets.setdefault(mid, 0.0)
        _save(WALLETS_FILE, wallets)
        user_orders = list(orders_db.get(mid, []))
    return jsonify({
        "ok": True,
        "uid": mid,
        "name": f"Member {mid}",
        "balance": bal(mid),
        "orders": user_orders
    })

@flask_app.route("/api/orders/<member_id>", methods=["GET"])
def api_get_orders(member_id):
    mid = str(member_id).strip()
    if not mid:
        return jsonify({"ok": False, "error": "Member ID មិនត្រឹមត្រូវ!"}), 400
    with DATA_LOCK:
        user_orders = list(orders_db.get(mid, []))
    return jsonify({"ok": True, "uid": mid, "orders": user_orders})

@flask_app.route("/api/accounts", methods=["GET"])
def api_get_accounts():
    with DATA_LOCK:
        accs = _load(ACCOUNTS_FILE, default_accounts)
        available = [
            {
                "id": a["id"],
                "key": a.get("key", a["id"]),
                "title": a["title"],
                "price": float(a["price"]),
                "duration": a.get("duration", "1ខែ"),
                "category": a.get("category", "ai"),
                "desc": a["desc"]
            }
            for a in accs if not a.get("sold", False)
        ]
    return jsonify({"ok": True, "accounts": available})

@flask_app.route("/api/buy", methods=["POST"])
def api_buy_account():
    data = flask_request.get_json(silent=True) or {}
    mid = str(data.get("uid", "")).strip()
    acc_id = str(data.get("acc_id", "")).strip()

    if not mid:
        return jsonify({"ok": False, "error": "សូមបញ្ចូល Member ID ជាមុនសិន!"}), 400
    if not acc_id:
        return jsonify({"ok": False, "error": "មិនមានលេខកូដអីវ៉ាន់ទេ!"}), 400

    with DATA_LOCK:
        accs = _load(ACCOUNTS_FILE, default_accounts)
        target_acc = next((a for a in accs if a["id"] == acc_id and not a.get("sold", False)), None)
        if not target_acc:
            return jsonify({"ok": False, "error": "អីវ៉ាន់នេះត្រូវបានលក់រួចហើយ ឬអស់ពីស្តុក!"}), 400

        price = round(float(target_acc["price"]), 2)
        current_bal = bal(mid)

        if current_bal < price:
            return jsonify({
                "ok": False,
                "error": f"ទឹកប្រាក់មិនគ្រប់គ្រាន់! សមតុល្យបច្ចុប្បន្ន ${current_bal:.2f} (ត្រូវការ ${price:.2f})។"
            }), 400

        wallets[mid] = round(current_bal - price, 2)
        _save(WALLETS_FILE, wallets)

        target_acc["sold"] = True
        target_acc["buyer"] = mid
        _save(ACCOUNTS_FILE, accs)

        record_order(mid, target_acc)
        new_b = bal(mid)
        acc_secret = target_acc["data"]
        acc_title = target_acc["title"]
        acc_dur = target_acc.get("duration", "1ខែ")

    try:
        bot.send_message(
            ADMIN_ID,
            f"🛒 <b>ការលក់អីវ៉ាន់ពីវេបសាយ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Member: <code>{mid}</code>\n"
            f"📦 ផលិតផល: <b>{acc_title} ({acc_dur})</b>\n"
            f"💵 តម្លៃ: <b>${price:.2f}</b>\n"
            f"💳 សមតុល្យនៅសល់: <b>${new_b:.2f}</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "account_data": acc_secret,
        "new_balance": new_b
    })

@flask_app.route("/api/create_khqr", methods=["POST"])
def api_create_khqr():
    data = flask_request.get_json(silent=True) or {}
    mid = str(data.get("uid", "")).strip()
    if not mid:
        return jsonify({"ok": False, "error": "មិនមាន Member ID ទេ!"}), 400
    try:
        amount = round(float(data.get("amount", 0)), 2)
    except Exception:
        return jsonify({"ok": False, "error": "ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវ!"}), 400

    if amount < 0.10:
        return jsonify({"ok": False, "error": "ចំនួនទឹកប្រាក់ត្រូវចាប់ពី $0.10 ឡើងទៅ!"}), 400

    qr_str = _generate_khqr(mid, amount, f"web_{int(time.time())}")
    if not qr_str:
        return jsonify({"ok": False, "error": "មិនអាចបង្កើត Bakong KHQR បានទេ!"}), 500

    try:
        from bakong_khqr import KHQR as _BK
        k = _BK(BAKONG_TOKEN)
        md5_hash = k.generate_md5(qr_str)
    except Exception:
        md5_hash = hashlib.md5(qr_str.encode()).hexdigest()

    dep_id = f"web_{mid}_{int(time.time())}"
    with DATA_LOCK:
        store_deps[dep_id] = {
            "uid": mid,
            "amount": amount,
            "status": "pending",
            "md5": md5_hash,
            "qr_str": qr_str,
        }
        _save(STORE_DEP_FILE, store_deps)

    try:
        admin_txt = (
            f"🌐 <b>សំណើ Auto Payment ពីវេបសាយ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Member: <code>{mid}</code>\n"
            f"💰 ចំនួន: <b>${amount:.2f}</b>"
        )
        bot.send_message(ADMIN_ID, admin_txt, parse_mode="HTML", reply_markup=_admin_deposit_kb(dep_id))
    except Exception as e:
        logger.error(f"{CLR_RED}[api_create_khqr] Admin notification error: {e}{CLR_RESET}")

    threading.Thread(
        target=_watch_deposit,
        args=(None, mid, dep_id, amount, None),
        daemon=True
    ).start()

    return jsonify({
        "ok": True,
        "dep_id": dep_id,
        "qr_str": qr_str,
        "md5": md5_hash,
        "amount": amount
    })

@flask_app.route("/api/check_khqr/<dep_id>", methods=["GET"])
def api_check_khqr(dep_id):
    with DATA_LOCK:
        dep = store_deps.get(dep_id)
        if not dep:
            return jsonify({"ok": False, "error": "រកមិនឃើញវិក្កយបត្រនេះទេ!"}), 404

        if dep.get("status") == "confirmed":
            return jsonify({"ok": True, "status": "PAID", "balance": bal(dep["uid"])})

        md5 = dep.get("md5", "")

    if md5 and _check_bakong(md5):
        ok, new_b = _confirm_deposit_if_pending(dep_id, source="Bakong Web Auto")
        if ok:
            return jsonify({"ok": True, "status": "PAID", "balance": new_b})

    return jsonify({"ok": True, "status": "PENDING"})

def run_flask():
    port = int(os.environ.get("PORT", 5055))
    logger.info(f"{CLR_CYAN}🌐 Control & Store API Server running on port {port}{CLR_RESET}")
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def print_banner():
    banner = f"""
{CLR_CYAN}{CLR_BOLD}╔══════════════════════════════════════════════════════════════╗
║     {CLR_GREEN}Kairozen Deposit Bot — カイロゼン                          ║
║     {CLR_YELLOW}Auto Payment Bakong KHQR + Safe Store & Order History  ║
║     {CLR_WHITE}Compatible: Python 3.10+ · Termux / Pydroid 3         {CLR_CYAN}║
╚══════════════════════════════════════════════════════════════╝{CLR_RESET}
"""
    print(banner)

if __name__ == "__main__":
    print_banner()
    logger.info(f"{CLR_BOLD}{CLR_GREEN}🚀 Kairozen Deposit Bot កំពុងចាប់ផ្ដើម...{CLR_RESET}")
    threading.Thread(target=run_flask, daemon=True).start()
    time.sleep(2)
    bot.infinity_polling(timeout=20, long_polling_timeout=15)
