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
    get_walk_control_keyboard
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
        
        # Текстовые сообщения
        self.dp.message.register(self.process_name, CatStates.waiting_for_name)
        self.dp.message.register(self.process_connection_code, CatStates.waiting_for_code)
        self.dp.message.register(self.process_walk_time, CatStates.waiting_for_walk_time)
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

    async def cmd_start(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Проверяем, есть ли уже котик у пользователя
        if user_id in self.storage.cats:
            await self.send_cat_status(user_id, "Вот ваш котик!")
            await message.answer(
                "Используйте кнопки под фото для взаимодействия с котиком\n"
                "или кнопку на клавиатуре для установки времени прогулки:",
                reply_markup=get_main_keyboard()
            )
            return
            
        await message.answer("Давайте создадим вашего котика! Как вы хотите его назвать?")
        await state.set_state(CatStates.waiting_for_name)

    async def process_name(self, message: Message, state: FSMContext):
        await state.update_data(name=message.text)
        await message.answer(
            "Отличное имя! Теперь выберите цвет котика:",
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
            f"Поздравляем! Вы создали котика {data['name']}!\n\n"
            f"Ваш код для подключения других пользователей: {code}\n"
            f"Код действителен в течение {self.config.connection_code_ttl} часов.\n"
            "Другие пользователи могут подключиться к вашему котику через команду /connect"
        )
        await callback.message.answer(
            "Исполь��уйте кнопки под фото для взаимодействия с котиком\n"
            "или кнопку на клавиатуре для установки времени прогулки:",
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
            await callback.answer("У вас нет котика!")
            return
            
        cat = self.storage.cats[owner_id]
        action = callback.data.split('_')[1]
        message_text = None
        is_connected_user = user_id != owner_id
        
        match action:
            case "feed":
                if cat.hunger >= 4:
                    await callback.answer("Котик не голоден!")
                    return
                cat.hunger = min(4, cat.hunger + 1)
                message_text = "Вы покормили котика!"
                if is_connected_user:
                    await self.bot.send_message(owner_id, "Стас покормил котика")
                
            case "play":
                if cat.energy <= 0:
                    await callback.answer("Котик слишком устал для игр!")
                    return
                cat.happiness = min(4, cat.happiness + 1)
                cat.energy = max(0, cat.energy - 1)
                message_text = "Вы поиграли с котиком!"
                if is_connected_user:
                    await self.bot.send_message(owner_id, "Стас поиграл с котиком")
                
            case "sleep":
                if cat.energy >= 4:
                    await callback.answer("Котик не хочет спать!")
                    return
                cat.energy = min(4, cat.energy + 2)
                message_text = "Котик поспал и восстановил энергию!"
                if is_connected_user:
                    await self.bot.send_message(owner_id, "Стас уложил котика спать")
                
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
            await callback.answer("У вас нет котика!")
            return
            
        cat = self.storage.cats[owner_id]
        
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
                await callback.message.delete()
                await callback.answer("Время прогулки удалено")
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
            await message.answer(
                "У вас нет котика! Используйте /start чтобы создать его."
            )
            return
            
        cat = self.storage.cats[owner_id]
        
        match message.text:
            case "Прогулка":
                current_time = cat.walk_time.strftime("%H:%M") if cat.walk_time else "не установлено"
                await message.answer(
                    f"Текущее время прогулки: {current_time}\n"
                    "Введите новое время прогулки в формате ЧЧ:ММ (например, 14:30)\n"
                    "или используйте кнопки ниже:",
                    reply_markup=get_walk_control_keyboard(has_walk_time=cat.walk_time is not None)
                )
                await state.set_state(CatStates.waiting_for_walk_time)
                
            case "Управление котиком":
                await self.send_cat_status(user_id, owner_id=owner_id)

    async def process_walk_time(self, message: Message):
        try:
            # Парсим время из сообщения
            hour, minute = map(int, message.text.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            
            # Сохраняем время как строку в формате HH:MM
            walk_time = f"{hour:02d}:{minute:02d}"
            
            user_id = message.from_user.id
            if user_id in self.storage.cats:
                cat = self.storage.cats[user_id]
                cat.walk_time = walk_time
                self.storage.save()
                
                await message.answer(
                    f"Время прогулки установлено на {walk_time}! "
                    "Я напомню за 30 минут до прогулки 🐱"
                )
            else:
                await message.answer("У вас нет котика!")
                
        except ValueError:
            await message.answer(
                "Пожалуйста, введите время в формате ЧЧ:ММ\n"
                "Например: 14:30"
            )

    async def send_walk_notification(self, user_id: int, text: str):
        await self.bot.send_message(user_id, text)

    async def cmd_connect(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Проверяем, есть ли уже котик у пользователя
        if user_id in self.storage.cats:
            await message.answer(
                "У вас уже есть котик! Вы не можете подключиться к другому."
            )
            return
            
        await message.answer("Введите код подключения:")
        await state.set_state(CatStates.waiting_for_code)

    async def process_connection_code(self, message: Message, state: FSMContext):
        code = message.text.upper()
        user_id = message.from_user.id
        
        if code not in self.storage.connection_codes:
            await message.answer("Неверный код подключения!")
            await state.clear()
            return
            
        owner_id, expires = self.storage.connection_codes[code]
        
        if datetime.now() > expires:
            await message.answer("Код подключения исте��!")
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
                "Стас подключился к котику"
            )
            
        # Отправляем статус котика от имени владельца
        await self.send_cat_status(
            user_id,
            f"Вы успешно подключились к котику {cat.name}!",
            owner_id
        )
        await message.answer(
            "Используйте кнопки под фото для взаимодействия с котиком\n"
            "или кнопку на клавиатуре для установки времени прогулки:",
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
                    message = f"До прогулки осталось {minutes_left} минут! {cat.name.capitalize()} ждёт 🐱"
                else:
                    message = f"Пора гулять! {cat.name.capitalize()} с нетерпением ждёт прогулки ��"
                    cat.walk_time = None
                    self.storage.save()
                
                await self.bot.send_message(cat.owner_id, message)
                for user_id in cat.connected_users:
                    await self.bot.send_message(user_id, message)

if __name__ == '__main__':
    bot = CatBot()
    asyncio.run(bot.start()) 