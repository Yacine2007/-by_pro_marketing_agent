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
OWNER_FB_ID = '2592319994'  # ضع هنا معرف المدير الحقيقي
OWNER_PASSWORD = "20070909"
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"
BINANCE_ID = "1074084246"
COMPANY_WEBSITE = "https://b.y-pro.kesug.com"

# ========== ملفات التخزين ==========
ORDERS_FILE = "orders.json"
BLOCKED_FILE = "blocked_users.json"
VERIFIED_FILE = "verified_users.json"

def load_json(file, default):
    try:
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

orders = load_json(ORDERS_FILE, [])
blocked_users = set(load_json(BLOCKED_FILE, []))
verified_users = set(load_json(VERIFIED_FILE, []))

# ========== سجل الأحداث ==========
logs = deque(maxlen=100)
stats = {'msgs_received': 0, 'msgs_sent': 0, 'start_time': datetime.now().isoformat()}

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
            add_log(f"✓ إلى {recipient[:10]}...: {text[:40]}")
            return True
    except:
        pass
    return False

def is_owner(sid):
    return sid == OWNER_FB_ID or sid in verified_users

# ========== دوال الطلبات ==========
def save_order(client):
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
        'status': 'جديد'
    }
    orders.append(order)
    save_json(ORDERS_FILE, orders)
    add_log(f"✅ طلب #{order['id']} - {client.name}")
    return order

def get_today_orders():
    today = datetime.now().strftime('%Y-%m-%d')
    return [o for o in orders if o['timestamp'].startswith(today)]

def get_unique_clients():
    return len(set(o['sid'] for o in orders))

def notify_owner(order):
    msg = f"""🔔 طلب جديد #{order['id']}
الاسم: {order['name']}
الخدمة: {order['service']}
الميزانية: {order['budget']}$
{order['link']}"""
    send_fb(OWNER_FB_ID, msg)

# ========== جلسات العملاء ==========
sessions = {}

class Client:
    def __init__(self, sid):
        self.sid = sid
        self.name = ""
        self.service = ""
        self.budget = 0
        self.phone = ""
        self.confirmed = False
        self.conversation = []
        self.awaiting_pw = False

    def is_complete(self):
        return bool(self.name and self.service and self.budget > 0)

    def get_link(self):
        return f"https://www.facebook.com/messages/t/{self.sid}"

# ========== استخراج البيانات ==========
def extract_client_data(text, client):
    updated = False
    # الاسم
    if not client.name:
        m = re.search(r'(?:اسمي|الاسم|my name is)[:\s]*([\w\s]{2,30})', text, re.I)
        if m:
            client.name = m.group(1).strip()
            add_log(f"الاسم: {client.name}")
            updated = True
    # الخدمة
    if not client.service:
        services = {
            'شعار|logo': 'تصميم شعار',
            'موقع|website': 'تصميم موقع',
            'متجر|ecommerce': 'متجر إلكتروني',
            'تطبيق|app': 'تطبيق جوال',
            'بوت|bot': 'بوت ذكاء اصطناعي',
            'تصميم|design': 'تصميم جرافيك'
        }
        for kw, svc in services.items():
            if re.search(kw, text, re.I):
                client.service = svc
                add_log(f"الخدمة: {svc}")
                updated = True
                break
    # الميزانية
    if client.budget == 0:
        m = re.search(r'(\d+)[\s-]*(?:usdt|\$|دولار)', text, re.I)
        if m:
            client.budget = int(m.group(1))
            add_log(f"الميزانية: {client.budget}$")
            updated = True
    # رقم الجوال
    if not client.phone:
        m = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9})', text)
        if m:
            client.phone = m.group(1)
            add_log(f"الجوال: {client.phone}")
            updated = True
    return updated

