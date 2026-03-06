import os
import re
import json
import requests
import time
import threading
import sys
import random
from flask import Flask, request, jsonify, render_template_string, session
from datetime import datetime
from collections import deque

app = Flask(__name__)
app.secret_key = os.urandom(24)  # مطلوب للجلسات

# ========== المتغيرات ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
# معرف المدير - أضف كل المعرفات الموثقة هنا (الشخصية والصفحة)
OWNER_FB_IDS = ['2592319994', '61580260328404']  # المعرف الشخصي أولاً ثم معرف الصفحة
# كلمة مرور المدير للتحقق الإضافي
OWNER_PASSWORD = "20070909"
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

# بينانس ID للدفع
BINANCE_ID = "1074084246"

# ========== تخزين البيانات ==========
logs = deque(maxlen=100)
stats = {
    'messages_received': 0,
    'messages_sent': 0,
    'errors': 0,
    'start_time': datetime.now().isoformat()
}

# ملفات التخزين الدائم
ORDERS_FILE = "orders.json"
BLOCKED_FILE = "blocked_users.json"
VERIFIED_USERS_FILE = "verified_users.json"  # المستخدمون الذين تحققوا بكلمة المرور

# ========== تحميل/حفظ البيانات ==========
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

# البيانات المحملة
orders = load_orders()
blocked_users = load_blocked()
verified_users = load_verified()  # مستخدمون تحققوا بكلمة المرور

# ========== البرومبت ==========
SYSTEM_PROMPT = (
    "You are the official sales agent of B.Y PRO, a technology and software company. "
    "You are a seasoned human sales executive: calm, confident, and concise. Do not act like a machine, avoid excessive emojis, and never use repetitive greetings.\n\n"
    "Core communication principles:\n"
    "1. Smart brevity: Answer precisely and only what the client asks. Respect their time and yours. Do not explain technical basics unless requested.\n"
    "2. Language adaptation: Immediately respond in the same language the client uses (Arabic, English, French, etc.). Use clean, professional language.\n"
    "3. No pushiness: If you present an offer and the client doesn't reply, do not chase them. We are a company sought by elite clients; B.Y PRO's train doesn't wait for anyone.\n"
    "4. Absolute confidentiality: Never mention the director's name (Mr. Yassine), employee count, member names, or details about country agents. If asked about headquarters, say: 'We are an international digital entity with operations in North Africa (Algeria) and a carefully planned global presence.'\n\n"
    "Services and average prices (market 2026):\n"
    "- Portfolio/Business websites: $300 – $800 (5-10 days)\n"
    "- E-commerce websites: $700 – $1800 (15-25 days)\n"
    "- Automation systems & AI bots: from $300 (7-14 days)\n"
    "- Mobile apps (Android/iOS): from $1500 (30-60 days)\n"
    "- Graphic design & professional editing: $50 – $200 (24-72 hours)\n\n"
    "Financial protocol:\n"
    "- Fixed rule: 30% upfront deposit to start work, 70% upon final delivery.\n"
    "- Payment method: USDT (Binance Pay) exclusively for fast international transactions.\n"
    "- Negotiation: If the client tries to excessively lower the price, politely say: 'Our prices reflect the quality standards and strict deadline commitment at B.Y PRO; we currently cannot offer additional discounts.'\n\n"
    "Ultimate goal: Convert inquiries into confirmed projects and send payment details only to serious clients."
)

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
        self.awaiting_password = False  # هل المستخدم في مرحلة إدخال كلمة المرور
    
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

# ========== فحص التوكن ==========
def check_token():
    add_log('INFO', '🔍 جاري فحص التوكن...')
    if not PAGE_ACCESS_TOKEN:
        add_log('ERROR', '❌ PAGE_ACCESS_TOKEN غير موجود!')
        return False
    try:
        url = f'https://graph.facebook.com/v18.0/me?access_token={PAGE_ACCESS_TOKEN}'
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            add_log('SUCCESS', f'✅ التوكن صالح للحساب: {data.get("name")}')
            return True
        else:
            error = r.json().get('error', {})
            add_log('ERROR', f'❌ التوكن غير صالح: {error.get("message")}')
            return False
    except Exception as e:
        add_log('ERROR', f'❌ خطأ في فحص التوكن: {e}')
        return False

