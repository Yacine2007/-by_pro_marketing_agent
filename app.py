import os
import re
import json
import requests
import time
import threading
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
    "1. NEVER mention names of managers or staff. Response for management: 'Senior management oversees all technical and financial details to ensure quality.' "
    "2. Never admit being an AI/Language model. "
    "3. Payment: 1/3 upfront, 2/3 on delivery via USDT only. "
    "4. Services: Web ($150-$1500), AI/Bots ($200+), Apps ($400+), Design ($30+). "
    "5. Style: Professional, confident, concise. End with: 'هل ترغب في أن نبدأ في دراسة هيكلة مشروعك الآن؟' or equivalent in user language. "
    "6. Extract client information naturally through conversation: name, project type, budget."
)

# ========== تخزين الجلسات والبيانات ==========
sessions = {}  # جلسات المستخدمين
processed_messages = set()  # الرسائل التي تمت معالجتها

# ========== نماذج البيانات ==========
class ClientData:
    """بيانات العميل المستخرجة من المحادثة"""
    def __init__(self, sender_id):
        self.sender_id = sender_id
        self.name = ""
        self.service = ""
        self.budget = ""
        self.phone = ""
        self.confirmed = False
        self.conversation = []
    
    def to_dict(self):
        return {
            'sender_id': self.sender_id,
            'name': self.name,
            'service': self.service,
            'budget': self.budget,
            'phone': self.phone,
            'confirmed': self.confirmed,
            'conversation': self.conversation[-5:]
        }
    
    def is_complete(self):
        """التحقق من اكتمال بيانات العميل"""
        return bool(self.name and self.service and self.budget)
    
    def get_conversation_link(self):
        return f"https://www.facebook.com/messages/t/{self.sender_id}"

