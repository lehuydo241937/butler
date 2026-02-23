import os
from datetime import datetime, timedelta
from agent.butler import ButlerAgent
from chat_history import RedisChatHistory
from dotenv import load_dotenv

load_dotenv()

def verify():
    print("--- Verifying Daily Context & Summaries ---")
    
    # 1. Setup
    history = RedisChatHistory()
    agent = ButlerAgent(history=history)
    sid = agent.session_id
    print(f"Session ID: {sid}")

    # 2. Test Time Filtering
    # Manually add an "old" message
    yesterday_iso = (datetime.now() - timedelta(days=1)).isoformat()
    history.add_message(sid, "user", "I am a message from yesterday", extra={"timestamp": yesterday_iso})
    
    # Add a "today" message
    history.add_message(sid, "user", "I am a message from today")
    
    # Check filtering
    today_start = datetime.now().strftime("%Y-%m-%dT00:00:00")
    filtered = history.get_history_by_time_range(sid, today_start)
    
    print(f"Total messages in Redis: {len(history.get_history(sid))}")
    print(f"Messages from today: {len(filtered)}")
    
    if any("yesterday" in m["content"] for m in filtered):
        print("[FAIL] Time filtering did not exclude yesterday's message.")
    else:
        print("[OK] Time filtering works.")

    # 3. Test Summary Tools
    day_str = datetime.now().strftime("%Y-%m-%d")
    summary_text = "Today we implemented daily context filtering and summaries."
    
    print(f"Storing summary for {day_str}...")
    res = agent.store_daily_summary(day_str, summary_text)
    print(res)
    
    retrieved = agent.get_daily_summary(day_str)
    print(f"Retrieved: {retrieved}")
    
    if retrieved == summary_text:
        print("[OK] Summary persistence works.")
    else:
        print("[FAIL] Summary retrieval failed or mismatch.")

if __name__ == "__main__":
    verify()
