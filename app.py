from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta'

# Configuración del correo
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'tucorreo@gmail.com'
app.config['MAIL_PASSWORD'] = 'tu_contraseña'
mail = Mail(app)

# ---------------------- BASE DE DATOS ----------------------

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL UNIQUE,
            contrasena TEXT NOT NULL,
            red TEXT,
            wallet TEXT,
            referido TEXT,
            saldo REAL DEFAULT 0,
            bonos REAL DEFAULT 0,
            fondos_depositados REAL DEFAULT 0,
            codigo_referido TEXT,
            referido_por INTEGER,
            ultima_recompensa TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS depositos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            monto REAL,
            moneda TEXT,
            estado TEXT,
            fecha TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS retiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            monto REAL,
            estado TEXT,
            fecha TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            contrasena TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS control (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retiros_habilitados INTEGER DEFAULT 1
        )
        """)
# ---------------------- UTILIDADES ----------------------

def obtener_usuario(correo):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM usuarios WHERE correo = ?", (correo,)).fetchone()
    conn.close()
    return user

def obtener_saldo_por_moneda(usuario_id):
    conn = get_db_connection()
    depositos = conn.execute("SELECT moneda, SUM(monto) as total FROM depositos WHERE usuario_id = ? AND estado = 'Aprobado' GROUP BY moneda", (usuario_id,)).fetchall()
    conn.close()
    saldos = {}
    for fila in depositos:
        saldos[fila["moneda"]] = round(fila["total"], 2)
    return saldos

# ---------------------- REGISTRO ----------------------

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        contrasena = generate_password_hash(request.form['contrasena'])
        red = request.form['red']
        wallet = request.form['wallet']
        referido = request.form.get('referido')

        conn = get_db_connection()
        cursor = conn.cursor()

        codigo_referido = nombre[:3].upper() + str(datetime.now().timestamp()).replace('.', '')[-4:]

        referido_por = None
        if referido:
            ref = cursor.execute("SELECT id FROM usuarios WHERE codigo_referido = ?", (referido,)).fetchone()
            if ref:
                referido_por = ref["id"]

        cursor.execute("""INSERT INTO usuarios (nombre, correo, contrasena, red, wallet, referido, codigo_referido, referido_por)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (nombre, correo, contrasena, red, wallet, referido, codigo_referido, referido_por))

        conn.commit()
        conn.close()
        return redirect('/login')

    return render_template('registro.html')
# ---------------------- LOGIN ----------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']

        user = obtener_usuario(correo)

        if user and check_password_hash(user["contrasena"], contrasena):
            session['usuario'] = user["id"]
            return redirect('/dashboard')
        else:
            return render_template('login.html', error='Correo o contraseña incorrectos.')

    return render_template('login.html')

# ---------------------- DASHBOARD ----------------------

@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect('/login')

    usuario_id = session['usuario']
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()

    depositos = conn.execute("SELECT monto, moneda, fecha FROM depositos WHERE usuario_id = ? AND estado = 'Aprobado'", (usuario_id,)).fetchall()
    retiros = conn.execute("SELECT monto, fecha FROM retiros WHERE usuario_id = ? AND estado = 'Procesado'", (usuario_id,)).fetchall()

    total_referidos = conn.execute("SELECT COUNT(*) as total FROM usuarios WHERE referido_por = ?", (usuario_id,)).fetchone()["total"]

    depositos_json = [{"fecha": d["fecha"], "monto": float(d["monto"])} for d in depositos]
    retiros_json = [{"fecha": r["fecha"], "monto": float(r["monto"])} for r in retiros]

    saldo_monedas = obtener_saldo_por_moneda(usuario_id)

    conn.close()

    return render_template("dashboard.html",
                           nombre_usuario=user["nombre"],
                           codigo_referido=user["codigo_referido"],
                           total_referidos=total_referidos,
                           saldo_monedas=saldo_monedas,
                           ganancias=round(user["bonos"], 2),
                           depositos=depositos,
                           retiros=retiros,
                           depositos_json=depositos_json,
                           retiros_json=retiros_json)
