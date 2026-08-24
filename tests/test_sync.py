import logging
from pathlib import Path

import mirror_server_reforged as msr


class FakeInterface:
    def __init__(self):
        self.commands = []
        self.messages = []
        self.logger = logging.getLogger('mirror-server-reforged-test')

    def execute(self, command):
        self.commands.append(command)

    def say(self, message):
        self.messages.append(message)


def test_copy_world_replaces_old_copy_and_ignores_session_lock(tmp_path):
    source_root = tmp_path / 'server'
    target_root = tmp_path / 'mirror' / 'server'
    source_world = source_root / 'world'
    target_world = target_root / 'world'
    source_world.mkdir(parents=True)
    target_world.mkdir(parents=True)
    (source_world / 'level.dat').write_text('new', encoding='utf-8')
    (source_world / 'session.lock').write_text('locked', encoding='utf-8')
    (target_world / 'level.dat').write_text('old', encoding='utf-8')
    (target_world / 'obsolete.dat').write_text('old', encoding='utf-8')

    msr.CopyWorld(str(source_root), str(target_root), 'world')

    assert (target_world / 'level.dat').read_text(encoding='utf-8') == 'new'
    assert not (target_world / 'obsolete.dat').exists()
    assert not (target_world / 'session.lock').exists()
    assert not list(target_root.glob('.world-msr-sync-*'))


def test_missing_source_preserves_existing_mirror(tmp_path):
    source_root = tmp_path / 'server'
    target_root = tmp_path / 'mirror' / 'server'
    target_world = target_root / 'world'
    target_world.mkdir(parents=True)
    (target_world / 'level.dat').write_text('keep', encoding='utf-8')

    try:
        msr.CopyWorld(str(source_root), str(target_root), 'world')
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('CopyWorld should reject a missing source')

    assert (target_world / 'level.dat').read_text(encoding='utf-8') == 'keep'


def test_server_sync_keeps_saving_disabled_until_copy_finishes(tmp_path, monkeypatch):
    source_root = tmp_path / 'server'
    target_root = tmp_path / 'mirror' / 'server'
    source_world = source_root / 'world'
    source_world.mkdir(parents=True)
    (source_world / 'level.dat').write_text('data', encoding='utf-8')
    monkeypatch.setattr(msr, 'config', {
        'world': ['world'],
        'source': str(source_root),
        'target': str(target_root),
    })
    interface = FakeInterface()
    msr.syncFlag = True

    msr.ServerSync.original(interface)

    assert interface.commands == ['save-off', 'save-all', 'save-on']
    assert all('\u00a7' not in command for command in interface.commands)
    assert interface.messages[-1].to_plain_text().startswith(
        '[MirrorServerReforged] \u540c\u6b65\u5b8c\u6210'
    )
    assert msr.syncFlag is False


def test_server_sync_reenables_saving_and_reports_copy_failure(tmp_path, monkeypatch):
    interface = FakeInterface()
    monkeypatch.setattr(msr, 'config', {
        'world': ['missing'],
        'source': str(tmp_path / 'server'),
        'target': str(tmp_path / 'mirror'),
    })
    msr.syncFlag = True

    msr.ServerSync.original(interface)

    assert interface.commands[-1] == 'save-on'
    assert '同步失败' in interface.messages[-1].to_plain_text()
    assert msr.syncFlag is False

