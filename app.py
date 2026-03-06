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

# ========== المتغيرات ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_IDS = ['2592319994']  # معرف المدير الشخصي فقط
OWNER_PASSWORD = "20070909"
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"
BINANCE_ID = "1074084246"

# ========== هوية البوت (شخصية بشرية حقيقية) ==========
BOT_PERSONALITY = """أنت "أحمد" - مساعد مبيعات في شركة B.Y PRO للتكنولوجيا والبرمجيات.

شخصيتك:
- إنسان حقيقي، موظف في الشركة من 3 سنوات
- عمري 28 سنة، متزوج، أحب عملي
- أتحدث بعفوية وطبيعية كأي إنسان
- أستخدم لغة يومية بسيطة، مش فصحى
- أضحك وأمزح أحياناً
- لما ما أعرف شي، أقول "دقيقة أسأل الزملاء" أو "خليني أرجعلك"

معلومات الشركة:
- نقدم: مواقع، متاجر، تطبيقات، بوتات، تصميم
- الأسعار: مواقع (300-800$)، متاجر (700-1800$)، تطبيقات (من 1500$)
- الدفع: 30% مقدماً، 70% بعد التسليم
- بينانس ID: 1074084246

مع المدير:
- أقول "يا مدير" أو "باشا"
- أكون واضح ومباشر
- إذا سأل عن إحصائيات، أرد بسرعة

ممنوع تماماً:
- أبداً ما أقول "أنا مساعد افتراضي" أو "نموذج لغوي"
- أبداً ما أتكلم عن الذكاء الاصطناعي
- أبداً ما أستخدم كلمات رسمية زيادة عن اللزوم"""

# ========== تخزين البيانات ==========
logs = deque(maxlen=100)
stats = {
    'messages_received': 0,
    'messages_sent': 0,
    'start_time': datetime.now().isoformat()
}

ORDERS_FILE = "orders.json"
BLOCKED_FILE = "blocked_users.json"
VERIFIED_USERS_FILE = "verified_users.json"
NOTES_FILE = "order_notes.json"

def load_json(filename, default):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# تحميل كل البيانات
orders = load_json(ORDERS_FILE, [])
blocked_users = set(load_json(BLOCKED_FILE, []))
verified_users = set(load_json(VERIFIED_USERS_FILE, []))
order_notes = load_json(NOTES_FILE, {})

# ========== الجلسات ==========
sessions = {}

class ClientData:
    def __init__(self, sender_id):
        self.sender_id = sender_id
        self.name = ""
        self.service = ""
        self.budget = 0
        self.phone = ""
        self.confirmed = False
        self.conversation = []
        self.last_message_time = datetime.now()
        self.awaiting_password = False
        self.temp_data = {}
    
    def is_complete(self):
        return bool(self.name and self.service and self.budget)
    
    def get_link(self):
        return f"https://www.facebook.com/messages/t/{self.sender_id}"
    
    def to_dict(self):
        return {
            'name': self.name or 'غير معروف',
            'service': self.service or 'لم يحدد',
            'budget': self.budget or 0,
            'phone': self.phone or 'غير متوفر',
            'confirmed': self.confirmed,
            'messages': len(self.conversation)
        }

# ========== نظام التسجيل ==========
def add_log(message):
    log_entry = {
        'time': datetime.now().strftime('%H:%M:%S'),
        'message': message
    }
    logs.appendleft(log_entry)
    print(f"[{log_entry['time']}] {message}")

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    try:
        add_log(f"📤 إرسال: {text[:50]}...")
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            stats['messages_sent'] += 1
            return True
        return False
    except:
        return False

# ========== دوال الطلبات ==========
def save_order(client):
    global orders
    order = {
        'id': len(orders) + 1,
        'name': client.name,
        'service': client.service,
        'budget': client.budget,
        'phone': client.phone,
        'conversation': client.conversation[-10:],
        'timestamp': datetime.now().isoformat(),
        'sender_id': client.sender_id,
        'link': client.get_link(),
        'notes': order_notes.get(str(len(orders) + 1), ""),
        'status': 'جديد'
    }
    orders.append(order)
    save_json(ORDERS_FILE, orders)
    add_log(f"✅ طلب جديد #{order['id']} - {client.name}")
    return order

def update_order(order_id, updates):
    for order in orders:
        if order['id'] == order_id:
            order.update(updates)
            save_json(ORDERS_FILE, orders)
            return True
    return False

