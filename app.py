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
OWNER_FB_ID = '2592319994'
OWNER_PASSWORD = "20070909"
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"
BINANCE_ID = "1074084246"
COMPANY_WEBSITE = "https://b.y-pro.kesug.com"

# ========== البرومبت المحترف ==========
SYSTEM_PROMPT = """أنت مساعد مبيعات رسمي لشركة B.Y PRO للتكنولوجيا والبرمجيات.

هويتك المهنية:
- وكيل مبيعات بشري محترف، هادئ، واثق، ومختصر جداً.
- تتحدث باللغة التي يخاطبك بها المستخدم (عربية فصحى، إنجليزية).
- لا تستخدم الرموز التعبيرية أبداً.
- لا تكرر الجمل الترحيبية المملة.

قواعد صارمة:
1. لا تختلق معلومات أبداً.
2. اجمع البيانات بهدوء: الاسم، الخدمة المطلوبة، الميزانية التقريبية، رقم الجوال (اختياري).
3. للتعريف بالشركة، يمكنك ذكر الموقع الرسمي.

الخدمات والأسعار:
- مواقع تعريفية: 300-800$ (5-10 أيام)
- متاجر إلكترونية: 700-1800$ (15-25 يوماً)
- بوتات ذكاء اصطناعي: من 300$ (7-14 يوماً)
- تطبيقات موبايل: من 1500$ (30-60 يوماً)
- تصميم جرافيك: 50-200$ (24-72 ساعة)

التعامل المالي:
- 30% عربون، 70% عند التسليم.
- الدفع عبر USDT (Binance Pay) فقط.
- معرف بينانس: 1074084246

مهمتك: تحويل الاستفسار إلى مشروع قائم."""

# ========== تخزين البيانات ==========
logs = deque(maxlen=100)
stats = {'msgs_received': 0, 'msgs_sent': 0, 'start_time': datetime.now().isoformat()}

ORDERS_FILE = "orders.json"
BLOCKED_FILE = "blocked_users.json"
VERIFIED_FILE = "verified_users.json"

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
        self.lang = 'ar'

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
    # التأكد من عدم وجود طلب مكرر (نفس المحادثة)
    for o in orders:
        if o.get('sid') == client.sid and o.get('status') == 'جديد':
            if (datetime.now() - datetime.fromisoformat(o['timestamp'])).seconds < 3600:
                return o  # طلب حديث موجود
    
    order = {
        'id': len(orders) + 1,
        'name': client.name,
        'service': client.service,
        'budget': client.budget,
        'phone': client.phone,
        'timestamp': datetime.now().isoformat(),
        'sid': client.sid,
        'link': client.get_link(),
        'status': 'جديد',
        'conversation': client.conversation[-5:]
    }
    orders.append(order)
    save_json(ORDERS_FILE, orders)
    add_log(f"✅ طلب #{order['id']} - {client.name}")
    return order

def get_orders_today():
    today = datetime.now().strftime('%Y-%m-%d')
    return [o for o in orders if o['timestamp'].startswith(today)]

def notify_owner(order):
    msg = f"""🔔 طلب جديد #{order['id']}
الاسم: {order['name']}
الخدمة: {order['service']}
الميزانية: {order['budget']}$
{order['link']}"""
    send_fb(OWNER_FB_ID, msg)

