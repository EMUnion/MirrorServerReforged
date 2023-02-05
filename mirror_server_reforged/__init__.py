import shutil
import os
import json
import sys
import time
import datetime
# MCDR Command & Class
from mcdreforged.api.decorator import new_thread
from mcdreforged.api.command import Literal, Text, SimpleCommandBuilder
from mcdreforged.api.rcon import RconConnection
from mcdreforged.mcdr_server import ServerInterface
from setuptools import Command
# Initalize Start
platform = sys.platform
Interface = None

if sys.platform == 'win32':
    MCDR_Command = 'python -m mcdreforged'
else:
    MCDR_Command = 'python3 -m mcdreforged'

PLUGIN_METADATA = {
    'id': 'mirror_server_reforged',
    'version': '1.0.5',
    'name': 'MirrorServerReforged',
    'description': 'A reforged version of [MCDR-Mirror-Server](https://github.com/GamerNoTitle/MCDR-Mirror-Server), which is a plugin for MCDR-Reforged 2.0+.',
    'author': 'GamerNoTitle',
    'link': 'https://github.com/EMUnion/MirrorServerReforged',
    'dependencies': {
        'mcdreforged': '>=2.6.0'
    }
}

config = {
    'world': ['world'],
    'command': MCDR_Command,
    'rcon': {
        'enable': False,
        'host': 'localhost',
        'port': 25575,
        'password': 'password'
    }
}

help_msg = '''{:=^50}
§b!!msr help §r- §6显示帮助信息
§b!!msr sync §r- §6同步服务器地图至镜像
§b!!msr reload §r- §6重载配置文件
§b!!msr start §r- §6启动镜像服务器
§b!!msr stop §r- §6关闭镜像服务器（需要开启Rcon）
§b!!msr init §r- §6初始化镜像服务器（仅MCDR类服务器可用）
{:=^50}'''.format(' §b[MirrorServerReforged] 帮助信息 §r', ' §b[MirrorServerReforged] Version: {} §r'.format(PLUGIN_METADATA['version']))
# §b!!msr status §r- §6查看镜像服务器状态


# Started = False  # Mirror server status
MCDR = False    # MCDR mode controller
path = os.getcwd()
syncFlag = False
# Initalize End


def InitalizeOnFirstRun():
    if os.path.exists('./Mirror/MCDReforged.py') or 'mcdreforged' in config['command']:
        global MCDR
        MCDR = True     # Turn on MCDR mode
    if not os.path.exists('./Mirror'):
        print('[MirrorServerReforged] 看起来你是第一次运行本插件？我们将会为您进行首次运行的初始化')
        print('[MirrorServerReforged] 正在创建镜像文件夹……')
        if MCDR:    # MCDR mode on, create Mirror folder and a server folder in Mirror folder
            print('[MirrorServerReforged] 检测到MCDR，我们将会按照MCDR的目录结构创建文件夹')
            try:
                os.makedirs('./Mirror')
            except:
                print('[MirrorServerReforged] Mirror文件夹已存在！')
            os.makedirs('./Mirror/server')
            os.chdir('Mirror')
            # Create MCDR dictionary structure
            os.system('python3 -m mcdreforged init')
            os.makedirs('./server/world')
            os.chdir(path)
        else:   # MCDR mode off, turn into legacy mode. Like Vanilla, Bukkit, Waterfalls and so on.
            print('[MirrorServerReforged] 未检测到MCDR，我们将会按照普通服务器的目录结构创建文件夹')
            try:
                os.makedirs('./Mirror')
            except:
                print('[MirrorServerReforged] Mirror文件夹已存在！')
            for world in config['world']:
                os.makedirs('./Mirror/{}'.format(world))
        print('[MirrorServerReforged] 初始化完成！')


def CreateConfig():
    print('[MirrorServerReforged] 正在创建配置文件……')
    global config
    with open('./config/MirrorServerReforged.json', 'w', encoding="utf-8") as f:
        f.write(json.dumps(config, indent=2, separators=(
            ',', ':'), ensure_ascii=False))
        f.close()


def RconInit(host, port, password):
    Rcon = RconConnection(host, port, password)
    return Rcon


def LoadConfig():
    print('[MirrorServerReforged] 正在加载配置文件……')
    global config
    with open('./config/MirrorServerReforged.json', 'r', encoding="utf-8") as f:
        config = json.load(f)


@new_thread('MSR-Sync')
def ServerSync(InterFace):
    start_time = datetime.datetime.now()
    ignore = shutil.ignore_patterns('session.lock')
    if MCDR:
        if os.path.exists('./Mirror/server/world'):
            shutil.rmtree('./Mirror/server/world')
        # shutil.copytree('./server/world/',
        #                 './Mirror/server/world', ignore=ignore)
        os.system(f'cp -r ./server/world ./Mirror/server/world')
    else:
        for world in config['world']:
            shutil.rmtree('./Mirror/{}/'.format(world))
            # shutil.copytree('./server/world/', './Mirror/world/', ignore=ignore)
            os.system(f'cp -r ./server/{world} ./Mirror/{world}')
    end_time = datetime.datetime.now()
    InterFace.execute(
        f'say §b[MirrorServerReforged] §6同步完成！用时{end_time-start_time}')


