import sqlite3

DB_PATH = r'C:\Users\woals\dev\classy-1\config\db.sqlite3'

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1. 빈 string phone → NULL
cur.execute("UPDATE accounts_user SET phone = NULL WHERE phone = ''")
print(f"Nulled empty strings: {cur.rowcount}")

# 2. 중복 phone 확인
cur.execute("""
    SELECT phone, COUNT(*) as cnt 
    FROM accounts_user 
    WHERE phone IS NOT NULL 
    GROUP BY phone 
    HAVING cnt > 1
""")
dupes = cur.fetchall()
print(f"Duplicate phone groups: {len(dupes)}")
for phone, cnt in dupes:
    print(f"  phone={phone!r}, count={cnt}")
    # 가장 오래된 ID 유지, 나머지 NULL
    cur.execute("SELECT id FROM accounts_user WHERE phone = ? ORDER BY id ASC", (phone,))
    ids = [row[0] for row in cur.fetchall()]
    for id_to_null in ids[1:]:
        cur.execute("UPDATE accounts_user SET phone = NULL WHERE id = ?", (id_to_null,))
        print(f"    -> Nulled user id={id_to_null}")

conn.commit()

# 3. 최종 확인
cur.execute("SELECT phone, COUNT(*) FROM accounts_user WHERE phone IS NOT NULL GROUP BY phone HAVING COUNT(*) > 1")
remaining = cur.fetchall()
print(f"\nRemaining duplicates: {len(remaining)}")

cur.execute("SELECT COUNT(*) FROM accounts_user WHERE phone IS NULL")
null_count = cur.fetchone()[0]
print(f"Users with NULL phone: {null_count}")

conn.close()
print("\nDone! Now run: .venv\\Scripts\\python.exe manage.py migrate")
