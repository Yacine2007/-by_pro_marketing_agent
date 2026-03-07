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

# ========== المتغيرات البيئية ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '2592319994')
OWNER_PASSWORD = os.environ.get('OWNER_PASSWORD', '20070909')
BIN_ID = os.environ.get('BIN_ID')
X_MASTER_KEY = os.environ.get('X_MASTER_KEY')
X_ACCESS_KEY = os.environ.get('X_ACCESS_KEY')
BINANCE_ID = os.environ.get('BINANCE_ID', '1074084246')
AI_API_URL = os.environ.get('AI_API_URL', 'http://fi8.bot-hosting.net:20163/elos-gemina')
COMPANY_WEBSITE = os.environ.get('COMPANY_WEBSITE', 'https://b.y-pro.kesug.com')

# ========== البرومبت المعدل مع آلية تأكيد الطلب ==========
BOT_PERSONALITY = """أنت مستشار تقني ومبيعات في B.Y PRO للتكنولوجيا والبرمجيات.

شخصيتك:
- خبير تقني متمرس، تفهم احتياجات العملاء التقنية بسرعة.
- ودود، مرن، ومختصر. لا تكرر نفسك.
- تهدف لكسب العميل وتنفيذ طلبه بأفضل شكل.

خدمات الشركة:
- تطوير مواقع الويب (تعريفي، متاجر، تطبيقات ويب)
- تطوير تطبيقات الموبايل (iOS, Android)
- أنظمة الأتمتة وبوتات الذكاء الاصطناعي
- التصميم الجرافيكي والهوية البصرية
- الاستشارات التقنية وحلول البرمجيات المخصصة

سياسة الدفع:
- 30% دفعة أولى، 70% عند التسليم النهائي.
- وسيلة الدفع: USDT (Binance Pay) – معرف بينانس: 1074084246.

مبادئ التواصل:
1. أجب بدقة واختصار.
2. تكيف مع لغة المستخدم.
3. اجمع البيانات التالية: الاسم الكامل، الخدمة المطلوبة، الميزانية، رقم الهاتف، المدة المتوقعة، تفاصيل المشروع.

آلية تأكيد الطلب:
- عندما تتأكد أن البيانات الأساسية (الاسم، الخدمة، الميزانية) متوفرة، اكتب في بداية ردك: `[ORDER_READY]`
- النظام سيتعرف على هذه العبارة ويحفظ الطلب تلقائياً."""

# ========== تخزين JSONBin.io ==========
def jsonbin_read():
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {
        'X-Master-Key': X_MASTER_KEY,
        'X-Access-Key': X_ACCESS_KEY
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            record = resp.json().get('record', {})
            return record if isinstance(record, dict) else {}
    except:
        return {}
    return {}

def jsonbin_write(data):
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': X_MASTER_KEY,
        'X-Access-Key': X_ACCESS_KEY
    }
    try:
        resp = requests.put(url, json=data, headers=headers, timeout=10)
        return resp.status_code == 200
    except:
        return False

# ========== هيكل البيانات الأساسي ==========
DEFAULT_DATA = {
    'orders': [],
    'blocked': [],
    'verified': [],
    'sessions': {},
    'order_notes': {},
    'stats': {
        'msgs_received': 0,
        'msgs_sent': 0,
        'start_time': datetime.now().isoformat()
    }
}

loaded_data = jsonbin_read()
data = DEFAULT_DATA.copy()
if loaded_data:
    for key in data:
        if key in loaded_data:
            data[key] = loaded_data[key]

# ========== سجل الأحداث المحلي ==========
logs = deque(maxlen=100)

