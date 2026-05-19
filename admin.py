import hashlib
import base64
from datetime import datetime, timedelta

def generate_key_for_client(hwid, days_valid):
    secret_salt = "kaiden_master_xuandinh"
    
    exp_date = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d")
    
    # THUẬT TOÁN MỚI: Không nhét chuỗi HWID vào Key, chỉ dùng nó để làm chữ ký đối chiếu
    signature = hashlib.md5((f"{hwid}|{exp_date}" + secret_salt).encode()).hexdigest()[:10]
    raw_key = f"{exp_date}|{signature}"
    final_key = base64.b64encode(raw_key.encode()).decode('utf-8')
    
    print("="*50)
    print(f"🖥️ HWID Khách: {hwid}")
    print(f"⏳ Hạn sử dụng: {exp_date}")
    print(f"🔑 Key Kích Hoạt Siêu Ngắn:\n{final_key}")
    print("="*50)


generate_key_for_client("5FD58B5B-FCE5-11EC-80F2-6C2408EBA9DF", 9999)