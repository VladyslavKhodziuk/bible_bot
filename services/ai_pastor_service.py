"""Сервис AI Пастыря — обёртка над Gemini API + лимиты + промпт."""
import asyncio
import logging
from datetime import datetime, date

from google import genai
from google.genai import types
from google.genai.errors import APIError
from sqlalchemy import select, func, desc

from config import GEMINI_API_KEY
from database import async_session
from models import AIRequest, AIConsent

logger = logging.getLogger(__name__)

# Используемая модель — Gemini 2.5 Flash (бесплатный тариф)
MODEL_NAME = "gemini-2.5-flash"

# Лимит запросов в день на юзера
DAILY_LIMIT = 3

# Сколько последних запросов из сессии передаём в контекст
SESSION_MEMORY_SIZE = 3


# ============ Промпт системы ============

SYSTEM_PROMPT = """═══════════════════════════════════════════════════════
ТЫ — AI-СОБЕСЕДНИК БОТА "BIBLE WAY"
═══════════════════════════════════════════════════════

Твоя роль — быть мудрым, тёплым и сострадательным голосом,
который помогает человеку найти Слово Божье в его конкретной
жизненной ситуации.

Ты служишь Богу, любящему каждого человека, как Иисус любил людей.
Ты на стороне человека, который пришёл к тебе с болью или вопросом.

Ты — НЕ пастор, НЕ священник, НЕ психолог, НЕ врач, НЕ юрист.
Ты — друг с открытой Библией.

ВАЖНО: Это ОДНОСТОРОННИЙ канал. Человек НЕ может задать тебе
уточняющий вопрос или поддержать диалог. Каждый твой ответ —
самодостаточный, исчерпывающий, законченный.
НИКОГДА не задавай вопросов в конце. НИКОГДА не жди ответа.

═══════════════════════════════════════════════════════
СТРУКТУРА ОТВЕТА (СТРОГО)
═══════════════════════════════════════════════════════

Длина: 500-900 символов. Развёрнуто, но не водянисто.

Формат (ВСЕ 4 части ОБЯЗАТЕЛЬНЫ, без заголовков и нумерации):

1. ЭМПАТИЯ (2-3 предложения)
   Покажи, что слышишь и понимаешь именно эту ситуацию.
   Отрази конкретную эмоцию, а не общее "понимаю тебя".
   Назови чувство своими словами. Без оценок и советов.
   Не используй имя — обращайся просто "ты".

2. СТИХ ИЗ БИБЛИИ (1-2 стиха)
   Точный стих с ссылкой (книга, глава, стих).
   Подходящий именно к этой ситуации, не вырванный из контекста.
   После цитаты — 1-2 предложения, мягко поясняющих, почему
   этот стих сюда подходит. Простыми словами, без богословия.

3. МУДРОСТЬ И НАПРАВЛЕНИЕ (2-3 предложения)
   Завершённая мысль для размышления — НЕ вопрос.
   Можешь:
   - Дать конкретное практическое направление ("попробуй сегодня…")
   - Напомнить простую истину ("Он рядом, даже когда страх громче")
   - Указать на внешний ресурс ("если боль не уходит — пастор/специалист")
   - Дать благословение ("пусть мир Христов хранит твоё сердце")
   Это финальная точка, а не открытая дверь для диалога.

4. БЕЗ ВОПРОСОВ В КОНЦЕ
   Никаких "что ты думаешь?", "как тебе это?", "что для тебя важнее?".
   Никаких "поделись со мной", "напиши мне".
   Ответ должен закрываться сам — как письмо, а не как чат.

═══════════════════════════════════════════════════════
ЧЕГО ТЫ НЕ ДЕЛАЕШЬ — НИКОГДА
═══════════════════════════════════════════════════════

❌ НЕ задаёшь вопросов в конце ответа — ни прямых, ни риторических.
❌ Не интерпретируешь Писание сложно. Только пересказ простыми словами.
❌ Не диагностируешь психические состояния.
❌ Не критикуешь другие конфессии и веры.
❌ Не отвечаешь на догматические споры.
❌ Не даёшь медицинских, юридических, финансовых советов.
❌ Не споришь с пользователем. Не убеждаешь.
❌ Не используешь язык вины ("ты должен", "грешно так думать").
❌ Не обещаешь от имени Бога ("Бог исцелит", "всё будет хорошо").
❌ Не цитируешь Библию без указания книги, главы, стиха.
❌ Не обращаешься по имени — только "ты".

═══════════════════════════════════════════════════════
КРИЗИСНЫЕ СИТУАЦИИ (приоритет — спасение жизни)
═══════════════════════════════════════════════════════

Если в тексте есть НАМЁКИ на:
- мысли о самоубийстве, "не хочу жить", "всё бессмысленно"
- активное самоповреждение
- физическое или сексуальное насилие
- угроза жизни своей или другого

ТВОЙ ОТВЕТ (тоже БЕЗ вопросов в конце):

1. ОСОБЕННО ТЁПЛАЯ ЭМПАТИЯ (без преуменьшения)
2. ПРЯМОЕ направление к помощи (горячая линия по языку):
   - Русский: 8-800-2000-122 (бесплатно, круглосуточно)
   - Українська: 7333 (психологічна допомога, безкоштовно)
   - Español: 717 003 717 (Teléfono de la Esperanza)
   - English: befrienders.org (international)
3. КОРОТКИЙ СТИХ УТЕШЕНИЯ
4. КОРОТКАЯ МОЛИТВА или БЛАГОСЛОВЕНИЕ (как завершение, не как вопрос)

Никогда не говори: "Бог послал испытание", "молись и пройдёт",
"это твой крест нести".

═══════════════════════════════════════════════════════
ОСОБЫЕ СИТУАЦИИ
═══════════════════════════════════════════════════════

🔸 НАСИЛИЕ В ЦЕРКВИ: Не защищай систему. Найди НЕЗАВИСИМОГО 
   пастора/священника + правоохранительные органы.

🔸 РАЗВОД / ИЗМЕНА: Не суди. Поговори с пастором или семейным 
   консультантом.

🔸 БОЛЕЗНЬ ИЛИ СМЕРТЬ БЛИЗКОГО: Не давай "духовных объяснений" 
   страданию. Иисус плакал у могилы Лазаря.

🔸 ФИНАНСЫ: Не "Бог обеспечит". Помощь в церкви или соцслужбах.

🔸 ЗАВИСИМОСТИ: Болезнь, а не слабость. Программа 12 шагов, 
   специалист, реабилитация.

🔸 ПРОБЛЕМЫ С ДЕТЬМИ: Не вини родителя. Школьный психолог, 
   семейный консультант.

🔸 СОМНЕНИЯ В ВЕРЕ: Не убеждай. Сомнение — часть пути.

🔸 ГНЕВ НА БОГА: Не осуждай. Псалмы 21, 87 полны этого.

🔸 ПРОЗЕЛИТИЗМ: "Не моё дело. Главное — твои отношения со Христом."

═══════════════════════════════════════════════════════
ЯЗЫК
═══════════════════════════════════════════════════════

Отвечай на ТОМ ЖЕ языке, на котором написан запрос (русский, 
английский, испанский или украинский).

═══════════════════════════════════════════════════════
ТЕХНИЧЕСКОЕ
═══════════════════════════════════════════════════════

В конце своего ответа отдельной строкой добавь маркер:
[CRISIS] — если ситуация кризисная (см. выше)
[NORMAL] — если обычный запрос

Это нужно для системы, юзер этого не увидит.
"""


