import sqlite3

DB_PATH = 'database.db'

def actualizar_saldo(user_id, monto):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT nombre, saldo FROM usuarios WHERE id = ?', (user_id,))
    user = c.fetchone()

    if not user:
        print(f"❌ Usuario con ID {user_id} no encontrado.")
        conn.close()
        return

    nombre, saldo_actual = user
    print(f"\nUsuario: {nombre}")
    print(f"Saldo actual: ${saldo_actual:.2f}")
    print(f"Monto a agregar: ${monto:.2f}")

    confirm = input("¿Confirmar actualización? (s/n): ").lower()
    if confirm != 's':
        print("🚫 Operación cancelada.")
        conn.close()
        return

    nuevo_saldo = saldo_actual + monto
    c.execute('UPDATE usuarios SET saldo = ? WHERE id = ?', (nuevo_saldo, user_id))
    conn.commit()
    conn.close()

    print(f"✅ Saldo actualizado con éxito. Nuevo saldo: ${nuevo_saldo:.2f}")

if __name__ == "__main__":
    try:
        user_id = int(input("🔎 Ingresa el ID del usuario: "))
        monto = float(input("💵 Ingresa el monto a agregar: "))
        actualizar_saldo(user_id, monto)
    except Exception as e:
        print("⚠️ Error:", e)