def Sync():
    InterFace = GetInterFace()
    if syncFlag:
        InterFace.execute(
            'say §b[MirrorServerReforged] §d服务器正在进行同步，请不要重复提交同步任务！')
    else:
        InterFace.execute('say §b[MirrorServerReforged] §6正在同步服务器地图……')
        InterFace.execute('save-off')
        InterFace.execute('save-all')
        ServerSync(InterFace)
        InterFace.execute('save-on')


@new_thread('MSR-Start')
def CommandExecute(InterFace):
    try:
        global MirrorPID, MirrorProcess
        if platform == 'win32':
            MirrorProcess = os.popen(f"start {config['command']}")
        else:
            MirrorProcess = os.popen(f"nohup {config['command']} &> MSR.log &")
    except:
        pass
    os.chdir(path)
    # InterFace.execute('say §b[MirrorServerReforged] §6镜像服已关闭！')
    # global Started
    # Started = False


@new_thread('MSR-Main')
def ServerStart(InterFace):
    # global Started
    try:
        os.chdir('Mirror')
        CommandExecute(InterFace)
        time.sleep(5)
        os.chdir(path)
    except Exception as e:
        InterFace.execute(
            'say §b[MirrorServerReforged] §6启动失败！原因为：{}'.format(e))


def Start(server):
    # global Started
    InterFace = GetInterFace()
    # if Started:
    #     server.reply('§b[MirrorServerReforged] §6镜像服正在运行……')
    # else:
    InterFace.execute('say §b[MirrorServerReforged] §6正在启动镜像服，这可能需要一定的时间……')
    InterFace.execute(
        'say §b[MirrorServerReforged] §6启动完成后，请自行利用BungeeCord的转服或者直连进行转服！')
    # Started = True
    ServerStart(InterFace)


def GetInterFace(*args):
    global Interface
    InterFace = ServerInterface.get_instance().as_plugin_server_interface()
    return InterFace

# def Status(server):
#     if Started:
#         server.reply('§b[MirrorServerReforged] §6镜像服正在运行……')
#     else:
#         server.reply('§b[MirrorServerReforged] §6镜像服未运行……')


def Stop(server):
    # global Started
    # if Started:
    if config['rcon']['enable']:
        conn = RconInit(config['rcon']['host'], config['rcon']
                        ['port'], config['rcon']['password'])
        try:
            connected = conn.connect()
            if connected:
                conn.send_command('stop', max_retry_time=3)
                conn.disconnect()
        except Exception as e:
            server.reply('§b[MirrorServerReforged] §6无法停止镜像服！原因为：{}'.format(e))
    else:
        server.reply('§b[MirrorServerReforged] §6无法通过Rcon停止镜像服，因为Rcon未开启！')
    # else:
    #     server.reply('§b[MirrorServerReforged] §6镜像服未运行！')


def Reload(server):
    server.reply('§b[MirrorServerReforged] §6正在重载配置文件……')
    ConfigToDo()
    server.reply('§b[MirrorServerReforged] §6重载完成！')


def DisplayHelp(server):
    for line in help_msg.splitlines():
        server.reply(line)


@new_thread('MSR-Init')
def MCDRInitalize(server):
    if MCDR:
        try:
            os.chdir('Mirror')
            system = sys.platform
            if system == 'win32':
                # Windows NT Platform
                os.system('python -m mcdreforged init')
            else:
                # Linux/Unix Platform
                os.system('python3 -m mcdreforged init')
            server.reply('§b[MirrorServerReforged] §6初始化已完成！')
        except Exception as e:
            server.reply('§b[MirrorServerReforged] §6初始化失败！原因为：{}'.format(e))
        os.chdir(path)
    else:
        server.reply('§b[MirrorServerReforged] §6非MCDR类服务器，无需初始化！')


def Initalize(server):
    server.reply('§b[MirrorServerReforged] §6已启动初始化进程！')
    MCDRInitalize(server)


def ConfigToDo():
    if os.path.exists('./config/MirrorServerReforged.json'):
        LoadConfig()
    else:
        CreateConfig()


def on_load(server, prev):
    ConfigToDo()    # Load Config
    InitalizeOnFirstRun()   # Initalize if this is the first run
    # builder = SimpleCommandBuilder()
    server.register_help_message('!!msr', 'MirrorServerReforged 帮助')
    server.register_command(Literal('!!msr').runs(DisplayHelp)
                            .then(Literal('help').runs(DisplayHelp))
                            .then(Literal('sync').runs(Sync))
                            .then(Literal('reload').runs(Reload))
                            .then(Literal('start').runs(Start))
                            .then(Literal('stop').runs(Stop))
                            .then(Literal('init').runs(Initalize))
                            # .then(Literal('status').runs(Status))
                            )
    # register stop confirm command (TOO LAZY TO REBUILD THE PREVIOUS COMMAND)
    # builder.command('!!msr help', DisplayHelp)
    # builder.command('!!msr sync', Sync)
    # builder.command('!!msr reload', Reload)
    # builder.command('!!msr start', Start)
    # builder.command('!!msr stop', Stop)
    # builder.command('!!msr init', Initalize)
    # builder.register(server)