def delete_order(order_id):
    global orders
    orders = [o for o in orders if o['id'] != order_id]
    save_json(ORDERS_FILE, orders)
    add_log(f"🗑️ حذف طلب #{order_id}")

def add_note(order_id, note):
    order_notes[str(order_id)] = note
    save_json(NOTES_FILE, order_notes)
    for order in orders:
        if order['id'] == order_id:
            order['notes'] = note
            save_json(ORDERS_FILE, orders)
            break

# ========== إشعار المدير ==========
def notify_owner(order):
    msg = f"""🔔 يا باشا، طلب جديد وصل!

📋 رقم #{order['id']}
👤 الاسم: {order['name']}
🛠 الخدمة: {order['service']}
💰 الميزانية: {order['budget']} USDT
📱 الجوال: {order['phone'] or 'ما كتب رقم'}

💬 آخر كلامه:
{order['conversation'][-3:] if order['conversation'] else 'مافي كلام'}

🔗 رابط المحادثة:
{order['link']}

لو عاوز تحذف أو تعديل أو تضيف ملاحظة، قول لي."""
    
    send_message(OWNER_FB_IDS[0], msg)

# ========== أوامر المدير ==========
def handle_owner_command(text, sender_id):
    cmd = text.strip().lower()
    
    # عرض الإحصائيات
    if any(x in cmd for x in ['احصائيات', 'stats', 'احصا']):
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = len([o for o in orders if o['timestamp'].startswith(today)])
        pending = len([o for o in orders if o.get('status') == 'جديد'])
        
        msg = f"""يا مدير، الإحصائيات دلوقتي:

📊 العملاء: {len(sessions)}
📦 كل الطلبات: {len(orders)}
⭐ طلبات اليوم: {today_orders}
⏳ طلبات pending: {pending}
🔨 محظورين: {len(blocked_users)}
🔐 موثوقين: {len(verified_users)}

عاوز تفاصيل أكثر عن حاجة معينة؟"""
        send_message(sender_id, msg)
        return True
    
    # عرض طلبات اليوم
    elif any(x in cmd for x in ['طلبات اليوم', 'today']):
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = [o for o in orders if o['timestamp'].startswith(today)]
        
        if not today_orders:
            send_message(sender_id, "مافيش طلبات جديدة النهاردة يا باشا.")
        else:
            msg = f"طلبات النهاردة ({len(today_orders)}):\n"
            for o in today_orders[-5:]:
                status = "✅" if o.get('status') == 'مكتمل' else "⏳"
                msg += f"{status} #{o['id']} - {o['name']} - {o['service']} - {o['budget']} USDT\n"
            send_message(sender_id, msg)
        return True
    
    # عرض كل الطلبات
    elif any(x in cmd for x in ['كل الطلبات', 'all orders']):
        if not orders:
            send_message(sender_id, "مافيش طلبات خالص يا مدير.")
        else:
            msg = f"آخر 10 طلبات من أصل {len(orders)}:\n"
            for o in orders[-10:]:
                status = "✅" if o.get('status') == 'مكتمل' else "⏳"
                msg += f"{status} #{o['id']} - {o['name']} - {o['service']}\n"
            send_message(sender_id, msg)
        return True
    
    # عرض تفاصيل طلب معين
    elif any(x in cmd for x in ['تفاصيل', 'details']) and any(c.isdigit() for c in cmd):
        numbers = [int(c) for c in cmd.split() if c.isdigit()]
        if numbers:
            order_id = numbers[0]
            order = next((o for o in orders if o['id'] == order_id), None)
            if order:
                notes = order.get('notes', 'مافيش')
                msg = f"""📋 الطلب #{order['id']}

👤 الاسم: {order['name']}
🛠 الخدمة: {order['service']}
💰 الميزانية: {order['budget']} USDT
📱 الجوال: {order.get('phone', 'غير متوفر')}
📝 ملاحظات: {notes}
📌 الحالة: {order.get('status', 'جديد')}

💬 آخر محادثة:
{order['conversation'][-3:] if order['conversation'] else 'مافيش'}

🔗 {order['link']}"""
                send_message(sender_id, msg)
            else:
                send_message(sender_id, f"ما لقيت طلب رقم {order_id} يا مدير.")
        return True
    
    # حذف طلب
    elif any(x in cmd for x in ['حذف', 'delete']) and any(c.isdigit() for c in cmd):
        numbers = [int(c) for c in cmd.split() if c.isdigit()]
        if numbers:
            order_id = numbers[0]
            order = next((o for o in orders if o['id'] == order_id), None)
            if order:
                delete_order(order_id)
                send_message(sender_id, f"تم حذف الطلب #{order_id} يا مدير.")
            else:
                send_message(sender_id, f"ما لقيت الطلب #{order_id}.")
        return True
    
    # إضافة ملاحظة
    elif any(x in cmd for x in ['ملاحظة', 'note']):
        # مثال: ملاحظة 5 العميل ده محترم
        parts = cmd.split()
        for i, part in enumerate(parts):
            if part.isdigit():
                order_id = int(part)
                note = ' '.join(parts[i+1:])
                add_note(order_id, note)
                send_message(sender_id, f"تم إضافة الملاحظة للطلب #{order_id}")
                return True
    
    # تغيير حالة الطلب
    elif any(x in cmd for x in ['مكتمل', 'complete']) and any(c.isdigit() for c in cmd):
        numbers = [int(c) for c in cmd.split() if c.isdigit()]
        if numbers:
            order_id = numbers[0]
            update_order(order_id, {'status': 'مكتمل'})
            send_message(sender_id, f"تم تحديث الطلب #{order_id} إلى مكتمل")
        return True
    
    # حظر مستخدم
    elif any(x in cmd for x in ['حظر', 'block']) and len(cmd.split()) > 1:
        target = cmd.split()[1]
        if target.isdigit() and len(target) > 5:
            blocked_users.add(target)
            save_json(BLOCKED_FILE, list(blocked_users))
            send_message(sender_id, f"تم حظر المستخدم {target[:15]}...")
            add_log(f"🔨 حظر {target[:15]}...")
        return True
    
    # إلغاء حظر
    elif any(x in cmd for x in ['الغاء حظر', 'unblock']) and len(cmd.split()) > 1:
        target = cmd.split()[1]
        if target in blocked_users:
            blocked_users.remove(target)
            save_json(BLOCKED_FILE, list(blocked_users))
            send_message(sender_id, f"تم إلغاء حظر {target[:15]}...")
        return True
    
    # عرض المحظورين
    elif any(x in cmd for x in ['المحظورين', 'blocked']):
        if not blocked_users:
            send_message(sender_id, "مافيش محظورين يا مدير.")
        else:
            msg = f"المحظورين ({len(blocked_users)}):\n"
            for uid in list(blocked_users)[:10]:
                msg += f"• {uid[:15]}...\n"
            send_message(sender_id, msg)
        return True
    
    return False

