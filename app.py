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

SYSTEM_PROMPT = "Identity: Official Marketing Agent for B.Y PRO..."

# ========== تخزين الجلسات ==========
sessions = {}
processed_messages = set()

# ========== دوال فيسبوك مع تسجيل ==========
def test_facebook_connection():
    """اختبار الاتصال بفيسبوك"""
    try:
        print("🔍 اختبار 1: التحقق من التوكن...")
        url = f'https://graph.facebook.com/v18.0/me?access_token={PAGE_ACCESS_TOKEN}'
        r = requests.get(url, timeout=5)
        print(f"   الحالة: {r.status_code}")
        if r.status_code == 200:
            print(f"   ✅ التوكن صحيح: {r.json()}")
            return True
        else:
            print(f"   ❌ خطأ: {r.text}")
            return False
    except Exception as e:
        print(f"   ❌ استثناء: {e}")
        return False

def test_page_info():
    """اختبار معلومات الصفحة"""
    try:
        print("🔍 اختبار 2: معلومات الصفحة...")
        url = f'https://graph.facebook.com/v18.0/923170140890240?access_token={PAGE_ACCESS_TOKEN}'
        r = requests.get(url, timeout=5)
        print(f"   الحالة: {r.status_code}")
        if r.status_code == 200:
            print(f"   ✅ الصفحة: {r.json()}")
            return True
        else:
            print(f"   ❌ خطأ: {r.text}")
            return False
    except Exception as e:
        print(f"   ❌ استثناء: {e}")
        return False

def test_conversations():
    """اختبار جلب المحادثات"""
    try:
        print("🔍 اختبار 3: جلب المحادثات...")
        url = f'https://graph.facebook.com/v18.0/923170140890240/conversations?access_token={PAGE_ACCESS_TOKEN}'
        r = requests.get(url, timeout=5)
        print(f"   الحالة: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ عدد المحادثات: {len(data.get('data', []))}")
            return data.get('data', [])
        else:
            print(f"   ❌ خطأ: {r.text}")
            return []
    except Exception as e:
        print(f"   ❌ استثناء: {e}")
        return []

def test_messages(conversation_id):
    """اختبار جلب الرسائل من محادثة"""
    try:
        print(f"🔍 اختبار 4: جلب رسائل من محادثة {conversation_id[:10]}...")
        url = f'https://graph.facebook.com/v18.0/{conversation_id}/messages?access_token={PAGE_ACCESS_TOKEN}&fields=message,from,created_time'
        r = requests.get(url, timeout=5)
        print(f"   الحالة: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ عدد الرسائل: {len(data.get('data', []))}")
            return data.get('data', [])
        else:
            print(f"   ❌ خطأ: {r.text}")
            return []
    except Exception as e:
        print(f"   ❌ استثناء: {e}")
        return []

def test_send_message():
    """اختبار إرسال رسالة للمالك"""
    try:
        print("🔍 اختبار 5: إرسال رسالة للمالك...")
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': OWNER_FB_ID},
            'message': {'text': '🔧 اختبار من البوت - إذا وصلت هذه الرسالة فالبوت يعمل!'},
            'messaging_type': 'RESPONSE'
        }
        r = requests.post(url, json=payload, timeout=5)
        print(f"   الحالة: {r.status_code}")
        if r.status_code == 200:
            print(f"   ✅ تم إرسال رسالة الاختبار")
            return True
        else:
            print(f"   ❌ خطأ: {r.text}")
            return False
    except Exception as e:
        print(f"   ❌ استثناء: {e}")
        return False

