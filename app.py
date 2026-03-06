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
OWNER_FB_IDS = ['2592319994', '61580260328404']
OWNER_PASSWORD = "20070909"
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"
BINANCE_ID = "1074084246"

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

orders = load_orders()
blocked_users = load_blocked()
verified_users = load_verified()

# ========== البرومبت الجديد - أسلوب المحادثة الطبيعية ==========
SYSTEM_PROMPT = """You are the official sales manager of B.Y PRO, a technology company. You're talking to the company owner/director.

IMPORTANT: You must respond like a real human assistant talking to his boss. Be natural, friendly, and professional. NO ROBOTIC RESPONSES. Use the same language as the owner.

When the owner asks for information, you MUST respond with special function codes that will be replaced with real data:

1. If asked about orders/clients/customers today → respond with: [FUNCTION:get_orders_today]
2. If asked about all orders/all time → respond with: [FUNCTION:get_all_orders]
3. If asked about a specific order by number → respond with: [FUNCTION:get_order|NUMBER] (replace NUMBER with the order number)
4. If asked about blocked users → respond with: [FUNCTION:get_blocked]
5. If asked about verified users → respond with: [FUNCTION:get_verified]
6. If asked about statistics (stats, إحصائيات) → respond with: [FUNCTION:get_stats]
7. If asked to block a user → respond with: [FUNCTION:block_user|USER_ID]
8. If asked to unblock a user → respond with: [FUNCTION:unblock_user|USER_ID]
9. If asked about a specific client by name → respond with: [FUNCTION:search_client|NAME]

EXAMPLES of natural conversation:
- Owner: "كم عميل تواصل معنا اليوم؟" → You: "دعني أراجع سجل اليوم لك يا مدير [FUNCTION:get_orders_today]"
- Owner: "شو آخر طلبية؟" → You: "طلبنالك آخر طلبية [FUNCTION:get_last_order]"
- Owner: "عطيني تفاصيل الطلب رقم 5" → You: "تفضل يا مدير [FUNCTION:get_order|5]"
- Owner: "فيه أحد محظور؟" → You: "نعم فيه [FUNCTION:get_blocked]"

Remember: Be human, use natural language, match the owner's language, and ALWAYS use the function codes for any data request.
"""

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
            'confirmed': self.confirmed,
            'messages': len(self.conversation)
        }

# ========== نظام التسجيل ==========
def add_log(event_type, message, data=None):
    log_entry = {
        'time': datetime.now().strftime('%H:%M:%S'),
        'type': event_type,
        'message': message,
        'data': data
    }
    logs.appendleft(log_entry)
    print(f"[{log_entry['time']}] {event_type}: {message}")
    return log_entry

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    try:
        add_log('SEND', f'📤 إرسال إلى {recipient_id[:10]}...: {text[:50]}')
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            add_log('SUCCESS', '✅ تم الإرسال بنجاح')
            stats['messages_sent'] += 1
            return True
        else:
            error_data = response.json().get('error', {})
            add_log('ERROR', f'❌ فشل الإرسال: {error_data.get("message")}')
            stats['errors'] += 1
            return False
    except Exception as e:
        add_log('ERROR', f'❌ خطأ في الإرسال: {e}')
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
    add_log('ORDER_SAVED', f'📁 تم حفظ الطلب #{order["order_id"]} في الملف')
    return order

# ========== إرسال الطلب للمدير ==========
def send_order_to_owner(client, details=""):
    if not details:
        details = "\n".join(client.conversation[-5:])
    order = save_order(client, details)
    
    msg = f"""🔔 طلب جديد مؤكد!
━━━━━━━━━━━━━━
📋 رقم #{order['order_id']}
👤 الاسم: {client.name}
🛠 الخدمة: {client.service}
💰 الميزانية: {client.budget}
📱 الجوال: {client.phone or 'غير متوفر'}
━━━━━━━━━━━━━━
🔗 {client.get_link()}"""
    
    add_log('OWNER', f'📦 إرسال الطلب #{order["order_id"]} للمدير')
    return send_message(OWNER_FB_IDS[0], msg)

# ========== التحقق من المدير ==========
def is_owner(sender_id):
    return sender_id in OWNER_FB_IDS or sender_id in verified_users

