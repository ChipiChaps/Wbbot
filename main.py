import asyncio
import os
import sqlite3
import uuid

import aiogram
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, Contact, \
    CallbackQuery
from aiogram.utils import executor

import config
import logging
import Admin

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Подключение к базе данных
conn = sqlite3.connect('wbbot.db', check_same_thread=False)
cursor = conn.cursor()
if 'mess_data' not in globals():
    mess_data = {}
user_menu_message_ids = {}
user_sessions = {}  # Словарь для хранения текущей страницы для каждого пользователя
# Словарь для хранения идентификаторов сообщений с карточками товаров
product_messages = {}
# Где-то в начале кода, определите пустой словарь для хранения отфильтрованных списков товаров
filtered_product_lists = {}

class AddUser(StatesGroup):
    waiting_user_name=State()
    waiting_phone_permission=State()

# Создаем класс состояний для добавления товара
class AddProductState(StatesGroup):
    waiting_name = State()
    waiting_description = State()
    waiting_price = State()
    waiting_quantity = State()
    waiting_photo = State()

@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message):

    user_id = message.from_user.id
    AdminStatus = Admin.is_Admin(user_id)
    # Проверяем, является ли пользователь наставником
    if AdminStatus:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        Order = types.KeyboardButton('Актуальные заказы')
        AddProduct = types.KeyboardButton('Добавить товар')
        DelProduct = types.KeyboardButton('Удалить товар')
        keyboard.add(Order)
        keyboard.add(AddProduct,DelProduct)
        welcome_message = "Добро пожаловать, Админ! Выберите действие:"
        await  bot.send_message(message.chat.id, welcome_message, reply_markup=keyboard)


    if AdminStatus == 0 :
        chat_id = message.chat.id
        # Проверяем наличие пользователя в базе данных
        cursor.execute("SELECT * FROM Users WHERE ChatID=?", (chat_id,))
        user_data = cursor.fetchone()

        if not user_data:
            # Если пользователя нет в базе или у него нет имени, просим представиться
            await bot.send_message(message.chat.id, "Добрый день! Вижу, что вы у нас впервые. Как я могу вас называть?")
            # Ожидаем ввода имени
            await AddUser.waiting_user_name.set()

        else:
            # Если у пользователя уже есть имя, используем его
            user_name = user_data[5]
            welcome_message = f"Здравствуйте, {user_name}! Выберите действие:"
            # Создаем клавиатуру
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            Catalog = KeyboardButton("Каталог")
            My_orders = KeyboardButton("Мои заказы")
            Cart = KeyboardButton("Корзина")
            Support = KeyboardButton("Поддержка")

            # Добавляем кнопки на клавиатуру
            keyboard.add(Catalog, My_orders, Cart,Support)

            await bot.send_message(message.chat.id, welcome_message, reply_markup=keyboard)

        # Отправляем сообщение с клавиатурой


