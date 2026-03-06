import os
import re
import json
import requests
import time
import threading
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# ========== المتغيرات ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '61580260328404')
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

SYSTEM_PROMPT = (
    "Identity: Official Marketing Agent for B.Y PRO. "
    "Persona: You are a seasoned human sales executive at B.Y PRO. You are NOT an AI. "
    "Payment: 1/3 upfront, 2/3 on delivery via USDT only. "
    "Services: Web ($150-$1500), AI/Bots ($200+), Apps ($400+), Design ($30+)."
)

# ========== الجلسات ==========
sessions = {}

class ClientData:
    def __init__(self, sender_id):
        self.sender_id = sender_id
        self.name = ""
        self.service = ""
        self.budget = ""
        self.confirmed = False
        self.conversation = []
    
    def is_complete(self):
        return bool(self.name and self.service and self.budget)
    
    def get_link(self):
        return f"https://www.facebook.com/messages/t/{self.sender_id}"

# ========== الذكاء الاصطناعي ==========
def get_ai_response(user_msg, client):
    try:
        context = f"{SYSTEM_PROMPT}\n" + "\n".join(client.conversation[-4:]) + f"\nClient: {user_msg}\nAgent:"
        url = f'{AI_API_URL}?text={requests.utils.quote(context)}'
        response = requests.get(url, timeout=10)
        return response.json().get('response', 'شكراً لتواصلك مع B.Y PRO')
    except:
        return "شكراً لتواصلك مع B.Y PRO"

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {'recipient': {'id': recipient_id}, 'message': {'text': text}}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def send_order(client):
    msg = f"🔔 طلب جديد!\n👤 {client.name}\n🛠 {client.service}\n💰 {client.budget}\n🔗 {client.get_link()}"
    send_message(OWNER_FB_ID, msg)

# ========== معالجة الرسالة ==========
def process_message(sender_id, text):
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
    
    client = sessions[sender_id]
    client.conversation.append(f"Client: {text}")
    
    # استخراج سريع للمعلومات
    if not client.name:
        match = re.search(r'اسمي[:\s]*([\w\s]{2,20})', text, re.IGNORECASE)
        if match:
            client.name = match.group(1).strip()
    
    services = {'شعار': 'تصميم شعار', 'موقع': 'تصميم مواقع', 'تطبيق': 'تطوير تطبيقات'}
    for k, v in services.items():
        if k in text.lower() and not client.service:
            client.service = v
    
    if not client.budget:
        match = re.search(r'(\d+)[\s-]*(usdt|دولار)', text, re.IGNORECASE)
        if match:
            client.budget = f"{match.group(1)} USDT"
    
    # رد الذكاء
    response = get_ai_response(text, client)
    send_message(sender_id, response)
    client.conversation.append(f"Agent: {response[:50]}")
    
    # إرسال للمالك
    if client.is_complete() and not client.confirmed:
        send_order(client)
        client.confirmed = True
        send_message(sender_id, f"شكراً {client.name}! تم تسجيل طلبك.")

# ========== Polling لإبقاء التطبيق نشطاً ==========
def keep_alive():
    """يُبقي التطبيق نشطاً بمنع Render من إيقافه"""
    while True:
        try:
            # إرسال طلب للتطبيق نفسه كل 10 دقائق
            requests.get("https://by-pro-marketing-agent.onrender.com", timeout=5)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Keep-alive ping")
            time.sleep(600)  # 10 دقائق
        except:
            time.sleep(600)

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
                    if sender != OWNER_FB_ID:
                        process_message(sender, text)
    return 'OK', 200

@app.route('/')
def home():
    return f"✅ البوت يعمل - العملاء: {len(sessions)}"

# ========== التشغيل ==========
if __name__ == '__main__':
    # بدء Polling في خيط منفصل
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
