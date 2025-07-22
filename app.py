from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

app = Flask(__name__)
app.secret_key = 'clave_secreta_segura'
DATABASE = 'database.db'

# ------------------------ INICIALIZAR DB ------------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL UNIQUE,
            contrasena TEXT NOT NULL,
            red TEXT NOT NULL,
            wallet TEXT NOT NULL,
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
            fecha TEXT,
            aprobado INTEGER DEFAULT 0,
            tipo_moneda_real TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS retiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            monto REAL,
            fecha TEXT,
            procesado INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            contrasena TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS control (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retiros_habilitados INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
# ------------------------ UTILIDADES ------------------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def obtener_usuario_por_correo(correo):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM usuarios WHERE correo = ?', (correo,)).fetchone()
    conn.close()
    return user

def obtener_usuario_por_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM usuarios WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def calcular_saldo_por_moneda(usuario_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tipo_moneda_real, SUM(monto) 
        FROM depositos 
        WHERE usuario_id = ? AND aprobado = 1 
        GROUP BY tipo_moneda_real
    """, (usuario_id,))
    resultados = cursor.fetchall()
    saldos = {fila[0]: round(fila[1], 2) for fila in resultados if fila[0] is not None}
    conn.close()
    return saldos

def enviar_correo(destinatario, asunto, cuerpo):
    remitente = "referidocoins@gmail.com"
    password = "xxxxxxxx"  # Reemplaza con tu contraseña de aplicación

    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = asunto

    msg.attach(MIMEText(cuerpo, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        texto = msg.as_string()
        server.sendmail(remitente, destinatario, texto)
        server.quit()
        return True
    except Exception as e:
        print(f"Error al enviar correo: {e}")
        return False
# ------------------------ RUTAS DE USUARIO ------------------------

@app.route('/')
def index():
    return redirect(url_for('login'))

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

        # Verificar si ya existe
        existente = cursor.execute("SELECT * FROM usuarios WHERE correo = ?", (correo,)).fetchone()
        if existente:
            conn.close()
            return "El correo ya está registrado."

        codigo_referido = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        referido_por = None

        if referido:
            referido_user = cursor.execute("SELECT id FROM usuarios WHERE codigo_referido = ?", (referido,)).fetchone()
            if referido_user:
                referido_por = referido_user['id']

        cursor.execute("""
            INSERT INTO usuarios (nombre, correo, contrasena, red, wallet, referido, codigo_referido, referido_por)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (nombre, correo, contrasena, red, wallet, referido, codigo_referido, referido_por))

        conn.commit()
        conn.close()
        return redirect(url_for('login'))

    return render_template('registro.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        user = obtener_usuario_por_correo(correo)

        if user and check_password_hash(user['contrasena'], contrasena):
            session['usuario_id'] = user['id']
            return redirect(url_for('dashboard'))
        else:
            return "Credenciales inválidas"

    return render_template('login.html')


@app.route('/logout', endpoint='logout')
def logout_usuario():
    session.pop('usuario_id', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    usuario_id = session['usuario_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Datos del usuario
    user = cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()

    # Saldos por tipo de moneda
    saldo_monedas = cursor.execute("""
        SELECT tipo_moneda_real, SUM(monto) as total
        FROM depositos
        WHERE usuario_id = ? AND aprobado = 1
        GROUP BY tipo_moneda_real
    """, (usuario_id,)).fetchall()

    saldo_monedas_dict = {fila['tipo_moneda_real']: round(fila['total'], 2) for fila in saldo_monedas}

    # Ganancias (bonos)
    ganancias = round(user['bonos'], 2)

    # Referidos
    total_referidos = cursor.execute("SELECT COUNT(*) FROM usuarios WHERE referido_por = ?", (usuario_id,)).fetchone()[0]

    # Depósitos aprobados para historial y gráficos
    depositos = cursor.execute("""
        SELECT monto, tipo_moneda_real AS moneda, fecha
        FROM depositos
        WHERE usuario_id = ? AND aprobado = 1
        ORDER BY fecha DESC
    """, (usuario_id,)).fetchall()

    depositos_json = [{'monto': dep['monto'], 'fecha': dep['fecha']} for dep in depositos]

    # Retiros aprobados
    retiros = cursor.execute("""
        SELECT monto, fecha
        FROM retiros
        WHERE usuario_id = ? AND procesado = 1
        ORDER BY fecha DESC
    """, (usuario_id,)).fetchall()

    retiros_json = [{'monto': ret['monto'], 'fecha': ret['fecha']} for ret in retiros]

    conn.close()

    return render_template('dashboard.html',
                           nombre_usuario=user['nombre'],
                           codigo_referido=user['codigo_referido'],
                           saldo_monedas=saldo_monedas_dict,
                           ganancias=ganancias,
                           total_referidos=total_referidos,
                           depositos=depositos,
                           depositos_json=depositos_json,
                           retiros=retiros,
                           retiros_json=retiros_json)
@app.route('/depositar', methods=['POST'])
def depositar():
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'mensaje': 'No has iniciado sesión'})

    usuario_id = session['usuario_id']
    datos = request.get_json()
    monto = datos.get('monto')
    metodo = datos.get('metodo')

    if not monto or not metodo:
        return jsonify({'success': False, 'mensaje': 'Faltan datos del depósito'})

    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO depositos (usuario_id, monto, tipo_moneda_real, fecha, aprobado)
        VALUES (?, ?, ?, ?, 0)
    """, (usuario_id, monto, metodo, fecha))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'mensaje': 'Depósito registrado correctamente. Será verificado en breve.'})


@app.route('/retirar', methods=['POST'])
def retirar():
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'mensaje': 'No has iniciado sesión'})

    usuario_id = session['usuario_id']
    datos = request.get_json()
    monto = datos.get('monto')

    if not monto:
        return jsonify({'success': False, 'mensaje': 'Faltan datos del retiro'})

    if float(monto) < 10:
        return jsonify({'success': False, 'mensaje': 'El monto mínimo de retiro es $10'})

    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    cursor = conn.cursor()

    usuario = cursor.execute("SELECT bonos FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if not usuario or usuario['bonos'] < float(monto):
        conn.close()
        return jsonify({'success': False, 'mensaje': 'No tienes suficientes ganancias disponibles'})

    # Descontar de bonos
    cursor.execute("UPDATE usuarios SET bonos = bonos - ? WHERE id = ?", (monto, usuario_id))

    # Insertar solicitud de retiro
    cursor.execute("""
        INSERT INTO retiros (usuario_id, monto, fecha, procesado)
        VALUES (?, ?, ?, 0)
    """, (usuario_id, monto, fecha))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'mensaje': 'Solicitud de retiro enviada. Será revisada en breve.'})


@app.route('/recompensa_diaria', methods=['POST'])
def recompensa_diaria():
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'mensaje': 'No has iniciado sesión'})

    usuario_id = session['usuario_id']
    ahora = datetime.now()

    conn = get_db_connection()
    cursor = conn.cursor()

    ultima_fecha = cursor.execute("""
        SELECT ultima_recompensa FROM usuarios WHERE id = ?
    """, (usuario_id,)).fetchone()

    if ultima_fecha and ultima_fecha['ultima_recompensa']:
        ultima = datetime.strptime(ultima_fecha['ultima_recompensa'], '%Y-%m-%d %H:%M:%S')
        if (ahora - ultima).total_seconds() < 86400:
            conn.close()
            return jsonify({'success': False, 'mensaje': 'Debes esperar 24 horas para reclamar nuevamente'})

    # Calcular recompensa: 3% de inversión aprobada
    total_inversion = cursor.execute("""
        SELECT SUM(monto) as total FROM depositos WHERE usuario_id = ? AND aprobado = 1
    """, (usuario_id,)).fetchone()['total'] or 0

    recompensa = round(total_inversion * 0.03, 2)

    cursor.execute("UPDATE usuarios SET bonos = bonos + ?, ultima_recompensa = ? WHERE id = ?",
                   (recompensa, ahora.strftime('%Y-%m-%d %H:%M:%S'), usuario_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'mensaje': f'Recompensa de ${recompensa} acreditada correctamente'})
# ---------------- PANEL DE ADMINISTRACIÓN ----------------

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        if correo == 'admin@admin.com' and contrasena == 'admin123':
            session['admin'] = True
            return redirect('/admin_dashboard')
        else:
            return render_template('admin_login.html', mensaje='Credenciales inválidas')
    return render_template('admin_login.html')


@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin_login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Depósitos pendientes
    depositos = cursor.execute("""
        SELECT d.*, u.nombre FROM depositos d
        JOIN usuarios u ON d.usuario_id = u.id
        WHERE d.aprobado = 0
    """).fetchall()

    # Retiros pendientes
    retiros = cursor.execute("""
        SELECT r.*, u.nombre FROM retiros r
        JOIN usuarios u ON r.usuario_id = u.id
        WHERE r.procesado = 0
    """).fetchall()

    # Ver estado de retiros habilitados
    estado = cursor.execute("SELECT valor FROM configuracion WHERE clave = 'retiros_habilitados'").fetchone()
    habilitados = estado['valor'] == '1' if estado else False

    conn.close()
    return render_template('admin_dashboard.html', depositos=depositos, retiros=retiros, habilitados=habilitados)


@app.route('/aprobar_deposito/<int:id>', methods=['POST'])
def aprobar_deposito(id):
    if not session.get('admin'):
        return redirect('/admin_login')

    moneda = request.form.get('tipo_moneda_real')
    if not moneda:
        return 'Falta seleccionar tipo de moneda', 400

    conn = get_db_connection()
    cursor = conn.cursor()

    deposito = cursor.execute("SELECT * FROM depositos WHERE id = ?", (id,)).fetchone()
    if not deposito:
        conn.close()
        return 'Depósito no encontrado', 404

    cursor.execute("UPDATE depositos SET aprobado = 1, tipo_moneda_real = ? WHERE id = ?", (moneda, id))
    cursor.execute("UPDATE usuarios SET saldo = saldo + ?, fondos_depositados = fondos_depositados + ? WHERE id = ?",
                   (deposito['monto'], deposito['monto'], deposito['usuario_id']))
    conn.commit()
    conn.close()

    return redirect('/admin_dashboard')


@app.route('/procesar_retiro/<int:id>', methods=['POST'])
def procesar_retiro(id):
    if not session.get('admin'):
        return redirect('/admin_login')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE retiros SET procesado = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect('/admin_dashboard')


@app.route('/toggle_retiros', methods=['POST'])
def toggle_retiros():
    if not session.get('admin'):
        return redirect('/admin_login')

    conn = get_db_connection()
    cursor = conn.cursor()

    estado = cursor.execute("SELECT valor FROM configuracion WHERE clave = 'retiros_habilitados'").fetchone()
    nuevo_valor = '0' if estado and estado['valor'] == '1' else '1'

    if estado:
        cursor.execute("UPDATE configuracion SET valor = ? WHERE clave = 'retiros_habilitados'", (nuevo_valor,))
    else:
        cursor.execute("INSERT INTO configuracion (clave, valor) VALUES (?, ?)", ('retiros_habilitados', nuevo_valor))

    conn.commit()
    conn.close()

    return redirect('/admin_dashboard')
# ---------------------- LOGOUT ----------------------
@app.route('/admin_logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin_login')


# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    init_db()
    app.run()

