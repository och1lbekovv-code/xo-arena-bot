
import os
import telebot
from telebot import types
import sqlite3
import random
import secrets
import logging
from urllib.parse import quote

# ==========================================
# 1. SOZLAMALAR
# ==========================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN server sozlamasiga kiritilmagan!")

bot = telebot.TeleBot(TOKEN, threaded=False)
logging.basicConfig(level=logging.ERROR)

games = {}

db = sqlite3.connect(
    "xo_arena_new.db",
    check_same_thread=False
)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS arena_users (
    uid INTEGER PRIMARY KEY,
    name TEXT DEFAULT 'Player',
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    coins INTEGER DEFAULT 0
)
""")
db.commit()


# ==========================================
# 2. FOYDALANUVCHILAR
# ==========================================

def get_name(user):
    return (user.first_name or user.username or "Player").strip()


def register(user):
    name = get_name(user)

    cur.execute("""
        INSERT OR IGNORE INTO arena_users (uid, name)
        VALUES (?, ?)
    """, (user.id, name))

    cur.execute("""
        UPDATE arena_users SET name = ? WHERE uid = ?
    """, (name, user.id))

    db.commit()


# ==========================================
# 3. COIN VA STATISTIKA
# ==========================================

def reward(uid, result):
    if not uid:
        return

    if result == "win":
        cur.execute("""
            UPDATE arena_users
            SET wins = wins + 1, coins = coins + 10
            WHERE uid = ?
        """, (uid,))

    elif result == "loss":
        cur.execute("""
            UPDATE arena_users
            SET losses = losses + 1
            WHERE uid = ?
        """, (uid,))

    elif result == "draw":
        cur.execute("""
            UPDATE arena_users
            SET draws = draws + 1, coins = coins + 2
            WHERE uid = ?
        """, (uid,))

    db.commit()


# ==========================================
# 4. MENYU
# ==========================================

def menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("🤖 BOT BILAN", "👥 DO'ST BILAN")
    m.row("👤 PROFIL", "🏆 REYTING")
    m.row("🪙 COIN", "ℹ️ YORDAM")
    return m


@bot.message_handler(commands=["start"])
def start(message):
    register(message.from_user)

    parts = message.text.split(maxsplit=1)

    if len(parts) > 1 and parts[1].startswith("join_"):
        join_friend(message, parts[1][5:])
        return

    bot.send_message(
        message.chat.id,
        "🔥 XO ARENA'ga xush kelibsiz!\n\n"
        "🎮 O'yin turini tanlang:",
        reply_markup=menu()
    )


# ==========================================
# 5. O'YIN MANTIG'I
# ==========================================

def winner(board):
    lines = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]

    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]

    return None


def empty_cells(board):
    return [i for i in range(9) if board[i] == ""]


def minimax(board, maximizing):
    w = winner(board)

    if w == "O":
        return 10

    if w == "X":
        return -10

    moves = empty_cells(board)

    if not moves:
        return 0

    if maximizing:
        best = -100

        for i in moves:
            board[i] = "O"
            score = minimax(board, False)
            board[i] = ""
            best = max(best, score)

        return best

    best = 100

    for i in moves:
        board[i] = "X"
        score = minimax(board, True)
        board[i] = ""
        best = min(best, score)

    return best


def computer_move(board, level):
    moves = empty_cells(board)

    if not moves:
        return None

    if level == "easy":
        return random.choice(moves)

    # Bot yutish imkoniyati
    for i in moves:
        board[i] = "O"
        if winner(board) == "O":
            board[i] = ""
            return i
        board[i] = ""

    # X yutishini to'xtatish
    for i in moves:
        board[i] = "X"
        if winner(board) == "X":
            board[i] = ""
            return i
        board[i] = ""

    if level == "medium":
        if 4 in moves:
            return 4

        corners = [i for i in [0, 2, 6, 8] if i in moves]

        if corners:
            return random.choice(corners)

        return random.choice(moves)

    # Qiyin daraja
    best_score = -100
    best_moves = []

    for i in moves:
        board[i] = "O"
        score = minimax(board, False)
        board[i] = ""

        if score > best_score:
            best_score = score
            best_moves = [i]
        elif score == best_score:
            best_moves.append(i)

    return random.choice(best_moves)


# ==========================================
# 6. O'YIN MAYDONI
# ==========================================

def icon(value):
    if value == "X":
        return "❌"
    if value == "O":
        return "🔵"
    return "▫️"


def board_text(g):
    if g["mode"] == "bot":
        text = "❌ SIZ (X)       🔵 BOT (O)\n\n"
    else:
        text = (
            f"❌ {g['x_name']} (X)    "
            f"🔵 {g['o_name']} (O)\n\n"
        )

    for r in range(3):
        row = []

        for c in range(3):
            i = r * 3 + c
            row.append(icon(g["board"][i]))

        text += "　　 ".join(row) + "\n\n"

    if not g["finished"]:
        text += (
            "👉 Navbat: "
            + ("❌ X" if g["turn"] == "X" else "🔵 O")
        )
    else:
        if g["winner"] == "X":
            text += "\n🏆 X G'ALABA QOZONDI!"
        elif g["winner"] == "O":
            text += "\n🏆 O G'ALABA QOZONDI!"
        else:
            text += "\n🤝 DURANG!"

    return text


def keyboard(g):
    m = types.InlineKeyboardMarkup(row_width=3)

    if not g["finished"]:
        for r in range(3):
            row = []

            for c in range(3):
                i = r * 3 + c

                row.append(
                    types.InlineKeyboardButton(
                        icon(g["board"][i]),
                        callback_data=f"move:{g['id']}:{i}"
                    )
                )

            m.row(*row)

    else:
        m.row(
            types.InlineKeyboardButton(
                "🔄 QAYTA O'YNASH",
                callback_data=f"restart:{g['id']}"
            )
        )

        m.row(
            types.InlineKeyboardButton(
                "🏠 MENYU",
                callback_data="back_menu"
            )
        )

    return m


def show_game(g):
    text = board_text(g)
    markup = keyboard(g)

    for uid in g["players"]:
        try:
            if uid in g["messages"]:
                bot.edit_message_text(
                    text=text,
                    chat_id=uid,
                    message_id=g["messages"][uid],
                    reply_markup=markup
                )
            else:
                msg = bot.send_message(
                    uid,
                    text,
                    reply_markup=markup
                )
                g["messages"][uid] = msg.message_id

        except Exception as e:
            logging.error("Maydon xatosi: %s", e)


# ==========================================
# 7. O'YINNI YAKUNLASH
# ==========================================

def finish(g, result):
    if g["finished"]:
        return

    g["finished"] = True
    g["winner"] = result

    if result == "X":
        reward(g["x_uid"], "win")

        if g["mode"] == "friend":
            reward(g["o_uid"], "loss")

    elif result == "O":
        if g["mode"] == "bot":
            reward(g["x_uid"], "loss")
        else:
            reward(g["o_uid"], "win")
            reward(g["x_uid"], "loss")

    else:
        reward(g["x_uid"], "draw")

        if g["mode"] == "friend":
            reward(g["o_uid"], "draw")


def check_end(g):
    w = winner(g["board"])

    if w:
        finish(g, w)
        return True

    if not empty_cells(g["board"]):
        finish(g, None)
        return True

    return False


# ==========================================
# 8. BOT BILAN O'YIN
# ==========================================

@bot.message_handler(func=lambda m: m.text == "🤖 BOT BILAN")
def bot_menu(message):
    register(message.from_user)

    m = types.InlineKeyboardMarkup()

    m.row(types.InlineKeyboardButton(
        "🟢 OSON", callback_data="level:easy"
    ))

    m.row(types.InlineKeyboardButton(
        "🟡 O'RTA", callback_data="level:medium"
    ))

    m.row(types.InlineKeyboardButton(
        "🔴 QIYIN", callback_data="level:hard"
    ))

    bot.send_message(
        message.chat.id,
        "🤖 Bot darajasini tanlang:",
        reply_markup=m
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("level:"))
def start_bot_game(call):
    bot.answer_callback_query(call.id)

    level = call.data.split(":")[1]
    uid = call.from_user.id

    register(call.from_user)

    gid = secrets.token_hex(4)

    g = {
        "id": gid,
        "mode": "bot",
        "level": level,
        "board": [""] * 9,
        "turn": "X",
        "finished": False,
        "winner": None,
        "x_uid": uid,
        "o_uid": None,
        "x_name": get_name(call.from_user),
        "o_name": "XO BOT",
        "players": [uid],
        "messages": {}
    }

    games[gid] = g

    try:
        bot.delete_message(
            call.message.chat.id,
            call.message.message_id
        )
    except Exception:
        pass

    show_game(g)


# ==========================================
# 9. DO'ST BILAN O'YIN
# ==========================================

@bot.message_handler(func=lambda m: m.text == "👥 DO'ST BILAN")
def create_friend(message):
    register(message.from_user)

    gid = secrets.token_hex(4)

    g = {
        "id": gid,
        "mode": "friend",
        "board": [""] * 9,
        "turn": "X",
        "finished": False,
        "winner": None,
        "x_uid": message.from_user.id,
        "o_uid": None,
        "x_name": get_name(message.from_user),
        "o_name": "Kutilmoqda",
        "players": [message.from_user.id],
        "messages": {},
        "waiting": True
    }

    games[gid] = g

    try:
        bot_username = bot.get_me().username
        game_link = f"https://t.me/{bot_username}?start=join_{gid}"

        share_link = (
            "https://t.me/share/url?"
            f"url={quote(game_link, safe='')}"
            f"&text={quote('🔥 XO ARENA — men bilan XO o‘yiniga qo‘shiling!')}"
        )

        m = types.InlineKeyboardMarkup()

        m.add(types.InlineKeyboardButton(
            "📨 DO'STINGIZGA YUBORISH",
            url=share_link
        ))

        m.add(types.InlineKeyboardButton(
            "🎮 O'YINGA KIRISH",
            url=game_link
        ))

        bot.send_message(
            message.chat.id,
            "🔥 XO ARENA — DO'ST BILAN\n\n"
            "❌ Siz X bo'lasiz.\n"
            "🔵 Do'stingiz O bo'ladi.\n\n"
            "📨 «DO'STINGIZGA YUBORISH» tugmasini bosing "
            "va havolani do'stingizga jo'nating.\n\n"
            "Do'stingiz havolani bosishi bilan o'yinga qo'shiladi.",
            reply_markup=m
        )

    except Exception as e:
        logging.error("Havola xatosi: %s", e)

        bot.send_message(
            message.chat.id,
            "❌ Havola yaratilmadi. Qayta urinib ko'ring."
        )


def join_friend(message, gid):
    register(message.from_user)

    g = games.get(gid)

    if not g:
        bot.send_message(
            message.chat.id,
            "❌ O'yin topilmadi.\n"
            "O'yin egasidan yangi havola so'rang."
        )
        return

    if not g.get("waiting", False):
        bot.send_message(
            message.chat.id,
            "❌ Bu o'yinga boshqa o'yinchi qo'shilgan."
        )
        return

    if message.from_user.id == g["x_uid"]:
        bot.send_message(
            message.chat.id,
            "❌ O'zingizning o'yiningizga qo'shila olmaysiz."
        )
        return

    g["o_uid"] = message.from_user.id
    g["o_name"] = get_name(message.from_user)
    g["players"].append(message.from_user.id)
    g["waiting"] = False

    bot.send_message(
        g["x_uid"],
        "✅ Do'stingiz o'yinga qo'shildi!\n🎮 O'yin boshlandi."
    )

    bot.send_message(
        g["o_uid"],
        "✅ Siz 🔵 O belgisini oldingiz!\n🎮 O'yin boshlandi."
    )

    show_game(g)


# ==========================================
# 10. QAYTA O'YNASH
# ==========================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("restart:"))
def restart_game(call):
    gid = call.data.split(":")[1]
    g = games.get(gid)

    if not g:
        bot.answer_callback_query(call.id, "O'yin topilmadi.")
        return

    if not g["finished"]:
        bot.answer_callback_query(call.id, "O'yin hali tugamagan.")
        return

    if call.from_user.id not in g["players"]:
        bot.answer_callback_query(call.id, "Bu sizning o'yiningiz emas.")
        return

    if g["mode"] == "friend":
        bot.answer_callback_query(
            call.id,
            "Yangi o'yin uchun menyudan taklif yarating."
        )
        return

    bot.answer_callback_query(call.id)

    g["board"] = [""] * 9
    g["turn"] = "X"
    g["finished"] = False
    g["winner"] = None

    show_game(g)


# ==========================================
# 11. MENYU
# ==========================================

@bot.callback_query_handler(func=lambda c: c.data == "back_menu")
def back_menu(call):
    bot.answer_callback_query(call.id)

    try:
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None
        )
    except Exception:
        pass

    bot.send_message(
        call.message.chat.id,
        "🏠 XO ARENA MENYU\n\nO'yin turini tanlang:",
        reply_markup=menu()
    )


# ==========================================
# 12. YURISHLAR
# ==========================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("move:"))
def move(call):
    try:
        _, gid, number = call.data.split(":")
        i = int(number)

        g = games.get(gid)

        if not g or g["finished"]:
            bot.answer_callback_query(
                call.id,
                "O'yin tugagan yoki topilmadi."
            )
            return

        uid = call.from_user.id

        if uid not in g["players"]:
            bot.answer_callback_query(
                call.id,
                "Bu sizning o'yiningiz emas."
            )
            return

        if i not in range(9) or g["board"][i] != "":
            bot.answer_callback_query(call.id, "Bu katak band!")
            return

        if g["mode"] == "bot":
            if uid != g["x_uid"] or g["turn"] != "X":
                bot.answer_callback_query(
                    call.id,
                    "Hozir sizning navbatingiz emas."
                )
                return
        else:
            expected = (
                g["x_uid"] if g["turn"] == "X" else g["o_uid"]
            )

            if uid != expected:
                bot.answer_callback_query(
                    call.id,
                    "Hozir sizning navbatingiz emas."
                )
                return

        bot.answer_callback_query(call.id)

        g["board"][i] = g["turn"]

        if check_end(g):
            show_game(g)
            return

        g["turn"] = "O" if g["turn"] == "X" else "X"

        if g["mode"] == "bot":
            j = computer_move(g["board"], g["level"])

            if j is not None:
                g["board"][j] = "O"

            if not check_end(g):
                g["turn"] = "X"

        show_game(g)

    except Exception as e:
        logging.exception("Yurish xatosi: %s", e)

        try:
            bot.answer_callback_query(
                call.id,
                "Xatolik. Qayta urinib ko'ring."
            )
        except Exception:
            pass


# ==========================================
# 13. PROFIL
# ==========================================

@bot.message_handler(func=lambda m: m.text == "👤 PROFIL")
def profile(message):
    register(message.from_user)

    cur.execute("""
        SELECT name, wins, losses, draws, coins
        FROM arena_users WHERE uid = ?
    """, (message.from_user.id,))

    row = cur.fetchone()

    if not row:
        bot.send_message(message.chat.id, "Profil topilmadi.")
        return

    name, wins, losses, draws, coins = row
    total = wins + losses + draws

    bot.send_message(
        message.chat.id,
        "👤 SIZNING PROFILINGIZ\n\n"
        f"🧑 Ism: {name}\n"
        f"🎮 Jami o'yin: {total}\n"
        f"🏆 G'alaba: {wins}\n"
        f"❌ Mag'lubiyat: {losses}\n"
        f"🤝 Durang: {draws}\n"
        f"🪙 Coin: {coins}"
    )


# ==========================================
# 14. REYTING
# ==========================================

@bot.message_handler(func=lambda m: m.text == "🏆 REYTING")
def rating(message):
    register(message.from_user)

    cur.execute("""
        SELECT name, wins, coins
        FROM arena_users
        ORDER BY wins DESC, coins DESC
        LIMIT 10
    """)

    rows = cur.fetchall()

    text = "🏆 XO ARENA REYTINGI\n\n"
    medals = ["🥇", "🥈", "🥉"]

    if not rows:
        text += "Hozircha o'yinchilar yo'q."
    else:
        for i, row in enumerate(rows):
            name, wins, coins = row
            medal = medals[i] if i < 3 else str(i + 1) + "."

            text += (
                f"{medal} {name}\n"
                f"🏆 {wins} | 🪙 {coins}\n\n"
            )

    bot.send_message(message.chat.id, text)


# ==========================================
# 15. COIN
# ==========================================

@bot.message_handler(func=lambda m: m.text == "🪙 COIN")
def coin(message):
    register(message.from_user)

    cur.execute("""
        SELECT coins FROM arena_users WHERE uid = ?
    """, (message.from_user.id,))

    row = cur.fetchone()
    coins = row[0] if row else 0

    bot.send_message(
        message.chat.id,
        "🪙 XO ARENA COIN\n\n"
        f"💰 Balansingiz: {coins} coin\n\n"
        "🏆 G'alaba: +10 coin\n"
        "🤝 Durang: +2 coin\n\n"
        "Coinlar virtual o'yin ballaridir."
    )


# ==========================================
# 16. YORDAM
# ==========================================

@bot.message_handler(func=lambda m: m.text == "ℹ️ YORDAM")
def help_text(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ XO ARENA YORDAM\n\n"
        "🤖 Bot bilan: oson, o'rta, qiyin.\n"
        "👥 Do'st bilan: taklif havolasi.\n"
        "👤 Profil: o'yin statistikasi.\n"
        "🏆 Reyting: TOP 10 o'yinchi.\n"
        "🪙 Coin: virtual ballaringiz.\n\n"
        "Maqsad — 3 ta belgini bir qatorga joylashtirish."
    )


# ==========================================
# 17. ISHGA TUSHIRISH
# ==========================================

print("🔥 XO ARENA ISHGA TUSHDI!")

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