# ---------------------- DEPOSITAR ----------------------

@app.route('/depositar', methods=['POST'])
def depositar():
    if 'usuario' not in session:
        return jsonify({'mensaje': 'No autenticado'}), 401

    data = request.json
    monto = float(data.get('monto', 0))
    metodo = data.get('metodo', '')

    if monto <= 0 or not metodo:
        return jsonify({'mensaje': 'Faltan datos del depósito'}), 400

    usuario_id = session['usuario']
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db_connection()
    conn.execute("INSERT INTO depositos (usuario_id, monto, moneda, estado, fecha) VALUES (?, ?, ?, ?, ?)",
                 (usuario_id, monto, metodo, 'Pendiente', fecha))
    conn.commit()
    conn.close()

    return jsonify({'mensaje': 'Depósito registrado con éxito. Será acreditado en 24 horas.'})

# ---------------------- RETIRAR ----------------------

@app.route('/retirar', methods=['POST'])
def retirar():
    if 'usuario' not in session:
        return jsonify({'mensaje': 'No autenticado'}), 401

    data = request.json
    monto = float(data.get('monto', 0))

    if monto < 10:
        return jsonify({'mensaje': 'El monto mínimo de retiro es $10'}), 400

    usuario_id = session['usuario']
    conn = get_db_connection()

    usuario = conn.execute("SELECT bonos FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    bonos = usuario["bonos"]

    retiros_habilitados = conn.execute("SELECT valor FROM configuracion WHERE clave = 'retiros_habilitados'").fetchone()
    if not retiros_habilitados or retiros_habilitados["valor"] != '1':
        conn.close()
        return jsonify({'mensaje': 'Los retiros no están habilitados por el administrador.'}), 403

    if monto > bonos:
        conn.close()
        return jsonify({'mensaje': 'No tienes suficientes ganancias para retirar'}), 400

    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("INSERT INTO retiros (usuario_id, monto, estado, fecha) VALUES (?, ?, ?, ?)",
                 (usuario_id, monto, 'Pendiente', fecha))
    conn.commit()
    conn.close()

    return jsonify({'mensaje': 'Solicitud de retiro enviada. Será procesada en breve.'})

# ---------------------- RECOMPENSA DIARIA ----------------------

@app.route('/recompensa', methods=['POST'])
def recompensa_diaria():
    if 'usuario' not in session:
        return jsonify({'mensaje': 'No autenticado'}), 401

    usuario_id = session['usuario']
    conn = get_db_connection()

    ultima = conn.execute("SELECT fecha FROM recompensas WHERE usuario_id = ? ORDER BY fecha DESC LIMIT 1", (usuario_id,)).fetchone()
    ahora = datetime.now()

    if ultima:
        ultima_fecha = datetime.strptime(ultima["fecha"], '%Y-%m-%d %H:%M:%S')
        diferencia = ahora - ultima_fecha
        if diferencia.total_seconds() < 86400:
            restante = int((86400 - diferencia.total_seconds()) // 3600)
            conn.close()
            return jsonify({'mensaje': f'Espera {restante}h para reclamar tu recompensa.'}), 400

    user = conn.execute("SELECT fondos_depositados FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    inversion = user["fondos_depositados"]
    recompensa = round(inversion * 0.03, 2)

    conn.execute("UPDATE usuarios SET saldo = saldo + ?, bonos = bonos + ? WHERE id = ?", (recompensa, recompensa, usuario_id))
    conn.execute("INSERT INTO recompensas (usuario_id, fecha) VALUES (?, ?)", (usuario_id, ahora.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

    return jsonify({'mensaje': f'¡Has recibido ${recompensa} como recompensa diaria!'})
# ---------------------- LOGIN ADMIN ----------------------

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']

        if correo == 'admin@admin.com' and contrasena == 'admin123':
            session['admin'] = True
            return redirect('/admin_dashboard')
        else:
            return render_template('admin_login.html', error='Credenciales inválidas')

    return render_template('admin_login.html')

# ---------------------- DASHBOARD ADMIN ----------------------

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin_login')

    conn = get_db_connection()
    depositos = conn.execute("SELECT d.id, u.nombre, d.monto, d.moneda, d.estado, d.fecha FROM depositos d JOIN usuarios u ON d.usuario_id = u.id WHERE d.estado = 'Pendiente'").fetchall()
    retiros = conn.execute("SELECT r.id, u.nombre, r.monto, r.estado, r.fecha FROM retiros r JOIN usuarios u ON r.usuario_id = u.id WHERE r.estado = 'Pendiente'").fetchall()
    retiros_habilitados = conn.execute("SELECT valor FROM configuracion WHERE clave = 'retiros_habilitados'").fetchone()
    conn.close()

    return render_template('admin_dashboard.html', depositos=depositos, retiros=retiros, retiros_habilitados=retiros_habilitados["valor"] == '1')

# ---------------------- CONFIRMAR DEPÓSITO ----------------------

@app.route('/confirmar_deposito/<int:deposito_id>', methods=['POST'])
def confirmar_deposito(deposito_id):
    if not session.get('admin'):
        return redirect('/admin_login')

    tipo_moneda_real = request.form.get('tipo_moneda_real')

    conn = get_db_connection()
    deposito = conn.execute("SELECT usuario_id, monto FROM depositos WHERE id = ?", (deposito_id,)).fetchone()

    if deposito:
        conn.execute("UPDATE depositos SET estado = 'Aprobado' WHERE id = ?", (deposito_id,))
        conn.execute("UPDATE usuarios SET saldo = saldo + ?, fondos_depositados = fondos_depositados + ? WHERE id = ?",
                     (deposito["monto"], deposito["monto"], deposito["usuario_id"]))
        conn.execute("INSERT INTO saldos_monedas (usuario_id, moneda, cantidad) VALUES (?, ?, ?) ON CONFLICT(usuario_id, moneda) DO UPDATE SET cantidad = cantidad + ?",
                     (deposito["usuario_id"], tipo_moneda_real, deposito["monto"], deposito["monto"]))
        conn.commit()

    conn.close()
    return redirect('/admin_dashboard')

# ---------------------- CONFIRMAR RETIRO ----------------------

@app.route('/confirmar_retiro/<int:retiro_id>', methods=['POST'])
def confirmar_retiro(retiro_id):
    if not session.get('admin'):
        return redirect('/admin_login')

    conn = get_db_connection()
    retiro = conn.execute("SELECT usuario_id, monto FROM retiros WHERE id = ?", (retiro_id,)).fetchone()

    if retiro:
        conn.execute("UPDATE retiros SET estado = 'Procesado' WHERE id = ?", (retiro_id,))
        conn.execute("UPDATE usuarios SET bonos = bonos - ? WHERE id = ?", (retiro["monto"], retiro["usuario_id"]))
        conn.commit()

    conn.close()
    return redirect('/admin_dashboard')

# ---------------------- TOGGLE RETIROS ----------------------

@app.route('/toggle_retiros', methods=['POST'])
def toggle_retiros():
    if not session.get('admin'):
        return redirect('/admin_login')

    estado_actual = request.form.get('estado')
    nuevo_estado = '1' if estado_actual == '0' else '0'

    conn = get_db_connection()
    conn.execute("UPDATE configuracion SET valor = ? WHERE clave = 'retiros_habilitados'", (nuevo_estado,))
    conn.commit()
    conn.close()

    return redirect('/admin_dashboard')
# ---------------------- LOGOUT USUARIO ----------------------
@app.route('/logout')
def logout_usuario():
    session.pop('usuario', None)
    return redirect('/login')


# ---------------------- LOGOUT ADMIN ----------------------
@app.route('/admin_logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin_login')


# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    init_db()
    app.run()

