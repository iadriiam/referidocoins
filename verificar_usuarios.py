import sqlite3

DB_PATH = 'database.db'

def verificar_usuarios():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('SELECT id, nombre, correo, saldo, bonos, codigo_referido, referido_por FROM usuarios')
    usuarios = c.fetchall()

    print("\n📋 Estado actual de usuarios:\n")
    for u in usuarios:
        id_usuario = u[0]
        nombre = u[1]
        correo = u[2]
        saldo = u[3]
        bonos = u[4]
        codigo_referido = u[5]
        referido_por = u[6]

        print(f"🧑 ID: {id_usuario}")
        print(f"   Nombre: {nombre}")
        print(f"   Correo: {correo}")
        print(f"   Saldo: ${saldo:.2f}")
        print(f"   Bonos: ${bonos:.2f}")
        print(f"   Código de referido: {codigo_referido}")
        print(f"   Referido por ID: {referido_por}\n")

    conn.close()

if __name__ == "__main__":
    verificar_usuarios()