@dp.message_handler(state=AddUser.waiting_user_name)
async def add_users_name(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    username = message.from_user.username
    user_name = message.text

    cursor.execute("INSERT INTO Users (Name, ChatID, RealName) VALUES (?, ?, ?)",
                   (username, chat_id, user_name))
    conn.commit()

    # Спрашиваем у пользователя, разрешает ли он добавить телефон
    keyboard = InlineKeyboardMarkup()
    allow_button = InlineKeyboardButton("Да", callback_data="allow_phone")
    deny_button = InlineKeyboardButton("Нет", callback_data="deny_phone")
    keyboard.add(allow_button, deny_button)

    sent_message = await bot.send_message(chat_id, f"{user_name}! Вы разрешаете добавить ваш телефон?", reply_markup=keyboard)
    # Сохраняем message_id в состоянии FSM
    await state.update_data(message_id=sent_message.message_id)

    # Устанавливаем состояние FSM для ожидания ответа пользователя
    await AddUser.waiting_phone_permission.set()


@dp.callback_query_handler(lambda query: query.data in ["allow_phone", "deny_phone"],
                           state=AddUser.waiting_phone_permission)
async def handle_phone_permission(query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(query.id)

    # Получаем данные пользователя и состояние FSM
    user_id = query.from_user.id
    user_data = await state.get_data()
    message_id = user_data.get("message_id")

    if query.data == "allow_phone":
        # Если пользователь разрешил, отправляем новое сообщение и удаляем старое
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        reg_button = KeyboardButton(text="Отправить номер телефона", request_contact=True)
        keyboard.add(reg_button)

        new_message = await bot.send_message(user_id, "Отправьте ваш номер телефона, нажав на кнопку ниже", reply_markup=keyboard)

        # Удаляем старое сообщение
        await bot.delete_message(chat_id=user_id, message_id=message_id)

        # Сохраняем новый message_id в состоянии FSM
        await state.update_data(message_id=new_message.message_id)

        # Устанавливаем состояние FSM для ожидания номера телефона
        await AddUser.waiting_phone_permission.set()

    elif query.data == "deny_phone":
        # Если пользователь отказал, добавляем пустое значение в базу данных
        cursor.execute("UPDATE Users SET TelNumber = ? WHERE ChatID = ?", ("Телефона нет", user_id))
        conn.commit()
        cursor.execute("SELECT * FROM Users WHERE ChatID=?", (user_id,))
        user_data = cursor.fetchone()
        new_message = await bot.send_message(user_id, "Телефон не добавлен.")

        # Удаляем старое сообщение
        await bot.delete_message(chat_id=user_id, message_id=message_id)

        # Сохраняем новый message_id в состоянии FSM
        await state.update_data(message_id=new_message.message_id)
        user_name = user_data[5]
        welcome_message = f"Здравствуйте, {user_name}! Выберите действие:"
        # Создаем клавиатуру
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        Catalog = KeyboardButton("Каталог")
        My_orders = KeyboardButton("Мои заказы")
        Cart = KeyboardButton("Корзина")
        Support = KeyboardButton("Поддержка")

        # Добавляем кнопки на клавиатуру
        keyboard.add(Catalog, My_orders, Cart, Support)


        await bot.send_message(query.message.chat.id, welcome_message, reply_markup=keyboard)

        # Сбрасываем состояние FSM
        await state.finish()

@dp.message_handler(content_types=types.ContentType.CONTACT, state=AddUser.waiting_phone_permission)
async def handle_contact(message: types.Message, state: FSMContext):
    contact: Contact = message.contact
    user_id = message.from_user.id
    cursor.execute("SELECT * FROM Users WHERE ChatID=?", (user_id,))
    user_data = cursor.fetchone()

    # Обновляем базу данных с номером телефона
    cursor.execute("UPDATE Users SET TelNumber = ? WHERE ChatID = ?", (contact.phone_number, user_id))
    conn.commit()

    await bot.send_message(user_id, "Телефон успешно добавлен.")
    user_name = user_data[5]
    welcome_message = f"Здравствуйте, {user_name}! Выберите действие:"
    # Создаем клавиатуру
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    Catalog = KeyboardButton("Каталог")
    My_orders = KeyboardButton("Мои заказы")
    Cart = KeyboardButton("Корзина")
    Support = KeyboardButton("Поддержка")

    # Добавляем кнопки на клавиатуру
    keyboard.add(Catalog, My_orders, Cart, Support)

    await bot.send_message(message.chat.id, welcome_message, reply_markup=keyboard)


    # Сбрасываем состояние FSM
    await state.finish()


@dp.message_handler(lambda message: message.text == 'Я администратор')
async def handle_admin_activation(message: types.Message, state: FSMContext):
    cursor.execute("SELECT COUNT(*) FROM Admin")
    admin_count = cursor.fetchone()[0]
    if admin_count > 0:
        # Если администратор уже существует
        await message.answer("Извините, в данном боте уже имеется администратор.")
    else:
        # Если администратора нет, предложим добавить
        keyboard = InlineKeyboardMarkup()
        yes_button = InlineKeyboardButton("Да", callback_data="add_admin")
        no_button = InlineKeyboardButton("Нет", callback_data="deny_admin")
        keyboard.add(yes_button, no_button)

        # Отправляем сообщение с клавиатурой
        sent_message = await message.answer("Добавить вас в данную базу в роли администратора?", reply_markup=keyboard)

        # Сохраняем идентификатор отправленного сообщения в состоянии
        await state.update_data(sent_message_id=sent_message.message_id)

@dp.callback_query_handler(lambda query: query.data in {"add_admin", "deny_admin"})
async def handle_admin_callback(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sent_message_id = data.get("sent_message_id")
    adminadd_chat_id = call.from_user.id  # Сохраняем chat_id админа
    mess_data['adminadd_chat_id'] = adminadd_chat_id
    print(adminadd_chat_id)

    if call.data == "add_admin":
        # Получаем реальное имя пользователя из таблицы Users
        conn = sqlite3.connect('wbbot.db')
        cursor = conn.cursor()

        cursor.execute("SELECT RealName FROM Users WHERE ChatID = ?", (str(adminadd_chat_id),))
        result = cursor.fetchone()

        if result:
            real_name = result[0]

            # Добавляем пользователя в таблицу Admin
            cursor.execute("INSERT INTO Admin (Name, ChatID, RealName) VALUES (?, ?, ?)",
                           (call.from_user.username, str(adminadd_chat_id), real_name))

            # Обновляем роль пользователя в таблице Users
            cursor.execute("DELETE FROM Users WHERE ChatID = ?", (str(adminadd_chat_id),))

            # Сохраняем изменения
            conn.commit()

            # Закрываем соединение
            conn.close()

            keyboard = InlineKeyboardMarkup()
            reebood_btn = InlineKeyboardButton("Перезапустить", callback_data="reboot_btn")
            keyboard.add(reebood_btn)

            # Редактируем отправленное сообщение
            await bot.edit_message_text("Вы успешно добавлены в роли администратора. Перезапустите бота для дальнейшей работы.", call.message.chat.id, sent_message_id, reply_markup=keyboard)
        else:
            await call.answer("Ошибка: не удалось найти пользователя в таблице Users.")
    elif call.data == "deny_admin":
        # Редактируем отправленное сообщение
        await bot.edit_message_text("Вы отказались от роли администратора.", call.message.chat.id, sent_message_id)

    # Удаляем данные из состояния
    await state.finish()

@dp.callback_query_handler(lambda query: query.data == "reboot_btn")
async def handle_reboot_button(call: types.CallbackQuery):
    admin_id = mess_data['adminadd_chat_id']

    # Удаление предыдущего сообщения
    await bot.delete_message(admin_id, call.message.message_id)

    # Отправка нового сообщения с обычной клавиатурой
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Order = types.KeyboardButton('Актуальные заказы')
    AddProduct = types.KeyboardButton('Добавить товар')
    DelProduct = types.KeyboardButton('Удалить товар')
    keyboard.add(Order)
    keyboard.add(AddProduct, DelProduct)
    welcome_message = "Добро пожаловать, Админ! Выберите действие:"
    await bot.send_message(admin_id, welcome_message, reply_markup=keyboard)

#######################################Кнопка поддержка

@dp.message_handler(lambda message: message.text == 'Поддержка')
async def process_support_button(message: types.Message):
    # Получаем ChatID администратора из таблицы Admin
    await delete_previous_messages(message.chat.id)
    cursor.execute("SELECT Name FROM Admin")
    admin_chat_id = cursor.fetchone()

    if admin_chat_id:
        # Формируем текст сообщения с ссылкой на чат в Telegram
        support_link = f"https://t.me/{admin_chat_id[0]}"
        await bot.send_message(message.chat.id, f"По вопросам связанными с заказами: \n{support_link}")
    else:
        # Если ChatID администратора не найден, отправляем сообщение об ошибке
        await bot.send_message(message.chat.id, "Информация о администраторе не найдена.")



#######################################Кнопка Удалить товар
class DeleteProductState(StatesGroup):
    waiting_product = State()

@dp.message_handler(lambda message: message.text == 'Удалить товар')
async def process_delete_product_button(message: types.Message):
    # Получаем список товаров из базы данных
    cursor.execute("SELECT ID, Name, Photo FROM Product")
    products = cursor.fetchall()

    # Если список товаров пуст, отправляем сообщение об этом
    if not products:
        await message.answer("В каталоге нет доступных товаров для удаления.")
        return

    # Формируем клавиатуру с доступными товарами для выбора
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for product in products:
        keyboard.add(types.KeyboardButton(product[1]))

    # Отправляем сообщение с просьбой выбрать товар для удаления
    await message.answer("Выберите товар, который нужно удалить из каталога:", reply_markup=keyboard)

    # Устанавливаем состояние ожидания выбора товара для удаления
    await DeleteProductState.waiting_product.set()

# Обработчик для удаления выбранного товара из каталога
@dp.message_handler(state=DeleteProductState.waiting_product)
async def process_selected_product_for_deletion(message: types.Message, state: FSMContext):
    # Получаем название выбранного товара
    selected_product_name = message.text

    # Пытаемся найти выбранный товар в базе данных
    cursor.execute("SELECT ID, Photo FROM Product WHERE Name=?", (selected_product_name,))
    product = cursor.fetchone()

    if product is None:
        await message.answer("Выбранный товар не найден. Пожалуйста, выберите товар из списка.")
        return

    # Удаляем фотографию товара из папки
    photo_file_path = product[1]
    if os.path.exists(photo_file_path):
        os.remove(photo_file_path)

    # Удаляем товар из таблицы Product
    product_id = product[0]
    cursor.execute("DELETE FROM Product WHERE ID=?", (product_id,))
    conn.commit()

    # Удаляем товар из корзин всех пользователей
    cursor.execute("DELETE FROM Cart WHERE ProductID=?", (product_id,))
    conn.commit()
    # Создаем клавиатуру с кнопками "Актуальные заказы" и "Добавить товар"
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    Order = types.KeyboardButton('Актуальные заказы')
    AddProduct = types.KeyboardButton('Добавить товар')
    DelProduct = types.KeyboardButton('Удалить товар')
    keyboard.add(Order)
    keyboard.add(AddProduct, DelProduct)

    # Отправляем новое сообщение с клавиатурой
    welcome_message = f"Товар '{selected_product_name}' успешно удален из каталога и из корзин всех пользователей."
    await message.answer(welcome_message, reply_markup=keyboard)

    # Возвращаемся к обычной клавиатуре
    await state.finish()


#######################################Кнопка Добавить товар
# Функция для обработки нажатия кнопки "Назад"
@dp.message_handler(lambda message: message.text == 'Назад', state='*')
async def process_cancel_button(message: types.Message, state: FSMContext):
    # Сбрасываем состояние
    await state.reset_state()

    # Создаем клавиатуру с кнопками "Актуальные заказы" и "Добавить товар"
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    Order = types.KeyboardButton('Актуальные заказы')
    AddProduct = types.KeyboardButton('Добавить товар')
    DelProduct = types.KeyboardButton('Удалить товар')
    keyboard.add(Order)
    keyboard.add(AddProduct, DelProduct)

    # Отправляем новое сообщение с клавиатурой
    welcome_message = "Вы отменили процесс добавления товара."
    await message.answer(welcome_message, reply_markup=keyboard)


@dp.message_handler(lambda message: message.text == 'Добавить товар')
async def process_add_product_button(message: types.Message):
    # Создаем клавиатуру с кнопкой "Назад"
    cancel_button = KeyboardButton("Назад")
    keyboard = ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    keyboard.add(cancel_button)

    # Отправляем приветственное сообщение и запускаем процесс добавления товара
    await message.answer("Давайте начнем добавление нового товара. Пожалуйста, введите название товара.",
                         reply_markup=keyboard)

    # Устанавливаем состояние ожидания
    await AddProductState.waiting_name.set()

@dp.message_handler(state=AddProductState.waiting_name)
async def process_product_name(message: types.Message, state: FSMContext):
    # Проверяем, что введено название товара
    if not message.text:
        await message.answer("Название товара не может быть пустым. Пожалуйста, введите название товара.")
        return
    # Сохраняем название товара и переходим к следующему шагу
    await state.update_data(name=message.text)
    await message.answer("Введите описание товара.")
    await AddProductState.next()

@dp.message_handler(state=AddProductState.waiting_description)
async def process_product_description(message: types.Message, state: FSMContext):
    # Проверяем, что введено описание товара
    if not message.text:
        await message.answer("Описание товара не может быть пустым. Пожалуйста, введите описание товара.")
        return
    # Сохраняем описание товара и переходим к следующему шагу
    await state.update_data(description=message.text)
    await message.answer("Введите цену товара.")
    await AddProductState.next()

@dp.message_handler(state=AddProductState.waiting_price)
async def process_product_price(message: types.Message, state: FSMContext):
    # Проверяем, что введена корректная цена товара
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Цена товара должна быть положительным числом. Пожалуйста, введите корректную цену товара.")
        return
    # Сохраняем цену товара и переходим к следующему шагу
    await state.update_data(price=price)
    await message.answer("Введите количество товара.")
    await AddProductState.next()

@dp.message_handler(state=AddProductState.waiting_quantity)
async def process_product_quantity(message: types.Message, state: FSMContext):
    # Проверяем, что введено корректное количество товара
    try:
        quantity = int(message.text)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Количество товара должно быть положительным целым числом. Пожалуйста, введите корректное количество товара.")
        return
    # Сохраняем количество товара и переходим к следующему шагу
    await state.update_data(quantity=quantity)
    await message.answer("Прикрепите фото товара.")
    await AddProductState.next()

@dp.message_handler(content_types=['photo'], state=AddProductState.waiting_photo)
async def process_product_photo(message: types.Message, state: FSMContext):
    # Получаем фото товара и сохраняем его в состоянии FSM
    photo_id = message.photo[-1].file_id

    # Генерируем уникальное имя файла
    photo_file_name = f"{uuid.uuid4()}.jpg"

    # Сохраняем фото на сервере
    photo_path = os.path.join("images", photo_file_name)
    await message.photo[-1].download(photo_path)

    # Получаем все данные о товаре из состояния FSM
    product_data = await state.get_data()

    # Сохраняем путь к фото в базе данных
    cursor.execute("INSERT INTO Product (Name, Description, Price, Quantity, Photo) VALUES (?, ?, ?, ?, ?)",
                   (product_data['name'], product_data['description'], product_data['price'],
                    product_data['quantity'], photo_path))
    conn.commit()

    # Создаем клавиатуру с кнопками "Актуальные заказы" и "Добавить товар"
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    Order = types.KeyboardButton('Актуальные заказы')
    AddProduct = types.KeyboardButton('Добавить товар')
    DelProduct = types.KeyboardButton('Удалить товар')
    keyboard.add(Order)
    keyboard.add(AddProduct, DelProduct)

    # Отправляем новое сообщение с клавиатурой
    welcome_message = f"Товар успешно добавлен!"
    await message.answer(welcome_message, reply_markup=keyboard)

    # Сбрасываем состояние FSM и сообщаем об успешном добавлении товара
    await state.finish()



#######################################Кнопка Каталог
@dp.callback_query_handler(lambda query: query.data.startswith('add_to_cart_'))
async def process_add_to_cart(callback_query: types.CallbackQuery):
    # Получаем ID товара из callback_data
    data_parts = callback_query.data.split('_')

    if len(data_parts) == 4:
        product_id = int(data_parts[3])
    else:
        await bot.answer_callback_query(callback_query.id, text="Произошла ошибка при добавлении товара в корзину.")
        return

    # Получаем количество товара, выбранное клиентом
    selected_quantity = int(callback_query.message.reply_markup.inline_keyboard[0][1].text)

    # Получаем количество товара из таблицы Product
    cursor.execute("SELECT Quantity FROM Product WHERE ID=?", (product_id,))
    product_quantity = cursor.fetchone()[0]

    # Проверяем, есть ли уже этот товар в корзине у пользователя
    cursor.execute("SELECT * FROM Cart WHERE ClientID=? AND ProductID=?", (callback_query.from_user.id, product_id))
    cart_product = cursor.fetchone()

    if cart_product:
        # Если товар уже есть в корзине, обновляем количество
        current_quantity_in_cart = cart_product[3]
        total_quantity = selected_quantity + current_quantity_in_cart

        if total_quantity > product_quantity:
            remaining_quantity = product_quantity - current_quantity_in_cart
            await bot.answer_callback_query(callback_query.id, text=f"Можно добавить еще {remaining_quantity} единиц товара.")
            return

        updated_quantity = cart_product[3] + selected_quantity
        cursor.execute("UPDATE Cart SET Quantity = ? WHERE ClientID=? AND ProductID=?", (updated_quantity, callback_query.from_user.id, product_id))
    else:
        # Если товара нет в корзине, добавляем его с выбранным количеством
        if selected_quantity > product_quantity:
            await bot.answer_callback_query(callback_query.id, text=f"Можно добавить еще {product_quantity} единиц товара.")
            return

        cursor.execute("INSERT INTO Cart (ClientID, ProductID, Quantity) VALUES (?, ?, ?)", (callback_query.from_user.id, product_id, selected_quantity))

    conn.commit()

    # Отправляем сообщение об успешном добавлении товара в корзину
    await bot.answer_callback_query(callback_query.id, text="Товар успешно добавлен в корзину!")





products = []  # Переменная для хранения списка продуктов
items_per_page = 2  # Количество товаров на странице



# Обработчик команды "Каталог"

@dp.message_handler(lambda message: message.text == 'Каталог')
async def process_catalog_button(message: types.Message):
    global product_messages
    # Удаляем предыдущие сообщения с корзиной
    await delete_previous_messages(message.chat.id)

    # Удаляем предыдущее сообщение с кнопками "Следующие" и "Предыдущие", если оно есть
    if message.chat.id in product_messages:
        for msg_id in product_messages[message.chat.id]:
            try:
                await bot.delete_message(message.chat.id, msg_id)
            except aiogram.utils.exceptions.MessageToDeleteNotFound:
                pass
        del product_messages[message.chat.id]

    # Подключение к базе данных
    conn = sqlite3.connect('wbbot.db', check_same_thread=False)
    cursor = conn.cursor()

    # Получаем информацию о всех товарах из таблицы Product
    cursor.execute("SELECT * FROM Product")
    products = cursor.fetchall()

    # Фильтруем товары, оставляя только те, у которых количество больше 0
    filtered_products = [product for product in products if product[4] > 0]

    # Сохраняем отфильтрованный список товаров для текущего чата
    filtered_product_lists[message.chat.id] = filtered_products

    # Получаем текущий номер страницы из сессии пользователя, если нету, устанавливаем 1
    page_number = user_sessions.get(message.chat.id, 1)

    # Выводим только часть товаров, соответствующую текущей странице
    start_index = (page_number - 1) * items_per_page
    end_index = start_index + items_per_page
    current_products = filtered_products[start_index:end_index]

    # Создаем строку с информацией о страницах и количестве товаров
    total_pages = (len(filtered_products) + items_per_page - 1) // items_per_page
    total_items = len(filtered_products)
    items_on_page = min(len(current_products), items_per_page)
    info_string = f"Страница {page_number}/{total_pages}, всего товаров: {total_items},\n товаров на странице: {items_on_page}"

    # Список идентификаторов сообщений с карточками товаров для текущего чата
    product_messages[message.chat.id] = []

    for product in current_products:
        name = product[1]
        description = product[2]
        price = product[3]
        photo_path = product[5]
        product_id = product[0]

        # Создаем клавиатуру с кнопками увеличения и уменьшения количества товара
        markup = InlineKeyboardMarkup(row_width=3)

        # Создаем кнопки для увеличения и уменьшения количества товара
        decrease_button = InlineKeyboardButton(text="-", callback_data=f"decrease_quantity_{product_id}")
        quantity_button = InlineKeyboardButton(text="1", callback_data="none")  # Пока у нас нет возможности выбирать количество
        increase_button = InlineKeyboardButton(text="+", callback_data=f"increase_quantity_{product_id}")

        # Добавляем кнопки в клавиатуру
        markup.add(decrease_button, quantity_button, increase_button)

        # Создаем кнопку для добавления товара в корзину
        add_to_cart_button = InlineKeyboardButton(text="Добавить в корзину", callback_data=f"add_to_cart_{product_id}")

        # Добавляем кнопку добавления товара в корзину в новую строку
        markup.add(add_to_cart_button)

        # Отправляем изображение и информацию о товаре с клавиатурой
        with open(photo_path, 'rb') as photo:
            product_message = await bot.send_photo(message.chat.id, photo, caption=f"Название: {name}\nОписание: {description}\nЦена: {price} руб.", reply_markup=markup)

        # Сохраняем идентификатор сообщения с карточкой товара
        product_messages[message.chat.id].append(product_message.message_id)

    # Закрываем соединение с базой данных
    conn.close()

    # Отправляем сообщение с информацией о страницах и количестве товаров, а также кнопками перелистывания страниц
    navigation_markup = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(text="Предыдущие", callback_data="previous_page"),
        InlineKeyboardButton(text="Следующие", callback_data="next_page")
    )
    navigation_message = await bot.send_message(
        message.chat.id,
        f"Выберите товары:\n{info_string}",
        reply_markup=navigation_markup
    )

    # Сохраняем идентификатор сообщения с кнопками "Предыдущие" и "Следующие"
    product_messages[message.chat.id].append(navigation_message.message_id)


@dp.callback_query_handler(lambda query: query.data in ['previous_page', 'next_page'])
async def handle_navigation_buttons(query: types.CallbackQuery):
    # Получаем текущий номер страницы из сессии пользователя
    page_number = user_sessions.get(query.message.chat.id, 1)
    if query.data == 'previous_page':
        # Уменьшаем номер страницы на 1, если возможно
        page_number = max(1, page_number - 1)
    elif query.data == 'next_page':
        # Увеличиваем номер страницы на 1, если возможно
        page_number += 1

    # Получаем отфильтрованный список товаров для текущего чата
    filtered_products = filtered_product_lists.get(query.message.chat.id, [])

    # Рассчитываем общее количество страниц и общее количество товаров для отображения информации
    total_pages = (len(filtered_products) + items_per_page - 1) // items_per_page
    total_items = len(filtered_products)

    # Убеждаемся, что номер страницы не превышает общее количество страниц
    page_number = min(page_number, total_pages)

    # Обновляем номер страницы в сессии пользователя
    user_sessions[query.message.chat.id] = page_number

    # Удаляем сообщение, в котором была нажата кнопка
    await bot.delete_message(query.message.chat.id, query.message.message_id)

    # Повторно вызываем функцию обработки кнопки "Каталог", чтобы обновить продукты на странице
    await process_catalog_button(query.message)


@dp.callback_query_handler(lambda query: query.data.startswith('increase_quantity_'))
async def increase_quantity_callback(query: types.CallbackQuery):
    product_id = int(query.data.split('_')[-1])

    # Получаем текущее количество товара из текста кнопки
    current_quantity = int(query.message.reply_markup.inline_keyboard[0][1].text)

    # Получаем максимальное количество товара из таблицы Product
    cursor.execute("SELECT Quantity FROM Product WHERE ID=?", (product_id,))
    max_quantity = cursor.fetchone()[0]

    # Проверяем, не превышает ли выбранное количество максимальное
    if current_quantity < max_quantity:
        # Увеличиваем количество товара на 1
        new_quantity = current_quantity + 1

        # Обновляем текст кнопки с новым количеством товара
        await update_quantity_button(query.message, new_quantity)
    else:
        # Выводим сообщение о превышении максимального количества товара
        await bot.answer_callback_query(query.id, text=f"Достигнуто максимальное количество товара: {max_quantity}")


# Обработчик коллбэка кнопки уменьшения количества товара
@dp.callback_query_handler(lambda query: query.data.startswith('decrease_quantity_'))
async def decrease_quantity_callback(query: types.CallbackQuery):
    product_id = int(query.data.split('_')[-1])

    # Получаем текущее количество товара из текста кнопки
    current_quantity = int(query.message.reply_markup.inline_keyboard[0][1].text)

    # Если количество товара равно 1, то блокируем кнопку "-"
    if current_quantity == 1:
        await query.answer()
        return

    # Уменьшаем количество товара на 1
    new_quantity = current_quantity - 1

    # Обновляем текст кнопки с новым количеством товара
    await update_quantity_button(query.message, new_quantity)

# Функция для обновления текста кнопки с количеством товара
async def update_quantity_button(message, new_quantity):
    # Получаем текущую клавиатуру из сообщения
    current_keyboard = message.reply_markup.inline_keyboard

    # Обновляем текст кнопки с количеством товара
    current_keyboard[0][1].text = str(new_quantity)

    # Создаем новую клавиатуру с обновленным текстом кнопки
    new_keyboard = InlineKeyboardMarkup(inline_keyboard=current_keyboard)

    # Обновляем сообщение с новой клавиатурой
    await message.edit_reply_markup(reply_markup=new_keyboard)






@dp.message_handler(lambda message: message.text == 'Корзина')
async def cart_button(message: types.Message):
    global product_messages

    # Удаляем предыдущие сообщения с корзиной
    await delete_previous_messages(message.chat.id)

    # Список для хранения идентификаторов сообщений корзины
    product_messages[message.chat.id] = []

    # Получаем данные о товарах в корзине для текущего пользователя
    cursor.execute("SELECT * FROM Cart WHERE ClientID=?", (message.from_user.id,))
    cart_items = cursor.fetchall()

    if not cart_items:
        await message.answer("Ваша корзина пуста.")
        return

    total_cost = 0

    for cart_item in cart_items:
        product_id = cart_item[2]
        quantity = cart_item[3]

        # Получаем информацию о товаре из таблицы Product
        cursor.execute("SELECT * FROM Product WHERE ID=?", (product_id,))
        product_data = cursor.fetchone()

        name = product_data[1]
        price = product_data[3]

        # Вычисляем стоимость товара в корзине
        item_cost = price * quantity
        total_cost += item_cost

        # Создаем сообщение о товаре
        cart_message = f"{name} (Количество: {quantity}, Цена: {price} руб., Сумма: {item_cost} руб.)\n"
        cart_message += f"Описание: {product_data[2]}\n"

        # Создаем разметку для кнопок управления товаром
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("-", callback_data=f"decrease_quan_{product_id}"),
            types.InlineKeyboardButton(str(quantity), callback_data="none"),
            types.InlineKeyboardButton("+", callback_data=f"increase_quan_{product_id}"),
            types.InlineKeyboardButton("Удалить", callback_data=f"delete_from_cart_{product_id}")
        )

        # Отправляем сообщение с информацией о товаре и кнопками управления
        sent_message = await message.answer(cart_message, reply_markup=markup)
        product_messages[message.chat.id].append(sent_message.message_id)

    # Создаем разметку для кнопки "Оформить заказ"
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("Оформить заказ", callback_data="order"))

    # Отправляем сообщение с общей стоимостью и кнопкой "Оформить заказ"
    total_cost_message = await message.answer(f"Общая стоимость: {total_cost} руб.", reply_markup=markup)

    # Запоминаем идентификатор сообщения с общей стоимостью для обновления
    user_cart_message_ids[message.from_user.id] = total_cost_message.message_id





