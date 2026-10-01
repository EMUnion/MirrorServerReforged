import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from enum import Enum, auto

# MCDR Command & Class
from mcdreforged.api.command import Literal, SimpleCommandBuilder, Text
from mcdreforged.api.decorator import new_thread
from mcdreforged.api.rcon import RconConnection
from mcdreforged.api.rtext import RColor, RText, RTextList
from mcdreforged.mcdr_server import ServerInterface

from .utils import (
    FindServerProperties,
    GetLogDirectories,
    GetNewestLogMtime,
    IsMinecraftServerReady,
    IsTcpPortOpen,
    ReadServerProperties,
    ToAbsolutePath,
)

# Initalize Start
platform = sys.platform
Interface = None

if sys.platform == "win32":
    MCDR_Command = "python -m mcdreforged"
else:
    MCDR_Command = "python3 -m mcdreforged"

PLUGIN_METADATA = {
    "id": "mirror_server_reforged",
    "version": "1.0.8-alpha.1",
    "name": "MirrorServerReforged",
    "description": "A reforged version of [MCDR-Mirror-Server](https://github.com/GamerNoTitle/MCDR-Mirror-Server), which is a plugin for MCDR-Reforged 2.6.0+.",
    "author": "GamerNoTitle",
    "link": "https://github.com/EMUnion/MirrorServerReforged",
    "dependencies": {"mcdreforged": ">=2.6.0"},
}

# Defaults of the mirror server status checks. The values live in the config file so
# that users can change them; these are only the defaults for a new config file, and for
# the keys missing from an existing one.
DEFAULT_CHECK_OPTIONS = {
    # Longest time (in second) to wait for the mirror server to finish starting up
    "start_timeout": 300,
    # Interval (in second) between two startup checks
    "start_interval": 2,
    # A launcher may hand the server off and exit, so the process exit alone is not a
    # failure: the startup is only reported as failed once the mirror server has shown
    # no sign of life for this many seconds
    "start_exit_grace": 90,
    # Longest time (in second) to wait for the mirror server to be fully stopped
    "stop_timeout": 120,
    # Interval (in second) between two shutdown checks
    "stop_interval": 1,
    # How recent a write to a mirror server log counts as a sign of life, in second
    "log_active_window": 15,
}

config = {
    "world": ["world"],
    "command": MCDR_Command,
    "rcon": {
        "enable": False,
        "host": "localhost",
        "port": 25575,
        "password": "password",
    },
    "source": "./server",
    "target": "./Mirror/server",
    "check": dict(DEFAULT_CHECK_OPTIONS),
}

help_msg = """{:=^50}
§b!!msr help §r- §6显示帮助信息
§b!!msr sync §r- §6同步服务器地图至镜像
§b!!msr reload §r- §6重载配置文件
§b!!msr start §r- §6启动镜像服务器
§b!!msr stop §r- §6关闭镜像服务器（需要开启Rcon）
§b!!msr init §r- §6初始化镜像服务器（仅MCDR类服务器可用）
{:=^50}""".format(
    " §b[MirrorServerReforged] 帮助信息 §r",
    " §b[MirrorServerReforged] Version: {} §r".format(PLUGIN_METADATA["version"]),
)
# §b!!msr status §r- §6查看镜像服务器状态


# Started = False  # Mirror server status
MCDR = False  # MCDR mode controller
path = os.getcwd()
syncFlag = False
# Initalize End


class MirrorStartResult(Enum):
    READY = auto()  # the mirror server finished starting up
    EXITED = auto()  # the launch ended without the mirror server ever coming up
    TIMEOUT = auto()  # still not ready when the wait timed out
    UNKNOWN = auto()  # no usable readiness probe is available


def CheckOption(name):
    return config.get("check", {}).get(name, DEFAULT_CHECK_OPTIONS[name])


def GetMirrorDir():
    return os.path.join(path, "Mirror")


def GetConfigPath():
    return os.path.join(path, "config", "MirrorServerReforged.json")


