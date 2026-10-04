import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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
    GetOnlinePlayerCount,
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

# Defaults of the idle shutdown. As above, these are only the defaults for the values
# missing from the config file.
DEFAULT_IDLE_OPTIONS = {
    # Whether the mirror server is shut down automatically once it stays empty
    "enable": False,
    # Longest time (in second) the mirror server may stay empty before it is shut down
    "idle_timeout": 1800,
    # How long (in second) before that shutdown the players are warned about it
    "notice_advance": 300,
    # How many seconds before that shutdown the countdown is broadcast every second
    "countdown": 10,
    # Interval (in second) between two online player checks while the shutdown is still far
    # away. The players are not going anywhere before the countdown, so a check now and then
    # is enough, and it keeps the watchdog cheap
    "check_interval": 300,
    # Interval (in second) between two online player checks once the players have been
    # warned: from then on the shutdown can happen at any moment, so the checks get fine
    "near_check_interval": 10,
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
    "idle_shutdown": dict(DEFAULT_IDLE_OPTIONS),
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


class MirrorStopResult(Enum):
    STOPPED = auto()  # the mirror server is fully stopped
    RCON_FAILED = auto()  # the Rcon connection could not be established
    SEND_FAILED = auto()  # the stop command could not be delivered
    TIMEOUT = auto()  # the stop command was sent, but the mirror server outlived the wait


def CheckOption(name):
    return config.get("check", {}).get(name, DEFAULT_CHECK_OPTIONS[name])


def IdleOption(name):
    return config.get("idle_shutdown", {}).get(name, DEFAULT_IDLE_OPTIONS[name])


def FormatDuration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return "{}秒".format(seconds)
    if seconds % 60 == 0:
        return "{}分钟".format(seconds // 60)
    return "{}分{}秒".format(seconds // 60, seconds % 60)


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
    idle_shutdown = config.setdefault("idle_shutdown", {})
    for name, value in DEFAULT_IDLE_OPTIONS.items():
        idle_shutdown.setdefault(name, value)
    CreateConfig()


def Broadcast(InterFace, message, color=RColor.gold):
    """Broadcast without putting legacy section signs in a server command."""
    InterFace.say(
        RTextList(RText("[MirrorServerReforged] ", RColor.aqua), RText(message, color))
    )


def MirrorBroadcast(InterFace, message, color=RColor.gold):
    """Broadcast the very same notice to the mirror server through Rcon."""
    rcon_config = config["rcon"]
    if not rcon_config["enable"]:
        return
    tellraw = RTextList(
        RText("[MirrorServerReforged] ", RColor.aqua), RText(message, color)
    )
    conn = RconInit(rcon_config["host"], rcon_config["port"], rcon_config["password"])
    try:
        if not conn.connect():
            raise RuntimeError("无法连接镜像服的Rcon")
        conn.send_command(
            "tellraw @a {}".format(tellraw.to_json_str()), max_retry_time=3
        )
    except Exception as e:
        InterFace.logger.warning(
            "[MirrorServerReforged] 无法向镜像服广播消息！原因为：{}".format(e)
        )
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


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


# The properties file is read on every online player check, and it only changes when the
# mirror server is reconfigured, so the parsed result is kept until the file it came from
# changes. `ConfigToDo` drops it as well, so a reload picks up an edited file right away.
mirror_properties = None
mirror_properties_source = None


def GetMirrorServerProperties():
    global mirror_properties, mirror_properties_source
    properties_path = FindServerProperties(GetMirrorServerDirectories())
    try:
        stamp = os.path.getmtime(properties_path) if properties_path else None
    except OSError:
        stamp = None
    source = (properties_path, stamp)
    if mirror_properties is None or mirror_properties_source != source:
        mirror_properties = ReadServerProperties(properties_path)
        mirror_properties_source = source
    return mirror_properties


def DropMirrorServerProperties():
    """Forget the cached mirror server properties, so the next read goes to the file."""
    global mirror_properties, mirror_properties_source
    mirror_properties = None
    mirror_properties_source = None


def GetMirrorOnlinePlayers():
    """Return the mirror server's online player count, or None when it cannot be read."""
    properties = GetMirrorServerProperties()
    if properties.port is None:
        return None
    return GetOnlinePlayerCount(properties.host, properties.port)


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


def SendMirrorStop():
    """Ask the mirror server to stop through Rcon, and wait until it is really gone.

    Returns a MirrorStopResult together with a message describing a failure, or None.
    """
    rcon_config = config["rcon"]
    host, port = rcon_config["host"], rcon_config["port"]
    # Only trust the process handle if it is still alive before the stop command is sent
    process = GetRunningMirrorProcess()
    conn = RconInit(host, port, rcon_config["password"])
    try:
        connected = conn.connect()
    except Exception as e:
        return MirrorStopResult.RCON_FAILED, "无法连接镜像服的Rcon！原因为：{}".format(e)
    if not connected:
        return (
            MirrorStopResult.RCON_FAILED,
            "无法连接镜像服的Rcon，请检查配置文件中的Rcon信息！",
        )
    try:
        conn.send_command("stop", max_retry_time=3)
    except Exception as e:
        return MirrorStopResult.SEND_FAILED, "无法停止镜像服！原因为：{}".format(e)
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass

    # Report the timeout value that was really used
    timeout = CheckOption("stop_timeout")
    if WaitForMirrorStop(host, port, process, timeout):
        return MirrorStopResult.STOPPED, None
    return (
        MirrorStopResult.TIMEOUT,
        "已向镜像服发送关闭指令，但等待{}秒后仍未检测到镜像服关闭，请手动检查！".format(timeout),
    )


@new_thread("MSR-Stop")
def StopMirrorServer(server):
    result, detail = SendMirrorStop()
    if result is MirrorStopResult.STOPPED:
        server.reply("§b[MirrorServerReforged] §6镜像服已彻底关闭！")
    else:
        server.reply("§b[MirrorServerReforged] §6{}".format(detail))


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


# The mirror server is shut down automatically once it has stayed empty for a while. The
# watchdog thread below owns that state, and `on_unload` is what stops it.
idle_stop_event = threading.Event()


def IdleShutdownProblem():
    """Return why the idle shutdown cannot work, or None when it can."""
    if not config["rcon"]["enable"]:
        return "Rcon 未开启，镜像服无法被自动关闭"
    if GetMirrorServerProperties().port is None:
        return "未找到镜像服的 server.properties，无法统计镜像服的在线人数"
    return None


def NextIdleCheckDelay(idle_seconds, problem):
    """How long to wait (in second) before the next online player check.

    The checks stay coarse while the shutdown is far away, and get fine once the players
    have been warned about it. The delay never runs past the next milestone, so neither the
    notice nor the countdown is pushed back by a coarse interval.

    Nothing is being counted while the shutdown is off or unusable, and only the config can
    change then, so a cheap local recheck is enough.
    """
    if problem is not None or not IdleOption("enable"):
        return max(1, IdleOption("near_check_interval"))
    timeout = IdleOption("idle_timeout")
    notice_at = timeout - IdleOption("notice_advance")
    countdown_at = timeout - IdleOption("countdown")
    if idle_seconds >= notice_at:
        interval = IdleOption("near_check_interval")
        milestone = countdown_at
    else:
        interval = IdleOption("check_interval")
        milestone = notice_at
    remaining = milestone - idle_seconds
    if remaining > 0:
        interval = min(interval, remaining)
    return max(1, interval)


def AutoStopMirrorServer(InterFace):
    """Stop the idle mirror server and tell the players how it went."""
    result, detail = SendMirrorStop()
    if result is MirrorStopResult.STOPPED:
        Broadcast(InterFace, "镜像服长时间无人使用，已自动关闭！")
    else:
        InterFace.logger.warning("[MirrorServerReforged] 自动关闭镜像服失败：{}".format(detail))
        Broadcast(InterFace, "自动关闭镜像服失败，请手动检查！", RColor.red)


def CancelIdleShutdown(InterFace, message, color=RColor.gold):
    """Tell both the main server and the mirror server that the countdown was called off."""
    Broadcast(InterFace, message, color)
    MirrorBroadcast(InterFace, message, color)


def CheckMirrorStillEmpty(InterFace):
    """Return True while the mirror server is still empty, calling the shutdown off if not.

    The countdown is checked every second, so a player joining in the middle of it is seen
    right away instead of at the next coarse check.
    """
    players = GetMirrorOnlinePlayers()
    if players is None:
        # A probe failure is an admin problem, so it only goes to the main server
        Broadcast(InterFace, "无法确认镜像服的在线人数，已取消自动关闭！", RColor.red)
        return False
    if players > 0:
        CancelIdleShutdown(InterFace, "镜像服有玩家加入，倒计时中止！")
        return False
    return True


def RunMirrorIdleShutdown(InterFace, stop_event):
    """Count the last seconds down, then stop the mirror server.

    A player showing up during the countdown calls it off: the mirror server keeps
    running, and the watchdog starts the whole idle check over again.
    """
    for remaining in range(IdleOption("countdown"), 0, -1):
        if not CheckMirrorStillEmpty(InterFace):
            return
        Broadcast(InterFace, "镜像服还有{}秒关闭！".format(remaining))
        if stop_event.wait(1):
            return
    # A player may have joined during the last broadcast, so look once more before the stop
    if CheckMirrorStillEmpty(InterFace):
        AutoStopMirrorServer(InterFace)


@new_thread("MSR-Idle")
def WatchMirrorIdle(InterFace):
    # Bind the event locally: a plugin reload replaces the module level one, and this thread
    # still has to be stoppable by the `on_unload` of the plugin instance that started it
    stop_event = idle_stop_event
    idle_seconds = 0
    noticed = False
    problem = None
    last_check = time.monotonic()
    # Check first and wait afterwards, so that a setup the idle shutdown cannot work with is
    # reported as soon as the plugin loads instead of a whole interval later
    while not stop_event.is_set():
        now = time.monotonic()
        elapsed = now - last_check
        last_check = now

        if not IdleOption("enable"):
            problem = None
            idle_seconds = 0
            noticed = False
        else:
            current_problem = IdleShutdownProblem()
            if current_problem != problem:
                if current_problem is not None:
                    InterFace.logger.warning(
                        "[MirrorServerReforged] 自动关闭镜像服已启用，但{}".format(current_problem)
                    )
                problem = current_problem
            if current_problem is not None:
                idle_seconds = 0
                noticed = False
            else:
                players = GetMirrorOnlinePlayers()
                if players is None or players > 0:
                    idle_seconds = 0
                    noticed = False
                else:
                    idle_seconds += elapsed
                    timeout = IdleOption("idle_timeout")
                    advance = IdleOption("notice_advance")
                    if not noticed and idle_seconds >= timeout - advance:
                        noticed = True
                        Broadcast(
                            InterFace, "镜像服还有{}关闭！".format(FormatDuration(advance))
                        )
                    if idle_seconds >= timeout - IdleOption("countdown"):
                        RunMirrorIdleShutdown(InterFace, stop_event)
                        idle_seconds = 0
                        noticed = False
                        last_check = time.monotonic()

        if stop_event.wait(NextIdleCheckDelay(idle_seconds, problem)):
            break


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
    # The mirror server may have been reconfigured while the plugin was running, and its
    # properties are cached, so drop that cache before the new config is read
    DropMirrorServerProperties()
    if os.path.exists(GetConfigPath()):
        LoadConfig()
    else:
        CreateConfig()


def on_load(server, prev):
    global idle_stop_event
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
    idle_stop_event = threading.Event()
    WatchMirrorIdle(GetInterFace())


def on_unload(server):
    idle_stop_event.set()
