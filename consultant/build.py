"""
鑫鑫鑫｜Quant--WQ
世坤因子挖掘

版权所有 ©️ 鑫鑫鑫
微信: xinxinjijin8

本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。

Author: 鑫鑫鑫
"""
import os
import PyInstaller.__main__
import shutil

# 清理之前的构建
if os.path.exists('dist'):
    shutil.rmtree('dist')
if os.path.exists('build'):
    shutil.rmtree('build')

# 定义文件收集函数
def collect_data_files(source, target):
    return [(source, target)]

# PyInstaller配置
pyinstaller_args = [
    'app.py',  # 主入口文件
    '--name=QuantFactorExplorer',  # 生成的exe名称
    '--onefile',  # 打包成单个exe
    '--windowed',  # 不显示控制台窗口
    '--add-data=templates;templates',  # 添加模板文件夹
    '--add-data=static;static',  # 添加静态资源文件夹
    '--add-data=config.py;.',  # 添加配置文件
    '--add-data=machine_lib.py;.',
    '--add-data=user_info.txt;.',
    '--add-data=records;records',  # 添加记录文件夹
    '--add-data=tasks;tasks',  # 添加任务文件夹
    '--collect-submodules=waitress',  # 确保包含所有子模块
    '--hidden-import=engineio.async_drivers.threading'  # 隐藏导入
]

pyinstaller_args.extend([
     '--collect-all=pandas',
     '--collect-all=numpy',
     '--collect-all=requests',
     '--collect-all=pyyaml',
     '--collect-all=aiohttp',
     '--collect-all=asyncio',
     '--collect-all=aiofiles',
     '--collect-all=tqdm',
     '--collect-all=loguru',
     '--collect-all=flask',
     '--collect-all=python-dotenv',
     '--collect-all=pyinstaller',
     '--collect-all=pywin32'
])

# 添加所有任务文件
for file in os.listdir('tasks'):
    if file.endswith('.py'):
        pyinstaller_args.append(f'--add-data=tasks/{file};tasks')

# 执行打包
PyInstaller.__main__.run(pyinstaller_args)