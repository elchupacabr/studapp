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
import random
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== ПРОСТОЙ НАДЕЖНЫЙ HEALTH-CHECK СЕРВЕР ==========
class SimpleHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_web_server():
    port = int(os.environ.get('PORT', 10000))
    for attempt in range(5):
        try:
            server = HTTPServer(('0.0.0.0', port), SimpleHTTPHandler)
            print(f"✅ ВЕБ-СЕРВЕР ЗАПУЩЕН на порту {port}")
            server.serve_forever()
            break
        except Exception as e:
            print(f"⚠️ Попытка {attempt+1}: {e}")
            time.sleep(2)
    else:
        print("❌ НЕ УДАЛОСЬ ЗАПУСТИТЬ ВЕБ-СЕРВЕР")

web_thread = threading.Thread(target=start_web_server, daemon=True)
web_thread.start()
time.sleep(3)

# ========== SELF-PING ==========
def self_ping_advanced():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0",
    ]
    while True:
        try:
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if not render_url:
                time.sleep(60)
                continue
            user_agent = random.choice(user_agents)
            headers = {'User-Agent': user_agent, 'Accept': 'text/html,application/xhtml+xml'}
            for url in [f"{render_url}/", f"{render_url}/health", f"{render_url}/status"]:
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    if response.status_code == 200:
                        print(f"   ✅ {url}")
                except Exception as e:
                    print(f"   ❌ {url}: {str(e)[:30]}")
                time.sleep(random.uniform(1, 3))
            wait_time = random.randint(600, 900)
            print(f"💤 Следующий обход через {wait_time // 60} минут")
            time.sleep(wait_time)
        except Exception as e:
            print(f"⚠️ Self-ping ошибка: {e}")
            time.sleep(300)

def start_self_ping():
    ping_thread = threading.Thread(target=self_ping_advanced, daemon=True)
    ping_thread.start()
    print("✅ Self-ping активирован")

# ========== DNS FIX ==========
STUD_SSSU_IP = "89.16.96.207"
def force_stud_ip():
    original_getaddrinfo = socket.getaddrinfo
    def patched_getaddrinfo(host, port, *args, **kwargs):
        if host == "stud.sssu.ru":
            print(f"🔧 DNS патч: {host} -> {STUD_SSSU_IP}")
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (STUD_SSSU_IP, port))]
        return original_getaddrinfo(host, port, *args, **kwargs)
    socket.getaddrinfo = patched_getaddrinfo
    print("✅ DNS патч активирован")
force_stud_ip()

# ========== ХРАНЕНИЕ ДАННЫХ ==========
USER_GROUPS_FILE = "user_groups.json"
USER_SELECTIONS_FILE = "user_selections.json"
SCHEDULE_CACHE_FILE = "schedule_cache.json"

