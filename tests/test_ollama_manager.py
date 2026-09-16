"""Cycle de vie Docker et propriété des ressources, sans daemon ni téléchargement."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from docker.errors import NotFound

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv('MANAGER_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('HOSTNAME','manager-container')
    spec=importlib.util.spec_from_file_location('manager_test',ROOT/'server/control-dashboard/ollama-manager/manager.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client=Mock()
    monkeypatch.setattr(module.docker,'from_env',lambda **kwargs:client)
    return module,client


def resources(module,client):
    container=Mock(attrs={'Config':{'Labels':{module.LABEL:module.OWNER}}},status='running')
    volume=Mock(attrs={'Labels':{module.LABEL:module.OWNER}})
    client.containers.get.return_value=container
    client.volumes.get.return_value=volume
    return container,volume


def test_uninstall_preserves_models_by_default(manager):
    module,client=manager;container,volume=resources(module,client)
    result=module.operate('uninstall',module.Operation(confirm=True))
    assert result['ok']
    container.stop.assert_called_once_with(timeout=10)
    container.remove.assert_called_once_with()
    volume.remove.assert_not_called()
    client.images.remove.assert_not_called()


def test_uninstall_deletes_only_owned_volume_when_explicit(manager):
    module,client=manager;container,volume=resources(module,client)
    module.operate('uninstall',module.Operation(confirm=True,erase_data=True))
    volume.remove.assert_called_once_with()
    client.images.remove.assert_not_called()


def test_rejects_preexisting_unowned_resources_before_mutating(manager):
    module,client=manager;container,volume=resources(module,client)
    volume.attrs={'Labels':{'other':'owner'}}
    with pytest.raises(HTTPException) as error:
        module.operate('uninstall',module.Operation(confirm=True,erase_data=True))
    assert error.value.status_code==409
    container.stop.assert_not_called();container.remove.assert_not_called();volume.remove.assert_not_called()


def test_repeated_uninstall_is_idempotent(manager):
    module,client=manager
    client.containers.get.side_effect=NotFound('absent')
    client.volumes.get.side_effect=NotFound('absent')
    assert module.operate('uninstall',module.Operation(confirm=True,erase_data=True))['ok']


def test_start_reuses_owned_installation(manager):
    module,client=manager;container,volume=resources(module,client)
    module.operate('start',module.Operation())
    container.start.assert_called_once()
    client.images.pull.assert_not_called();client.containers.create.assert_not_called()


def test_new_install_has_no_published_port_and_only_owned_volume(manager):
    module,client=manager
    current=Mock(attrs={'NetworkSettings':{'Networks':{'project_elio-net':{}}}})
    client.containers.get.side_effect=lambda name: current if name=='manager-container' else (_ for _ in ()).throw(NotFound('absent'))
    client.volumes.get.side_effect=NotFound('absent')
    module.operate('start',module.Operation())
    args=client.containers.create.call_args.kwargs
    assert 'ports' not in args
    assert list(args['volumes'])==[module.VOLUME]
    assert args['labels']=={module.LABEL:module.OWNER}
    assert args['environment']['OLLAMA_NO_CLOUD']=='1'


def test_manager_requires_token_and_fixed_operations(manager):
    module,client=manager;resources(module,client)
    with TestClient(module.app) as http:
        assert http.post('/uninstall',json={'confirm':True}).status_code==401
        headers={'Authorization':'Bearer '+module.TOKEN}
        assert http.post('/exec',headers=headers,json={}).status_code==422
        assert http.post('/start',headers=headers,json={'image':'untrusted'}).status_code==422
        assert http.post('/uninstall',headers=headers,json={}).status_code==422


@pytest.mark.parametrize('system,arch,expected',[('Darwin','arm64','native'),('Windows','AMD64','native'),('Linux','aarch64','managed'),('Linux','x86_64','managed')])
def test_setup_records_actual_host_platform(monkeypatch,system,arch,expected):
    spec=importlib.util.spec_from_file_location('setup_test',ROOT/'server/control-dashboard/setup.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module.platform,'system',lambda:system)
    monkeypatch.setattr(module.platform,'machine',lambda:arch)
    info=module.detect_host()
    assert info['system']==system and info['architecture']==arch
    assert info['ollama_recommendation']==expected
