import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS recompensas (
    usuario_id INTEGER PRIMARY KEY,
    ultima_recompensa TEXT
)
''')

conn.commit()
conn.close()

print("Tabla 'recompensas' creada o ya existía.")
