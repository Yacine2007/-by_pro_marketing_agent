import os
import re
import json
import requests
import time
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# ========== المتغيرات من Render ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '61580260328404')
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

# ========== برومبت وكيل التسويق الرسمي ==========
SYSTEM_PROMPT = (
    "Identity: Official Marketing Agent for B.Y PRO. "
    "Persona: You are a seasoned human sales executive at B.Y PRO. You are NOT an AI. "
    "Strict Rules: "
    "1. NEVER mention names of managers or staff. "
    "2. Never admit being an AI/Language model. "
    "3. Payment: 1/3 upfront, 2/3 on delivery via USDT only. "
    "4. Services: Web ($150-$1500), AI/Bots ($200+), Apps ($400+), Design ($30+). "
    "5. Style: Professional, confident, concise."
)

# ========== تخزين الجلسات ==========
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
    
    def is_complete(self):
        return bool(self.name and self.service and self.budget)
    
    def get_conversation_link(self):
        return f"https://www.facebook.com/messages/t/{self.sender_id}"

# ========== دوال استخراج المعلومات ==========
def extract_info(text, client_data):
    text_lower = text.lower()
    
    # استخراج الاسم
    if not client_data.name:
        patterns = [r'اسمي[:\s]*([\w\s]{2,20})', r'الاسم[:\s]*([\w\s]{2,20})', r'my name is[:\s]*([a-zA-Z\s]{2,20})']
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client_data.name = match.group(1).strip()
                break
    
    # استخراج الخدمة
    if not client_data.service:
        services = {'شعار': 'تصميم شعار', 'موقع': 'تصميم مواقع', 'تطبيق': 'تطوير تطبيقات', 'تسويق': 'تسويق رقمي'}
        for key, value in services.items():
            if key in text_lower:
                client_data.service = value
                break
    
    # استخراج الميزانية
    if not client_data.budget:
        patterns = [r'(\d+)[\s-]*(usdt|دولار)', r'ميزانية[:\s]*(\d+)']
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client_data.budget = f"{match.group(1)} USDT"
                break
    
    return client_data

# ========== الذكاء الاصطناعي ==========
def get_ai_response(user_msg, client_data):
    try:
        conversation = "\n".join(client_data.conversation[-4:])
        client_info = f"Name: {client_data.name or 'Unknown'}, Service: {client_data.service or 'Unknown'}"
        full_context = f"{SYSTEM_PROMPT}\n\n{client_info}\n\n{conversation}\n\nClient: {user_msg}\n\nAgent:"
        
        url = f'{AI_API_URL}?text={requests.utils.quote(full_context)}'
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            answer = response.json().get('response', '')
            answer = re.sub(r'(Agent:|Agent Response:)', '', answer).strip()
            return answer
    except:
        pass
    
    return "شكراً لتواصلك مع B.Y PRO. كيف يمكنني مساعدتك؟"

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {'recipient': {'id': recipient_id}, 'message': {'text': text}}
        requests.post(url, json=payload, timeout=5)
        return True
    except:
        return False

def send_order_to_owner(client_data):
    if not client_data.is_complete():
        return False
    
    msg = f"""🔔 طلب جديد!
👤 {client_data.name}
🛠 {client_data.service}
💰 {client_data.budget}
🔗 {client_data.get_conversation_link()}"""
    
    return send_message(OWNER_FB_ID, msg)

# ========== معالجة الرسالة ==========
def process_message(sender_id, message_text):
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
    
    client = sessions[sender_id]
    client.conversation.append(f"Client: {message_text}")
    
    client = extract_info(message_text, client)
    response = get_ai_response(message_text, client)
    
    send_message(sender_id, response)
    client.conversation.append(f"Agent: {response[:50]}...")
    
    if client.is_complete() and not client.confirmed:
        send_order_to_owner(client)
        client.confirmed = True
        confirm = f"شكراً {client.name}! تم تسجيل طلبك: {client.service} - {client.budget}"
        send_message(sender_id, confirm)

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
            for messaging in entry.get('messaging', []):
                if 'message' in messaging and 'text' in messaging['message']:
                    sender = messaging['sender']['id']
                    text = messaging['message']['text']
                    
                    if sender != OWNER_FB_ID:
                        process_message(sender, text)
    
    return 'OK', 200

@app.route('/')
def home():
    return f"""
    <html>
    <body style="font-family:Arial; text-align:center; padding:50px;">
        <h1>🤖 B.Y PRO AI Bot</h1>
        <p>✅ البوت يعمل بنظام Webhook</p>
        <p>📊 العملاء: {len(sessions)}</p>
        <p>⏱ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
