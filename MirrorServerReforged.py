from email.headerregistry import Address
from importlib.resources import path
import sys
import shutil
import os
import json
# MCDR Command & Class
from mcdreforged.api.decorator import new_thread
from mcdreforged.api.command import Literal, Text
from mcdreforged.api.rcon import rcon
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
    'path': './Mirror/',
    'world': ['world'],
    'command': 'python3 -m MCDReforged'
}

help_msg = '''
'''
# Initalize End

def CreateConfig():
    global config
    with open('./config/MirrorServerReforged.json', 'w', encoding="utf-8") as f:
        f.write(json.dumps(config, indent=2, separators=(',', ':'), ensure_ascii=False))
        f.close()


def LoadConfig():
    global config
    with open('./config/MirrorServerReforged.json', 'r', encoding="utf-8") as f:
        config = json.load(f)

def Sync(target):
    shutil.copy('./')

def Start():
    pass

def Stop():
    pass

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
    server.register_help_message('!!msr', 'MirrorServerReforged Help')
    server.register_command(Literal('!!msr').runs(DisplayHelp)\
        .then(Literal('help').runs(DisplayHelp))\
        .then(Literal('sync').runs(Sync))\
        .then(Literal('reload').runs(Reload))\
        .then(Literal('start').runs(Start))\
        .then(Literal('stop').runs(Stop))\
        )   