# ========== دوال استخراج المعلومات ==========
def extract_info(text, client_data):
    """استخراج معلومات العميل من النص"""
    text_lower = text.lower()
    
    # استخراج الاسم
    if not client_data.name:
        patterns = [
            r'اسمي[:\s]*([\w\s]{2,20})',
            r'الاسم[:\s]*([\w\s]{2,20})',
            r'أنا[:\s]*([\w\s]{2,20})',
            r'my name is[:\s]*([a-zA-Z\s]{2,20})',
            r"i'm[:\s]*([a-zA-Z\s]{2,20})",
            r'call me[:\s]*([a-zA-Z\s]{2,20})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client_data.name = match.group(1).strip()
                print(f"✅ تم استخراج الاسم: {client_data.name}")
                break
    
    # استخراج الخدمة
    if not client_data.service:
        services = {
            'شعار': 'تصميم شعار', 'لوجو': 'تصميم شعار', 'logo': 'تصميم شعار',
            'موقع': 'تصميم مواقع', 'ويب': 'تصميم مواقع', 'web': 'تصميم مواقع',
            'تسويق': 'تسويق رقمي', 'marketing': 'تسويق رقمي',
            'جرافيك': 'تصميم جرافيك', 'design': 'تصميم جرافيك',
            'تطبيق': 'تطوير تطبيقات', 'app': 'تطوير تطبيقات',
            'ذكاء': 'ذكاء اصطناعي', 'ai': 'ذكاء اصطناعي', 'bot': 'ذكاء اصطناعي',
            'برمجة': 'تطوير ويب', 'برنامج': 'تطوير تطبيقات'
        }
        for key, value in services.items():
            if key in text_lower:
                client_data.service = value
                print(f"✅ تم استخراج الخدمة: {client_data.service}")
                break
    
    # استخراج الميزانية
    if not client_data.budget:
        patterns = [
            r'(\d+)[\s-]*(usdt|دولار|dollar|\$)',
            r'ميزانية[:\s]*(\d+)',
            r'سعر[:\s]*(\d+)',
            r'(\d+)\s*دولار',
            r'\$(\d+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = match.group(1)
                client_data.budget = f"{amount} USDT"
                print(f"✅ تم استخراج الميزانية: {client_data.budget}")
                break
    
    # استخراج رقم الجوال
    if not client_data.phone:
        phone_patterns = [
            r'(05[0-9]{8})',
            r'(5[0-9]{8})',
            r'(\+966[0-9]{9})',
            r'(00966[0-9]{9})'
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                client_data.phone = match.group(1)
                print(f"✅ تم استخراج الجوال: {client_data.phone}")
                break
    
    return client_data

# ========== دوال الذكاء الاصطناعي ==========
def get_ai_response(user_msg, client_data):
    """الحصول على رد من الذكاء الاصطناعي"""
    try:
        print(f"🤖 جاري استدعاء الذكاء الاصطناعي...")
        
        # بناء المحادثة للسياق
        conversation = "\n".join(client_data.conversation[-6:])
        
        # إضافة معلومات العميل المستخرجة للسياق
        client_info = f"Client Info - Name: {client_data.name if client_data.name else 'Unknown'}, Service: {client_data.service if client_data.service else 'Unknown'}, Budget: {client_data.budget if client_data.budget else 'Unknown'}"
        
        full_context = f"{SYSTEM_PROMPT}\n\n{client_info}\n\nConversation history:\n{conversation}\n\nClient: {user_msg}\n\nAgent:"
        
        # استدعاء API
        url = f'{AI_API_URL}?text={requests.utils.quote(full_context)}'
        response = requests.get(url, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            answer = data.get('response', '')
            
            # تنظيف الرد
            answer = answer.strip()
            if "Agent:" in answer:
                answer = answer.split("Agent:")[-1].strip()
            if "Agent Response:" in answer:
                answer = answer.split("Agent Response:")[-1].strip()
            
            print(f"✅ تم الحصول على رد من الذكاء الاصطناعي")
            return answer
        else:
            print(f"❌ خطأ في API: {response.status_code}")
            return get_fallback_response(user_msg)
            
    except Exception as e:
        print(f"❌ خطأ في الذكاء الاصطناعي: {e}")
        return get_fallback_response(user_msg)

def get_fallback_response(user_msg):
    """رد احتياطي عند فشل الذكاء الاصطناعي"""
    responses = [
        "شكراً لتواصلك مع B.Y PRO. كيف يمكنني مساعدتك في مشروعك اليوم؟",
        "مرحباً! أنا وكيل المبيعات الرسمي لـ B.Y PRO. ما هي الخدمة التي تبحث عنها؟",
        "نقدر استفسارك. هل يمكنك إخباري بالمزيد عن مشروعك؟",
        "أهلاً بك في B.Y PRO. كيف أقدر أخدمك اليوم؟"
    ]
    import random
    return random.choice(responses)

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
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ تم إرسال رسالة إلى {recipient_id[:10]}...")
            return True
        else:
            print(f"❌ فشل إرسال الرسالة: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")
        return False

def send_order_to_owner(client_data):
    """إرسال الطلب المكتمل للمالك"""
    if not client_data.is_complete():
        return False
    
    # تنسيق رسالة الطلب
    order_message = f"""
🔔 *طلب جديد مكتمل!*
━━━━━━━━━━━━━━━━
👤 *العميل:* {client_data.name}
🛠 *الخدمة:* {client_data.service}
💰 *الميزانية:* {client_data.budget}
📱 *الجوال:* {client_data.phone if client_data.phone else 'غير متوفر'}
━━━━━━━━━━━━━━━━
💬 *آخر محادثة:*
{chr(10).join(client_data.conversation[-3:])}
━━━━━━━━━━━━━━━━
🔗 *رابط المحادثة:*
{client_data.get_conversation_link()}
━━━━━━━━━━━━━━━━
⚡️ *تواصل مع العميل فوراً!*
    """.strip()
    
    # إرسال للمالك
    success = send_message(OWNER_FB_ID, order_message)
    
    if success:
        print(f"✅ تم إرسال طلب {client_data.name} للمالك")
        return True
    else:
        print(f"❌ فشل إرسال الطلب للمالك")
        return False

# ========== دالة معالجة الرسالة ==========
def process_message(sender_id, message_text):
    """معالجة رسالة واحدة"""
    print(f"\n{'='*50}")
    print(f"📨 معالجة رسالة من {sender_id[:10]}...")
    print(f"💬 النص: {message_text[:100]}")
    
    # إنشاء بيانات العميل إذا لم توجد
    if sender_id not in sessions:
        sessions[sender_id] = ClientData(sender_id)
        print(f"🆕 جلسة جديدة للمستخدم")
    
    client = sessions[sender_id]
    
    # إضافة الرسالة للمحادثة
    client.conversation.append(f"Client: {message_text}")
    if len(client.conversation) > 20:
        client.conversation = client.conversation[-20:]
    
    # استخراج المعلومات
    client = extract_info(message_text, client)
    
    # الحصول على رد الذكاء الاصطناعي
    ai_response = get_ai_response(message_text, client)
    
    # إضافة الرد للمحادثة
    client.conversation.append(f"Agent: {ai_response[:50]}...")
    
    # إرسال الرد
    send_message(sender_id, ai_response)
    
    # التحقق من اكتمال الطلب
    if client.is_complete() and not client.confirmed:
        print(f"🎯 اكتملت بيانات العميل: {client.name} - {client.service} - {client.budget}")
        
        # إرسال الطلب للمالك
        if send_order_to_owner(client):
            client.confirmed = True
            print(f"✅ تم تأكيد وإرسال الطلب للمالك")
        
        # إرسال رسالة تأكيد للعميل
        confirm_msg = f"""
شكراً جزيلاً {client.name}! 🙏

تم تسجيل طلبك:
• الخدمة: {client.service}
• الميزانية: {client.budget}

سيتواصل معك فريق B.Y PRO خلال ٢٤ ساعة لتأكيد التفاصيل.
هل هناك أي شيء آخر تريد الاستفسار عنه؟
        """.strip()
        send_message(sender_id, confirm_msg)
    
    print(f"✅ تمت معالجة الرسالة بنجاح")
    print(f"{'='*50}\n")

# ========== دالة Polling الرئيسية ==========
def polling_worker():
    """تعمل كل 5 ثوان وتجلب الرسائل الجديدة"""
    print("\n" + "🚀"*50)
    print("🔥🔥🔥 POLLING WORKER بدأ العمل 🔥🔥🔥")
    print("🚀"*50 + "\n")
    
    counter = 0
    
    while True:
        try:
            counter += 1
            current_time = datetime.now().strftime('%H:%M:%S')
            print(f"\n[{current_time}] 🔄 Polling دورة #{counter}")
            
            # التحقق من التوكن
            if not PAGE_ACCESS_TOKEN:
                print("❌ PAGE_ACCESS_TOKEN غير موجود!")
                time.sleep(30)
                continue
            
            # جلب المحادثات - استخدام me/conversations بدلاً من معرف الصفحة
            print("📥 جلب المحادثات...")
            url = f'https://graph.facebook.com/v18.0/me/conversations?access_token={PAGE_ACCESS_TOKEN}&limit=10'
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ فشل جلب المحادثات: {response.status_code}")
                print(f"   {response.text[:200]}")
                time.sleep(30)
                continue
            
            data = response.json()
            conversations = data.get('data', [])
            print(f"📊 عدد المحادثات: {len(conversations)}")
            
            # معالجة كل محادثة
            for conv in conversations:
                conv_id = conv.get('id')
                
                # جلب رسائل المحادثة
                msg_url = f'https://graph.facebook.com/v18.0/{conv_id}/messages?access_token={PAGE_ACCESS_TOKEN}&fields=message,from,created_time&limit=5'
                msg_response = requests.get(msg_url, timeout=10)
                
                if msg_response.status_code != 200:
                    continue
                
                messages = msg_response.json().get('data', [])
                
                # معالجة كل رسالة (من الأقدم للأحدث)
                for msg in reversed(messages):
                    msg_id = msg.get('id')
                    
                    if msg_id in processed_messages:
                        continue
                    
                    msg_text = msg.get('message', '')
                    from_data = msg.get('from', {})
                    sender_id = from_data.get('id', '')
                    
                    # تجاهل رسائل الصفحة نفسها
                    if sender_id == '923170140890240':
                        processed_messages.add(msg_id)
                        continue
                    
                    # تجاهل رسائل المالك
                    if sender_id == OWNER_FB_ID:
                        processed_messages.add(msg_id)
                        continue
                    
                    print(f"\n📨 رسالة جديدة!")
                    print(f"   👤 من: {sender_id[:15]}...")
                    print(f"   💬 نص: {msg_text[:100]}")
                    
                    # معالجة الرسالة
                    process_message(sender_id, msg_text)
                    
                    # إضافة للرسائل المعالجة
                    processed_messages.add(msg_id)
                    
                    # انتظار قصير بين الرسائل
                    time.sleep(1)
            
            # تنظيف الذاكرة
            if len(processed_messages) > 1000:
                processed_messages = set(list(processed_messages)[-500:])
            
            print(f"\n⏱️ انتظار 5 ثوان...")
            time.sleep(5)
            
        except Exception as e:
            print(f"❌ خطأ كبير في Polling: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(30)

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """التحقق من Webhook"""
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    """نتركه للتوافق - نعتمد على Polling"""
    return 'OK', 200

@app.route('/')
def home():
    """الصفحة الرئيسية"""
    active_clients = len([c for c in sessions.values() if c.is_complete()])
    pending = len([c for c in sessions.values() if c.is_complete() and not c.confirmed])
    
    return f"""
    <html dir='rtl'>
    <head>
        <title>B.Y PRO AI Bot</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; padding: 20px; margin: 0; min-height: 100vh; }}
            .card {{ background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 30px; margin: 20px auto; max-width: 800px; box-shadow: 0 8px 32px rgba(0,0,0,0.1); }}
            h1 {{ color: #fff; font-size: 2.5em; margin-bottom: 20px; }}
            .status {{ background: #4ade80; color: #166534; padding: 15px; border-radius: 10px; margin: 20px 0; font-weight: bold; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 30px 0; }}
            .stat {{ background: rgba(255,255,255,0.2); border-radius: 10px; padding: 20px; }}
            .stat-value {{ font-size: 2.5em; font-weight: bold; }}
            .stat-label {{ font-size: 1em; opacity: 0.9; }}
            .clients {{ background: rgba(0,0,0,0.2); border-radius: 10px; padding: 20px; margin-top: 30px; text-align: right; }}
            .client-item {{ background: rgba(255,255,255,0.1); border-radius: 5px; padding: 10px; margin: 5px 0; }}
            .badge {{ background: #f59e0b; color: #000; padding: 3px 10px; border-radius: 15px; font-size: 0.8em; }}
        </style>
    </head>
    <body>
        <div class='card'>
            <h1>🤖 B.Y PRO AI Marketing Bot</h1>
            <div class='status'>✅ البوت يعمل بنظام Polling + الذكاء الاصطناعي</div>
            
            <div class='stats'>
                <div class='stat'>
                    <div class='stat-value'>{len(sessions)}</div>
                    <div class='stat-label'>إجمالي العملاء</div>
                </div>
                <div class='stat'>
                    <div class='stat-value'>{active_clients}</div>
                    <div class='stat-label'>عملاء مكتملين</div>
                </div>
                <div class='stat'>
                    <div class='stat-value'>{pending}</div>
                    <div class='stat-label'>في انتظار الإرسال</div>
                </div>
            </div>
            
            <div class='clients'>
                <h3>📋 آخر العملاء</h3>
                {''.join([f"<div class='client-item'><b>{c.name if c.name else 'غير معروف'}</b> - {c.service if c.service else '...'} - {c.budget if c.budget else '...'}</div>" for c in list(sessions.values())[-5:]])}
            </div>
            
            <p style='margin-top: 30px; font-size: 0.9em;'>⏱ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </body>
    </html>
    """

@app.route('/debug')
def debug():
    """صفحة التصحيح"""
    return {
        'sessions_count': len(sessions),
        'processed_messages': len(processed_messages),
        'completed_clients': len([c for c in sessions.values() if c.is_complete()]),
        'confirmed_orders': len([c for c in sessions.values() if c.confirmed]),
        'token_exists': bool(PAGE_ACCESS_TOKEN),
        'owner_id': OWNER_FB_ID,
        'sessions': {k[:10]: v.to_dict() for k, v in list(sessions.items())[:5]}
    }

# ========== تشغيل Polling و Flask ==========
print("\n" + "⭐"*50)
print("🚀 بدء تشغيل B.Y PRO AI Marketing Bot")
print("⭐"*50 + "\n")

# بدء Polling في خيط منفصل
polling_thread = threading.Thread(target=polling_worker, daemon=True)
polling_thread.start()
print("✅ تم بدء Polling Worker")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
