import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes, filters,
    ConversationHandler
)
from openai import OpenAI
from calendar_utils import list_free_slots, create_appointment
import datetime
import re

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

SELECT_SPECIALIST, SELECT_SLOT, ASK_EMAIL = range(3)

SPECIALISTS = ["Валерія", "Тамара", "Дмитро", "Іван"]
SPECIALISTS_GENITIVE = {
    "валерія": "Валерія", "валерії": "Валерія",
    "тамара": "Тамара", "тамари": "Тамара",
    "дмитро": "Дмитро", "дмитра": "Дмитро",
    "іван": "Іван", "івана": "Іван"
}
SLOT_DURATION = 30

user_selected_specialist = {}
user_slots = {}
user_slot_selection = {}

with open("context.txt", "r", encoding="utf-8") as f:
    system_content = f.read()


async def start_recording(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"До якого спеціаліста бажаєте запис? Наші спеціалісти: {', '.join(SPECIALISTS)}"
    )
    return SELECT_SPECIALIST


async def handle_specialist_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()

    # Поиск имени специалиста в тексте
    selected = None
    for word in text.split():
        cleaned = word.strip('.,!?():')
        if cleaned in SPECIALISTS_GENITIVE:
            selected = SPECIALISTS_GENITIVE[cleaned]
            break

    if not selected:
        await update.message.reply_text(
            f"Невірний спеціаліст. Будь ласка, оберіть одного з: {', '.join(SPECIALISTS)}"
        )
        return SELECT_SPECIALIST

    user_selected_specialist[user_id] = selected

    now = datetime.datetime.now(datetime.timezone.utc)
    start_iso = now.isoformat()
    end_iso = (now + datetime.timedelta(days=7)).isoformat()

    slots = list_free_slots(
        specialist="laserepilation",
        start_iso=start_iso,
        end_iso=end_iso,
        duration_minutes=SLOT_DURATION
    )
    user_slots[user_id] = slots

    msg = f"Ось доступні слоти для {selected}:\n"
    for slot in slots[:5]:
        dt = slot['start']
        date = dt[8:10] + "." + dt[5:7]
        time = dt[11:16]
        msg += f"{date} о {time} ({SLOT_DURATION} хв)\n"
    msg += "\nВведіть бажану дату та час (наприклад 15.07 о 11:30):"
    await update.message.reply_text(msg)
    return SELECT_SLOT


async def handle_slot_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text.strip().lower()

    match = re.match(r"(\d{1,2})[.\-/](\d{1,2}).*?(\d{1,2}):(\d{2})", user_text)
    if not match:
        await update.message.reply_text(
            "Невірний формат. Введіть, наприклад: 15.07 о 11:30"
        )
        return SELECT_SLOT

    day, month, hour, minute = match.groups()
    formatted = f"{day.zfill(2)}.{month.zfill(2)} о {hour.zfill(2)}:{minute}"

    slots = user_slots.get(user_id, [])
    for slot in slots:
        dt = slot['start']
        date = dt[8:10] + "." + dt[5:7]
        time = dt[11:16]
        if f"{date} о {time}" == formatted:
            user_slot_selection[user_id] = slot
            await update.message.reply_text("Введіть ваш Email для підтвердження запису:")
            return ASK_EMAIL

    await update.message.reply_text("На жаль, цього слоту немає в списку. Спробуйте іншу дату і час.")
    return SELECT_SLOT


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    email = update.message.text.strip()

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("❗ Це не схоже на email. Спробуйте ще раз:")
        return ASK_EMAIL

    slot = user_slot_selection.get(user_id)
    specialist = user_selected_specialist.get(user_id, "laserepilation")

    create_appointment(
        specialist=specialist,
        start_iso=slot['start'],
        end_iso=slot['end'],
        summary="Лазерна епіляція",
        description=f"Запис через Telegram до {specialist}",
        attendee_email=email
    )

    date = slot['start'][8:10] + "." + slot['start'][5:7]
    time = slot['start'][11:16]

    await update.message.reply_text(f"Запис підтверджено ✅ Чекаємо вас {date} о {time}")
    return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.lower()
    if "запис" in user_message or "хочу записатися" in user_message:
        return await start_recording(update, context)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": update.message.text},
        ]
    )
    await update.message.reply_text(response.choices[0].message.content)


app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
    states={
        SELECT_SPECIALIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_specialist_selection)],
        SELECT_SLOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_slot_selection)],
        ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
    },
    fallbacks=[],
)

app.add_handler(conv_handler)

print("Бот запущено...")
app.run_polling()