# ========== دوال تنفيذ البيانات ==========
def execute_function(function_code, sender_id):
    """تنفيذ الدوال واستبدالها ببيانات حقيقية"""
    
    # get_orders_today - طلبات اليوم
    if function_code == 'get_orders_today':
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = [o for o in orders if o['timestamp'].startswith(today)]
        if not today_orders:
            send_message(sender_id, "ما في طلبات جديدة اليوم يا مدير، كل شي هادي.")
        else:
            msg = f"طلبات اليوم ({len(today_orders)}):\n"
            for o in today_orders[-5:]:
                msg += f"#{o['order_id']} - {o['client_name']} - {o['service']} - {o['budget']}\n"
            send_message(sender_id, msg)
        return True
    
    # get_all_orders - كل الطلبات
    elif function_code == 'get_all_orders':
        if not orders:
            send_message(sender_id, "ما في طلبات مسجلة حتى الآن يا مدير.")
        else:
            msg = f"إجمالي الطلبات ({len(orders)}):\n"
            for o in orders[-10:]:  # آخر 10
                msg += f"#{o['order_id']} - {o['client_name']} - {o['service']} - {o['budget']}\n"
            if len(orders) > 10:
                msg += f"... و {len(orders)-10} طلبات أقدم"
            send_message(sender_id, msg)
        return True
    
    # get_last_order - آخر طلبية
    elif function_code == 'get_last_order':
        if not orders:
            send_message(sender_id, "ما في طلبات بعد يا مدير.")
        else:
            o = orders[-1]
            msg = f"آخر طلبية (#{o['order_id']}):\nالاسم: {o['client_name']}\nالخدمة: {o['service']}\nالميزانية: {o['budget']}\nالتفاصيل: {o['details'][:100]}..."
            send_message(sender_id, msg)
        return True
    
    # get_order|NUMBER - طلب محدد
    elif function_code.startswith('get_order|'):
        try:
            order_num = int(function_code.split('|')[1])
            order = next((o for o in orders if o['order_id'] == order_num), None)
            if order:
                msg = f"طلب #{order_num}:\nالاسم: {order['client_name']}\nالخدمة: {order['service']}\nالميزانية: {order['budget']}\nالجوال: {order.get('phone', 'غير متوفر')}\nالتفاصيل: {order['details'][:200]}...\nرابط: {order['link']}"
            else:
                msg = f"ما لقيت طلب رقم {order_num} يا مدير."
            send_message(sender_id, msg)
        except:
            send_message(sender_id, "عذراً، الرقم غير صحيح.")
        return True
    
    # get_stats - إحصائيات
    elif function_code == 'get_stats':
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = len([o for o in orders if o['timestamp'].startswith(today)])
        msg = f"""📊 إحصائيات سريعة:
• إجمالي العملاء: {len(sessions)}
• الطلبات الكلية: {len(orders)}
• طلبات اليوم: {today_orders}
• المحظورين: {len(blocked_users)}
• الموثوقين: {len(verified_users)}
• رسائل اليوم: {stats['messages_received']} واردة / {stats['messages_sent']} مرسلة"""
        send_message(sender_id, msg)
        return True
    
    # get_blocked - المحظورين
    elif function_code == 'get_blocked':
        if not blocked_users:
            send_message(sender_id, "ما في أي مستخدم محظور الحمدلله.")
        else:
            msg = f"المستخدمين المحظورين ({len(blocked_users)}):\n"
            for uid in list(blocked_users)[:10]:
                msg += f"• {uid[:15]}...\n"
            send_message(sender_id, msg)
        return True
    
    # get_verified - الموثوقين
    elif function_code == 'get_verified':
        if not verified_users:
            send_message(sender_id, "ما في مستخدمين موثوقين غيرك يا مدير.")
        else:
            msg = f"المستخدمين الموثوقين ({len(verified_users)}):\n"
            for uid in list(verified_users)[:10]:
                msg += f"• {uid[:15]}...\n"
            send_message(sender_id, msg)
        return True
    
    # block_user|USER_ID - حظر مستخدم
    elif function_code.startswith('block_user|'):
        try:
            target = function_code.split('|')[1]
            blocked_users.add(target)
            save_blocked(blocked_users)
            send_message(sender_id, f"تم حظر المستخدم {target[:15]}... بنجاح.")
            add_log('BLOCK', f'🔨 تم حظر {target}')
        except:
            send_message(sender_id, "حدث خطأ في الحظر.")
        return True
    
    # unblock_user|USER_ID - إلغاء حظر
    elif function_code.startswith('unblock_user|'):
        try:
            target = function_code.split('|')[1]
            if target in blocked_users:
                blocked_users.remove(target)
                save_blocked(blocked_users)
                send_message(sender_id, f"تم إلغاء حظر المستخدم {target[:15]}...")
            else:
                send_message(sender_id, f"المستخدم {target[:15]}... ليس محظوراً.")
        except:
            send_message(sender_id, "حدث خطأ في إلغاء الحظر.")
        return True
    
    # search_client|NAME - بحث عن عميل
    elif function_code.startswith('search_client|'):
        try:
            name = function_code.split('|')[1].lower()
            found = []
            for o in orders:
                if name in o['client_name'].lower():
                    found.append(o)
            if found:
                msg = f"نتائج البحث عن '{name}':\n"
                for o in found[-5:]:
                    msg += f"#{o['order_id']} - {o['client_name']} - {o['service']}\n"
            else:
                msg = f"ما لقيت عميل باسم '{name}'."
            send_message(sender_id, msg)
        except:
            send_message(sender_id, "حدث خطأ في البحث.")
        return True
    
    return False