def add_log(msg):
    logs.appendleft({'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg})
    print(f"[{logs[0]['time']}] {msg}")

# ========== دوال فيسبوك ==========
def send_fb(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("❌ PAGE_ACCESS_TOKEN غير موجود")
        return False
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            data['stats']['msgs_sent'] += 1
            save_data()
            add_log(f"📤 إلى {recipient_id[:10]}...: {text[:40]}")
            return True
    except:
        pass
    return False

# ========== حفظ البيانات ==========
def save_data():
    success = jsonbin_write(data)
    if success:
        add_log("💾 تم حفظ البيانات في JSONBin")
    return success

# ========== التحقق من المدير ==========
def is_owner(sender_id):
    sender_str = str(s_id)
    if sender_str == str(OWNER_FB_ID):
        return True
    return sender_str in [str(v) for v in data.get('verified', [])]

# ========== دوال الطلبات ==========
def get_live_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    orders_list = data.get('orders', [])
    today_orders = [o for o in orders_list if o.get('timestamp', '').startswith(today)]
    unique_clients = len(set(o.get('sender_id', '') for o in orders_list))
    return {
        'unique_clients': unique_clients,
        'total_orders': len(orders_list),
        'today_orders': len(today_orders),
        'today_orders_list': today_orders[-10:],
        'blocked': len(data.get('blocked', [])),
        'verified': len(data.get('verified', [])),
        'msgs_received': data['stats']['msgs_received'],
        'msgs_sent': data['stats']['msgs_sent']
    }

def add_order(order_dict):
    order_dict['id'] = len(data.get('orders', [])) + 1
    if 'orders' not in data:
        data['orders'] = []
    data['orders'].append(order_dict)
    save_data()
    add_log(f"✅ طلب جديد #{order_dict['id']} - {order_dict['name']} - {order_dict['budget']}$")
    
    # إشعار المدير
    stats = get_live_stats()
    msg = f"""🔔 طلب جديد #{order_dict['id']}
الاسم: {order_dict['name']}
الخدمة: {order_dict['service']}
الميزانية: {order_dict['budget']}$
رقم: {order_dict.get('phone', 'غير متوفر')}
المدة: {order_dict.get('duration', 'غير محددة')}
{order_dict['link']}"""
    send_fb(OWNER_FB_ID, msg)
    return order_dict['id']

# ========== إدارة الجلسات ==========
def get_session(sender_id):
    if 'sessions' not in data:
        data['sessions'] = {}
    if sender_id not in data['sessions']:
        data['sessions'][sender_id] = {
            'name': '',
            'service': '',
            'budget': 0,
            'budget_min': 0,
            'budget_max': 0,
            'phone': '',
            'duration': '',
            'details': '',
            'conversation': [],
            'awaiting_password': False,
            'asked_for_phone': False
        }
    return data['sessions'][sender_id]

def update_session(sender_id, updates):
    if 'sessions' in data and sender_id in data['sessions']:
        data['sessions'][sender_id].update(updates)
        save_data()

def add_to_conversation(sender_id, role, message):
    sess = get_session(sender_id)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 15:
        sess['conversation'] = sess['conversation'][-15:]
    save_data()

# ========== استخراج البيانات ==========
def extract_client_data(text, sess):
    updated = False
    text_lower = text.lower()
    
    # الاسم
    if not sess['name']:
        patterns = [
            r'اسمي[:\s]*([\u0600-\u06FF\s]{3,30})',
            r'الاسم[:\s]*([\u0600-\u06FF\s]{3,30})',
            r'my name is[:\s]*([a-zA-Z\s]{3,30})',
            r'i am[:\s]*([a-zA-Z\s]{3,30})'
        ]
        for p in patterns:
            m = re.search(p, text, re.I)
            if m:
                sess['name'] = m.group(1).strip()
                add_log(f"📝 الاسم: {sess['name']}")
                updated = True
                break
    
    # الخدمة
    if not sess['service']:
        services = [
            (r'شعار|logo|لوجو', 'تصميم شعار'),
            (r'موقع|website|web', 'تطوير موقع'),
            (r'متجر|ecommerce|store', 'متجر إلكتروني'),
            (r'تطبيق|app|mobile', 'تطبيق جوال'),
            (r'بوت|bot|chatbot', 'بوت ذكاء اصطناعي'),
            (r'بورتفوليو|portfolio', 'بورتفوليو شخصي'),
            (r'تصميم|design', 'تصميم جرافيكي')
        ]
        for pattern, service in services:
            if re.search(pattern, text_lower):
                sess['service'] = service
                add_log(f"🛠 الخدمة: {service}")
                updated = True
                break
    
    # الميزانية (رقم واحد أو نطاق)
    if sess['budget'] == 0:
        # نطاق مثل 300-500
        range_match = re.search(r'(\d+)[\s-]*[\-\–][\s-]*(\d+)', text)
        if range_match:
            sess['budget_min'] = int(range_match.group(1))
            sess['budget_max'] = int(range_match.group(2))
            sess['budget'] = sess['budget_min']  # نأخذ القيمة الدنيا للحسابات
            add_log(f"💰 الميزانية: {sess['budget_min']}-{sess['budget_max']}$")
            updated = True
        else:
            # رقم واحد مع عملة
            m = re.search(r'(\d+)[\s-]*(?:usdt|\$|دولار)', text, re.I)
            if m:
                sess['budget'] = int(m.group(1))
                sess['budget_min'] = sess['budget']
                sess['budget_max'] = sess['budget']
                add_log(f"💰 الميزانية: {sess['budget']}$")
                updated = True
    
    # رقم الجوال
    if not sess['phone']:
        m = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9})', text)
        if m:
            sess['phone'] = m.group(1)
            add_log(f"📱 الجوال: {sess['phone']}")
            updated = True
    
    # المدة
    if not sess['duration']:
        m = re.search(r'(\d+)[\s-]*(يوم|شهر|أسبوع|week|month|day)', text, re.I)
        if m:
            sess['duration'] = m.group(0)
            add_log(f"⏱ المدة: {sess['duration']}")
            updated = True
    
    return updated

# ========== الذكاء الاصطناعي ==========
def ask_ai(user_msg, sess, is_owner_mode=False, live_stats=None):
    context = "\n".join(sess.get('conversation', [])[-10:])
    system = BOT_PERSONALITY
    
    if is_owner_mode and live_stats:
        system += f"\n\nالإحصائيات: عملاء {live_stats['unique_clients']}، طلبات {live_stats['total_orders']}، اليوم {live_stats['today_orders']}"
    
    prompt = f"{system}\n\n{context}\n\nالمستخدم: {user_msg}\nالرد:"
    try:
        r = requests.get(f'{AI_API_URL}?text={requests.utils.quote(prompt)}', timeout=10)
        return r.json().get('response', '')[:1800] if r.status_code == 200 else "عذراً، حدث خطأ."
    except:
        return "عذراً، حدث خطأ تقني."

# ========== معالجة كلمة المرور ==========
def handle_password(s_id, text, sess):
    if text.strip() == OWNER_PASSWORD:
        if str(s_id) not in [str(v) for v in data.get('verified', [])]:
            data.setdefault('verified', []).append(str(s_id))
            save_data()
        sess['awaiting_password'] = False
        update_session(s_id, {'awaiting_password': False})
        send_fb(s_id, "أهلاً بك يا مدير.")
    else:
        send_fb(s_id, "❌ كلمة المرور غير صحيحة.")

# ========== المعالجة الرئيسية ==========
def process_message(s_id, text):
    data['stats']['msgs_received'] += 1
    save_data()
    add_log(f"📨 من {str(s_id)[:10]}...: {text[:40]}")

    if s_id in data.get('blocked', []):
        return

    sess = get_session(s_id)
    add_to_conversation(s_id, 'المستخدم', text)

    # المدير
    if is_owner(s_id):
        stats = get_live_stats()
        if any(k in text.lower() for k in ['اي جديد', 'what\'s new']):
            if stats['today_orders'] > 0:
                msg = f"طلبات اليوم ({stats['today_orders']}):\n"
                for o in stats['today_orders_list']:
                    msg += f"#{o['id']} {o['name']} - {o['budget']}$\n"
                send_fb(s_id, msg)
            else:
                send_fb(s_id, "لا توجد طلبات جديدة اليوم.")
            return
        reply = ask_ai(text, sess, is_owner_mode=True, live_stats=stats)
        send_fb(s_id, reply)
        add_to_conversation(s_id, 'النظام', reply)
        return

    # كلمة المرور
    if sess.get('awaiting_password'):
        handle_password(s_id, text, sess)
        return

    # محاولة دخول كمدير
    if any(k in text.lower() for k in ['مدير', 'owner', 'المالك']):
        sess['awaiting_password'] = True
        update_session(s_id, {'awaiting_password': True})
        send_fb(s_id, "🔐 الرجاء إدخال الرقم السري:")
        return

    # استخراج البيانات
    extract_client_data(text, sess)
    update_session(s_id, sess)

    # رد الذكاء
    reply = ask_ai(text, sess)
    
    # التحقق من ORDER_READY
    if '[ORDER_READY]' in reply:
        clean_reply = reply.replace('[ORDER_READY]', '').strip()
        
        # التحقق من اكتمال البيانات
        data_complete = False
        if sess['name'] and sess['service']:
            if sess['budget'] > 0 or (sess['budget_min'] > 0 and sess['budget_max'] > 0):
                data_complete = True
        
        if data_complete:
            # طلب رقم الجوال إذا لم يقدمه
            if not sess['phone'] and not sess.get('asked_for_phone'):
                send_fb(s_id, "شكراً لك. هل يمكن تزويدي برقم جوالك للتواصل؟ (اختياري)")
                sess['asked_for_phone'] = True
                update_session(s_id, {'asked_for_phone': True})
                send_fb(s_id, clean_reply)
                add_to_conversation(s_id, 'النظام', clean_reply)
                return
            
            # حفظ الطلب
            budget_display = f"{sess['budget']}$"
            if sess['budget_min'] != sess['budget_max']:
                budget_display = f"{sess['budget_min']}-{sess['budget_max']}$"
            
            order = {
                'name': sess['name'],
                'service': sess['service'],
                'budget': budget_display,
                'budget_value': sess['budget'],  # للحسابات
                'phone': sess.get('phone', ''),
                'duration': sess.get('duration', ''),
                'details': sess.get('details', '') or text[:200],
                'timestamp': datetime.now().isoformat(),
                'sender_id': s_id,
                'link': f"https://www.facebook.com/messages/t/{s_id}",
                'status': 'جديد'
            }
            order_id = add_order(order)
            add_log(f"✅ تم حفظ الطلب #{order_id}")
            
            # إعادة تعيين بيانات الطلب الجديد
            update_session(s_id, {
                'service': '',
                'budget': 0,
                'budget_min': 0,
                'budget_max': 0,
                'duration': '',
                'details': '',
                'asked_for_phone': False
            })
            
            send_fb(s_id, clean_reply)
            add_to_conversation(s_id, 'النظام', clean_reply)
        else:
            send_fb(s_id, clean_reply)
            add_to_conversation(s_id, 'النظام', clean_reply)
    else:
        send_fb(s_id, reply)
        add_to_conversation(s_id, 'النظام', reply)

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
                    s = msg['sender']['id']
                    t = msg['message']['text']
                    if 'تسجيل الخروج كمدير' in t and is_owner(s):
                        update_session(s, {'awaiting_password': False})
                        send_fb(s, "تم تسجيل الخروج.")
                    else:
                        threading.Thread(target=process_message, args=(s, t)).start()
    return 'OK', 200

@app.route('/')
def home():
    stats = get_live_stats()
    orders_list = sorted(data.get('orders', []), key=lambda x: x.get('id', 0), reverse=True)[:50]
    
    html = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>B.Y PRO - لوحة التحكم</title>
        <style>
            *{font-family:system-ui;box-sizing:border-box}
            body{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);margin:0;padding:20px}
            .container{max-width:1400px;margin:0 auto}
            .header{background:white;border-radius:20px;padding:30px;margin-bottom:20px}
            h1{margin:0;color:#333}
            .badge{background:#4ade80;color:#166534;padding:5px 15px;border-radius:25px;display:inline-block}
            .stats{display:grid;grid-template-columns:repeat(6,1fr);gap:15px;margin:20px 0}
            .card{background:white;border-radius:15px;padding:20px}
            .card .num{font-size:2.2em;font-weight:bold;color:#2563eb}
            .logs{background:white;border-radius:15px;padding:20px;margin-bottom:20px;max-height:200px;overflow-y:auto}
            .orders{background:white;border-radius:15px;padding:20px}
            table{width:100%;border-collapse:collapse}
            th{text-align:right;padding:12px;background:#f8fafc}
            td{padding:12px;border-bottom:1px solid #e2e8f0}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤵 B.Y PRO</h1>
                <div class="badge">✅ يعمل</div>
                <p>⏱ {{ start_time }} | 💰 {{ binance_id }}</p>
            </div>
            <div class="stats">
                <div class="card"><h3>العملاء</h3><div class="num">{{ stats.unique_clients }}</div></div>
                <div class="card"><h3>الطلبات</h3><div class="num">{{ stats.total_orders }}</div></div>
                <div class="card"><h3>طلبات اليوم</h3><div class="num">{{ stats.today_orders }}</div></div>
                <div class="card"><h3>المحظورون</h3><div class="num">{{ stats.blocked }}</div></div>
                <div class="card"><h3>الموثوقون</h3><div class="num">{{ stats.verified }}</div></div>
                <div class="card"><h3>الرسائل</h3><div class="num">{{ stats.msgs_received }}</div></div>
            </div>
            <div class="logs">
                <h3>📋 آخر الأحداث</h3>
                {% for log in logs %}<div>[{{ log.time }}] {{ log.msg }}</div>{% endfor %}
            </div>
            <div class="orders">
                <h3>📦 الطلبات ({{ stats.total_orders }})</h3>
                <table>
                    <tr><th>#</th><th>الاسم</th><th>الخدمة</th><th>الميزانية</th><th>الحالة</th></tr>
                    {% for o in orders %}
                    <tr>
                        <td>#{{ o.id }}</td>
                        <td>{{ o.name }}</td>
                        <td>{{ o.service }}</td>
                        <td>{{ o.budget }}</td>
                        <td>{{ o.status }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>
        <script>setTimeout(()=>location.reload(),10000)</script>
    </body>
    </html>
    """
    
    return render_template_string(html,
        start_time=data['stats']['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        stats=stats,
        logs=list(logs)[:20],
        orders=orders_list
    )

# ========== Keep alive ==========
def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get(f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/", timeout=5)
        except:
            pass

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 B.Y PRO Agent - النسخة النهائية")
    print("="*70)
    print(f"👤 المدير: {OWNER_FB_ID}")
    print(f"🔑 كلمة المرور: {OWNER_PASSWORD}")
    print(f"💰 بينانس: {BINANCE_ID}")
    print(f"📦 الطلبات الحالية: {len(data.get('orders', []))}")
    print("="*70 + "\n")
    
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
