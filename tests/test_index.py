
import os
import sys

# Add current directory to path so we can import agent modules
sys.path.append(os.getcwd())

from agent.butler import ButlerAgent

def test_index():
    try:
        print("Initializing ButlerAgent...")
        agent = ButlerAgent()
        
        print("Starting index of 5 recent emails...")
        result = agent.index_recent_emails(count=5)
        print(f"Index result: {result}")
        
    except Exception as e:
        print(f"Error during indexing test: {e}")

if __name__ == "__main__":
    test_index()