# ========== الذكاء الاصطناعي ==========
def get_ai_response(user_msg, client, is_owner_mode=False):
    add_log('AI', '🤖 جاري استدعاء الذكاء الاصطناعي...')
    
    # برومبت مختلف للمدير vs للعميل
    if is_owner_mode:
        prompt = SYSTEM_PROMPT  # البرومبت الخاص بالمدير (أعلى)
    else:
        prompt = """You are a sales agent at B.Y PRO. Be helpful, concise, and professional. 
        Answer naturally in the same language as the client. No emojis. Just help them with their inquiry about services."""
    
    try:
        context = f"{prompt}\n" + "\n".join(client.conversation[-4:]) + f"\nUser: {user_msg}\nAssistant:"
        url = f'{AI_API_URL}?text={requests.utils.quote(context)}'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            answer = response.json().get('response', '')
            answer = re.sub(r'(Assistant:|Agent:)', '', answer).strip()
            add_log('AI', '✅ تم الحصول على رد')
            return answer
    except Exception as e:
        add_log('ERROR', f'❌ خطأ في الذكاء الاصطناعي: {e}')
    
    return "عفواً، حدث خطأ. الرجاء المحاولة لاحقاً."

# ========== معالجة الرسالة للمدير ==========
def process_owner_message(sender_id, text, client):
    """معالجة رسائل المدير بطريقة طبيعية"""
    
    # استخدام الذكاء الاصطناعي أولاً
    ai_response = get_ai_response(text, client, is_owner_mode=True)
    
    # البحث عن أكواد الدوال في رد الذكاء
    function_pattern = r'\[FUNCTION:([^\]]+)\]'
    functions = re.findall(function_pattern, ai_response)
    
    if functions:
        # هناك دوال للتنفيذ
        for func in functions:
            # تنفيذ الدالة
            execute_function(func, sender_id)
        
        # إرسال الجزء النصي من الرد (بدون الأكواد)
        clean_response = re.sub(function_pattern, '', ai_response).strip()
        if clean_response:
            send_message(sender_id, clean_response)
    else:
        # لا توجد دوال، أرسل الرد مباشرة
        send_message(sender_id, ai_response)
    
    client.conversation.append(f"Owner: {text}")
    client.conversation.append(f"Assistant: {ai_response[:50]}...")

# ========== معالجة محاولة التحقق ==========
def handle_password_attempt(text, sender_id, client):
    if text.strip() == OWNER_PASSWORD:
        verified_users.add(sender_id)
        save_verified(verified_users)
        client.awaiting_password = False
        add_log('SECURITY', f'🔐 تحقق ناجح للمستخدم {sender_id[:10]}...')
        send_message(sender_id, "أهلاً بك يا مدير. كيف أقدر أساعدك اليوم؟")
    else:
        add_log('SECURITY', f'⚠️ محاولة دخول فاشلة من {sender_id[:10]}...')
        send_message(sender_id, "❌ الرقم السري خطأ.")