def InitalizeOnFirstRun():
    if (
        os.path.exists(os.path.join(GetMirrorDir(), "MCDReforged.py"))
        or "mcdreforged" in config["command"]
    ):
        global MCDR
        MCDR = True  # Turn on MCDR mode
    if not os.path.exists(GetMirrorDir()):
        print(
            "[MirrorServerReforged] 看起来你是第一次运行本插件？我们将会为您进行首次运行的初始化"
        )
        print("[MirrorServerReforged] 正在创建镜像文件夹……")
        if MCDR:
            # MCDR mode on, create Mirror folder and a server folder in Mirror folder
            print(
                "[MirrorServerReforged] 检测到MCDR，我们将会按照MCDR的目录结构创建文件夹"
            )
            try:
                os.makedirs(GetMirrorDir())
            except Exception:
                print("[MirrorServerReforged] Mirror文件夹已存在！")
            os.makedirs(os.path.join(GetMirrorDir(), "server"))
            os.chdir(GetMirrorDir())
            # Create MCDR dictionary structure
            os.system("python3 -m mcdreforged init")
            os.makedirs(os.path.join(GetMirrorDir(), "server", "world"))
            os.chdir(path)
        else:  # MCDR mode off, turn into legacy mode. Like Vanilla, Bukkit, Waterfalls and so on.
            print(
                "[MirrorServerReforged] 未检测到MCDR，我们将会按照普通服务器的目录结构创建文件夹"
            )
            try:
                os.makedirs(GetMirrorDir())
            except Exception:
                print("[MirrorServerReforged] Mirror文件夹已存在！")
            for world in config["world"]:
                os.makedirs(os.path.join(GetMirrorDir(), world))
        print("[MirrorServerReforged] 初始化完成！")


def CreateConfig():
    print("[MirrorServerReforged] 正在创建配置文件……")
    global config
    with open(GetConfigPath(), "w", encoding="utf-8") as f:
        f.write(json.dumps(config, indent=2, separators=(",", ":"), ensure_ascii=False))
        f.close()


def RconInit(host, port, password):
    Rcon = RconConnection(host, port, password)
    return Rcon


def LoadConfig():
    print("[MirrorServerReforged] 正在加载配置文件……")
    global config
    with open(GetConfigPath(), "r", encoding="utf-8") as f:
        config = json.load(f)
    if "source" not in config:
        config["source"] = "./server"
    if "target" not in config:
        config["target"] = "./Mirror/server"
    check = config.setdefault("check", {})
    for name, value in DEFAULT_CHECK_OPTIONS.items():
        check.setdefault(name, value)
    CreateConfig()


def Broadcast(InterFace, message, color=RColor.gold):
    """Broadcast without putting legacy section signs in a server command."""
    InterFace.say(
        RTextList(RText("[MirrorServerReforged] ", RColor.aqua), RText(message, color))
    )


def CopyWorld(source_root, target_root, world):
    """Copy a world into place without deleting the last good mirror first."""
    source = os.path.abspath(os.path.join(source_root, world))
    target = os.path.abspath(os.path.join(target_root, world))
    if not os.path.isdir(source):
        raise FileNotFoundError("源世界目录不存在: {}".format(source))
    try:
        common_path = os.path.commonpath((source, target))
    except ValueError:
        # Different Windows drives cannot overlap.
        common_path = None
    if source == target or common_path in (source, target):
        raise ValueError("镜像目录与源世界目录不能互相包含")

    target_parent = os.path.dirname(target)
    os.makedirs(target_parent, exist_ok=True)
    temporary_root = tempfile.mkdtemp(
        prefix=".{}-msr-sync-".format(os.path.basename(target)), dir=target_parent
    )
    staged = os.path.join(temporary_root, "new")
    previous = os.path.join(temporary_root, "previous")
    moved_previous = False
    try:
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("session.lock"))
        if os.path.exists(target):
            os.replace(target, previous)
            moved_previous = True
        try:
            os.replace(staged, target)
        except Exception:
            if moved_previous and not os.path.exists(target):
                os.replace(previous, target)
            raise
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


@new_thread("MSR-Sync")
def ServerSync(InterFace):
    global syncFlag
    start_time = datetime.datetime.now()
    try:
        InterFace.execute("save-off")
        InterFace.execute("save-all")
        for world in config["world"]:
            CopyWorld(config["source"], config["target"], world)
        end_time = datetime.datetime.now()
        Broadcast(InterFace, "同步完成！用时{}".format(end_time - start_time))
    except Exception as e:
        InterFace.logger.exception("[MirrorServerReforged] 同步失败")
        Broadcast(InterFace, "同步失败！原因：{}".format(e), RColor.red)
    finally:
        InterFace.execute("save-on")
        syncFlag = False


def Sync():
    global syncFlag
    InterFace = GetInterFace()
    if syncFlag:
        Broadcast(
            InterFace,
            "服务器正在进行同步，请不要重复提交同步任务！",
            RColor.light_purple,
        )
    else:
        syncFlag = True
        Broadcast(InterFace, "正在同步服务器地图……")
        ServerSync(InterFace)


def GetMirrorServerDirectories():
    directories = []
    target = config.get("target")
    if target:
        directories.append(ToAbsolutePath(path, target))
    mirror_dir = GetMirrorDir()
    if os.path.normpath(mirror_dir) not in (os.path.normpath(d) for d in directories):
        directories.append(mirror_dir)
    return directories


def GetMirrorServerProperties():
    return ReadServerProperties(FindServerProperties(GetMirrorServerDirectories()))


