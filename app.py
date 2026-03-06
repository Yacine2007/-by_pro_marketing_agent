import os
import re
import json
import requests
import time
import threading
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ========== المتغيرات الأساسية ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
# معرف المدير الوحيد والصحيح
OWNER_FB_ID = '2592319994'
OWNER_PASSWORD = "20070909"
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"
BINANCE_ID = "1074084246"
COMPANY_WEBSITE = "https://b.y-pro.kesug.com"  # الرابط المطلوب

# ========== البرومبت المحترف (بدون هلوسة) ==========
SYSTEM_PROMPT = """أنت مساعد مبيعات رسمي لشركة B.Y PRO للتكنولوجيا والبرمجيات.

هويتك المهنية:
- وكيل مبيعات بشري محترف، هادئ، واثق، ومختصر جداً.
- تتحدث باللغة التي يخاطبك بها المستخدم (عربية فصحى، إنجليزية، إلخ).
- لا تستخدم الرموز التعبيرية أبداً.
- لا تكرر الجمل الترحيبية المملة.

قواعد صارمة:
1. لا تختلق معلومات أبداً. إذا لم تكن متأكداً، قل "ليس لدي هذه المعلومة حالياً".
2. لا تسأل عن تفاصيل شخصية غير ضرورية (العمر، المهنة، إلخ).
3. للتعريف بالشركة، يمكنك ذكر الموقع الرسمي: b.y-pro.kesug.com

الخدمات والأسعار (سوق 2026):
- مواقع تعريفية: 300-800$ (5-10 أيام)
- متاجر إلكترونية: 700-1800$ (15-25 يوماً)
- بوتات الذكاء الاصطناعي: من 300$ (7-14 يوماً)
- تطبيقات موبايل: من 1500$ (30-60 يوماً)
- تصميم جرافيك: 50-200$ (24-72 ساعة)

التعامل المالي:
- 30% عربون، 70% عند التسليم.
- الدفع عبر USDT (Binance Pay) فقط.
- معرف بينانس: 1074084246

التفاوض: إذا حاول العميل تخفيض السعر كثيراً، قل: "أسعارنا تعكس معايير الجودة والالتزام بالمواعيد، ولا نقدم خصومات إضافية حالياً".

مهمتك: تحويل الاستفسار إلى مشروع قائم وتقديم تفاصيل الدفع للعميل الجاد."""

# ========== تخزين البيانات ==========
logs = deque(maxlen=100)
stats = {'msgs_received': 0, 'msgs_sent': 0, 'start_time': datetime.now().isoformat()}

ORDERS_FILE = "orders.json"
BLOCKED_FILE = "blocked_users.json"
VERIFIED_FILE = "verified_users.json"
NOTES_FILE = "order_notes.json"

def load_json(f, default):
    try:
        with open(f, 'r', encoding='utf-8') as file:
            return json.load(file)
    except:
        return default