# ========== ردود المدير (بيانات حقيقية فقط) ==========
def owner_reply(sid, text):
    t = text.strip().lower()
    
    # إحصائيات عامة
    if any(k in t for k in ['احصائيات', 'stats', 'احصاء']):
        msg = f"""📊 إحصائيات:
• العملاء الفريدون: {get_unique_clients()}
• إجمالي الطلبات: {len(orders)}
• طلبات اليوم: {len(get_today_orders())}
• المحظورون: {len(blocked_users)}
• الرسائل المستلمة: {stats['msgs_received']}"""
        send_fb(sid, msg)
        return True
    
    # طلبات اليوم
    if any(k in t for k in ['طلبات اليوم', 'اليوم']):
        today = get_today_orders()
        if not today:
            send_fb(sid, "لا توجد طلبات اليوم.")
        else:
            msg = f"طلبات اليوم ({len(today)}):\n"
            for o in today[-10:]:
                msg += f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$\n"
            send_fb(sid, msg)
        return True
    
    # كل الطلبات
    if any(k in t for k in ['كل الطلبات', 'جميع الطلبات']):
        if not orders:
            send_fb(sid, "لا توجد طلبات.")
        else:
            msg = f"آخر 10 طلبات من أصل {len(orders)}:\n"
            for o in orders[-10:]:
                msg += f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$\n"
            send_fb(sid, msg)
        return True
    
    # تفاصيل طلب
    if 'تفاصيل' in t:
        nums = [int(p) for p in t.split() if p.isdigit()]
        if nums:
            o = next((o for o in orders if o['id'] == nums[0]), None)
            if o:
                msg = f"""📋 الطلب #{o['id']}
الاسم: {o['name']}
الخدمة: {o['service']}
الميزانية: {o['budget']}$
الجوال: {o.get('phone', 'غير متوفر')}
التاريخ: {o['timestamp'][:10]}
{o['link']}"""
                send_fb(sid, msg)
            else:
                send_fb(sid, f"الطلب {nums[0]} غير موجود.")
        return True
    
    # عرض أسماء العملاء
    if any(k in t for k in ['اعرض العملاء', 'اسمائهم']):
        if not orders:
            send_fb(sid, "لا يوجد عملاء مسجلون.")
        else:
            names = list(set(o['name'] for o in orders))
            msg = f"العملاء المسجلون ({len(names)}):\n" + "\n".join([f"• {n}" for n in names[-15:]])
            send_fb(sid, msg)
        return True
    
    # المحظورون
    if any(k in t for k in ['المحظورين', 'blocked']):
        if not blocked_users:
            send_fb(sid, "لا يوجد محظورون.")
        else:
            bl = "\n".join([f"• {uid[:15]}..." for uid in list(blocked_users)[:10]])
            send_fb(sid, f"المحظورون ({len(blocked_users)}):\n{bl}")
        return True
    
    # حظر مستخدم
    if t.startswith('حظر ') or t.startswith('block '):
        parts = t.split()
        if len(parts) >= 2 and parts[1].isdigit():
            blocked_users.add(parts[1])
            save_json(BLOCKED_FILE, list(blocked_users))
            send_fb(sid, f"تم حظر {parts[1][:10]}...")
        return True
    
    # إلغاء حظر
    if t.startswith('الغاء حظر ') or t.startswith('unblock '):
        parts = t.split()
        if len(parts) >= 2 and parts[1] in blocked_users:
            blocked_users.remove(parts[1])
            save_json(BLOCKED_FILE, list(blocked_users))
            send_fb(sid, f"تم إلغاء حظر {parts[1][:10]}...")
        return True
    
    # عدد الرسائل
    if 'كم رسالة' in t:
        send_fb(sid, f"إجمالي الرسائل المستلمة: {stats['msgs_received']}, المرسلة: {stats['msgs_sent']}")
        return True
    
    # عدد العملاء
    if 'كم عميل' in t:
        send_fb(sid, f"عدد العملاء الفريدين: {get_unique_clients()}")
        return True
    
    # أي شيء آخر
    send_fb(sid, "أهلاً بك يا مدير. الأوامر المتاحة: إحصائيات، طلبات اليوم، كل الطلبات، تفاصيل [رقم]، اعرض العملاء، المحظورون.")
    return True

