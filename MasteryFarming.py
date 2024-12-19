from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from collections import defaultdict
import asyncio
from datetime import datetime, timedelta

class LikeBot:
    def __init__(self, token):
        self.token = token
        self.likes_data = defaultdict(list)  # ذخیره داده‌ها به صورت لیستی برای هر چت
        self.input_data = defaultdict(lambda: {
            'required_likes': 1,  # تعداد پیش‌فرض
            'timer_minutes': 1  # زمان پیش‌فرض
        })
        self.additional_time = timedelta(hours=3, minutes=29, seconds=59)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        # هر بار که فرآیند جدید شروع می‌شود، یک چرخه جدید برای آن چت ایجاد می‌شود
        self.likes_data[chat_id].append({
            'likes_count': 0,
            'liked_users': set(),
            'message_id': None,
            'remaining_time': self.input_data[chat_id]['timer_minutes'] * 60,
            'timer_task': None,
            'stop_requested': False,
            'end_time': datetime.now() + timedelta(minutes=self.input_data[chat_id]['timer_minutes']) + self.additional_time,
            'stopped': False,
            'did_touch': set(),
            'did_not_touch': set(),
            'first_message': True
        })

        await update.message.reply_text(
            "لطفاً تعداد لایک موردنیاز و زمان تایمر (به دقیقه) را به این صورت وارد کنید:\n"
            "`تعداد لایک, زمان`\nمثال: `10, 5`\n\n"
            "برای توقف چرخه، کلمه `stop` را ارسال کنید.",
            parse_mode="Markdown"
        )

    async def handle_likes_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        if self.likes_data[chat_id][-1]['stopped']:
            return  # جلوگیری از پاسخ بعد از توقف

        user_input = update.message.text.strip().lower()

        if user_input == "stop":
            await self.stop_cycle(chat_id, context)
            return

        try:
            required_likes, timer_minutes = map(int, user_input.split(","))
            if required_likes > 0 and timer_minutes > 0:
                self.input_data[chat_id]['required_likes'] = required_likes
                self.input_data[chat_id]['timer_minutes'] = timer_minutes
                await self.start_new_cycle(chat_id, context)
            else:
                await update.message.reply_text("لطفاً مقادیر معتبر وارد کنید.")
        except ValueError:
            pass

    async def start_new_cycle(self, chat_id, context):
        # فقط داده‌های مربوط به چرخه جدید ریست می‌شوند
        current_cycle = self.likes_data[chat_id][-1]  # گرفتن جدیدترین چرخه
        current_cycle['likes_count'] = 0
        current_cycle['liked_users'] = set()
        current_cycle['remaining_time'] = self.input_data[chat_id]['timer_minutes'] * 60
        current_cycle['end_time'] = datetime.now() + timedelta(minutes=self.input_data[chat_id]['timer_minutes']) + self.additional_time
        current_cycle['did_touch'] = set()
        current_cycle['did_not_touch'] = set()
        current_cycle['first_message'] = True

        # ارسال پیام جدید برای چرخه فعلی
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=self.format_message(chat_id),
            parse_mode="Markdown",
            reply_markup=self.get_keyboard(chat_id)
        )

        # ذخیره شناسه پیام جدید برای بروزرسانی آن در چرخه‌های بعدی
        current_cycle['message_id'] = message.message_id
        current_cycle['timer_task'] = asyncio.create_task(self.start_timer(chat_id, context))

    def get_keyboard(self, chat_id):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👍 لایک", callback_data='like')],
            [
                InlineKeyboardButton("💥 بهم خورد", callback_data='did_touch'),
                InlineKeyboardButton("🤝 بهم نخورد", callback_data='did_not_touch')
            ]
        ])

    async def handle_like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        chat_id = query.message.chat_id
        user_id = query.from_user.id

        await query.answer()

        current_cycle = self.likes_data[chat_id][-1]

        if user_id in current_cycle['liked_users']:
            await query.answer("شما قبلاً لایک کرده‌اید!", show_alert=True)
            return

        current_cycle['liked_users'].add(user_id)
        current_cycle['likes_count'] += 1

        await query.edit_message_text(
            text=self.format_message(chat_id),
            parse_mode="Markdown",
            reply_markup=self.get_keyboard(chat_id)
        )

    async def handle_touch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        chat_id = query.message.chat_id
        user_id = query.from_user.id

        await query.answer()

        current_cycle = self.likes_data[chat_id][-1]

        if user_id in current_cycle['did_touch'] or user_id in current_cycle['did_not_touch']:
            await query.answer("شما قبلاً رای داده‌اید!", show_alert=True)
            return

        if query.data == 'did_touch':
            current_cycle['did_touch'].add(user_id)
        elif query.data == 'did_not_touch':
            current_cycle['did_not_touch'].add(user_id)

        await query.edit_message_text(
            text=self.format_message(chat_id),
            parse_mode="Markdown",
            reply_markup=self.get_keyboard(chat_id)
        )

    async def start_timer(self, chat_id, context):
        current_cycle = self.likes_data[chat_id][-1]
        remaining_time = current_cycle['remaining_time']

        while remaining_time > 0:
            if current_cycle['stop_requested']:
                return  # در صورت درخواست توقف، تایمر متوقف می‌شود

            # به‌روزرسانی زمان باقی‌مانده در هر دقیقه
            await asyncio.sleep(60)  # خوابیدن برای 60 ثانیه
            remaining_time -= 60
            current_cycle['remaining_time'] = remaining_time

            # بررسی زمان باقی‌مانده و ارسال پیام به‌روزرسانی
            if remaining_time % 60 == 0:  # ارسال پیام هر دقیقه
                await context.bot.edit_message_text(
                    text=self.format_message(chat_id),
                    chat_id=chat_id,
                    message_id=current_cycle['message_id'],
                    parse_mode="Markdown",
                    reply_markup=self.get_keyboard(chat_id)
                )

        # پس از اتمام زمان، کلیدها را حذف می‌کنیم
        await context.bot.edit_message_text(
            text=self.format_message(chat_id),
            chat_id=chat_id,
            message_id=current_cycle['message_id'],
            parse_mode="Markdown",
            reply_markup=None  # حذف کلیدها
        )

        # پس از اتمام زمان، چک می‌کنیم که لایک‌ها کافی هستند یا نه
        if current_cycle['likes_count'] >= self.input_data[chat_id]['required_likes']:
            await context.bot.send_message(chat_id=chat_id, text="شمارش معکوس شروع می‌شود ✅️")
            await asyncio.sleep(1.5)
            await self.start_countdown(chat_id, context)
        else:
            await context.bot.send_message(chat_id=chat_id, text="⏳ زمان به پایان رسید اما تعداد لایک‌ها کافی نبود. چرخه مجدداً شروع شد!")
            await self.start_new_cycle(chat_id, context)

    async def start_countdown(self, chat_id, context):
        for i in range(5, 0, -1):
            await context.bot.send_message(chat_id=chat_id, text=f"⏳{i}")
            await asyncio.sleep(1.5)
        await asyncio.sleep(3)
        await context.bot.send_message(chat_id=chat_id, text="🎉 شمارش معکوس به پایان رسید!")
        await asyncio.sleep(1.5)
        await self.start_new_cycle(chat_id, context)

    async def stop_cycle(self, chat_id, context):
        current_cycle = self.likes_data[chat_id][-1]
        current_cycle['stop_requested'] = True
        current_cycle['stopped'] = True

        if current_cycle['timer_task']:
            current_cycle['timer_task'].cancel()

        await context.bot.send_message(chat_id=chat_id, text="⛔ چرخه متوقف شد.")

    def format_time(self, seconds):
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02}:{seconds:02}"

    def format_message(self, chat_id):
        current_cycle = self.likes_data[chat_id][-1]
        return (f"✅ تعداد لایک‌ها: {current_cycle['likes_count']}/{self.input_data[chat_id]['required_likes']}\n"
                f"⏳ زمان باقی‌مانده: {self.format_time(current_cycle['remaining_time'])}\n"
                f"⏰️ زمان اتمام: {current_cycle['end_time'].strftime('%H:%M:%S')}\n\n"
                f"👥 بهم نخوردند: {len(current_cycle['did_not_touch'])}\n"
                f"💥 بهم خوردند: {len(current_cycle['did_touch'])}")

    def run(self):
        application = Application.builder().token(self.token).read_timeout(60).write_timeout(60).build()

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_likes_input))
        application.add_handler(CallbackQueryHandler(self.handle_like, pattern='like'))
        application.add_handler(CallbackQueryHandler(self.handle_touch, pattern='did_touch'))
        application.add_handler(CallbackQueryHandler(self.handle_touch, pattern='did_not_touch'))

        application.run_polling()

if __name__ == '__main__':
    token = 'token_robot'
    bot = LikeBot(token)
    bot.run()