# ========== الذكاء الاصطناعي ==========
def get_ai_response(user_msg, client):
    add_log('AI', '🤖 جاري استدعاء الذكاء الاصطناعي...')
    try:
        context = f"{SYSTEM_PROMPT}\n" + "\n".join(client.conversation[-4:]) + f"\nClient: {user_msg}\nAgent:"
        url = f'{AI_API_URL}?text={requests.utils.quote(context)}'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            answer = response.json().get('response', '')
            answer = re.sub(r'(Agent:|Agent Response:)', '', answer).strip()
            add_log('AI', '✅ تم الحصول على رد')
            return answer
        else:
            add_log('WARNING', f'⚠️ الذكاء الاصطناعي رد بـ {response.status_code}')
    except requests.exceptions.Timeout:
        add_log('WARNING', '⏱️ timeout في الذكاء الاصطناعي')
    except Exception as e:
        add_log('ERROR', f'❌ خطأ في الذكاء الاصطناعي: {e}')
    
    waiting_messages = [
        "شكراً لتواصلك مع B.Y PRO. فريقنا سيراجع طلبك قريباً.",
        "Thank you for contacting B.Y PRO. Our team will review your request shortly.",
        "Merci de nous contacter. Notre équipe examinera votre demande.",
        "شكراً لك! سيتم الرد عليك في أقرب وقت."
    ]
    return random.choice(waiting_messages)

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

# ========== حفظ الطلب في ملف JSON ==========
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
        details = "\n".join(client.conversation[-5:])  # آخر 5 رسائل كملخص
    order = save_order(client, details)
    
    msg = f"""🔔 *New Order Confirmed!*
━━━━━━━━━━━━━━━━━━━
📋 Order #{order['order_id']}
👤 Name: {client.name}
🛠 Service: {client.service}
💰 Budget: {client.budget}
📱 Phone: {client.phone or 'Not provided'}
━━━━━━━━━━━━━━━━━━━
📝 Details:
{details[:300]}{'...' if len(details)>300 else ''}
━━━━━━━━━━━━━━━━━━━
🔗 {client.get_link()}
    """.strip()
    
    add_log('OWNER', f'📦 إرسال الطلب #{order["order_id"]} للمدير')
    return send_message(OWNER_FB_IDS[0], msg)  # استخدم المعرف الرئيسي للإرسال

# ========== التحقق من المدير ==========
def is_owner(sender_id):
    """التحقق مما إذا كان المستخدم مديراً (معرف موثوق أو تحقق بكلمة المرور)"""
    return sender_id in OWNER_FB_IDS or sender_id in verified_users

# ========== معالجة أوامر المدير ==========
def handle_owner_command(text, sender_id):
    cmd = text.strip().lower()
    response = ""
    
    if cmd in ['تقارير', 'report', 'orders', 'الطلبات']:
        if not orders:
            response = "📭 لا توجد طلبات مؤكدة بعد."
        else:
            lines = ["📊 *تقرير الطلبات*"]
            for o in orders[-5:]:  # آخر 5
                lines.append(f"#{o['order_id']} - {o['client_name']} - {o['service']} - {o['budget']}")
            response = "\n".join(lines)
    
    elif cmd.startswith('حظر ') or cmd.startswith('block '):
        parts = cmd.split()
        if len(parts) >= 2:
            target = parts[1]
            blocked_users.add(target)
            save_blocked(blocked_users)
            response = f"✅ تم حظر المستخدم {target}"
    
    elif cmd.startswith('الغاء حظر ') or cmd.startswith('unblock '):
        parts = cmd.split()
        if len(parts) >= 2:
            target = parts[1]
            if target in blocked_users:
                blocked_users.remove(target)
                save_blocked(blocked_users)
                response = f"✅ تم إلغاء حظر {target}"
            else:
                response = f"❌ المستخدم {target} غير موجود في قائمة الحظر"
    
    elif cmd.startswith('تفاصيل ') or cmd.startswith('order '):
        parts = cmd.split()
        if len(parts) >= 2:
            try:
                oid = int(parts[1])
                order = next((o for o in orders if o['order_id'] == oid), None)
                if order:
                    response = f"📋 الطلب #{oid}\nالاسم: {order['client_name']}\nالخدمة: {order['service']}\nالميزانية: {order['budget']}\nالهاتف: {order.get('phone','')}\nالتفاصيل: {order['details'][:200]}..."
                else:
                    response = f"❌ لا يوجد طلب رقم {oid}"
            except:
                response = "❌ الرقم غير صحيح"
    
    elif cmd in ['احصائيات', 'stats']:
        response = f"📈 إحصائيات:\nالرسائل الواردة: {stats['messages_received']}\nالرسائل المرسلة: {stats['messages_sent']}\nالطلبات: {len(orders)}\nالمحظورين: {len(blocked_users)}\nالمستخدمين الموثوقين: {len(verified_users)}"
    
    elif cmd == 'مساعدة' or cmd == 'help':
        response = """🔹 أوامر المدير:
تقارير - عرض آخر الطلبات
حظر [معرف] - حظر مستخدم
الغاء حظر [معرف] - فك الحظر
تفاصيل [رقم] - تفاصيل طلب
احصائيات - إحصائيات عامة"""
    
    else:
        response = "👋 مرحباً بك يا مدير. أرسل 'مساعدة' لرؤية الأوامر."
    
    send_message(sender_id, response)
    return True

