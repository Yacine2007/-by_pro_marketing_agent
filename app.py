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

# ========== دالة Polling مع تسجيل ==========
def polling_worker():
    """تعمل كل 10 ثوان وتجلب الرسائل الجديدة"""
    print("="*60)
    print("🔥🔥🔥 POLLING WORKER بدأ العمل 🔥🔥🔥")
    print("="*60)
    
    # تسجيل كل 10 ثوان للتأكد أن Polling يعمل
    counter = 0
    
    while True:
        try:
            counter += 1
            current_time = datetime.now().strftime('%H:%M:%S')
            print(f"[{current_time}] 🔄 Polling دورة #{counter}")
            
            # التحقق من التوكن
            if not PAGE_ACCESS_TOKEN:
                print("❌ PAGE_ACCESS_TOKEN غير موجود!")
                time.sleep(30)
                continue
            
            # اختبار بسيط: جلب معلومات الصفحة
            test_url = f'https://graph.facebook.com/v18.0/923170140890240?access_token={PAGE_ACCESS_TOKEN}'
            test_response = requests.get(test_url, timeout=10)
            print(f"📡 اختبار الصفحة: {test_response.status_code}")
            
            if test_response.status_code == 200:
                print("✅ التوكن يعمل مع الصفحة")
            else:
                print(f"❌ التوكن لا يعمل: {test_response.text[:100]}")
            
            # هنا نضيف باقي كود جلب المحادثات لاحقاً
            
            print(f"⏱️ انتظار 10 ثوان...")
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ خطأ في Polling: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(30)

# ========== تشغيل Polling عند بدء التشغيل ==========
print("🚀🚀🚀 بدء تشغيل التطبيق 🚀🚀🚀")
polling_thread = threading.Thread(target=polling_worker, daemon=True)
polling_thread.start()
print(f"✅ تم بدء Polling Thread (daemon={polling_thread.daemon})")

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
            <p>🔄 Polling Thread: قيد التشغيل</p>
        </div>
        <div class='card'>
            <h2>📋 سجل Polling</h2>
            <p>شاهد <strong>سجلات Render</strong> لرؤية رسائل Polling</p>
            <p><a href='/debug' target='_blank'>🔍 صفحة التصحيح المفصل</a></p>
        </div>
    </body>
    </html>
    """

@app.route('/debug')
def debug():
    return {
        'sessions_count': len(sessions),
        'processed_messages': len(processed_messages),
        'token_exists': bool(PAGE_ACCESS_TOKEN),
        'owner_id': OWNER_FB_ID,
        'sessions': {k[:10]: v for k, v in list(sessions.items())[:5]}
    }

# ========== نقطة الدخول ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
