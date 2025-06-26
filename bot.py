import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import numpy as np
import textwrap
import random
import requests
from io import BytesIO

# Конфигурация
API_TOKEN = 'ВАШ_TELEGRAM_TOKEN'
ADMIN_ID = 123456789  # Ваш ID для статистики

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# База пользователей (временная)
users_db = {}
styles_db = {
    1: {"name": "Советская открытка", "desc": "Яркие цвета, соцреализм", "price": 0},
    2: {"name": "Винтажная фотография", "desc": "Ч/Б с эффектом старения", "price": 0},
    3: {"name": "Киноафиша 60-х", "desc": "Графика в стиле ретро-постеров", "price": 0},
    4: {"name": "Дореволюционная Россия", "desc": "Сепя, картонка, виньетки", "price": 1},
    5: {"name": "Цветная пленка 80-х", "desc": "Выцветшие цвета, зерно", "price": 1}
}

class UserState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_style = State()
    waiting_for_text = State()

def apply_soviet_style(image):
    """Стиль советской открытки"""
    # Усиление цветов
    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(1.8)
    
    # Добавление текстуры бумаги
    texture = Image.open('textures/paper.jpg').convert("RGBA").resize(image.size)
    image = Image.blend(image.convert("RGBA"), texture, 0.2)
    
    # Эффект легкой размытости
    image = image.filter(ImageFilter.GaussianBlur(0.8))
    
    # Добавление градиентного виньетирования
    vignette = Image.open('effects/vignette.png').convert("RGBA").resize(image.size)
    image = Image.alpha_composite(image.convert("RGBA"), vignette)
    
    return image

def apply_vintage_style(image):
    """Ч/Б винтажный стиль"""
    # Конвертация в ч/б с тонированием
    image = image.convert("L")
    image = ImageOps.colorize(image, '#3a1f00', '#e0c78c')
    
    # Добавление царапин
    scratches = Image.open('effects/scratches.png').convert("RGBA").resize(image.size)
    image = image.convert("RGBA")
    image.alpha_composite(scratches)
    
    # Эффект зерна
    grain = np.random.normal(0, 25, (image.size[1], image.size[0], 3))
    grain_img = Image.fromarray(np.uint8(grain)).convert("RGBA")
    image = Image.blend(image, grain_img, 0.1)
    
    return image

def apply_cinema_style(image, text=""):
    """Стиль киноафиши 60-х"""
    # Яркие контрастные цвета
    image = image.convert("RGB")
    r, g, b = image.split()
    r = r.point(lambda x: min(x + 50, 255))
    b = b.point(lambda x: max(x - 30, 0))
    image = Image.merge("RGB", (r, g, b))
    
    # Добавление текста в стиле ретро
    if text:
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("fonts/retro.ttf", 80)
        
        # Разбивка текста на строки
        wrapped_text = textwrap.wrap(text, width=15)
        y_position = 50
        
        for line in wrapped_text:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (image.width - text_width) // 2
            draw.text((x, y_position), line, font=font, fill="yellow", stroke_width=3, stroke_fill="black")
            y_position += 90
    
    # Добавление рамки
    border = Image.open('effects/cinema_border.png').convert("RGBA").resize(image.size)
    image = image.convert("RGBA")
    image.alpha_composite(border)
    
    return image

