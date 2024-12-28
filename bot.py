import asyncio
import logging
import random
import string
from datetime import datetime, timedelta, time, date
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

from config import Config, load_config
from models import Storage, Cat
from keyboards import (
    get_color_keyboard,
    get_main_keyboard,
    get_confirm_keyboard,
    get_cat_actions_keyboard,
    get_walk_control_keyboard,
    get_cancel_message_keyboard
)
from image_generator import ImageGenerator

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния FSM
class CatStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_color = State()
    waiting_for_code = State()
    waiting_for_walk_time = State()
    waiting_for_message = State()

class CatBot:
    def __init__(self):
        self.config = load_config()
        self.storage = Storage()
        self.image_generator = ImageGenerator()
        self.bot = Bot(self.config.token)
        self.dp = Dispatcher()
        self.scheduler = AsyncIOScheduler(timezone=self.config.timezone)
        self.setup_handlers()
        self.setup_scheduler()

    def setup_handlers(self):
        # Команды
        self.dp.message.register(self.cmd_start, Command('start'))
        self.dp.message.register(self.cmd_connect, Command('connect'))
        self.dp.message.register(self.cmd_message, Command('message'))
        
        # Колбэки
        self.dp.callback_query.register(
            self.process_color_selection,
            F.data.startswith('color_')
        )
        self.dp.callback_query.register(
            self.process_cat_action,
            F.data.startswith('action_')
        )
        self.dp.callback_query.register(
            self.process_walk_control,
            F.data.startswith('walk_')
        )
        self.dp.callback_query.register(
            self.process_message_cancel,
            F.data == 'cancel_message'
        )
        
        # Текстовые сообщения
        self.dp.message.register(self.process_name, CatStates.waiting_for_name)
        self.dp.message.register(self.process_connection_code, CatStates.waiting_for_code)
        self.dp.message.register(self.process_walk_time, CatStates.waiting_for_walk_time)
        self.dp.message.register(self.process_message, CatStates.waiting_for_message)
        self.dp.message.register(self.process_message, CatStates.waiting_for_message, F.photo)
        self.dp.message.register(self.process_main_keyboard, F.text)

    def setup_scheduler(self):
        # Уменьшение характеристик
        self.scheduler.add_job(
            self.decrease_stats,
            'interval',
            hours=self.config.stats_decrease_hours
        )
        
        # Очистка просроченных кодов подключения
        self.scheduler.add_job(
            self.cleanup_connection_codes,
            'interval',
            hours=1
        )
        
        # Поздравление с днем рождения (26 января)
        self.scheduler.add_job(
            self.send_birthday_greeting,
            CronTrigger(
                month=1,
                day=26,
                hour=0,
                minute=0,
                timezone=self.config.timezone
            )
        )
        
        # Поздравление с Новым годом (1 января)
        self.scheduler.add_job(
            self.send_new_year_greeting,
            CronTrigger(
                month=1,
                day=1,
                hour=0,
                minute=0,
                timezone=self.config.timezone
            )
        )

    async def decrease_stats(self):
        now = datetime.now(timezone(self.config.timezone))
        
        # Не уменьшаем характеристики ночью
        if self.config.night_start <= now.time() <= self.config.night_end:
            return
            
        for cat in self.storage.cats.values():
            cat.hunger = max(0, cat.hunger - 1)
            cat.happiness = max(0, cat.happiness - 1)
            cat.energy = max(0, cat.energy - 1)
        
        self.storage.save()

    async def cleanup_connection_codes(self):
        now = datetime.now()
        expired_codes = [
            code for code, (_, expires) in self.storage.connection_codes.items()
            if expires < now
        ]
        for code in expired_codes:
            del self.storage.connection_codes[code]
        self.storage.save()

    async def send_birthday_greeting(self):
        """Отправка поздравления хозяйке от котика."""
        # Отправляем поздравление только владельцам (Маше)
        for cat in self.storage.cats.values():
            greeting_text = (
                f"Сообщение от {cat.name}:\n\n"
                "Любимая Машенька! 🎉\n"
                "Поздравляю тебя с днём рождения! 🎂\n"
                "Спасибо, что заботишься обо мне, играешь со мной и любишь меня. "
                "Ты самая лучшая хозяйка на свете! ❤️\n"
                "Желаю тебе много счастья, радости и вкусных угощений "
                "\n\n"
                "Твой котик 🐱"
            )
            # Отправляем только владельцу (Маше)
            await self.bot.send_message(cat.owner_id, greeting_text)

    async def send_new_year_greeting(self):
        """Отправка новогоднего поздравления всем пользователям."""
        greeting_text = "С новым годоооом!!!! ❤️🎄🎅🎁✨"
        
        # Отправляем поздравление всем владельцам и подключенным пользователям
        for cat in self.storage.cats.values():
            # Отправляем владельцу
            await self.bot.send_message(cat.owner_id, greeting_text)
            
            # Отправляем подключенным пользователям
            for user_id in cat.connected_users:
                await self.bot.send_message(user_id, greeting_text)

    async def cmd_start(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Проверяем, есть ли уже котик у пользователя
        if user_id in self.storage.cats:
            await self.send_cat_status(user_id, "Вот ваш котик! 🐱")
            await message.answer(
                "Используй кнопки под фото для взаимодействия с котиком 🎮\n"
                "или кнопку на клавиатуре для установки времени прогулки 🚶‍♂️:",
                reply_markup=get_main_keyboard()
            )
            return
            
        await message.answer("Давай создадим твоего котика! 🎉\nКак ты хочешь его назвать? ✨")
        await state.set_state(CatStates.waiting_for_name)

    async def process_name(self, message: Message, state: FSMContext):
        await state.update_data(name=message.text)
        await message.answer(
            f"Отличное имя! 🌟\nТеперь выбери цвет котика 🎨:",
            reply_markup=get_color_keyboard()
        )
        await state.set_state(CatStates.waiting_for_color)

    async def process_color_selection(self, callback: CallbackQuery, state: FSMContext):
        color = callback.data.split('_')[1]
        data = await state.get_data()
        
        # Создаем нового котика
        cat = Cat(
            owner_id=callback.from_user.id,
            name=data['name'],
            color=color
        )
        
        self.storage.cats[callback.from_user.id] = cat
        
        # Генерируем код подключения
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        expires = datetime.now() + timedelta(hours=self.config.connection_code_ttl)
        self.storage.connection_codes[code] = (callback.from_user.id, expires)
        
        self.storage.save()
        
        # Отправляем приветственное сообщение с кодом
        await self.send_cat_status(
            callback.from_user.id,
            f"Поздравляем! 🎉 Ты создала котика {data['name']}! ✨\n\n"
            f"Твой код для подключения других пользоватлей: 🔑 {code}\n"
        )
        await callback.message.answer(
            "Используй кнопки под фото для взаимодействия с котиком 🎮\n"
            "или кнопку на клавиатуре для установки времени прогулки 🚶‍♂️:",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        await callback.answer()

    async def send_cat_status(self, user_id: int, message_text: str = None, owner_id: int = None):
        # Если owner_id не указан, значит это владелец котика
        cat_owner_id = owner_id if owner_id is not None else user_id
        cat = self.storage.cats[cat_owner_id]
        
        image_path = self.image_generator.generate_status_image(
            color=cat.color,
            name=cat.name,
            hunger=cat.hunger,
            happiness=cat.happiness,
            energy=cat.energy,
            owner_m="",  # Оставляем пустым, так как это не важно для статуса
            owner_f="",
            age_days=cat.age_days
        )
        
        await self.bot.send_photo(
            chat_id=user_id,
            photo=FSInputFile(image_path),
            caption=message_text if message_text else None,
            reply_markup=get_cat_actions_keyboard()
        )

    async def process_cat_action(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        # Ищем котика, к которому подключен пользователь
        owner_id = None
        for cat_owner_id, cat in self.storage.cats.items():
            if user_id == cat_owner_id or user_id in cat.connected_users:
                owner_id = cat_owner_id
                break
                
        if not owner_id:
            await callback.answer("У тебя нет котика! 😿")
            return
            
        cat = self.storage.cats[owner_id]
        action = callback.data.split('_')[1]
        message_text = None
        is_connected_user = user_id != owner_id
        
        match action:
            case "feed":
                if cat.hunger >= 4:
                    await callback.answer("Котик не голоден! 😊")
                    return
                cat.hunger = min(4, cat.hunger + 1)
                message_text = "Вы покормили котика! 🍽️"
                if is_connected_user:
                    await self.bot.send_message(owner_id, "Стас покормил котика 🍽️")
                
            case "play":
                if cat.energy <= 0:
                    await callback.answer("Котик слишком устал для игр! 😴")
                    return
                cat.happiness = min(4, cat.happiness + 1)
                cat.energy = max(0, cat.energy - 1)
                message_text = "Ты поиграла с котиком! 🎾"
                if is_connected_user:
                    await self.bot.send_message(owner_id, "Стас поиграл с котиком 🎾")
                
            case "sleep":
                if cat.energy >= 4:
                    await callback.answer("Котик не хочет спать! 👀")
                    return
                cat.energy = min(4, cat.energy + 2)
                message_text = "Котик поспал и восстановил энергию! 💤"
                if is_connected_user:
                    await self.bot.send_message(owner_id, "Стас уложил котика спать 💤")
                
            case "status":
                pass  # Просто покажем статус без сообщения
        
        self.storage.save()
        
        # Удаляем предыдущее сообщение со статусом
        await callback.message.delete()
        
        # Отправляем новое сообщение со статусом
        await self.send_cat_status(user_id, message_text, owner_id)
        await callback.answer()

    async def process_walk_control(self, callback: CallbackQuery, state: FSMContext):
        action = callback.data.split('_', 1)[1]
        user_id = callback.from_user.id
        
        # Ищем котика, к которому подключен пользователь
        owner_id = None
        for cat_owner_id, cat in self.storage.cats.items():
            if user_id == cat_owner_id or user_id in cat.connected_users:
                owner_id = cat_owner_id
                break
                
        if not owner_id:
            await callback.answer("У тебя нет котика!")
            return
            
        cat = self.storage.cats[owner_id]
        is_connected_user = user_id != owner_id
        
        # Обработка быстрого выбора времени
        if action.startswith('time_'):
            time_str = action.split('_')[1]
            hour, minute = map(int, time_str.split(':'))
            
            # Обновляем время прогулки
            cat.walk_time = time_str
            self.storage.save()
            
            # Уведомляем владельца о смене времени прогулки
            if is_connected_user:
                await self.bot.send_message(
                    owner_id,
                    f"Стас установил время прогулки на {time_str} 🕒"
                )
            
            # Настраиваем напоминания
            walk_id = f"walk_{owner_id}"
            
            # Удаляем старые напоминания, если они есть
            for job in self.scheduler.get_jobs():
                if job.id.startswith(walk_id):
                    self.scheduler.remove_job(job.id)
            
            # Устанавливаем время для напоминаний
            walk_datetime = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            if walk_datetime < datetime.now():
                walk_datetime += timedelta(days=1)
            
            # Добавляем напоминания
            reminders = [
                (60, "До прогулки остался 1 час! ⏰"),
                (30, "До прогулки осталось 30 минут! ⏰"),
                (10, "До прогулки осталось 10 минут! ⏰"),
                (0, "Пора гулять! 🚶‍♂️")
            ]
            
            for minutes_before, text in reminders:
                notify_datetime = walk_datetime - timedelta(minutes=minutes_before)
                
                # Если время уведомл��ния уже прошло, пропускаем его
                if notify_datetime <= datetime.now():
                    continue
                
                self.scheduler.add_job(
                    self.send_walk_notification,
                    'date',
                    run_date=notify_datetime,
                    args=[owner_id, f"{text} {cat.name.capitalize()} ждёт 🐱"],
                    id=f"{walk_id}_{minutes_before}"
                )
                
                # Отправляем уведомления и подключенным пользователям
                for connected_user in cat.connected_users:
                    self.scheduler.add_job(
                        self.send_walk_notification,
                        'date',
                        run_date=notify_datetime,
                        args=[connected_user, f"{text}"],
                        id=f"{walk_id}_{minutes_before}_{connected_user}"
                    )
            
            # Отправляем подтверждение и очищаем состояние
            await state.clear()  # Очищаем состояние после установки времени
            await callback.message.edit_text(
                f"Время прогулки установлено на {time_str}! ⏰\n\n"
                "Я напомню о прогулке:\n"
                "- За 1 час до прогулки 🕐\n"
                "- За 30 минут до прогулки 🕐\n"
                "- За 10 минут до прогулки 🕐\n"
                "- В момент начала прогулки 🚶‍♂️"
            )
            await callback.answer()
            return
            
        match action:
            case "cancel_setup":
                await state.clear()
                await callback.message.delete()
                await callback.answer("Установка времени отменена")
                await self.send_cat_status(user_id, owner_id=owner_id)
                
            case "delete_time":
                if not cat.walk_time:
                    await callback.answer("Время прогулки не установлено!")
                    return
                    
                # Удаляем задачи уведомлений
                walk_id = f"walk_{owner_id}"
                for job in self.scheduler.get_jobs():
                    if job.id.startswith(walk_id):
                        self.scheduler.remove_job(job.id)
                
                cat.walk_time = None
                self.storage.save()
                await state.clear()
                await callback.message.delete()
                await callback.answer("Время п��огулки удалено")
                await self.send_cat_status(user_id, owner_id=owner_id)

    async def process_main_keyboard(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Ищем котика, к которому подключен пользователь
        owner_id = None
        for cat_owner_id, cat in self.storage.cats.items():
            if user_id == cat_owner_id or user_id in cat.connected_users:
                owner_id = cat_owner_id
                break
                
        if not owner_id:
            await message.answer("У тебя нет котика! 😿")
            return
            
        cat = self.storage.cats[owner_id]
        
        if message.text == "Управление котиком":
            await self.send_cat_status(user_id, owner_id=owner_id)
        elif message.text == "Прогулка":
            current_time = cat.walk_time if cat.walk_time else "не установлено"
            
            await message.answer(
                f"Текущее время прогулки: {current_time} 🕒\n"
                "Выбери время прогулки из предложенных вариантов или введи своё время в одном из форматов:\n"
                "ЧЧ:ММ (например: 14:30)\n"
                "ЧЧ.ММ (например: 14.30)\n"
                "ЧЧ (например: 14)\n"
                "Ч (например: 9) ⏰",
                reply_markup=get_walk_control_keyboard(has_walk_time=cat.walk_time is not None)
            )
            await state.set_state(CatStates.waiting_for_walk_time)
        elif message.text == "Отправить сообщение":
            # Сначала показываем предупреждение о лимите
            await message.answer("⚠️ Внимание! Сообщение можно отправить только один раз в день (24 часа)!")
            
            # Проверяем, отправлял ли пользователь сообщение сегодня
            now = datetime.now(timezone(self.config.timezone))
            last_message_date = cat.last_messages.get(user_id)
            
            if last_message_date:
                # Преобразуем время последнего сообщения в часовой пояс Новосибирска
                last_message_date = last_message_date.astimezone(timezone(self.config.timezone))
                # Проверяем, прошло ли 24 часа
                time_passed = now - last_message_date
                if time_passed.total_seconds() < 24 * 3600:  # меньше 24 часов
                    # Вычисляем, сколько осталось ждать
                    seconds_left = 24 * 3600 - time_passed.total_seconds()
                    hours_left = int(seconds_left // 3600)
                    minutes_left = int((seconds_left % 3600) // 60)
                    await message.answer(f"Ты уже отправляла сообщение! Следующее сообщение можно будет отправить через {hours_left} ч. {minutes_left} мин. ⏳")
                    return
            
            await message.answer(
                "Отправь текстовое сообщение или фото с подписью ✏️ 📸:",
                reply_markup=get_cancel_message_keyboard()
            )
            await state.set_state(CatStates.waiting_for_message)
            await state.update_data(owner_id=owner_id)

    async def process_walk_time(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Ищем котика, к которому подключен пользователь
        owner_id = None
        for cat_owner_id, cat in self.storage.cats.items():
            if user_id == cat_owner_id or user_id in cat.connected_users:
                owner_id = cat_owner_id
                break
                
        if not owner_id:
            await message.answer("У тебя нет котика! 😿")
            await state.clear()
            return
            
        cat = self.storage.cats[owner_id]
        is_connected_user = user_id != owner_id
        
        if message.text.lower() == 'отмена':
            await message.answer("Установка времени отменена! ❌")
            await state.clear()
            await self.send_cat_status(user_id, owner_id=owner_id)
            return

        try:
            time_text = message.text.strip()
            hour = 0
            minute = 0
            
            # Обработка разных форматов
            if ':' in time_text:
                parts = time_text.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            elif '.' in time_text:
                parts = time_text.split('.')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            else:
                # Просто число - считаем как часы
                hour = int(time_text)
                minute = 0
            
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            
            # Проверяем, что время не ночное
            if hour < 6 or hour >= 22:
                await message.answer(
                    "Время прогулки должно быть между 6:00 и 22:00! 🌙",
                    reply_markup=get_walk_control_keyboard(has_walk_time=cat.walk_time is not None)
                )
                return

            time_str = f"{hour:02d}:{minute:02d}"
            walk_time = time_str
            
            # Обновляем время прогулки
            cat.walk_time = walk_time
            self.storage.save()
            
            # Уведомляем владельца о смене времени прогулки
            if is_connected_user:
                await self.bot.send_message(
                    owner_id,
                    f"Стас установил время прогулки на {time_str} 🕒"
                )
            
            # Настраиваем напоминания
            walk_id = f"walk_{owner_id}"
            
            # Удаляем старые напоминания, если они есть
            for job in self.scheduler.get_jobs():
                if job.id.startswith(walk_id):
                    self.scheduler.remove_job(job.id)
            
            # Устанавливаем время для напоминаний
            walk_datetime = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            if walk_datetime < datetime.now():
                walk_datetime += timedelta(days=1)
            
            # Добавляем напоминания
            reminders = [
                (60, "До прогулки остался 1 час! ⏰"),
                (30, "До прогулки осталось 30 минут! ⏰"),
                (10, "До прогулки осталось 10 минут! ⏰"),
                (0, "Пора гулять! 🚶‍♂️")
            ]
            
            for minutes_before, text in reminders:
                notify_datetime = walk_datetime - timedelta(minutes=minutes_before)
                
                # Если время уведомления уже прошло, пропускаем его
                if notify_datetime <= datetime.now():
                    continue
                
                self.scheduler.add_job(
                    self.send_walk_notification,
                    'date',
                    run_date=notify_datetime,
                    args=[owner_id, f"{text} {cat.name.capitalize()} ждёт 🐱"],
                    id=f"{walk_id}_{minutes_before}"
                )
                
                # Отправляем уведомления и подключенным пользователям
                for connected_user in cat.connected_users:
                    self.scheduler.add_job(
                        self.send_walk_notification,
                        'date',
                        run_date=notify_datetime,
                        args=[connected_user, f"{text}"],
                        id=f"{walk_id}_{minutes_before}_{connected_user}"
                    )
            
            # Настраиваем уведомления
            await message.answer(
                f"Время прогулки установлено на {time_str}! ⏰\n\n"
                "Я напомню о прогулке:\n"
                "- За 1 час до прогулки 🕐\n"
                "- За 30 минут до прогулки 🕐\n"
                "- За 10 минут до прогулки 🕐\n"
                "- В момент начала прогулки 🚶‍♂️"
            )
            await state.clear()
            await self.send_cat_status(user_id, owner_id=owner_id)
            
        except (ValueError, IndexError):
            # Создаем клавиатуру только с кнопкой отмены
            builder = InlineKeyboardBuilder()
            builder.button(text='Отменить установку ❌', callback_data='walk_cancel_setup')
            keyboard = builder.as_markup()
            
            await message.answer(
                "Пожалуйста, введи время в одном из форматов:\n"
                "ЧЧ:ММ (например: 14:30)\n"
                "ЧЧ.ММ (например: 14.30)\n"
                "ЧЧ (например: 14)\n"
                "Ч (например: 9) ⏰",
                reply_markup=keyboard
            )

    async def send_walk_notification(self, user_id: int, text: str):
        await self.bot.send_message(user_id, text)

    async def cmd_connect(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Проверяем, есть ли уже котик у пользователя
        if user_id in self.storage.cats:
            await message.answer(
                "У вас уже есть котик! 🐱 Вы не можете подключиться к другому. ❌"
            )
            return
            
        await message.answer("Введите код подключения 🔑:")
        await state.set_state(CatStates.waiting_for_code)

    async def process_connection_code(self, message: Message, state: FSMContext):
        code = message.text.upper()
        user_id = message.from_user.id
        
        if code not in self.storage.connection_codes:
            await message.answer("Неверный код подключения! ❌")
            await state.clear()
            return
            
        owner_id, expires = self.storage.connection_codes[code]
        
        if datetime.now() > expires:
            await message.answer("Код подключения истек! ⌛")
            del self.storage.connection_codes[code]
            self.storage.save()
            await state.clear()
            return
            
        cat = self.storage.cats[owner_id]
        if user_id not in cat.connected_users:
            cat.connected_users.append(user_id)
            self.storage.save()
            
            # Отправляем уведомление владельцу
            await self.bot.send_message(
                owner_id,
                "Стас подключился к котику 🤝"
            )
            
        # Отправляем статус котика от имени владельца
        await self.send_cat_status(
            user_id,
            f"Ты успешно подключился к котику {cat.name}! 🎉",
            owner_id
        )
        await message.answer(
            "Используй кнопки под фото для взаимодействия с котиком 🎮\n"
            "или кнопку на клавиатуре для установки времени прогулки 🚶‍♂️:",
            reply_markup=get_main_keyboard()
        )
        await state.clear()

    async def start(self):
        self.scheduler.start()
        await self.dp.start_polling(self.bot)

    async def check_walk_reminders(self):
        now = datetime.now(timezone(self.config.timezone))
        current_time = now.strftime('%H:%M')
        
        for cat in self.storage.cats.values():
            if not cat.walk_time:
                continue
            
            # Если текущее время больше времени прогулки, удаляем прогулку
            if current_time > cat.walk_time:
                cat.walk_time = None
                self.storage.save()
                continue
            
            # Вычисляем разницу во времени
            current_hours, current_minutes = map(int, current_time.split(':'))
            walk_hours, walk_minutes = map(int, cat.walk_time.split(':'))
            
            total_current_minutes = current_hours * 60 + current_minutes
            total_walk_minutes = walk_hours * 60 + walk_minutes
            minutes_left = total_walk_minutes - total_current_minutes
            
            if 0 <= minutes_left <= 30:
                if minutes_left > 0:
                    message = f"До прогулки осталось {minutes_left} минут!"
                else:
                    message = f"Пора гулять! 🐱"
                    cat.walk_time = None
                    self.storage.save()
                
                await self.bot.send_message(cat.owner_id, message)
                for user_id in cat.connected_users:
                    await self.bot.send_message(user_id, message)

    async def cmd_message(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Ищем котика, к которому подключен пользователь
        owner_id = None
        for cat_owner_id, cat in self.storage.cats.items():
            if user_id == cat_owner_id or user_id in cat.connected_users:
                owner_id = cat_owner_id
                break
                
        if not owner_id:
            await message.answer("У вас нет котика! 😿")
            return
            
        cat = self.storage.cats[owner_id]
        
        # Проверяем, прошло ли 24 часа с момента последнего сообщения
        now = datetime.now(timezone(self.config.timezone))
        last_message_date = cat.last_messages.get(user_id)
        
        if last_message_date:
            # Преобразуем время последнего сообщения в часовой пояс Новосибирска
            last_message_date = last_message_date.astimezone(timezone(self.config.timezone))
            # Проверяем, прошло ли 24 часа
            time_passed = now - last_message_date
            if time_passed.total_seconds() < 24 * 3600:  # меньше 24 часов
                # Вычисляем, сколько осталось ждать
                seconds_left = 24 * 3600 - time_passed.total_seconds()
                hours_left = int(seconds_left // 3600)
                minutes_left = int((seconds_left % 3600) // 60)
                await message.answer(f"Ты сможешь отправить следующее сообщение через {hours_left} ч. {minutes_left} мин. ⏳")
                return
            
        await message.answer(
            "Отправь текстовое сообщение или фото с подписью ✏️ 📸:",
            reply_markup=get_cancel_message_keyboard()
        )
        await state.set_state(CatStates.waiting_for_message)
        await state.update_data(owner_id=owner_id)

    async def process_message(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        data = await state.get_data()
        owner_id = data['owner_id']
        cat = self.storage.cats[owner_id]
        
        # Отправляем сообщение всем пользователям, кроме отправителя
        recipients = [owner_id] + cat.connected_users
        recipients.remove(user_id)
        
        # Определяем имя отправителя
        sender_name = "Маша" if user_id == owner_id else "Стас"
        message_text = "отправила" if user_id == owner_id else "отправил"
        
        for recipient in recipients:
            if message.photo:
                # Если есть фото, отправляем его с подписью
                photo = message.photo[-1]  # Берем последнее (самое качественное) фото
                caption = f"💌 {sender_name} {message_text} фото:"
                if message.caption:
                    caption += f"\n{message.caption}"
                await self.bot.send_photo(
                    recipient,
                    photo.file_id,
                    caption=caption
                )
            else:
                # Если только текст, отправляем как обычно
                await self.bot.send_message(
                    recipient,
                    f"💌 {sender_name} {message_text} сообщение:\n{message.text}"
                )
        
        # Сохраняем время отправки сообщения с учетом часового пояса
        cat.last_messages[user_id] = datetime.now(timezone(self.config.timezone))
        self.storage.save()
        
        await message.answer("Сообщение отправлено! ✉️")
        await state.clear()

    async def process_message_cancel(self, callback: CallbackQuery, state: FSMContext):
        """Обработка отмены отправки сообщения"""
        await state.clear()
        await callback.message.edit_text("Отправка сообщения отменена ❌")
        await callback.answer()

if __name__ == '__main__':
    bot = CatBot()
    asyncio.run(bot.start()) 
    