
import os
import sys

sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')

from agent.butler import ButlerAgent

def test_semantic_search():
    try:
        agent = ButlerAgent()
        
        print("Testing semantic search for 'Adecco'...")
        result = agent.semantic_search_emails(query="Adecco", limit=2)
        print("--- Search Result ---")
        print(result)
        print("---------------------")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_semantic_search()