# Остальные стили аналогично...

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    users_db[user_id] = {"credits": 5, "processed": 0}
    
    text = (
        "📸 *Добро пожаловать в NostalgiaBot!*\n\n"
        "Я превращаю ваши фото в ретро-шедевры:\n"
        "• Советские открытки\n"
        "• Винтажные фотографии\n"
        "• Ретро-постеры\n\n"
        "🔮 _Просто отправьте мне фото и выберите стиль_"
    )
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🎨 Выбрать стиль", callback_data="choose_style"))
    keyboard.add(InlineKeyboardButton("🎁 Бесплатные кредиты", callback_data="free_credits"))
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == 'choose_style')
async def process_choose_style(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(row_width=2)
    for style_id, style in styles_db.items():
        btn_text = f"{style['name']} {'🔓' if style['price'] == 0 else '🔒'}"
        keyboard.insert(InlineKeyboardButton(btn_text, callback_data=f"style_{style_id}"))
    
    await bot.send_message(
        callback_query.from_user.id,
        "🎨 Выберите стиль преобразования:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith('style_'))
async def process_style_selection(callback_query: types.CallbackQuery, state: FSMContext):
    style_id = int(callback_query.data.split('_')[1])
    style = styles_db[style_id]
    user_id = callback_query.from_user.id
    
    # Проверка кредитов
    if style['price'] > 0 and (user_id not in users_db or users_db[user_id]['credits'] < style['price']):
        await bot.answer_callback_query(
            callback_query.id,
            "❌ Недостаточно кредитов!",
            show_alert=True
        )
        return
    
    async with state.proxy() as data:
        data['style_id'] = style_id
    
    # Для стилей с тектом запрашиваем дополнительный ввод
    if style_id == 3:  # Киноафиша
        await bot.send_message(
            callback_query.from_user.id,
            "🎬 Введите текст для афиши (макс. 40 символов):"
        )
        await UserState.waiting_for_text.set()
    else:
        await bot.send_message(
            callback_query.from_user.id,
            f"🖼 Отправьте фото для стиля: *{style['name']}*\n\n{style['desc']}",
            parse_mode="Markdown"
        )
        await UserState.waiting_for_photo.set()

@dp.message_handler(state=UserState.waiting_for_text)
async def process_text_input(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['text'] = message.text[:40]
    
    await message.answer(
        f"📝 Текст сохранен: *{message.text[:40]}*\nТеперь отправьте фото",
        parse_mode="Markdown"
    )
    await UserState.waiting_for_photo.set()

@dp.message_handler(content_types=types.ContentType.PHOTO, state=UserState.waiting_for_photo)
async def process_photo(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with state.proxy() as data:
        style_id = data.get('style_id', 1)
        text = data.get('text', "")
    
    style = styles_db[style_id]
    
    # Скачивание фото
    photo = message.photo[-1]
    file_id = photo.file_id
    file = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file.file_path}"
    
    response = requests.get(file_url)
    image = Image.open(BytesIO(response.content))
    
    # Применение стиля
    await message.answer("🪄 Обрабатываю изображение...")
    
    try:
        if style_id == 1:
            result = apply_soviet_style(image)
        elif style_id == 2:
            result = apply_vintage_style(image)
        elif style_id == 3:
            result = apply_cinema_style(image, text)
        # Остальные стили...
        
        # Сохранение результата
        output = BytesIO()
        result.save(output, format='PNG')
        output.seek(0)
        
        # Отправка результата
        await message.answer_photo(
            output,
            caption=f"✨ Ваше фото в стиле: *{style['name']}*",
            parse_mode="Markdown"
        )
        
        # Обновление статистики
        if user_id in users_db:
            users_db[user_id]['processed'] += 1
            if style['price'] > 0:
                users_db[user_id]['credits'] -= style['price']
        
        # Предложить поделиться
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("📱 Поделиться в Instagram", url="https://instagram.com"))
        keyboard.add(InlineKeyboardButton("🔄 Создать еще", callback_data="choose_style"))
        
        await message.answer(
            "❤️ Понравился результат? Поделитесь с друзьями!",
            reply_markup=keyboard
        )
    
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        await message.answer("⚠️ Произошла ошибка при обработке. Попробуйте другое фото.")
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'free_credits')
async def process_free_credits(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Проверка, получал ли уже сегодня
    if users_db.get(user_id, {}).get('last_bonus') == str(datetime.date.today()):
        await bot.answer_callback_query(
            callback_query.id,
            "❌ Вы уже получали бонус сегодня!",
            show_alert=True
        )
        return
    
    # Выдача кредитов
    if user_id not in users_db:
        users_db[user_id] = {"credits": 10, "processed": 0, "last_bonus": str(datetime.date.today())}
    else:
        users_db[user_id]['credits'] += 5
        users_db[user_id]['last_bonus'] = str(datetime.date.today())
    
    await bot.send_message(
        user_id,
        f"🎁 Получено +5 кредитов!\n\nВаш баланс: *{users_db[user_id]['credits']}* 🪙",
        parse_mode="Markdown"
    )

# Статистика для админа
@dp.message_handler(commands=['stats'])
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    total_users = len(users_db)
    total_processed = sum([u['processed'] for u in users_db.values()])
    
    text = (
        "📊 *Статистика бота*\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"🖼 Обработано фото: {total_processed}\n"
        f"🪙 Выдано кредитов: {sum([u.get('credits', 0) for u in users_db.values()])}"
    )
    
    await message.answer(text, parse_mode="Markdown")

if __name__ == '__main__':
    # Создание необходимых директорий
    os.makedirs('textures', exist_ok=True)
    os.makedirs('effects', exist_ok=True)
    os.makedirs('fonts', exist_ok=True)
    
    # Загрузка текстур (в реальном проекте нужно загрузить файлы)
    if not os.path.exists('textures/paper.jpg'):
        open('textures/paper.jpg', 'wb').write(requests.get('https://example.com/paper.jpg').content)
    
    executor.start_polling(dp, skip_updates=True)
