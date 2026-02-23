import asyncio
import logging
from datetime import datetime, timezone
from agent.db_manager import DBManager
from telegram_bot import TelegramButler
from unittest.mock import MagicMock, AsyncMock

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_background_tasks():
    db = DBManager()
    
    # 1. Add a test task that runs every minute
    task_name = "Test Task"
    task_desc = "Say hello and tell me the current time."
    cron_expr = "* * * * *" # Every minute
    chat_id = 123456789 # Dummy chat ID
    
    logging.info(f"Adding test task: {task_name}")
    db.add_background_task(task_name, task_desc, cron_expr, chat_id)
    
    # 2. Instantiate TelegramButler (mocking dependencies)
    bot = TelegramButler()
    bot.get_agent = MagicMock()
    mock_agent = MagicMock()
    bot.get_agent.return_value = mock_agent
    mock_agent.chat = MagicMock(return_value="Hello! The current time is " + datetime.now().isoformat())
    
    # 3. Create a mock context for JobQueue
    mock_context = MagicMock()
    mock_context.bot = AsyncMock()
    
    # 4. Run the check_background_tasks once
    logging.info("Running check_background_tasks...")
    await bot.check_background_tasks(mock_context)
    
    # 5. Verify that the agent was called and message was "sent"
    # Actually, the first run will only set next_run if it was None.
    # Let's check the database.
    tasks = db.get_active_tasks()
    test_task = next(t for t in tasks if t["name"] == task_name)
    
    logging.info(f"Task next_run after 1st check: {test_task['next_run']}")
    
    if test_task["next_run"]:
        logging.info("Step 1 PASSED: next_run initialized.")
    else:
        logging.error("Step 1 FAILED: next_run not initialized.")
        return

    # 6. Manually set next_run to the past to trigger execution
    from datetime import timedelta
    past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.update_task_run_times(test_task["id"], datetime.fromtimestamp(0, timezone.utc), past_time)
    
    logging.info("Running check_background_tasks again with past next_run...")
    await bot.check_background_tasks(mock_context)
    
    # 7. Check if agent.chat was called
    if mock_agent.chat.called:
        logging.info("Step 2 PASSED: agent.chat was called for the due task.")
        sent_args = mock_context.bot.send_message.call_args_list
        if sent_args:
             logging.info(f"Step 3 PASSED: send_message was called with: {sent_args[0]}")
        else:
             logging.error("Step 3 FAILED: send_message was NOT called.")
    else:
        logging.error("Step 2 FAILED: agent.chat was NOT called.")

if __name__ == "__main__":
    asyncio.run(test_background_tasks())