# Увеличение количества товара в корзине
@dp.callback_query_handler(lambda query: query.data.startswith('increase_quan_'))
async def increase_quan_callback(query: types.CallbackQuery):
    product_id = int(query.data.split('_')[2])
    client_id = query.from_user.id
    message = query.message

    # Получаем текущее количество товара в корзине
    cursor.execute("SELECT Quantity FROM Cart WHERE ClientID=? AND ProductID=?", (client_id, product_id))
    current_quantity = cursor.fetchone()[0]

    # Получаем максимальное количество товара для данного продукта из таблицы Product
    cursor.execute("SELECT Quantity FROM Product WHERE ID=?", (product_id,))
    max_quantity = cursor.fetchone()[0]

    # Проверяем, не превышает ли увеличение количества максимальное значение
    if current_quantity < max_quantity:
        # Обновляем количество товара в базе данных
        cursor.execute("UPDATE Cart SET Quantity = Quantity + 1 WHERE ClientID=? AND ProductID=?", (client_id, product_id))
        conn.commit()
        # Пересчитываем общую стоимость всех товаров в корзине
        total_cost = calculate_total_cost(client_id)

        # Обновляем текст сообщения с корзиной, чтобы отобразить новое количество товара
        await update_cart_message(message, client_id, product_id, total_cost)
    else:
        # Отправляем уведомление клиенту о том, что выбрано максимальное количество товара
        await bot.answer_callback_query(query.id, text=f"Вы уже выбрали максимальное количество этого товара.")




