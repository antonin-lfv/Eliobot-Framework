"""Contrats de l'assistant : MCP réel, fournisseurs simulés, aucune action physique."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server/control-dashboard/fastapi-dashboard'))
from assistant_config import ConfigStore, Settings
from assistant_providers import ModelConversation, ProviderError
from robot_mcp import local_mcp_client


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv('ASSISTANT_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('GEMINI_API_KEY', 'test-secret-not-for-display')
    spec = importlib.util.spec_from_file_location('assistant_test_app', ROOT / 'server/control-dashboard/fastapi-dashboard/app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._publish = Mock(return_value=True)
    module._mqttc = Mock()
    module._state['connected'] = True
    module._state['last_seen_mono'] = time.monotonic()
    return module


class FakeConversation:
    replies = []
    def __init__(self, *args):
        self.index = 0
    async def next(self):
        value = self.replies[self.index]
        self.index += 1
        return value
    def results(self, values):
        pass
    async def close(self):
        pass


def install_replies(monkeypatch, replies):
    class Conversation(FakeConversation):
        pass
    Conversation.replies = replies
    monkeypatch.setattr('assistant.ModelConversation', Conversation)


HEADERS = {'X-Elio-Assistant':'1'}
SESSION = 'test-conversation-123456'


def test_keys_are_loaded_but_never_returned_or_echoed(server):
    with TestClient(server.app) as client:
        r = client.get('/assistant/config')
        assert r.json()['gemini_key_configured'] is True
        assert 'test-secret-not-for-display' not in r.text
        assert client.post('/assistant/config', json={'gemini_key':'new-secret'}, headers=HEADERS).status_code == 200
        assert 'new-secret' not in client.get('/assistant/config').text
        invalid = client.post('/assistant/config', json={'gemini_key':'sensitive'*300}, headers=HEADERS)
        assert invalid.status_code == 422 and 'sensitive' not in invalid.text


def test_mutations_require_same_origin_header_and_mcp_is_private(server):
    with TestClient(server.app) as client:
        assert client.post('/assistant/config', json={}).status_code == 403
        assert client.post('/assistant/config', json={}, headers={**HEADERS,'Origin':'https://other.example'}).status_code == 403
        assert client.post('/mcp/', json={}).status_code == 401


def test_chat_uses_real_mcp_tools_and_preserves_history(server, monkeypatch):
    install_replies(monkeypatch, [('', [{'name':'get_robot_state','arguments':{}}]), ('La batterie est inconnue.', [])])
    with TestClient(server.app) as client:
        response = client.post('/assistant/chat', json={'session':SESSION,'message':'Quelle est la batterie ?'}, headers=HEADERS)
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert any(event.get('name') == 'get_robot_state' and event['status'] == 'done' for event in events)
        assert events[-1]['type'] == 'done'
        history = client.get('/assistant/history/' + SESSION).json()['messages']
        assert history[-1]['text'] == 'La batterie est inconnue.'
        assert history[-1]['actions'][0]['tool'] == 'get_robot_state'
        assert not any(t == 'elio/command/move' for t, p in (call.args for call in server._publish.call_args_list))


def test_unknown_tool_is_not_executed(server, monkeypatch):
    install_replies(monkeypatch, [('', [{'name':'execute_shell','arguments':{'command':'bad'}}])])
    with TestClient(server.app) as client:
        r = client.post('/assistant/chat', json={'session':SESSION,'message':'Bonjour'}, headers=HEADERS)
        assert 'outil inconnu' in r.text
        assert not any(t == 'elio/command/move' for t, p in (call.args for call in server._publish.call_args_list))


@pytest.mark.asyncio
async def test_mcp_movement_is_bounded_and_rejects_nonfinite_values(server):
    async with server.assistant.mcp.session_manager.run():
        async with local_mcp_client(server.assistant.mcp_app) as client:
            bad = await client.call_tool('move_robot', {'generation':0,'direction':'forward','duration':99,'speed':35})
            assert bad.isError
            assert not server._publish.called
            good = await client.call_tool('move_robot', {'generation':0,'direction':'forward','duration':.2,'speed':35})
            assert not good.isError
            assert server._publish.call_args.args == ('elio/command/move', 'stop')
    with pytest.raises(ValueError):
        await server.assistant.actions.move(0,'forward',float('nan'),35)


@pytest.mark.asyncio
async def test_mcp_turn_70_degrees_sends_right_then_stop(server):
    server._state['battery_v'] = 3.8
    server._state['status']['turn_factor'] = 1.2
    async with server.assistant.mcp.session_manager.run():
        async with local_mcp_client(server.assistant.mcp_app) as client:
            result = await client.call_tool('turn_robot', {'generation':0, 'direction':'right', 'degrees':70})
    assert not result.isError
    data = result.structuredContent or json.loads(result.content[0].text)
    assert data['approximate'] and not data['physical_completion_confirmed']
    assert data['requested_degrees'] == 70
    assert data['duration'] == pytest.approx(1.2, abs=.002)
    assert data['calibration_source'] == 'robot_config'
    assert data['battery_source'] == 'telemetry'
    moves = [call.args[1] for call in server._publish.call_args_list if call.args[0] == 'elio/command/move']
    assert moves[:-1] and set(moves[:-1]) == {'right'}
    assert moves[-1] == 'stop'


@pytest.mark.asyncio
async def test_turn_supports_older_robot_and_calibration_changes_duration(server):
    actions = server.assistant.actions
    actions.move = AsyncMock(return_value={'physical_completion_confirmed':False})
    default = await actions.turn(0, 'left', 70, 35)
    assert default['calibration_source'] == 'default'
    assert default['battery_source'] == 'nominal'
    server._state['status']['turn_factor'] = 1.5
    calibrated = await actions.turn(0, 'left', 70, 35)
    assert calibrated['duration'] == pytest.approx(default['duration'] * 1.5, abs=.002)
    server._state['battery_v'] = 4.2
    charged = await actions.turn(0, 'left', 70, 35)
    assert charged['duration'] < calibrated['duration']


@pytest.mark.asyncio
@pytest.mark.parametrize('degrees,speed,factor,battery', [
    (float('nan'),35,1,3.8), (70,100,1,3.8), (360,15,1,3.8),
    (1,70,1,3.8), (70,35,float('inf'),3.8), (70,35,1,float('nan')),
])
async def test_invalid_turn_never_moves(server, degrees, speed, factor, battery):
    server._state['status']['turn_factor'] = factor
    server._state['battery_v'] = battery
    with pytest.raises(ValueError):
        await server.assistant.actions.turn(0, 'right', degrees, speed)
    assert not server._publish.called


@pytest.mark.asyncio
async def test_turn_preserves_takeover_and_generation_checks(server):
    server._state['control']['active'] = 'exploration'
    with pytest.raises(ValueError, match='autonomie'):
        await server.assistant.actions.turn(0, 'right', 70, 35)
    server.assistant.actions.invalidate()
    with pytest.raises(ValueError, match='périmée'):
        await server.assistant.actions.turn(0, 'right', 70, 35)
    assert not server._publish.called


@pytest.mark.asyncio
async def test_takeover_invalidates_old_actions_without_stopping_new_driver(server):
    actions = server.assistant.actions
    task = asyncio.create_task(actions.move(0, 'forward', 2, 30))
    await asyncio.sleep(.02)
    actions.invalidate()
    await server.cmd_move(server.MoveCmd(direction='right'))
    with pytest.raises(ValueError):
        await task
    assert server._publish.call_args.args == ('elio/command/move', 'right')
    with pytest.raises(ValueError):
        await actions.move(0,'forward',.1,30)


@pytest.mark.asyncio
async def test_autonomy_confirmation_and_missing_robot_are_preserved(server):
    server._state['mode'] = 'exploration'
    server._state['control']['active'] = 'exploration'
    async with server.assistant.mcp.session_manager.run():
        async with local_mcp_client(server.assistant.mcp_app) as client:
            r = await client.call_tool('move_robot', {'generation':0,'direction':'forward','duration':.2,'speed':35})
            assert r.isError
            assert not server._publish.called
            server._state['mode'] = 'idle'
            server._state['control']['active'] = 'idle'
            server._state['last_seen_mono'] = 0
            r = await client.call_tool('move_robot', {'generation':0,'direction':'forward','duration':.2,'speed':35})
            assert r.isError
            assert not server._publish.called


def test_stop_during_inference_cancels_late_movement(server, monkeypatch):
    started = threading.Event()
    class SlowConversation(FakeConversation):
        async def next(self):
            started.set()
            await asyncio.sleep(10)
            return '', [{'name':'move_robot','arguments':{'direction':'forward','duration':1,'speed':30}}]
    monkeypatch.setattr('assistant.ModelConversation', SlowConversation)
    with TestClient(server.app) as client:
        responses = []
        thread = threading.Thread(target=lambda: responses.append(client.post('/assistant/chat', json={'session':SESSION,'message':'Avance'}, headers=HEADERS)))
        thread.start()
        assert started.wait(3)
        assert client.post('/command/stop').status_code == 200
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert 'interrompue' in responses[0].text
        assert not any(p == 'forward' for t,p in (call.args for call in server._publish.call_args_list))


def test_switching_and_deletion_are_blocked_or_explicit(server):
    with TestClient(server.app) as client:
        assert client.post('/assistant/ollama/uninstall', json={}, headers=HEADERS).status_code == 422
        assert client.post('/assistant/config', json={'ollama_kind':'remote','ollama_url':'http://192.168.1.4:11434'}, headers=HEADERS).status_code == 200
        assert client.post('/assistant/ollama/uninstall', json={'confirm':True}, headers=HEADERS).status_code == 409
        assert client.post('/assistant/ollama/delete', json={'confirm':True,'model':'qwen3:4b'}, headers=HEADERS).status_code == 422
        assert client.post('/assistant/ollama/disconnect', json={}, headers=HEADERS).status_code == 200
        assert client.get('/assistant/config').json()['provider'] == 'gemini'
        assert client.get('/assistant/config').json()['ollama_enabled'] is False


@pytest.mark.asyncio
async def test_gemini_preserves_signature_and_returns_tool_results():
    from types import SimpleNamespace
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests)==1:
            return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'thoughtSignature':'signature','functionCall':{'name':'get_robot_state','args':{}}}]}}]})
        return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'text':'Prêt.'}]}}]})
    tools=[SimpleNamespace(name='get_robot_state',description='État',inputSchema={'type':'object','properties':{}})]
    conversation=ModelConversation(Settings(), 'secret', [{'role':'user','text':'État ?'}], tools)
    await conversation.client.aclose()
    conversation.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    _,calls=await conversation.next()
    conversation.results([(calls[0],{'battery_v':3.7})])
    text,_=await conversation.next()
    assert text=='Prêt.'
    assert requests[1]['contents'][1]['parts'][0]['thoughtSignature']=='signature'
    assert requests[1]['contents'][2]['parts'][0]['functionResponse']['response']['battery_v']==3.7
    await conversation.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('code,word',[(429,'Quota'),(401,'Accès'),(404,'introuvable')])
async def test_provider_errors_do_not_leak_response_bodies(code,word):
    c=ModelConversation(Settings(), 'secret', [{'role':'user','text':'Bonjour'}], [])
    await c.client.aclose()
    c.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(code,json={'error':'secret'})))
    with pytest.raises(ProviderError,match=word) as error:
        await c.next()
    assert 'secret' not in str(error.value)
    assert error.value.code == ('quota_exceeded' if code == 429 else 'provider_error')
    await c.close()

@pytest.mark.asyncio
async def test_ollama_tool_protocol_and_invalid_output():
    from types import SimpleNamespace
    seen=[]
    def handler(request):
        seen.append(json.loads(request.content))
        if len(seen)==1:
            return httpx.Response(200,json={'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'move_robot','arguments':{'direction':'left','duration':.1,'speed':20}}}]}})
        return httpx.Response(200,json={'message':{'role':'assistant','content':'Commande envoyée.'}})
    tool=SimpleNamespace(name='move_robot',description='Bouger',inputSchema={'type':'object','properties':{'generation':{'type':'integer'},'duration':{'type':'number'}},'required':['generation','duration']})
    c=ModelConversation(Settings(provider='ollama'),'', [{'role':'user','text':'Tourne un peu'}],[tool])
    await c.client.aclose();c.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    _,calls=await c.next()
    assert 'generation' not in seen[0]['tools'][0]['function']['parameters']['properties']
    assert seen[0]['think'] is False
    c.results([(calls[0],{'transmitted':True})])
    text,_=await c.next()
    assert text=='Commande envoyée.'
    assert seen[1]['messages'][-1]['role']=='tool'
    await c.close()


@pytest.mark.asyncio
async def test_expired_movement_releases_its_slot(server):
    actions=server.assistant.actions
    task=asyncio.create_task(actions.move(0,'forward',2,30))
    await asyncio.sleep(.02)
    with server._lock:
        server._set_active('idle')
    with pytest.raises(Exception):
        await task
    assert not actions.moving
    # La modification de révision ne bloque pas indéfiniment le prochain mouvement.
    await actions.move(0,'left',.1,20)


def test_stop_does_not_claim_success_when_broker_rejects(server):
    server._publish=Mock(return_value=False)
    with TestClient(server.app) as client:
        response=client.post('/command/stop')
        assert response.status_code==503


def test_switch_keeps_history_and_disconnect_prevents_ollama_call(server,monkeypatch):
    install_replies(monkeypatch,[('Bonjour.',[])])
    with TestClient(server.app) as client:
        client.post('/assistant/chat',json={'session':SESSION,'message':'Bonjour'},headers=HEADERS)
        assert client.post('/assistant/config',json={'provider':'ollama'},headers=HEADERS).status_code==200
        assert client.get('/assistant/history/'+SESSION).json()['messages'][-1]['text']=='Bonjour.'
        client.post('/assistant/ollama/disconnect',json={},headers=HEADERS)
        r=client.post('/assistant/chat',json={'session':SESSION,'message':'Avance'},headers=HEADERS)
        assert r.status_code==409
        assert client.get('/assistant/config').json()['provider']=='ollama'


def test_malformed_json_is_a_validation_error(server):
    with TestClient(server.app) as client:
        for path in ['/assistant/chat','/assistant/config','/assistant/ollama/start']:
            assert client.post(path,content='invalid',headers=HEADERS).status_code==422


def test_external_mcp_can_initialize_with_explicit_token(server,monkeypatch):
    monkeypatch.setenv('ELIO_MCP_TOKEN','test-private-mcp-token')
    headers={'Authorization':'Bearer test-private-mcp-token','Accept':'application/json, text/event-stream'}
    with TestClient(server.app) as client:
        r=client.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
        assert r.status_code==200
        assert r.json()['result']['serverInfo']['name']=='ElioBot'


@pytest.mark.parametrize('provider', ['gemini', 'ollama'])
def test_quota_preserves_completed_actions_and_offers_switch_only_from_gemini(server, monkeypatch, provider):
    class QuotaConversation(FakeConversation):
        async def next(self):
            if self.index == 0:
                self.index += 1
                return '', [{'name':'move_robot', 'arguments':{'direction':'right', 'duration':.1, 'speed':35}}]
            raise ProviderError('Quota de test atteint.', code='quota_exceeded')
    monkeypatch.setattr('assistant.ModelConversation', QuotaConversation)
    server.assistant.config.update({'provider':provider})
    with TestClient(server.app) as client:
        response = client.post('/assistant/chat', json={'session':SESSION, 'message':'Tourne un peu'}, headers=HEADERS)
        events = [json.loads(line) for line in response.text.splitlines()]
        error = next(item for item in events if item['type'] == 'error')
        assert error['code'] == 'quota_exceeded' and error['provider'] == provider
        assert error.get('suggested_provider') == ('ollama' if provider == 'gemini' else None)
        history = client.get('/assistant/history/' + SESSION).json()['messages']
        assert len(history[-1]['actions']) == 1
        assert history[-1]['error']['code'] == 'quota_exceeded'
        assert server.assistant.config.settings.provider == provider
        moves = [call.args[1] for call in server._publish.call_args_list if call.args[0] == 'elio/command/move']
        assert moves.count('right') == 1  # Aucune reprise après l'erreur, même après une action réussie.


def mock_ollama_show(monkeypatch, response):
    seen = []
    original = httpx.AsyncClient
    def handler(request):
        seen.append(request)
        return response
    monkeypatch.setattr('assistant.httpx.AsyncClient', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    return seen


def test_explicit_ollama_switch_checks_tools_and_preserves_history_without_replay(server, monkeypatch):
    history = server.assistant.history(SESSION)
    history.append({'role':'assistant', 'text':'Rotation déjà transmise.', 'actions':[{'tool':'turn_robot', 'result':{'ok':True}}]})
    seen = mock_ollama_show(monkeypatch, httpx.Response(200, json={'capabilities':['completion','tools']}))
    with TestClient(server.app) as client:
        assert client.post('/assistant/switch-to-ollama').status_code == 403
        result = client.post('/assistant/switch-to-ollama', json={}, headers=HEADERS)
        assert result.status_code == 200
        assert result.json()['config']['provider'] == 'ollama'
        assert client.get('/assistant/history/' + SESSION).json()['messages'] == history
        assert len(seen) == 1
        assert seen[0].url.path == '/api/show'
        assert json.loads(seen[0].content) == {'model':'qwen3:4b'}
        assert not server._publish.called


@pytest.mark.parametrize('code,info', [(404,{}), (503,{}), (200,{}), (200,{'capabilities':['completion']}),
                                    (200,{'capabilities':['tools'], 'remote_host':'https://ollama.com'})])
def test_unavailable_ollama_does_not_change_provider(server, monkeypatch, code, info):
    mock_ollama_show(monkeypatch, httpx.Response(code, json=info))
    with TestClient(server.app) as client:
        result = client.post('/assistant/switch-to-ollama', json={}, headers=HEADERS)
        assert result.status_code in (409,503)
        assert server.assistant.config.settings.provider == 'gemini'
        assert not server._publish.called


def test_disconnected_ollama_is_not_queried_or_reenabled_by_fallback(server, monkeypatch):
    server.assistant.config.update({'ollama_enabled':False})
    seen = mock_ollama_show(monkeypatch, httpx.Response(200, json={'capabilities':['tools']}))
    with TestClient(server.app) as client:
        result = client.post('/assistant/switch-to-ollama', json={}, headers=HEADERS)
        assert result.status_code == 409
        assert not seen
        assert server.assistant.config.settings.provider == 'gemini'
