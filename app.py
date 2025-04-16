from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import json
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_passwords():
    with open('passwords.json', 'r') as f:
        return json.load(f)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/', methods=['GET', 'POST'])
def common_login():
    passwords = get_passwords()
    if request.method == 'POST':
        common_pw = request.form['password']
        if common_pw == passwords['common']:
            session['common_auth'] = True
            return redirect(url_for('home'))
        else:
            flash('Incorrect site password!')
    return render_template('common_login.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    passwords = get_passwords()
    if request.method == 'POST':
        admin_pw = request.form['password']
        if admin_pw == passwords['admin']:
            session['admin_auth'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Incorrect admin password!')
    return render_template('admin_login.html')

@app.route('/employee_login', methods=['GET', 'POST'])
def employee_login():
    passwords = get_passwords()
    if request.method == 'POST':
        employee = request.form['employee']
        pw = request.form['password']
        if employee in passwords['employees'] and pw == passwords['employees'][employee]:
            session['employee'] = employee
            return redirect(url_for('account'))
        else:
            flash('Incorrect employee credentials!')
    return render_template('employee_login.html')

@app.route('/home')
def home():
    if not session.get('common_auth'):
        return redirect(url_for('common_login'))
    return render_template('home.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin_auth'):
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html')

@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    if not session.get('admin_auth'):
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        points = request.form['points']
        conn = get_db_connection()
        conn.execute('INSERT INTO tasks (title, description, points, status) VALUES (?,?,?,?)',
                     (title, description, points, 'available'))
        conn.commit()
        conn.close()
        flash('Task added!')
        return redirect(url_for('admin_dashboard'))
    return render_template('add_task.html')

@app.route('/tasks')
def tasks():
    if not session.get('common_auth'):
        return redirect(url_for('common_login'))
    conn = get_db_connection()
    tasks = conn.execute("SELECT * FROM tasks WHERE status = 'available'").fetchall()
    conn.close()
    return render_template('tasks.html', tasks=tasks)

@app.route('/claim_task/<int:task_id>', methods=['GET', 'POST'])
def claim_task(task_id):
    if 'employee' not in session:
        return redirect(url_for('employee_login'))
    if request.method == 'POST':
        passwords = get_passwords()
        employee = session['employee']
        pw = request.form['password']
        if employee in passwords['employees'] and pw == passwords['employees'][employee]:
            conn = get_db_connection()
            task = conn.execute('SELECT * FROM tasks WHERE id = ? AND status = "available"', (task_id,)).fetchone()
            if task:
                conn.execute('UPDATE tasks SET status = ?, assigned_to = ? WHERE id = ?',
                             ('in_progress', employee, task_id))
                conn.commit()
                conn.close()
                flash('Task claimed successfully!')
                return redirect(url_for('in_progress'))
            else:
                flash('Task is not available!')
                return redirect(url_for('tasks'))
        else:
            flash('Incorrect password for claiming the task!')
    return render_template('claim_task.html', task_id=task_id)

@app.route('/in_progress')
def in_progress():
    if not session.get('common_auth'):
        return redirect(url_for('common_login'))
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks WHERE status = "in_progress"').fetchall()
    conn.close()
    return render_template('in_progress.html', tasks=tasks)

@app.route('/abandon_task/<int:task_id>', methods=['POST'])
def abandon_task(task_id):
    if 'employee' not in session:
        return redirect(url_for('employee_login'))
    employee = session['employee']
    conn = get_db_connection()
    task = conn.execute('SELECT * FROM tasks WHERE id = ? AND assigned_to = ? AND status = "in_progress"', 
                        (task_id, employee)).fetchone()
    if task:
        half_points = int(task['points']) // 2
        conn.execute('UPDATE tasks SET status = ?, assigned_to = NULL WHERE id = ?', ('available', task_id))
        conn.commit()
        flash(f'Task abandoned. You lose {half_points} points!')
    else:
        flash('Task not found or not assigned to you.')
    conn.close()
    return redirect(url_for('in_progress'))

@app.route('/history')
def history():
    if not session.get('common_auth'):
        return redirect(url_for('common_login'))
    conn = get_db_connection()
    tasks = conn.execute("SELECT * FROM tasks WHERE status = 'completed'").fetchall()
    conn.close()
    return render_template('history.html', tasks=tasks)

@app.route('/leaderboard')
def leaderboard():
    if not session.get('common_auth'):
        return redirect(url_for('common_login'))
    conn = get_db_connection()
    leaderboard_data = conn.execute("""
        SELECT assigned_to, SUM(points) as total_points 
        FROM tasks 
        WHERE status = 'completed'
        GROUP BY assigned_to 
        ORDER BY total_points DESC
    """).fetchall()
    conn.close()
    return render_template('leaderboard.html', leaderboard=leaderboard_data)

@app.route('/reset_scores', methods=['POST'])
def reset_scores():
    if not session.get('admin_auth'):
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    conn.execute("""
        UPDATE tasks
        SET status = 'available',
            assigned_to = NULL,
            proof = NULL
        WHERE status = 'completed'
    """)
    conn.commit()
    conn.close()
    flash("All scores have been reset. Completed tasks are now available again.")
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    origin = request.form.get('redirect_to')
    password = request.form.get('password')
    passwords = get_passwords()

    if password != passwords['admin']:
        flash("Incorrect password.")
        return redirect(url_for('confirm_delete', task_id=task_id, origin=origin))

    conn = get_db_connection()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

    flash("Task deleted successfully.")

    if origin == 'tasks':
        return redirect(url_for('tasks'))
    elif origin == 'in_progress':
        return redirect(url_for('in_progress'))
    elif origin == 'history':
        return redirect(url_for('history'))
    else:
        return redirect(url_for('home'))

@app.route('/confirm_delete/<int:task_id>')
def confirm_delete(task_id):
    origin = request.args.get('origin')
    return render_template('confirm_delete.html', task_id=task_id, origin=origin)

@app.route('/account')
def account():
    if not session.get('common_auth'):
        return redirect(url_for('common_login'))
    if 'employee' not in session:
        return redirect(url_for('employee_login'))
    employee = session['employee']
    conn = get_db_connection()
    tasks_in_progress = conn.execute('SELECT * FROM tasks WHERE status = "in_progress" AND assigned_to = ?', (employee,)).fetchall()
    completed_tasks = conn.execute('SELECT * FROM tasks WHERE status = "completed" AND assigned_to = ?', (employee,)).fetchall()
    conn.close()
    return render_template('account.html', employee=employee, tasks_in_progress=tasks_in_progress, completed_tasks=completed_tasks)

@app.route('/upload_proof/<int:task_id>', methods=['GET', 'POST'])
def upload_proof(task_id):
    if 'employee' not in session:
        return redirect(url_for('employee_login'))
    if request.method == 'POST':
        if 'proof' not in request.files:
            flash('No file part!')
            return redirect(request.url)
        file = request.files['proof']
        if file.filename == '':
            flash('No file selected!')
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            conn = get_db_connection()
            conn.execute('UPDATE tasks SET status = ?, proof = ? WHERE id = ?', ('completed', filename, task_id))
            conn.commit()
            conn.close()
            flash('Proof uploaded and task marked as completed!')
            return redirect(url_for('account'))
    return render_template('upload_proof.html', task_id=task_id)

if __name__ == '__main__':
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            points INTEGER,
            status TEXT,
            assigned_to TEXT,
            proof TEXT
        )
    """)
    conn.commit()
    conn.close()
    app.run(debug=True)