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

# ========== برومبت صارم جداً - بدون ثرثرة ==========
STRICT_PROMPT = """أنت مساعد مبيعات آلي لشركة B.Y PRO. مهمتك الوحيدة: جمع 3 بيانات فقط من العميل (الاسم، الخدمة، الميزانية) ثم إرسال تفاصيل الدفع.

قواعد صارمة:
1. لا تتحدث عن نفسك أبداً.
2. لا تطرح أسئلة شخصية (العمر، العمل، إلخ).
3. لا تعتذر إلا إذا طلب منك ذلك.
4. لا تكرر المعلومات.
5. أجب فقط على سؤال العميل، ثم عد لجمع البيانات.
6. إذا اكتملت البيانات (الاسم، الخدمة، الميزانية)، أرسل رسالة الدفع فوراً.

الخدمات والأسعار:
- مواقع تعريفية: 300-800$
- متاجر إلكترونية: 700-1800$
- بوتات ذكاء اصطناعي: من 300$
- تطبيقات موبايل: من 1500$
- تصميم جرافيك: 50-200$

مثال للحوار المثالي:
العميل: "ابغى موقع"
الرد: "اسمك؟"
العميل: "محمد"
الرد: "الميزانية التقريبية؟"
العميل: "500 دولار"
الرد: [يرسل تفاصيل الدفع فوراً]

لا شيء غير ذلك."""

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
        self.awaiting_pw = False
        self.step = 0  # 0:بداية, 1:طلب اسم, 2:طلب خدمة, 3:طلب ميزانية, 4:مكتمل

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
        'status': 'جديد'
    }
    orders.append(order)
    save_json(ORDERS_FILE, orders)
    add_log(f"✅ طلب #{order['id']} - {client.name}")
    return order

def get_orders_today():
    today = datetime.now().strftime('%Y-%m-%d')
    return [o for o in orders if o['timestamp'].startswith(today)]

def get_client_count():
    return len(set(o['sid'] for o in orders)) if orders else 0

def notify_owner(order):
    msg = f"""🔔 طلب جديد #{order['id']}
الاسم: {order['name']}
الخدمة: {order['service']}
الميزانية: {order['budget']}$
{order['link']}"""
    send_fb(OWNER_FB_ID, msg)

# ========== أوامر المدير ==========
def handle_owner(sid, text):
    t = text.strip().lower()
    
    # إحصائيات سريعة
    if 'احصائيات' in t or 'stats' in t:
        unique = get_client_count()
        today = len(get_orders_today())
        msg = f"""إحصائيات:
عملاء: {unique}
طلبات: {len(orders)}
اليوم: {today}
محظورون: {len(blocked_users)}"""
        send_fb(sid, msg)
        return True
    
    # طلبات اليوم
    if 'اليوم' in t and 'طلب' in t:
        today_ords = get_orders_today()
        if not today_ords:
            send_fb(sid, "لا توجد طلبات اليوم")
        else:
            msg = "\n".join([f"#{o['id']} {o['name']} - {o['service']}" for o in today_ords])
            send_fb(sid, msg)
        return True
    
    # كل الطلبات
    if 'كل الطلبات' in t:
        if not orders:
            send_fb(sid, "لا توجد طلبات")
        else:
            msg = "\n".join([f"#{o['id']} {o['name']} - {o['service']}" for o in orders[-10:]])
            send_fb(sid, msg)
        return True
    
    # تفاصيل طلب
    if 'تفاصيل' in t:
        nums = [int(p) for p in t.split() if p.isdigit()]
        if nums:
            o = next((o for o in orders if o['id'] == nums[0]), None)
            if o:
                send_fb(sid, f"طلب {o['id']}: {o['name']}, {o['service']}, {o['budget']}$, {o.get('phone','')}")
        return True
    
    # حظر
    if t.startswith('حظر '):
        parts = t.split()
        if len(parts) >= 2 and parts[1].isdigit():
            blocked_users.add(parts[1])
            save_json(BLOCKED_FILE, list(blocked_users))
            send_fb(sid, f"تم حظر {parts[1][:10]}")
        return True
    
    # محظورون
    if 'المحظورين' in t:
        if not blocked_users:
            send_fb(sid, "لا يوجد محظورون")
        else:
            send_fb(sid, "\n".join([f"• {uid[:15]}" for uid in list(blocked_users)[:10]]))
        return True
    
    return False