def save_json(f, data):
    with open(f, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

orders = load_json(ORDERS_FILE, [])
blocked_users = set(load_json(BLOCKED_FILE, []))
verified_users = set(load_json(VERIFIED_FILE, []))
order_notes = load_json(NOTES_FILE, {})

# ========== الجلسات ==========
sessions = {}

class ClientData:
    def __init__(self, sid):
        self.sid = sid
        self.name = ""
        self.service = ""
        self.budget = 0
        self.phone = ""
        self.confirmed = False
        self.conversation = []
        self.awaiting_pw = False
        self.lang = 'ar'  # لغة افتراضية

    def is_complete(self):
        return bool(self.name and self.service and self.budget > 0)

    def get_link(self):
        return f"https://www.facebook.com/messages/t/{self.sid}"

# ========== دوال مساعدة ==========
def add_log(msg):
    logs.appendleft({'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg})
    print(f"[{logs[0]['time']}] {msg}")

def send_fb(recipient, text):
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {'recipient': {'id': recipient}, 'message': {'text': text}, 'messaging_type': 'RESPONSE'}
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            stats['msgs_sent'] += 1
            add_log(f"✓ أرسل إلى {recipient[:10]}...: {text[:40]}")
            return True
    except:
        pass
    return False

def is_owner(sid):
    return sid == OWNER_FB_ID or sid in verified_users

# ========== دوال الطلبات ==========
def save_new_order(client):
    global orders
    order = {
        'id': len(orders) + 1,
        'name': client.name,
        'service': client.service,
        'budget': client.budget,
        'phone': client.phone,
        'timestamp': datetime.now().isoformat(),
        'sid': client.sid,
        'link': client.get_link(),
        'notes': '',
        'status': 'جديد',
        'conversation': client.conversation[-5:]
    }
    orders.append(order)
    save_json(ORDERS_FILE, orders)
    add_log(f"طلب #{order['id']} - {client.name}")
    return order

def get_orders_today():
    today = datetime.now().strftime('%Y-%m-%d')
    return [o for o in orders if o['timestamp'].startswith(today)]

def format_order_list(order_list, title):
    if not order_list:
        return "لا توجد طلبات."
    lines = [f"{title} ({len(order_list)}):"]
    for o in order_list[-5:]:
        lines.append(f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$")
    return "\n".join(lines)

def notify_owner(order):
    msg = f"""🔔 طلب جديد
رقم {order['id']}
الاسم: {order['name']}
الخدمة: {order['service']}
الميزانية: {order['budget']}$
{order['link']}"""
    send_fb(OWNER_FB_ID, msg)

# ========== تنفيذ أوامر المدير (بدون ذكاء اصطناعي) ==========
def exec_owner_cmd(text, sid):
    t = text.strip().lower()
    parts = t.split()

    # إحصائيات
    if any(k in t for k in ['احصائيات', 'احصاء', 'stats']):
        today_ords = len(get_orders_today())
        msg = f"📊 إحصائيات:\n• العملاء: {len(sessions)}\n• الطلبات الكلية: {len(orders)}\n• طلبات اليوم: {today_ords}\n• المحظورين: {len(blocked_users)}"
        send_fb(sid, msg)
        return True

    # طلبات اليوم
    if any(k in t for k in ['طلبات اليوم', 'اليوم']):
        ords = get_orders_today()
        send_fb(sid, format_order_list(ords, "طلبات اليوم"))
        return True

    # كل الطلبات
    if any(k in t for k in ['كل الطلبات', 'جميع الطلبات']):
        send_fb(sid, format_order_list(orders, "جميع الطلبات"))
        return True

    # تفاصيل طلب محدد
    if any(k in t for k in ['تفاصيل', 'order']):
        nums = [int(p) for p in parts if p.isdigit()]
        if nums:
            oid = nums[0]
            order = next((o for o in orders if o['id'] == oid), None)
            if order:
                msg = f"""📋 الطلب {oid}
الاسم: {order['name']}
الخدمة: {order['service']}
الميزانية: {order['budget']}$
الجوال: {order.get('phone', 'غير متوفر')}
الحالة: {order['status']}
ملاحظات: {order_notes.get(str(oid), '')}"""
                send_fb(sid, msg)
            else:
                send_fb(sid, f"الطلب {oid} غير موجود.")
        return True

    # حظر مستخدم
    if t.startswith('حظر ') or t.startswith('block '):
        if len(parts) >= 2 and parts[1].isdigit():
            blocked_users.add(parts[1])
            save_json(BLOCKED_FILE, list(blocked_users))
            send_fb(sid, f"تم حظر {parts[1][:10]}...")
            add_log(f"حظر {parts[1][:10]}...")
        return True

    # إلغاء حظر
    if t.startswith('الغاء حظر ') or t.startswith('unblock '):
        if len(parts) >= 2 and parts[1] in blocked_users:
            blocked_users.remove(parts[1])
            save_json(BLOCKED_FILE, list(blocked_users))
            send_fb(sid, f"تم إلغاء حظر {parts[1][:10]}...")
        return True

    # المحظورون
    if any(k in t for k in ['المحظورين', 'blocked']):
        if not blocked_users:
            send_fb(sid, "لا يوجد محظورون.")
        else:
            bl = "\n".join([f"• {uid[:15]}..." for uid in list(blocked_users)[:10]])
            send_fb(sid, f"المحظورون ({len(blocked_users)}):\n{bl}")
        return True

    return False  # ليس أمراً معروفاً

# ========== استخراج بيانات العميل ==========
def extract_data(text, client):
    changed = False
    # الاسم
    if not client.name:
        match = re.search(r'(?:اسمي|الاسم|my name is)\s*[:\s]*([\w\s]{2,30})', text, re.I)
        if match:
            client.name = match.group(1).strip()
            add_log(f"الاسم: {client.name}")
            changed = True
    # الخدمة
    if not client.service:
        svc_map = {
            'شعار': 'تصميم شعار', 'logo': 'تصميم شعار',
            'موقع': 'تصميم موقع', 'website': 'تصميم موقع',
            'متجر': 'متجر إلكتروني', 'ecommerce': 'متجر إلكتروني',
            'تطبيق': 'تطبيق جوال', 'app': 'تطبيق جوال',
            'بوت': 'بوت ذكاء اصطناعي', 'bot': 'بوت ذكاء اصطناعي',
            'تصميم': 'تصميم جرافيك', 'design': 'تصميم جرافيك'
        }
        for kw, svc in svc_map.items():
            if kw in text.lower():
                client.service = svc
                add_log(f"الخدمة: {svc}")
                changed = True
                break
    # الميزانية
    if client.budget == 0:
        match = re.search(r'(\d+)[\s-]*(?:usdt|\$|دولار)', text, re.I)
        if match:
            client.budget = int(match.group(1))
            add_log(f"الميزانية: {client.budget}$")
            changed = True
    # رقم الجوال (أرقام سعودية شائعة)
    if not client.phone:
        match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9})', text)
        if match:
            client.phone = match.group(1)
            add_log(f"الجوال: {client.phone}")
            changed = True
    return changed

# ========== الذكاء الاصطناعي (للردود فقط) ==========
def get_ai_response(msg, client, owner_mode=False):
    try:
        prompt = SYSTEM_PROMPT
        if owner_mode:
            prompt += "\n\n(المستخدم هو المدير، كن مباشراً جداً.)"
        else:
            prompt += "\n\n(المستخدم عميل محتمل، اجمع البيانات بأدب.)"

        context = f"{prompt}\n\nآخر محادثة:\n" + "\n".join(client.conversation[-4:]) + f"\nالمستخدم: {msg}\nالرد:"
        r = requests.get(f'{AI_API_URL}?text={requests.utils.quote(context)}', timeout=10)
        if r.status_code == 200:
            return r.json().get('response', '').strip()
    except:
        pass
    return "عذراً، حدث خطأ تقني. حاول مرة أخرى."

# ========== المعالجة الرئيسية ==========
def process_message(sid, text):
    stats['msgs_received'] += 1
    add_log(f"من {sid[:10]}...: {text[:40]}")

    # حظر
    if sid in blocked_users:
        return

    # جلسة جديدة
    if sid not in sessions:
        sessions[sid] = ClientData(sid)
    client = sessions[sid]
    client.conversation.append(f"المستخدم: {text}")

    # مدير
    if is_owner(sid):
        if exec_owner_cmd(text, sid):  # إذا كان أمراً، نفذ ولا تستخدم الذكاء
            client.conversation.append("النظام: أمر منفذ")
            return
        # وإلا رد عادي بالذكاء
        resp = get_ai_response(text, client, owner_mode=True)
        send_fb(sid, resp)
        client.conversation.append(f"الرد: {resp[:40]}")
        return

    # كلمة المرور
    if client.awaiting_pw:
        if text.strip() == OWNER_PASSWORD:
            verified_users.add(sid)
            save_json(VERIFIED_FILE, list(verified_users))
            client.awaiting_pw = False
            send_fb(sid, "أهلاً بك.")
            add_log(f"تحقق مدير: {sid[:10]}...")
        else:
            send_fb(sid, "كلمة المرور غير صحيحة.")
        return

    # كشف محاولة مدير
    if any(k in text.lower() for k in ['مدير', 'owner', 'المالك', 'ياسين']):
        client.awaiting_pw = True
        send_fb(sid, "الرجاء إدخال الرقم السري:")
        return

    # استخراج البيانات
    data_changed = extract_data(text, client)

    # إذا اكتملت البيانات
    if client.is_complete() and not client.confirmed:
        order = save_new_order(client)
        # رسالة الدفع للعميل
        deposit = int(client.budget * 0.3)
        pay_msg = f"""تم تأكيد طلبك {client.name}.

الخدمة: {client.service}
المبلغ: {client.budget}$ (المقدم {deposit}$)

للدفع عبر USDT (Binance):
المعرف: {BINANCE_ID}

بعد الدفع نبدأ التنفيذ فوراً.
للاستفسار: {COMPANY_WEBSITE}"""
        send_fb(sid, pay_msg)
        # إشعار المدير
        notify_owner(order)
        client.confirmed = True
        return

    # رد عادي من الذكاء
    resp = get_ai_response(text, client)
    send_fb(sid, resp)
    client.conversation.append(f"الرد: {resp[:40]}")

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            for msg in entry.get('messaging', []):
                if 'message' in msg and 'text' in msg['message']:
                    threading.Thread(target=process_message, args=(msg['sender']['id'], msg['message']['text'])).start()
    return 'OK', 200

@app.route('/')
def home():
    html = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head><title>B.Y PRO Agent</title>
    <style>body{background:#f0f2f5;font-family:system-ui;padding:20px}.container{max-width:1200px;margin:0 auto}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:15px;margin-bottom:20px}.card{background:white;padding:20px;border-radius:12px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}.card h3{margin:0 0 10px;color:#444}.card .num{font-size:2em;font-weight:bold;color:#2563eb}.logs{background:white;border-radius:12px;padding:20px;margin-bottom:20px;max-height:200px;overflow-y:auto}.orders{background:white;border-radius:12px;padding:20px}.order{border-bottom:1px solid #eee;padding:10px;display:grid;grid-template-columns:auto 2fr 2fr 1fr 1fr}</style>
    </head>
    <body>
    <div class="container">
        <h1>🤖 B.Y PRO Agent</h1>
        <div class="stats">
            <div class="card"><h3>العملاء</h3><div class="num">{{ total_clients }}</div></div>
            <div class="card"><h3>الطلبات</h3><div class="num">{{ orders_count }}</div></div>
            <div class="card"><h3>المحظورون</h3><div class="num">{{ blocked_count }}</div></div>
            <div class="card"><h3>موثوقون</h3><div class="num">{{ verified_count }}</div></div>
            <div class="card"><h3>رسائل اليوم</h3><div class="num">{{ msgs_today }}</div></div>
        </div>
        <div class="logs">
            <h3>📋 آخر الأحداث</h3>
            {% for log in logs %}<div>[{{ log.time }}] {{ log.msg }}</div>{% endfor %}
        </div>
        <div class="orders">
            <h3>📦 آخر الطلبات</h3>
            {% for o in recent_orders %}
            <div class="order"><span>#{{ o.id }}</span><span>{{ o.name }}</span><span>{{ o.service }}</span><span>{{ o.budget }}$</span><span>{{ o.status }}</span></div>
            {% endfor %}
        </div>
    </div>
    <script>setTimeout(()=>location.reload(),10000);</script>
    </body>
    </html>
    """
    today = datetime.now().strftime('%Y-%m-%d')
    msgs_today = len([l for l in logs if l['time'].startswith(datetime.now().strftime('%H'))])  # تقريبي
    return render_template_string(html,
        total_clients=len(sessions),
        orders_count=len(orders),
        blocked_count=len(blocked_users),
        verified_count=len(verified_users),
        msgs_today=stats['msgs_received'],
        logs=list(logs)[:15],
        recent_orders=orders[-10:] if orders else []
    )

# ========== Keep alive ==========
def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get("https://by-pro-marketing-agent.onrender.com", timeout=3)
        except:
            pass

if __name__ == '__main__':
    print("\n" + "="*50)
    print("B.Y PRO Agent - Version 5 (Professional)")
    print("="*50)
    print(f"👤 Owner: {OWNER_FB_ID}")
    print(f"🔑 Password: {OWNER_PASSWORD}")
    print(f"💰 Binance: {BINANCE_ID}")
    print(f"🌐 Website: {COMPANY_WEBSITE}")
    print(f"📦 Orders: {len(orders)}")
    print("="*50 + "\n")
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