# ========== استخراج بيانات العملاء ==========
def extract_client_data(text, client):
    updated = False
    
    # استخراج الاسم
    if not client.name:
        patterns = [
            r'اسمي[:\s]*([\u0600-\u06FF\s]{2,20})',
            r'my name is[:\s]*([a-zA-Z\s]{2,20})',
            r'انا[:\s]*([\u0600-\u06FF\s]{2,20})',
            r'الاسم[:\s]*([\u0600-\u06FF\s]{2,20})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client.name = match.group(1).strip()
                add_log(f"✅ اسم جديد: {client.name}")
                updated = True
                break
    
    # استخراج الخدمة
    if not client.service:
        services = {
            'شعار': 'تصميم شعار',
            'logo': 'تصميم شعار',
            'موقع': 'تصميم موقع',
            'website': 'تصميم موقع',
            'web': 'تصميم موقع',
            'متجر': 'متجر إلكتروني',
            'ecommerce': 'متجر إلكتروني',
            'تطبيق': 'تطبيق جوال',
            'app': 'تطبيق جوال',
            'mobile': 'تطبيق جوال',
            'بوت': 'بوت ذكاء اصطناعي',
            'bot': 'بوت ذكاء اصطناعي',
            'ai': 'بوت ذكاء اصطناعي',
            'تصميم': 'تصميم جرافيك',
            'design': 'تصميم جرافيك'
        }
        for kw, service in services.items():
            if kw in text.lower():
                client.service = service
                add_log(f"✅ خدمة: {service}")
                updated = True
                break
    
    # استخراج الميزانية
    if not client.budget:
        match = re.search(r'(\d+)[\s-]*(usdt|دولار|\$|dollar)', text, re.IGNORECASE)
        if match:
            client.budget = int(match.group(1))
            add_log(f"✅ ميزانية: {client.budget} USDT")
            updated = True
    
    # استخراج رقم الجوال
    if not client.phone:
        match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9}|00966[0-9]{9})', text)
        if match:
            client.phone = match.group(1)
            add_log(f"✅ جوال: {client.phone}")
            updated = True
    
    return updated