# ========== معالجة محاولة التحقق بالرقم السري ==========
def handle_password_attempt(text, sender_id, client):
    """معالجة محاولة إدخال الرقم السري"""
    if text.strip() == OWNER_PASSWORD:
        # كلمة المرور صحيحة
        verified_users.add(sender_id)
        save_verified(verified_users)
        client.awaiting_password = False
        add_log('SECURITY', f'🔐 تحقق ناجح بكلمة المرور للمستخدم {sender_id[:10]}...')
        send_message(sender_id, "✅ تم التحقق بنجاح! أنت الآن مخول كمدير. أرسل 'مساعدة' لرؤية الأوامر.")
    else:
        # كلمة المرور خاطئة
        add_log('SECURITY', f'⚠️ محاولة دخول فاشلة بكلمة مرور خاطئة من {sender_id[:10]}...')
        send_message(sender_id, "❌ كلمة المرور غير صحيحة. إذا كنت المدير، يرجى إدخال الرقم السري الصحيح، أو انتظر حتى يتم التحقق من هويتك.")

# ========== معالجة رسالة العميل ==========
def process_message(sender_id, text):
    add_log('RECEIVE', f'📨 رسالة من {sender_id[:10]}...: {text[:50]}')
    stats['messages_received'] += 1
    
    # 1. التحقق من الحظر
    if sender_id in blocked_users:
        add_log('BLOCKED', f'🚫 مستخدم محظور {sender_id[:10]}... تم تجاهل الرسالة')
        return
    
    # 2. إنشاء جلسة إذا لم تكن موجودة
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
        add_log('INFO', '🆕 جلسة جديدة')
    
    client = sessions[sender_id]
    client.conversation.append(f"Client: {text}")
    client.last_message_time = datetime.now()
    
    # 3. التحقق من المدير
    if is_owner(sender_id):
        # هذا مدير موثوق (معرف مسبق أو تحقق بكلمة المرور)
        handle_owner_command(text, sender_id)
        return
    
    # 4. إذا كان المستخدم في مرحلة إدخال كلمة المرور
    if client.awaiting_password:
        handle_password_attempt(text, sender_id, client)
        return
    
    # 5. التحقق مما إذا كان المستخدم يدعي أنه المدير
    owner_claims = [
        'انا المدير', 'أنا المدير', 'i am the owner', 'i'm the manager',
        'مديرك', 'المالك', 'الowner', 'انا مديرك', 'انا مالك الشركة'
    ]
    
    if any(claim in text.lower() for claim in owner_claims):
        # المستخدم يدعي أنه المدير - نطلب كلمة المرور
        client.awaiting_password = True
        add_log('SECURITY', f'🔐 طلب تحقق بهوية المدير من {sender_id[:10]}...')
        send_message(sender_id, "🔐 إذا كنت المدير، يرجى إدخال الرقم السري للمتابعة:")
        return
    
    # 6. معالجة العميل العادي (نفس الكود السابق)
    
    # استخراج المعلومات
    if not client.name:
        name_match = re.search(r'اسمي[:\s]*([\w\s]{2,20})|my name is[:\s]*([\w\s]{2,20})|je m\'appelle[:\s]*([\w\s]{2,20})', text, re.IGNORECASE)
        if name_match:
            client.name = (name_match.group(1) or name_match.group(2) or name_match.group(3) or "").strip()
            add_log('EXTRACT', f'✅ الاسم: {client.name}')
    
    service_keywords = {
        'شعار': 'Logo design', 'logo': 'Logo design', 'لوجو': 'Logo design',
        'موقع': 'Website', 'website': 'Website', 'web': 'Website',
        'متجر': 'E-commerce website', 'ecommerce': 'E-commerce website',
        'تطبيق': 'Mobile app', 'app': 'Mobile app', 'mobile': 'Mobile app',
        'بوت': 'AI Bot', 'bot': 'AI Bot', 'ai': 'AI Bot', 'ذكاء': 'AI Bot',
        'تصميم': 'Graphic design', 'design': 'Graphic design', 'graphic': 'Graphic design',
        'تسويق': 'Digital marketing', 'marketing': 'Digital marketing'
    }
    if not client.service:
        for kw, service in service_keywords.items():
            if kw in text.lower():
                client.service = service
                add_log('EXTRACT', f'✅ الخدمة: {client.service}')
                break
    
    if not client.budget:
        budget_match = re.search(r'(\d+)[\s-]*(usdt|dollar|دولار|\$)', text, re.IGNORECASE)
        if budget_match:
            client.budget = f"{budget_match.group(1)} USDT"
            add_log('EXTRACT', f'✅ الميزانية: {client.budget}')
    
    if not client.phone:
        phone_match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9}|00966[0-9]{9})', text)
        if phone_match:
            client.phone = phone_match.group(1)
            add_log('EXTRACT', f'✅ الجوال: {client.phone}')
    
    # إذا كان الطلب مكتملاً بالفعل (confirmed) نرسل رسالة ثابتة ولا نستخدم AI
    if client.confirmed:
        send_message(sender_id, "شكراً لك. سيتم التواصل معك بشأن طلبك قريباً.")
        return
    
    # التحقق مما إذا كان العميل قد أكمل البيانات (ولم يتم التأكيد بعد)
    if client.is_complete():
        wallet_msg = f"✅ تم تأكيد طلبك! سنقوم الآن بتجهيز المحفظة لاستقبال الدفع.\n🔹 معرف بينانس للدفع: `{BINANCE_ID}`\n🔹 يرجى إرسال المبلغ على هذا المعرف، وسيتم إعلامك فور استلام الدفع لبدء العمل."
        send_message(sender_id, wallet_msg)
        
        details = "\n".join(client.conversation[-10:])  # آخر 10 رسائل كوصف تفصيلي
        send_order_to_owner(client, details)
        
        client.confirmed = True
        return
    
    # إذا لم يكتمل الطلب، نستخدم الذكاء الاصطناعي
    response = get_ai_response(text, client)
    if send_message(sender_id, response):
        client.conversation.append(f"Agent: {response[:50]}...")

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
    add_log('VERIFY', f'🔐 تحقق: mode={mode}, token={token}')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        add_log('SUCCESS', '✅ تحقق ناجح')
        return challenge
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    add_log('WEBHOOK', '🔥 حدث من فيسبوك')
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            for msg in entry.get('messaging', []):
                if 'message' in msg and 'text' in msg['message']:
                    sender = msg['sender']['id']
                    text = msg['message']['text']
                    threading.Thread(target=process_message, args=(sender, text)).start()
    return 'OK', 200

