"""Utility helpers for MirrorServerReforged.

The functions here do not depend on the plugin's state: they take the values they need
as arguments, and ``__init__.py`` passes in the config.
"""
import json
import os
import socket
import struct

import javaproperties

from mcdreforged.api.utils import Serializable


def ToAbsolutePath(base_dir, target):
    return target if os.path.isabs(target) else os.path.join(base_dir, target)


def FindServerProperties(candidate_dirs):
    for directory in candidate_dirs:
        candidate = os.path.join(directory, "server.properties")
        if os.path.isfile(candidate):
            return candidate
    return None


def GetLogDirectories(server_dirs, base_dir):
    """Return the log directories of the mirror server, derived from its server dirs.

    A parent directory is the MCDR instance wrapping the server, so its log counts too,
    unless the parent is base_dir itself, which holds the main server's logs.
    """
    directories = []
    for server_dir in server_dirs:
        candidates = [os.path.join(server_dir, "logs")]
        parent = os.path.dirname(os.path.normpath(server_dir))
        if os.path.normpath(parent) != os.path.normpath(base_dir):
            candidates.append(os.path.join(parent, "logs"))
        for candidate in candidates:
            if candidate not in directories:
                directories.append(candidate)
    return directories


def GetNewestLogMtime(log_directories):
    newest = None
    for log_dir in log_directories:
        try:
            names = os.listdir(log_dir)
        except OSError:
            continue
        for name in names:
            if not name.endswith(".log"):
                continue
            try:
                mtime = os.path.getmtime(os.path.join(log_dir, name))
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


class MirrorServerProperties(Serializable):
    server_ip: str = ""
    server_port: str = ""

    @property
    def host(self):
        """The address to probe: server-ip when usable, else the loopback address."""
        if self.server_ip in ("", "0.0.0.0"):
            return "127.0.0.1"
        return self.server_ip

    @property
    def port(self):
        """server-port as an int, or None when it is missing or not a number."""
        try:
            return int(self.server_port)
        except ValueError:
            return None


def ReadServerProperties(properties_path):
    if properties_path is None:
        return MirrorServerProperties.get_default()
    try:
        # utf-8-sig drops a BOM, which would otherwise end up glued to the first key
        with open(properties_path, "r", encoding="utf-8-sig", errors="replace") as file:
            parsed = javaproperties.load(file)
    except (OSError, UnicodeDecodeError):
        return MirrorServerProperties.get_default()
    # server-port -> server_port, so the keys map onto the field names
    raw = {key.replace("-", "_"): value for key, value in parsed.items()}
    return MirrorServerProperties.deserialize(raw)


def IsTcpPortOpen(host, port, timeout=1):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def EncodeVarInt(value):
    data = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            data.append(byte | 0x80)
        else:
            data.append(byte)
            return bytes(data)


def DecodeVarInt(sock):
    value = 0
    shift = 0
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise OSError("连接已被对端关闭")
        byte = chunk[0]
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
        shift += 7
        if shift > 35:
            raise OSError("VarInt 过长")


# A server answers a status request regardless of the protocol version it carries, so
# this only bootstraps the first request
BOOTSTRAP_PROTOCOL_VERSION = 0

_protocol_version = None


def ReadStatusPayload(host, port, protocol_version, timeout=2):
    """Do a Server List Ping handshake and return the raw status payload, or None."""
    try:
        with socket.create_connection((host, port), timeout) as connection:
            connection.settimeout(timeout)
            host_bytes = host.encode("utf-8")
            handshake = (
                b"\x00"
                + EncodeVarInt(protocol_version)
                + EncodeVarInt(len(host_bytes))
                + host_bytes
                + struct.pack(">H", port)
                + b"\x01"
            )
            connection.sendall(EncodeVarInt(len(handshake)) + handshake)
            connection.sendall(EncodeVarInt(1) + b"\x00")
            DecodeVarInt(connection)  # packet length
            if DecodeVarInt(connection) != 0:  # packet id
                return None
            length = DecodeVarInt(connection)
            if length <= 0:
                return None
            payload = b""
            while len(payload) < length:
                chunk = connection.recv(length - len(payload))
                if not chunk:
                    return None
                payload += chunk
            return payload
    except (OSError, struct.error):
        return None


def SendStatusRequest(host, port, protocol_version, timeout=2):
    payload = ReadStatusPayload(host, port, protocol_version, timeout)
    if payload is None:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def GetServerProtocolVersion(host, port, timeout=2):
    """Return the protocol version the server reports, caching the answer.

    Returns None when the server does not answer.
    """
    global _protocol_version
    if _protocol_version is None:
        request_version = BOOTSTRAP_PROTOCOL_VERSION
    else:
        request_version = _protocol_version
    status = SendStatusRequest(host, port, request_version, timeout)
    if status is None:
        return None
    protocol = (status.get("version") or {}).get("protocol")
    if isinstance(protocol, int):
        _protocol_version = protocol
        return protocol
    return None


def IsMinecraftServerReady(host, port, timeout=2):
    return GetServerProtocolVersion(host, port, timeout) is not None