# ========== معالجة رسالة العميل العادي ==========
def process_client_message(sender_id, text, client):
    """معالجة رسائل العملاء العاديين"""
    
    # استخراج المعلومات (نفس الكود السابق)
    if not client.name:
        name_match = re.search(r'اسمي[:\s]*([\w\s]{2,20})|my name is[:\s]*([\w\s]{2,20})', text, re.IGNORECASE)
        if name_match:
            client.name = (name_match.group(1) or name_match.group(2) or "").strip()
            add_log('EXTRACT', f'✅ الاسم: {client.name}')
    
    service_keywords = {
        'شعار': 'تصميم شعار', 'logo': 'تصميم شعار',
        'موقع': 'تصميم مواقع', 'website': 'تصميم مواقع',
        'تطبيق': 'تطبيق جوال', 'app': 'تطبيق جوال',
        'بوت': 'بوت ذكاء اصطناعي', 'bot': 'بوت ذكاء اصطناعي',
    }
    if not client.service:
        for kw, service in service_keywords.items():
            if kw in text.lower():
                client.service = service
                add_log('EXTRACT', f'✅ الخدمة: {client.service}')
                break
    
    if not client.budget:
        budget_match = re.search(r'(\d+)[\s-]*(usdt|دولار|\$)', text, re.IGNORECASE)
        if budget_match:
            client.budget = f"{budget_match.group(1)} USDT"
            add_log('EXTRACT', f'✅ الميزانية: {client.budget}')
    
    if not client.phone:
        phone_match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9})', text)
        if phone_match:
            client.phone = phone_match.group(1)
            add_log('EXTRACT', f'✅ الجوال: {client.phone}')
    
    # إذا اكتملت البيانات
    if client.is_complete() and not client.confirmed:
        wallet_msg = f"✅ تم تأكيد طلبك! سنقوم بتجهيز المحفظة للدفع.\n🔹 معرف بينانس: {BINANCE_ID}"
        send_message(sender_id, wallet_msg)
        send_order_to_owner(client)
        client.confirmed = True
        return
    
    # رد عادي
    response = get_ai_response(text, client, is_owner_mode=False)
    send_message(sender_id, response)
    client.conversation.append(f"Client: {text}")
    client.conversation.append(f"Agent: {response[:50]}...")

# ========== المعالجة الرئيسية ==========
def process_message(sender_id, text):
    add_log('RECEIVE', f'📨 رسالة من {sender_id[:10]}...: {text[:50]}')
    stats['messages_received'] += 1
    
    # تحقق الحظر
    if sender_id in blocked_users:
        add_log('BLOCKED', f'🚫 مستخدم محظور')
        return
    
    # إنشاء جلسة
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
    
    client = sessions[sender_id]
    
    # إذا كان في مرحلة إدخال كلمة المرور
    if client.awaiting_password:
        handle_password_attempt(text, sender_id, client)
        return
    
    # إذا كان مديراً
    if is_owner(sender_id):
        process_owner_message(sender_id, text, client)
        return
    
    # كشف محاولات انتحال شخصية المدير
    owner_keywords = ['مدير', 'owner', 'المالك', 'boss', 'admin', 'ياسين', 'المسؤول']
    if any(kw in text.lower() for kw in owner_keywords):
        client.awaiting_password = True
        send_message(sender_id, "🔐 إذا كنت المدير، الرجاء إدخال الرقم السري:")
        return
    
    # معالجة كعميل عادي
    process_client_message(sender_id, text, client)

# ========== Keep alive ==========
def keep_alive():
    while True:
        try:
            time.sleep(600)
            requests.get("https://by-pro-marketing-agent.onrender.com", timeout=5)
            add_log('ALIVE', '💓 Keep-alive ping')
        except:
            pass

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge
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
        <title>B.Y PRO - البوت الذكي</title>
        <style>
            * { font-family: 'Segoe UI', Tahoma, sans-serif; }
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: white; border-radius: 15px; padding: 30px; margin-bottom: 20px; }
            h1 { color: #333; }
            .status { background: #4ade80; color: #166534; padding: 8px 20px; border-radius: 25px; display: inline-block; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .card { background: white; border-radius: 15px; padding: 20px; }
            .card .value { font-size: 2.5em; font-weight: bold; color: #667eea; }
            .logs { background: white; border-radius: 15px; padding: 20px; max-height: 200px; overflow-y: auto; }
        </style>
    </head>
    <body>
        <div class='container'>
            <div class='header'>
                <h1>🤖 B.Y PRO - البوت الذكي</h1>
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
        </div>
        <script>setTimeout(()=>location.reload(), 10000);</script>
    </body>
    </html>
    """
    
    return render_template_string(
        html,
        total_clients=len(sessions),
        orders_count=len(orders),
        blocked_count=len(blocked_users),
        verified_count=len(verified_users),
        start_time=stats['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        logs=list(logs)[:20]
    )

# ========== التشغيل ==========
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 B.Y PRO - البوت الذكي بالمحادثة الطبيعية")
    print("="*60)
    print(f"👤 معرف المدير: {OWNER_FB_IDS[0]}")
    print(f"🔐 كلمة المرور: {OWNER_PASSWORD}")
    print("="*60 + "\n")
    
    check_token()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