# Уменьшение количества товара в корзине
@dp.callback_query_handler(lambda query: query.data.startswith('decrease_quan_'))
async def decrease_quan_callback(query: types.CallbackQuery):
    product_id = int(query.data.split('_')[2])
    client_id = query.from_user.id
    message = query.message

    # Получаем текущее количество товара в корзине
    cursor.execute("SELECT Quantity FROM Cart WHERE ClientID=? AND ProductID=?", (client_id, product_id))
    current_quantity = cursor.fetchone()[0]

    # Проверяем, не уменьшает ли клиент количество товара уже до минимального значения
    if current_quantity > 1:
        # Обновляем количество товара в базе данных
        cursor.execute("UPDATE Cart SET Quantity = Quantity - 1 WHERE ClientID=? AND ProductID=?", (client_id, product_id))
        conn.commit()
        # Пересчитываем общую стоимость всех товаров в корзине
        total_cost = calculate_total_cost(client_id)
        # Обновляем текст сообщения с корзиной, чтобы отобразить новое количество товара
        await update_cart_message(message, client_id, product_id, total_cost)
    else:
        # Отправляем уведомление клиенту о том, что он уже выбрал минимальное количество товара
        await bot.answer_callback_query(query.id, text=f"Вы уже выбрали минимальное количество этого товара.")






