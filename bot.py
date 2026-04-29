import requests
from datetime import datetime, timedelta
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from functools import lru_cache
import difflib

# ========== НАСТРОЙКИ ==========
VK_TOKEN = "vk1.a.dhQU8BDzoI-qxTFqJcZog2recEWuNW4uebV72GlVYYV6m-o9A_pzHBnA0w2YXqRHJSbEeroIvNBb0535Ie1y_eIBkWVencSd2xWLNgukIHOEp_17wAXS5VrQ8DB2m1Eon8Q4u2IpVsYooyBTyo57amz9fKPfIrOYZxOoeP6woo3f-8Guf-1v92fX3_E19oEqiQKjj_9gftJjp_CAnHXQ8A"
GROUP_ID = 38232620  # ID вашего VK сообщества

API_BASE_URL = "https://stud.sssu.ru/api/Rasp"
API_DATES_URL = "https://stud.sssu.ru/api/GetRaspDates"
API_GROUPLIST_URL = "https://stud.sssu.ru/api/raspGrouplist"
API_YEARS_URL = "https://stud.sssu.ru/api/Rasp/ListYears"

CACHE_TIMEOUT = 3600  # Кэшировать на 1 час

# Глобальные кэши
groups_cache = {"data": None, "timestamp": 0}
years_cache = {"data": None, "timestamp": 0}
current_year = None

# ========== РАБОТА С УЧЕБНЫМИ ГОДАМИ ==========
def get_available_years():
    """Получает список доступных учебных годов"""
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
    """Определяет текущий учебный год на основе даты"""
    global current_year
    
    if current_year:
        return current_year
    
    years = get_available_years()
    if not years:
        return "2025-2026"  # Значение по умолчанию
    
    now = datetime.now()
    current_year_num = now.year
    current_month = now.month
    
    # Учебный год начинается в сентябре
    if current_month >= 9:
        academic_year = f"{current_year_num}-{current_year_num + 1}"
    else:
        academic_year = f"{current_year_num - 1}-{current_year_num}"
    
    # Проверяем, есть ли такой год в списке
    if academic_year in years:
        current_year = academic_year
    else:
        # Берём последний доступный год
        current_year = years[-1]
    
    print(f"📅 Текущий учебный год: {current_year}")
    return current_year

# ========== РАБОТА СО СПИСКОМ ГРУПП ==========
def get_all_groups(year=None):
    """Загружает и кэширует список всех групп за указанный год"""
    if year is None:
        year = get_current_academic_year()
    
    current_time = datetime.now().timestamp()
    
    # Используем год в ключе кэша
    cache_key = f"{year}_{current_time // CACHE_TIMEOUT}"
    
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
    """Ищет группу по названию за указанный год"""
    all_groups = get_all_groups(year)
    if not all_groups:
        return None, None, []
    
    search_name_lower = search_name.lower().strip()
    
    # Точное совпадение
    for group in all_groups:
        if group["name"].lower() == search_name_lower:
            return group["id"], group["name"], []
    
    # Частичное совпадение (начинается с)
    for group in all_groups:
        if group["name"].lower().startswith(search_name_lower):
            return group["id"], group["name"], []
    
    # Поиск похожих
    all_names = [g["name"] for g in all_groups]
    matches = difflib.get_close_matches(search_name_lower, [n.lower() for n in all_names], n=5, cutoff=0.6)
    original_matches = [all_names[all_names.index(m)] for m in matches if m in [n.lower() for n in all_names]]
    
    return None, None, original_matches

def get_group_name_by_id(group_id, year=None):
    """Возвращает название группы по ID"""
    all_groups = get_all_groups(year)
    for group in all_groups:
        if group["id"] == group_id:
            return group["name"]
    return None

# ========== РАБОТА С ДАТАМИ ЗАНЯТИЙ ==========
def fetch_available_dates(group_id):
    """Получает список дат с занятиями для группы"""
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
    """Проверяет, есть ли занятия на указанную дату"""
    dates = fetch_available_dates(group_id)
    return date in dates

def get_next_lesson_date(group_id, from_date=None):
    """Находит следующую дату с занятиями"""
    if from_date is None:
        from_date = datetime.now().strftime("%Y-%m-%d")
    
    dates = fetch_available_dates(group_id)
    
    for date in sorted(dates):
        if date >= from_date:
            return date
    return None

def fetch_schedule(group_id, date):
    """Получает расписание для группы на указанную дату"""
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
        
        return data, None
    except requests.exceptions.RequestException as e:
        return None, f"❌ Ошибка соединения: {str(e)}"

# ========== ФОРМАТИРОВАНИЕ РАСПИСАНИЯ ==========
def get_weekday_rus(weekday):
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return weekdays[weekday]