def IsMirrorLogActive(window=None):
    if window is None:
        window = CheckOption("log_active_window")
    log_directories = GetLogDirectories(GetMirrorServerDirectories(), path)
    newest = GetNewestLogMtime(log_directories)
    return newest is not None and (time.time() - newest) <= window


def IsMirrorAlive():
    if IsMirrorLogActive():
        return True
    properties = GetMirrorServerProperties()
    if properties.port is not None and IsTcpPortOpen(properties.host, properties.port):
        return True
    if config["rcon"]["enable"]:
        if IsTcpPortOpen(config["rcon"]["host"], config["rcon"]["port"]):
            return True
    return False


def GetMirrorReadyProbes():
    probes = []
    properties = GetMirrorServerProperties()
    if properties.port is not None:
        probes.append(lambda: IsMinecraftServerReady(properties.host, properties.port))
    if config["rcon"]["enable"]:
        rcon_host = config["rcon"]["host"]
        rcon_port = config["rcon"]["port"]
        probes.append(lambda: IsTcpPortOpen(rcon_host, rcon_port))
    return probes


def DescribeMirrorReadyProbes():
    parts = []
    properties = GetMirrorServerProperties()
    if properties.port is not None:
        parts.append("状态查询 {}:{}".format(properties.host, properties.port))
    else:
        parts.append("状态查询不可用（未读到 server-port）")
    if config["rcon"]["enable"]:
        parts.append("Rcon {}:{}".format(config["rcon"]["host"], config["rcon"]["port"]))
    else:
        parts.append("Rcon 未开启")
    return "，".join(parts)


def WaitForMirrorStart(process, timeout=None):
    if timeout is None:
        timeout = CheckOption("start_timeout")
    probes = GetMirrorReadyProbes()
    if len(probes) == 0:
        return MirrorStartResult.UNKNOWN
    deadline = time.monotonic() + timeout
    exited_at = None
    last_alive_at = None
    while time.monotonic() < deadline:
        for probe in probes:
            if probe():
                return MirrorStartResult.READY
        if process is not None and process.poll() is not None:
            now = time.monotonic()
            first_check = exited_at is None
            if first_check:
                exited_at = now
            alive = IsMirrorAlive()
            exit_code = getattr(process, "returncode", None)
            if first_check and exit_code not in (0, None) and not alive:
                # the launch itself failed, e.g. command not found or no permission
                return MirrorStartResult.EXITED
            if alive:
                # the launcher handed the server off, or it is still starting up
                last_alive_at = now
            else:
                reference = exited_at if last_alive_at is None else max(exited_at, last_alive_at)
                if now - reference >= CheckOption("start_exit_grace"):
                    return MirrorStartResult.EXITED
        time.sleep(CheckOption("start_interval"))
    return MirrorStartResult.TIMEOUT


def NotifyMirrorStart(InterFace, process):
    InterFace.logger.info(
        "[MirrorServerReforged] 启动检测方式：{}".format(DescribeMirrorReadyProbes())
    )
    result = WaitForMirrorStart(process)
    if result is MirrorStartResult.READY:
        Broadcast(InterFace, "镜像服已启动完成，现在可以转服了！")
    elif result is MirrorStartResult.EXITED:
        Broadcast(
            InterFace,
            "镜像服启动失败！启动进程已退出，且未检测到镜像服运行，请查看镜像服控制台的报错信息。",
            RColor.red,
        )
    elif result is MirrorStartResult.TIMEOUT:
        Broadcast(
            InterFace,
            "已启动镜像服，但等待{}秒后仍未检测到启动完成，请手动检查！（检测方式：{}）".format(
                CheckOption("start_timeout"), DescribeMirrorReadyProbes()
            ),
            RColor.red,
        )
    else:
        Broadcast(
            InterFace,
            "无法确认镜像服是否启动完成：未找到镜像服的server.properties，且Rcon未开启！",
            RColor.red,
        )


