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
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== FIX ДЛЯ DNS ПРОБЛЕМ НА RENDER ==========
STUD_SSSU_IP = "89.16.96.207"
STUD_SSSU_PORT = 443

def force_stud_ip():
    original_getaddrinfo = socket.getaddrinfo
    def patched_getaddrinfo(host, port, *args, **kwargs):
        if host == "stud.sssu.ru":
            print(f"🔧 DNS патч: {host} -> {STUD_SSSU_IP}:{port}")
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (STUD_SSSU_IP, port))]
        return original_getaddrinfo(host, port, *args, **kwargs)
    socket.getaddrinfo = patched_getaddrinfo
    print("✅ DNS патч для stud.sssu.ru активирован")

force_stud_ip()

# ========== HEALTHCHECK ДЛЯ RENDER ==========
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🏥 Health-check сервер запущен на порту {port}")
    server.serve_forever()

Thread(target=run_health_server, daemon=True).start()

# ========== ХРАНЕНИЕ ГРУПП ПОЛЬЗОВАТЕЛЕЙ ==========
USER_GROUPS_FILE = "user_groups.json"

def load_user_groups():
    try:
        if os.path.exists(USER_GROUPS_FILE):
            with open(USER_GROUPS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Ошибка загрузки групп пользователей: {e}")
        return {}

def save_user_groups(groups):
    try:
        with open(USER_GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения групп пользователей: {e}")

def get_user_group(user_id):
    groups = load_user_groups()
    return groups.get(str(user_id))

def set_user_group(user_id, group_id, group_name):
    groups = load_user_groups()
    groups[str(user_id)] = {"group_id": group_id, "group_name": group_name}
    save_user_groups(groups)

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
            print(f"✅ Список годов обновлён: {years}")
            return years
        return []
    except Exception as e:
        print(f"❌ Ошибка при получении списка годов: {e}")
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
    print(f"📅 Текущий учебный год: {current_year}")
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
            print(f"✅ Список групп за {year} обновлён. Всего: {len(data['data'])}")
            return groups_cache["data"]
        return []
    except Exception as e:
        print(f"❌ Ошибка при получении списка групп: {e}")
        return []

def find_group_by_name(search_name, year=None):
    all_groups = get_all_groups(year)
    if not all_groups:
        return None, None, []
    search_name_lower = search_name.lower().strip()
    for group in all_groups:
        if group["name"].lower() == search_name_lower:
            return group["id"], group["name"], []
    for group in all_groups:
        if group["name"].lower().startswith(search_name_lower):
            return group["id"], group["name"], []
    all_names_lower = [g["name"].lower() for g in all_groups]
    all_names_original = [g["name"] for g in all_groups]
    matches = difflib.get_close_matches(search_name_lower, all_names_lower, n=5, cutoff=0.6)
    original_matches = []
    for match_lower in matches:
        try:
            index = all_names_lower.index(match_lower)
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
    keyword_lower = keyword.lower()
    results = []
    for group in all_groups:
        if keyword_lower in group["name"].lower():
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
    result += f"💡 Чтобы выбрать группу, напишите: `выбрать {groups[0]['name'] if groups else ''}`"
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
    result += f"\n💡 Чтобы выбрать группу, напишите: `выбрать {results[0]['name']}`"
    return result

# ========== РАБОТА С ДАТАМИ ЗАНЯТИЙ ==========
def fetch_available_dates(group_id):
    try:
        response = requests.get(API_DATES_URL, params={"idGroup": group_id}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") == 1:
            return data.get("data", {}).get("dates", [])
        return []
    except Exception as e:
        print(f"Ошибка получения дат: {e}")
        return []

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

def fetch_schedule(group_id, date):
    params = {
        "idGroup": group_id,
        "sdate": date
    }
    try:
        response = requests.get(API_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") != 1:
            return None, f"❌ Ошибка: {data.get('msg', 'Неизвестная ошибка')}"
        all_lessons = data.get("data", {}).get("rasp", [])
        filtered_lessons = [lesson for lesson in all_lessons if lesson.get("дата", "")[:10] == date]
        filtered_data = {
            "data": {
                "rasp": filtered_lessons,
                "info": data.get("data", {}).get("info", {})
            },
            "state": data.get("state"),
            "msg": data.get("msg")
        }
        return filtered_data, None
    except requests.exceptions.RequestException as e:
        return None, f"❌ Ошибка соединения: {str(e)}"

# ========== ФОРМАТИРОВАНИЕ РАСПИСАНИЯ ==========
def get_weekday_rus(weekday):
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return weekdays[weekday]

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
    return result

# ========== ОСНОВНЫЕ ФУНКЦИИ РАСПИСАНИЯ ==========
def get_schedule(group_id, date):
    if not has_lessons_on_date(group_id, date):
        return f"📭 На {format_date_compact(date)} занятий нет"
    data, error = fetch_schedule(group_id, date)
    if error:
        return error
    group_name = get_group_name_by_id(group_id)
    return parse_schedule_data(data, date, group_name)

def get_schedule_for_today(group_id):
    today = datetime.now().strftime("%Y-%m-%d")
    return get_schedule(group_id, today)

def get_schedule_for_tomorrow(group_id):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return get_schedule(group_id, tomorrow)

def get_next_weekday(target_weekday):
    today = datetime.now()
    days_ahead = target_weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def get_next_lesson(group_id):
    next_date = get_next_lesson_date(group_id)
    if not next_date:
        return "📭 Ближайших занятий не найдено"
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
    result = f"🎯 БЛИЖАЙШЕЕ ЗАНЯТИЕ\n"
    result += f"📅 {date_str} ({weekday})\n"
    result += f"⏰ {time_start}\n"
    if lesson_type:
        result += f"{lesson_type}\n"
    result += f"📚 {clean_discipline}\n"
    result += f"👨‍🏫 {teacher}\n"
    result += f"📍 ауд. {room}"
    return result

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

def get_schedule_for_current_week(group_id):
    start_date, end_date = get_current_week_range()
    all_dates = fetch_available_dates(group_id)
    target_dates = sorted([d for d in all_dates if start_date <= d <= end_date])
    if not target_dates:
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_obj = datetime.strptime(end_date, "%Y-%m-%d")
        return f"📭 На текущей неделе ({start_obj.strftime('%d.%m')}–{end_obj.strftime('%d.%m')}) занятий нет"
    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj = datetime.strptime(end_date, "%Y-%m-%d")
    result = f"📅 РАСПИСАНИЕ НА ТЕКУЩУЮ НЕДЕЛЮ\n"
    result += f"📆 {start_obj.strftime('%d.%m')} – {end_obj.strftime('%d.%m.%Y')}\n"
    result += "=" * 40 + "\n\n"
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
        result += f"📌 {weekday.upper()} ({date_short})\n"
        result += "─" * 35 + "\n"
        sorted_lessons = sorted(rasp_list, key=lambda x: x.get("начало", "00:00"))
        for lesson in sorted_lessons:
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
            result += f"\n   📚 {clean_discipline}\n"
            result += f"   👨‍🏫 {teacher}  |  🏫 {room}\n\n"
        result += "\n"
    return result

def get_schedule_for_next_week(group_id):
    start_date, end_date = get_next_week_range()
    all_dates = fetch_available_dates(group_id)
    target_dates = sorted([d for d in all_dates if start_date <= d <= end_date])
    if not target_dates:
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_obj = datetime.strptime(end_date, "%Y-%m-%d")
        return f"📭 На следующей неделе ({start_obj.strftime('%d.%m')}–{end_obj.strftime('%d.%m')}) занятий нет"
    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj = datetime.strptime(end_date, "%Y-%m-%d")
    result = f"📅 РАСПИСАНИЕ НА СЛЕДУЮЩУЮ НЕДЕЛЮ\n"
    result += f"📆 {start_obj.strftime('%d.%m')} – {end_obj.strftime('%d.%m.%Y')}\n"
    result += "=" * 40 + "\n\n"
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
        result += f"📌 {weekday.upper()} ({date_short})\n"
        result += "─" * 35 + "\n"
        sorted_lessons = sorted(rasp_list, key=lambda x: x.get("начало", "00:00"))
        for lesson in sorted_lessons:
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
            result += f"\n   📚 {clean_discipline}\n"
            result += f"   👨‍🏫 {teacher}  |  🏫 {room}\n\n"
        result += "\n"
    return result

# ========== КЛАВИАТУРЫ ДЛЯ КНОПОК ==========

def get_main_keyboard(user_has_group=False):
    keyboard = {
        "one_time": False,
        "buttons": []
    }
    if user_has_group:
        keyboard["buttons"] = [
            [
                {"action": {"type": "text", "label": "📅 РАСПИСАНИЕ"}},
                {"action": {"type": "text", "label": "📆 НЕДЕЛЯ"}}
            ],
            [
                {"action": {"type": "text", "label": "⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ"}},
                {"action": {"type": "text", "label": "🎯 БЛИЖАЙШЕЕ"}}
            ],
            [
                {"action": {"type": "text", "label": "🏫 МОЯ ГРУППА"}},
                {"action": {"type": "text", "label": "📚 ВСЕ ГРУППЫ"}}
            ],
            [
                {"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}
            ]
        ]
    else:
        keyboard["buttons"] = [
            [
                {"action": {"type": "text", "label": "📚 ВЫБРАТЬ ГРУППУ"}},
                {"action": {"type": "text", "label": "🔍 ПОИСК ГРУППЫ"}}
            ],
            [
                {"action": {"type": "text", "label": "📋 ВСЕ ГРУППЫ"}},
                {"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}
            ]
        ]
    return keyboard

def get_search_keyboard():
    return {
        "one_time": True,
        "buttons": [
            [
                {"action": {"type": "text", "label": "❌ ОТМЕНА"}}
            ]
        ]
    }

def get_after_select_keyboard(group_name):
    return {
        "one_time": False,
        "buttons": [
            [
                {"action": {"type": "text", "label": "✅ ДА, ЭТА ГРУППА"}},
                {"action": {"type": "text", "label": "🔍 ВЫБРАТЬ ДРУГУЮ"}}
            ],
            [
                {"action": {"type": "text", "label": "❌ ОТМЕНА"}}
            ]
        ]
    }

def send_keyboard(vk, peer_id, message, keyboard):
    """Отправляет сообщение с клавиатурой (работает и в ЛС, и в чатах)"""
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=0,
        keyboard=json.dumps(keyboard, ensure_ascii=False)
    )

def send_message(vk, peer_id, message):
    """Отправляет обычное сообщение без клавиатуры"""
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=0
    )

# ========== ОБРАБОТЧИК КОМАНД (ДЛЯ ЧАТОВ И ЛС) ==========

user_states = {}

def handle_message(text, user_id, peer_id, from_chat, vk):
    """
    Обрабатывает сообщение
    user_id - ID отправителя (всегда человек)
    peer_id - куда отвечать (ЛС или чат)
    from_chat - True если сообщение из чата
    """
    text_lower = text.lower().strip()
    user_id_str = str(user_id)
    
    # ===== ПРОВЕРКА СОСТОЯНИЙ (диалоги с ботом) =====
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
                user_states[user_id_str] = {"mode": "confirm_group", "group_id": group_id, "group_name": found_name}
                send_keyboard(vk, peer_id, f"📌 Выбрана группа: `{found_name}`\n\n✅ Подтвердите выбор:", get_after_select_keyboard(found_name))
            else:
                if suggestions:
                    msg = f"❌ Группа `{group_name}` не найдена.\n\n🤔 Возможно, вы имели в виду:\n" + "\n".join([f"• {s}" for s in suggestions[:5]])
                    send_keyboard(vk, peer_id, msg, get_search_keyboard())
                else:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена.\nПопробуйте `📚 ВСЕ ГРУППЫ`", get_search_keyboard())
            return
        
        elif state.get("mode") == "confirm_group":
            if "да, эта" in text_lower or "подтверждаю" in text_lower:
                set_user_group(user_id, state["group_id"], state["group_name"])
                del user_states[user_id_str]
                send_keyboard(vk, peer_id, f"✅ Группа `{state['group_name']}` сохранена!\n\nТеперь вы можете пользоваться кнопками:", get_main_keyboard(user_has_group=True))
            else:
                del user_states[user_id_str]
                send_keyboard(vk, peer_id, "❌ Выбор отменён", get_main_keyboard(user_has_group=False))
            return
    
    # ===== ОБРАБОТКА КНОПОК =====
    
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
    
    if text == "📅 РАСПИСАНИЕ":
        user_group = get_user_group(user_id)
        if user_group:
            answer = get_schedule_for_today(user_group['group_id'])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Сначала выберите группу!", get_main_keyboard(user_has_group=False))
        return
    
    if text == "📆 НЕДЕЛЯ":
        user_group = get_user_group(user_id)
        if user_group:
            answer = get_schedule_for_current_week(user_group['group_id'])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Сначала выберите группу!", get_main_keyboard(user_has_group=False))
        return
    
    if text == "⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ":
        user_group = get_user_group(user_id)
        if user_group:
            answer = get_schedule_for_next_week(user_group['group_id'])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Сначала выберите группу!", get_main_keyboard(user_has_group=False))
        return
    
    if text == "🎯 БЛИЖАЙШЕЕ":
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
    
    if text == "❓ ПОМОЩЬ":
        user_group = get_user_group(user_id)
        help_text = (
            "🤖 *Тони Диспетчер - Бот с расписанием*\n\n"
            f"📌 Группа: `{user_group['group_name']}`\n\n" if user_group else "❓ Группа не выбрана\n\n"
            "✨ *Что умеет бот:*\n\n"
            "**Основные команды:**\n"
            "• 📅 РАСПИСАНИЕ - сегодня\n"
            "• 📆 НЕДЕЛЯ - текущая неделя\n"
            "• ⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ\n"
            "• 🎯 БЛИЖАЙШЕЕ - следующая пара\n\n"
            "**Управление группой:**\n"
            "• 📚 ВЫБРАТЬ ГРУППУ - ввести название\n"
            "• 🔍 ПОИСК ГРУППЫ - по ключевому слову\n"
            "• 📋 ВСЕ ГРУППЫ - список\n"
            "• 🏫 МОЯ ГРУППА - посмотреть\n\n"
            "💡 *Совет:* Можно писать текстом: `завтра иктс тб31`"
        )
        send_keyboard(vk, peer_id, help_text, get_main_keyboard(user_has_group=bool(user_group)))
        return
    
    if text == "❌ ОТМЕНА":
        if user_id_str in user_states:
            del user_states[user_id_str]
        user_group = get_user_group(user_id)
        send_keyboard(vk, peer_id, "✅ Действие отменено", get_main_keyboard(user_has_group=bool(user_group)))
        return
    
    # ===== ТЕКСТОВЫЕ КОМАНДЫ =====
    
    # Команда "группы"
    if text_lower == "группы" or text_lower == "список групп":
        answer = get_groups_list_message(1)
        send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Поиск "найди XXX"
    if text_lower.startswith("найди ") or text_lower.startswith("поиск "):
        keyword = text_lower.replace("найди ", "").replace("поиск ", "").strip()
        if keyword:
            answer = search_groups_message(keyword)
            send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите, что искать", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        return
    
    # Выбор группы "выбрать XXX"
    if text_lower.startswith("выбрать "):
        group_name = text_lower.replace("выбрать ", "").strip()
        if group_name:
            group_id, found_name, suggestions = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                send_keyboard(vk, peer_id, f"✅ Группа `{found_name}` сохранена!", get_main_keyboard(user_has_group=True))
            else:
                if suggestions:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена.\n\n🤔 Возможно: {', '.join(suggestions[:3])}", get_main_keyboard(user_has_group=False))
                else:
                    send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена", get_main_keyboard(user_has_group=False))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите название группы", get_main_keyboard(user_has_group=False))
        return
    
    # Моя группа
    if text_lower == "моя группа" or text_lower == "моя группа?":
        user_group = get_user_group(user_id)
        if user_group:
            send_keyboard(vk, peer_id, f"📌 Ваша группа: `{user_group['group_name']}`", get_main_keyboard(user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Группа не выбрана", get_main_keyboard(user_has_group=False))
        return
    
    # Помощь текстом
    if text_lower in ["/start", "/help", "начать", "помощь", "start", "help"]:
        user_group = get_user_group(user_id)
        help_text = (
            f"🤖 *Тони Диспетчер - Бот с расписанием*\n\n"
            f"📌 Группа: `{user_group['group_name']}`\n\n" if user_group else "❓ Группа не выбрана\n\n"
            "✨ *Как пользоваться:*\n\n"
            "**Выбор группы:**\n"
            "• `выбрать иктс тб31` - сохранить группу\n"
            "• `группы` - список всех групп\n"
            "• `найди иктс` - поиск группы\n\n"
            "**Команды (после выбора группы):**\n"
            "• `расписание` - на сегодня\n"
            "• `завтра` - на завтра\n"
            "• `неделя` - на текущую неделю\n"
            "• `следующая неделя` - на следующую неделю\n"
            "• `следующее` - ближайшее занятие\n\n"
            "💡 *Совет:* Используйте кнопки для быстрого доступа!"
        )
        send_keyboard(vk, peer_id, help_text, get_main_keyboard(user_has_group=bool(user_group)))
        return
    
    # Команды с указанием группы (неделя иктс тб31, завтра иктс тб31 и т.д.)
    action = "today"
    next_week_patterns = ["следующая неделя", "следущая неделя", "след неделя", "следующ неделя", "следущ неделя", "next week"]
    
    if any(pattern in text_lower for pattern in next_week_patterns):
        action = "next_week"
    elif any(word in text_lower for word in ["завтра", "tomorrow"]):
        action = "tomorrow"
    elif any(word in text_lower for word in ["следующее", "ближайщее", "след", "next"]):
        action = "next"
    elif any(word in text_lower for word in ["неделя", "week"]):
        action = "week"
    elif any(word in text_lower for word in ["пн", "понедельник"]):
        action = "monday"
    elif any(word in text_lower for word in ["вт", "вторник"]):
        action = "tuesday"
    elif any(word in text_lower for word in ["ср", "среда"]):
        action = "wednesday"
    elif any(word in text_lower for word in ["чт", "четверг"]):
        action = "thursday"
    elif any(word in text_lower for word in ["пт", "пятница"]):
        action = "friday"
    
    # Извлекаем название группы
    query_for_group = text_lower
    action_words = [
        "завтра", "tomorrow", "следующее", "ближайщее", "след",
        "неделя", "week", "пн", "понедельник", "вт", "вторник",
        "ср", "среда", "чт", "четверг", "пт", "пятница",
        "следующая неделя", "следущая неделя", "след неделя", 
        "следующ неделя", "следущ неделя", "next week"
    ]
    for word in action_words:
        query_for_group = query_for_group.replace(word, "").strip()
    
    if query_for_group:
        group_id, group_name, suggestions = find_group_by_name(query_for_group)
        if not group_id:
            if suggestions:
                send_keyboard(vk, peer_id, f"❌ Группа не найдена.\n\n🤔 Возможно: {', '.join(suggestions[:3])}", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            else:
                send_keyboard(vk, peer_id, f"❌ Группа `{query_for_group}` не найдена", get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
            return
        set_user_group(user_id, group_id, group_name)
    else:
        user_group = get_user_group(user_id)
        if not user_group:
            send_keyboard(vk, peer_id, "❓ У вас не выбрана группа.\n\nНажмите `📚 ВЫБРАТЬ ГРУППУ`", get_main_keyboard(user_has_group=False))
            return
        group_id = user_group['group_id']
    
    # Выполняем действие
    if action == "tomorrow":
        answer = get_schedule_for_tomorrow(group_id)
    elif action == "next":
        answer = get_next_lesson(group_id)
    elif action == "next_week":
        answer = get_schedule_for_next_week(group_id)
    elif action == "week":
        answer = get_schedule_for_current_week(group_id)
    elif action == "monday":
        answer = get_schedule(group_id, get_next_weekday(0))
    elif action == "tuesday":
        answer = get_schedule(group_id, get_next_weekday(1))
    elif action == "wednesday":
        answer = get_schedule(group_id, get_next_weekday(2))
    elif action == "thursday":
        answer = get_schedule(group_id, get_next_weekday(3))
    elif action == "friday":
        answer = get_schedule(group_id, get_next_weekday(4))
    else:
        answer = get_schedule_for_today(group_id)
    
    send_keyboard(vk, peer_id, answer, get_main_keyboard(user_has_group=True))

# ========== ЗАПУСК БОТА ==========
def main():
    print("🚀 Запуск бота расписания СГУ (с поддержкой чатов)")
    print("=" * 40)
    get_available_years()
    get_current_academic_year()
    get_all_groups()
    
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    print("🤖 Бот готов к работе!")
    print("📡 Функции:")
    print("   - Работа в личных сообщениях и чатах")
    print("   - Клавиатуры с кнопками")
    print("   - Запоминание группы для каждого пользователя")
    print("   - Список всех групп")
    print("   - Поиск групп")
    print("=" * 40)
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_message = event.obj.message['text']
            user_id = event.obj.message['from_id']
            
            # Определяем, откуда пришло сообщение
            if event.from_chat:
                # Сообщение из беседы
                peer_id = 2000000000 + event.chat_id
                from_chat = True
                # Игнорируем служебные сообщения от самого бота
                if user_id < 0:
                    continue
                print(f"📨 Чат {event.chat_id} от {user_id}: {user_message[:50]}...")
            else:
                # Личное сообщение
                peer_id = user_id
                from_chat = False
                print(f"📨 ЛС от {user_id}: {user_message[:50]}...")
            
            # Обрабатываем сообщение
            handle_message(user_message, user_id, peer_id, from_chat, vk)

if __name__ == "__main__":
    main()
