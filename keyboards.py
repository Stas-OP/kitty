from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Клавиатура выбора цвета котика
def get_color_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    colors = ['серый', 'белый', 'рыжий', 'чёрный']
    for color in colors:
        builder.button(text=color, callback_data=f'color_{color}')
    builder.adjust(2)
    return builder.as_markup()

# Основная клавиатура действий
def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text='Управление котиком'),
                KeyboardButton(text='Прогулка')
            ],
            [
                KeyboardButton(text='Отправить сообщение')
            ]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура действий с котиком (инлайн)
def get_cat_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    actions = [
        ('Покормить', 'action_feed'),
        ('Поиграть', 'action_play'),
        ('Уложить спать', 'action_sleep'),
        ('Статус', 'action_status')
    ]
    for text, callback_data in actions:
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(2)
    return builder.as_markup()

# Клавиатура подтверждения
def get_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Да', callback_data='confirm_yes')
    builder.button(text='Нет', callback_data='confirm_no')
    builder.adjust(2)
    return builder.as_markup()

# Клавиатура управления временем прогулки
def get_walk_control_keyboard(has_walk_time: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Отменить установку', callback_data='walk_cancel_setup')
    if has_walk_time:
        builder.button(text='Удалить время прогулки', callback_data='walk_delete_time')
    builder.adjust(1)
    return builder.as_markup() 