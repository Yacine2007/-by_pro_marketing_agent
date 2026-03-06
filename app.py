import os
import re
import json
import requests
import time
import threading
from flask import Flask, request
from datetime import datetime, timedelta

app = Flask(__name__)

# ========== المتغيرات من Render ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '61580260328404')
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

# ========== برومبت وكيل التسويق ==========
SYSTEM_PROMPT = (
    "Identity: Official Marketing Agent for B.Y PRO. "
    "Persona: You are a seasoned human sales executive at B.Y PRO. You are NOT an AI. "
    "Strict Rules: 1. NEVER mention names of managers or staff. "
    "2. Never admit being an AI/Language model. 3. Payment: 1/3 upfront, 2/3 on delivery via USDT only. "
    "4. Services: Web ($150-$1500), AI/Bots ($200+), Apps ($400+), Design ($30+). "
    "5. Style: Professional, confident, concise."
)

# ========== تخزين الجلسات ==========
sessions = {}
last_message_timestamp = {}  # تخزين آخر وقت رسالة لكل مستخدم

class Session:
    def __init__(self):
        self.memory = []
        self.lead = {'name': '', 'service': '', 'budget': '', 'phone': ''}
    
    def add_message(self, role, text):
        self.memory.append(f"{role}: {text}")
        if len(self.memory) > 10:  # نحتفظ بآخر 10 رسائل فقط
            self.memory = self.memory[-10:]

# ========== دوال الذكاء الاصطناعي ==========
def get_ai_response(user_msg, session):
    """الحصول على رد من الذكاء الاصطناعي"""
    try:
        full_context = f"{SYSTEM_PROMPT}\n\nRecent context:\n" + "\n".join(session.memory[-4:]) + f"\n\nClient: {user_msg}\n\nAgent Response:"
        url = f'{AI_API_URL}?text={requests.utils.quote(full_context)}'
        response = requests.get(url, timeout=10)
        res = response.json()
        answer = res.get('response', 'نعتذر، هناك ضغط على خوادم الشركة حالياً.')
        answer = answer.strip()
        if "Agent Response:" in answer:
            answer = answer.split("Agent Response:")[-1].strip()
        return answer
    except:
        return "شكراً لتواصلك مع B.Y PRO. كيف يمكنني مساعدتك؟"

# ========== دوال فيسبوك ==========
def get_page_conversations():
    """جلب كل المحادثات النشطة للصفحة"""
    try:
        url = f'https://graph.facebook.com/v18.0/me/conversations?access_token={PAGE_ACCESS_TOKEN}&fields=messages.limit(1){{message,from,created_time}}'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', [])
    except:
        pass
    return []

def get_messages_from_conversation(conversation_id):
    """جلب كل الرسائل من محادثة محددة"""
    try:
        url = f'https://graph.facebook.com/v18.0/{conversation_id}/messages?access_token={PAGE_ACCESS_TOKEN}&fields=message,from,created_time'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', [])
    except:
        pass
    return []

def send_message(recipient_id, text):
    """إرسال رسالة عبر فيسبوك"""
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        requests.post(url, json=payload, timeout=5)
        print(f"✅ تم إرسال رد إلى {recipient_id[:10]}...")
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")

def notify_owner(customer_id, lead_info):
    """إرسال إشعار للمالك"""
    if customer_id == OWNER_FB_ID:
        return
    
    name = lead_info.get('name', 'غير معروف')
    service = lead_info.get('service', 'غير محدد')
    budget = lead_info.get('budget', 'غير محدد')
    
    msg = f"""🔔 عميل جديد مؤهل!
👤 الاسم: {name}
🛠 الخدمة: {service}
💰 الميزانية: {budget}
💬 للرد: https://www.facebook.com/messages/t/{customer_id}"""
    
    send_message(OWNER_FB_ID, msg)

