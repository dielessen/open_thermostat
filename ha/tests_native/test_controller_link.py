"""Exact native E32 HTTP contract, privacy, bounds and cleanup; no live device."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_room_editor import configured
from custom_components.open_thermostat.product import configuration_snapshot

from custom_components.open_thermostat import controller_link as link

BASE = "http://192.168.50.10"
CSRF = "c" * 64
TAG = '"' + "d" * 64 + '"'


class Content:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            yield chunk


class Response:
    def __init__(self, value=None, *, raw=None, chunks=None, status=200, tag=None):
        self.status = status
        self.headers = {} if tag is None else {"ETag": tag}
        self.content = Content(chunks if chunks is not None else [
            raw if raw is not None else json.dumps(value).encode()])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False
        self.cookie_jar = SimpleNamespace(clear=Mock())

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self):
        self.closed = True


def setup(monkeypatch, *responses):
    session = Session(responses)
    create = Mock(return_value=session)
    monkeypatch.setattr(link.aiohttp, "ClientSession", create)
    return session, create


def login_responses():
    return [Response({"authenticated": True}),
            Response({"authenticated": True, "csrf": CSRF, "expires_in": 60})]


@pytest.mark.parametrize("address", [BASE, BASE + "/", "http://e32.local:8080",
                                     "https://thermostat.home", "http://[fd00::1]", "http://e32",
                                     "http://e32.fritz.box", "http://e32.home.arpa", "http://e32.localdomain",
                                     "http://e32.internal", "http://e32.lan", "http://heating.cellar.home.arpa",
                                     "http://10.1.2.3", "http://172.16.0.9"])
def test_local_address_preserves_one_explicit_origin(address):
    assert link.controller_address(address) == address.rstrip("/")


@pytest.mark.parametrize("address,origin", [("http://E32.LOCAL:80/", "http://e32.local"),
    ("https://E32.HOME:443", "https://e32.home"),
    ("http://192.168.50.10:80", BASE)])
def test_address_origin_matches_http_host_normalization(address, origin):
    assert link.controller_address(address) == origin


@pytest.mark.parametrize("address", ["", " " + BASE, BASE + "\n", "http://192.168.\n50.10",
    BASE + "/status", BASE + "/?token=private", BASE + "/#x", "http://user:password@e32.local",
    "ftp://e32.local", "http://example.com", "http://8.8.8.8", "http://127.0.0.1",
    "http://2130706433", "http://0x7f000001", "http://localhost", "http://169.254.1.2",
    "http://0.0.0.0", "http://[::1]", "http://e32.local:0", "http://e32.local:65536", None, True,
    "http://e32.example.org", "http://e32.box", "http://fritz.box.example.com", "http://e32.arpa",
    "http://e32..local", "http://-e32.local", "http://e32.local.", "http://100.64.0.1", "http://[fe80::1]"])
def test_invalid_address_cannot_become_a_proxy_or_credential_url(address):
    with pytest.raises(link.ControllerLinkError, match="^controller_address_invalid$"):
        link.controller_address(address)


class FakeResolver:
    def __init__(self, *hosts):
        self.hosts, self.closed = hosts, False

    async def resolve(self, host, port=0, family=None):
        return [{"hostname": host, "host": h, "port": port, "family": family, "proto": 0, "flags": 0}
                for h in self.hosts]

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("hosts,kept", [
    (("192.168.1.20",), ["192.168.1.20"]),
    (("93.184.216.34", "10.0.0.5"), ["10.0.0.5"]),         # a public answer is dropped
    (("fe80::1%eth0", "fd00::20"), ["fe80::1%eth0", "fd00::20"]),  # mDNS link-local is on the LAN
    (("169.254.10.2",), ["169.254.10.2"]),
])
async def test_a_name_is_only_contacted_at_a_local_network_address(monkeypatch, hosts, kept):
    made = []
    monkeypatch.setattr(link.aiohttp, "DefaultResolver", lambda: made.append(FakeResolver(*hosts)) or made[-1])
    results = await link.PrivateResolver().resolve("e32.fritz.box", 80)
    assert [r["host"] for r in results] == kept
    assert made[0].closed


@pytest.mark.asyncio
@pytest.mark.parametrize("hosts", [("8.8.8.8",), ("127.0.0.1",), ("::1",), ("0.0.0.0",), ("224.0.0.1",), ()])
async def test_a_name_resolving_to_a_public_or_loopback_address_is_never_contacted(monkeypatch, hosts):
    monkeypatch.setattr(link.aiohttp, "DefaultResolver", lambda: FakeResolver(*hosts))
    with pytest.raises(OSError, match="does not resolve to a local network address"):
        await link.PrivateResolver().resolve("e32.lan", 80)


@pytest.mark.asyncio
async def test_the_session_resolves_names_through_the_private_resolver(monkeypatch):
    session, create = setup(monkeypatch)
    async with link.ControllerClient("http://e32.fritz.box"):
        pass
    connector = create.call_args.kwargs["connector"]
    assert isinstance(connector._resolver, link.PrivateResolver)
    await connector.close()


@pytest.mark.asyncio
async def test_exact_login_cookie_csrf_readback_if_match_and_logout(monkeypatch):
    session, create = setup(monkeypatch, *login_responses(),
        Response(chunks=[b'{"mqtt":', b'{"password":""}}'], tag=TAG),
        Response(raw=b"saved", status=201), Response(raw=b"requested", status=202),
        Response({"authenticated": False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("ephemeral-test-password")
        document, tag = await client.async_read("/config/device")
        assert document == {"mqtt": {"password": ""}} and tag == TAG
        await client.async_save_settings(document, tag)
        await client.async_reboot()
        assert "ephemeral-test-password" not in vars(client).values()
    assert client.logout_confirmed and client._csrf is None and session.closed
    session.cookie_jar.clear.assert_called_once()
    assert create.call_args.kwargs["trust_env"] is False
    assert [x[1].removeprefix(BASE) for x in session.calls] == [
        "/auth/login", "/auth/session", "/config/device", "/config/device", "/updates/reboot", "/auth/logout"]
    login = session.calls[0][2]
    assert login["data"] == {"username": "admin", "password": "ephemeral-test-password"}
    assert login["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    for method, url, kwargs in session.calls:
        assert kwargs["allow_redirects"] is False and kwargs["headers"]["Origin"] == BASE
        if method == "POST" and not url.endswith("/auth/login"):
            assert kwargs["headers"]["X-OpenThermostat-CSRF"] == CSRF
    assert session.calls[3][2]["headers"]["If-Match"] == TAG


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(301,"controller_response_invalid"),
    (401,"controller_auth_failed"),(403,"controller_auth_failed"),
    (409,"controller_busy_or_conflict"),(412,"controller_settings_changed"),
    (500,"controller_response_invalid")])
async def test_remote_rejection_is_not_retried_or_disclosed(monkeypatch,status,code):
    session,_ = setup(monkeypatch,*login_responses(),
        Response(raw=b"private broker credential exception",status=status),Response({"authenticated":False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        with pytest.raises(link.ControllerLinkError,match="^"+code+"$"):
            await client.async_save_settings({"mqtt":{}},TAG)
    assert len(session.calls)==4 and client.logout_confirmed and session.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("tag",[None,"",'*',"d"*64,'W/'+TAG,TAG+', '+TAG])
async def test_missing_or_nonopaque_tag_requires_firmware_update_no_write(monkeypatch,tag):
    session,_=setup(monkeypatch,*login_responses(),Response({"mqtt":{}},tag=tag),Response({"authenticated":False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        with pytest.raises(link.ControllerLinkError,match="^controller_update_required$"):
            await client.async_read("/config/device")
    assert all(not (method=="POST" and url.endswith("/config/device")) for method,url,_ in session.calls)
    assert client.logout_confirmed and session.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("raw",[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}',b'{',b'\xff'])
async def test_corrupt_duplicate_and_nonfinite_response_is_rejected(monkeypatch,raw):
    session,_=setup(monkeypatch,*login_responses(),Response(raw=raw),Response({"authenticated":False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        with pytest.raises(link.ControllerLinkError,match="^controller_response_invalid$"):
            await client.async_read("/status")
    assert client.logout_confirmed and session.closed


@pytest.mark.asyncio
async def test_response_budget_and_cancellation_always_close_and_logout(monkeypatch):
    for response,expected in ((Response(chunks=[b"x"*8192,b"y"]),link.ControllerLinkError),
                              (asyncio.CancelledError(),asyncio.CancelledError)):
        session,_=setup(monkeypatch,*login_responses(),response,Response({"authenticated":False}))
        with pytest.raises(expected):
            async with link.ControllerClient(BASE) as client:
                await client.async_login("temporary")
                await client.async_read("/status")
        assert client.logout_confirmed and session.closed and client._csrf is None
        session.cookie_jar.clear.assert_called_once()


@pytest.mark.asyncio
async def test_request_allowlist_and_outgoing_budget_precede_network(monkeypatch):
    session,_=setup(monkeypatch,*login_responses(),Response({"authenticated":False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        for method,path in (("GET","/config/wifi"),("POST","/ota"),("DELETE","/config/device"),
                            ("GET","/status?secret=x"),("GET","http://other.local/status")):
            with pytest.raises(link.ControllerLinkError,match="^controller_request_invalid$"):
                await client._request(method,path)
        for document in (None,True,[],{"a":float("nan")},{"a":object()}):
            with pytest.raises(link.ControllerLinkError,match="^controller_request_invalid$"):
                await client.async_save_settings(document,TAG)
        with pytest.raises(link.ControllerLinkError,match="^controller_readback_invalid$"):
            await client.async_save_settings({},None)
        with pytest.raises(link.ControllerLinkError,match="^controller_settings_too_large$"):
            await client.async_save_settings({"data":"x"*2048},TAG)
    assert len(session.calls)==3 and session.closed


@pytest.mark.asyncio
async def test_logout_failure_is_explicit_and_does_not_mask_operation_error(monkeypatch):
    session,_=setup(monkeypatch,*login_responses(),Response(raw=b"private",status=403))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("temporary")
    assert client.logout_confirmed is False and session.closed and client._csrf is None
    session.cookie_jar.clear.assert_called_once()


def authenticated_readbacks():
    return {"version": {"version":"v0.1.0-e32v2-alpha.9","source":"a"*40,
                         "sha256":"b"*64,"web_sha256":"c"*64},
        "status": {"controlMode":"legacy","control_build": {"schema":1,
            "scope":"compiled_support_only","authorizes_physical_outputs":False,
            "source_formats":["native.source.local.week.v1"],
            "plans":[{"contract":"control.plan.week.v1","minimum_zones":1,"maximum_zones":2}]}},
        "updates": {"busy":False,"boot_pending":False,"reboot_required":False,"reboot_scheduled":False},
        "settings": {"mqtt":{"enabled":True,"brokerAddress":"broker.local","brokerPort":1883,
            "username":"existing-account","password":"","base":"old-base","clientId":"keep-client-id",
            "modern_shadow":False,"adapter_id":"","native_source_device_id":"e32_123456789abc",
            "native_source_live_apply":False},"openweather":{"appid":"","enabled":False},
            "interface_mode":"ethernet","emsEnabled":False,"emsForwarderEnabled":False,
            "unknown_preserved_field":{"kept":[1,False,"value"]}},"etag":TAG,"rooms":[]}


@pytest.mark.asyncio
@pytest.mark.parametrize('version_tag',['v0.1.0-e32v2-alpha.9','v0.1.0-e32v2-beta.4','v0.1.0-e32v2-beta.6'])
async def test_initial_link_reuses_actual_room_source_preserves_other_settings_and_never_writes(hass,configured,version_tag):
    parent,sub,_=configured;before=configuration_snapshot(parent);reads=authenticated_readbacks();old=deepcopy(reads)
    reads['version']['version']=version_tag;old['version']['version']=version_tag
    plan=link.initial_controller_link(hass,parent,**reads)
    assert reads==old and configuration_snapshot(parent)==before and plan.before==before
    assert plan.source.policy.week_reviewed and plan.source.room_count==1
    assert plan.source.policy.controller_id==reads['settings']['mqtt']['native_source_device_id']
    assert plan.settings_unchanged is False and plan.needs_reboot is True
    expected=deepcopy(reads['settings']);expected['mqtt'].pop('native_source_device_id');expected['mqtt'].pop('native_source_live_apply')
    assert plan.observed_settings==expected
    expected['mqtt'].update(modern_shadow=True,adapter_id=plan.source.policy.adapter_id,
        base=parent.data['topic_prefix'],native_shadow_source=plan.settings['mqtt']['native_shadow_source'])
    assert plan.settings==expected and plan.settings['mqtt']['clientId']=='keep-client-id'
    descriptor=plan.settings['mqtt']['native_shadow_source']
    assert descriptor[0]=='native.source.local.week.v1' and descriptor[1]==plan.source.policy.controller_id
    assert descriptor[6][0][0]==sub.data['room_id']
    assert 'existing-account' not in repr(plan) and TAG not in repr(plan)


@pytest.mark.asyncio
@pytest.mark.parametrize('fault,code',[
    ('tag','controller_update_required'),('version','controller_update_required'),
    ('build','controller_update_required'),('authority','controller_update_required'),
    ('limit','controller_update_required'),('busy','controller_busy_or_conflict'),
    ('pending','controller_busy_or_conflict'),('reboot','controller_busy_or_conflict'),
    ('legacy','controller_legacy_rooms_present'),('broker','controller_broker_setup_required'),
    ('port_bool','controller_broker_setup_required'),('secret','controller_broker_setup_required'),
    ('identity','controller_update_required'),('live_bool','controller_update_required'),
    ('other_source','controller_source_conflict'),('other_owner','controller_source_conflict'),
    ('budget','controller_settings_too_large'),('runtime','controller_runtime_off_required')])
async def test_initial_link_rejects_incompatible_or_busy_reads_without_mutation(hass,configured,fault,code):
    parent,_,_=configured;reads=authenticated_readbacks()
    if fault=='tag':reads['etag']=None
    if fault=='version':reads['version']['sha256']='invalid'
    if fault=='build':reads['status']['control_build']={}
    if fault=='authority':reads['status']['control_build']['authorizes_physical_outputs']=True
    if fault=='limit':reads['status']['control_build']['plans'][0]['maximum_zones']=8
    if fault=='busy':reads['updates']['busy']=True
    if fault=='pending':reads['updates']['boot_pending']=True
    if fault=='reboot':reads['updates']['reboot_scheduled']=True
    if fault=='legacy':reads['rooms']=[{'name':'old room'}]
    if fault=='broker':reads['settings']['mqtt']['enabled']=False
    if fault=='port_bool':reads['settings']['mqtt']['brokerPort']=True
    if fault=='secret':reads['settings']['mqtt']['password']='unredacted-test-only'
    if fault=='identity':reads['settings']['mqtt']['native_source_device_id']='other-controller'
    if fault=='live_bool':reads['settings']['mqtt']['native_source_live_apply']=0
    if fault=='other_source':reads['settings']['mqtt']['native_shadow_source']=['other']
    if fault=='other_owner':reads['settings']['mqtt'].update(modern_shadow=True,adapter_id='other-owner')
    if fault=='budget':reads['settings']['padding']='x'*2048
    if fault=='runtime':hass.config_entries.async_update_entry(parent,options={**parent.options,'shadow_enabled':True})
    before=configuration_snapshot(parent);old=deepcopy(reads)
    with pytest.raises(link.ControllerLinkError,match='^'+code+'$'):
        link.initial_controller_link(hass,parent,**reads)
    assert reads==old and configuration_snapshot(parent)==before


@pytest.mark.asyncio
async def test_exact_prior_link_is_idempotent_but_pending_restart_is_not_claimed_live(hass,configured):
    parent,_,_=configured;reads=authenticated_readbacks();first=link.initial_controller_link(hass,parent,**reads)
    reads['settings']=deepcopy(first.settings);reads['settings']['mqtt'].update(
        native_source_device_id=first.source.policy.controller_id,native_source_live_apply=True)
    reads['status']['controlMode']='shadow'
    same=link.initial_controller_link(hass,parent,**reads)
    assert same.settings_unchanged is True and same.needs_reboot is False
    reads['settings']['mqtt']['native_source_live_apply']=False;reads['status']['controlMode']='legacy'
    pending=link.initial_controller_link(hass,parent,**reads)
    assert pending.settings_unchanged is True and pending.needs_reboot is True
    # JSON boolean false must not alias the descriptor's integer-zero field.
    reads['settings']['mqtt']['native_shadow_source'][6][0][4]=False
    with pytest.raises(link.ControllerLinkError,match='^controller_source_conflict$'):
        link.initial_controller_link(hass,parent,**reads)


@pytest.mark.asyncio
async def test_actual_aiohttp_ip_cookie_form_csrf_etag_and_logout_over_local_http(monkeypatch):
    """Real client/server HTTP, independently specified native firmware contract."""
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    calls=[];state={'logged_in':False,'settings':{'mqtt':{'password':'','base':'original'}}}
    origin=''

    async def serve(request):
        assert request.headers['Origin']==origin
        calls.append((request.method,request.path))
        if request.path=='/auth/login':
            assert request.content_type=='application/x-www-form-urlencoded'
            assert request.headers['Content-Type']=='application/x-www-form-urlencoded'
            assert dict(await request.post())=={'username':'admin','password':'http-fixture-only'}
            state['logged_in']=True
            response=web.json_response({'authenticated':True})
            response.set_cookie('OTSESSION','a'*64,httponly=True,samesite='Strict',path='/')
            return response
        if not state['logged_in'] or request.cookies.get('OTSESSION')!='a'*64:
            return web.json_response({'error':'authentication_required'},status=401)
        if request.method=='POST' and request.headers.get('X-OpenThermostat-CSRF')!=CSRF:
            return web.json_response({'error':'csrf_required'},status=403)
        if request.path=='/auth/session':
            return web.json_response({'authenticated':True,'csrf':CSRF,'expires_in':60})
        if request.path=='/auth/logout':
            state['logged_in']=False
            return web.json_response({'authenticated':False})
        if request.path=='/config/device':
            if request.method=='GET':
                return web.json_response(state['settings'],headers={'ETag':TAG})
            if request.headers.get('If-Match')!=TAG or state.get('concurrent_edit'):
                return web.json_response({'error':'device_settings_changed'},status=412)
            state['settings']=await request.json()
            return web.Response(text='saved', status=201)
        return web.Response(status=404)

    app=web.Application();app.router.add_route('*','/{path:.*}',serve)
    async with TestServer(app) as server:
        origin=str(server.make_url('/')).rstrip('/')
        # Production rejects loopback. Permit exactly this ephemeral test origin
        # so the real IP-cookie behavior runs; no live HA/device is contacted.
        def test_origin(value):
            assert value==origin
            return origin
        monkeypatch.setattr(link,'controller_address',test_origin)
        async with link.ControllerClient(origin) as client:
            await client.async_login('http-fixture-only')
            settings,tag=await client.async_read('/config/device')
            settings['mqtt']['base']='changed'
            await client.async_save_settings(settings,tag)
            assert state['settings']['mqtt']['base']=='changed'
            state['concurrent_edit']=True
            with pytest.raises(link.ControllerLinkError,match='^controller_settings_changed$'):
                await client.async_save_settings({'mqtt':{'base':'must-not-save'}},tag)
            assert state['settings']['mqtt']['base']=='changed'
        assert client.logout_confirmed and not state['logged_in'] and client._session.closed
        assert not list(client._session.cookie_jar)
    assert calls==[('POST','/auth/login'),('GET','/auth/session'),('GET','/config/device'),
                   ('POST','/config/device'),('POST','/config/device'),('POST','/auth/logout')]


class NativeReceiver:
    """Protocol fixture only; not physical firmware or source qualification."""
    def __init__(self):
        self.readbacks=authenticated_readbacks();self.calls=[];self.mode=None
        self.saved=False;self.rebooted=False;self.authenticated=True;self.on_save=None

    async def async_read(self,path):
        self.calls.append(('read',path))
        if not self.authenticated:
            raise link.ControllerLinkError('controller_auth_failed')
        key={'/status/version':'version','/status':'status','/updates/status':'updates',
             '/config/device':'settings','/config/rooms':'rooms'}[path]
        value=deepcopy(self.readbacks[key])
        if key=='settings':
            if self.saved and self.mode=='wrong_readback':value['unexpected_after_write']=True
            if self.rebooted and self.mode=='wrong_identity':value['mqtt']['native_source_device_id']='e32_999999999999'
            return value,self.readbacks['etag']
        if self.rebooted and self.mode=='wrong_firmware' and key=='version':value['source']='f'*40
        return value

    async def async_save_settings(self,document,etag):
        self.calls.append(('save',etag))
        if self.mode=='save_412':raise link.ControllerLinkError('controller_settings_changed')
        if self.mode=='save_timeout':raise link.ControllerLinkError('controller_unreachable')
        self.saved=True;self.readbacks['settings']=deepcopy(document)
        self.readbacks['settings']['mqtt'].update(native_source_device_id='e32_123456789abc',native_source_live_apply=False)
        if self.on_save:self.on_save()
        if self.mode=='cancel_save':raise asyncio.CancelledError

    async def async_reboot(self):
        self.calls.append(('reboot',));self.rebooted=True
        if self.mode!='never_boot':
            self.readbacks['status']['controlMode']='shadow'
            self.readbacks['settings']['mqtt']['native_source_live_apply']=True
        if self.mode=='reboot_auth':self.authenticated=False
        if self.mode=='lost_reboot_response':raise link.ControllerLinkError('controller_unreachable')

    async def async_login(self,password):
        assert password=='http-fixture-only';self.calls.append(('reauthenticate',));self.authenticated=True


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',[None,'reboot_auth','lost_reboot_response'])
async def test_actual_native_source_and_week_compiler_then_verified_device_only_provision(hass,configured,mode):
    parent,_,_=configured;before=configuration_snapshot(parent);peer=NativeReceiver();peer.mode=mode
    plan=await link.async_prepare_controller_link(hass,parent,peer)
    assert peer.saved is False and configuration_snapshot(parent)==before
    result=await link.async_provision_controller(hass,parent,peer,plan,'http-fixture-only')
    assert result['running_logical_source_verified'] and result['device_settings_verified']
    assert result['mqtt_session_verified'] is False and result['room_plan_applied'] is False
    assert result['authorizes_physical_outputs'] is False and result['settings_written'] is True
    assert result['reboot_acknowledged'] is (mode!='lost_reboot_response')
    assert sum(c[0]=='save' for c in peer.calls)==sum(c[0]=='reboot' for c in peer.calls)==1
    assert sum(c[0]=='reauthenticate' for c in peer.calls)==(1 if mode=='reboot_auth' else 0)
    assert configuration_snapshot(parent)==before and 'native_logical_source' not in parent.options


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['concurrent_etag','concurrent_ha','tampered_plan'])
async def test_provision_rechecks_current_device_and_ha_before_mutation(hass,configured,fault):
    parent,_,_=configured;peer=NativeReceiver();plan=await link.async_prepare_controller_link(hass,parent,peer)
    if fault=='concurrent_etag':peer.readbacks['etag']='"'+'e'*64+'"'
    if fault=='concurrent_ha':hass.config_entries.async_update_entry(parent,title='Other editor')
    if fault=='tampered_plan':plan.settings['mqtt']['brokerAddress']='unreviewed.local'
    before=configuration_snapshot(parent)
    with pytest.raises(link.ControllerProvisioningError) as caught:
        await link.async_provision_controller(hass,parent,peer,plan,'http-fixture-only')
    assert caught.value.device_may_have_changed is False
    assert not peer.saved and not peer.rebooted and all(c[0]=='read' for c in peer.calls)
    assert configuration_snapshot(parent)==before


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,changed,code',[
    ('save_412',False,'controller_settings_changed'),('save_timeout',True,'controller_unreachable'),
    ('wrong_readback',True,'controller_settings_changed'),('wrong_identity',True,'controller_changed'),
    ('wrong_firmware',True,'controller_changed'),('never_boot',True,'controller_boot_unconfirmed')])
async def test_partial_or_ambiguous_outcome_never_retries_or_commits_ha(hass,configured,monkeypatch,mode,changed,code):
    parent,_,_=configured;before=configuration_snapshot(parent);peer=NativeReceiver();peer.mode=mode
    monkeypatch.setattr(link,'LINK_BOOT_TIMEOUT',.02);monkeypatch.setattr(link,'LINK_POLL_INTERVAL',.001)
    plan=await link.async_prepare_controller_link(hass,parent,peer)
    with pytest.raises(link.ControllerProvisioningError,match='^'+code+'$') as caught:
        await link.async_provision_controller(hass,parent,peer,plan,'http-fixture-only')
    assert caught.value.device_may_have_changed is changed
    assert sum(c[0]=='save' for c in peer.calls)==1 and sum(c[0]=='reboot' for c in peer.calls)<=1
    assert configuration_snapshot(parent)==before and parent.options.get('shadow_enabled') is False


@pytest.mark.asyncio
async def test_concurrent_ha_change_after_device_write_is_reported_partial_without_reboot(hass,configured):
    parent,_,_=configured;peer=NativeReceiver();plan=await link.async_prepare_controller_link(hass,parent,peer)
    peer.on_save=lambda:hass.config_entries.async_update_entry(parent,title='Concurrent writer')
    with pytest.raises(link.ControllerProvisioningError,match='^setup_changed$') as caught:
        await link.async_provision_controller(hass,parent,peer,plan,'http-fixture-only')
    assert caught.value.device_may_have_changed and peer.saved and not peer.rebooted
    assert 'native_logical_source' not in parent.options and parent.options.get('shadow_enabled') is False


@pytest.mark.asyncio
@pytest.mark.parametrize('live',[True,False])
async def test_exact_existing_device_source_is_read_only_or_one_explicit_reboot(hass,configured,live):
    parent,_,_=configured;peer=NativeReceiver();initial=link.initial_controller_link(hass,parent,**peer.readbacks)
    peer.readbacks['settings']=deepcopy(initial.settings);peer.readbacks['settings']['mqtt'].update(
        native_source_device_id=initial.source.policy.controller_id,native_source_live_apply=live)
    peer.readbacks['status']['controlMode']='shadow' if live else 'legacy'
    plan=await link.async_prepare_controller_link(hass,parent,peer)
    result=await link.async_provision_controller(hass,parent,peer,plan,'http-fixture-only')
    assert result['settings_written'] is False and result['running_logical_source_verified']
    assert all(c[0]!='save' for c in peer.calls) and sum(c[0]=='reboot' for c in peer.calls)==(0 if live else 1)


@pytest.mark.asyncio
async def test_cancellation_after_save_does_not_retry_reboot_commit_or_claim_rollback(hass,configured):
    parent,_,_=configured;peer=NativeReceiver();peer.mode='cancel_save';before=configuration_snapshot(parent)
    plan=await link.async_prepare_controller_link(hass,parent,peer)
    with pytest.raises(asyncio.CancelledError):
        await link.async_provision_controller(hass,parent,peer,plan,'http-fixture-only')
    assert peer.saved and not peer.rebooted and configuration_snapshot(parent)==before
    assert sum(c[0]=='save' for c in peer.calls)==1


@pytest.mark.asyncio
async def test_public_room_snapshot_never_contains_or_hashes_controller_password(hass,configured):
    from custom_components.open_thermostat import room_editor
    parent,sub,_=configured
    hass.config_entries.async_update_entry(parent,data={**parent.data,'controller_password':'private-fixture-one'})
    before=configuration_snapshot(parent);model=room_editor.read_room(hass,parent.entry_id,sub.data['room_id'])
    assert 'controller_password' not in before[1] and 'private-fixture-one' not in json.dumps(before)
    hass.config_entries.async_update_entry(parent,data={**parent.data,'controller_password':'private-fixture-two'})
    # Public room intent does not include the password. Privileged device IO
    # additionally pins full private entry state, tested separately below.
    assert configuration_snapshot(parent)==before
    assert room_editor.read_room(hass,parent.entry_id,sub.data['room_id'])['token']==model['token']
    assert 'private-fixture' not in json.dumps(model)


@pytest.mark.asyncio
@pytest.mark.parametrize('after_write',[False,True])
async def test_private_entry_fence_detects_password_only_change_even_when_public_snapshot_equal(hass,configured,after_write):
    parent,_,_=configured
    hass.config_entries.async_update_entry(parent,data={**parent.data,'controller_password':'private-fixture-one'})
    peer=NativeReceiver();plan=await link.async_prepare_controller_link(hass,parent,peer)
    public=configuration_snapshot(parent)
    def rotate():hass.config_entries.async_update_entry(parent,data={**parent.data,'controller_password':'private-fixture-two'})
    if after_write:peer.on_save=rotate
    else:rotate()
    with pytest.raises(link.ControllerProvisioningError,match='^setup_changed$') as caught:
        await link.async_provision_controller(hass,parent,peer,plan,'http-fixture-only')
    assert caught.value.device_may_have_changed is after_write
    assert peer.saved is after_write and not peer.rebooted and configuration_snapshot(parent)==public
    assert 'private-fixture' not in repr(plan)


@pytest.mark.asyncio
async def test_room_save_preserves_new_current_credential_instead_of_restoring_old_snapshot(hass,configured,monkeypatch):
    from custom_components.open_thermostat import room_editor
    parent,sub,_=configured
    hass.config_entries.async_update_entry(parent,data={**parent.data,'controller_password':'private-fixture-one'})
    model=room_editor.read_room(hass,parent.entry_id,sub.data['room_id'])
    settings=deepcopy(model['settings']);settings['name']='Edited room'
    async def executor(function,*args):
        hass.config_entries.async_update_entry(parent,data={**parent.data,'controller_password':'private-fixture-two'})
        return function(*args)
    monkeypatch.setattr(hass,'async_add_executor_job',executor)
    result=await room_editor.save_room(hass,parent.entry_id,model['room_id'],model['token'],settings)
    assert parent.data['controller_password']=='private-fixture-two'
    assert parent.subentries[sub.subentry_id].title=='Edited room'
    assert 'private-fixture' not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('descriptor_fault',[None,'other_owner','wrong_predecessor','boolean_alias','missing_predecessor'])
async def test_selected_evolution_replaces_only_exact_predecessor(hass,configured,descriptor_fault):
    from custom_components.open_thermostat import room_editor as ui
    from custom_components.open_thermostat.native_provisioning import (
        SOURCE_OPTION,source_selection,propose_room_source_change)
    parent,sub,model=configured
    reads=authenticated_readbacks();old=link.initial_controller_link(hass,parent,**reads)
    hass.config_entries.async_update_entry(parent,options={**parent.options,SOURCE_OPTION:source_selection(old.source)})
    model=ui.read_room(hass,parent.entry_id,model['room_id'])
    settings=deepcopy(model['settings']);settings['maximum_centi_c']-=100
    _,current_sub,room=ui._target(hass,parent.entry_id,model['room_id'])
    candidate,graph,_=ui.prepare_room_edit(hass,parent,current_sub,room,settings)()
    proposed=propose_room_source_change(hass,parent,old.source,candidate,graph.storage_document())
    await ui.save_room(hass,parent.entry_id,model['room_id'],model['token'],settings)
    hass.config_entries.async_update_entry(parent,options={**parent.options,SOURCE_OPTION:source_selection(proposed)})
    reads['settings']=deepcopy(old.settings)
    reads['settings']['mqtt'].update(native_source_device_id=old.source.policy.controller_id,
        native_source_live_apply=True)
    reads['status']['controlMode']='shadow'
    if descriptor_fault=='missing_predecessor':reads['settings']['mqtt'].pop('native_shadow_source')
    if descriptor_fault=='other_owner':reads['settings']['mqtt']['adapter_id']='other-owner'
    if descriptor_fault=='wrong_predecessor':reads['settings']['mqtt']['native_shadow_source'][6][0][5]='f'*64
    if descriptor_fault=='boolean_alias':reads['settings']['mqtt']['native_shadow_source'][6][0][4]=False
    if descriptor_fault:
        with pytest.raises(link.ControllerLinkError,match='controller_source_conflict'):
            link.initial_controller_link(hass,parent,**reads)
    else:
        result=link.initial_controller_link(hass,parent,**reads)
        assert result.source==proposed and not result.settings_unchanged
        assert result.settings['mqtt']['native_shadow_source'][0]=='native.source.evolution.v1'
        assert result.observed_settings['mqtt']['native_shadow_source']==old.settings['mqtt']['native_shadow_source']
