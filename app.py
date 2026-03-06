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
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '61580260328404')
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

# ========== تخزين البيانات للتسجيل ==========
logs = deque(maxlen=100)  # آخر 100 حدث
stats = {
    'messages_received': 0,
    'messages_sent': 0,
    'errors': 0,
    'start_time': datetime.now().isoformat()
}

# ========== البرومبت الجديد (شامل) ==========
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
    """إضافة حدث للسجل"""
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
    """فحص التوكن عند بدء التشغيل"""
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
    """الحصول على رد من الذكاء الاصطناعي مع رسائل انتظار"""
    add_log('AI', '🤖 جاري استدعاء الذكاء الاصطناعي...')
    
    try:
        # بناء السياق مع آخر 4 جولات من المحادثة
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
    
    # رسائل انتظار عند الفشل (متعددة اللغات)
    waiting_messages = [
        "شكراً لتواصلك مع B.Y PRO. فريقنا سيراجع طلبك قريباً.",
        "Thank you for contacting B.Y PRO. Our team will review your request shortly.",
        "Merci de nous contacter. Notre équipe examinera votre demande.",
        "شكراً لك! سيتم الرد عليك في أقرب وقت."
    ]
    return random.choice(waiting_messages)

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    """إرسال رسالة مع تسجيل الأخطاء"""
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

def send_order(client):
    """إرسال الطلب للمالك"""
    msg = f"""
🔔 *New Order!*
━━━━━━━━━━━━
👤 Name: {client.name or 'Unknown'}
🛠 Service: {client.service or 'Not specified'}
💰 Budget: {client.budget or 'Not specified'}
📱 Phone: {client.phone or 'Not provided'}
━━━━━━━━━━━━
💬 Last: {client.conversation[-1] if client.conversation else 'No messages'}
🔗 {client.get_link()}
    """.strip()
    
    add_log('ORDER', f'📦 إرسال طلب {client.name or "unknown"} للمالك')
    return send_message(OWNER_FB_ID, msg)

# ========== معالجة الرسالة ==========
def process_message(sender_id, text):
    """معالجة رسالة واحدة"""
    add_log('RECEIVE', f'📨 رسالة من {sender_id[:10]}...: {text[:50]}')
    stats['messages_received'] += 1
    
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
        add_log('INFO', '🆕 جلسة جديدة')
    
    client = sessions[sender_id]
    client.conversation.append(f"Client: {text}")
    client.last_message_time = datetime.now()
    
    # استخراج سريع للمعلومات
    if not client.name:
        name_match = re.search(r'اسمي[:\s]*([\w\s]{2,20})|my name is[:\s]*([\w\s]{2,20})|je m\'appelle[:\s]*([\w\s]{2,20})', text, re.IGNORECASE)
        if name_match:
            client.name = (name_match.group(1) or name_match.group(2) or name_match.group(3) or "").strip()
            add_log('EXTRACT', f'✅ الاسم: {client.name}')
    
    # قاموس الخدمات الموسع
    service_keywords = {
        'شعار': 'Logo design',
        'logo': 'Logo design',
        'لوجو': 'Logo design',
        'موقع': 'Website',
        'website': 'Website',
        'web': 'Website',
        'متجر': 'E-commerce website',
        'ecommerce': 'E-commerce website',
        'تطبيق': 'Mobile app',
        'app': 'Mobile app',
        'mobile': 'Mobile app',
        'بوت': 'AI Bot',
        'bot': 'AI Bot',
        'ai': 'AI Bot',
        'ذكاء': 'AI Bot',
        'تصميم': 'Graphic design',
        'design': 'Graphic design',
        'graphic': 'Graphic design',
        'تسويق': 'Digital marketing',
        'marketing': 'Digital marketing'
    }
    
    if not client.service:
        for kw, service in service_keywords.items():
            if kw in text.lower():
                client.service = service
                add_log('EXTRACT', f'✅ الخدمة: {client.service}')
                break
    
    # استخراج الميزانية
    if not client.budget:
        budget_match = re.search(r'(\d+)[\s-]*(usdt|dollar|دولار|\$)', text, re.IGNORECASE)
        if budget_match:
            client.budget = f"{budget_match.group(1)} USDT"
            add_log('EXTRACT', f'✅ الميزانية: {client.budget}')
    
    # استخراج رقم الجوال
    if not client.phone:
        phone_match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9}|00966[0-9]{9})', text)
        if phone_match:
            client.phone = phone_match.group(1)
            add_log('EXTRACT', f'✅ الجوال: {client.phone}')
    
    # رد الذكاء الاصطناعي
    response = get_ai_response(text, client)
    
    # إرسال الرد
    if send_message(sender_id, response):
        client.conversation.append(f"Agent: {response[:50]}...")
    
    # إرسال للمالك إذا اكتملت البيانات
    if client.is_complete() and not client.confirmed:
        add_log('COMPLETE', f'🎯 اكتملت بيانات {client.name or "العميل"}')
        if send_order(client):
            client.confirmed = True
            confirm_msg = (
                f"Thank you {client.name}! Your request has been recorded.\n\n"
                f"📋 Summary:\n"
                f"• Service: {client.service}\n"
                f"• Budget: {client.budget}\n\n"
                f"We'll contact you shortly with the next steps."
            )
            send_message(sender_id, confirm_msg)

