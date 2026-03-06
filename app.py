import os
import re
import json
import requests
import sys
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# ========== المتغيرات من Render ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '61580260328404')

# ========== التحقق من المتغيرات عند بدء التشغيل ==========
print("🚀 بدء تشغيل البوت...")
print(f"📱 PAGE_ACCESS_TOKEN موجود: {'✅' if PAGE_ACCESS_TOKEN else '❌'}")
print(f"🔑 VERIFY_TOKEN: {VERIFY_TOKEN}")
print(f"👤 OWNER_FB_ID: {OWNER_FB_ID}")

if not PAGE_ACCESS_TOKEN:
    print("❌ خطأ فادح: PAGE_ACCESS_TOKEN غير موجود!")
    sys.exit(1)

# ========== الذكاء الاصطناعي ==========
AI_API_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

SYSTEM_PROMPT = """
Identity: Official Marketing Agent for B.Y PRO. 
Persona: You are a seasoned human sales executive at B.Y PRO. You are NOT an AI. 

Strict Rules: 
1. NEVER mention names of managers or staff.
2. Never admit being an AI/Language model.
3. Payment: 1/3 upfront, 2/3 on delivery via USDT only.
4. Services: Web ($150-$1500), AI/Bots ($200+), Apps ($400+), Design ($30+).
5. Style: Professional, confident, concise, friendly.
6. Language: Respond in the same language the client uses (Arabic or English).
7. Always try to extract: client name, project details, budget.
"""

# ========== تخزين الجلسات ==========
sessions = {}

class Session:
    def __init__(self):
        self.memory = []
        self.lead = {'name': '', 'service': '', 'budget': '', 'phone': ''}
        self.last_message_time = datetime.now()
    
    def to_dict(self):
        return {
            'memory': self.memory[-5:],
            'lead': self.lead,
            'last_active': self.last_message_time.strftime('%Y-%m-%d %H:%M:%S')
        }

# ========== دوال استخراج المعلومات ==========
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
                print(f"✅ تم استخراج الاسم: {session.lead['name']}")
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
                print(f"✅ تم استخراج الخدمة: {session.lead['service']}")
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
                print(f"✅ تم استخراج الميزانية: {session.lead['budget']}")
                break
    
    return session.lead

