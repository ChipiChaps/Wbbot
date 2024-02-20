import sqlite3

# Создание соединения с базой данных
conn = sqlite3.connect('wbbot.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы Администратор
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Admin (
        ID INTEGER PRIMARY KEY,
        ChatID INTEGER,
        Name TEXT
    )
''')

# Создание таблицы Users
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Users (
        ID INTEGER PRIMARY KEY,
        ChatID INTEGER,
        Name TEXT,
        Address TEXT,
        TelNumber TEXT,
        RelaName TEXT
    )
''')

# Создание таблицы Товар
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Product (
        ID INTEGER PRIMARY KEY,
        Name TEXT,
        Description TEXT,
        Price REAL,
        Quantity INTEGER,
        Photo TEXT
    )
''')

# Создание таблицы Корзина
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Cart (
        ID INTEGER PRIMARY KEY,
        ClientID INTEGER,
        ProductID INTEGER,
        Quantity INTEGER,
        FOREIGN KEY (ClientID) REFERENCES Users(ID),
        FOREIGN KEY (ProductID) REFERENCES Product(ID)
    )
''')

# Создание таблицы New Заказы
cursor.execute('''
    CREATE TABLE IF NOT EXISTS NewOrders (
        ID INTEGER PRIMARY KEY,
        ClientChatID INTEGER,
        OrderStatus TEXT,
        DeliveryAddress TEXT
    )
''')

# Создание таблицы New Товар на выдачу
cursor.execute('''
    CREATE TABLE IF NOT EXISTS NewProductRelease (
        ID INTEGER PRIMARY KEY,
        OrderID INTEGER,
        ProductID INTEGER,
        Quantity INTEGER,
        FOREIGN KEY (OrderID) REFERENCES NewOrders(ID),
        FOREIGN KEY (ProductID) REFERENCES Product(ID)
    )
''')

# Создание таблицы Old Заказы
cursor.execute('''
    CREATE TABLE IF NOT EXISTS OldOrders (
        ID INTEGER PRIMARY KEY,
        ClientChatID INTEGER,
        OrderStatus TEXT,
        DeliveryAddress TEXT
    )
''')

# Создание таблицы Old Товар на выдачу
cursor.execute('''
    CREATE TABLE IF NOT EXISTS OldProductRelease (
        ID INTEGER PRIMARY KEY,
        OrderID INTEGER,
        ProductID INTEGER,
        Quantity INTEGER,
        FOREIGN KEY (OrderID) REFERENCES OldOrders(ID),
        FOREIGN KEY (ProductID) REFERENCES Product(ID)
    )
''')

# Сохранение изменений и закрытие соединения
conn.commit()
conn.close()
