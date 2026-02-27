import logging
import os
import asyncio
from datetime import datetime, timezone
from croniter import croniter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from langfuse import observe

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
        
        # Configure Langfuse early so the @observe decorator has keys
        ButlerAgent.configure_langfuse(self.secrets)

        self.agents = {} # chat_id -> ButlerAgent

    def get_agent(self, chat_id: int) -> ButlerAgent:
        if chat_id not in self.agents:
            # We use chat_id as a session_id or map it to one.
            session_id = f"telegram_{chat_id}"
            self.agents[chat_id] = ButlerAgent(session_id=session_id)
        return self.agents[chat_id]

    @observe()
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
        logging.info(f"Callback received: {data}")
        
        if data and data.startswith("hitl:"):
            try:
                parts = data.split(":")
                if len(parts) < 3:
                    logging.warning(f"Invalid callback data: {data}")
                    return
                    
                decision = parts[1]
                action_id = parts[2]
                
                chat_id = update.effective_chat.id
                agent = self.get_agent(chat_id)
                
                approved = (decision == "approve")
                success = agent.db.execute_action(action_id, approved=approved)
                
                if success:
                    status_text = f"Action {decision}d"
                    # Edit the button message immediately for feedback
                    await query.edit_message_text(text=f"{status_text}! 👍 (Wait a moment while I continue...)")
                    
                    # Notify agent about the outcome and get a follow-up reply
                    loop = asyncio.get_event_loop()
                    follow_up_prompt = f"[SYSTEM] The user has {decision}d action {action_id} via button click. Please acknowledge and proceed."
                    
                    try:
                        reply = await loop.run_in_executor(None, agent.chat, follow_up_prompt)
                        await context.bot.send_message(chat_id=chat_id, text=reply)
                    except Exception as e:
                        logging.error(f"Error in agent follow-up: {e}")
                        await context.bot.send_message(chat_id=chat_id, text="The action was successful, but I failed to generate a follow-up message.")
                else:
                    logging.warning(f"Action execution failed for {action_id}")
                    await query.edit_message_text(text="Failed to process action. It might have expired or been processed already.")
            except Exception as e:
                logging.error(f"Callback error: {e}")
                await query.edit_message_text(text="An error occurred while processing your decision.")

    async def check_background_tasks(self, context: ContextTypes.DEFAULT_TYPE):
        """Checks for due tasks and executes them."""
        # We need a db instance. We can get it from a dummy agent or instantiate DBManager directly.
        from agent.db_manager import DBManager
        from agent.protocol_runner import ProtocolRunner
        db = DBManager()
        
        active_tasks = db.get_active_tasks()
        active_protocols = db.get_active_protocols()
        now = datetime.now(timezone.utc)
        
        for task in active_tasks:
            task_id = task["id"]
            cron_expr = task["cron_expression"]
            last_run_str = task["last_run"]
            next_run_str = task["next_run"]
            chat_id = task["target_chat_id"]
            description = task["task_description"]
            
            # Calculate next run if not set
            if not next_run_str:
                iter = croniter(cron_expr, now)
                next_run = iter.get_next(datetime)
                db.update_task_run_times(task_id, datetime.fromtimestamp(0, timezone.utc), next_run)
                continue
            
            next_run = datetime.fromisoformat(next_run_str)
            if now >= next_run:
                logging.info(f"Executing background task {task_id}: {task['name']}")
                
                # Execute task
                agent = self.get_agent(chat_id)
                loop = asyncio.get_event_loop()
                
                # Generate a background-specific prompt
                bg_prompt = f"[BACKGROUND TASK] {description}\n\nPlease execute this task. If there is a result or notification for the user, provide it."
                
                try:
                    reply = await loop.run_in_executor(None, agent.chat, bg_prompt)
                    await context.bot.send_message(chat_id=chat_id, text=f"🔔 *Automated Task: {task['name']}*\n\n{reply}", parse_mode='Markdown')
                except Exception as e:
                    logging.error(f"Error executing task {task_id}: {e}")
                    await context.bot.send_message(chat_id=chat_id, text=f"❌ Error executing automated task '{task['name']}': {e}")
                
                # Update run times
                iter = croniter(cron_expr, now)
                new_next_run = iter.get_next(datetime)
                db.update_task_run_times(task_id, now, new_next_run)

        # ── Check Protocols ──────────────────────────────────────────────────
        for proto in active_protocols:
            proto_id = proto["id"]
            cron_expr = proto["cron_expression"]
            last_run_str = proto["last_run"]
            next_run_str = proto["next_run"]
            chat_id = proto["target_chat_id"]
            
            # Calculate next run if not set
            if not next_run_str:
                iter = croniter(cron_expr, now)
                next_run = iter.get_next(datetime)
                db.update_protocol_run_times(proto_id, datetime.fromtimestamp(0, timezone.utc), next_run)
                continue
            
            next_run = datetime.fromisoformat(next_run_str)
            if now >= next_run:
                logging.info(f"Executing protocol {proto_id}: {proto['name']}")
                
                agent = self.get_agent(chat_id)
                loop = asyncio.get_event_loop()
                
                try:
                    # Instantiate runner
                    runner = ProtocolRunner(
                        gemini_client=agent.client,
                        gemini_model=agent.model,
                        gmail_tools=agent.gmail,
                        secrets=agent.secrets,
                        telegram_bot=context.bot,
                    )
                    
                    # Run it in thread
                    await loop.run_in_executor(None, runner.run, proto, chat_id)
                    logging.info(f"Protocol '{proto['name']}' finished successfully.")
                except Exception as e:
                    logging.error(f"Error executing protocol {proto_id}: {e}")
                    await context.bot.send_message(
                        chat_id=chat_id, 
                        text=f"❌ Error executing protocol '{proto['name']}': {e}"
                    )
                
                # Update run times
                iter = croniter(cron_expr, now)
                new_next_run = iter.get_next(datetime)
                db.update_protocol_run_times(proto_id, now, new_next_run)

    def run(self):
        # Increased timeouts for slow networks
        builder = ApplicationBuilder().token(self.token)
        builder.read_timeout(60)
        builder.connect_timeout(60)
        
        # Optional proxy support
        proxy_url = os.getenv("TELEGRAM_PROXY")
        if proxy_url:
            logging.info(f"Using proxy: {proxy_url}")
            builder.proxy_url(proxy_url)
            builder.get_updates_proxy_url(proxy_url)

        application = builder.build()
        
        # Add background task checker job
        if application.job_queue:
            application.job_queue.run_repeating(self.check_background_tasks, interval=60, first=10)
        else:
            logging.error("JobQueue not available. Background tasks will not run.")
        
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