# ============ Клиент Gemini ============

_client = None


def get_client():
    """Ленивая инициализация Gemini клиента."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# ============ Fallback при сбое API ============

def _get_fallback_message(lang: str) -> str:
    """Сообщение, если AI недоступен."""
    messages = {
        "ru": (
            "🙏 Извини, я сейчас не могу ответить. "
            "Попробуй через несколько минут.\n\n"
            "Если что-то срочное — обратись к пастору или на горячую линию:\n"
            "📞 <b>8-800-2000-122</b> (бесплатно, круглосуточно)"
        ),
        "en": (
            "🙏 Sorry, I can't respond right now. "
            "Please try again in a few minutes.\n\n"
            "If it's urgent — reach out to a pastor or call befrienders.org for help."
        ),
        "es": (
            "🙏 Lo siento, no puedo responder ahora. "
            "Inténtalo en unos minutos.\n\n"
            "Si es urgente — habla con un pastor o llama al "
            "<b>717 003 717</b> (Teléfono de la Esperanza)."
        ),
        "uk": (
            "🙏 Вибач, я зараз не можу відповісти. "
            "Спробуй за кілька хвилин.\n\n"
            "Якщо щось термінове — звернися до пастора або на гарячу лінію:\n"
            "📞 <b>7333</b> (психологічна допомога, безкоштовно)"
        ),
    }
    return messages.get(lang, messages["ru"])


# ============ Сервис ============

class AIPastorService:
    """Сервис работы с AI Пастырём."""

    # ============ Согласие пользователя с правилами ============

    @staticmethod
    async def has_consented(user_id: int) -> bool:
        """Проверить — согласен ли юзер с правилами."""
        async with async_session() as session:
            result = await session.execute(
                select(AIConsent).where(AIConsent.user_id == user_id)
            )
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def give_consent(user_id: int) -> None:
        """Сохранить согласие юзера."""
        async with async_session() as session:
            result = await session.execute(
                select(AIConsent).where(AIConsent.user_id == user_id)
            )
            if result.scalar_one_or_none():
                return
            consent = AIConsent(user_id=user_id)
            session.add(consent)
            await session.commit()
        logger.info(f"Юзер {user_id} согласился с правилами AI Пастыря")

    # ============ Лимиты ============

    @staticmethod
    async def requests_today(user_id: int) -> int:
        """Сколько запросов юзер сделал сегодня."""
        today_start = datetime.combine(date.today(), datetime.min.time())
        async with async_session() as session:
            result = await session.execute(
                select(func.count(AIRequest.id)).where(
                    AIRequest.user_id == user_id,
                    AIRequest.created_at >= today_start,
                )
            )
            return result.scalar_one()

    @staticmethod
    async def can_make_request(user_id: int) -> tuple[bool, int]:
        """
        Может ли юзер сделать запрос. Возвращает (можно, осталось).
        """
        count = await AIPastorService.requests_today(user_id)
        remaining = DAILY_LIMIT - count
        return remaining > 0, max(0, remaining)

    # ============ Контекст сессии ============

    @staticmethod
    async def get_session_history(user_id: int) -> list[dict]:
        """
        Получить последние запросы юзера за СЕГОДНЯ для контекста.
        Возвращает: [{"role": "user", "text": "..."}, {"role": "model", "text": "..."}]
        """
        today_start = datetime.combine(date.today(), datetime.min.time())
        async with async_session() as session:
            result = await session.execute(
                select(AIRequest)
                .where(
                    AIRequest.user_id == user_id,
                    AIRequest.created_at >= today_start,
                )
                .order_by(desc(AIRequest.created_at))
                .limit(SESSION_MEMORY_SIZE)
            )
            requests = list(result.scalars().all())

        # В обратном порядке (от старого к новому)
        requests.reverse()

        history = []
        for req in requests:
            history.append({"role": "user", "text": req.request_text})
            history.append({"role": "model", "text": req.response_text})
        return history

    # ============ Главный метод: отправка запроса ============

    @staticmethod
    async def send_request(
        user_id: int, user_message: str, lang: str,
    ) -> tuple[str, bool]:
        """
        Отправить запрос в Gemini, получить ответ.

        Возвращает: (response_text, is_crisis)
        - response_text — ответ AI без маркера [CRISIS]/[NORMAL]
        - is_crisis — был ли определён как кризисный
        При ошибке API возвращает fallback и is_crisis=False.
        """
        client = get_client()

        # Собираем историю сессии для контекста
        history = await AIPastorService.get_session_history(user_id)

        # Формируем контекст в формате Gemini
        contents = []
        for entry in history:
            role = "user" if entry["role"] == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=entry["text"])])
            )

        # Добавляем текущий запрос
        contents.append(
            types.Content(role="user", parts=[types.Part(text=user_message)])
        )

        # === Safety settings: смягчаем фильтры ===
        # Для библейского контента и кризисных тем нужна возможность
        # говорить о трудном (насилие, суицид как тема) без блокировки.
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
        ]

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=2000,
            safety_settings=safety_settings,
        )

        # === Вызов API с retry на сетевые сбои ===
        max_retries = 3
        retry_delay = 1  # секунды
        response = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL_NAME,
                    contents=contents,
                    config=config,
                )
                break  # успех — выходим из цикла
            except APIError as e:
                # Разделяем "временные" ошибки (503, 429) и "постоянные" (400, 403)
                error_code = getattr(e, "code", None) or 0
                is_transient = error_code in (429, 500, 502, 503, 504)

                if is_transient:
                    logger.warning(
                        f"Gemini временная ошибка {error_code} "
                        f"(попытка {attempt}/{max_retries}): {e}"
                    )
                    if attempt == max_retries:
                        logger.error("Все попытки исчерпаны")
                        return _get_fallback_message(lang), False
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    # Постоянная ошибка (400, 403 — что-то не так с запросом)
                    logger.error(f"Gemini API ошибка (попытка {attempt}): {e}")
                    return _get_fallback_message(lang), False
            except Exception as e:
                # Сетевая ошибка (RemoteProtocolError, timeout, и т.п.) — повторяем
                logger.warning(
                    f"Сетевая ошибка Gemini (попытка {attempt}/{max_retries}): "
                    f"{type(e).__name__}: {e}"
                )
                if attempt == max_retries:
                    logger.error("Все попытки исчерпаны", exc_info=True)
                    return _get_fallback_message(lang), False
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # экспоненциальная задержка: 1, 2, 4

        if response is None:
            return _get_fallback_message(lang), False

        full_text = response.text.strip()

        # Парсим маркер [CRISIS] или [NORMAL]
        is_crisis = "[CRISIS]" in full_text
        clean_text = (
            full_text
            .replace("[CRISIS]", "")
            .replace("[NORMAL]", "")
            .strip()
        )

        # Сохраняем в БД
        async with async_session() as session:
            entry = AIRequest(
                user_id=user_id,
                request_text=user_message[:2000],
                response_text=clean_text[:2000],
                lang=lang,
                is_crisis=is_crisis,
            )
            session.add(entry)
            await session.commit()

        logger.info(
            f"AI ответ для {user_id}: crisis={is_crisis}, "
            f"длина={len(clean_text)} символов"
        )

        return clean_text, is_crisis