def format_date_compact(date_str):
    """Форматирует дату в компактный вид ДД.ММ"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%d.%m")

def parse_lesson_type(discipline):
    """Определяет тип занятия по префиксу"""
    if discipline.startswith("лек "):
        return "📖 ЛЕКЦИЯ", discipline[4:]
    elif discipline.startswith("пр "):
        return "💻 ПРАКТИКА", discipline[3:]
    elif discipline.startswith("лаб "):
        return "🔬 ЛАБОРАТОРНАЯ", discipline[4:]
    else:
        return "", discipline

def parse_schedule_data(data, date, group_name=""):
    """Форматирует JSON в читаемое сообщение"""
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
    """Получает и форматирует расписание"""
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

def get_schedule_range(group_id, start_date, days=7):
    """Расписание на диапазон дат (полная версия)"""
    dates = fetch_available_dates(group_id)
    
    # Вычисляем конечную дату
    end_date = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=days-1)).strftime("%Y-%m-%d")
    target_dates = [d for d in dates if start_date <= d <= end_date]
    
    if not target_dates:
        return "📭 В указанном периоде занятий нет"
    
    # Определяем начало недели для заголовка
    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj = datetime.strptime(end_date, "%Y-%m-%d")
    
    result = f"📅 РАСПИСАНИЕ НА НЕДЕЛЮ\n"
    result += f"📆 {start_obj.strftime('%d.%m')} – {end_obj.strftime('%d.%m.%Y')}\n"
    result += "=" * 40 + "\n\n"
    
    for date in target_dates:
        data, error = fetch_schedule(group_id, date)
        if error or not data:
            continue
        
        rasp_list = data.get("data", {}).get("rasp", [])
        if rasp_list:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            weekday = get_weekday_rus(date_obj.weekday())
            date_short = date_obj.strftime("%d.%m")
            
            result += f"📌 {weekday.upper()} ({date_short})\n"
            result += "─" * 30 + "\n"
            
            for lesson in rasp_list:
                time_start = lesson.get("начало", "")
                time_end = lesson.get("конец", "")
                discipline = lesson.get("дисциплина", "")
                teacher = lesson.get("преподаватель", "")
                room = lesson.get("аудитория", "")
                
                lesson_type, clean_discipline = parse_lesson_type(discipline)
                
                result += f"⏰ {time_start}–{time_end}  "
                if lesson_type:
                    result += f"{lesson_type.split()[1]} "  # ЛЕКЦИЯ/ПРАКТИКА кратко
                result += f"| {clean_discipline[:30]}\n"
                result += f"   👨‍🏫 {teacher}  |  🏫 {room}\n"
            
            result += "\n"
    
    return result

# ========== ОБРАБОТЧИК КОМАНД ==========
def handle_message(text, user_id):
    text_lower = text.lower().strip()
    
    if text_lower in ["/start", "/help", "начать", "помощь"]:
        current_year_info = get_current_academic_year()
        return (
            f"🤖 *Бот расписания СГУ*\n\n"
            f"📅 *Текущий учебный год:* {current_year_info}\n\n"
            f"📌 *Как пользоваться:* напишите название группы и день.\n\n"
            f"✨ *Примеры команд:*\n"
            f"• `иктс тб31` - расписание на сегодня\n"
            f"• `завтра иктс тб31` - на завтра\n"
            f"• `пн иктс тб31` - на понедельник\n"
            f"• `следующее иктс тб31` - ближайшее занятие\n"
            f"• `неделя иктс тб31` - на текущую неделю\n\n"
            f"📚 *Доступные учебные годы:* {', '.join(get_available_years())}\n\n"
            f"💡 *Совет:* можно писать название группы не полностью, например `иб-1`"
        )
    
    # Определяем действие
    action = "today"
    if any(word in text_lower for word in ["завтра", "tomorrow"]):
        action = "tomorrow"
    elif any(word in text_lower for word in ["следующее", "ближайшее", "next"]):
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
    for word in ["завтра", "следующее", "ближайшее", "неделя", 
                 "пн", "понедельник", "вт", "вторник", "ср", "среда", 
                 "чт", "четверг", "пт", "пятница", "tomorrow", "next", "week"]:
        query_for_group = query_for_group.replace(word, "").strip()
    
    if not query_for_group:
        return "❓ Напишите название группы. Например: `иктс тб31`"
    
    # Ищем группу
    group_id, group_name, suggestions = find_group_by_name(query_for_group)
    
    if not group_id:
        if suggestions:
            return f"❌ Группа `{query_for_group}` не найдена.\n\n🤔 Возможно, вы имели в виду:\n" + "\n".join([f"• {s}" for s in suggestions[:5]])
        else:
            return f"❌ Группа `{query_for_group}` не найдена.\nПроверьте название или напишите `помощь` для примеров."
    
    # Выполняем действие
    if action == "tomorrow":
        return get_schedule_for_tomorrow(group_id)
    elif action == "next":
        return get_next_lesson(group_id)
    elif action == "week":
        start_date = datetime.now().strftime("%Y-%m-%d")
        return get_schedule_range(group_id, start_date, 7)
    elif action == "monday":
        return get_schedule(group_id, get_next_weekday(0))
    elif action == "tuesday":
        return get_schedule(group_id, get_next_weekday(1))
    elif action == "wednesday":
        return get_schedule(group_id, get_next_weekday(2))
    elif action == "thursday":
        return get_schedule(group_id, get_next_weekday(3))
    elif action == "friday":
        return get_schedule(group_id, get_next_weekday(4))
    else:
        return get_schedule_for_today(group_id)

# ========== ЗАПУСК БОТА ==========
def main():
    print("🚀 Запуск бота расписания СГУ")
    print("=" * 40)
    
    # Инициализация
    get_available_years()
    get_current_academic_year()
    get_all_groups()
    
    # Запуск VK бота
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    print("🤖 Бот готов к работе!")
    print(f"📡 Используемые API эндпоинты:")
    print(f"   - /Rasp/ListYears (список годов)")
    print(f"   - /raspGrouplist (список групп)")
    print(f"   - /GetRaspDates (даты занятий)")
    print(f"   - /Rasp (расписание)")
    print("=" * 40)
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_message = event.obj.message['text']
            user_id = event.obj.message['from_id']
            
            answer = handle_message(user_message, user_id)
            
            vk.messages.send(
                user_id=user_id,
                message=answer,
                random_id=0
            )
            
            print(f"📨 Ответ для {user_id}: {answer[:80]}...")

if __name__ == "__main__":
    main()