# ========== المعالجة الرئيسية ==========
def process_message(sid, text):
    stats['msgs_received'] += 1
    add_log(f"من {sid[:10]}...: {text[:40]}")

    # حظر
    if sid in blocked_users:
        return

    # جلسة جديدة
    if sid not in sessions:
        sessions[sid] = Client(sid)
    client = sessions[sid]
    client.conversation.append(f"المستخدم: {text}")

    # مدير
    if is_owner(sid):
        owner_reply(sid, text)
        client.conversation.append("رد للمدير")
        return

    # كلمة المرور
    if client.awaiting_pw:
        if text.strip() == OWNER_PASSWORD:
            verified_users.add(sid)
            save_json(VERIFIED_FILE, list(verified_users))
            client.awaiting_pw = False
            send_fb(sid, "أهلاً بك.")
            add_log(f"مدير جديد: {sid[:10]}...")
        else:
            send_fb(sid, "كلمة المرور غير صحيحة.")
        return

    # كشف محاولة مدير
    if any(k in text.lower() for k in ['مدير', 'owner', 'المالك']):
        client.awaiting_pw = True
        send_fb(sid, "الرجاء إدخال الرقم السري:")
        return

    # استخراج البيانات
    extract_client_data(text, client)

    # إذا اكتملت البيانات
    if client.is_complete() and not client.confirmed:
        client.confirmed = True
        order = save_order(client)
        deposit = int(client.budget * 0.3)
        pay_msg = f"""تم تأكيد طلبك {client.name}.

الخدمة: {client.service}
المبلغ: {client.budget}$ (المقدم {deposit}$)

للدفع عبر USDT (Binance):
المعرف: {BINANCE_ID}

بعد الدفع نبدأ التنفيذ.
للاستفسار: {COMPANY_WEBSITE}"""
        send_fb(sid, pay_msg)
        notify_owner(order)
        return

    # رد عادي للعميل عبر الذكاء الاصطناعي (مختصر)
    try:
        prompt = f"أنت مساعد مبيعات في B.Y PRO. كن مختصراً. الخدمات: مواقع(300-800$)، متاجر(700-1800$)، بوتات(300$+)، تطبيقات(1500$+). العميل: {text}\nالرد:"
        r = requests.get(f'{AI_API_URL}?text={requests.utils.quote(prompt)}', timeout=8)
        resp = r.json().get('response', 'كيف يمكنني مساعدتك؟')[:200]
    except:
        resp = "كيف يمكنني مساعدتك؟"
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
    today_ords = len(get_today_orders())
    unique_clients = get_unique_clients()
    html = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head><title>B.Y PRO Agent</title>
    <style>
        body{background:#f0f2f5;font-family:system-ui;padding:20px}
        .container{max-width:1400px;margin:0 auto}
        .header{background:white;border-radius:12px;padding:25px;margin-bottom:20px}
        .stats{display:grid;grid-template-columns:repeat(5,1fr);gap:15px;margin-bottom:20px}
        .card{background:white;padding:20px;border-radius:12px}
        .card .num{font-size:2.2em;font-weight:bold;color:#2563eb}
        .logs{background:white;border-radius:12px;padding:20px;margin-bottom:20px;max-height:200px;overflow-y:auto}
        .orders{background:white;border-radius:12px;padding:20px}
        table{width:100%;border-collapse:collapse}
        th{text-align:right;padding:12px;background:#f8fafc}
        td{padding:12px;border-bottom:1px solid #e2e8f0}
    </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
            <h1>🤖 B.Y PRO Agent</h1>
            <p>⏱ {{ start_time }} | 💰 بينانس: {{ binance_id }}</p>
        </div>
        <div class="stats">
            <div class="card"><h3>العملاء</h3><div class="num">{{ unique_clients }}</div></div>
            <div class="card"><h3>الطلبات</h3><div class="num">{{ orders_count }}</div></div>
            <div class="card"><h3>طلبات اليوم</h3><div class="num">{{ today_orders }}</div></div>
            <div class="card"><h3>المحظورون</h3><div class="num">{{ blocked_count }}</div></div>
            <div class="card"><h3>موثوقون</h3><div class="num">{{ verified_count }}</div></div>
        </div>
        <div class="logs"><h3>📋 آخر الأحداث</h3>{% for log in logs %}<div>[{{ log.time }}] {{ log.msg }}</div>{% endfor %}</div>
        <div class="orders">
            <h3>📦 الطلبات المسجلة ({{ orders_count }})</h3>
            <table><tr><th>#</th><th>الاسم</th><th>الخدمة</th><th>الميزانية</th><th>التاريخ</th></tr>
            {% for o in recent_orders %}
            <tr><td>{{ o.id }}</td><td>{{ o.name }}</td><td>{{ o.service }}</td><td>{{ o.budget }}$</td><td>{{ o.timestamp[:10] }}</td></tr>
            {% endfor %}
            </table>
        </div>
    </div>
    <script>setTimeout(()=>location.reload(),5000);</script>
    </body>
    </html>
    """
    return render_template_string(html,
        unique_clients=unique_clients,
        orders_count=len(orders),
        today_orders=today_ords,
        blocked_count=len(blocked_users),
        verified_count=len(verified_users),
        start_time=stats['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        logs=list(logs)[:20],
        recent_orders=orders[-15:] if orders else []
    )

def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get("https://by-pro-marketing-agent.onrender.com", timeout=3)
        except:
            pass

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 B.Y PRO Agent - النسخة المبسطة")
    print("="*60)
    print(f"👤 Owner: {OWNER_FB_ID}")
    print(f"🔑 Password: {OWNER_PASSWORD}")
    print(f"📦 Orders: {len(orders)}")
    print("="*60 + "\n")
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
