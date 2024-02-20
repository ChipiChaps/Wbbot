import sqlite3

# Подключение к базе данных
conn = sqlite3.connect('wbbot.db', check_same_thread=False)
cursor = conn.cursor()

# Изменение структуры таблицы Users
cursor.execute('''
    ALTER TABLE OldOrders 
    ADD COLUMN DeliveryAddress TEXT
''')

# Сохранение изменений
conn.commit()
