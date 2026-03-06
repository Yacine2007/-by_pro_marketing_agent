import os
import re
import json
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# ========== المتغيرات من Render ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '61580260328404')

# ========== الذكاء الاصطناعي ==========
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

SYSTEM_PROMPT = """
Identity: Official Marketing Agent for B.Y PRO. 
Persona: You are a seasoned human sales executive at B.Y PRO. 
Rules: 
1. Never mention being an AI
2. Payment: 1/3 upfront, 2/3 on delivery via USDT
3. Services: Web ($150-$1500), AI/Bots ($200+), Apps ($400+), Design ($30+)
4. Be professional and concise
5. Respond in the same language as the client
"""

# ========== تخزين الجلسات ==========
sessions = {}

class Session:
    def __init__(self):
        self.memory = []
        self.lead = {'name': '', 'service': '', 'budget': ''}

# ========== دوال المساعدة ==========
def extract_info(text, session):
    """استخراج معلومات العميل"""
    text_lower = text.lower()
    
    # استخراج الاسم
    if not session.lead['name']:
        name_match = re.search(r'اسمي[:\s]*([\w\s]{2,20})|الاسم[:\s]*([\w\s]{2,20})', text)
        if name_match:
            session.lead['name'] = name_match.group(1) or name_match.group(2)
    
    # استخراج الخدمة
    services = {'شعار': 'تصميم شعار', 'موقع': 'تصميم مواقع', 'تطبيق': 'تطوير تطبيقات'}
    for key, value in services.items():
        if key in text_lower and not session.lead['service']:
            session.lead['service'] = value
    
    return session.lead

def get_ai_response(user_msg, session):
    """الحصول على رد من الذكاء الاصطناعي"""
    try:
        # بناء السياق
        context = f"{SYSTEM_PROMPT}\n"
        context += "\n".join(session.memory[-4:])
        context += f"\nClient: {user_msg}\nAgent:"
        
        # استدعاء API
        url = f'{AI_API_URL}?text={requests.utils.quote(context)}'
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            ai_response = data.get('response', '')
            
            # تنظيف الرد
            if "Agent:" in ai_response:
                ai_response = ai_response.split("Agent:")[-1].strip()
            
            return ai_response
    except:
        pass
    
    return "شكراً لتواصلك مع B.Y PRO. كيف يمكنني مساعدتك؟"

def send_message(recipient_id, text):
    """إرسال رسالة عبر فيسبوك"""
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text}
        }
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def notify_owner(customer_id, customer_name):
    """إرسال إشعار للمالك"""
    if customer_id != OWNER_FB_ID:  # لا نرسل للمالك إذا كان هو نفسه
        msg = f"🔔 عميل جديد!\n👤 {customer_name}\n💬 https://www.facebook.com/messages/t/{customer_id}"
        send_message(OWNER_FB_ID, msg)

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """التحقق من Webhook"""
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    """استقبال الرسائل"""
    data = request.json
    
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            for messaging in entry.get('messaging', []):
                if 'message' in messaging and 'text' in messaging['message']:
                    sender_id = messaging['sender']['id']
                    message_text = messaging['message']['text']
                    
                    # إنشاء جلسة جديدة إذا لم توجد
                    if sender_id not in sessions:
                        sessions[sender_id] = Session()
                        # إشعار للمالك بمستخدم جديد
                        notify_owner(sender_id, "مستخدم جديد")
                    
                    session = sessions[sender_id]
                    
                    # حفظ الرسالة
                    session.memory.append(f"Client: {message_text}")
                    
                    # استخراج المعلومات
                    extract_info(message_text, session)
                    
                    # الحصول على رد
                    response = get_ai_response(message_text, session)
                    
                    # حفظ الرد
                    session.memory.append(f"Agent: {response}")
                    
                    # إرسال الرد
                    send_message(sender_id, response)
                    
                    # إذا اكتملت المعلومات، أرسل إشعار
                    if session.lead['name'] and session.lead['service']:
                        notify_owner(sender_id, session.lead['name'])
    
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
    </style>
    </head>
    <body>
        <div class='card'>
            <h1>🤖 B.Y PRO Bot</h1>
            <p class='status'>✅ البوت يعمل على سيرفر Render</p>
            <p>📊 الجلسات النشطة: {len(sessions)}</p>
            <p>🌐 Webhook: /webhook</p>
            <p>⏱ {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        </div>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)