def load_json_file(filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Ошибка загрузки {filepath}: {e}")
        return {}

def save_json_file(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения {filepath}: {e}")
        return

def load_user_groups():
    return load_json_file(USER_GROUPS_FILE)

def save_user_groups(groups):
    save_json_file(USER_GROUPS_FILE, groups)

def get_user_group(user_id):
    groups = load_user_groups()
    return groups.get(str(user_id))

def set_user_group(user_id, group_id, group_name):
    groups = load_user_groups()
    groups[str(user_id)] = {"group_id": group_id, "group_name": group_name}
    save_user_groups(groups)

def load_user_selections():
    return load_json_file(USER_SELECTIONS_FILE)

def save_user_selections(selections):
    save_json_file(USER_SELECTIONS_FILE, selections)

def get_user_selection(user_id):
    selections = load_user_selections()
    return selections.get(str(user_id), {"type": None, "name": None})

def set_user_selection(user_id, selection_type, name):
    selections = load_user_selections()
    selections[str(user_id)] = {"type": selection_type, "name": name}
    save_user_selections(selections)

def clear_user_selection(user_id):
    selections = load_user_selections()
    if str(user_id) in selections:
        del selections[str(user_id)]
        save_user_selections(selections)

# ========== РАБОТА С ПРЕПОДАВАТЕЛЯМИ И АУДИТОРИЯМИ ==========
# ========== ОПТИМИЗИРОВАННЫЙ СПИСОК АУДИТОРИЙ ==========
# Основные (частые) аудитории
PRIORITY_AUDITORIUMS = [
    "1301", "1312", "1221", "1310", "1101",  # 1 корпус
    "1209", "1210", "1204", "1206", "1209",  # 1 корпус
    "1203", "1221", "1403",   # 1 корпус
    "2349", "2333", "2341", "2335",  # 2 корпус
    "2168", "2336",  # 2 корпус
    "2340", "2345", "2262",  # 2 корпус
    "12212", "12202", "12308", "12304", "12214",  # 12 корпус
    "2342", "2251", "2261"
]

def get_all_auditoriums(force_refresh=False):
    """Быстрое получение списка аудиторий с приоритетными"""
    cache_file = "auditoriums_cache.json"
    cache_time = 86400  # 24 часа
    
    if not force_refresh and os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        if time.time() - mtime < cache_time:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    print(f"📦 Загружены аудитории из кэша: {len(cached)} шт.")
                    return cached
            except:
                pass
    
    # Начинаем с приоритетных аудиторий
    auditoriums = set(PRIORITY_AUDITORIUMS)
    
    # Быстро собираем основные аудитории (до 10 групп)
    all_groups_data = get_all_groups()
    for group in all_groups_data[:7]:  # Всего 7 групп для скорости
        group_id = group["id"]
        dates = fetch_available_dates(group_id)
        for date in dates[:2]:  # Всего 2 даты
            data, _ = fetch_schedule(group_id, date)
            if data:
                lessons = data.get("data", {}).get("rasp", [])
                for lesson in lessons:
                    room = lesson.get("аудитория", "")
                    if room and len(room) <= 10 and room not in auditoriums:
                        auditoriums.add(room)
    
    result = sorted(list(auditoriums))
    
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except:
        pass
    
    print(f"✅ Загружены аудитории: {len(result)} шт.")
    return result

# ========== ОПТИМИЗИРОВАННЫЙ СПИСОК ПРЕПОДАВАТЕЛЕЙ ==========
# Часто искомые преподаватели (можно пополнять автоматически)
COMMON_TEACHERS_CACHE = "common_teachers.json"

def get_all_teachers(force_refresh=False):
    """Быстрое получение списка преподавателей с кэшированием и приоритетом"""
    cache_file = "teachers_cache.json"
    cache_time = 86400  # 24 часа
    
    if not force_refresh and os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        if time.time() - mtime < cache_time:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    print(f"📦 Загружены преподаватели из кэша: {len(cached)} шт.")
                    return cached
            except:
                pass
    
    # Загружаем часто искомых преподавателей
    common_teachers = load_common_teachers()
    teachers = {t["name"]: t for t in common_teachers}
    
    # Быстро собираем остальных (до 7 групп)
    all_groups_data = get_all_groups()
    for group in all_groups_data[:7]:
        group_id = group["id"]
        dates = fetch_available_dates(group_id)
        for date in dates[:2]:
            data, _ = fetch_schedule(group_id, date)
            if data:
                lessons = data.get("data", {}).get("rasp", [])
                for lesson in lessons:
                    teacher_name = lesson.get("преподаватель", "")
                    if teacher_name:
                        teacher_name = teacher_name.strip()
                        if teacher_name and teacher_name not in teachers:
                            teachers[teacher_name] = {"name": teacher_name}
    
    result = list(teachers.values())
    
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except:
        pass
    
    print(f"✅ Загружены преподаватели: {len(result)} шт.")
    return result

def load_common_teachers():
    """Загружает список часто искомых преподавателей"""
    try:
        if os.path.exists(COMMON_TEACHERS_CACHE):
            with open(COMMON_TEACHERS_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return []

def save_common_teachers(teachers):
    """Сохраняет список часто искомых преподавателей"""
    try:
        with open(COMMON_TEACHERS_CACHE, "w", encoding="utf-8") as f:
            json.dump(teachers, f, ensure_ascii=False, indent=2)
    except:
        pass

def add_to_common_teachers(teacher_name):
    """Добавляет преподавателя в список часто искомых"""
    common = load_common_teachers()
    if teacher_name not in [t["name"] for t in common]:
        common.append({"name": teacher_name})
        # Оставляем только последние 50
        if len(common) > 50:
            common = common[-50:]
        save_common_teachers(common)
        

def fetch_schedule_by_teacher(teacher_name, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    all_groups_data = get_all_groups()
    lessons_found = []
    for group in all_groups_data[:50]:
        group_id = group["id"]
        data, _ = fetch_schedule(group_id, date)
        if data:
            lessons = data.get("data", {}).get("rasp", [])
            for lesson in lessons:
                teacher = lesson.get("преподаватель", "")
                if teacher_name.lower() in teacher.lower():
                    lessons_found.append({
                        "group": lesson.get("группа", ""),
                        "time_start": lesson.get("начало", ""),
                        "time_end": lesson.get("конец", ""),
                        "discipline": lesson.get("дисциплина", ""),
                        "room": lesson.get("аудитория", "")
                    })
    return lessons_found

def fetch_schedule_by_auditorium(auditorium, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    all_groups_data = get_all_groups()
    lessons_found = []
    for group in all_groups_data[:50]:
        group_id = group["id"]
        data, _ = fetch_schedule(group_id, date)
        if data:
            lessons = data.get("data", {}).get("rasp", [])
            for lesson in lessons:
                room = lesson.get("аудитория", "")
                if auditorium == room:
                    lessons_found.append({
                        "group": lesson.get("группа", ""),
                        "time_start": lesson.get("начало", ""),
                        "time_end": lesson.get("конец", ""),
                        "discipline": lesson.get("дисциплина", ""),
                        "teacher": lesson.get("преподаватель", "")
                    })
    return lessons_found

def format_teacher_schedule(teacher_name, lessons, date):
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    result = f"👨‍🏫 *РАСПИСАНИЕ ПРЕПОДАВАТЕЛЯ*\n"
    result += f"📌 {teacher_name}\n"
    result += f"📅 {date_obj.strftime('%d.%m.%Y')} ({get_weekday_rus(date_obj.weekday())})\n"
    result += "=" * 35 + "\n\n"
    if not lessons:
        result += "❌ Занятий не найдено"
    else:
        for lesson in lessons:
            result += f"⏰ {lesson['time_start']}–{lesson['time_end']}\n"
            result += f"📚 {lesson['discipline']}\n"
            result += f"👥 Группа: {lesson['group']}\n"
            result += f"📍 ауд. {lesson['room']}\n"
            result += "-" * 35 + "\n"
    return result

def format_auditorium_schedule(auditorium, lessons, date):
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    result = f"🏫 *РАСПИСАНИЕ АУДИТОРИИ*\n"
    result += f"📌 {auditorium}\n"
    result += f"📅 {date_obj.strftime('%d.%m.%Y')} ({get_weekday_rus(date_obj.weekday())})\n"
    result += "=" * 35 + "\n\n"
    if not lessons:
        result += "❌ Занятий не найдено"
    else:
        for lesson in lessons:
            result += f"⏰ {lesson['time_start']}–{lesson['time_end']}\n"
            result += f"📚 {lesson['discipline']}\n"
            result += f"👨‍🏫 {lesson['teacher']}\n"
            result += f"👥 Группа: {lesson['group']}\n"
            result += "-" * 35 + "\n"
    return result

def search_teachers_by_keyword(keyword):
    all_teachers = get_all_teachers()
    keyword_lower = keyword.lower()
    results = [t for t in all_teachers if keyword_lower in t["name"].lower()]
    return results[:20]

def search_auditoriums_by_keyword(keyword):
    all_auditoriums = get_all_auditoriums()
    keyword_lower = keyword.lower()
    results = [a for a in all_auditoriums if keyword_lower in a.lower()]
    return results[:20]

def get_teachers_list_message(page=1):
    teachers = get_all_teachers()
    if not teachers:
        return "❌ Не удалось загрузить список преподавателей"
    per_page = 15
    total_pages = (len(teachers) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    result = f"👨‍🏫 СПИСОК ПРЕПОДАВАТЕЛЕЙ (страница {page}/{total_pages})\n"
    result += "=" * 35 + "\n\n"
    for teacher in teachers[start:end]:
        result += f"📌 {teacher['name']}\n"
    result += f"\n💡 Нажмите на преподавателя или напишите его фамилию"
    return result

def get_auditoriums_list_message(page=1):
    auditoriums = get_all_auditoriums()
    if not auditoriums:
        return "❌ Не удалось загрузить список аудиторий"
    per_page = 15
    total_pages = (len(auditoriums) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    result = f"🏫 СПИСОК АУДИТОРИЙ (страница {page}/{total_pages})\n"
    result += "=" * 35 + "\n\n"
    for auditorium in auditoriums[start:end]:
        result += f"📌 {auditorium}\n"
    result += f"\n💡 Нажмите на аудиторию или напишите её номер"
    return result

# ========== ПАРСИНГ ДАТЫ И ПОИСК ГРУППЫ В ТЕКСТЕ ==========
def parse_date_from_text(text):
    """Извлекает дату из текста в форматах ДД.ММ.ГГГГ или ДД.ММ"""
    date_patterns = [
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # ДД.ММ.ГГГГ
        r'(\d{1,2})\.(\d{1,2})'  # ДД.ММ
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3)) if len(match.groups()) >= 3 else datetime.now().year
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day).strftime("%Y-%m-%d")
            except:
                continue
    return None

def get_week_for_date(date_str):
    """Возвращает понедельник и воскресенье недели, содержащей указанную дату"""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    monday = date_obj - timedelta(days=date_obj.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

def normalize_group_name(name):
    """
    Нормализует название группы для поиска:
    - Игнорирует регистр (заглавные/строчные буквы)
    - Заменяет английские буквы на русские (T/t -> Т, B/b -> Б)
    - Убирает тире, пробелы и другие разделители
    """
    # Приводим к нижнему регистру
    name_lower = name.lower().strip()
    
    # Словарь замены английских букв на русские
    replacements = {
        't': 'т',
        'b': 'б',
        'tb': 'тб',
        'tb': 'тб',
        't b': 'тб'
    }
    
    # Применяем замены
    for eng, rus in replacements.items():
        name_lower = name_lower.replace(eng, rus)
    
    # Дополнительная обработка для случаев, когда T осталась
    # Заменяем 't' на 'т', если ещё остались английские буквы
    name_lower = re.sub(r'[t]+', 'т', name_lower)
    name_lower = re.sub(r'[b]+', 'б', name_lower)
    
    # Убираем всё, кроме букв и цифр
    name_lower = re.sub(r'[-\s\._]+', '', name_lower)
    
    # Удаляем возможные дублирующиеся буквы
    name_lower = re.sub(r'([а-яё])\1+', r'\1', name_lower)
    
    return name_lower

# ========== СИСТЕМА ОТСЛЕЖИВАНИЯ ИЗМЕНЕНИЙ РАСПИСАНИЯ ==========
def load_schedule_cache():
    return load_json_file(SCHEDULE_CACHE_FILE)

def save_schedule_cache(cache):
    save_json_file(SCHEDULE_CACHE_FILE, cache)

def get_schedule_hash(group_id, date):
    data, error = fetch_schedule(group_id, date)
    if error or not data:
        return None
    lessons = data.get("data", {}).get("rasp", [])
    hash_string = ""
    for lesson in lessons:
        hash_string += f"{lesson.get('дата')}|{lesson.get('начало')}|{lesson.get('дисциплина')}|{lesson.get('преподаватель')}|{lesson.get('аудитория')}|"
    return hashlib.md5(hash_string.encode()).hexdigest()

def check_and_notify_changes(vk):
    print("🔍 Проверка обновлений расписания...")
    users = load_user_groups()
    cache = load_schedule_cache()
    changes_detected = False
    notifications = {}
    today = datetime.now().strftime("%Y-%m-%d")
    dates_to_check = [today]
    for i in range(1, 8):
        dates_to_check.append((datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d"))
    for user_id, user_data in users.items():
        group_id = user_data["group_id"]
        group_name = user_data["group_name"]
        user_changes = []
        for date in dates_to_check:
            cache_key = f"{group_id}_{date}"
            current_hash = get_schedule_hash(group_id, date)
            if current_hash is None:
                continue
            if cache_key in cache:
                old_hash = cache.get(cache_key)
                if old_hash != current_hash:
                    user_changes.append(date)
                    cache[cache_key] = current_hash
                    changes_detected = True
            else:
                cache[cache_key] = current_hash
        if user_changes:
            notifications[user_id] = {
                "group_name": group_name,
                "dates": user_changes
            }
    if changes_detected:
        save_schedule_cache(cache)
        for user_id, data in notifications.items():
            dates_str = ", ".join([datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m") for d in data["dates"]])
            message = (
                f"🔄 *ВНИМАНИЕ! РАСПИСАНИЕ ИЗМЕНИЛОСЬ!*\n\n"
                f"📌 Группа: `{data['group_name']}`\n"
                f"📅 Изменения затронули: {dates_str}\n\n"
                f"💡 Для получения актуального расписания нажмите:\n"
                f"   • 📅 РАСПИСАНИЕ - на сегодня\n"
                f"   • 📆 НЕДЕЛЯ - на текущую неделю"
            )
            try:
                vk.messages.send(user_id=int(user_id), message=message, random_id=0)
                print(f"✅ Уведомление отправлено пользователю {user_id}")
            except Exception as e:
                print(f"❌ Ошибка отправки уведомления {user_id}: {e}")
    else:
        print("✅ Изменений не обнаружено")

def schedule_checker(vk):
    while True:
        try:
            time.sleep(21600)
            print("⏰ Запуск плановой проверки расписания...")
            check_and_notify_changes(vk)
        except Exception as e:
            print(f"❌ Ошибка в потоке проверки: {e}")

def start_schedule_checker(vk):
    checker_thread = threading.Thread(target=schedule_checker, args=(vk,), daemon=True)
    checker_thread.start()
    print("✅ Поток проверки расписания запущен (каждые 6 часов)")

def get_last_check_time():
    cache = load_schedule_cache()
    return cache.get("_last_check", "Никогда")

# ========== НАСТРОЙКИ ==========
VK_TOKEN = "vk1.a.caFxSOtgxlqz1GOqzR5VUhDTxl6Yi7Nhz2-n5bJ3Za8RCAQKsweYPbQtZQRLKYlmWQhg_mPFQ9UKppanLGRKkVVEOmhXYnN9b4hpmJ3jmcrCvZhafBGhWEwR77FFR0OKR2tJi4x-AZ73hc6rr4R0N1iKkHwvqBxdoqJ3P21AHEHTT1Cf538JnbyCUcwAaH8OiIHC10p6nQRLrW6vPifD3Q"
GROUP_ID = 238232620

API_BASE_URL = "https://stud.sssu.ru/api/Rasp"
API_DATES_URL = "https://stud.sssu.ru/api/GetRaspDates"
API_GROUPLIST_URL = "https://stud.sssu.ru/api/raspGrouplist"
API_YEARS_URL = "https://stud.sssu.ru/api/Rasp/ListYears"

CACHE_TIMEOUT = 3600
groups_cache = {"data": None, "timestamp": 0}
years_cache = {"data": None, "timestamp": 0}
current_year = None

# ========== РАБОТА С УЧЕБНЫМИ ГОДАМИ ==========
def get_available_years():
    current_time = datetime.now().timestamp()
    if years_cache["data"] and (current_time - years_cache["timestamp"]) < CACHE_TIMEOUT:
        return years_cache["data"]
    try:
        response = requests.get(API_YEARS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") == 1 and data.get("data", {}).get("years"):
            years = data["data"]["years"]
            years_cache["data"] = years
            years_cache["timestamp"] = current_time
            print(f"✅ Список годов: {years}")
            return years
        return []
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []

def get_current_academic_year():
    global current_year
    if current_year:
        return current_year
    years = get_available_years()
    if not years:
        return "2025-2026"
    now = datetime.now()
    current_year_num = now.year
    current_month = now.month
    if current_month >= 9:
        academic_year = f"{current_year_num}-{current_year_num + 1}"
    else:
        academic_year = f"{current_year_num - 1}-{current_year_num}"
    if academic_year in years:
        current_year = academic_year
    else:
        current_year = years[-1]
    print(f"📅 Текущий год: {current_year}")
    return current_year

# ========== РАБОТА СО СПИСКОМ ГРУПП ==========
def get_all_groups(year=None):
    if year is None:
        year = get_current_academic_year()
    current_time = datetime.now().timestamp()
    if groups_cache["data"] and groups_cache.get("year") == year:
        if (current_time - groups_cache["timestamp"]) < CACHE_TIMEOUT:
            return groups_cache["data"]
    try:
        response = requests.get(API_GROUPLIST_URL, params={"year": year}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
            groups_cache["data"] = data["data"]
            groups_cache["timestamp"] = current_time
            groups_cache["year"] = year
            print(f"✅ Список групп: {len(data['data'])}")
            return groups_cache["data"]
        return []
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []

def find_group_by_name(search_name, year=None):
    all_groups = get_all_groups(year)
    if not all_groups:
        return None, None, []
    
    # Нормализуем поисковый запрос
    normalized_search = normalize_group_name(search_name)
    
    # Точное совпадение после нормализации
    for group in all_groups:
        normalized_group = normalize_group_name(group["name"])
        if normalized_group == normalized_search:
            return group["id"], group["name"], []
    
    # Частичное совпадение (начинается с)
    for group in all_groups:
        normalized_group = normalize_group_name(group["name"])
        if normalized_group.startswith(normalized_search):
            return group["id"], group["name"], []
    
    # Поиск похожих названий
    all_names_normalized = [normalize_group_name(g["name"]) for g in all_groups]
    all_names_original = [g["name"] for g in all_groups]
    
    matches = difflib.get_close_matches(normalized_search, all_names_normalized, n=5, cutoff=0.6)
    original_matches = []
    for match_lower in matches:
        try:
            index = all_names_normalized.index(match_lower)
            original_matches.append(all_names_original[index])
        except ValueError:
            continue
    
    return None, None, original_matches

def get_group_name_by_id(group_id, year=None):
    all_groups = get_all_groups(year)
    for group in all_groups:
        if group["id"] == group_id:
            return group["name"]
    return None

def get_all_groups_list(page=1, per_page=20):
    all_groups = get_all_groups()
    if not all_groups:
        return []
    sorted_groups = sorted(all_groups, key=lambda x: x["name"])
    start = (page - 1) * per_page
    end = start + per_page
    return sorted_groups[start:end]

def search_groups_by_keyword(keyword):
    all_groups = get_all_groups()
    if not all_groups:
        return []
    
    # Нормализуем ключевое слово
    keyword_normalized = normalize_group_name(keyword)
    
    results = []
    for group in all_groups:
        group_normalized = normalize_group_name(group["name"])
        # Ищем частичное совпадение
        if keyword_normalized in group_normalized:
            results.append(group)
        # Также ищем по оригинальному названию
        elif keyword.lower() in group["name"].lower():
            if group not in results:
                results.append(group)
    
    return sorted(results, key=lambda x: x["name"])

def get_groups_list_message(page=1):
    groups = get_all_groups_list(page=page, per_page=20)
    if not groups:
        return "❌ Не удалось загрузить список групп"
    total_groups = len(get_all_groups())
    total_pages = (total_groups + 19) // 20
    result = f"📚 СПИСОК ГРУПП (страница {page}/{total_pages})\n"
    result += "=" * 35 + "\n\n"
    for group in groups:
        result += f"📌 {group['name']}\n"
        result += f"   🏫 {group.get('facul', 'Факультет не указан')} | 📚 {group.get('kurs', '?')} курс\n\n"
    result += f"💡 Нажмите на группу или напишите `выбрать {groups[0]['name'] if groups else ''}`"
    return result

def search_groups_message(keyword):
    results = search_groups_by_keyword(keyword)
    if not results:
        return f"❌ Группы по запросу `{keyword}` не найдены"
    result = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА: `{keyword}`\n"
    result += f"📚 Найдено групп: {len(results)}\n"
    result += "=" * 35 + "\n\n"
    for group in results[:20]:
        result += f"📌 {group['name']}\n"
        result += f"   🏫 {group.get('facul', 'Факультет не указан')} | 📚 {group.get('kurs', '?')} курс\n\n"
    if len(results) > 20:
        result += f"\n... и ещё {len(results) - 20} групп"
    result += f"\n💡 Напишите `выбрать {results[0]['name']}` для выбора группы"
    return result

# ========== РАБОТА С РАСПИСАНИЕМ ==========
def fetch_available_dates(group_id):
    try:
        response = requests.get(API_DATES_URL, params={"idGroup": group_id}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") == 1:
            return data.get("data", {}).get("dates", [])
        return []
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

def fetch_schedule(group_id, date):
    try:
        response = requests.get(API_BASE_URL, params={"idGroup": group_id, "sdate": date}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") != 1:
            return None, f"Ошибка: {data.get('msg')}"
        all_lessons = data.get("data", {}).get("rasp", [])
        filtered = [l for l in all_lessons if l.get("дата", "")[:10] == date]
        return {"data": {"rasp": filtered, "info": data.get("data", {}).get("info", {})}}, None
    except Exception as e:
        return None, f"Ошибка: {e}"

def get_weekday_rus(weekday):
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return days[weekday]

def format_date_compact(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%d.%m")

def parse_lesson_type(discipline):
    if discipline.startswith("лек "):
        return "📖 ЛЕКЦИЯ", discipline[4:]
    elif discipline.startswith("пр "):
        return "💻 ПРАКТИКА", discipline[3:]
    elif discipline.startswith("лаб "):
        return "🔬 ЛАБОРАТОРНАЯ", discipline[4:]
    else:
        return "", discipline

def parse_schedule_data(data, date, group_name=""):
    rasp_list = data.get("data", {}).get("rasp", [])
    if not rasp_list:
        return f"📭 На {date} занятий нет"
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    date_str_rus = date_obj.strftime("%d.%m.%Y")
    weekday = get_weekday_rus(date_obj.weekday())
    result = f"📅 РАСПИСАНИЕ НА {date_str_rus} ({weekday})\n"
    result += "=" * 35 + "\n\n"
    for lesson in rasp_list:
        time_start = lesson.get("начало", "")
        time_end = lesson.get("конец", "")
        discipline = lesson.get("дисциплина", "")
        teacher = lesson.get("преподаватель", "")
        room = lesson.get("аудитория", "")
        lesson_type, clean_discipline = parse_lesson_type(discipline)
        result += f"⏰ {time_start}–{time_end}\n"
        if lesson_type:
            result += f"{lesson_type}\n"
        result += f"📚 {clean_discipline}\n"
        result += f"👨‍🏫 {teacher}\n"
        result += f"📍 ауд. {room}\n"
        result += "-" * 35 + "\n"
    if group_name:
        result += f"\n👥 Группа: {group_name}"
    last_check = get_last_check_time()
    result += f"\n🕐 Последняя проверка обновлений: {last_check}"
    return result

# ========== ОСНОВНЫЕ ФУНКЦИИ РАСПИСАНИЯ ==========
def get_schedule_for_week_by_group(group_id, target_date):
    """Получает расписание группы на неделю, содержащую target_date"""
    start_date, end_date = get_week_for_date(target_date)
    all_dates = fetch_available_dates(group_id)
    target_dates = sorted([d for d in all_dates if start_date <= d <= end_date])
    if not target_dates:
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_obj = datetime.strptime(end_date, "%Y-%m-%d")
        return f"📭 На неделе ({start_obj.strftime('%d.%m')}–{end_obj.strftime('%d.%m')}) занятий нет\n\n🕐 Последняя проверка обновлений: {get_last_check_time()}"
    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj = datetime.strptime(end_date, "%Y-%m-%d")
    result = f"📅 РАСПИСАНИЕ НА НЕДЕЛЮ\n📆 {start_obj.strftime('%d.%m')} – {end_obj.strftime('%d.%m.%Y')}\n" + "=" * 40 + "\n\n"
    for date in target_dates:
        data, error = fetch_schedule(group_id, date)
        if error or not data:
            continue
        rasp_list = data.get("data", {}).get("rasp", [])
        if not rasp_list:
            continue
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        weekday = get_weekday_rus(date_obj.weekday())
        date_short = date_obj.strftime("%d.%m")
        result += f"📌 {weekday.upper()} ({date_short})\n" + "─" * 35 + "\n"
        for lesson in sorted(rasp_list, key=lambda x: x.get("начало", "00:00")):
            time_start = lesson.get("начало", "")
            time_end = lesson.get("конец", "")
            discipline = lesson.get("дисциплина", "")
            teacher = lesson.get("преподаватель", "")
            room = lesson.get("аудитория", "")
            clean_discipline = discipline
            lesson_type_short = ""
            if discipline.startswith("лек "):
                clean_discipline = discipline[4:]
                lesson_type_short = "ЛЕК"
            elif discipline.startswith("пр "):
                clean_discipline = discipline[3:]
                lesson_type_short = "ПРАК"
            elif discipline.startswith("лаб "):
                clean_discipline = discipline[4:]
                lesson_type_short = "ЛАБ"
            result += f"⏰ {time_start}–{time_end}"
            if lesson_type_short:
                result += f"  [{lesson_type_short}]"
            result += f"\n   📚 {clean_discipline}\n   👨‍🏫 {teacher}  |  🏫 {room}\n\n"
        result += "\n"
    result += f"\n🕐 Последняя проверка обновлений: {get_last_check_time()}"
    return result

def get_schedule_for_week_by_teacher(teacher_name, target_date):
    """Получает расписание преподавателя на неделю, содержащую target_date"""
    start_date, end_date = get_week_for_date(target_date)
    result = f"👨‍🏫 *РАСПИСАНИЕ ПРЕПОДАВАТЕЛЯ НА НЕДЕЛЮ*\n"
    result += f"📌 {teacher_name}\n"
    result += f"📆 {datetime.strptime(start_date, '%Y-%m-%d').strftime('%d.%m')} – {datetime.strptime(end_date, '%Y-%m-%d').strftime('%d.%m.%Y')}\n"
    result += "=" * 35 + "\n\n"
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
    found = False
    while current_date <= end_date_obj:
        date_str = current_date.strftime("%Y-%m-%d")
        lessons = fetch_schedule_by_teacher(teacher_name, date_str)
        if lessons:
            found = True
            weekday = get_weekday_rus(current_date.weekday())
            result += f"📌 {weekday} ({current_date.strftime('%d.%m')})\n"
            result += "─" * 30 + "\n"
            for lesson in lessons:
                result += f"⏰ {lesson['time_start']}–{lesson['time_end']}\n"
                result += f"📚 {lesson['discipline']}\n"
                result += f"👥 {lesson['group']} | 🏫 {lesson['room']}\n\n"
            result += "\n"
        current_date += timedelta(days=1)
    if not found:
        result += "❌ Занятий на этой неделе не найдено"
    return result

def get_schedule_for_week_by_auditorium(auditorium, target_date):
    """Получает расписание аудитории на неделю, содержащую target_date"""
    start_date, end_date = get_week_for_date(target_date)
    result = f"🏫 *РАСПИСАНИЕ АУДИТОРИИ НА НЕДЕЛЮ*\n"
    result += f"📌 {auditorium}\n"
    result += f"📆 {datetime.strptime(start_date, '%Y-%m-%d').strftime('%d.%m')} – {datetime.strptime(end_date, '%Y-%m-%d').strftime('%d.%m.%Y')}\n"
    result += "=" * 35 + "\n\n"
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
    found = False
    while current_date <= end_date_obj:
        date_str = current_date.strftime("%Y-%m-%d")
        lessons = fetch_schedule_by_auditorium(auditorium, date_str)
        if lessons:
            found = True
            weekday = get_weekday_rus(current_date.weekday())
            result += f"📌 {weekday} ({current_date.strftime('%d.%m')})\n"
            result += "─" * 30 + "\n"
            for lesson in lessons:
                result += f"⏰ {lesson['time_start']}–{lesson['time_end']}\n"
                result += f"📚 {lesson['discipline']}\n"
                result += f"👨‍🏫 {lesson['teacher']} | 👥 {lesson['group']}\n\n"
            result += "\n"
        current_date += timedelta(days=1)
    if not found:
        result += "❌ Занятий на этой неделе не найдено"
    return result

def get_schedule_for_today_by_group(group_id):
    return get_schedule_for_week_by_group(group_id, datetime.now().strftime("%Y-%m-%d"))

def get_schedule_for_today_by_teacher(teacher_name):
    return get_schedule_for_week_by_teacher(teacher_name, datetime.now().strftime("%Y-%m-%d"))

def get_schedule_for_today_by_auditorium(auditorium):
    return get_schedule_for_week_by_auditorium(auditorium, datetime.now().strftime("%Y-%m-%d"))

def get_schedule_for_tomorrow_by_group(group_id):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return get_schedule_for_week_by_group(group_id, tomorrow)

def get_schedule_for_tomorrow_by_teacher(teacher_name):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return get_schedule_for_week_by_teacher(teacher_name, tomorrow)

def get_schedule_for_tomorrow_by_auditorium(auditorium):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return get_schedule_for_week_by_auditorium(auditorium, tomorrow)

def get_next_lesson(group_id):
    next_date = get_next_lesson_date(group_id)
    if not next_date:
        return "📭 Ближайших занятий не найдено"
    # Показываем ближайшее занятие
    data, error = fetch_schedule(group_id, next_date)
    if error:
        return error
    rasp_list = data.get("data", {}).get("rasp", [])
    if not rasp_list:
        return "📭 Нет данных о занятиях"
    first_lesson = rasp_list[0]
    time_start = first_lesson.get("начало", "")
    discipline = first_lesson.get("дисциплина", "")
    teacher = first_lesson.get("преподаватель", "")
    room = first_lesson.get("аудитория", "")
    lesson_type, clean_discipline = parse_lesson_type(discipline)
    date_str = format_date_compact(next_date)
    weekday = get_weekday_rus(datetime.strptime(next_date, "%Y-%m-%d").weekday())
    result = f"🎯 БЛИЖАЙШЕЕ ЗАНЯТИЕ\n📅 {date_str} ({weekday})\n⏰ {time_start}\n"
    if lesson_type:
        result += f"{lesson_type}\n"
    result += f"📚 {clean_discipline}\n👨‍🏫 {teacher}\n📍 ауд. {room}\n\n"
    # Добавляем информацию о том, что это за неделя
    result += f"📆 Неделя: {datetime.strptime(next_date, '%Y-%m-%d').strftime('%d.%m.%Y')}"
    return result

def has_lessons_on_date(group_id, date):
    dates = fetch_available_dates(group_id)
    return date in dates

def get_next_lesson_date(group_id, from_date=None):
    if from_date is None:
        from_date = datetime.now().strftime("%Y-%m-%d")
    dates = fetch_available_dates(group_id)
    for date in sorted(dates):
        if date >= from_date:
            return date
    return None

def get_current_week_range():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

def get_next_week_range():
    today = datetime.now()
    current_monday = today - timedelta(days=today.weekday())
    next_monday = current_monday + timedelta(days=7)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday.strftime("%Y-%m-%d"), next_sunday.strftime("%Y-%m-%d")

def get_schedule_for_current_week_by_group(group_id):
    return get_schedule_for_week_by_group(group_id, datetime.now().strftime("%Y-%m-%d"))

def get_schedule_for_next_week_by_group(group_id):
    next_week_start = (datetime.now() + timedelta(days=7 - datetime.now().weekday())).strftime("%Y-%m-%d")
    return get_schedule_for_week_by_group(group_id, next_week_start)

def get_schedule_for_current_week_by_teacher(teacher_name):
    return get_schedule_for_week_by_teacher(teacher_name, datetime.now().strftime("%Y-%m-%d"))

def get_schedule_for_next_week_by_teacher(teacher_name):
    next_week_start = (datetime.now() + timedelta(days=7 - datetime.now().weekday())).strftime("%Y-%m-%d")
    return get_schedule_for_week_by_teacher(teacher_name, next_week_start)

def get_schedule_for_current_week_by_auditorium(auditorium):
    return get_schedule_for_week_by_auditorium(auditorium, datetime.now().strftime("%Y-%m-%d"))

def get_schedule_for_next_week_by_auditorium(auditorium):
    next_week_start = (datetime.now() + timedelta(days=7 - datetime.now().weekday())).strftime("%Y-%m-%d")
    return get_schedule_for_week_by_auditorium(auditorium, next_week_start)

# ========== ПРОВЕРКА СТАТУСА САЙТА ==========
def check_site_status():
    results = {"site_reachable": False, "api_reachable": False, "response_time": None, "error": None}
    try:
        start_time = datetime.now()
        response = requests.get("https://stud.sssu.ru", timeout=10, allow_redirects=True)
        results["response_time"] = int((datetime.now() - start_time).total_seconds() * 1000)
        if response.status_code == 200:
            results["site_reachable"] = True
        else:
            results["error"] = f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        results["error"] = "Таймаут (нет ответа 10 секунд)"
    except requests.exceptions.ConnectionError:
        results["error"] = "Ошибка соединения (сервер не отвечает)"
    except Exception as e:
        results["error"] = str(e)[:100]
    try:
        response = requests.get(API_YEARS_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("state") == 1:
                results["api_reachable"] = True
            else:
                results["api_reachable"] = False
                results["error"] = f"API вернул ошибку: {data.get('msg', 'неизвестно')}"
        else:
            results["api_reachable"] = False
    except Exception as e:
        results["api_reachable"] = False
        if not results["error"]:
            results["error"] = str(e)[:100]
    return results

def get_status_message():
    status = check_site_status()
    result = "🖥️ **СТАТУС СЕРВЕРА stud.sssu.ru**\n" + "=" * 35 + "\n\n"
    if status["site_reachable"]:
        result += "✅ **Основной сайт:** Доступен\n"
        if status["response_time"]:
            result += f"   ⏱️ Время ответа: {status['response_time']} мс\n"
    else:
        result += "❌ **Основной сайт:** НЕ ДОСТУПЕН\n"
    if status["api_reachable"]:
        result += "✅ **API расписания:** Работает\n   📡 Бот может получать расписание\n"
    else:
        result += "❌ **API расписания:** НЕ РАБОТАЕТ\n   ⚠️ Бот не может получить расписание\n"
    if status["error"]:
        result += f"\n⚠️ **Детали ошибки:**\n   {status['error']}\n"
    result += "\n💡 **Рекомендации:**\n"
    if not status["api_reachable"]:
        result += "   • Проверьте подключение к интернету\n   • Сайт может быть на техническом обслуживании\n"
    elif not status["site_reachable"] and not status["api_reachable"]:
        result += "   • Вероятно, сервер университета не работает\n"
    else:
        result += "   • Всё работает, можно пользоваться!\n"
    result += f"\n🕐 Проверено: {datetime.now().strftime('%H:%M:%S')}"
    result += f"\n🕐 Последняя проверка обновлений расписания: {get_last_check_time()}"
    return result

# ========== КЛАВИАТУРЫ ДЛЯ КНОПОК ==========
def get_main_keyboard(user_has_group=False):
    keyboard = {"one_time": False, "buttons": []}
    if user_has_group:
        keyboard["buttons"] = [
            [{"action": {"type": "text", "label": "📅 РАСПИСАНИЕ"}}, {"action": {"type": "text", "label": "📆 НЕДЕЛЯ"}}],
            [{"action": {"type": "text", "label": "⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ"}}, {"action": {"type": "text", "label": "🎯 БЛИЖАЙШЕЕ"}}],
            [{"action": {"type": "text", "label": "🏫 МОЯ ГРУППА"}}, {"action": {"type": "text", "label": "📚 ВСЕ ГРУППЫ"}}],
            [{"action": {"type": "text", "label": "👨‍🏫 ПРЕПОДАВАТЕЛИ"}}, {"action": {"type": "text", "label": "🏢 АУДИТОРИИ"}}],
            [{"action": {"type": "text", "label": "🖥️ СТАТУС САЙТА"}}, {"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}],
            [{"action": {"type": "text", "label": "🗑️ СБРОСИТЬ ВЫБОР"}}]
        ]
    else:
        keyboard["buttons"] = [
            [{"action": {"type": "text", "label": "📚 ВЫБРАТЬ ГРУППУ"}}, {"action": {"type": "text", "label": "🔍 ПОИСК ГРУППЫ"}}],
            [{"action": {"type": "text", "label": "👨‍🏫 ПРЕПОДАВАТЕЛИ"}}, {"action": {"type": "text", "label": "🏢 АУДИТОРИИ"}}],
            [{"action": {"type": "text", "label": "📋 ВСЕ ГРУППЫ"}}, {"action": {"type": "text", "label": "🖥️ СТАТУС САЙТА"}}],
            [{"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}]
        ]
    return keyboard

def get_back_keyboard():
    return {"one_time": False, "buttons": [[{"action": {"type": "text", "label": "◀️ НАЗАД"}}]]}

def get_search_keyboard():
    return {"one_time": True, "buttons": [[{"action": {"type": "text", "label": "❌ ОТМЕНА"}}]]}

def get_after_select_keyboard(group_name):
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "✅ ДА, ЭТА ГРУППА"}}, {"action": {"type": "text", "label": "🔍 ВЫБРАТЬ ДРУГУЮ"}}],
            [{"action": {"type": "text", "label": "❌ ОТМЕНА"}}]
        ]
    }

def send_keyboard(vk, peer_id, message, keyboard):
    vk.messages.send(peer_id=peer_id, message=message, random_id=0, keyboard=json.dumps(keyboard, ensure_ascii=False))

def send_message(vk, peer_id, message):
    vk.messages.send(peer_id=peer_id, message=message, random_id=0)

# ========== ОБРАБОТЧИК КОМАНД ==========
user_states = {}

def handle_message(text, user_id, peer_id, from_chat, vk):
    text_lower = text.lower().strip()
    user_id_str = str(user_id)
    current_selection = get_user_selection(user_id)
    
    # Кнопка НАЗАД
    if text == "◀️ НАЗАД":
        clear_user_selection(user_id)
        user_group = get_user_group(user_id)
        send_keyboard(vk, peer_id, "🔙 Вы вернулись в главное меню", get_main_keyboard(user_has_group=bool(user_group)))
        return
    
    # Кнопка СБРОСИТЬ ВЫБОР
    if text == "🗑️ СБРОСИТЬ ВЫБОР":
        clear_user_selection(user_id)
        user_group = get_user_group(user_id)
        send_keyboard(vk, peer_id, "🗑️ Выбор сброшен. Теперь кнопки показывают расписание вашей группы.", get_main_keyboard(user_has_group=bool(user_group)))
        return
    
    # Состояния
    if user_id_str in user_states:
        state = user_states[user_id_str]
        if state.get("mode") == "search_groups":
            keyword = text.strip()
            if keyword:
                results = search_groups_by_keyword(keyword)
                if results:
                    message = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА: `{keyword}`\n📚 Найдено: {len(results)}\n\n"
                    for group in results[:10]:
                        message += f"📌 {group['name']} | 🏫 {group.get('facul', '?')}\n"
                    if len(results) > 10:
                        message += f"\n... и ещё {len(results) - 10} групп"
                    message += f"\n\n💡 Напишите полное название группы для выбора"
                    send_keyboard(vk, peer_id, message, get_search_keyboard())
                else:
                    send_keyboard(vk, peer_id, f"❌ По запросу `{keyword}` ничего не найдено", get_search_keyboard())
                del user_states[user_id_str]
            else:
                send_keyboard(vk, peer_id, "❓ Введите текст для поиска", get_search_keyboard())
            return
        elif state.get("mode") == "waiting_for_group":
            group_name = text.strip()
            group_id, found_name, suggestions = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                clear_user_selection(user_id)
                del user_states[user_id_str]
                send_keyboard(vk, peer_id, f"✅ Группа `{found_name}` сохранена!", get_main_keyboard(user_has_group=True))
            else:
                if suggestions:
                    msg = f"❌ Группа `{group_name}` не найдена.\n\n🤔 Возможно, вы имели в виду:\n" + "\n".join([f"• {s}" for s in suggestions[:5]])
                    send_keyboard(vk, peer_id, msg, get_search_keyboard())
                else:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена.\nПопробуйте `📚 ВСЕ ГРУППЫ`", get_search_keyboard())
            return
        elif state.get("mode") == "waiting_for_teacher":
            teacher_name = text.strip()
            if teacher_name:
                set_user_selection(user_id, "teacher", teacher_name)
                del user_states[user_id_str]
                # Показываем расписание на сегодня (неделя)
                answer = get_schedule_for_today_by_teacher(teacher_name)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            else:
                send_keyboard(vk, peer_id, "❓ Введите фамилию преподавателя", get_search_keyboard())
            return
        elif state.get("mode") == "waiting_for_auditorium":
            auditorium = text.strip()
            if auditorium:
                set_user_selection(user_id, "auditorium", auditorium)
                del user_states[user_id_str]
                answer = get_schedule_for_today_by_auditorium(auditorium)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            else:
                send_keyboard(vk, peer_id, "❓ Введите номер аудитории", get_search_keyboard())
            return
    
    # Обработка кнопок
    if text == "📚 ВЫБРАТЬ ГРУППУ" or text == "🔍 ВЫБРАТЬ ДРУГУЮ":
        user_states[user_id_str] = {"mode": "waiting_for_group"}
        send_keyboard(vk, peer_id, "📝 Напишите название группы (например: `иктс тб31`)", get_search_keyboard())
        return
    if text == "🔍 ПОИСК ГРУППЫ":
        user_states[user_id_str] = {"mode": "search_groups"}
        send_keyboard(vk, peer_id, "🔍 Введите ключевое слово для поиска группы", get_search_keyboard())
        return
    if text == "📚 ВСЕ ГРУППЫ" or text == "📋 ВСЕ ГРУППЫ":
        message = get_groups_list_message(1)
        send_keyboard(vk, peer_id, message, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    if text == "👨‍🏫 ПРЕПОДАВАТЕЛИ":
        teachers = get_all_teachers()
        if teachers:
            message = "👨‍🏫 *Список преподавателей*\n\n"
            for t in teachers[:20]:
                message += f"📌 {t['name']}\n"
            if len(teachers) > 20:
                message += f"\n... и ещё {len(teachers) - 20}"
            message += f"\n\n💡 Напишите фамилию преподавателя для просмотра расписания"
            user_states[user_id_str] = {"mode": "waiting_for_teacher"}
            send_keyboard(vk, peer_id, message, get_search_keyboard())
        else:
            send_keyboard(vk, peer_id, "❌ Не удалось загрузить список преподавателей", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    if text == "🏢 АУДИТОРИИ":
        auditoriums = get_all_auditoriums()
        if auditoriums:
            message = "🏫 *Список аудиторий*\n\n"
            for a in auditoriums[:20]:
                message += f"📌 {a}\n"
            if len(auditoriums) > 20:
                message += f"\n... и ещё {len(auditoriums) - 20}"
            message += f"\n\n💡 Напишите номер аудитории для просмотра расписания"
            user_states[user_id_str] = {"mode": "waiting_for_auditorium"}
            send_keyboard(vk, peer_id, message, get_search_keyboard())
        else:
            send_keyboard(vk, peer_id, "❌ Не удалось загрузить список аудиторий", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    if text == "📅 РАСПИСАНИЕ":
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_today_by_teacher(current_selection["name"])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_today_by_auditorium(current_selection["name"])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_today_by_group(user_group['group_id'])
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!", get_main_keyboard(user_has_group=False))
        return
    if text == "📆 НЕДЕЛЯ":
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_current_week_by_teacher(current_selection["name"])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_current_week_by_auditorium(current_selection["name"])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_current_week_by_group(user_group['group_id'])
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!", get_main_keyboard(user_has_group=False))
        return
    if text == "⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ":
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_next_week_by_teacher(current_selection["name"])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_next_week_by_auditorium(current_selection["name"])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_next_week_by_group(user_group['group_id'])
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!", get_main_keyboard(user_has_group=False))
        return
    if text == "🎯 БЛИЖАЙШЕЕ":
        if current_selection["type"] in ["teacher", "auditorium"]:
            send_keyboard(vk, peer_id, "🎯 Ближайшее занятие доступно только для групп", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_next_lesson(user_group['group_id'])
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!", get_main_keyboard(user_has_group=False))
        return
    if text == "🏫 МОЯ ГРУППА":
        user_group = get_user_group(user_id)
        if user_group:
            send_keyboard(vk, peer_id, f"📌 Ваша группа: `{user_group['group_name']}`", get_main_keyboard(user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Группа не выбрана. Нажмите `📚 ВЫБРАТЬ ГРУППУ`", get_main_keyboard(user_has_group=False))
        return
    if text == "🖥️ СТАТУС САЙТА":
        answer = get_status_message()
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    if text == "❓ ПОМОЩЬ":
        user_group = get_user_group(user_id)
        selection = get_user_selection(user_id)
        selection_text = ""
        if selection["type"] == "teacher":
            selection_text = f"\n🎯 Текущий выбор: преподаватель `{selection['name']}`"
        elif selection["type"] == "auditorium":
            selection_text = f"\n🎯 Текущий выбор: аудитория `{selection['name']}`"
        help_text = (
            "🤖 *Тони Диспетчер - Бот с расписанием*\n\n"
            f"📌 Группа: `{user_group['group_name']}`" if user_group else "❓ Группа не выбрана"
            f"{selection_text}\n\n"
            "✨ *Что умеет бот:*\n\n"
            "**По группам:**\n"
            "• 📅 РАСПИСАНИЕ - сегодня\n"
            "• 📆 НЕДЕЛЯ - текущая неделя\n"
            "• ⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ\n"
            "• 🎯 БЛИЖАЙШЕЕ - следующая пара\n\n"
            "**По преподавателям:**\n"
            "• 👨‍🏫 ПРЕПОДАВАТЕЛИ - выбор\n"
            "• После выбора работают 📅 и 📆\n\n"
            "**По аудиториям:**\n"
            "• 🏢 АУДИТОРИИ - выбор\n"
            "• После выбора работают 📅 и 📆\n\n"
            "**Управление:**\n"
            "• 📚 ВЫБРАТЬ ГРУППУ - задать группу\n"
            "• 🗑️ СБРОСИТЬ ВЫБОР - вернуться к группе\n"
            "• ◀️ НАЗАД - из любого меню\n\n"
            "**Текстовые команды (примеры):**\n"
            "• `расписание иктс тб31` - сегодня\n"
            "• `неделя иктс тб31` - текущая неделя\n"
            "• `следующая неделя иктс тб31` - следующая неделя\n"
            "• `преподаватель Иванов` - выбрать преподавателя\n"
            "• `аудитория 2349` - выбрать аудиторию\n"
            "• `неделя иктс тб31 на 12.05` - неделя с указанной датой\n\n"
            f"🕐 Последняя проверка: {get_last_check_time()}\n\n"
            "💡 *Совет:* Пишите `иктс тб31` без тире, можно `иктс тb31` с английской b"
        )
        send_keyboard(vk, peer_id, help_text, get_main_keyboard(user_has_group=bool(user_group)))
        return
    if text == "❌ ОТМЕНА":
        if user_id_str in user_states:
            del user_states[user_id_str]
        user_group = get_user_group(user_id)
        send_keyboard(vk, peer_id, "✅ Действие отменено", get_main_keyboard(user_has_group=bool(user_group)))
        return
    
    # Текстовые команды
    # Проверяем, есть ли дата в тексте для команды "неделя ... на ДД.ММ"
    target_date = parse_date_from_text(text)
    
    # Команда "неделя ... на дату"
    if target_date and ("неделя" in text_lower or "week" in text_lower):
        # Извлекаем название группы/преподавателя/аудитории
        name_part = re.sub(r'неделя|week|на|\d{1,2}\.\d{1,2}(?:\.\d{4})?', '', text_lower).strip()
        if name_part:
            # Проверяем, может это группа
            group_id, group_name, _ = find_group_by_name(name_part)
            if group_id:
                answer = get_schedule_for_week_by_group(group_id, target_date)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
                return
            # Проверяем, может это преподаватель
            lessons = fetch_schedule_by_teacher(name_part, target_date)
            if lessons:
                set_user_selection(user_id, "teacher", name_part)
                answer = get_schedule_for_week_by_teacher(name_part, target_date)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
                return
            # Проверяем, может это аудитория
            lessons = fetch_schedule_by_auditorium(name_part, target_date)
            if lessons:
                set_user_selection(user_id, "auditorium", name_part)
                answer = get_schedule_for_week_by_auditorium(name_part, target_date)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
                return
            # Если ничего не найдено, пробуем как группу с нормализацией
            group_id, group_name, _ = find_group_by_name(normalize_group_name(name_part))
            if group_id:
                answer = get_schedule_for_week_by_group(group_id, target_date)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
                return
        else:
            # Только дата, без названия - используем выбранную группу
            if current_selection["type"] == "teacher":
                answer = get_schedule_for_week_by_teacher(current_selection["name"], target_date)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            elif current_selection["type"] == "auditorium":
                answer = get_schedule_for_week_by_auditorium(current_selection["name"], target_date)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            else:
                user_group = get_user_group(user_id)
                if user_group:
                    answer = get_schedule_for_week_by_group(user_group['group_id'], target_date)
                    send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
                else:
                    send_keyboard(vk, peer_id, "❓ Группа не выбрана. Напишите `выбрать ИКТС-Тb31`", get_main_keyboard(user_has_group=False))
        return
    
    # Команда "преподаватель ..."
    if text_lower.startswith("преподаватель "):
        teacher_name = text_lower.replace("преподаватель ", "").strip()
        if teacher_name:
            # Добавляем в список часто искомых
            add_to_common_teachers(teacher_name)
            set_user_selection(user_id, "teacher", teacher_name)
            answer = get_schedule_for_today_by_teacher(teacher_name)
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите фамилию преподавателя", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return

    # Команда "аудитория ..."
    if text_lower.startswith("аудитория "):
        auditorium = text_lower.replace("аудитория ", "").strip()
        if auditorium:
            set_user_selection(user_id, "auditorium", auditorium)
            answer = get_schedule_for_today_by_auditorium(auditorium)
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите номер аудитории", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Команда для показа недели по группе
    if text_lower.startswith("неделя "):
        group_name = text_lower.replace("неделя ", "").strip()
        if group_name:
            group_id, found_name, suggestions = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                clear_user_selection(user_id)
                answer = get_schedule_for_current_week_by_group(group_id)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
            else:
                if suggestions:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена.\n\n🤔 Возможно: {', '.join(suggestions[:3])}", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
                else:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите название группы", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Команда для показа следующей недели по группе
    if text_lower.startswith("следующая неделя "):
        group_name = text_lower.replace("следующая неделя ", "").strip()
        if group_name:
            group_id, found_name, suggestions = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                clear_user_selection(user_id)
                answer = get_schedule_for_next_week_by_group(group_id)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
            else:
                if suggestions:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена.\n\n🤔 Возможно: {', '.join(suggestions[:3])}", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
                else:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите название группы", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Команда "расписание ..." (синоним для недели)
    if text_lower.startswith("расписание "):
        group_name = text_lower.replace("расписание ", "").strip()
        if group_name:
            group_id, found_name, suggestions = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                clear_user_selection(user_id)
                answer = get_schedule_for_current_week_by_group(group_id)
                send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
            else:
                if suggestions:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена.\n\n🤔 Возможно: {', '.join(suggestions[:3])}", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
                else:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите название группы", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Команда "группы"
    if text_lower == "группы" or text_lower == "список групп":
        answer = get_groups_list_message(1)
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Команда "найди"
    if text_lower.startswith("найди ") or text_lower.startswith("поиск "):
        keyword = text_lower.replace("найди ", "").replace("поиск ", "").strip()
        if keyword:
            answer = search_groups_message(keyword)
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите, что искать", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Команда "выбрать"
    if text_lower.startswith("выбрать "):
        group_name = text_lower.replace("выбрать ", "").strip()
        if group_name:
            group_id, found_name, suggestions = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                clear_user_selection(user_id)
                send_keyboard(vk, peer_id, f"✅ Группа `{found_name}` сохранена!", get_main_keyboard(user_has_group=True))
            else:
                if suggestions:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена.\n\n🤔 Возможно: {', '.join(suggestions[:3])}", get_main_keyboard(user_has_group=False))
                else:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена", get_main_keyboard(user_has_group=False))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите название группы", get_main_keyboard(user_has_group=False))
        return
    
    # Команда "узнать группу" или "моя группа"
    if text_lower == "моя группа" or text_lower == "моя группа?" or text_lower == "моя группа":
        user_group = get_user_group(user_id)
        if user_group:
            send_keyboard(vk, peer_id, f"📌 Ваша группа: `{user_group['group_name']}`", get_main_keyboard(user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Группа не выбрана", get_main_keyboard(user_has_group=False))
        return
    
    # Команда "статус"
    if text_lower == "статус" or text_lower == "статус сайта" or text_lower == "проверка":
        answer = get_status_message()
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Команда "помощь"
    if text_lower in ["/start", "/help", "начать", "помощь", "start", "help"]:
        user_group = get_user_group(user_id)
        selection = get_user_selection(user_id)
        selection_text = ""
        if selection["type"] == "teacher":
            selection_text = f"\n🎯 Выбран преподаватель: `{selection['name']}`"
        elif selection["type"] == "auditorium":
            selection_text = f"\n🎯 Выбрана аудитория: `{selection['name']}`"
        help_text = (
            f"🤖 *Тони Диспетчер - Бот с расписанием*\n\n"
            f"📌 Группа: `{user_group['group_name']}`" if user_group else "❓ Группа не выбрана"
            f"{selection_text}\n\n"
            "✨ *Как пользоваться:*\n\n"
            "**Выбор группы:**\n• `выбрать иктс тб31` - сохранить группу\n\n"
            "**Преподаватели и аудитории:**\n• `преподаватель Иванов` - выбрать преподавателя\n• `аудитория 2349` - выбрать аудиторию\n• 🗑️ СБРОСИТЬ ВЫБОР - вернуться к группе\n\n"
            "**Команды:**\n• `неделя` - текущая неделя\n• `следующая неделя` - следующая неделя\n"
            "• `неделя иктс тб31 на 12.05` - неделя с указанной датой\n\n"
            f"🕐 Последняя проверка: {get_last_check_time()}\n\n"
            "💡 *Совет:* Пишите `иктс тб31` без тире, можно `иктс тb31` с английской b"
        )
        send_keyboard(vk, peer_id, help_text, get_main_keyboard(user_has_group=bool(user_group)))
        return
    
    # Команды с указанием группы (если не обработаны выше)
    action = "today"
    next_week_patterns = ["следующая неделя", "следущая неделя", "след неделя", "next week"]
    if any(p in text_lower for p in next_week_patterns):
        action = "next_week"
    elif any(w in text_lower for w in ["завтра", "tomorrow"]):
        action = "tomorrow"
    elif any(w in text_lower for w in ["неделя", "week"]):
        action = "week"
    else:
        # Если просто группа без указания действия - показываем неделю по умолчанию
        action = "week"
    
    # Извлекаем название группы
    query_for_group = text_lower
    action_words = ["завтра", "tomorrow", "неделя", "week", "следующая неделя", "следущая неделя", "след неделя", "next week"]
    for word in action_words:
        query_for_group = query_for_group.replace(word, "").strip()
    
    if query_for_group:
        # Явно указана группа
        group_id, group_name, suggestions = find_group_by_name(query_for_group)
        if not group_id:
            if suggestions:
                send_keyboard(vk, peer_id, f"❌ Группа не найдена.\n\n🤔 Возможно: {', '.join(suggestions[:3])}", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            else:
                send_keyboard(vk, peer_id, f"❌ Группа `{query_for_group}` не найдена", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            return
        set_user_group(user_id, group_id, group_name)
        clear_user_selection(user_id)
        if action == "tomorrow":
            answer = get_schedule_for_week_by_group(group_id, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
        elif action == "next_week":
            answer = get_schedule_for_next_week_by_group(group_id)
        else:
            answer = get_schedule_for_current_week_by_group(group_id)
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
        return
    
    # Нет явной группы - используем выбранную
    if current_selection["type"] == "teacher":
        if action == "tomorrow":
            answer = get_schedule_for_week_by_teacher(current_selection["name"], (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
        elif action == "next_week":
            answer = get_schedule_for_next_week_by_teacher(current_selection["name"])
        else:
            answer = get_schedule_for_current_week_by_teacher(current_selection["name"])
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    elif current_selection["type"] == "auditorium":
        if action == "tomorrow":
            answer = get_schedule_for_week_by_auditorium(current_selection["name"], (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
        elif action == "next_week":
            answer = get_schedule_for_next_week_by_auditorium(current_selection["name"])
        else:
            answer = get_schedule_for_current_week_by_auditorium(current_selection["name"])
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    else:
        user_group = get_user_group(user_id)
        if not user_group:
            send_keyboard(vk, peer_id, "❓ У вас не выбрана группа.\n\nНажмите `📚 ВЫБРАТЬ ГРУППУ`", get_main_keyboard(user_has_group=False))
            return
        group_id = user_group['group_id']
        if action == "tomorrow":
            answer = get_schedule_for_week_by_group(group_id, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
        elif action == "next_week":
            answer = get_schedule_for_next_week_by_group(group_id)
        else:
            answer = get_schedule_for_current_week_by_group(group_id)
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))

# ========== ЗАПУСК ==========
def main():
    print("🚀 Запуск Тони Диспетчер - Бот с расписанием")
    print("=" * 40)
    
    start_self_ping()
    get_available_years()
    get_current_academic_year()
    get_all_groups()
    
    # Предзагружаем списки в фоновом потоке (чтобы не зависало)
    def preload():
        print("🔄 Предзагрузка списков в фоне...")
        get_all_teachers()
        get_all_auditoriums()
        print("✅ Предзагрузка завершена")
    
    preload_thread = threading.Thread(target=preload, daemon=True)
    preload_thread.start()
    
    # ... остальной код main()    
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    start_schedule_checker(vk)
    
    print("🤖 Бот готов к работе!")
    print("📡 Функции: веб-сервер, self-ping, все кнопки")
    print("👨‍🏫 Преподаватели и аудитории с запоминанием выбора")
    print("🔙 Кнопка НАЗАД для возврата в главное меню")
    print("📅 Поддержка дат в командах (неделя иктс тб31 на 12.05)")
    print("🕐 Автоматическая проверка обновлений: каждые 6 часов")
    print("=" * 40)
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_message = event.obj.message['text']
            user_id = event.obj.message['from_id']
            
            if event.from_chat:
                peer_id = 2000000000 + event.chat_id
                from_chat = True
                if user_id < 0:
                    continue
                print(f"📨 Чат {event.chat_id} от {user_id}: {user_message[:50]}...")
            else:
                peer_id = user_id
                from_chat = False
                print(f"📨 ЛС от {user_id}: {user_message[:50]}...")
            
            handle_message(user_message, user_id, peer_id, from_chat, vk)

if __name__ == "__main__":
    main()
