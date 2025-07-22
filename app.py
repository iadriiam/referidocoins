from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
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
            metodo TEXT,
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
            username TEXT,
            password TEXT
        )
    """)

    # Crear admin por defecto si no existe
    c.execute("SELECT * FROM admin WHERE username = ?", ('shanks',))
    if not c.fetchone():
        c.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('shanks', 'akagamiarmless'))

    conn.commit()
    conn.close()

init_db()
# ------------------------ REGISTRO ------------------------
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        data = request.json
        nombre = data['nombre']
        correo = data['correo']
        contrasena = generate_password_hash(data['contrasena'])
        red = data['red']
        wallet = data['wallet']
        referido = data.get('referido', None)
        codigo_referido = ''.join([c for c in nombre if c.isalnum()]) + str(datetime.now().timestamp()).replace('.', '')[:5]

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        referido_por = None
        if referido:
            c.execute("SELECT id FROM usuarios WHERE codigo_referido = ?", (referido,))
            ref = c.fetchone()
            if ref:
                referido_por = ref[0]

        try:
            c.execute("""INSERT INTO usuarios 
                        (nombre, correo, contrasena, red, wallet, referido, codigo_referido, referido_por) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (nombre, correo, contrasena, red, wallet, referido, codigo_referido, referido_por))
            conn.commit()
            return jsonify({'success': True})
        except:
            return jsonify({'success': False, 'error': 'Correo ya registrado'})
        finally:
            conn.close()

    return render_template('registro.html')

# ------------------------ LOGIN ------------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT id, contrasena, nombre FROM usuarios WHERE correo = ?", (correo,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[1], contrasena):
            session['usuario_id'] = user[0]
            session['nombre'] = user[2]
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Credenciales inválidas")

    return render_template('login.html')

# ------------------------ RECOMPENSA DIARIA ------------------------
@app.route('/recompensa-diaria', methods=['POST'])
def recompensa_diaria():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401

    usuario_id = session['usuario_id']
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT ultima_recompensa, fondos_depositados FROM usuarios WHERE id = ?", (usuario_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({'error': 'Usuario no encontrado'}), 404

    ultima, invertido = row
    ahora = datetime.now()

    if ultima:
        ultima_fecha = datetime.strptime(ultima, "%Y-%m-%d %H:%M:%S")
        if ahora - ultima_fecha < timedelta(hours=24):
            restante = timedelta(hours=24) - (ahora - ultima_fecha)
            conn.close()
            return jsonify({'error': f'Ya reclamaste. Intenta de nuevo en {str(restante).split(".")[0]}'}), 400

    recompensa = round(invertido * 0.03, 2)
    c.execute("UPDATE usuarios SET bonos = bonos + ?, ultima_recompensa = ? WHERE id = ?",
              (recompensa, ahora.strftime("%Y-%m-%d %H:%M:%S"), usuario_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'bono': recompensa})
# ------------------------ DASHBOARD ------------------------
@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    usuario_id = session['usuario_id']
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT nombre, saldo, bonos, codigo_referido FROM usuarios WHERE id = ?", (usuario_id,))
    user = c.fetchone()
    nombre_usuario, saldo_total, bonos, codigo_referido = user

    # Saldo por moneda
    c.execute("SELECT tipo_moneda_real, SUM(monto) FROM depositos WHERE usuario_id = ? AND estado = 'confirmado' GROUP BY tipo_moneda_real", (usuario_id,))
    saldo_monedas = {row[0]: row[1] for row in c.fetchall()}

    # Total referidos
    c.execute("SELECT COUNT(*) FROM usuarios WHERE referido_por = ?", (usuario_id,))
    total_referidos = c.fetchone()[0]

    # Historial depósitos
    c.execute("SELECT monto, tipo_moneda_real, fecha FROM depositos WHERE usuario_id = ? AND estado = 'confirmado' ORDER BY fecha DESC", (usuario_id,))
    depositos = [{'monto': row[0], 'moneda': row[1], 'fecha': row[2]} for row in c.fetchall()]

    # Historial retiros
    c.execute("SELECT monto, fecha FROM retiros WHERE usuario_id = ? ORDER BY fecha DESC")
    retiros = [{'monto': row[0], 'fecha': row[1]} for row in c.fetchall()]

    # Estadísticas para gráficos
    c.execute("SELECT strftime('%Y-%m-%d', fecha) as dia, SUM(monto) FROM depositos WHERE usuario_id = ? AND estado = 'confirmado' GROUP BY dia ORDER BY dia ASC", (usuario_id,))
    depositos_json = [{'fecha': row[0], 'monto': row[1]} for row in c.fetchall()]

    c.execute("SELECT strftime('%Y-%m-%d', fecha) as dia, SUM(monto) FROM retiros WHERE usuario_id = ? GROUP BY dia ORDER BY dia ASC", (usuario_id,))
    retiros_json = [{'fecha': row[0], 'monto': row[1]} for row in c.fetchall()]

    conn.close()

    return render_template('dashboard.html',
                           nombre_usuario=nombre_usuario,
                           saldo_monedas=saldo_monedas,
                           ganancias=bonos,
                           codigo_referido=codigo_referido,
                           total_referidos=total_referidos,
                           depositos=depositos,
                           retiros=retiros,
                           depositos_json=depositos_json,
                           retiros_json=retiros_json)

# ------------------------ ENVIAR DEPÓSITO ------------------------
@app.route('/depositar', methods=['POST'])
def depositar():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401

    data = request.json
    monto = data.get('monto')
    metodo = data.get('moneda')

    if not monto or not metodo:
        return jsonify({'error': 'Faltan datos del depósito'}), 400

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("""INSERT INTO depositos (usuario_id, monto, tipo_moneda_real, estado, fecha) 
                 VALUES (?, ?, ?, 'pendiente', datetime('now'))""", 
              (session['usuario_id'], monto, metodo))
    conn.commit()
    conn.close()

    return jsonify({'success': True})