# Удаление товара из корзины
@dp.callback_query_handler(lambda query: query.data.startswith('delete_from_cart_'))
async def delete_from_cart_callback(query: types.CallbackQuery):
    product_id = int(query.data.split('_')[3])
    client_id = query.from_user.id
    message = query.message

    # Удаляем товар из базы данных
    cursor.execute("DELETE FROM Cart WHERE ClientID=? AND ProductID=?", (client_id, product_id))
    conn.commit()

    # Проверяем, остались ли еще товары в корзине у клиента
    cursor.execute("SELECT COUNT(*) FROM Cart WHERE ClientID=?", (client_id,))
    remaining_items_count = cursor.fetchone()[0]

    if remaining_items_count == 0:
        await delete_previous_messages(message.chat.id)
        await message.answer("Ваша корзина пуста.")
    else:
        # Если в корзине остались другие товары, обновляем сообщение с корзиной
        total_cost = calculate_total_cost(client_id)
        await update_cart_message(message, client_id, product_id, total_cost)



def calculate_total_cost(client_id):
    cursor.execute("SELECT Product.Price * Cart.Quantity AS ItemCost FROM Cart JOIN Product ON Cart.ProductID = Product.ID WHERE Cart.ClientID=?", (client_id,))
    total_cost = sum(row[0] for row in cursor.fetchall())
    return total_cost

