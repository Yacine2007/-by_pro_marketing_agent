import os
import re
import json
import requests
import time
import threading
import sys
import random
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ========== المتغيرات ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_IDS = ['2592319994', '61580260328404']  # المديرين الموثوقين
OWNER_PASSWORD = "20070909"
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"
BINANCE_ID = "1074084246"

# ========== البرومبت الأساسي ==========
MAIN_SYSTEM_PROMPT = """أنت مساعد مبيعات B.Y PRO الرسمي.

هويتك المهنية:
أنت وكيل مبيعات بشري محنك، تعمل لصالح شركة B.Y PRO للتكنولوجيا والبرمجيات. أنت هادئ، واثق، ومختصر جداً في حديثك.

مبادئ التواصل:
1. الاختصار الذكي: أجب على قدر السؤال بدقة.
2. التكيف اللغوي: تحدث بنفس لغة المستخدم.
3. عدم الإلحاح: إذا قدمت العرض ولم يرد، لا تلاحقه.

الخدمات والأسعار:
- المواقع التعريفية: 300$ - 800$ (5-10 أيام)
- المتاجر الإلكترونية: 700$ - 1800$ (15-25 يوماً)
- أنظمة الأتمتة وبوتات الذكاء الاصطناعي: من 300$ (7-14 يوماً)
- تطبيقات الموبايل: من 1500$ (30-60 يوماً)
- التصميم الجرافيكي: 50$ - 200$ (24-72 ساعة)

بروتوكول التعامل المالي:
- 30% عربون مقدم، 70% عند التسليم
- وسيلة الدفع: USDT (Binance Pay)
- معرف بينانس: 1074084246

مهمتك الأساسية: جمع بيانات العملاء (الاسم، الخدمة المطلوبة، الميزانية، رقم الجوال) وتحويلهم إلى طلبات مؤكدة."""

OWNER_SYSTEM_PROMPT = """أنت مساعد مبيعات B.Y PRO، تتحدث مع المدير.

تفاعلك مع المدير:
- كن محترفاً ومختصراً
- أجب على أسئلته بكل شفافية
- استخدم نظام الدوال لجلب البيانات:
  * [FUNCTION:get_stats] - إحصائيات عامة
  * [FUNCTION:get_today_orders] - طلبات اليوم
  * [FUNCTION:get_all_orders] - كل الطلبات
  * [FUNCTION:get_order|NUMBER] - طلب محدد
  * [FUNCTION:get_blocked] - المحظورين
  * [FUNCTION:get_verified] - الموثوقين
  * [FUNCTION:block_user|ID] - حظر مستخدم
  * [FUNCTION:unblock_user|ID] - إلغاء حظر
  * [FUNCTION:search_client|NAME] - بحث عن عميل"""

# ========== تخزين البيانات ==========
logs = deque(maxlen=100)
stats = {
    'messages_received': 0,
    'messages_sent': 0,
    'errors': 0,
    'start_time': datetime.now().isoformat()
}

ORDERS_FILE = "orders.json"
BLOCKED_FILE = "blocked_users.json"
VERIFIED_USERS_FILE = "verified_users.json"