@new_thread("MSR-Start")
def CommandExecute(InterFace):
    try:
        global MirrorProcess
        MirrorProcess = None
        if platform == "win32":
            MirrorProcess = subprocess.Popen(
                config["command"], creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            MirrorProcess = subprocess.Popen(config["command"], shell=True)
    except Exception as e:
        Broadcast(InterFace, "启动失败！原因为：{}".format(e), RColor.red)
    os.chdir(path)


@new_thread("MSR-Main")
def ServerStart(InterFace):
    # global Started
    try:
        os.chdir(GetMirrorDir())
        CommandExecute(InterFace)
        time.sleep(5)
        os.chdir(path)
    except Exception as e:
        Broadcast(InterFace, "启动失败！原因为：{}".format(e), RColor.red)
        return
    NotifyMirrorStart(InterFace, GetMirrorProcess())


def Start(server):
    # global Started
    InterFace = GetInterFace()
    # if Started:
    #     server.reply('§b[MirrorServerReforged] §6镜像服正在运行……')
    # else:
    if syncFlag:
        Broadcast(
            InterFace,
            "镜像服正在进行同步，请在同步完成后再启动镜像服！",
            RColor.light_purple,
        )
    else:
        Broadcast(InterFace, "正在启动镜像服，这可能需要一定的时间……")
        Broadcast(InterFace, "启动完成后，请自行利用BungeeCord的转服或者直连进行转服！")
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


def GetMirrorProcess():
    """Return the raw mirror server process handle, which may already have exited."""
    return globals().get("MirrorProcess")


def GetRunningMirrorProcess():
    """Return the mirror server process handle, or None if it is unknown or already exited."""
    process = GetMirrorProcess()
    if process is not None and process.poll() is None:
        return process
    return None


def WaitForMirrorStop(host, port, process, timeout=None):
    """Wait until the mirror server is fully stopped.

    The process handle is used when it is available, otherwise the RCON port.
    """
    if timeout is None:
        timeout = CheckOption("stop_timeout")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None:
            if process.poll() is not None:
                return True
        elif not IsTcpPortOpen(host, port):
            return True
        time.sleep(CheckOption("stop_interval"))
    return False


@new_thread("MSR-Stop")
def StopMirrorServer(server):
    rcon_config = config["rcon"]
    host, port = rcon_config["host"], rcon_config["port"]
    # Only trust the process handle if it is still alive before the stop command is sent
    process = GetRunningMirrorProcess()
    conn = RconInit(host, port, rcon_config["password"])
    try:
        connected = conn.connect()
    except Exception as e:
        server.reply("§b[MirrorServerReforged] §6无法连接镜像服的Rcon！原因为：{}".format(e))
        return
    if not connected:
        server.reply(
            "§b[MirrorServerReforged] §6无法连接镜像服的Rcon，请检查配置文件中的Rcon信息！"
        )
        return
    try:
        conn.send_command("stop", max_retry_time=3)
    except Exception as e:
        server.reply("§b[MirrorServerReforged] §6无法停止镜像服！原因为：{}".format(e))
        return
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass

    # Report the timeout value that was really used
    timeout = CheckOption("stop_timeout")
    if WaitForMirrorStop(host, port, process, timeout):
        server.reply("§b[MirrorServerReforged] §6镜像服已彻底关闭！")
    else:
        server.reply(
            "§b[MirrorServerReforged] §6已向镜像服发送关闭指令，但等待{}秒后仍未检测到镜像服关闭，请手动检查！".format(
                timeout
            )
        )


def Stop(server):
    # global Started
    # if Started:
    if config["rcon"]["enable"]:
        server.reply("§b[MirrorServerReforged] §6正在向镜像服发送关闭指令……")
        StopMirrorServer(server)
    else:
        server.reply(
            "§b[MirrorServerReforged] §6无法通过Rcon停止镜像服，因为Rcon未开启！"
        )
    # else:
    #     server.reply('§b[MirrorServerReforged] §6镜像服未运行！')


def Reload(server):
    server.reply("§b[MirrorServerReforged] §6正在重载配置文件……")
    ConfigToDo()
    server.reply("§b[MirrorServerReforged] §6重载完成！")


def DisplayHelp(server):
    for line in help_msg.splitlines():
        server.reply(line)


@new_thread("MSR-Init")
def MCDRInitalize(server):
    if MCDR:
        try:
            os.chdir(GetMirrorDir())
            system = sys.platform
            if system == "win32":
                # Windows NT Platform
                os.system("python -m mcdreforged init")
            else:
                # Linux/Unix Platform
                os.system("python3 -m mcdreforged init")
            server.reply("§b[MirrorServerReforged] §6初始化已完成！")
        except Exception as e:
            server.reply("§b[MirrorServerReforged] §6初始化失败！原因为：{}".format(e))
        os.chdir(path)
    else:
        server.reply("§b[MirrorServerReforged] §6非MCDR类服务器，无需初始化！")


def Initalize(server):
    server.reply("§b[MirrorServerReforged] §6已启动初始化进程！")
    MCDRInitalize(server)


def ConfigToDo():
    if os.path.exists(GetConfigPath()):
        LoadConfig()
    else:
        CreateConfig()


def on_load(server, prev):
    ConfigToDo()  # Load Config
    InitalizeOnFirstRun()  # Initalize if this is the first run
    # builder = SimpleCommandBuilder()
    server.register_help_message("!!msr", "MirrorServerReforged 帮助")
    server.register_command(
        Literal("!!msr")
        .runs(DisplayHelp)
        .then(Literal("help").runs(DisplayHelp))
        .then(Literal("sync").runs(Sync))
        .then(Literal("reload").runs(Reload))
        .then(Literal("start").runs(Start))
        .then(Literal("stop").runs(Stop))
        .then(Literal("init").runs(Initalize))
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