# ========== دالة Polling (تعمل في الخلفية) ==========
def polling_worker():
    """تعمل كل 5 ثوان وتجلب الرسائل الجديدة"""
    print("🚀 بدء Polling Worker...")
    processed_messages = set()  # تخزين IDs الرسائل التي تمت معالجتها
    
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔄 Polling: جلب المحادثات...")
            
            # جلب كل المحادثات
            conversations = get_page_conversations()
            
            for conv in conversations:
                conv_id = conv.get('id')
                if not conv_id:
                    continue
                
                # جلب آخر رسالة في المحادثة
                messages = get_messages_from_conversation(conv_id)
                
                for msg in messages:
                    msg_id = msg.get('id')
                    
                    # نتأكد أننا لم نعالج هذه الرسالة من قبل
                    if msg_id in processed_messages:
                        continue
                    
                    # نأخذ المعلومات
                    message_text = msg.get('message', '')
                    from_data = msg.get('from', {})
                    sender_id = from_data.get('id', '')
                    
                    # نتأكد أن المرسل ليس الصفحة نفسها
                    if sender_id and sender_id != '923170140890240' and sender_id != OWNER_FB_ID:
                        print(f"📩 رسالة جديدة من {sender_id[:10]}...: {message_text[:50]}")
                        
                        # إضافة للـ set
                        processed_messages.add(msg_id)
                        
                        # إنشاء جلسة للمستخدم
                        if sender_id not in sessions:
                            sessions[sender_id] = Session()
                        
                        session = sessions[sender_id]
                        
                        # إضافة للذاكرة
                        session.add_message("Client", message_text)
                        
                        # الحصول على رد الذكاء
                        response = get_ai_response(message_text, session)
                        
                        # إضافة الرد للذاكرة
                        session.add_message("Agent", response)
                        
                        # إرسال الرد
                        send_message(sender_id, response)
                        
                        # التحقق من معلومات العميل
                        name = session.lead.get('name')
                        service = session.lead.get('service')
                        if name and service:
                            notify_owner(sender_id, session.lead)
            
            # نحد من حجم processed_messages
            if len(processed_messages) > 1000:
                processed_messages = set(list(processed_messages)[-500:])
            
            # ننتظر 5 ثوان قبل الجلب التالي
            time.sleep(5)
            
        except Exception as e:
            print(f"❌ خطأ في Polling: {e}")
            time.sleep(10)  # ننتظر أطول إذا حصل خطأ

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """التحقق من Webhook - نحتفظ به للتوافق"""
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    """نتركه فارغاً - نعتمد على Polling"""
    return 'OK', 200

@app.route('/')
def home():
    """الصفحة الرئيسية"""
    active = len([s for s in sessions if (datetime.now() - datetime.now()).seconds < 3600])
    return f"""
    <html dir='rtl'>
    <head><title>B.Y PRO Bot</title>
    <style>
        body {{ font-family: Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; padding: 50px; }}
        .card {{ background: rgba(255,255,255,0.1); border-radius: 20px; padding: 30px; margin: 20px; }}
        .status {{ color: #4ade80; font-size: 24px; }}
        .polling {{ background: #ffd700; color: black; padding: 10px; border-radius: 10px; }}
    </style>
    </head>
    <body>
        <div class='card'>
            <h1>🤖 B.Y PRO Bot (Polling Mode)</h1>
            <p class='status'>✅ البوت يعمل بنظام Polling</p>
            <div class='polling'>
                🔄 Polling يعمل كل 5 ثوان
            </div>
            <p>📊 الجلسات النشطة: {len(sessions)}</p>
            <p>⏱ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </body>
    </html>
    """

@app.route('/debug')
def debug():
    """صفحة التصحيح"""
    return {
        'active_sessions': len(sessions),
        'processed_messages': len(processed_messages) if 'processed_messages' in dir() else 0,
        'sessions': {k[:10]: v.lead for k, v in sessions.items()}
    }

# ========== تشغيل Polling و Flask ==========
if __name__ == '__main__':
    # بدء Polling في خيط منفصل
    polling_thread = threading.Thread(target=polling_worker, daemon=True)
    polling_thread.start()
    print("✅ تم بدء Polling Thread")
    
    # تشغيل Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