@app.route('/test-connection', methods=['GET'])
def test_connection():
    add_log('TEST', '🔍 بدء اختبار الاتصال...')
    results = []
    if not PAGE_ACCESS_TOKEN:
        results.append({'test': 'Token', 'status': '❌', 'message': 'Token missing'})
    else:
        try:
            r = requests.get(f'https://graph.facebook.com/v18.0/me?access_token={PAGE_ACCESS_TOKEN}', timeout=5)
            if r.status_code == 200:
                data = r.json()
                results.append({'test': 'Token', 'status': '✅', 'message': f"Valid for {data.get('name')}"})
            else:
                error = r.json().get('error', {})
                results.append({'test': 'Token', 'status': '❌', 'message': error.get('message')})
        except Exception as e:
            results.append({'test': 'Token', 'status': '❌', 'message': str(e)})
    test_msg = f"🔧 Test message from B.Y PRO Bot at {datetime.now().strftime('%H:%M')}"
    send_result = send_message(OWNER_FB_IDS[0], test_msg)
    results.append({'test': 'Send', 'status': '✅' if send_result else '❌', 'message': 'Message sent to owner' if send_result else 'Failed to send'})
    add_log('TEST', '✅ اختبار الاتصال مكتمل')
    return jsonify({'results': results, 'timestamp': datetime.now().isoformat()})

