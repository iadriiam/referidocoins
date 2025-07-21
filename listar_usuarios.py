import sqlite3
import csv
from tabulate import tabulate

DB_PATH = 'database.db'

def columnas_extras_existentes():
    """Verifica si las columnas 'saldo' y 'bonos' existen en la tabla usuarios."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(usuarios)")
    columnas = [col[1] for col in c.fetchall()]
    conn.close()
    return 'saldo' in columnas and 'bonos' in columnas

def obtener_usuarios():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if columnas_extras_existentes():
            c.execute('SELECT id, nombre, correo, red, wallet, referido, saldo, bonos FROM usuarios')
        else:
            c.execute('SELECT id, nombre, correo, red, wallet, referido FROM usuarios')

        usuarios = c.fetchall()
        conn.close()
        return usuarios
    except sqlite3.Error as e:
        print(f"❌ Error al conectar con la base de datos: {e}")
        return []

def mostrar_usuarios(usuarios):
    if not usuarios:
        print("⚠️ No hay usuarios registrados.\n")
        return

    tiene_saldo = len(usuarios[0]) > 6

    headers = ["ID", "Nombre", "Correo", "Red", "Wallet", "Referido"]
    if tiene_saldo:
        headers += ["Saldo (USDT)", "Bonos (USDT)"]

    print("\n📋 Usuarios registrados:\n")
    print(tabulate(usuarios, headers=headers, tablefmt="grid", stralign="center"))

    total_usuarios = len(usuarios)
    print(f"\n👤 Total de usuarios: {total_usuarios}")

    if tiene_saldo:
        total_saldo = sum(u[6] for u in usuarios)
        total_bonos = sum(u[7] for u in usuarios)
        print(f"💰 Saldo total disponible: ${total_saldo:.2f} USDT")
        print(f"🎁 Total de bonos acumulados: ${total_bonos:.2f} USDT")

    # Conteo por red
    redes = {}
    for u in usuarios:
        red = u[3]
        redes[red] = redes.get(red, 0) + 1

    print("\n🔗 Usuarios por red:")
    for red, cantidad in redes.items():
        print(f"   • {red}: {cantidad}")

    print()

def exportar_a_csv(usuarios, archivo="usuarios_exportados.csv"):
    if not usuarios:
        print("⚠️ No hay usuarios para exportar.\n")
        return

    tiene_saldo = len(usuarios[0]) > 6

    with open(archivo, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        headers = ["ID", "Nombre", "Correo", "Red", "Wallet", "Referido"]
        if tiene_saldo:
            headers += ["Saldo", "Bonos"]
        writer.writerow(headers)
        writer.writerows(usuarios)

    print(f"✅ Usuarios exportados exitosamente a '{archivo}'\n")

if __name__ == "__main__":
    usuarios = obtener_usuarios()
    mostrar_usuarios(usuarios)
    exportar_a_csv(usuarios)