# ========== تنفيذ أوامر المدير ==========
def exec_owner_cmd(text, sid):
    t = text.strip().lower()
    parts = t.split()

    # إحصائيات
    if any(k in t for k in ['احصائيات', 'احصاء', 'stats']):
        today_ords = len(get_orders_today())
        msg = f"""📊 إحصائيات:
• العملاء الحاليون: {len(sessions)}
• إجمالي الطلبات: {len(orders)}
• طلبات اليوم: {today_ords}
• المحظورون: {len(blocked_users)}"""
        send_fb(sid, msg)
        return True

    # طلبات اليوم
    if any(k in t for k in ['طلبات اليوم', 'اليوم']):
        today_ords = get_orders_today()
        if not today_ords:
            send_fb(sid, "لا توجد طلبات اليوم.")
        else:
            msg = f"طلبات اليوم ({len(today_ords)}):\n"
            for o in today_ords[-10:]:
                msg += f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$\n"
            send_fb(sid, msg)
        return True

    # كل الطلبات
    if any(k in t for k in ['كل الطلبات', 'جميع الطلبات']):
        if not orders:
            send_fb(sid, "لا توجد طلبات مسجلة.")
        else:
            msg = f"آخر 10 طلبات من أصل {len(orders)}:\n"
            for o in orders[-10:]:
                msg += f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$\n"
            send_fb(sid, msg)
        return True

    # تفاصيل طلب
    if any(k in t for k in ['تفاصيل', 'order']):
        nums = [int(p) for p in parts if p.isdigit()]
        if nums:
            o = next((o for o in orders if o['id'] == nums[0]), None)
            if o:
                msg = f"""📋 الطلب #{o['id']}
الاسم: {o['name']}
الخدمة: {o['service']}
الميزانية: {o['budget']}$
رقم الجوال: {o.get('phone', 'غير متوفر')}
الحالة: {o['status']}
التاريخ: {o['timestamp'][:10]}
{order['link']}"""
                send_fb(sid, msg)
            else:
                send_fb(sid, f"الطلب {nums[0]} غير موجود.")
        return True

    # حظر
    if t.startswith('حظر ') or t.startswith('block '):
        if len(parts) >= 2 and parts[1].isdigit():
            blocked_users.add(parts[1])
            save_json(BLOCKED_FILE, list(blocked_users))
            send_fb(sid, f"تم حظر {parts[1][:10]}...")
            add_log(f"🔨 حظر {parts[1][:10]}...")
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

    return False

# ========== استخراج بيانات العميل ==========
def extract_data(text, client):
    changed = False
    
    # الاسم
    if not client.name:
        patterns = [
            r'(?:اسمي|الاسم|my name is)[:\s]*([\w\s]{2,30})',
            r'انا\s+([\w\s]{2,20})',
            r'i am\s+([a-zA-Z\s]{2,20})'
        ]
        for p in patterns:
            m = re.search(p, text, re.I)
            if m:
                client.name = m.group(1).strip()
                add_log(f"📝 الاسم: {client.name}")
                changed = True
                break
    
    # الخدمة
    if not client.service:
        services = {
            'شعار|logo|لوجو': 'تصميم شعار',
            'موقع|website|web': 'تصميم موقع',
            'متجر|ecommerce|store': 'متجر إلكتروني',
            'تطبيق|app|mobile': 'تطبيق جوال',
            'بوت|bot|chatbot': 'بوت ذكاء اصطناعي',
            'تصميم|design|graphic': 'تصميم جرافيك'
        }
        for kw, svc in services.items():
            if re.search(kw, text, re.I):
                client.service = svc
                add_log(f"🛠 الخدمة: {svc}")
                changed = True
                break
    
    # الميزانية
    if client.budget == 0:
        m = re.search(r'(\d+)[\s-]*(?:usdt|\$|دولار)', text, re.I)
        if m:
            client.budget = int(m.group(1))
            add_log(f"💰 الميزانية: {client.budget}$")
            changed = True
    
    # رقم الجوال
    if not client.phone:
        m = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9}|00966[0-9]{9})', text)
        if m:
            client.phone = m.group(1)
            add_log(f"📱 الجوال: {client.phone}")
            changed = True
    
    return changed

