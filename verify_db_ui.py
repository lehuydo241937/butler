
from agent.db_manager import DBManager

def test_db_manager():
    db = DBManager("test_ui.db")
    
    # Test list_all_tables
    print("Testing list_all_tables...")
    tables = db.list_all_tables()
    print(f"Tables: {tables}")
    
    # Test execute_raw_query (DDL)
    print("\nTesting execute_raw_query (CREATE)...")
    res = db.execute_raw_query("CREATE TABLE IF NOT EXISTS test_table (id INTEGER, name TEXT)")
    print(f"Result: {res}")
    
    # Test list_all_tables again
    tables = db.list_all_tables()
    print(f"Tables after create: {tables}")
    assert "test_table" in tables
    
    # Test execute_raw_query (SELECT)
    print("\nTesting execute_raw_query (SELECT)...")
    res = db.execute_raw_query("SELECT name FROM sqlite_master")
    print(f"Result (first 2): {res['data'][:2]}")
    assert res["success"] == True
    
    print("\nAll DBManager tests passed!")

if __name__ == "__main__":
    try:
        test_db_manager()
    except Exception as e:
        print(f"Test failed: {e}")
    finally:
        import os
        if os.path.exists("test_ui.db"):
            os.remove("test_ui.db")
