import sqlite3

def agregar_columna_si_no_existe(cursor, tabla, columna, tipo_sql):
    cursor.execute(f"PRAGMA table_info({tabla})")
    columnas_existentes = [col[1] for col in cursor.fetchall()]
    if columna not in columnas_existentes:
        print(f"➕ Agregando columna '{columna}' a la tabla '{tabla}'...")
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo_sql}")
    else:
        print(f"✅ La columna '{columna}' ya existe en '{tabla}'.")

def corregir_tabla_usuarios():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Verificar y agregar columnas necesarias
    columnas_necesarias = {
        "fondos_depositados": "REAL DEFAULT 0",
        "referido_por": "INTEGER",
        "bonos": "REAL DEFAULT 15"
    }

    for columna, tipo_sql in columnas_necesarias.items():
        agregar_columna_si_no_existe(c, "usuarios", columna, tipo_sql)

    conn.commit()
    conn.close()
    print("✅ Esquema corregido exitosamente.")

if __name__ == "__main__":
    corregir_tabla_usuarios()