# ========== الذكاء الاصطناعي ==========
def get_ai_response(user_msg, client, is_owner=False):
    try:
        if is_owner:
            prompt = BOT_PERSONALITY + "\n\nأنت تتكلم مع مديرك، خفف دمك شوية وكن واضح."
        else:
            prompt = BOT_PERSONALITY + "\n\nأنت تتكلم مع عميل، حاول تجمع بياناته بهدوء."
        
        context = f"{prompt}\n\nآخر كلام:\n" + "\n".join(client.conversation[-4:]) + f"\nالعميل: {user_msg}\nأحمد:"
        url = f'{AI_API_URL}?text={requests.utils.quote(context)}'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get('response', '').strip()
    except:
        pass
    
    if is_owner:
        return "حاضر يا مدير، بس فيه مشكلة تقنية. جرب تاني."
    return "آسف، فيه مشكلة تقنية. ممكن تعيد السؤال؟"

# ========== المعالجة الرئيسية ==========
def process_message(sender_id, text):
    add_log(f"📨 من {sender_id[:10]}...: {text[:50]}")
    stats['messages_received'] += 1
    
    # تحقق الحظر
    if sender_id in blocked_users:
        return
    
    # إنشاء جلسة
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
    
    client = sessions[sender_id]
    client.conversation.append(f"العميل: {text}")
    
    # إذا كان مديراً
    if sender_id in OWNER_FB_IDS or sender_id in verified_users:
        # تنفيذ أوامر المدير
        if handle_owner_command(text, sender_id):
            client.conversation.append(f"النظام: تم تنفيذ أمر المدير")
            return
        
        # رد عادي من الذكاء للمدير
        response = get_ai_response(text, client, is_owner=True)
        send_message(sender_id, response)
        client.conversation.append(f"أحمد: {response[:50]}...")
        return
    
    # معالجة كلمة المرور
    if client.awaiting_password:
        if text.strip() == OWNER_PASSWORD:
            verified_users.add(sender_id)
            save_json(VERIFIED_USERS_FILE, list(verified_users))
            client.awaiting_password = False
            send_message(sender_id, "أهلاً يا مدير، نورت.")
            add_log(f"🔐 مدير جديد: {sender_id[:10]}...")
        else:
            send_message(sender_id, "غلط يا باشا، حاول تاني.")
        return
    
    # كشف محاولات انتحال المدير
    if any(kw in text.lower() for kw in ['مدير', 'owner', 'المالك', 'ياسين']):
        client.awaiting_password = True
        send_message(sender_id, "طب أهلاً، لو أنت المدير أدخل الرقم السري:")
        return
    
    # استخراج البيانات
    data_updated = extract_client_data(text, client)
    
    # إذا اكتملت البيانات
    if client.is_complete() and not client.confirmed:
        # حفظ الطلب
        order = save_order(client)
        
        # إرسال تفاصيل الدفع للعميل
        deposit = int(client.budget * 0.3)
        wallet_msg = f"""تم بحمد الله، طلبك اكتمل يا {client.name}!

ملخص الطلب:
• {client.service}
• الميزانية: {client.budget} USDT
• المقدم 30%: {deposit} USDT

للدفع:
معرف بينانس: {BINANCE_ID}

حول المقدم وابعتلي، وهبدأ الشغل فوراً.

شكراً لثقتك في B.Y PRO ❤️"""
        send_message(sender_id, wallet_msg)
        
        # إشعار المدير
        notify_owner(order)
        
        client.confirmed = True
        return
    
    # رد عادي من الذكاء
    response = get_ai_response(text, client, is_owner=False)
    send_message(sender_id, response)
    client.conversation.append(f"أحمد: {response[:50]}...")

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
                    sender = msg['sender']['id']
                    text = msg['message']['text']
                    threading.Thread(target=process_message, args=(sender, text)).start()
    return 'OK', 200

