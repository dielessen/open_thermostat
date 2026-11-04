"""Small Home Assistant client for the demo: onboarding, REST flows and the websocket API.

Only talks to the demo Home Assistant on 127.0.0.1 inside the demo's own network namespace.
"""
import asyncio
import itertools
import json

import aiohttp


class HassError(RuntimeError):
    pass


class Hass:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.client_id = self.base + "/"
        self.session = None
        self.access = None  # the owner user's access token (password grant at onboarding)
        self.refresh = None
        self.expires_in = 1800
        self._ws = None
        self._ids = itertools.count(1)
        self._pending = {}
        self._reader = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
        return self

    async def __aexit__(self, *_):
        await self.close_ws()
        await self.session.close()

    # -- REST ----------------------------------------------------------------------------------------
    def _headers(self):
        return {"Authorization": "Bearer " + self.access} if self.access else {}

    async def get(self, path, ok=(200,)):
        async with self.session.get(self.base + path, headers=self._headers()) as r:
            text = await r.text()
            if r.status not in ok:
                raise HassError(f"GET {path}: {r.status} {text[:500]}")
            return json.loads(text) if text else None

    async def post(self, path, data=None, ok=(200, 201), form=None):
        kwargs = {"data": form} if form is not None else {"json": data if data is not None else {}}
        async with self.session.post(self.base + path, headers=self._headers(), **kwargs) as r:
            text = await r.text()
            if r.status not in ok:
                raise HassError(f"POST {path}: {r.status} {text[:800]}")
            return json.loads(text) if text else None

    async def wait_up(self, timeout=180):
        """Until the HTTP server answers the onboarding status (no auth needed)."""
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        last = None
        while loop.time() < end:
            try:
                async with self.session.get(self.base + "/api/onboarding", timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status in (200, 404):
                        return
                    last = r.status
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last = repr(err)
            await asyncio.sleep(1)
        raise HassError(f"Home Assistant did not answer in {timeout} s ({last})")

    async def token(self, code):
        result = await self.post("/auth/token", form={"grant_type": "authorization_code", "code": code,
                                                       "client_id": self.client_id})
        self.access, self.refresh = result["access_token"], result["refresh_token"]
        self.expires_in = result.get("expires_in", 1800)
        return result

    async def refresh_access(self):
        async with self.session.post(self.base + "/auth/token", data={
                "grant_type": "refresh_token", "refresh_token": self.refresh, "client_id": self.client_id}) as r:
            result = await r.json()
            if r.status != 200:
                raise HassError(f"token refresh: {r.status} {result}")
        self.access = result["access_token"]
        self.expires_in = result.get("expires_in", 1800)
        return result

    async def onboard(self, name, username, password, language):
        """Owner user, core config, analytics, integration step: the frontend's own onboarding calls."""
        steps = {s["step"]: s["done"] for s in await self.get("/api/onboarding")}
        if not steps.get("user"):
            result = await self.post("/api/onboarding/users", {
                "client_id": self.client_id, "name": name, "username": username, "password": password,
                "language": language})
            await self.token(result["auth_code"])
        else:
            await self.login(username, password)
        steps = {s["step"]: s["done"] for s in await self.get("/api/onboarding")}
        if not steps.get("core_config"):
            await self.post("/api/onboarding/core_config", {})
        if not steps.get("analytics"):
            await self.post("/api/onboarding/analytics", {})
        if not steps.get("integration"):
            await self.post("/api/onboarding/integration", {"client_id": self.client_id,
                                                            "redirect_uri": self.client_id + "?auth_callback=1"})

    async def login(self, username, password):
        """The login flow of the frontend's login page (homeassistant auth provider)."""
        flow = await self.post("/auth/login_flow", {"client_id": self.client_id, "handler": ["homeassistant", None],
                                                    "redirect_uri": self.client_id + "?auth_callback=1"})
        result = await self.post("/auth/login_flow/" + flow["flow_id"], {
            "client_id": self.client_id, "username": username, "password": password})
        if result.get("type") != "create_entry":
            raise HassError(f"login: {result}")
        await self.token(result["result"])

    # -- config flows --------------------------------------------------------------------------------
    @staticmethod
    def form_defaults(schema, **values):
        """A form's answer: every field's default (sections too), then the given values on top."""
        result = {}
        for field in schema or []:
            name = field.get("name")
            if field.get("type") == "expandable":
                result[name] = Hass.form_defaults(field.get("schema"), **values.pop(name, {}))
            elif "default" in field:
                result[name] = field["default"]
        result.update(values)
        return result

    async def flow_start(self, handler, kind="config"):
        path = "/api/config/config_entries/flow" if kind == "config" else "/api/config/config_entries/options/flow"
        return await self.post(path, {"handler": handler, "show_advanced_options": True})

    async def flow_step(self, flow_id, data, kind="config"):
        path = ("/api/config/config_entries/flow/" if kind == "config"
                else "/api/config/config_entries/options/flow/") + flow_id
        return await self.post(path, data)

    async def flow_get(self, flow_id, kind="config"):
        path = ("/api/config/config_entries/flow/" if kind == "config"
                else "/api/config/config_entries/options/flow/") + flow_id
        return await self.get(path)

    # -- websocket -----------------------------------------------------------------------------------
    async def connect_ws(self):
        self._ws = await self.session.ws_connect(self.base + "/api/websocket", max_msg_size=0)
        hello = await self._ws.receive_json()
        assert hello["type"] == "auth_required", hello
        await self._ws.send_json({"type": "auth", "access_token": self.access})
        ok = await self._ws.receive_json()
        if ok["type"] != "auth_ok":
            raise HassError(f"websocket auth: {ok}")
        self._reader = asyncio.create_task(self._read())

    async def _read(self):
        async for msg in self._ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = json.loads(msg.data)
            for item in data if isinstance(data, list) else [data]:
                future = self._pending.pop(item.get("id"), None)
                if future is not None and not future.done() and item.get("type") == "result":
                    future.set_result(item)
        for future in self._pending.values():
            if not future.done():
                future.set_exception(HassError("websocket closed"))

    async def ws(self, type_, **kwargs):
        if self._ws is None or self._ws.closed:
            await self.connect_ws()
        msg_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        await self._ws.send_json({"id": msg_id, "type": type_, **kwargs})
        result = await asyncio.wait_for(future, 120)
        if not result.get("success"):
            raise HassError(f"{type_}: {result.get('error')}")
        return result.get("result")

    async def close_ws(self):
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._reader is not None:
            self._reader.cancel()
        self._ws = None