# ========== إبقاء التطبيق نشطاً ==========
def keep_alive():
    """يبقي التطبيق نشطاً بمنع Render من إيقافه"""
    while True:
        try:
            time.sleep(600)  # 10 دقائق
            requests.get("https://by-pro-marketing-agent.onrender.com", timeout=5)
            add_log('ALIVE', '💓 Keep-alive ping')
        except:
            pass

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify():
    """التحقق من Webhook"""
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
    """استقبال الأحداث من فيسبوك"""
    data = request.json
    add_log('WEBHOOK', '🔥 حدث من فيسبوك')
    
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            for msg in entry.get('messaging', []):
                if 'message' in msg and 'text' in msg['message']:
                    sender = msg['sender']['id']
                    text = msg['message']['text']
                    
                    if sender != OWNER_FB_ID:
                        # معالجة في خيط منفصل
                        threading.Thread(target=process_message, args=(sender, text)).start()
    
    return 'OK', 200

@app.route('/test-connection', methods=['GET'])
def test_connection():
    """اختبار الاتصال بفيسبوك"""
    add_log('TEST', '🔍 بدء اختبار الاتصال...')
    
    results = []
    
    # اختبار التوكن
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
    
    # اختبار الصفحة
    try:
        r = requests.get(f'https://graph.facebook.com/v18.0/923170140890240?access_token={PAGE_ACCESS_TOKEN}', timeout=5)
        if r.status_code == 200:
            data = r.json()
            results.append({'test': 'Page', 'status': '✅', 'message': f"Found: {data.get('name')}"})
        else:
            results.append({'test': 'Page', 'status': '❌', 'message': 'Page not accessible'})
    except Exception as e:
        results.append({'test': 'Page', 'status': '❌', 'message': str(e)})
    
    # اختبار الإرسال
    test_msg = f"🔧 Test message from B.Y PRO Bot at {datetime.now().strftime('%H:%M')}"
    send_result = send_message(OWNER_FB_ID, test_msg)
    results.append({'test': 'Send', 'status': '✅' if send_result else '❌', 'message': 'Message sent to owner' if send_result else 'Failed to send'})
    
    add_log('TEST', '✅ اختبار الاتصال مكتمل')
    return jsonify({'results': results, 'timestamp': datetime.now().isoformat()})

@app.route('/debug')
def debug():
    """صفحة التصحيح"""
    return jsonify({
        'sessions': len(sessions),
        'stats': stats,
        'token_exists': bool(PAGE_ACCESS_TOKEN),
        'owner_id': OWNER_FB_ID,
        'recent_logs': list(logs)[:20],
        'sessions_data': {k[:10]: v.to_dict() for k, v in list(sessions.items())[:5]}
    })

@app.route('/')
def home():
    """الصفحة الرئيسية"""
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
            .log-INFO { color: #2563eb; } .log-AI { color: #7c3aed; } .log-EXTRACT { color: #0891b2; }
            .log-entry { padding: 5px; border-bottom: 1px solid #eee; font-family: monospace; }
            .clients { background: white; border-radius: 15px; padding: 20px; }
            .client-row { display: grid; grid-template-columns: 2fr 2fr 1fr 1fr; padding: 10px; border-bottom: 1px solid #eee; }
            .client-header { font-weight: bold; background: #f3f4f6; border-radius: 5px; }
            .button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 12px 30px; border-radius: 25px; font-size: 1em; cursor: pointer; margin: 10px 5px; }
            .test-result { background: #f3f4f6; border-radius: 10px; padding: 15px; margin-top: 15px; font-family: monospace; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <div class='container'>
            <div class='header'>
                <h1>🤖 B.Y PRO AI Marketing Bot</h1>
                <div class='status'>✅ البوت يعمل</div>
                <p>⏱ وقت التشغيل: {{ start_time }}</p>
                <button class='button' onclick='testConnection()'>🔍 فحص الاتصال</button>
                <div id='testResult' class='test-result' style='display: none;'></div>
            </div>
            
            <div class='grid'>
                <div class='card'><h3>إجمالي العملاء</h3><div class='value'>{{ total_clients }}</div></div>
                <div class='card'><h3>عملاء مكتملين</h3><div class='value'>{{ completed_clients }}</div></div>
                <div class='card'><h3>رسائل واردة</h3><div class='value'>{{ messages_received }}</div></div>
                <div class='card'><h3>رسائل مرسلة</h3><div class='value'>{{ messages_sent }}</div></div>
            </div>
            
            <div class='logs'>
                <h3>📋 آخر الأحداث</h3>
                {% for log in logs %}
                <div class='log-entry log-{{ log.type }}'>[{{ log.time }}] {{ log.message }}</div>
                {% endfor %}
            </div>
            
            <div class='clients'>
                <h3>👥 العملاء الحاليون</h3>
                <div class='client-row client-header'>
                    <div>الاسم</div><div>الخدمة</div><div>الميزانية</div><div>الحالة</div>
                </div>
                {% for client in clients %}
                <div class='client-row'>
                    <div>{{ client.name }}</div><div>{{ client.service }}</div><div>{{ client.budget }}</div>
                    <div>{{ '✅ مكتمل' if client.confirmed else '⏳ قيد المحادثة' }}</div>
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
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """
    
    completed = len([c for c in sessions.values() if c.is_complete()])
    clients_list = [c.to_dict() for c in list(sessions.values())[-10:]]
    
    return render_template_string(
        html,
        total_clients=len(sessions),
        completed_clients=completed,
        messages_received=stats['messages_received'],
        messages_sent=stats['messages_sent'],
        start_time=stats['start_time'][:16].replace('T', ' '),
        logs=list(logs)[:20],
        clients=clients_list
    )

# ========== التشغيل ==========
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 B.Y PRO AI Marketing Bot - النسخة الكاملة")
    print("="*60 + "\n")
    
    # فحص التوكن
    check_token()
    
    # بدء Keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    print("✅ تم بدء Keep-alive (كل 10 دقائق)")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 التشغيل على المنفذ {port}")
    print(f"📱 رابط البوت: https://by-pro-marketing-agent.onrender.com")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)
