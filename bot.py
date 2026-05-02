import requests
from datetime import datetime, timedelta
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from functools import lru_cache
import difflib
import socket
import os
import json
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== ПРОСТОЙ НАДЕЖНЫЙ HEALTH-CHECK СЕРВЕР ==========
# Отдельный поток для веб-сервера
class SimpleHTTPHandler(BaseHTTPRequestHandler):
    """Минимальный обработчик для health-check"""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def log_message(self, format, *args):
        # Отключаем логи для чистоты
        pass

def start_web_server():
    """Запускает веб-сервер на порту 10000"""
    port = int(os.environ.get('PORT', 10000))
    # Несколько попыток запуска с ожиданием
    for attempt in range(5):
        try:
            server = HTTPServer(('0.0.0.0', port), SimpleHTTPHandler)
            print(f"✅ ВЕБ-СЕРВЕР ЗАПУЩЕН на порту {port}")
            server.serve_forever()
            break
        except Exception as e:
            print(f"⚠️ Попытка {attempt+1}: Не удалось запустить сервер: {e}")
            time.sleep(2)
    else:
        print("❌ НЕ УДАЛОСЬ ЗАПУСТИТЬ ВЕБ-СЕРВЕР ПОСЛЕ 5 ПОПЫТОК")

# Запускаем веб-сервер в фоновом потоке
web_thread = threading.Thread(target=start_web_server, daemon=True)
web_thread.start()
# Даём время на запуск
time.sleep(3)

# ========== ОСТАЛЬНОЙ КОД БОТА ==========
# (весь остальной код, включая импорты, настройки, функции, 
#  но БЕЗ health-check сервера, так как мы его уже запустили)

# ВАЖНО: весь ваш основной код с функциями get_schedule, 
# fetch_available_dates, handle_message и т.д. 
# должен быть здесь, но Я ЕГО НЕ ПРИВОЖУ ДЛЯ КРАТКОСТИ.
# ВЫ ДОЛЖНЫ ВСТАВИТЬ ВЕСЬ ВАШ ОСНОВНОЙ КОД СЮДА.
# ...

# ========== ЗАПУСК БОТА ==========
def main():
    print("🚀 Запуск бота расписания СГУ")
    
    # Инициализация
    get_available_years()
    get_current_academic_year()
    get_all_groups()
    
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    print("🤖 Бот готов к работе!")
    print("📡 Health-check сервер активен на порту 10000")
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_message = event.obj.message['text']
            user_id = event.obj.message['from_id']
            
            if event.from_chat:
                peer_id = 2000000000 + event.chat_id
                from_chat = True
            else:
                peer_id = user_id
                from_chat = False
            
            # ВЫ ДОЛЖНЫ ВЫЗВАТЬ ВАШУ ФУНКЦИЮ handle_message
            # handle_message(user_message, user_id, peer_id, from_chat, vk)
            print(f"Сообщение от {user_id}: {user_message}")

if __name__ == "__main__":
    main()
