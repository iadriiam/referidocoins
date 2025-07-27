from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_super_segura'

# ----------------------------- INICIALIZACIÓN DB -----------------------------
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL UNIQUE,
            contrasena TEXT NOT NULL,
            referido TEXT,
            saldo REAL DEFAULT 0,
            bonos REAL DEFAULT 0,
            fondos_depositados REAL DEFAULT 0,
            codigo_referido TEXT,
            referido_por INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS retiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            monto REAL NOT NULL,
            fecha TEXT NOT NULL,
            procesado INTEGER DEFAULT 0,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS depositos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            monto REAL NOT NULL,
            moneda TEXT NOT NULL,
            fecha TEXT NOT NULL,
            confirmado INTEGER DEFAULT 0,
            tipo_moneda_real TEXT,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')

    c.execute("SELECT * FROM configuracion WHERE clave = 'retiros_habilitados'")
    if not c.fetchone():
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('retiros_habilitados', '0')")

    try:
        c.execute("ALTER TABLE depositos ADD COLUMN tipo_moneda_real TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

init_db()
# ----------------------------- FUNCIONES AUX -----------------------------
def generar_codigo_referido():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def enviar_correo(destinatario, asunto, mensaje_html):
    remitente = "tucorreo@gmail.com"
    password = "tu_contraseña_de_app"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = destinatario

    parte_html = MIMEText(mensaje_html, "html")
    msg.attach(parte_html)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(remitente, password)
            server.sendmail(remitente, destinatario, msg.as_string())
        print("✅ Correo enviado a", destinatario)
    except Exception as e:
        print("❌ Error al enviar correo:", e)

def retiros_estan_habilitados():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT valor FROM configuracion WHERE clave = 'retiros_habilitados'")
    estado = c.fetchone()
    conn.close()
    return estado and estado[0] == '1'

def alternar_estado_retiros():
    nuevo_estado = '0' if retiros_estan_habilitados() else '1'
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE configuracion SET valor = ? WHERE clave = 'retiros_habilitados'", (nuevo_estado,))
    conn.commit()
    conn.close()

# ---------------------- RECOMPENSA DIARIA ----------------------

@app.route('/recompensa', methods=['POST'])
def recompensa_diaria():
    if 'user_id' not in session:
        return jsonify({'mensaje': 'No autenticado'}), 401

    usuario_id = session['user_id']
    conn = sqlite3.connect('database.db')

    ultima = conn.execute("SELECT fecha FROM recompensas WHERE usuario_id = ? ORDER BY fecha DESC LIMIT 1", (usuario_id,)).fetchone()
    ahora = datetime.now()

    if ultima:
        ultima_fecha = datetime.strptime(ultima[0], '%Y-%m-%d %H:%M:%S')
        diferencia = ahora - ultima_fecha
        if diferencia.total_seconds() < 86400:
            restante = int((86400 - diferencia.total_seconds()) // 3600)
            conn.close()
            return jsonify({'mensaje': f'Espera {restante}h para reclamar tu recompensa.'}), 400

    user = conn.execute("SELECT fondos_depositados FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    inversion = user[0]
    recompensa = round(inversion * 0.03, 2)

    conn.execute("UPDATE usuarios SET saldo = saldo + ?, bonos = bonos + ? WHERE id = ?", (recompensa, recompensa, usuario_id))
    conn.execute("INSERT INTO recompensas (usuario_id, fecha) VALUES (?, ?)", (usuario_id, ahora.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

    return jsonify({'mensaje': f'¡Has recibido ${recompensa} como recompensa diaria!', 'recompensa': recompensa})

# ----------------------------- RUTAS -----------------------------
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/registro', methods=['POST', 'GET'])
def procesar_registro():
    if request.method == 'GET':
        return render_template('registro.html')
    
    if request.content_type == 'application/json':
        data = request.get_json()
        campos = ['nombre', 'correo', 'contrasena']
        if not all(data.get(c) for c in campos):
            return jsonify({'mensaje': 'Faltan campos obligatorios'}), 400

        hashed_password = generate_password_hash(data['contrasena'])
        codigo_referido = generar_codigo_referido()
        referido_por_id = None

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Verificar si ya existe el correo
        c.execute('SELECT id FROM usuarios WHERE correo = ?', (data['correo'],))
        if c.fetchone():
            conn.close()
            return jsonify({'mensaje': 'Correo ya registrado'}), 400

        # Verificar referido
        if data.get('referido'):
            c.execute('SELECT id FROM usuarios WHERE codigo_referido = ?', (data['referido'],))
            ref = c.fetchone()
            if ref:
                referido_por_id = ref[0]

        # Insertar nuevo usuario
        c.execute('''
            INSERT INTO usuarios (nombre, correo, contrasena, referido, codigo_referido, referido_por, saldo, bonos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['nombre'],
            data['correo'],
            hashed_password,
            data.get('referido'),
            codigo_referido,
            referido_por_id,
            0,
            0
        ))

        if referido_por_id:
            c.execute('UPDATE usuarios SET saldo = saldo + 5, bonos = bonos + 5 WHERE id = ?', (referido_por_id,))

        conn.commit()
        conn.close()

        mensaje_html = f"""
        <h3>¡Hola, {data['nombre']}!</h3>
        <p>Gracias por registrarte en Referido Coins.</p>
        <p>¡Listo para invertir!</p>
        """
        enviar_correo(data['correo'], "Registro exitoso", mensaje_html)
        return jsonify({'mensaje': f'¡Usuario {data["nombre"]} registrado exitosamente!'}), 200

    return jsonify({'mensaje': 'Formato no soportado. Usa Content-Type: application/json'}), 415


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return render_template('login.html')

    data = request.get_json()
    correo = data.get('correo')
    contrasena = data.get('contrasena')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT id, nombre, contrasena FROM usuarios WHERE correo = ?', (correo,))
    usuario = c.fetchone()
    conn.close()

    if usuario and check_password_hash(usuario[2], contrasena):
        session['user_id'] = usuario[0]
        session['user_nombre'] = usuario[1]
        return jsonify({'mensaje': 'Login exitoso'}), 200
    else:
        return jsonify({'mensaje': 'Correo o contraseña incorrectos'}), 401
    
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Datos del usuario
    c.execute('SELECT saldo, bonos, codigo_referido, fondos_depositados FROM usuarios WHERE id = ?', (session['user_id'],))
    datos = c.fetchone()
    saldo, bonos, codigo_referido, fondos = datos
    ganancias = saldo - fondos if saldo > fondos else 0

    # Códigos y referidos
    c.execute('SELECT COUNT(*) FROM usuarios WHERE referido_por = ?', (session['user_id'],))
    total_referidos = c.fetchone()[0]

    # Historial de depósitos y retiros
    c.execute('SELECT monto, moneda, fecha FROM depositos WHERE usuario_id = ?', (session['user_id'],))
    depositos = [dict(monto=row[0], moneda=row[1], fecha=row[2]) for row in c.fetchall()]

    c.execute('SELECT monto, fecha FROM retiros WHERE usuario_id = ?', (session['user_id'],))
    retiros = [dict(monto=row[0], fecha=row[1]) for row in c.fetchall()]

    # Saldo desglosado por moneda real
    c.execute('''
        SELECT tipo_moneda_real, SUM(monto)
        FROM depositos
        WHERE usuario_id = ? AND confirmado = 1 AND tipo_moneda_real IS NOT NULL
        GROUP BY tipo_moneda_real
    ''', (session['user_id'],))
    resultados = c.fetchall()

    saldo_monedas = {row[0]: round(row[1], 2) for row in resultados} if resultados else {}

    conn.close()

    return render_template(
        'dashboard.html',
        nombre_usuario=session['user_nombre'],
        fondos=saldo,
        saldo_disponible=saldo,
        ganancias=ganancias,
        codigo_referido=codigo_referido,
        total_referidos=total_referidos,
        depositos=depositos,
        retiros=retiros,
        depositos_json=depositos,
        retiros_json=retiros,
        saldo_monedas=saldo_monedas  # 👈 esto es lo que faltaba
    )


@app.route('/depositar', methods=['POST'])
def depositar():
    if 'user_id' not in session:
        return jsonify({'mensaje': 'No autorizado'}), 401

    data = request.get_json()
    monto = data.get('monto')
    moneda = data.get('moneda')

    if not monto or not moneda:
        return jsonify({'mensaje': 'Faltan datos del depósito'}), 400

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('INSERT INTO depositos (usuario_id, monto, moneda, fecha) VALUES (?, ?, ?, ?)', 
              (session['user_id'], monto, moneda, fecha))
    conn.commit()
    conn.close()

    return jsonify({'mensaje': '✅ Depósito registrado. Será confirmado por el administrador en las próximas 24 horas'}), 200

@app.route('/retiro', methods=['POST'])
def retiro():
    if 'user_id' not in session:
        return jsonify({'mensaje': 'No autorizado'}), 401

    if not retiros_estan_habilitados():
        return jsonify({'mensaje': 'Los retiros están temporalmente deshabilitados'}), 403

    data = request.get_json()
    monto = data.get('monto')
    tipo_cuenta = data.get('tipo_cuenta')
    cuenta_destino = data.get('cuenta_destino')

    if not tipo_cuenta or not cuenta_destino:
        return jsonify({'mensaje': 'Faltan datos de la cuenta de retiro'}), 400

    try:
        monto = float(monto)
    except (TypeError, ValueError):
        return jsonify({'mensaje': 'Monto inválido'}), 400

    if monto < 10:
        return jsonify({'mensaje': 'El monto mínimo de retiro es $10'}), 400

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT saldo, fondos_depositados FROM usuarios WHERE id = ?', (session['user_id'],))
    actual = c.fetchone()
    saldo_actual, fondos = actual
    ganancias = saldo_actual - fondos if saldo_actual > fondos else 0

    if monto > ganancias:
        conn.close()
        return jsonify({'mensaje': 'Solo puedes retirar tus ganancias. El monto supera tus ganancias disponibles'}), 400

    nuevo_saldo = saldo_actual - monto
    c.execute('UPDATE usuarios SET saldo = ? WHERE id = ?', (nuevo_saldo, session['user_id']))
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('INSERT INTO retiros (usuario_id, monto, fecha, cuenta, tipo_cuenta) VALUES (?, ?, ?, ?, ?)', (session['user_id'], monto, fecha, cuenta_destino, tipo_cuenta))

    conn.commit()
    conn.close()

    return jsonify({'mensaje': '✅ Retiro procesado con éxito', 'nuevo_saldo': f"{nuevo_saldo:.2f}"}), 200

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'GET':
        if 'admin_logged' in session:
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html')

    username = request.form.get('username')
    password = request.form.get('password')

    if username == 'shanks' and password == 'akagamiarmless':
        session['admin_logged'] = True
        return redirect(url_for('admin_dashboard'))
    else:
        return render_template('admin_login.html', error='Credenciales incorrectas')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_logged' not in session:
        return redirect(url_for('admin'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''
        SELECT r.id, u.nombre,
               r.cuenta, r.tipo_cuenta,
               r.monto, r.fecha, r.procesado
        FROM retiros r
        JOIN usuarios u ON r.usuario_id = u.id
        ORDER BY r.fecha DESC
    ''')
    retiros = c.fetchall()
    

    c.execute('''
        SELECT d.id, u.nombre, d.wallet, d.monto, d.moneda, d.fecha, d.confirmado, d.tipo_moneda_real
        FROM depositos d
        JOIN usuarios u ON d.usuario_id = u.id
        ORDER BY d.fecha DESC
    ''')
    depositos = c.fetchall()

    conn.close()

    return render_template('admin_dashboard.html', retiros=retiros, depositos=depositos, retiros_habilitados=retiros_estan_habilitados())

@app.route('/admin/confirmar_deposito/<int:deposito_id>', methods=['GET', 'POST'])
def confirmar_deposito(deposito_id):
    if 'admin_logged' not in session:
        return redirect(url_for('admin'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        tipo_moneda_real = request.form.get('tipo_moneda_real')
        c.execute('SELECT usuario_id, monto FROM depositos WHERE id = ? AND confirmado = 0', (deposito_id,))
        deposito = c.fetchone()
        if deposito:
            usuario_id, monto = deposito
            c.execute('''
                UPDATE usuarios SET saldo = saldo + ?, fondos_depositados = fondos_depositados + ?
                WHERE id = ?
            ''', (monto, monto, usuario_id))
            c.execute('''
                UPDATE depositos SET confirmado = 1, tipo_moneda_real = ? WHERE id = ?
            ''', (tipo_moneda_real, deposito_id))
            conn.commit()

        conn.close()
        return redirect(url_for('admin_dashboard'))

    # Mostrar formulario para seleccionar tipo de moneda real
    return '''
    <form method="POST">
      <label>Tipo de moneda real:</label>
      <select name="tipo_moneda_real" required>
        <option value="">Selecciona una opción</option>
        <option value="DOP">Pesos Dominicanos</option>
        <option value="USDT">USDT</option>
        <option value="BTC">Bitcoin</option>
      </select>
      <button type="submit">Confirmar</button>
    </form>
    '''

@app.route('/admin/marcar_procesado/<int:retiro_id>')
def marcar_procesado(retiro_id):
    if 'admin_logged' not in session:
        return redirect(url_for('admin'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('UPDATE retiros SET procesado = 1 WHERE id = ?', (retiro_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/toggle_retiros', methods=['POST'])
def toggle_retiros():
    if 'admin_logged' not in session:
        return redirect(url_for('admin'))
    alternar_estado_retiros()
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin'))
if __name__ == '__main__':
    app.run(debug=True)