def load_orders():
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_orders(orders):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def load_blocked():
    try:
        with open(BLOCKED_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_blocked(blocked_set):
    with open(BLOCKED_FILE, 'w') as f:
        json.dump(list(blocked_set), f)

def load_verified():
    try:
        with open(VERIFIED_USERS_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_verified(verified_set):
    with open(VERIFIED_USERS_FILE, 'w') as f:
        json.dump(list(verified_set), f)

# تحميل البيانات
orders = load_orders()
blocked_users = load_blocked()
verified_users = load_verified()

# ========== الجلسات ==========
sessions = {}

class ClientData:
    def __init__(self, sender_id):
        self.sender_id = sender_id
        self.name = ""
        self.service = ""
        self.budget = ""
        self.phone = ""
        self.confirmed = False
        self.conversation = []
        self.last_message_time = datetime.now()
        self.awaiting_password = False
    
    def is_complete(self):
        return bool(self.name and self.service and self.budget)
    
    def get_link(self):
        return f"https://www.facebook.com/messages/t/{self.sender_id}"
    
    def to_dict(self):
        return {
            'name': self.name or 'غير معروف',
            'service': self.service or 'لم يحدد',
            'budget': self.budget or 'لم يحدد',
            'phone': self.phone or 'غير متوفر',
            'confirmed': self.confirmed,
            'messages': len(self.conversation)
        }

# ========== نظام التسجيل ==========
def add_log(event_type, message):
    log_entry = {
        'time': datetime.now().strftime('%H:%M:%S'),
        'type': event_type,
        'message': message
    }
    logs.appendleft(log_entry)
    print(f"[{log_entry['time']}] {event_type}: {message}")

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    try:
        add_log('SEND', f'إلى {recipient_id[:10]}...: {text[:50]}')
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
        else:
            stats['errors'] += 1
            return False
    except:
        stats['errors'] += 1
        return False

# ========== حفظ الطلب ==========
def save_order(client, details):
    global orders
    order = {
        'order_id': len(orders) + 1,
        'client_name': client.name,
        'service': client.service,
        'budget': client.budget,
        'phone': client.phone,
        'details': details,
        'timestamp': datetime.now().isoformat(),
        'sender_id': client.sender_id,
        'link': client.get_link()
    }
    orders.append(order)
    save_orders(orders)
    add_log('ORDER', f'✅ طلب جديد #{order["order_id"]} - {client.name}')
    return order

# ========== إرسال الطلب للمدير ==========
def send_order_to_owner(client):
    details = "\n".join(client.conversation[-5:]) if client.conversation else ""
    order = save_order(client, details)
    
    msg = f"""🔔 طلب جديد!
رقم: #{order['order_id']}
الاسم: {client.name}
الخدمة: {client.service}
الميزانية: {client.budget}
الجوال: {client.phone or 'غير متوفر'}
{client.get_link()}"""
    
    send_message(OWNER_FB_IDS[0], msg)
    return order

# ========== التحقق من المدير ==========
def is_owner(sender_id):
    return sender_id in OWNER_FB_IDS or sender_id in verified_users

# ========== تنفيذ أوامر المدير ==========
def execute_owner_command(text, sender_id):
    cmd = text.lower().strip()
    
    # إحصائيات
    if any(x in cmd for x in ['احصائيات', 'stats', 'احصاء']):
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = len([o for o in orders if o['timestamp'].startswith(today)])
        msg = f"""📊 إحصائيات:
العملاء: {len(sessions)}
الطلبات الكلية: {len(orders)}
طلبات اليوم: {today_orders}
المحظورين: {len(blocked_users)}
الموثوقين: {len(verified_users)}"""
        send_message(sender_id, msg)
        return True
    
    # طلبات اليوم
    elif any(x in cmd for x in ['طلبات اليوم', 'ليوم', 'today']):
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = [o for o in orders if o['timestamp'].startswith(today)]
        if not today_orders:
            send_message(sender_id, "ما في طلبات اليوم.")
        else:
            msg = f"طلبات اليوم ({len(today_orders)}):\n"
            for o in today_orders[-5:]:
                msg += f"#{o['order_id']} - {o['client_name']} - {o['service']} - {o['budget']}\n"
            send_message(sender_id, msg)
        return True
    
    # كل الطلبات
    elif any(x in cmd for x in ['كل الطلبات', 'all orders']):
        if not orders:
            send_message(sender_id, "ما في طلبات مسجلة.")
        else:
            msg = f"آخر 10 طلبات من {len(orders)}:\n"
            for o in orders[-10:]:
                msg += f"#{o['order_id']} - {o['client_name']} - {o['service']}\n"
            send_message(sender_id, msg)
        return True
    
    # المحظورين
    elif any(x in cmd for x in ['محظورين', 'blocked']):
        if not blocked_users:
            send_message(sender_id, "ما في محظورين.")
        else:
            msg = f"المحظورين ({len(blocked_users)}):\n"
            for uid in list(blocked_users)[:10]:
                msg += f"• {uid[:15]}...\n"
            send_message(sender_id, msg)
        return True
    
    # الموثوقين
    elif any(x in cmd for x in ['موثوقين', 'verified']):
        if not verified_users:
            send_message(sender_id, "ما في موثوقين غيرك.")
        else:
            msg = f"الموثوقين ({len(verified_users)}):\n"
            for uid in list(verified_users)[:10]:
                msg += f"• {uid[:15]}...\n"
            send_message(sender_id, msg)
        return True
    
    return False

# ========== الذكاء الاصطناعي ==========
def get_ai_response(user_msg, client, is_owner=False):
    try:
        if is_owner:
            prompt = OWNER_SYSTEM_PROMPT
        else:
            prompt = MAIN_SYSTEM_PROMPT
        
        context = f"{prompt}\n\nآخر محادثة:\n" + "\n".join(client.conversation[-4:]) + f"\nالمستخدم: {user_msg}\nالرد:"
        url = f'{AI_API_URL}?text={requests.utils.quote(context)}'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get('response', '').strip()
    except:
        pass
    
    if is_owner:
        return "عذراً يا مدير، الرجاء المحاولة مرة أخرى."
    return "عذراً، حدث خطأ. كيف يمكنني مساعدتك؟"

# ========== معالجة الرسائل ==========
def process_message(sender_id, text):
    add_log('RECEIVE', f'من {sender_id[:10]}...: {text[:50]}')
    stats['messages_received'] += 1
    
    # تحقق الحظر
    if sender_id in blocked_users:
        return
    
    # إنشاء جلسة
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
    
    client = sessions[sender_id]
    client.conversation.append(f"المستخدم: {text}")
    
    # معالجة المدير
    if is_owner(sender_id):
        # تنفيذ الأوامر المباشرة أولاً
        if execute_owner_command(text, sender_id):
            client.conversation.append(f"النظام: تم تنفيذ أمر المدير")
            return
        
        # إذا ما كان أمر مباشر، استخدم الذكاء
        response = get_ai_response(text, client, is_owner=True)
        send_message(sender_id, response)
        client.conversation.append(f"المساعد: {response[:50]}...")
        return
    
    # معالجة كلمة المرور
    if client.awaiting_password:
        if text.strip() == OWNER_PASSWORD:
            verified_users.add(sender_id)
            save_verified(verified_users)
            client.awaiting_password = False
            send_message(sender_id, "أهلاً بك يا مدير.")
            add_log('SECURITY', f'✅ تحقق ناجح {sender_id[:10]}...')
        else:
            send_message(sender_id, "❌ كلمة المرور خطأ.")
        return
    
    # كشف محاولات انتحال المدير
    if any(kw in text.lower() for kw in ['مدير', 'owner', 'المالك']):
        client.awaiting_password = True
        send_message(sender_id, "🔐 الرجاء إدخال الرقم السري:")
        return
    
    # ========== استخراج بيانات العميل ==========
    
    # استخراج الاسم
    if not client.name:
        patterns = [
            r'اسمي[:\s]*([\w\s]{2,20})',
            r'my name is[:\s]*([\w\s]{2,20})',
            r'انا[:\s]*([\w\s]{2,20})',
            r'الاسم[:\s]*([\w\s]{2,20})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client.name = match.group(1).strip()
                add_log('DATA', f'✅ الاسم: {client.name}')
                break
    
    # استخراج الخدمة
    if not client.service:
        services = {
            'شعار': 'تصميم شعار',
            'logo': 'تصميم شعار',
            'موقع': 'تصميم موقع',
            'website': 'تصميم موقع',
            'متجر': 'متجر إلكتروني',
            'ecommerce': 'متجر إلكتروني',
            'تطبيق': 'تطبيق جوال',
            'app': 'تطبيق جوال',
            'بوت': 'بوت ذكاء اصطناعي',
            'bot': 'بوت ذكاء اصطناعي',
            'تصميم': 'تصميم جرافيك',
            'design': 'تصميم جرافيك'
        }
        for kw, service in services.items():
            if kw in text.lower():
                client.service = service
                add_log('DATA', f'✅ الخدمة: {client.service}')
                break
    
    # استخراج الميزانية
    if not client.budget:
        match = re.search(r'(\d+)[\s-]*(usdt|دولار|\$|dollar)', text, re.IGNORECASE)
        if match:
            client.budget = f"{match.group(1)} USDT"
            add_log('DATA', f'✅ الميزانية: {client.budget}')
    
    # استخراج رقم الجوال
    if not client.phone:
        match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9}|00966[0-9]{9})', text)
        if match:
            client.phone = match.group(1)
            add_log('DATA', f'✅ الجوال: {client.phone}')
    
    # إذا اكتملت البيانات، أرسل تفاصيل الدفع
    if client.is_complete() and not client.confirmed:
        wallet_msg = f"""✅ تم تأكيد طلبك!

📋 ملخص الطلب:
• الخدمة: {client.service}
• الميزانية: {client.budget}
• الاسم: {client.name}
• الجوال: {client.phone or 'غير متوفر'}

💰 للدفع:
• 30% عربون: {int(client.budget.split()[0]) * 0.3} USDT
• معرف بينانس: {BINANCE_ID}

بعد الدفع نبدأ التنفيذ فوراً."""
        
        send_message(sender_id, wallet_msg)
        send_order_to_owner(client)
        client.confirmed = True
        return
    
    # رد عادي من الذكاء
    response = get_ai_response(text, client, is_owner=False)
    send_message(sender_id, response)
    client.conversation.append(f"المساعد: {response[:50]}...")

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

@app.route('/block/<user_id>', methods=['POST'])
def block_user(user_id):
    blocked_users.add(user_id)
    save_blocked(blocked_users)
    return jsonify({'status': 'blocked'})

@app.route('/unblock/<user_id>', methods=['POST'])
def unblock_user(user_id):
    if user_id in blocked_users:
        blocked_users.remove(user_id)
        save_blocked(blocked_users)
    return jsonify({'status': 'unblocked'})

@app.route('/debug')
def debug():
    clients_list = []
    for k, v in list(sessions.items())[-10:]:
        clients_list.append({'id': k[:10], **v.to_dict()})
    
    return jsonify({
        'sessions': len(sessions),
        'orders': len(orders),
        'blocked': len(blocked_users),
        'verified': len(verified_users),
        'stats': stats,
        'recent_clients': clients_list,
        'recent_orders': orders[-5:] if orders else []
    })

@app.route('/')
def home():
    html = """
    <!DOCTYPE html>
    <html dir='rtl' lang='ar'>
    <head>
        <meta charset='UTF-8'>
        <title>B.Y PRO - البوت</title>
        <style>
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; font-family: 'Segoe UI', Tahoma, sans-serif; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: white; border-radius: 15px; padding: 30px; margin-bottom: 20px; }
            h1 { color: #333; }
            .status { background: #4ade80; color: #166534; padding: 8px 20px; border-radius: 25px; display: inline-block; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .card { background: white; border-radius: 15px; padding: 20px; }
            .card .value { font-size: 2.5em; font-weight: bold; color: #667eea; }
            .logs { background: white; border-radius: 15px; padding: 20px; max-height: 200px; overflow-y: auto; margin-bottom: 20px; }
            .orders { background: white; border-radius: 15px; padding: 20px; }
            .order-item { border-bottom: 1px solid #eee; padding: 10px; }
        </style>
    </head>
    <body>
        <div class='container'>
            <div class='header'>
                <h1>🤖 B.Y PRO - مساعد المبيعات</h1>
                <div class='status'>✅ يعمل</div>
                <p>⏱ وقت التشغيل: {{ start_time }}</p>
                <p>💰 بينانس: <code>{{ binance_id }}</code></p>
            </div>
            
            <div class='grid'>
                <div class='card'><h3>العملاء</h3><div class='value'>{{ total_clients }}</div></div>
                <div class='card'><h3>الطلبات</h3><div class='value'>{{ orders_count }}</div></div>
                <div class='card'><h3>المحظورين</h3><div class='value'>{{ blocked_count }}</div></div>
                <div class='card'><h3>الموثوقين</h3><div class='value'>{{ verified_count }}</div></div>
            </div>
            
            <div class='logs'>
                <h3>📋 آخر الأحداث</h3>
                {% for log in logs %}
                <div>[{{ log.time }}] {{ log.message }}</div>
                {% endfor %}
            </div>
            
            <div class='orders'>
                <h3>📦 آخر الطلبات</h3>
                {% for order in recent_orders %}
                <div class='order-item'>
                    #{{ order.order_id }} - {{ order.client_name }} - {{ order.service }} - {{ order.budget }}
                </div>
                {% endfor %}
                {% if not recent_orders %}
                <p>لا توجد طلبات بعد</p>
                {% endif %}
            </div>
        </div>
        <script>setTimeout(()=>location.reload(), 5000);</script>
    </body>
    </html>
    """
    
    recent_orders = orders[-10:] if orders else []
    
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

# ========== التشغيل ==========
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 B.Y PRO - البوت الشغال 100%")
    print("="*60)
    print(f"👤 معرف المدير: {OWNER_FB_IDS[0]}")
    print(f"🔐 كلمة المرور: {OWNER_PASSWORD}")
    print(f"💰 بينانس ID: {BINANCE_ID}")
    print(f"📊 الطلبات الحالية: {len(orders)}")
    print("="*60 + "\n")
    
    threading.Thread(target=lambda: [time.sleep(600) or requests.get("https://by-pro-marketing-agent.onrender.com") for _ in iter(int, 1)], daemon=True).start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