# ------------------------ ENVIAR RETIRO ------------------------
@app.route('/retirar', methods=['POST'])
def retirar():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401

    data = request.json
    monto = float(data.get('monto'))

    if monto < 10:
        return jsonify({'error': 'El retiro mínimo es $10'}), 400

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT bonos FROM usuarios WHERE id = ?", (session['usuario_id'],))
    bonos_actuales = c.fetchone()[0]

    c.execute("SELECT habilitar_retiros FROM configuracion")
    retiros_habilitados = c.fetchone()[0]

    if not retiros_habilitados:
        conn.close()
        return jsonify({'error': 'Los retiros están deshabilitados temporalmente'}), 403

    if monto > bonos_actuales:
        conn.close()
        return jsonify({'error': 'Fondos insuficientes en ganancias'}), 400

    c.execute("""INSERT INTO retiros (usuario_id, monto, estado, fecha)
                 VALUES (?, ?, 'pendiente', datetime('now'))""",
              (session['usuario_id'], monto))

    conn.commit()
    conn.close()

    return jsonify({'success': True})


# ------------------------ LOGOUT ------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ------------------------ PANEL ADMINISTRADOR ------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'shanks' and password == 'akagamiarmless':
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Credenciales inválidas')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT d.id, u.nombre, d.monto, d.tipo_moneda_real, d.fecha FROM depositos d JOIN usuarios u ON d.usuario_id = u.id WHERE d.estado = 'pendiente'")
    depositos = c.fetchall()

    c.execute("SELECT r.id, u.nombre, r.monto, r.fecha FROM retiros r JOIN usuarios u ON r.usuario_id = u.id WHERE r.estado = 'pendiente'")
    retiros = c.fetchall()

    c.execute("SELECT habilitar_retiros FROM configuracion")
    retiros_habilitados = c.fetchone()[0]

    conn.close()

    return render_template('admin_dashboard.html', depositos=depositos, retiros=retiros, retiros_habilitados=retiros_habilitados)


@app.route('/admin/confirmar_deposito/<int:deposito_id>', methods=['POST'])
def confirmar_deposito(deposito_id):
    if not session.get('admin'):
        return "No autorizado", 403

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT usuario_id, monto, tipo_moneda_real FROM depositos WHERE id = ? AND estado = 'pendiente'", (deposito_id,))
    deposito = c.fetchone()

    if not deposito:
        conn.close()
        return "Depósito no encontrado", 404

    usuario_id, monto, moneda = deposito

    c.execute("UPDATE depositos SET estado = 'confirmado' WHERE id = ?", (deposito_id,))
    c.execute("UPDATE usuarios SET saldo = saldo + ?, fondos_depositados = fondos_depositados + ? WHERE id = ?", (monto, monto, usuario_id))

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/procesar_retiro/<int:retiro_id>', methods=['POST'])
def procesar_retiro(retiro_id):
    if not session.get('admin'):
        return "No autorizado", 403

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT usuario_id, monto FROM retiros WHERE id = ? AND estado = 'pendiente'", (retiro_id,))
    retiro = c.fetchone()

    if not retiro:
        conn.close()
        return "Retiro no encontrado", 404

    usuario_id, monto = retiro

    c.execute("UPDATE retiros SET estado = 'procesado' WHERE id = ?", (retiro_id,))
    c.execute("UPDATE usuarios SET bonos = bonos - ? WHERE id = ?", (monto, usuario_id))

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/toggle-retiros', methods=['POST'])
def toggle_retiros():
    if not session.get('admin'):
        return "No autorizado", 403

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT habilitar_retiros FROM configuracion")
    actual = c.fetchone()[0]
    nuevo_estado = 0 if actual else 1
    c.execute("UPDATE configuracion SET habilitar_retiros = ?", (nuevo_estado,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))
# ------------------------ RECOMPENSA DIARIA ------------------------
@app.route('/recompensa', methods=['POST'])
def recompensa_diaria():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute("SELECT fondos_depositados FROM usuarios WHERE id = ?", (session['usuario_id'],))
    inversion = c.fetchone()[0]

    c.execute("SELECT ultima_recompensa FROM recompensas WHERE usuario_id = ?", (session['usuario_id'],))
    row = c.fetchone()

    ahora = datetime.now()

    if row:
        ultima_recompensa = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        diferencia = ahora - ultima_recompensa
        if diferencia.total_seconds() < 86400:
            tiempo_restante = 86400 - diferencia.total_seconds()
            horas = int(tiempo_restante // 3600)
            minutos = int((tiempo_restante % 3600) // 60)
            return jsonify({'error': f'Debes esperar {horas}h {minutos}min para reclamar de nuevo'}), 403

        c.execute("UPDATE recompensas SET ultima_recompensa = ? WHERE usuario_id = ?", (ahora.strftime("%Y-%m-%d %H:%M:%S"), session['usuario_id']))
    else:
        c.execute("INSERT INTO recompensas (usuario_id, ultima_recompensa) VALUES (?, ?)", (session['usuario_id'], ahora.strftime("%Y-%m-%d %H:%M:%S")))

    recompensa = round(inversion * 0.03, 2)
    c.execute("UPDATE usuarios SET bonos = bonos + ? WHERE id = ?", (recompensa, session['usuario_id']))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'bono': recompensa})


# ------------------------ INICIAR APP ------------------------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