# ========== دوال الذكاء الاصطناعي ==========
def get_ai_response(user_msg, session):
    """الحصول على رد من الذكاء الاصطناعي"""
    try:
        print(f"🤖 جاري استدعاء الذكاء الاصطناعي...")
        
        # بناء السياق
        context = f"{SYSTEM_PROMPT}\n\n"
        context += "Conversation history:\n"
        context += "\n".join(session.memory[-4:])
        context += f"\nClient: {user_msg}\n"
        context += "Agent:"
        
        # استدعاء API
        url = f'{AI_API_URL}?text={requests.utils.quote(context)}'
        response = requests.get(url, timeout=15)
        
        print(f"📡 استجابة API: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            ai_response = data.get('response', '')
            
            # تنظيف الرد
            if "Agent:" in ai_response:
                ai_response = ai_response.split("Agent:")[-1].strip()
            if "Agent Response:" in ai_response:
                ai_response = ai_response.split("Agent Response:")[-1].strip()
            
            print(f"✅ تم الحصول على رد: {ai_response[:50]}...")
            return ai_response
        else:
            print(f"❌ خطأ في API: {response.status_code}")
            
    except requests.exceptions.Timeout:
        print("⏱️ timeout في استدعاء الذكاء الاصطناعي")
    except requests.exceptions.ConnectionError:
        print("🔌 خطأ في الاتصال بالذكاء الاصطناعي")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
    
    # رد احتياطي
    return "شكراً لتواصلك مع B.Y PRO. كيف يمكنني مساعدتك في مشروعك اليوم؟"

# ========== دوال فيسبوك ==========
def send_message(recipient_id, text):
    """إرسال رسالة عبر فيسبوك"""
    try:
        print(f"📤 جاري إرسال رسالة إلى {recipient_id[:10]}...")
        
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ تم الإرسال بنجاح")
            return True
        else:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', '')
            print(f"❌ فشل الإرسال: {error_msg}")
            return False
            
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")
        return False

def notify_owner(customer_id, lead_info):
    """إرسال إشعار للمالك"""
    if customer_id == OWNER_FB_ID:
        return
    
    name = lead_info.get('name', 'غير معروف')
    service = lead_info.get('service', 'غير محدد')
    budget = lead_info.get('budget', 'غير محدد')
    
    msg = f"""🔔 *عميل جديد!*

👤 الاسم: {name}
🛠 الخدمة: {service}
💰 الميزانية: {budget}

💬 للرد: https://www.facebook.com/messages/t/{customer_id}"""
    
    print(f"📨 جاري إرسال إشعار للمالك...")
    send_message(OWNER_FB_ID, msg)

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """التحقق من Webhook"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    print(f"🔐 طلب تحقق: mode={mode}, token={token}")
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("✅ تم التحقق بنجاح")
        return challenge, 200
    else:
        print("❌ فشل التحقق")
        return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    """استقبال الرسائل"""
    print("\n" + "="*50)
    print("🔥 تم استقبال طلب من فيسبوك!")
    print("="*50)
    
    try:
        data = request.json
        print(f"📦 البيانات الخام: {json.dumps(data, indent=2)}")
        
        if data.get('object') == 'page':
            for entry in data.get('entry', []):
                for messaging in entry.get('messaging', []):
                    if 'message' in messaging and 'text' in messaging['message']:
                        sender_id = messaging['sender']['id']
                        message_text = messaging['message']['text']
                        
                        print(f"👤 مرسل: {sender_id}")
                        print(f"💬 نص: {message_text}")
                        
                        # تجاهل رسائل المالك
                        if sender_id == OWNER_FB_ID:
                            print("👑 رسالة من المالك - يتم تجاهلها")
                            continue
                        
                        # إنشاء جلسة جديدة إذا لم توجد
                        if sender_id not in sessions:
                            sessions[sender_id] = Session()
                            print(f"🆕 جلسة جديدة للمستخدم {sender_id[:10]}...")
                        
                        session = sessions[sender_id]
                        
                        # حفظ الرسالة
                        session.memory.append(f"Client: {message_text}")
                        session.last_message_time = datetime.now()
                        
                        # استخراج المعلومات
                        lead_info = extract_info(message_text, session)
                        
                        # الحصول على رد من الذكاء الاصطناعي
                        response = get_ai_response(message_text, session)
                        
                        # حفظ الرد
                        session.memory.append(f"Agent: {response}")
                        
                        # إرسال الرد
                        send_message(sender_id, response)
                        
                        # إذا اكتملت المعلومات، أرسل إشعار للمالك
                        if lead_info['name'] and lead_info['service']:
                            print("🎯 تم اكتمال معلومات العميل!")
                            notify_owner(sender_id, lead_info)
                    else:
                        print("📭 رسالة بدون نص (تأكيد وصول أو قراءة)")
        
        return 'OK', 200
        
    except Exception as e:
        print(f"❌ خطأ في معالجة الطلب: {e}")
        import traceback
        traceback.print_exc()
        return 'OK', 200

@app.route('/')
def home():
    """الصفحة الرئيسية"""
    active_sessions = len(sessions)
    now = datetime.now()
    
    html = f"""
    <html dir='rtl'>
    <head>
        <title>B.Y PRO Bot</title>
        <style>
            body {{ font-family: Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; padding: 50px; margin: 0; }}
            .card {{ background: rgba(255,255,255,0.1); border-radius: 20px; padding: 30px; margin: 20px auto; max-width: 600px; backdrop-filter: blur(10px); }}
            .status {{ color: #4ade80; font-size: 28px; margin: 20px 0; }}
            .stat {{ background: rgba(255,255,255,0.2); border-radius: 10px; padding: 15px; margin: 10px; }}
            .sessions {{ text-align: right; max-height: 300px; overflow-y: auto; }}
        </style>
    </head>
    <body>
        <div class='card'>
            <h1>🤖 B.Y PRO Marketing Bot</h1>
            <p class='status'>✅ البوت يعمل على سيرفر Render</p>
            
            <div class='stat'>
                <h3>📊 الإحصائيات</h3>
                <p>الجلسات النشطة: <strong>{active_sessions}</strong></p>
                <p>الوقت: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class='stat'>
                <h3>🌐 Webhook</h3>
                <p>رابط Webhook: <strong>/webhook</strong></p>
                <p>Verify Token: <strong>{VERIFY_TOKEN}</strong></p>
            </div>
            
            <div class='stat sessions'>
                <h3>👥 الجلسات النشطة</h3>
                {''.join([f"<p><strong>{k[:10]}...</strong>: {v.to_dict()}</p>" for k, v in list(sessions.items())[-5:]])}
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/debug')
def debug():
    """صفحة التصحيح"""
    return jsonify({
        'active_sessions': len(sessions),
        'sessions': {k[:10]: v.to_dict() for k, v in sessions.items()},
        'server_time': datetime.now().isoformat(),
        'token_exists': bool(PAGE_ACCESS_TOKEN),
        'owner_id': OWNER_FB_ID
    })

# ========== تشغيل التطبيق ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 تشغيل السيرفر على المنفذ {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