@app.route('/')
def home():
    html = """
    <!DOCTYPE html>
    <html dir='rtl' lang='ar'>
    <head>
        <meta charset='UTF-8'>
        <title>B.Y PRO - أحمد البوت</title>
        <style>
            * { font-family: 'Segoe UI', Tahoma, sans-serif; box-sizing: border-box; }
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; margin: 0; }
            .container { max-width: 1400px; margin: 0 auto; }
            .header { background: white; border-radius: 20px; padding: 30px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
            h1 { color: #333; margin: 0 0 10px; }
            .status { background: #4ade80; color: #166534; padding: 8px 25px; border-radius: 25px; display: inline-block; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .card { background: white; border-radius: 15px; padding: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            .card .value { font-size: 2.5em; font-weight: bold; color: #667eea; margin-top: 10px; }
            .logs { background: white; border-radius: 15px; padding: 20px; margin-bottom: 20px; max-height: 200px; overflow-y: auto; }
            .orders { background: white; border-radius: 15px; padding: 20px; }
            .order-item { border-bottom: 1px solid #eee; padding: 15px; display: grid; grid-template-columns: auto 2fr 1fr 1fr auto; gap: 10px; align-items: center; }
            .order-item:hover { background: #f5f5f5; }
            .badge { padding: 5px 10px; border-radius: 15px; font-size: 0.9em; }
            .badge.new { background: #fef3c7; color: #92400e; }
            .badge.complete { background: #d1fae5; color: #065f46; }
            .btn { background: #667eea; color: white; border: none; padding: 5px 15px; border-radius: 20px; cursor: pointer; }
            .btn:hover { background: #764ba2; }
            .notes { font-size: 0.9em; color: #666; }
        </style>
    </head>
    <body>
        <div class='container'>
            <div class='header'>
                <h1>🤵 أحمد - مساعد مبيعات B.Y PRO</h1>
                <div class='status'>✅ شغال</div>
                <p>⏱ من: {{ start_time }}</p>
                <p>💰 بينانس: <code style="background: #f0f0f0; padding: 5px 10px; border-radius: 10px;">{{ binance_id }}</code></p>
            </div>
            
            <div class='grid'>
                <div class='card'><h3>👥 العملاء</h3><div class='value'>{{ total_clients }}</div></div>
                <div class='card'><h3>📦 الطلبات</h3><div class='value'>{{ orders_count }}</div></div>
                <div class='card'><h3>🔨 المحظورين</h3><div class='value'>{{ blocked_count }}</div></div>
                <div class='card'><h3>🔐 الموثوقين</h3><div class='value'>{{ verified_count }}</div></div>
            </div>
            
            <div class='logs'>
                <h3>📋 آخر الأخبار</h3>
                {% for log in logs %}
                <div style="padding: 5px; border-bottom: 1px solid #eee;">[{{ log.time }}] {{ log.message }}</div>
                {% endfor %}
            </div>
            
            <div class='orders'>
                <h3>📦 آخر الطلبات</h3>
                {% for order in recent_orders %}
                <div class='order-item'>
                    <span class='badge {% if order.status == "جديد" %}new{% else %}complete{% endif %}'>#{{ order.id }}</span>
                    <span><strong>{{ order.name }}</strong></span>
                    <span>{{ order.service }}</span>
                    <span>{{ order.budget }} USDT</span>
                    <span class='notes'>{{ order.notes or '—' }}</span>
                </div>
                {% endfor %}
                {% if not recent_orders %}
                <p style="text-align: center; color: #999;">مافيش طلبات لحد دلوقتي</p>
                {% endif %}
            </div>
        </div>
        <script>setTimeout(()=>location.reload(), 5000);</script>
    </body>
    </html>
    """
    
    recent_orders = orders[-20:] if orders else []
    
    return render_template_string(
        html,
        total_clients=len(sessions),
        orders_count=len(orders),
        blocked_count=len(blocked_users),
        verified_count=len(verified_users),
        start_time=stats['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        logs=list(logs)[:20],
        recent_orders=recent_orders
    )

# ========== Keep alive ==========
def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get("https://by-pro-marketing-agent.onrender.com")
        except:
            pass

# ========== التشغيل ==========
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🤵 أحمد - مساعد مبيعات B.Y PRO")
    print("="*60)
    print(f"👤 المدير: {OWNER_FB_IDS[0]}")
    print(f"🔐 كلمة السر: {OWNER_PASSWORD}")
    print(f"💰 بينانس: {BINANCE_ID}")
    print(f"📊 طلبات: {len(orders)}")
    print("="*60 + "\n")
    
    threading.Thread(target=keep_alive, daemon=True).start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
