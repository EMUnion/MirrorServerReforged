from email.headerregistry import Address
from http import server
from importlib.resources import path
import shutil
import os
import json
from xmlrpc.client import FastUnmarshaller
# MCDR Command & Class
from mcdreforged.api.decorator import new_thread
from mcdreforged.api.command import Literal, Text
from mcdreforged.api.rcon import RconConnection
# Initalize Start
PLUGIN_METADATA = {
    'id': 'mirror_server_reforged',
    'version': '1.0.0',
    'name': 'MirrorServerReforged',
    'description': 'A reforged version of [MCDR-Mirror-Server](https://github.com/GamerNoTitle/MCDR-Mirror-Server), which is a plugin for MCDR-Reforged 2.0+.',
    'author': 'GamerNoTitle',
    'link': 'https://github.com/GamerNoTitle/MirrorServerReforged',
    'dependencies': {
        'mcdreforged': '>=2.0.0'
    }
}

config = {
    'world': ['world'],
    'command': 'python3 -m MCDReforged',
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
{:=^50}'''.format('§b[MirrorServerReforged] 帮助信息', '§b[MirrorServerReforged] Version: {}'.format(PLUGIN_METADATA['version']))

Started = False  # Mirror server status
MCDR = False    # MCDR mode controller

# Initalize End


def InitalizeOnFirstRun():
    if os.path.exists('./Mirror/MCDReforged.py') or 'MCDReforged' in config['command']:
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


def Sync(server):
    server.reply('§b[MirrorServerReforged] §6正在同步服务器地图……')
    if os.path.exists('./Mirror/world') and MCDR == True:
        shutil.copytree('./server/world/', './Mirror/world/')
    else:
        for world in config['world']:
            shutil.copytree('./server/{}/'.format(world),
                            './Mirror/{}/'.format(world))
    server.reply('§b[MirrorServerReforged] §6同步完成！')


@new_thread('MirrorServerReforged')
def Start(server):
    global Started
    if Started:
        server.reply('b[MirrorServerReforged] §6镜像服正在运行……')
    else:
        server.reply('§b[MirrorServerReforged] §6正在启动镜像服，这可能需要一定的时间……')
        server.reply(
            '§b[MirrorServerReforged] §6启动完成后，请自行利用BungeeCord的转服或者直连进行转服！')
        Started = True
        os.system(config['command'])
        server.reply('§b[MirrorServerReforged] §6镜像服已关闭！')
    Started = False


def Status(server):
    if Started:
        server.reply('§b[MirrorServerReforged] §6镜像服正在运行……')
    else:
        server.reply('§b[MirrorServerReforged] §6镜像服未运行……')


def Stop(server):
    if config['rcon']['enable']:
        conn = RconInit(config['rcon']['host'], config['rcon']
                        ['port'], config['rcon']['password'])
        connected = conn.connect()
        if connected:
            conn.send('stop')
            conn.disconnect()
            global Started
            Started = False
        else:
            server.reply(
                '§b[MirrorServerReforged] §6Rcon连接失败，请检查网络原因或配置信息是否正确！')
    else:
        server.reply('§b[MirrorServerReforged] §6无法在主服务器停止宿服务器，因为Rcon未开启！')


def Reload(server):
    server.reply('§b[MirrorServerReforged] §6正在重载配置文件……')
    ConfigToDo()
    server.reply('§b[MirrorServerReforged] §6重载完成！')


def DisplayHelp(server):
    for line in help_msg.splitlines():
        server.reply(line)


def ConfigToDo():
    if os.path.exists('./config/MirrorServerReforged.json'):
        LoadConfig()
    else:
        CreateConfig()


def on_load(server, prev):
    ConfigToDo()    # Load Config
    InitalizeOnFirstRun()   # Initalize if this is the first run
    server.register_help_message('!!msr', 'MirrorServerReforged 帮助')
    server.register_command(Literal('!!msr').runs(DisplayHelp)
                            .then(Literal('help').runs(DisplayHelp))
                            .then(Literal('sync').runs(Sync))
                            .then(Literal('reload').runs(Reload))
                            .then(Literal('start').runs(Start))
                            .then(Literal('stop').runs(Stop))
                            )