# ========== دالة Polling مع تسجيل ==========
def polling_worker():
    """تعمل كل 10 ثوان وتجلب الرسائل الجديدة"""
    print("\n" + "="*60)
    print("🚀 بدء Polling Worker مع تسجيل كل خطوة")
    print("="*60)
    
    # تشغيل الاختبارات مرة واحدة
    test_facebook_connection()
    test_page_info()
    conversations = test_conversations()
    
    if conversations:
        test_messages(conversations[0]['id'])
    
    test_send_message()
    
    print("\n" + "="*60)
    print("🔄 بدء حلقة Polling الرئيسية")
    print("="*60)
    
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔄 دورة Polling جديدة")
            
            # جلب المحادثات
            url = f'https://graph.facebook.com/v18.0/923170140890240/conversations?access_token={PAGE_ACCESS_TOKEN}'
            r = requests.get(url, timeout=10)
            
            if r.status_code != 200:
                print(f"❌ فشل جلب المحادثات: {r.status_code}")
                print(f"   الرد: {r.text[:200]}")
                time.sleep(30)
                continue
            
            data = r.json()
            conversations = data.get('data', [])
            print(f"📊 عدد المحادثات: {len(conversations)}")
            
            for conv in conversations:
                conv_id = conv.get('id')
                print(f"   📁 محادثة: {conv_id[:20]}...")
                
                # جلب رسائل المحادثة
                msg_url = f'https://graph.facebook.com/v18.0/{conv_id}/messages?access_token={PAGE_ACCESS_TOKEN}&fields=message,from,created_time'
                msg_r = requests.get(msg_url, timeout=10)
                
                if msg_r.status_code != 200:
                    print(f"   ❌ فشل جلب الرسائل: {msg_r.status_code}")
                    continue
                
                messages = msg_r.json().get('data', [])
                print(f"   💬 عدد الرسائل: {len(messages)}")
                
                for msg in messages:
                    msg_id = msg.get('id')
                    if msg_id in processed_messages:
                        continue
                    
                    message_text = msg.get('message', '')
                    from_data = msg.get('from', {})
                    sender_id = from_data.get('id', '')
                    
                    print(f"      📨 رسالة جديدة: {message_text[:50]}")
                    print(f"      👤 من: {sender_id[:10]}...")
                    
                    # تجاهل رسائل الصفحة
                    if sender_id == '923170140890240':
                        print(f"      ⏭️ رسالة من الصفحة نفسها - تجاهل")
                        processed_messages.add(msg_id)
                        continue
                    
                    if sender_id and sender_id != OWNER_FB_ID:
                        processed_messages.add(msg_id)
                        
                        if sender_id not in sessions:
                            sessions[sender_id] = {'memory': [], 'lead': {}}
                            print(f"      🆕 جلسة جديدة للمستخدم")
                        
                        # هنا نضيف ردود الذكاء الاصطناعي
                        print(f"      ✅ تمت معالجة الرسالة")
            
            # نحد من حجم processed_messages
            if len(processed_messages) > 1000:
                processed_messages = set(list(processed_messages)[-500:])
            
            print(f"⏱️ انتظار 10 ثوان...")
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ خطأ كبير في Polling: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(30)

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    return 'OK', 200

@app.route('/')
def home():
    return f"""
    <html>
    <head>
        <title>B.Y PRO Bot - تشخيص</title>
        <style>
            body {{ font-family: Arial; background: #f0f2f5; padding: 20px; }}
            .card {{ background: white; border-radius: 10px; padding: 20px; margin: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            pre {{ background: #eee; padding: 10px; border-radius: 5px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class='card'>
            <h1>🤖 B.Y PRO Bot - وضع التشخيص</h1>
            <p class='success'>✅ البوت يعمل على Render</p>
            <p>📊 الجلسات المخزنة: {len(sessions)}</p>
            <p>💬 الرسائل المعالجة: {len(processed_messages)}</p>
            <p>⏱ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div class='card'>
            <h2>📋 سجل Polling</h2>
            <p>شاهد سجلات Render لرؤية كل الخطوات</p>
            <p><a href='/debug' target='_blank'>🔍 صفحة التصحيح المفصل</a></p>
        </div>
    </body>
    </html>
    """

@app.route('/debug')
def debug():
    """صفحة تصحيح مفصلة"""
    return {
        'sessions_count': len(sessions),
        'processed_messages': len(processed_messages),
        'token_exists': bool(PAGE_ACCESS_TOKEN),
        'owner_id': OWNER_FB_ID,
        'sessions': {k[:10]: v for k, v in list(sessions.items())[:5]}
    }

# ========== تشغيل Polling و Flask ==========
if __name__ == '__main__':
    print("\n" + "🚀"*20)
    print("بدء تشغيل البوت في وضع التشخيص الكامل")
    print("🚀"*20 + "\n")
    
    # بدء Polling في خيط منفصل
    polling_thread = threading.Thread(target=polling_worker, daemon=True)
    polling_thread.start()
    
    # تشغيل Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
