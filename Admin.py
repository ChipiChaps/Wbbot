from main import dp, conn

bot = dp.bot

def is_Admin(user_id):
    if cursor is not None:
        cursor.execute("SELECT COUNT(*) FROM Admin WHERE ChatID=?",(user_id,))
        result = cursor.fetchone()
        if result is not None:
            return result[0]
        return False
cursor = conn.cursor()