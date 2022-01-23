from email.headerregistry import Address
from importlib.resources import path
import sys
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
        if MCDR:    # MCDR mode on, create Mirror folder and a server folder in Mirror folder
            os.makedirs('./Mirror')
            os.makedirs('./Mirror/server')
        else:   # MCDR mode off, turn into legacy mode. Like Vanilla, Bukkit, Waterfalls and so on.
            os.makedirs('./Mirror')
            for world in config['world']:
                os.makedirs('./Mirror/{}'.format(world))


def CreateConfig():
    global config
    with open('./config/MirrorServerReforged.json', 'w', encoding="utf-8") as f:
        f.write(json.dumps(config, indent=2, separators=(
            ',', ':'), ensure_ascii=False))
        f.close()


def RconInit(host, port, password):
    Rcon = RconConnection(host, port, password)
    return Rcon

def LoadConfig():
    global config
    with open('./config/MirrorServerReforged.json', 'r', encoding="utf-8") as f:
        config = json.load(f)


def Sync():
    if os.path.exists('./Mirror/world') and MCDR == True:
        shutil.copytree('./server/world/', './Mirror/world/')
    else:
        for world in config['world']:
            shutil.copytree('./server/{}/'.format(world), './Mirror/{}/'.format(world))


@new_thread('MirrorServerReforged')
def Start(server):
    global Started
    if Started:
        server.reply('b[MirrorServerReforged] §6镜像服正在运行……')
    else:
        Started = True
        os.system(config['command'])
    Started = False


def Status(server):
    if Started:
        server.reply('§b[MirrorServerReforged] §6镜像服正在运行……')
    else:
        server.reply('§b[MirrorServerReforged] §6镜像服未运行……')

def Stop(server):
    if config['rcon']['enable']:
        conn = RconInit(config['rcon']['host'], config['rcon']['port'], config['rcon']['password'])
        connected = conn.connect()
        if connected:
            conn.send('stop')
            conn.disconnect()
            global Started
            Started = False
        else:
            server.reply('§b[MirrorServerReforged] §6Rcon连接失败，请检查网络原因或配置信息是否正确！')



def Reload():
    ConfigToDo()


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

