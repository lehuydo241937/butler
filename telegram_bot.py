import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from agent.butler import ButlerAgent
from secrets_manager.redis_secrets import RedisSecretsManager

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class TelegramButler:
    def __init__(self):
        self.secrets = RedisSecretsManager()
        self.token = self.secrets.get_secret("telegram")
        
        if not self.token:
            raise ValueError("Telegram API key not found in Redis secrets.")
        
        self.agents = {} # chat_id -> ButlerAgent

    def get_agent(self, chat_id: int) -> ButlerAgent:
        if chat_id not in self.agents:
            # We use chat_id as a session_id or map it to one.
            session_id = f"telegram_{chat_id}"
            self.agents[chat_id] = ButlerAgent(session_id=session_id)
        return self.agents[chat_id]

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        user_text = update.message.text
        
        logging.info(f"Received message from {chat_id}: {user_text}")
        
        agent = self.get_agent(chat_id)
        
        # ButlerAgent.chat is synchronous, so we run it in a thread to avoid blocking the loop
        loop = asyncio.get_event_loop()
        reply = await loop.run_in_executor(None, agent.chat, user_text)
        
        # Check if the reply contains a HITL proposal
        if "HITL_PROPOSAL" in reply:
            try:
                # Format: HITL_PROPOSAL:type:action_id:message
                parts = reply.split(":", 3)
                if len(parts) >= 4:
                    action_id = parts[2]
                    display_text = parts[3]
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("Approve ✅", callback_data=f"hitl:approve:{action_id}"),
                            InlineKeyboardButton("Reject ❌", callback_data=f"hitl:reject:{action_id}")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(chat_id=chat_id, text=display_text, reply_markup=reply_markup)
                    return
            except Exception as e:
                logging.error(f"Error parsing HITL proposal: {e}")

        await context.bot.send_message(chat_id=chat_id, text=reply)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return
            
        await query.answer()
        
        data = query.data
        if data and data.startswith("hitl:"):
            try:
                _, decision, action_id = data.split(":")
                chat_id = update.effective_chat.id
                agent = self.get_agent(chat_id)
                
                approved = (decision == "approve")
                success = agent.db.execute_action(action_id, approved=approved)
                
                if success:
                    msg = f"Action {decision}d successfully! 👍"
                else:
                    msg = "Failed to process action. It might have expired or been processed already."
                
                await query.edit_message_text(text=msg)
                
                # Notify agent about the outcome
                agent.history.add_message(agent.session_id, "system", f"[HITL] Action {action_id} was {decision}d by user.")
            except Exception as e:
                logging.error(f"Callback error: {e}")
                await query.edit_message_text(text="An error occurred while processing your decision.")

    def run(self):
        application = ApplicationBuilder().token(self.token).build()
        
        message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message)
        callback_handler = CallbackQueryHandler(self.handle_callback)
        
        application.add_handler(message_handler)
        application.add_handler(callback_handler)
        
        logging.info("Telegram Bot started...")
        application.run_polling()

if __name__ == '__main__':
    try:
        bot = TelegramButler()
        bot.run()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
