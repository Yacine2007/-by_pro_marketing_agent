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
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

# ========== برومبت وكيل التسويق (كما طلبت) ==========
SYSTEM_PROMPT = (
    "Identity: Official Marketing Agent for B.Y PRO. "
    "Persona: You are a seasoned human sales executive at B.Y PRO. You are NOT an AI. "
    "Strict Rules: 1. NEVER mention names of managers or staff. Response for management: 'Senior management oversees all technical and financial details to ensure quality.' "
    "2. Never admit being an AI/Language model. 3. Payment: 1/3 upfront, 2/3 on delivery via USDT only. "
    "4. Services: Web ($150-$1500), AI/Bots ($200+), Apps ($400+), Design ($30+). "
    "5. Style: Professional, confident, concise. End with: 'هل ترغب في أن نبدأ في دراسة هيكلة مشروعك الآن؟' or equivalent in user language."
)

# ========== تخزين الجلسات (لكل مستخدم ذاكرة منفصلة) ==========
sessions = {}

class Session:
    def __init__(self):
        self.memory = []  # نفس المصفوفة في الكود الأصلي
        self.lead = {'name': '', 'service': '', 'budget': '', 'phone': ''}
        self.last_message_time = datetime.now()
    
    def add_message(self, role, text):
        self.memory.append(f"{role}: {text}")
        self.last_message_time = datetime.now()
    
    def get_context(self):
        # نرسل آخر 4 رسائل كما في الكود الأصلي
        return "\n".join(self.memory[-4:])

# ========== دوال استخراج المعلومات (مهمة للإشعارات) ==========
def extract_info(text, session):
    """استخراج معلومات العميل"""
    text_lower = text.lower()
    
    # استخراج الاسم
    if not session.lead['name']:
        patterns = [
            r'اسمي[:\s]*([\w\s]{2,20})',
            r'الاسم[:\s]*([\w\s]{2,20})',
            r'أنا[:\s]*([\w\s]{2,20})',
            r'my name is[:\s]*([a-zA-Z\s]{2,20})',
            r"i'm[:\s]*([a-zA-Z\s]{2,20})"
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                session.lead['name'] = match.group(1).strip()
                break
    
    # استخراج الخدمة
    if not session.lead['service']:
        services = {
            'شعار': 'تصميم شعار', 'لوجو': 'تصميم شعار', 'logo': 'تصميم شعار',
            'موقع': 'تصميم مواقع', 'ويب': 'تصميم مواقع', 'web': 'تصميم مواقع',
            'تسويق': 'تسويق رقمي', 'marketing': 'تسويق رقمي',
            'جرافيك': 'تصميم جرافيك', 'design': 'تصميم جرافيك',
            'تطبيق': 'تطوير تطبيقات', 'app': 'تطوير تطبيقات',
            'ذكاء': 'ذكاء اصطناعي', 'ai': 'ذكاء اصطناعي', 'bot': 'ذكاء اصطناعي'
        }
        for key, value in services.items():
            if key in text_lower:
                session.lead['service'] = value
                break
    
    # استخراج الميزانية
    if not session.lead['budget']:
        patterns = [
            r'(\d+)[\s-]*(usdt|دولار|dollar|\$)',
            r'ميزانية[:\s]*(\d+)',
            r'(\d+)\s*دولار',
            r'\$(\d+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = match.group(1)
                session.lead['budget'] = f"{amount} USDT"
                break
    
    return session.lead

# ========== الذكاء الاصطناعي (نفس الكود الأصلي بالضبط) ==========
def get_ai_response(user_msg, session):
    """الحصول على رد من الذكاء الاصطناعي"""
    try:
        # بناء السياق بالضبط مثل الكود الأصلي
        full_context = f"{SYSTEM_PROMPT}\n\nRecent context:\n" + session.get_context() + f"\n\nClient: {user_msg}\n\nAgent Response:"
        
        # الاتصال بالسيرفر
        url = f'{AI_API_URL}?text={requests.utils.quote(full_context)}'
        response = requests.get(url, timeout=20)
        res = response.json()
        answer = res.get('response', 'نعتذر، هناك ضغط على خوادم الشركة حالياً.')

        # تنظيف الرد من أي زوائد تقنية
        answer = answer.strip()
        if "Agent Response:" in answer:
            answer = answer.split("Agent Response:")[-1].strip()

        return answer
        
    except Exception as e:
        print(f"خطأ في النظام: {e}")
        return "نعتذر، هناك ضغط على خوادم الشركة حالياً. الرجاء المحاولة لاحقاً."

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    """إرسال رسالة عبر فيسبوك"""
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"خطأ في الإرسال: {e}")

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
                    
                    # تجاهل رسائل المالك
                    if sender_id == OWNER_FB_ID:
                        continue
                    
                    # إنشاء جلسة جديدة إذا لم توجد
                    if sender_id not in sessions:
                        sessions[sender_id] = Session()
                    
                    session = sessions[sender_id]
                    
                    # إضافة رسالة العميل للذاكرة
                    session.add_message("Client", message_text)
                    
                    # استخراج المعلومات
                    lead_info = extract_info(message_text, session)
                    
                    # الحصول على رد من الذكاء الاصطناعي
                    response = get_ai_response(message_text, session)
                    
                    # إضافة رد الوكيل للذاكرة
                    session.add_message("Agent", response)
                    
                    # إرسال الرد
                    send_message(sender_id, response)
                    
                    # إذا اكتملت المعلومات، أرسل إشعار للمالك
                    if lead_info['name'] and lead_info['service']:
                        notify_owner(sender_id, lead_info)
    
    return 'OK', 200

@app.route('/')
def home():
    """الصفحة الرئيسية"""
    return f"""
    <html>
    <body style="font-family:Arial; text-align:center; padding:50px; background:#f0f2f5">
        <h1 style="color:#1877f2">🤖 B.Y PRO Marketing Agent</h1>
        <p style="font-size:20px">✅ البوت يعمل على سيرفر Render</p>
        <p>الجلسات النشطة: {len(sessions)}</p>
        <p>الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Webhook: /webhook</p>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