@app.route('/block/<user_id>', methods=['POST'])
def block_user(user_id):
    blocked_users.add(user_id)
    save_blocked(blocked_users)
    add_log('BLOCK', f'🔨 تم حظر {user_id}')
    return jsonify({'status': 'blocked', 'user': user_id})

@app.route('/unblock/<user_id>', methods=['POST'])
def unblock_user(user_id):
    if user_id in blocked_users:
        blocked_users.remove(user_id)
        save_blocked(blocked_users)
        add_log('UNBLOCK', f'🔓 تم إلغاء حظر {user_id}')
    return jsonify({'status': 'unblocked', 'user': user_id})

@app.route('/debug')
def debug():
    return jsonify({
        'sessions': len(sessions),
        'stats': stats,
        'token_exists': bool(PAGE_ACCESS_TOKEN),
        'owner_ids': OWNER_FB_IDS,
        'verified_users': list(verified_users),
        'blocked': list(blocked_users),
        'orders_count': len(orders),
        'recent_logs': list(logs)[:20],
        'sessions_data': {k[:10]: v.to_dict() for k, v in list(sessions.items())[:5]}
    })

@app.route('/')
def home():
    html = """
    <!DOCTYPE html>
    <html dir='rtl' lang='ar'>
    <head>
        <meta charset='UTF-8'>
        <meta name='viewport' content='width=device-width, initial-scale=1.0'>
        <title>B.Y PRO AI Bot - Dashboard</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: white; border-radius: 15px; padding: 30px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
            h1 { color: #333; font-size: 2em; margin-bottom: 10px; }
            .status { display: inline-block; padding: 8px 20px; border-radius: 25px; font-weight: bold; margin: 10px 0; background: #4ade80; color: #166534; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .card { background: white; border-radius: 15px; padding: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            .card .value { font-size: 2.5em; font-weight: bold; color: #667eea; }
            .logs { background: white; border-radius: 15px; padding: 20px; margin-bottom: 20px; max-height: 300px; overflow-y: auto; }
            .log-SUCCESS { color: #059669; } .log-ERROR { color: #dc2626; } .log-WARNING { color: #d97706; }
            .log-INFO { color: #2563eb; } .log-AI { color: #7c3aed; } .log-EXTRACT { color: #0891b2; } .log-OWNER { color: #b45309; } .log-SECURITY { color: #8b5cf6; }
            .log-entry { padding: 5px; border-bottom: 1px solid #eee; font-family: monospace; }
            .clients, .blocked-section, .verified-section { background: white; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
            .client-row, .blocked-row, .verified-row { display: grid; grid-template-columns: 2fr 2fr 1fr 1fr auto; padding: 10px; border-bottom: 1px solid #eee; align-items: center; }
            .client-header { font-weight: bold; background: #f3f4f6; border-radius: 5px; }
            .button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 8px 15px; border-radius: 20px; font-size: 0.9em; cursor: pointer; margin: 2px; }
            .block-btn { background: #ef4444; }
            .unblock-btn { background: #10b981; }
            .test-result { background: #f3f4f6; border-radius: 10px; padding: 15px; margin-top: 15px; font-family: monospace; white-space: pre-wrap; }
            .password-info { background: #fef3c7; border-right: 4px solid #f59e0b; padding: 10px; margin: 10px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class='container'>
            <div class='header'>
                <h1>🤖 B.Y PRO AI Marketing Bot</h1>
                <div class='status'>✅ البوت يعمل</div>
                <p>⏱ وقت التشغيل: {{ start_time }}</p>
                <p>💰 بينانس ID: <code>{{ binance_id }}</code></p>
                <div class='password-info'>
                    <strong>🔐 نظام التحقق:</strong> أي مستخدم يدعي أنه المدير سيُطلب منه الرقم السري <code>20070909</code>
                </div>
                <button class='button' onclick='testConnection()'>🔍 فحص الاتصال</button>
                <div id='testResult' class='test-result' style='display: none;'></div>
            </div>
            
            <div class='grid'>
                <div class='card'><h3>إجمالي العملاء</h3><div class='value'>{{ total_clients }}</div></div>
                <div class='card'><h3>عملاء مكتملين</h3><div class='value'>{{ completed_clients }}</div></div>
                <div class='card'><h3>الطلبات المحفوظة</h3><div class='value'>{{ orders_count }}</div></div>
                <div class='card'><h3>المحظورين</h3><div class='value'>{{ blocked_count }}</div></div>
                <div class='card'><h3>موثوقين بكلمة مرور</h3><div class='value'>{{ verified_count }}</div></div>
            </div>
            
            <div class='logs'>
                <h3>📋 آخر الأحداث</h3>
                {% for log in logs %}
                <div class='log-entry log-{{ log.type }}'>[{{ log.time }}] {{ log.message }}</div>
                {% endfor %}
            </div>
            
            <div class='verified-section'>
                <h3>🔐 المستخدمون الموثوقون (تحققوا بكلمة المرور)</h3>
                <div class='client-row client-header'>
                    <div>معرف المستخدم</div><div></div><div></div><div></div><div></div>
                </div>
                {% for uid in verified %}
                <div class='verified-row'>
                    <div>{{ uid[:15] }}...</div><div></div><div></div><div></div><div>✅ موثوق</div>
                </div>
                {% endfor %}
                {% if not verified %}<p>لا يوجد مستخدمين موثوقين</p>{% endif %}
            </div>
            
            <div class='blocked-section'>
                <h3>🔨 المستخدمون المحظورون (توقف الـ AI)</h3>
                <div class='client-row client-header'>
                    <div>معرف المستخدم</div><div></div><div></div><div></div><div>إجراء</div>
                </div>
                {% for uid in blocked %}
                <div class='blocked-row'>
                    <div>{{ uid[:15] }}...</div><div></div><div></div><div></div>
                    <div><button class='button unblock-btn' onclick='unblockUser("{{ uid }}")'>إلغاء الحظر</button></div>
                </div>
                {% endfor %}
                {% if not blocked %}<p>لا يوجد محظورين</p>{% endif %}
            </div>
            
            <div class='clients'>
                <h3>👥 العملاء الحاليون</h3>
                <div class='client-row client-header'>
                    <div>الاسم</div><div>الخدمة</div><div>الميزانية</div><div>الحالة</div><div>إجراء</div>
                </div>
                {% for client in clients %}
                <div class='client-row'>
                    <div>{{ client.name }}</div><div>{{ client.service }}</div><div>{{ client.budget }}</div>
                    <div>{{ '✅ مكتمل' if client.confirmed else '⏳ قيد المحادثة' }}</div>
                    <div><button class='button block-btn' onclick='blockUser("{{ client.sender_id }}")'>حظر</button></div>
                </div>
                {% endfor %}
            </div>
        </div>
        
        <script>
            function testConnection() {
                const resultDiv = document.getElementById('testResult');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '⏳ جاري فحص الاتصال...';
                fetch('/test-connection')
                    .then(r => r.json())
                    .then(data => resultDiv.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>')
                    .catch(e => resultDiv.innerHTML = '❌ خطأ: ' + e);
            }
            function blockUser(uid) {
                if(confirm('حظر هذا المستخدم؟')) {
                    fetch('/block/' + uid, {method:'POST'}).then(()=>location.reload());
                }
            }
            function unblockUser(uid) {
                fetch('/unblock/' + uid, {method:'POST'}).then(()=>location.reload());
            }
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """
    
    completed = len([c for c in sessions.values() if c.is_complete()])
    clients_list = [{'sender_id':k, **v.to_dict()} for k, v in list(sessions.items())[-10:]]
    
    return render_template_string(
        html,
        total_clients=len(sessions),
        completed_clients=completed,
        orders_count=len(orders),
        blocked_count=len(blocked_users),
        verified_count=len(verified_users),
        blocked=list(blocked_users)[-20:],
        verified=list(verified_users)[-20:],
        messages_received=stats['messages_received'],
        messages_sent=stats['messages_sent'],
        start_time=stats['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        logs=list(logs)[:20],
        clients=clients_list
    )

# ========== التشغيل ==========
if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 B.Y PRO AI Marketing Bot - النسخة الكاملة مع التحقق بكلمة المرور")
    print("="*70 + "\n")
    print(f"👤 معرفات المدير الموثقة: {OWNER_FB_IDS}")
    print(f"🔐 كلمة مرور المدير: {OWNER_PASSWORD}")
    print("-"*70)
    
    check_token()
    threading.Thread(target=keep_alive, daemon=True).start()
    print("✅ تم بدء Keep-alive (كل 10 دقائق)")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 التشغيل على المنفذ {port}")
    print(f"📱 رابط البوت: https://by-pro-marketing-agent.onrender.com")
    print("="*70 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)