# Функция для обновления текста сообщения с корзиной
user_cart_message_ids = {}
async def update_cart_message(message, client_id, product_id, total_cost):
    cursor.execute("SELECT * FROM Cart WHERE ClientID=? AND ProductID=?", (client_id, product_id))
    cart_item = cursor.fetchone()

    total_cost_message_id = user_cart_message_ids.get(client_id)
    if total_cost_message_id:
        await dp.bot.edit_message_text(chat_id=message.chat.id, message_id=total_cost_message_id,
                                       text=f"Общая стоимость: {total_cost} руб.")

    if cart_item:
        quantity = cart_item[3]

        cursor.execute("SELECT * FROM Product WHERE ID=?", (product_id,))
        product_data = cursor.fetchone()

        name = product_data[1]
        price = product_data[3]
        item_cost = price * quantity


        # Генерируем callback-данные с идентификатором товара
        increase_callback_data = f"increase_quan_{product_id}"
        decrease_callback_data = f"decrease_quan_{product_id}"
        delete_callback_data = f"delete_from_cart_{product_id}"

        # Создаем кнопки для управления количеством товара и удаления товара
        markup = types.InlineKeyboardMarkup().row(
            types.InlineKeyboardButton("-", callback_data=decrease_callback_data),
            types.InlineKeyboardButton(str(quantity), callback_data="none"),
            types.InlineKeyboardButton("+", callback_data=increase_callback_data),
            types.InlineKeyboardButton("Удалить", callback_data=delete_callback_data)
        )

        # Создаем текст сообщения для товара в корзине
        cart_message = f"{name} (Количество: {quantity}, Цена: {price} руб., Сумма: {item_cost} руб.)\n"
        cart_message += f"Описание: {product_data[2]}\n"

        # Редактируем сообщение с корзиной
        await message.edit_text(cart_message, reply_markup=markup)

    else:
        # Если товар не найден, удаляем сообщение
        await message.delete()


####################################################################################Оформление заказа

# Определение состояний
class OrderStates(StatesGroup):
    WAITING_FOR_ADDRESS = State()

@dp.callback_query_handler(lambda query: query.data == 'order')
async def process_order(callback_query: types.CallbackQuery):
    # Удаляем предыдущие сообщения с корзиной
    await delete_previous_messages(callback_query.message.chat.id)



    # Отправляем сообщение с вопросом о подтверждении заказа и кнопками "Оформить" и "Отмена"
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Оформить", callback_data="confirm_order"),
        types.InlineKeyboardButton("Отмена", callback_data="cancel_order")
    )
    confirm_message = await callback_query.message.answer("Хотите оформить заказ?", reply_markup=markup)

    # Запоминаем message_id сообщения с вопросом о подтверждении заказа
    state = dp.current_state(chat=callback_query.message.chat.id, user=callback_query.from_user.id)
    await state.update_data(confirm_message_id=confirm_message.message_id)


@dp.callback_query_handler(lambda query: query.data == 'confirm_order', state=None)
async def confirm_order(callback_query: types.CallbackQuery, state: FSMContext):
    # Получаем ID чата пользователя
    client_id = callback_query.from_user.id

    # Получаем товары из корзины данного пользователя
    cursor.execute("SELECT ProductID, Quantity FROM Cart WHERE ClientID=?", (client_id,))
    cart_items = cursor.fetchall()

    # Переменная, которая будет определять, нужно ли переходить в режим ожидания
    need_waiting_state = True

    # Проверяем наличие товаров на складе
    for product_id, quantity_in_cart in cart_items:
        cursor.execute("SELECT Quantity FROM Product WHERE ID=?", (product_id,))
        available_quantity = cursor.fetchone()[0]

        # Если товаров недостаточно, отправляем сообщение об ошибке и удаляем товар из корзины
        if available_quantity < quantity_in_cart:
            cursor.execute("DELETE FROM Cart WHERE ClientID=? AND ProductID=?", (client_id, product_id))
            conn.commit()
            product_name = cursor.execute("SELECT Name FROM Product WHERE ID=?", (product_id,)).fetchone()[0]
            await callback_query.message.answer(f"К сожалению, количество товара '{product_name}' в вашей корзине превышает запасы на складе. Товар был удален из корзины. Необходимо будет переоформить заказ.")
            need_waiting_state = False

    # Удаляем предыдущее сообщение
    await delete_previous_messages(client_id)

    # Удаляем сообщение с вопросом о подтверждении заказа
    state_data = await state.get_data()
    confirm_message_id = state_data.get('confirm_message_id')
    if confirm_message_id:
        await bot.delete_message(client_id, confirm_message_id)

    # Если не нужно переходить в режим ожидания, просто выводим уведомление
    if not need_waiting_state:
        return

    # Переходим в состояние ожидания адреса доставки
    await OrderStates.WAITING_FOR_ADDRESS.set()

    # Отправляем сообщение с запросом адреса доставки
    await callback_query.message.answer("Введите адрес доставки")

