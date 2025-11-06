"""
Zach
Zheng Xing
"""
import signal

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import sys
import importlib
import logging
import threading
import uuid
import requests
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
import webbrowser
import time

# 判断是否是打包环境
if getattr(sys, 'frozen', False):
    # 打包后，基础路径是sys._MEIPASS
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_WQwq9999'
# 确保所有路径都基于base_dir
app.config['TASKS_DIR'] = os.path.join(base_dir, 'tasks')
app.config['RECORDS_PATH'] = os.path.join(base_dir, 'records')
app.config['AUTH_SERVER_URL'] = 'https://www.alphamarket.cn/verify'

# 配置日志
log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
log_handler = RotatingFileHandler('app.log', maxBytes=10000000, backupCount=5)
log_handler.setFormatter(log_formatter)
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

# 存储任务状态
tasks = {}
stop_events = {}  # 用于中止任务的Event对象

class TaskRunner:
    def __init__(self, task_name, params):
        self.task_id = str(uuid.uuid4())
        self.task_name = task_name
        self.params = params
        self.status = 'pending'
        self.log = []
        self.start_time = None
        self.end_time = None
        self.thread = None
        self.stop_event = threading.Event()
        stop_events[self.task_id] = self.stop_event

    def run(self):
        self.status = 'running'
        self.start_time = datetime.now()

        try:
            # 动态导入任务模块
            module_name = self.task_name
            if not module_name.endswith('.py'):
                module_name += '.py'

            module_path = os.path.join(app.config['TASKS_DIR'], module_name)
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 重定向标准输出
            original_stdout = sys.stdout
            sys.stdout = TaskLogger(self)

            # 运行任务
            if hasattr(module, 'run_task'):
                # 传递stop_event给任务函数
                result = module.run_task(**self.params)
            elif hasattr(module, 'main'):
                result = module.main()
            else:
                raise AttributeError("No run_task or main function found in module")

            sys.stdout = original_stdout
            self.status = 'completed' if not self.stop_event.is_set() else 'stopped'
            self.end_time = datetime.now()
            return result
        except Exception as e:
            self.log.append(f"Error: {str(e)}")
            self.status = 'failed'
            self.end_time = datetime.now()
            return None
        finally:
            # 清理stop_event
            if self.task_id in stop_events:
                del stop_events[self.task_id]

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        if self.status == 'running':
            self.stop_event.set()
            self.log.append("任务中止请求已发送")
            return True
        return False

class TaskLogger:
    def __init__(self, task):
        self.task = task

    def write(self, message):
        if message.strip():
            self.task.log.append(message.strip())
            app.logger.info(f"[Task {self.task.task_id}] {message.strip()}")

    def flush(self):
        pass

def verify_credentials(user_id, license_key):
    """向远程服务器验证用户凭证"""
    try:
        response = requests.post(
            app.config['AUTH_SERVER_URL'],
            json={'user_id': user_id, 'license_key': license_key},
            timeout=5
        )
        return response.status_code == 200 and response.json().get('valid', False)
    except Exception as e:
        app.logger.error(f"认证服务器错误: {str(e)}")
        return False


@app.route('/')
def index():
    """主页面路由"""
    # 检查用户是否已登录
    if 'user_id' not in session or 'license_key' not in session:
        return redirect(url_for('login'))

    # 获取任务目录路径
    tasks_dir = app.config['TASKS_DIR']

    # 确保任务目录存在
    if not os.path.exists(tasks_dir):
        os.makedirs(tasks_dir, exist_ok=True)
        app.logger.info(f"Created tasks directory at {tasks_dir}")

    # 列出可用任务
    try:
        task_files = [f for f in os.listdir(tasks_dir)
                      if f.endswith('.py') and f != '__init__.py']
        task_names = [os.path.splitext(f)[0] for f in task_files]
    except FileNotFoundError as e:
        app.logger.error(f"Tasks directory not found: {e}")
        task_names = []

    return render_template('index.html', tasks=task_names, user_id=session['user_id'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面路由"""
    if request.method == 'POST':
        user_id = request.form['user_id']
        license_key = request.form['license_key']
        remember = request.form.get('remember') == 'on'

        # 验证凭证
        if verify_credentials(user_id, license_key):
            session['user_id'] = user_id
            session['license_key'] = license_key
            if remember:
                # 设置长期有效的session（10天）
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=10)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="无效的用户ID或激活码")

    # 如果session中有凭证，自动填充
    user_id = session.get('user_id', '')
    license_key = session.get('license_key', '')
    return render_template('login.html', user_id=user_id, license_key=license_key)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """注销路由"""
    session.pop('user_id', None)
    session.pop('license_key', None)
    return redirect(url_for('login'))


@app.route('/shutdown', methods=['POST'])
def shutdown():
    # 安全关闭服务器
    os.kill(os.getpid(), signal.SIGINT)
    return '服务器正在关闭...'


@app.route('/start_task', methods=['POST'])
def start_task():
    """启动新任务路由"""
    # 检查用户是否已登录
    if 'user_id' not in session or 'license_key' not in session:
        return jsonify({'error': '未登录'}), 401

    # 验证凭证
    if not verify_credentials(session['user_id'], session['license_key']):
        return jsonify({'error': '凭证验证失败'}), 401

    task_name = request.form['task']
    params = {k: v for k, v in request.form.items() if k != 'task'}

    # 创建任务运行器
    task_runner = TaskRunner(task_name, params)
    tasks[task_runner.task_id] = task_runner
    task_runner.start()

    return jsonify({'task_id': task_runner.task_id})

@app.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    """中止任务路由"""
    if task_id in tasks:
        task = tasks[task_id]
        if task.stop():
            return jsonify({'success': True})
        return jsonify({'error': '任务无法中止'}), 400
    return jsonify({'error': '任务不存在'}), 404

@app.route('/delete_task/<task_id>', methods=['POST'])
def delete_task(task_id):
    """删除任务路由"""
    if task_id in tasks:
        task = tasks[task_id]
        # 如果任务正在运行，先尝试中止
        if task.status == 'running':
            task.stop()
            # 等待任务状态更新
            for _ in range(10):
                if task.status != 'running':
                    break
                time.sleep(0.5)

        # 从任务字典中移除
        del tasks[task_id]
        return jsonify({'success': True})
    return jsonify({'error': '任务不存在'}), 404

@app.route('/task_status/<task_id>')
def task_status(task_id):
    """获取任务状态路由"""
    if task_id in tasks:
        task = tasks[task_id]
        return jsonify({
            'status': task.status,
            'log': task.log,
            'start_time': task.start_time.isoformat() if task.start_time else None,
            'end_time': task.end_time.isoformat() if task.end_time else None
        })
    return jsonify({'error': 'Task not found'}), 404

@app.route('/tasks')
def list_tasks():
    """列出所有任务路由"""
    return jsonify({
        task_id: {
            'name': task.task_name,
            'status': task.status,
            'start_time': task.start_time.isoformat() if task.start_time else None,
            'end_time': task.end_time.isoformat() if task.end_time else None
        }
        for task_id, task in tasks.items()
    })

@app.route('/task_logs/<task_id>')
def task_logs(task_id):
    """获取任务日志路由"""
    if task_id in tasks:
        return jsonify({'logs': tasks[task_id].log})
    return jsonify({'error': 'Task not found'}), 404

def open_browser():
    # 等待服务器启动
    time.sleep(1.5)
    webbrowser.open_new('http://127.0.0.1:5000/')

if __name__ == '__main__':
    # 在另一个线程中打开浏览器
    threading.Thread(target=open_browser).start()

    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
