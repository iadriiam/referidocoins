import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()
c.execute("ALTER TABLE usuarios ADD COLUMN referido_por TEXT")
conn.commit()
conn.close()

print("✅ Columna 'referido_por' agregada.")