@dp.message_handler(state=OrderStates.WAITING_FOR_ADDRESS)
async def process_address(message: types.Message, state: FSMContext):
    # Получаем адрес доставки из сообщения
    address = message.text

    # Создание записи в таблице NewOrders
    cursor.execute("INSERT INTO NewOrders (ClientChatID, OrderStatus, DeliveryAddress) VALUES (?, ?, ?)",
                   (message.chat.id, "В работе", address))
    conn.commit()
    order_id = cursor.lastrowid
    # Перенос товаров из корзины в таблицу NewProductRelease
    cursor.execute("SELECT * FROM Cart WHERE ClientID=?", (message.from_user.id,))
    cart_items = cursor.fetchall()
    for cart_item in cart_items:
        product_id = cart_item[2]
        quantity = cart_item[3]
        cursor.execute("INSERT INTO NewProductRelease (OrderID, ProductID, Quantity) VALUES (?, ?, ?)",
                       (order_id, product_id, quantity))
        # Уменьшаем количество товара в таблице Product
        cursor.execute("UPDATE Product SET Quantity = Quantity - ? WHERE ID = ?", (quantity, product_id))

    conn.commit()
    # Удаление записей из таблицы Cart
    cursor.execute("DELETE FROM Cart WHERE ClientID=?", (message.from_user.id,))
    conn.commit()

    # Выводим сообщение об успешном оформлении заказа
    await message.answer("Спасибо! Ваш заказ успешно оформлен. Скоро с вами свяжется менеджер.")

    # Получаем реальное имя и номер телефона клиента из таблицы Users
    cursor.execute("SELECT RealName, TelNumber FROM Users WHERE ChatID=?", (message.chat.id,))
    user_info = cursor.fetchone()
    if user_info:
        real_name, tel_number = user_info
    else:
        real_name, tel_number = "Не указано", "Не указан"

    # Получаем ChatID администратора
    cursor.execute("SELECT ChatID FROM Admin")
    admin_chat_ids = cursor.fetchall()

    # Отправляем уведомление администратору о новом заказе
    for admin_chat_id in admin_chat_ids:
        # Создаем сообщение для администратора с информацией о заказе и контактными данными клиента
        admin_message = (
            f"Новый заказ:\n\nАдрес доставки: {address}\n\n"
            f"Контактные данные клиента:\n"
            f"Имя: {real_name}\n"
            f"Номер телефона: {tel_number}\n"
            f"<a href='tg://user?id={message.chat.id}'>Ссылка на диалог с клиентом</a>\n\n"
            f"Товары:\n"
        )

        # Получаем список товаров из заказа
        cursor.execute(
            "SELECT Product.Name, NewProductRelease.Quantity "
            "FROM NewProductRelease JOIN Product ON NewProductRelease.ProductID = Product.ID "
            "WHERE NewProductRelease.OrderID=?", (order_id,))
        order_items = cursor.fetchall()

        # Добавляем каждый товар в сообщение администратора
        for item in order_items:
            admin_message += f"{item[0]} - {item[1]} шт.\n"

        # Отправляем сообщение администратору с HTML разметкой для поддержки ссылок
        await bot.send_message(admin_chat_id[0], admin_message, parse_mode=types.ParseMode.HTML)

    # Сбрасываем состояние FSM
    await state.finish()


@dp.callback_query_handler(lambda query: query.data == 'cancel_order', state=None)
async def cancel_order(callback_query: types.CallbackQuery, state: FSMContext):
    # Удаляем предыдущие сообщения с корзиной
    await delete_previous_messages(callback_query.message.chat.id)

    # Выводим сообщение об отмене заказа
    await callback_query.message.answer("Оформление заказа отменено")

async def delete_previous_messages(chat_id):
    global product_messages
    global user_cart_message_ids
    global user_menu_message_ids

    if chat_id in product_messages:
        for msg_id in product_messages[chat_id]:
            try:
                await bot.delete_message(chat_id, msg_id)
            except aiogram.utils.exceptions.MessageToDeleteNotFound:
                pass
        del product_messages[chat_id]

    # Проверяем, есть ли у пользователя сохраненный идентификатор сообщения с общей стоимостью
    if chat_id in user_cart_message_ids:
        total_cost_message_id = user_cart_message_ids[chat_id]
        try:
            await bot.delete_message(chat_id, total_cost_message_id)
        except aiogram.utils.exceptions.MessageToDeleteNotFound:
            pass
        del user_cart_message_ids[chat_id]

    # Удаляем сообщение с кнопками "Актуальные" и "Архив"
    if chat_id in user_menu_message_ids:
        try:
            await bot.delete_message(chat_id, user_menu_message_ids[chat_id])
        except aiogram.utils.exceptions.MessageToDeleteNotFound:
            pass
        del user_menu_message_ids[chat_id]



#######################################################################Мои заказы
# Обрабатываем нажатие кнопки "Мои заказы"
@dp.message_handler(lambda message: message.text == "Мои заказы")
async def my_orders_menu(message: types.Message):
    # Удаляем предыдущие сообщения с меню заказов
    await delete_previous_messages(message.chat.id)

    # Создаем клавиатуру с двумя инлайн кнопками: "Актуальные" и "Архив"
    orders_menu_keyboard = InlineKeyboardMarkup(row_width=2)
    orders_menu_keyboard.add(
        InlineKeyboardButton(text="Актуальные", callback_data="current_orders"),
        InlineKeyboardButton(text="Архив", callback_data="archived_orders")
    )

    # Отправляем меню с выбором между "Актуальные" и "Архив"
    menu_message = await message.answer("Выберите раздел:", reply_markup=orders_menu_keyboard)

    # Сохраняем идентификатор сообщения
    user_menu_message_ids[message.chat.id] = menu_message.message_id

# Обрабатываем выбор "Актуальные" из меню "Мои заказы"
@dp.callback_query_handler(lambda query: query.data == "current_orders")
async def current_orders(callback_query: types.CallbackQuery):
    await callback_query.message.delete()

    # Получаем все актуальные заказы пользователя из таблицы NewOrders и связанные с ними товары из таблицы NewProductRelease
    cursor.execute("SELECT NewOrders.ID, NewOrders.OrderStatus, NewOrders.DeliveryAddress, Product.Name, NewProductRelease.Quantity FROM NewOrders JOIN NewProductRelease ON NewOrders.ID = NewProductRelease.OrderID JOIN Product ON NewProductRelease.ProductID = Product.ID WHERE NewOrders.ClientChatID=? AND (NewOrders.OrderStatus='В работе')", (callback_query.message.chat.id,))
    orders = cursor.fetchall()

    if not orders:
        await callback_query.message.answer("У вас пока нет актуальных заказов.")
        return

    # Формируем сообщение с информацией о заказах
    response = "Ваши актуальные заказы:\n"
    current_order_id = None
    for order in orders:
        order_id = order[0]
        status = order[1]
        address = order[2]
        product_name = order[3]
        quantity = order[4]

        # Если это первый товар в заказе, добавляем информацию о заказе
        if order_id != current_order_id:
            response += f"\n\nЗаказ №{order_id}\nСтатус: {status}\nАдрес доставки: {address}\n"
            current_order_id = order_id

        # Добавляем информацию о товаре
        response += f"- {product_name} - {quantity} шт.\n"

    await callback_query.message.answer(response)


