import customtkinter as ctk
import threading
import asyncio
import re
import os
import subprocess
import hashlib
import base64
import pyperclip
import json  
import time
import qrcode
import webbrowser  
from PIL import Image 
from playwright.async_api import async_playwright 
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession  
from telethon.errors import SessionPasswordNeededError  

# ==========================================
# HỆ THỐNG BẢN QUYỀN (HWID & TIME KEY)
# ==========================================
def get_hwid():
    try:
        hwid = subprocess.check_output('wmic csproduct get uuid', shell=True).decode().split('\n')[1].strip()
        return hwid
    except Exception:
        return "UNKNOWN_DEVICE"

def validate_license(current_hwid, user_key):
    secret_salt = "kaiden_master_xuandinh"
    try:
        decoded_key = base64.b64decode(user_key).decode('utf-8')
        exp_date_in_key, signature_in_key = decoded_key.split('|')
        
        expected_sig = hashlib.md5((f"{current_hwid}|{exp_date_in_key}" + secret_salt).encode()).hexdigest()[:10]
        if signature_in_key != expected_sig:
            return False, "❌ Key không hợp lệ hoặc đã bị làm giả!"

        exp_dt = datetime.strptime(exp_date_in_key, "%Y-%m-%d")
        if datetime.now() > exp_dt:
            return False, f"❌ Key đã hết hạn vào ngày {exp_date_in_key}!"

        return True, f"✅ Kích hoạt thành công! (HSD: {exp_date_in_key})"
    except Exception:
        return False, "❌ Định dạng Key sai!"

# ==========================================
# CẤU HÌNH CORE TOOL
# ==========================================
SHOPEE_API_URL = "https://shopee.vn/api/v2/voucher_wallet/save_voucher"
VOUCHER_REGEX = re.compile(r'\b[A-Z0-9]{8,30}\b')
CONFIG_FILE = "tool_config.json"  

class VoucherSniperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KAIDEN SHOPEE AUTO v8.9")
        self.geometry("1180x830")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        
        self.is_running = False
        self.loop = None
        self.client = None 
        self.browser = None  
        self.context = None 
        self.async_queue = None
        self.voucher_data = [] 
        self.voucher_counter = 0
        self.saved_session_str = "" 
        self.qr_login_state = None  
        self.phone_code_hash = ""   
        
        self.setup_ui()
        self.load_tool_config() 

    def setup_ui(self):
        # --- KHUNG TRÁI: KHUNG CUỘN CẤU HÌNH ---
        self.frame_left = ctk.CTkScrollableFrame(self, width=340)
        self.frame_left.pack(side="left", fill="y", padx=10, pady=10)

        self.tele_visible = True  
        self.btn_toggle_tele = ctk.CTkButton(self.frame_left, text="👁️ ẨN CẤU HÌNH TELEGRAM", font=("Arial", 12, "bold"), fg_color="#2980b9", hover_color="#3498db", height=35, command=self.toggle_tele_frame)
        self.btn_toggle_tele.pack(pady=(15, 5), padx=10, fill="x")

        self.frame_tele_login = ctk.CTkFrame(self.frame_left, fg_color="transparent")
        self.frame_tele_login.pack(fill="x", pady=5)

        ctk.CTkLabel(self.frame_tele_login, text="📸 ĐĂNG NHẬP TELEGRAM SYSTEM", font=("Arial", 13, "bold"), text_color="#00FFFF").pack(pady=(5, 5), padx=10, anchor="w")
        
        self.ent_api_id = ctk.CTkEntry(self.frame_tele_login, placeholder_text="Telegram API ID...", width=310)
        self.ent_api_id.pack(pady=3, padx=10)

        # Ô NHẬP API HASH + NÚT 👁️ ẨN/HIỆN
        self.frame_hash = ctk.CTkFrame(self.frame_tele_login, fg_color="transparent")
        self.frame_hash.pack(pady=3, padx=10, fill="x")
        
        self.ent_api_hash = ctk.CTkEntry(self.frame_hash, placeholder_text="Telegram API Hash...", show="*", width=260)
        self.ent_api_hash.pack(side="left", fill="x", expand=True)
        
        self.btn_show_hash = ctk.CTkButton(self.frame_hash, text="👁️", width=45, fg_color="#34495e", hover_color="#2c3e50", command=self.toggle_hash_visibility)
        self.btn_show_hash.pack(side="right", padx=(5, 0))

        # Ô NHẬP 2FA CLOUD + NÚT 👁️ ẨN/HIỆN
        self.frame_two_step = ctk.CTkFrame(self.frame_tele_login, fg_color="transparent")
        self.frame_two_step.pack(pady=3, padx=10, fill="x")
        
        self.ent_two_step = ctk.CTkEntry(self.frame_two_step, placeholder_text="Mật khẩu 2FA Cloud (Nếu có)...", show="*", width=260)
        self.ent_two_step.pack(side="left", fill="x", expand=True)
        
        self.btn_show_two_step = ctk.CTkButton(self.frame_two_step, text="👁️", width=45, fg_color="#34495e", hover_color="#2c3e50", command=self.toggle_two_step_visibility)
        self.btn_show_two_step.pack(side="right", padx=(5, 0))

        # PHÂN CHIA TAB ĐĂNG NHẬP
        self.tab_login = ctk.CTkTabview(self.frame_tele_login, width=320, height=250)
        self.tab_login.pack(pady=5, padx=10)
        self.tab_login.add("📸 Cách 1: Quét mã QR")
        self.tab_login.add("📱 Cách 2: Nhập SĐT + OTP")

        # --- TAB 1: QUÉT MÃ QR INTERACTION ---
        tab_qr = self.tab_login.tab("📸 Cách 1: Quét mã QR")
        self.btn_gen_qr = ctk.CTkButton(tab_qr, text="🔍 PHÁT SINH MÃ QR ĐĂNG NHẬP", font=("Arial", 11, "bold"), fg_color="#34495e", hover_color="#2c3e50", command=self.trigger_generate_qr)
        self.btn_gen_qr.pack(pady=5, fill="x")
        self.lbl_qr_viewer = ctk.CTkLabel(tab_qr, text="[ KHUNG HIỂN THỊ MÃ QR ]\n(Ấn nút phát sinh để lấy mã)", width=140, height=140, fg_color="#111111", corner_radius=8)
        self.lbl_qr_viewer.pack(pady=5)

        # --- TAB 2: GIAO DIỆN NHẬP SĐT NHẬN OTP ---
        tab_phone = self.tab_login.tab("📱 Cách 2: Nhập SĐT + OTP")
        self.ent_phone = ctk.CTkEntry(tab_phone, placeholder_text="Số điện thoại (Ví dụ: +849123...)", width=280)
        self.ent_phone.pack(pady=5)
        self.btn_send_otp = ctk.CTkButton(tab_phone, text="📨 GỬI MÃ OTP VỀ MÁY", font=("Arial", 11, "bold"), fg_color="#34495e", hover_color="#2c3e50", command=self.trigger_send_otp)
        self.btn_send_otp.pack(pady=5, fill="x")
        self.ent_otp = ctk.CTkEntry(tab_phone, placeholder_text="Nhập mã 5 số OTP nhận được...", width=280)
        self.ent_otp.pack(pady=5)
        self.ent_otp.configure(state="disabled")
        self.btn_verify_otp = ctk.CTkButton(tab_phone, text="✅ XÁC NHẬN ĐĂNG NHẬP", font=("Arial", 11, "bold"), fg_color="#27ae60", hover_color="#2ecc71", command=self.trigger_verify_otp)
        self.btn_verify_otp.pack(pady=5, fill="x")
        self.btn_verify_otp.configure(state="disabled")

        # THÔNG TIN TELEGRAM HỖ TRỢ
        self.lbl_main_contact = ctk.CTkLabel(
            self.frame_tele_login, 
            text="💬 Hỗ trợ kỹ thuật: t.me/harukaiden", 
            font=("Arial", 11, "italic", "bold"), 
            text_color="#00FFFF",  
            cursor="hand2"         
        )
        self.lbl_main_contact.pack(pady=(5, 8), padx=10)
        self.lbl_main_contact.bind("<Button-1>", lambda event: webbrowser.open("https://t.me/harukaiden"))

        # KHUNG CẤU HÌNH LIÊN THÔNG SHOPEE
        self.frame_shopee_config = ctk.CTkFrame(self.frame_left, fg_color="transparent")
        self.frame_shopee_config.pack(fill="x")

        ctk.CTkFrame(self.frame_shopee_config, height=2, fg_color="#333333").pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.frame_shopee_config, text="📡 CẤU HÌNH MÃ", font=("Arial", 13, "bold"), text_color="#2ecc71").pack(pady=(5, 5), padx=10, anchor="w")

        self.ent_target_chat = ctk.CTkEntry(self.frame_shopee_config, placeholder_text="Link Nhóm Telegram (Cách nhau dấu phẩy)...", width=310)
        self.ent_target_chat.pack(pady=3, padx=10)
        self.ent_target_chat.insert(0, "t.me/nghienshopee")

        ctk.CTkLabel(self.frame_shopee_config, text="DÁN LIST MÃ VÀO BẢNG CHỜ:", font=("Arial", 11, "bold"), text_color="gray").pack(padx=10, anchor="w", pady=(8,0))
        self.txt_manual_codes = ctk.CTkTextbox(self.frame_shopee_config, height=110, width=310)
        self.txt_manual_codes.pack(pady=(2, 15), padx=10)

        self.btn_start = ctk.CTkButton(self.frame_shopee_config, text="▶ KHỞI ĐỘNG HỆ THỐNG", font=("Arial", 13, "bold"), fg_color="#27ae60", hover_color="#2ecc71", height=42, command=self.start_bot)
        self.btn_start.pack(pady=4, padx=10, fill="x")

        self.btn_stop = ctk.CTkButton(self.frame_shopee_config, text="■ DỪNG HỆ THỐNG", font=("Arial", 13, "bold"), fg_color="#c0392b", hover_color="#e74c3c", height=42, command=self.stop_bot)
        self.btn_stop.pack(pady=4, padx=10, fill="x")
        self.btn_stop.configure(state="disabled")

        # --- KHUNG PHẢI: KHUNG CUỘN CHỨA TOÀN BỘ GIÁM SÁT MẢNG PHẢI NGOÀI CÙNG ---
        self.frame_right = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.frame_right.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self.frame_current = ctk.CTkFrame(self.frame_right, fg_color="#1e272e", border_width=2, border_color="#2ecc71")
        self.frame_current.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(self.frame_current, text="🎯 MÃ ĐANG ĐƯỢC ĐIỀN VÀ ENTER TRÊN CHROME CHÍNH", font=("Arial", 11, "bold"), text_color="#2ecc71").pack(pady=(5,0))
        self.lbl_current_code = ctk.CTkLabel(self.frame_current, text="--- CHỜ MÃ ---", font=("Consolas", 32, "bold"), text_color="#f1c40f")
        self.lbl_current_code.pack(pady=10)

        self.frame_bar = ctk.CTkFrame(self.frame_right, fg_color="transparent")
        self.frame_bar.pack(fill="x", padx=15, pady=(5, 2))

        self.lbl_status = ctk.CTkLabel(self.frame_bar, text="Trạng thái: ĐANG TẮT", text_color="gray", font=("Arial", 13, "bold"))
        self.lbl_status.pack(side="left")

        self.lbl_counter = ctk.CTkLabel(self.frame_bar, text="Mã: 0/0", text_color="#00FFFF", font=("Arial", 13, "bold"))
        self.lbl_counter.pack(side="right")

        self.header_frame = ctk.CTkFrame(self.frame_right, fg_color="#1a1a1a", height=30)
        self.header_frame.pack(fill="x", padx=10, pady=(5, 0))
        self.header_frame.pack_propagate(False)
        
        ctk.CTkLabel(self.header_frame, text="No.", font=("Arial", 11, "bold"), text_color="gray", width=60, anchor="w").pack(side="left", padx=(15, 0))
        ctk.CTkLabel(self.header_frame, text="CODE VOUCHER (CLICK ĐỂ COPY)", font=("Arial", 11, "bold"), text_color="gray", width=250, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(self.header_frame, text="TRẠNG THÁI HỆ THỐNG", font=("Arial", 11, "bold"), text_color="gray", width=220, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(self.header_frame, text="TIME", font=("Arial", 11, "bold"), text_color="gray", width=100, anchor="w").pack(side="left", padx=10)

        # Hộp đen lớn chứa danh sách mã chờ
        self.grid_container = ctk.CTkFrame(self.frame_right, fg_color="#111111", height=450)
        self.grid_container.pack(fill="x", expand=True, padx=10, pady=(2, 5))

        ctk.CTkLabel(self.frame_right, text=" LOG HỆ THỐNG CONTROL", font=("Arial", 11, "bold"), text_color="gray").pack(anchor="w", padx=15, pady=(5,0))
        self.log_box = ctk.CTkTextbox(self.frame_right, height=120, font=("Consolas", 11), text_color="#00FF00", fg_color="#1e1e1e")
        self.log_box.pack(pady=(0, 5), padx=10, fill="x")

    def toggle_hash_visibility(self):
        if self.ent_api_hash.cget("show") == "*":
            self.ent_api_hash.configure(show="")
            self.btn_show_hash.configure(fg_color="#27ae60", hover_color="#2ecc71")
        else:
            self.ent_api_hash.configure(show="*")
            self.btn_show_hash.configure(fg_color="#34495e", hover_color="#2c3e50")

    def toggle_two_step_visibility(self):
        if self.ent_two_step.cget("show") == "*":
            self.ent_two_step.configure(show="")
            self.btn_show_two_step.configure(fg_color="#27ae60", hover_color="#2ecc71")
        else:
            self.ent_two_step.configure(show="*")
            self.btn_show_two_step.configure(fg_color="#34495e", hover_color="#2c3e50")

    def toggle_tele_frame(self):
        if self.tele_visible:
            self.frame_tele_login.pack_forget() 
            self.btn_toggle_tele.configure(text="👁️ HIỆN CẤU HÌNH TELEGRAM", fg_color="#27ae60", hover_color="#2ecc71")
            self.tele_visible = False
        else:
            self.frame_tele_login.pack(fill="x", pady=5, before=self.frame_shopee_config)
            self.btn_toggle_tele.configure(text="👁️ ẨN CẤU HÌNH TELEGRAM", fg_color="#2980b9", hover_color="#3498db")
            self.tele_visible = True

    def load_tool_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.ent_api_id.insert(0, config.get("api_id", ""))
                self.ent_api_hash.insert(0, config.get("api_hash", ""))
                self.ent_two_step.insert(0, config.get("two_step", ""))
                self.ent_phone.insert(0, config.get("phone", ""))
                if config.get("target_chats"):
                    self.ent_target_chat.delete(0, "end")
                    self.ent_target_chat.insert(0, config.get("target_chats", ""))
                self.saved_session_str = config.get("string_session", "")
                if self.saved_session_str:
                    self.lbl_qr_viewer.configure(image=None, text="✅ Đã nhớ thiết bị!\nCó thể thu gọn cấu hình.", text_color="#2ecc71")
                    self.log_to_ui("💾 Đã tải lại cấu hình cũ! Khách có thể bấm [KHỞI ĐỘNG HỆ THỐNG] luôn.")
            except Exception:
                pass

    def save_tool_config(self, api_id, api_hash, target_chats, string_session, two_step, phone=""):
        config = {
            "api_id": str(api_id),
            "api_hash": api_hash,
            "target_chats": target_chats,
            "string_session": string_session,
            "two_step": two_step,
            "phone": phone
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

    def ensure_login_loop(self):
        if not hasattr(self, 'login_loop') or self.login_loop is None:
            self.login_loop = asyncio.new_event_loop()
            def run_loop(loop):
                asyncio.set_event_loop(loop)
                loop.run_forever()
            threading.Thread(target=run_loop, args=(self.login_loop,), daemon=True).start()

    def trigger_generate_qr(self):
        self.ensure_login_loop()
        asyncio.run_coroutine_threadsafe(self._async_qr_workflow(), self.login_loop)

    async def _async_qr_workflow(self):
        try:
            api_id = int(self.ent_api_id.get().strip())
            api_hash = self.ent_api_hash.get().strip()
            two_step_pass = self.ent_two_step.get().strip()
            
            if not api_id or not api_hash:
                self.log_to_ui("❌ LỖI: Hãy điền đầy đủ API ID và API Hash trước khi phát sinh mã QR!")
                return

            self.log_to_ui("📡 Đang kết nối Server Telegram xin cấp mã QR liên kết...")
            self.temp_client = TelegramClient(StringSession(''), api_id, api_hash)
            await self.temp_client.connect()
            
            self.qr_login_state = await self.temp_client.qr_login()
            qr_img = qrcode.make(self.qr_login_state.url)
            qr_pil = qr_img.resize((140, 140)).convert("RGB")
            
            ctk_image = ctk.CTkImage(light_image=qr_pil, dark_image=qr_pil, size=(140, 140))
            self.after(0, lambda: self.lbl_qr_viewer.configure(image=ctk_image, text=""))
            self.log_to_ui("📸 ĐÃ TẠO MÃ QR THÀNH CÔNG! Hãy mở điện thoại quét liền tay (Mã sống 30 giây).")

            user = None
            try:
                user = await self.qr_login_state.wait(timeout=300)
            except SessionPasswordNeededError:
                self.log_to_ui("🔒 Tài khoản yêu cầu Mật khẩu đám mây cấp 2!")
                if not two_step_pass:
                    self.log_to_ui("❌ THẤT BẠI: Vui lòng điền Mật khẩu vào ô [Mật khẩu 2FA Cloud] ở phía trên rồi quét lại mã QR mới!")
                    self.after(0, lambda: self.lbl_qr_viewer.configure(image=None, text="🔒 Cần nhập mật khẩu\n2FA rồi quét lại!", text_color="#f1c40f"))
                    await self.temp_client.disconnect()
                    return
                else:
                    user = await self.temp_client.sign_in(password=two_step_pass)

            if user:
                self.saved_session_str = self.temp_client.session.save()
                raw_chats = self.ent_target_chat.get().strip()
                self.save_tool_config(api_id, api_hash, raw_chats, self.saved_session_str, two_step_pass)
                self.after(0, lambda: self.lbl_qr_viewer.configure(image=None, text="✅ QUÉT QR THÀNH CÔNG!", text_color="#2ecc71"))
                self.log_to_ui(f"🎉 Đăng nhập thành công tài khoản Telegram: {user.first_name}!")
            
            await self.temp_client.disconnect()
        except asyncio.TimeoutError:
            self.after(0, lambda: self.lbl_qr_viewer.configure(image=None, text="❌ Mã QR hết hạn!\nVui lòng thử lại.", text_color="#e74c3c"))
            self.log_to_ui("⏱️ Quá thời gian chờ quét mã QR.")
        except Exception as e:
            self.log_to_ui(f"❌ Lỗi phát sinh luồng QR: {e}")

    def trigger_send_otp(self):
        self.ensure_login_loop()
        asyncio.run_coroutine_threadsafe(self._async_send_otp(), self.login_loop)

    async def _async_send_otp(self):
        try:
            api_id = int(self.ent_api_id.get().strip())
            api_hash = self.ent_api_hash.get().strip()
            phone = self.ent_phone.get().strip()
            
            if not api_id or not api_hash or not phone:
                self.log_to_ui("❌ LỖI: Vui lòng nhập đầy đủ API ID, API Hash và Số điện thoại!")
                return

            self.log_to_ui("📡 Đang gửi yêu cầu mã xác thực tới hệ thống Telegram...")
            self.temp_client = TelegramClient(StringSession(''), api_id, api_hash)
            await self.temp_client.connect()
            
            send_code_res = await self.temp_client.send_code_request(phone)
            self.phone_code_hash = send_code_res.phone_code_hash
            
            self.log_to_ui("📩 Gửi mã OTP thành công! Hãy kiểm tra tin nhắn Telegram nhập code vào ô bên dưới.")
            self.after(0, lambda: self.ent_otp.configure(state="normal"))
            self.after(0, lambda: self.btn_verify_otp.configure(state="normal"))
        except Exception as e:
            self.log_to_ui(f"❌ Lỗi gửi OTP: {e}")

    def trigger_verify_otp(self):
        self.ensure_login_loop()
        asyncio.run_coroutine_threadsafe(self._async_verify_otp(), self.login_loop)

    async def _async_verify_otp(self):
        try:
            api_id = int(self.ent_api_id.get().strip())
            api_hash = self.ent_api_hash.get().strip()
            phone = self.ent_phone.get().strip()
            otp_code = self.ent_otp.get().strip()
            two_step_pass = self.ent_two_step.get().strip()

            self.log_to_ui("⏳ Đang xác thực OTP...")
            user = None
            try:
                user = await self.temp_client.sign_in(phone, otp_code, phone_code_hash=self.phone_code_hash)
            except SessionPasswordNeededError:
                self.log_to_ui("🔒 Tài khoản yêu cầu Mật khẩu đám mây cấp 2!")
                if not two_step_pass:
                    self.log_to_ui("❌ THẤT BẠI: Vui lòng điền Mật khẩu đám mây vào ô [Mật khẩu 2FA Cloud] ở phía trên rồi ấn xác nhận lại!")
                    await self.temp_client.disconnect()
                    return
                else:
                    user = await self.temp_client.sign_in(password=two_step_pass)

            if user:
                self.saved_session_str = self.temp_client.session.save()
                raw_chats = self.ent_target_chat.get().strip()
                self.save_tool_config(api_id, api_hash, raw_chats, self.saved_session_str, two_step_pass, phone)
                self.log_to_ui(f"🎉 ĐĂNG NHẬP SĐT THÀNH CÔNG! Đã liên kết tài khoản: {user.first_name}")
            
            await self.temp_client.disconnect()
        except Exception as e:
            self.log_to_ui(f"❌ Lỗi khớp mã xác thực: {e}")

    def start_bot(self):
        if not self.is_running:
            self.manual_codes_text = self.txt_manual_codes.get("1.0", "end-1c").strip()
            
            self.voucher_data.clear()
            self.voucher_counter = 0
            for widget in self.grid_container.winfo_children():
                widget.destroy()

            if self.manual_codes_text:
                matches = VOUCHER_REGEX.findall(self.manual_codes_text)
                for match in matches:
                    self.register_new_voucher_row(match, push_to_top=True)
                self.lbl_counter.configure(text=f"Mã: 0/{len(self.voucher_data)}")

            if not self.manual_codes_text:
                try:
                    self.api_id = int(self.ent_api_id.get().strip())
                    self.api_hash = self.ent_api_hash.get().strip()
                    
                    raw_chats = self.ent_target_chat.get().strip()
                    self.target_chats = [chat.strip() for chat in raw_chats.split(',') if chat.strip()]
                    
                    if not self.api_hash or len(self.target_chats) == 0:
                        self.log_to_ui("❌ LỖI: Vui lòng điền đủ API Telegram và Link nhóm mục tiêu!")
                        return
                except ValueError:
                    self.log_to_ui("❌ LỖI: API ID Telegram phải là số chuỗi.")
                    return
                if not self.saved_session_str:
                    self.log_to_ui("❌ LỖI: Chưa có dữ liệu đăng nhập Telegram! Hãy quét mã QR hoặc nhận OTP ở trên trước.")
                    return

            self.is_running = True
            self.btn_start.configure(state="disabled", text="⚡ SNIPER ACTIVE...", fg_color="#7f8c8d")
            self.btn_stop.configure(state="normal")
            
            self.ent_api_id.configure(state="disabled")
            self.ent_api_hash.configure(state="disabled")
            self.ent_two_step.configure(state="disabled")
            self.btn_gen_qr.configure(state="disabled")
            self.ent_phone.configure(state="disabled")
            self.btn_send_otp.configure(state="disabled")
            self.btn_verify_otp.configure(state="disabled")
            self.ent_otp.configure(state="disabled")
            self.ent_target_chat.configure(state="disabled")
            self.txt_manual_codes.configure(state="disabled")
            self.btn_show_hash.configure(state="disabled")
            self.btn_show_two_step.configure(state="disabled")
            self.lbl_status.configure(text="Trạng thái: AUTO ĐANG CHẠY", text_color="#2ecc71")
            
            threading.Thread(target=self.run_async_engine, daemon=True).start()

    def stop_bot(self):
        if self.is_running:
            self.is_running = False  
            
            self.btn_start.configure(state="normal", text="▶ KHỞI ĐỘNG HỆ THỐNG", fg_color="#27ae60")
            self.btn_stop.configure(state="disabled")
            self.ent_api_id.configure(state="normal")
            self.ent_api_hash.configure(state="normal")
            self.ent_two_step.configure(state="normal")
            self.btn_gen_qr.configure(state="normal")
            self.ent_phone.configure(state="normal")
            self.btn_send_otp.configure(state="normal")
            self.ent_target_chat.configure(state="normal")
            self.txt_manual_codes.configure(state="normal")
            self.btn_show_hash.configure(state="normal")
            self.btn_show_two_step.configure(state="normal")
            self.lbl_status.configure(text="Trạng thái: ĐÃ DỪNG HỖ TRỢ", text_color="#777777")
            self.log_to_ui("✅ Đã ra lệnh đóng liên thông trình duyệt an toàn!")

    def run_async_engine(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.core_workflow())
        except asyncio.CancelledError:
            pass

    def scroll_to_active_row(self, item_id):
        total = len(self.voucher_data)
        if total > 1:
            fraction = max(0.0, (item_id - 1) / total)
            try:
                self.frame_right._parent_canvas.yview_moveto(fraction)
            except Exception:
                pass

    def user_click_copy_trigger(self, code):
        pyperclip.copy(code)
        self.lbl_current_code.configure(text=code)
        self.log_to_ui(f"📋 Đã nhanh tay Copy mã vào Clipboard: {code}")

    # 🔥 ĐÃ SỬA: Hỗ trợ găm mã mới lên đầu bảng chờ (Vị trí số 1)
    def register_new_voucher_row(self, code, push_to_top=False):
        self.voucher_counter += 1
        now_time = datetime.now().strftime('%H:%M:%S')
        
        row_frame = ctk.CTkFrame(self.grid_container, fg_color="#1e1e1e", height=38, border_width=1, border_color="#2d2d2d")
        row_frame.pack_propagate(False)

        if push_to_top:
            children = self.grid_container.winfo_children()
            if children:
                row_frame.pack(fill="x", padx=5, pady=2, before=children[0])
            else:
                row_frame.pack(fill="x", padx=5, pady=2)
        else:
            row_frame.pack(fill="x", padx=5, pady=2)

        lbl_no = ctk.CTkLabel(row_frame, text=f"#{str(self.voucher_counter).zfill(2)}", font=("Arial", 12), text_color="#888888", width=60, anchor="w")
        lbl_no.pack(side="left", padx=(15, 0))

        lbl_code = ctk.CTkLabel(row_frame, text=code, font=("Consolas", 14, "bold"), text_color="#f1c40f", width=250, anchor="w", cursor="hand2")
        lbl_code.pack(side="left", padx=10)
        lbl_code.bind("<Button-1>", lambda event, c=code: self.user_click_copy_trigger(c))

        lbl_status = ctk.CTkLabel(row_frame, text="o  Chờ lệnh...", font=("Arial", 12), text_color="#a5b1c2", width=220, anchor="w")
        lbl_status.pack(side="left", padx=10)

        lbl_time = ctk.CTkLabel(row_frame, text=now_time, font=("Arial", 12), text_color="#777777", width=100, anchor="w")
        lbl_time.pack(side="left", padx=10)

        item_dict = {
            "id": self.voucher_counter,
            "code": code,
            "time": now_time,
            "frame": row_frame,
            "status_lbl": lbl_status
        }
        self.voucher_data.append(item_dict)
        return item_dict

    def set_row_ui_active(self, item_id, code):
        self.lbl_current_code.configure(text=code)
        total = len(self.voucher_data)
        self.lbl_counter.configure(text=f"Mã: {item_id}/{total}")
        for item in self.voucher_data:
            if item["id"] == item_id:
                item["frame"].configure(fg_color="#1b3a24", border_color="#2ecc71", border_width=1)
                item["status_lbl"].configure(text="▶ Đang nhập...", text_color="#00FFFF")
                break
        self.after(10, self.scroll_to_active_row, item_id)

    def set_row_ui_completed(self, item_id, status_msg, is_success):
        for item in self.voucher_data:
            if item["id"] == item_id:
                item["frame"].configure(fg_color="#141414", border_color="#2d2d2d", border_width=1)
                if is_success:
                    item["status_lbl"].configure(text=f"✓ {status_msg}", text_color="#2ecc71")
                else:
                    item["status_lbl"].configure(text=f"✕ {status_msg}", text_color="#e74c3c")
                break

    # === 🔥 ĐÃ FIX TUYỆT ĐỐI: CHỈ LIÊN THÔNG VÀO TAB CHROME ĐANG MỞ — KHÔNG TỰ CHẠY APP PHỤ ===
    async def playwright_worker(self, queue):
        voucher_input_selector = 'input[placeholder*="voucher"], input[placeholder*="Voucher"], input[placeholder*="mã"], input[type="text"]'
        
        async with async_playwright() as p:
            self.log_to_ui("🔌 Đang liên thông kết nối vào cổng Chrome Debug ông đang mở sẵn (127.0.0.1:9222)...")
            try:
                # Móc trực tiếp qua cổng CDP, KHÔNG gọi lệnh subprocess khởi tạo profile rác
                self.browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                
                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = await self.browser.new_context()
                
                # Quét mọi tab trên trình duyệt tìm đúng trang Ví Voucher Shopee của ông
                page = None
                for open_page in self.context.pages:
                    if "user/voucher-wallet" in open_page.url:
                        page = open_page
                        break
                
                if page:
                    self.log_to_ui("🎯 Đã bắt trúng tiêu điểm tab Ví Voucher! Khóa mục tiêu.")
                    await page.bring_to_front() 
                else:
                    shopee_page = None
                    for open_page in self.context.pages:
                        if "shopee.vn" in open_page.url:
                            shopee_page = open_page
                            break
                    if shopee_page:
                        page = shopee_page
                        self.log_to_ui("🔄 Phát hiện tab Shopee thường, đang chuyển hướng sang trang Ví Voucher...")
                        await page.goto('https://shopee.vn/user/voucher-wallet?sort=1&type=0', wait_until='networkidle')
                    else:
                        self.log_to_ui("🌐 Không tìm thấy tab Shopee nào. Đang tự mở trang Ví Voucher trên tab mới...")
                        page = await self.context.new_page()
                        await page.goto('https://shopee.vn/user/voucher-wallet?sort=1&type=0', wait_until='networkidle')
                
                self.log_to_ui("🔥 LIÊN THÔNG CHROME ĐANG DÙNG THÀNH CÔNG - HỆ THỐNG READY 🔥")
            except Exception as e:
                self.log_to_ui(f"❌ THẤT BẠI: Không tìm thấy Chrome Debug! Vui lòng cài cờ --remote-debugging-port=9222 vào shortcut Chrome. Lỗi: {e}")
                self.after(0, self.stop_bot)
                return

            was_processing = False
            try:
                while self.is_running:
                    try:
                        item_dict = await asyncio.wait_for(queue.get(), timeout=1.0)
                        was_processing = True
                    except asyncio.TimeoutError:
                        if was_processing:
                            self.log_to_ui("🚨 HỆ THỐNG CONTROL: Đã chạy hết mã trong danh sách!")
                            was_processing = False
                        continue
                    
                    voucher_code = item_dict["code"]
                    item_id = item_dict["id"]
                    
                    self.after(0, self.set_row_ui_active, item_id, voucher_code)
                    
                    # === 🔥 ĐÃ FIX: ĐỘ HỆ THỐNG LOG THEO ĐÚNG KHUÔN MẪU MMO THỜI GIAN THỰC ===
                    self.log_to_ui("🚀 1 mã | delay 40ms | Playwright Direct")
                    start_time = time.time()
                    
                    clean_msg = "Xử lý xong"
                    is_success = True
                    
                    try:
                        if "user/voucher-wallet" not in page.url:
                            self.log_to_ui("⚠️ Cảnh báo: Chrome chưa ở trang Ví Voucher! Đang treo luồng đợi ông...")
                            while "user/voucher-wallet" not in page.url and self.is_running:
                                await asyncio.sleep(1)
                            if not self.is_running: break
                            self.log_to_ui("🎯 Đã khóa lại mục tiêu trang Ví Voucher!")

                        input_field = page.locator(voucher_input_selector).first
                        await input_field.wait_for(timeout=4000)
                        
                        await input_field.click()
                        await page.keyboard.press('Control+A')
                        await page.keyboard.press('Backspace')
                        
                        await page.keyboard.type(voucher_code, delay=40)
                        await asyncio.sleep(0.2)
                        
                        result = None
                        try:
                            async with page.expect_response(lambda res: SHOPEE_API_URL in res.url, timeout=3000) as res_info:
                                await page.keyboard.press('Enter')
                            response = await res_info.value
                            result = await response.json()
                        except Exception:
                            await page.keyboard.press('Enter')

                        if result:
                            error_code = result.get("error", -1)
                            error_msg = result.get("error_msg", "").strip()
                            data_res = result.get("data", {})
                            msg_status = data_res.get("msg_status", "") if data_res else ""
                            
                            if "fully redeemed" in error_msg.lower() or "hết lượt" in error_msg.lower():
                                clean_msg = "Hết lượt"
                                is_success = False
                            elif "not exist" in error_msg.lower() or "không tồn tại" in error_msg.lower() or "invalid" in error_msg.lower():
                                clean_msg = "Không tồn tại"
                                is_success = False
                            elif error_code == 0 and (error_msg == "Thành công" or error_msg == ""):
                                clean_msg = "Thành công vào ví!"
                                is_success = True
                            elif error_msg:
                                clean_msg = error_msg[:18]
                                is_success = False
                            elif msg_status:
                                clean_msg = msg_status[:18]
                                is_success = False
                            else:
                                clean_msg = f"Lỗi: {error_code}"
                                is_success = False
                        else:
                            clean_msg = "Đã ấn Enter"
                            is_success = True
                            
                        # Tính toán và xuất log tổng kết đúng tiến trình giây
                        elapsed = time.time() - start_time
                        status_icon = "✅" if is_success else "❌"
                        self.log_to_ui(f"{status_icon} {voucher_code}: {clean_msg}")
                        
                        succ_count = "1" if is_success else "0"
                        fail_count = "0" if is_success else "1"
                        self.log_to_ui(f"🏁 1 mã | {elapsed:.1f}s | ✅ {succ_count} ❌ {fail_count}")
                    except Exception as e:
                        clean_msg = "Lỗi UI Trình Duyệt"
                        is_success = False
                        elapsed = time.time() - start_time
                        self.log_to_ui(f"❌ {voucher_code}: {clean_msg}")
                        self.log_to_ui(f"🏁 1 mã | {elapsed:.1f}s | ✅ 0 ❌ 1")

                    self.after(0, self.set_row_ui_completed, item_id, clean_msg, is_success)
                    queue.task_done()
                    await asyncio.sleep(1.2) 
            finally:
                pass

    async def core_workflow(self):
        self.async_queue = asyncio.Queue()
        
        for item in self.voucher_data:
            await self.async_queue.put(item)

        asyncio.create_task(self.playwright_worker(self.async_queue))

        if not self.manual_codes_text:
            self.log_to_ui("📡 Kích hoạt: LẮNG NGHE TELEGRAM REAL-TIME BẰNG STRING SESSION")
            self.client = TelegramClient(StringSession(self.saved_session_str), self.api_id, self.api_hash)
            
            @self.client.on(events.NewMessage(chats=self.target_chats))
            async def handler(event):
                if not self.is_running: return
                for match in VOUCHER_REGEX.findall(event.raw_text):
                    self.log_to_ui(f"📡 Tele rớt mã mới: {match}")
                    self.after(0, self.handle_incoming_tele_match, match)

            await self.client.start()
            self.log_to_ui("✅ Trợ lý Kaiden kết nối nhận sóng Telegram thành công!")
            
            self.log_to_ui("🔄 Đang quét nhanh tin nhắn cũ để hốt mã sót...")
            for chat in self.target_chats:
                try:
                    async_messages = self.client.iter_messages(chat, limit=10)
                    async for message in async_messages:
                        if not self.is_running: break
                        if message.text:
                            matches = VOUCHER_REGEX.findall(message.text)
                            for match in matches:
                                self.log_to_ui(f"🔍 Phát hiện mã cũ chưa cày: {match}")
                                self.after(0, self.handle_incoming_tele_match, match)
                except Exception as e:
                    self.log_to_ui(f"⚠️ Không thể quét tin cũ của nhóm {chat}: {e}")
            
            if self.is_running:
                self.log_to_ui("⚡ Đã quét xong tin nhắn cũ! Hệ thống chuyển sang chế độ CHỜ MÃ REAL-TIME...")

            while self.is_running:
                await asyncio.sleep(1)
            try:
                await self.client.disconnect()
            except Exception:
                pass
        else:
            self.log_to_ui("🎯 Đang chạy danh sách mã thủ công...")
            while self.is_running and any(x["status_lbl"].cget("text").startswith("o") or x["status_lbl"].cget("text").startswith("▶") for x in self.voucher_data):
                await asyncio.sleep(1)

    def handle_incoming_tele_match(self, code):
        item_dict = self.register_new_voucher_row(code, push_to_top=True)
        total = len(self.voucher_data)
        self.lbl_counter.configure(text=f"Mã: 0/{total}")
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.async_queue.put_nowait, item_dict)

    def log_to_ui(self, message):
        msg = f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n"
        self.after(0, self._append_textbox, self.log_box, msg)

    def _append_textbox(self, textbox, text):
        textbox.configure(state="normal")
        textbox.insert("end", text)
        textbox.see("end")
        textbox.configure(state="disabled")

# ==========================================
# CỬA SỔ LOGIN BẢN QUYỀN
# ==========================================
class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KÍCH HOẠT HỆ THỐNG")
        self.geometry("450x320") 
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self.setup_ui()

    def setup_ui(self):
        ctk.CTkLabel(self, text="HỆ THỐNG BẢO MẬT KAIDEN", font=("Arial", 16, "bold"), text_color="#2ecc71").pack(pady=15)
        
        ctk.CTkLabel(self, text="Mã Máy Của Bạn (HWID):", font=("Arial", 11)).pack(anchor="w", padx=35)
        self.ent_hwid = ctk.CTkEntry(self, width=380, font=("Consolas", 11))
        self.ent_hwid.pack(pady=(2, 10), padx=35)
        self.ent_hwid.insert(0, get_hwid())
        self.ent_hwid.configure(state="readonly")

        ctk.CTkLabel(self, text="Nhập Cấp Quyền License Key:", font=("Arial", 11)).pack(anchor="w", padx=35)
        self.ent_key = ctk.CTkEntry(self, placeholder_text="Dán Activation Key từ Admin...", show="*", width=380)
        self.ent_key.pack(pady=(2, 15), padx=35)

        self.lbl_msg = ctk.CTkLabel(self, text="", font=("Arial", 11, "bold"))
        self.lbl_msg.pack(pady=2)

        self.btn_login = ctk.CTkButton(self, text="ĐĂNG NHẬP HỆ THỐNG", font=("Arial", 12, "bold"), height=35, command=self.check_license)
        self.btn_login.pack(pady=5, padx=35, fill="x")

        self.lbl_contact = ctk.CTkLabel(
            self, 
            text="💬 Liên hệ Tele: t.me/harukaiden", 
            font=("Arial", 11, "italic", "bold"), 
            text_color="#00FFFF",  
            cursor="hand2"         
        )
        self.lbl_contact.pack(pady=(12, 5))
        self.lbl_contact.bind("<Button-1>", lambda event: self.open_telegram_link())

    def open_telegram_link(self):
        webbrowser.open("https://t.me/harukaiden")

    def check_license(self):
        my_hwid = get_hwid()
        user_key = self.ent_key.get().strip()
        
        is_valid, msg = validate_license(my_hwid, user_key)
        if is_valid:
            self.lbl_msg.configure(text=msg, text_color="#2ecc71")
            self.after(1000, self.open_main_app)
        else:
            self.lbl_msg.configure(text=msg, text_color="#e74c3c")

    def open_main_app(self):
        self.destroy()
        main_app = VoucherSniperApp()
        main_app.mainloop()

if __name__ == "__main__":
    login_app = LoginWindow()
    login_app.mainloop()