# ========== معالجة العملاء (بدون ذكاء اصطناعي - يدوي) ==========
def handle_client(sid, text, client):
    # إذا في انتظار كلمة المرور
    if client.awaiting_pw:
        if text.strip() == OWNER_PASSWORD:
            verified_users.add(sid)
            save_json(VERIFIED_FILE, list(verified_users))
            client.awaiting_pw = False
            send_fb(sid, "أهلاً بك")
        else:
            send_fb(sid, "كلمة المرور خطأ")
        return

    # كشف محاولة مدير
    if any(k in text.lower() for k in ['مدير', 'owner', 'المالك']):
        client.awaiting_pw = True
        send_fb(sid, "الرقم السري:")
        return

    # استخراج البيانات بشكل مباشر
    data_extracted = False
    
    # استخراج الاسم
    if not client.name:
        name_match = re.search(r'(?:اسمي|الاسم|انا)[:\s]*([\w\s]{2,30})', text, re.I)
        if name_match:
            client.name = name_match.group(1).strip()
            add_log(f"الاسم: {client.name}")
            data_extracted = True
    
    # استخراج الخدمة
    if not client.service:
        if 'موقع' in text or 'website' in text.lower():
            client.service = 'موقع تعريفي'
            data_extracted = True
        elif 'متجر' in text or 'ecommerce' in text.lower():
            client.service = 'متجر إلكتروني'
            data_extracted = True
        elif 'تطبيق' in text or 'app' in text.lower():
            client.service = 'تطبيق جوال'
            data_extracted = True
        elif 'بوت' in text or 'bot' in text.lower():
            client.service = 'بوت ذكاء اصطناعي'
            data_extracted = True
        elif 'شعار' in text or 'logo' in text.lower():
            client.service = 'تصميم شعار'
            data_extracted = True
    
    # استخراج الميزانية
    if client.budget == 0:
        budget_match = re.search(r'(\d+)[\s-]*(?:usdt|\$|دولار)', text, re.I)
        if budget_match:
            client.budget = int(budget_match.group(1))
            add_log(f"الميزانية: {client.budget}$")
            data_extracted = True
    
    # استخراج رقم الجوال
    if not client.phone:
        phone_match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9})', text)
        if phone_match:
            client.phone = phone_match.group(1)
            add_log(f"الجوال: {client.phone}")
            data_extracted = True

    # إذا اكتملت البيانات
    if client.is_complete() and not client.confirmed:
        client.confirmed = True
        order = save_new_order(client)
        
        deposit = int(client.budget * 0.3)
        pay_msg = f"""تم تأكيد طلبك {client.name}

الخدمة: {client.service}
المبلغ: {client.budget}$ (المقدم {deposit}$)

للدفع عبر USDT (Binance): {BINANCE_ID}

بعد الدفع نبدأ التنفيذ"""
        send_fb(sid, pay_msg)
        notify_owner(order)
        return

    # إذا ما اكتملت البيانات، اسأل عن الناقص
    if not client.name:
        send_fb(sid, "اسمك؟")
    elif not client.service:
        send_fb(sid, "الخدمة المطلوبة؟ (موقع، متجر، تطبيق، بوت، شعار)")
    elif client.budget == 0:
        send_fb(sid, "الميزانية التقريبية؟")
    else:
        # هذا معناه أن البيانات اكتملت ولكن لم يتم التأكيد بعد (لسبب ما)
        # نعيد التأكيد
        client.confirmed = True
        order = save_new_order(client)
        deposit = int(client.budget * 0.3)
        pay_msg = f"""تم تأكيد طلبك {client.name}

الخدمة: {client.service}
المبلغ: {client.budget}$ (المقدم {deposit}$)

للدفع عبر USDT (Binance): {BINANCE_ID}"""
        send_fb(sid, pay_msg)
        notify_owner(order)

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

    # مدير
    if is_owner(sid):
        if not handle_owner(sid, text):
            send_fb(sid, "أهلاً بك. الأوامر: احصائيات، طلبات اليوم، كل الطلبات، تفاصيل [رقم]، حظر [معرف]، المحظورين")
        return

    # عميل
    handle_client(sid, text, client)

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
    unique_clients = get_client_count()
    today_orders = len(get_orders_today())
    
    html = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <title>B.Y PRO Agent</title>
        <style>
            body { background: #f0f2f5; font-family: system-ui; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: white; border-radius: 12px; padding: 25px; margin-bottom: 20px; }
            .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 15px; margin-bottom: 20px; }
            .card { background: white; padding: 20px; border-radius: 12px; }
            .card .num { font-size: 2.2em; font-weight: bold; color: #2563eb; }
            .orders { background: white; border-radius: 12px; padding: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th { text-align: right; padding: 10px; background: #f8fafc; }
            td { padding: 10px; border-bottom: 1px solid #e2e8f0; }
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
            </div>
            
            <div class="orders">
                <h3>📦 الطلبات</h3>
                <table>
                    <tr><th>#</th><th>الاسم</th><th>الخدمة</th><th>الميزانية</th><th>التاريخ</th></tr>
                    {% for o in recent_orders %}
                    <tr>
                        <td>{{ o.id }}</td>
                        <td>{{ o.name }}</td>
                        <td>{{ o.service }}</td>
                        <td>{{ o.budget }}$</td>
                        <td>{{ o.timestamp[:10] }}</td>
                    </tr>
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
        today_orders=today_orders,
        blocked_count=len(blocked_users),
        start_time=stats['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        recent_orders=orders[-15:] if orders else []
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
    print("\n" + "="*60)
    print("🚀 B.Y PRO Agent - نسخة صارمة بدون ثرثرة")
    print("="*60)
    print(f"👤 المدير: {OWNER_FB_ID}")
    print(f"🔑 كلمة السر: {OWNER_PASSWORD}")
    print(f"📦 الطلبات: {len(orders)}")
    print("="*60 + "\n")
    
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