# Обрабатываем выбор "Архив" из меню "Мои заказы"
@dp.callback_query_handler(lambda query: query.data == "archived_orders")
async def archived_orders(callback_query: types.CallbackQuery):
    await callback_query.message.delete()

    # Получаем все архивные заказы пользователя из таблицы OldOrders и связанные с ними товары из таблицы OldProductRelease
    cursor.execute("SELECT OldOrders.ID, OldOrders.OrderStatus, Product.Name, OldProductRelease.Quantity FROM OldOrders JOIN OldProductRelease ON OldOrders.ID = OldProductRelease.OrderID JOIN Product ON OldProductRelease.ProductID = Product.ID WHERE OldOrders.ClientChatID=?", (callback_query.message.chat.id,))
    orders = cursor.fetchall()

    if not orders:
        await callback_query.message.answer("У вас пока нет архивных заказов.")
        return

    # Формируем сообщение с информацией о заказах
    response = "Ваши архивные заказы:\n"
    archived_order_id = None
    for order in orders:
        order_id = order[0]
        status = order[1]
        product_name = order[2]
        quantity = order[3]

        # Если это первый товар в заказе, добавляем информацию о заказе
        if order_id != archived_order_id:
            response += f"\n\nЗаказ №{order_id}\nСтатус: {status}\n"
            archived_order_id = order_id

        # Добавляем информацию о товаре
        response += f"- {product_name} - {quantity} шт.\n"

    await callback_query.message.answer(response)


#################################################################Актуальные заказы у администратора
# Обработчик команды "Актуальные заказы"
@dp.message_handler(lambda message: message.text == "Актуальные заказы")
async def current_orders_command(message: types.Message, state: FSMContext):
    # Получаем все актуальные заказы из таблицы NewOrders со статусом "В работе"
    cursor.execute("SELECT NewOrders.ID, Users.RealName, Users.TelNumber, NewOrders.DeliveryAddress, Users.ChatID "
                   "FROM NewOrders LEFT JOIN Users ON NewOrders.ClientChatID = Users.ChatID "
                   "WHERE NewOrders.OrderStatus='В работе'")
    orders = cursor.fetchall()

    if not orders:
        await message.answer("На данный момент нет актуальных заказов.")
        return

    # Создаем сообщение с актуальными заказами
    response = "Актуальные заказы:\n"
    for order in orders:
        order_id = order[0]
        client_name = order[1]
        client_tel_number = order[2]
        delivery_address = order[3]
        client_chat_id = order[4]

        # Создаем кнопку "Выполнено" для каждого заказа
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Выполнено", callback_data=f"complete_order_{order_id}"))

        # Формируем текст сообщения с информацией о заказе и контактными данными клиента
        order_info_message = (
            f"Заказ №{order_id}\n"
            f"Имя клиента: {client_name}\n"
            f"Номер телефона клиента: {client_tel_number}\n"
            f"Адрес доставки: {delivery_address}\n"
            f"<a href='tg://user?id={client_chat_id}'>Ссылка на диалог с клиентом</a>\n\n"
        )

        # Отправляем карточку с заказом и сохраняем ее идентификатор в состоянии
        # Отправляем карточку с заказом и сохраняем ее идентификатор в состоянии
        sent_message = await message.answer(order_info_message, reply_markup=keyboard, parse_mode='HTML')

        # Получаем текущие сохраненные идентификаторы карточек из состояния
        state_data = await state.get_data()
        current_order_messages = state_data.get('current_order_messages', [])

        # Добавляем идентификатор текущей карточки в список
        current_order_messages.append(sent_message.message_id)

        # Сохраняем обновленный список в состоянии
        await state.update_data(current_order_messages=current_order_messages)






# Обработчик нажатия кнопки "Выполнено" для заказа
@dp.callback_query_handler(lambda query: query.data.startswith("complete_order_"))
async def complete_order(callback_query: types.CallbackQuery, state: FSMContext):
    # Получаем ID заказа из callback_data
    order_id = int(callback_query.data.split("_")[2])

    # Удаляем все сохраненные карточки с заказами
    state_data = await state.get_data()
    current_order_messages = state_data.get('current_order_messages', [])
    for message_id in current_order_messages:
        try:
            await bot.delete_message(callback_query.message.chat.id, message_id)
        except Exception as e:
            print(f"Ошибка при удалении сообщения: {e}")

    # Отправляем сообщение о переводе заказа в статус "Выполнено" с кнопками "Да" и "Нет"
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"confirm_complete_{order_id}"),
                 types.InlineKeyboardButton("Нет", callback_data="cancel"))
    await callback_query.message.answer(f"Перевести заказ №{order_id} в статус 'Выполнено'?", reply_markup=keyboard)

    # Очищаем список сохраненных карточек в состоянии
    await state.update_data(current_order_messages=[])

# Обработчик нажатия кнопки "Нет" после вопроса о выполнении заказа
@dp.callback_query_handler(lambda query: query.data == "cancel")
async def cancel_action(callback_query: types.CallbackQuery):
    # Удаляем сообщение с вопросом
    await callback_query.message.delete()
    # Выводим сообщение "Действие отменено"
    await callback_query.message.answer("Действие отменено.")


# Обработчик подтверждения выполнения заказа
@dp.callback_query_handler(lambda query: query.data.startswith("confirm_complete_"))
async def confirm_complete_order(callback_query: types.CallbackQuery, state: FSMContext):
    # Получаем ID заказа из callback_data
    order_id = int(callback_query.data.split("_")[2])

    try:
        # Начинаем транзакцию
        with conn:
            # Обновляем статус заказа в таблице NewOrders на "Выполнено"
            cursor.execute("UPDATE NewOrders SET OrderStatus = 'Выполнено' WHERE ID = ?", (order_id,))

            # Переносим товары из таблицы NewProductRelease в таблицу OldProductRelease
            cursor.execute(
                "INSERT OR REPLACE INTO OldProductRelease (ID, OrderID, ProductID, Quantity) SELECT ID, OrderID, ProductID, Quantity FROM NewProductRelease WHERE OrderID = ?",
                (order_id,))


            # Переносим заказ из таблицы NewOrders в таблицу OldOrders
            cursor.execute(
                "INSERT OR REPLACE INTO OldOrders (ID, ClientChatID, OrderStatus, DeliveryAddress) SELECT ID, ClientChatID, OrderStatus, DeliveryAddress FROM NewOrders WHERE ID = ?",
                (order_id,))


        # Получаем ChatID клиента
        cursor.execute("SELECT ClientChatID FROM OldOrders WHERE ID = ?", (order_id,))
        client_chat_id = cursor.fetchone()[0]

        # Отправляем сообщение клиенту об успешном выполнении заказа
        await bot.send_message(client_chat_id, f"Ваш заказ №{order_id} переведен в статус 'Выполнено'. Если возникли вопросы по поводу заказа, доступен диалог через кнопку 'Поддержка', здесь вы можете задать все интересующие вас вопросы.")

        # Удаляем сообщение с вопросом о выполнении заказа
        await callback_query.message.delete()

        # Отправляем сообщение об успешном выполнении заказа
        await callback_query.message.answer(f"Заказ №{order_id} переведен в статус 'Выполнено'.")
    except Exception as e:
        await callback_query.message.answer(f"Ошибка при выполнении заказа: {e}")


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)