# ========== الذكاء الاصطناعي ==========
def get_ai_response(msg, client, owner_mode=False):
    try:
        prompt = SYSTEM_PROMPT
        if owner_mode:
            prompt += "\n\n(المستخدم هو المدير، كن مباشراً جداً.)"
        
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
    add_log(f"📨 من {sid[:10]}...: {text[:40]}")

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
        if exec_owner_cmd(text, sid):
            client.conversation.append("النظام: أمر منفذ")
            return
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
            add_log(f"🔐 مدير جديد: {sid[:10]}...")
        else:
            send_fb(sid, "كلمة المرور غير صحيحة.")
        return

    # كشف محاولة مدير
    if any(k in text.lower() for k in ['مدير', 'owner', 'المالك', 'ياسين']):
        client.awaiting_pw = True
        send_fb(sid, "الرجاء إدخال الرقم السري:")
        return

    # استخراج البيانات
    extract_data(text, client)

    # التحقق من اكتمال البيانات
    if client.is_complete() and not client.confirmed:
        # تأكيد الطلب وحفظه
        client.confirmed = True
        order = save_new_order(client)
        
        # رسالة الدفع
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
        return

    # رد عادي
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
    today = datetime.now().strftime('%Y-%m-%d')
    today_orders = len([o for o in orders if o['timestamp'].startswith(today)])
    
    html = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <title>B.Y PRO Agent</title>
        <meta charset="UTF-8">
        <style>
            body { background: #f0f2f5; font-family: system-ui; padding: 20px; margin: 0; }
            .container { max-width: 1400px; margin: 0 auto; }
            .header { background: white; border-radius: 12px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { margin: 0; color: #1e293b; }
            .stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-bottom: 20px; }
            .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
            .card h3 { margin: 0 0 10px; color: #64748b; font-size: 0.9em; }
            .card .num { font-size: 2.2em; font-weight: bold; color: #2563eb; }
            .logs { background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px; max-height: 250px; overflow-y: auto; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
            .log-item { padding: 5px; border-bottom: 1px solid #e2e8f0; font-family: monospace; }
            .orders { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
            table { width: 100%; border-collapse: collapse; }
            th { text-align: right; padding: 12px; background: #f8fafc; color: #475569; }
            td { padding: 12px; border-bottom: 1px solid #e2e8f0; }
            .badge { background: #2563eb; color: white; padding: 3px 10px; border-radius: 15px; font-size: 0.8em; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 B.Y PRO Agent</h1>
                <p>⏱ {{ start_time }} | 💰 بينانس: <code style="background:#f1f5f9;padding:3px 8px;border-radius:5px;">{{ binance_id }}</code></p>
            </div>
            
            <div class="stats">
                <div class="card"><h3>العملاء</h3><div class="num">{{ total_clients }}</div></div>
                <div class="card"><h3>الطلبات</h3><div class="num">{{ orders_count }}</div></div>
                <div class="card"><h3>طلبات اليوم</h3><div class="num">{{ today_orders }}</div></div>
                <div class="card"><h3>المحظورون</h3><div class="num">{{ blocked_count }}</div></div>
                <div class="card"><h3>موثوقون</h3><div class="num">{{ verified_count }}</div></div>
            </div>
            
            <div class="logs">
                <h3>📋 آخر الأحداث</h3>
                {% for log in logs %}
                <div class="log-item">[{{ log.time }}] {{ log.msg }}</div>
                {% endfor %}
            </div>
            
            <div class="orders">
                <h3>📦 الطلبات المسجلة ({{ orders_count }})</h3>
                <table>
                    <tr><th>#</th><th>الاسم</th><th>الخدمة</th><th>الميزانية</th><th>التاريخ</th></tr>
                    {% for o in recent_orders %}
                    <tr>
                        <td><span class="badge">{{ o.id }}</span></td>
                        <td>{{ o.name }}</td>
                        <td>{{ o.service }}</td>
                        <td>{{ o.budget }}$</td>
                        <td>{{ o.timestamp[:10] }}</td>
                    </tr>
                    {% endfor %}
                </table>
                {% if not recent_orders %}
                <p style="text-align:center;color:#94a3b8;">لا توجد طلبات مسجلة</p>
                {% endif %}
            </div>
        </div>
        <script>setTimeout(()=>location.reload(), 5000);</script>
    </body>
    </html>
    """
    
    return render_template_string(html,
        total_clients=len(sessions),
        orders_count=len(orders),
        today_orders=today_orders,
        blocked_count=len(blocked_users),
        verified_count=len(verified_users),
        start_time=stats['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        logs=list(logs)[:20],
        recent_orders=orders[-15:] if orders else []
    )

# ========== Keep alive ==========
def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get("https://by-pro-marketing-agent.onrender.com", timeout=3)
            add_log("💓 Ping")
        except:
            pass

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 B.Y PRO Agent - Version 6 (التخزين الفوري)")
    print("="*60)
    print(f"👤 Owner ID: {OWNER_FB_ID}")
    print(f"🔑 Password: {OWNER_PASSWORD}")
    print(f"💰 Binance: {BINANCE_ID}")
    print(f"📦 Orders in DB: {len(orders)}")
    print("="*60 + "\n")
    
    threading.Thread(target=keep_alive, daemon=True).start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
