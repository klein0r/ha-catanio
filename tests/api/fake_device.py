"""CoAP server emulating a CatanIO device for the client tests."""

import asyncio
from typing import Any

import aiocoap
from aiocoap import resource

from custom_components.catanio.api import proto
from custom_components.catanio.api.models import (
    BooleanSetting,
    DiscoverOption,
    DiscoverStatus,
    Setting,
    SysMsgType,
    UiType,
    UoiType,
)


class FakeResource(resource.Resource):
    """Resource answering GET and PATCH with protobuf messages."""

    def __init__(self, device: FakeCatanDevice, path: str) -> None:
        """Initialize the resource."""
        super().__init__()
        self._device = device
        self._path = path

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        """Answer a GET request."""
        return await self._device.handle("GET", self._path, request)

    async def render_patch(self, request: aiocoap.Message) -> aiocoap.Message:
        """Answer a PATCH request."""
        return await self._device.handle("PATCH", self._path, request)


class FakeCatanDevice:
    """A Catan C1 with a few channels and a backend discovery."""

    def __init__(self) -> None:
        """Initialize the device state."""
        self.requests: list[tuple[str, str, Any]] = []
        self.discover_polls = 0
        self.raw_responses: dict[str, bytes] = {}
        self.silent_paths: set[str] = set()
        self.wrong_sys_response = False
        self.uoi13: Any = proto.UoiResp(
            type=UoiType.AO_VOLTAGE,
            analog_val=2.5,
            analog_set_val=2.5,
            actuator_val=2.5,
        )
        self.dor1: Any = proto.DorResp(digital_val=False, counter_val=3)
        self.doi9_cfg: Any = proto.UoiCfgResp(
            enabled=True, type=UoiType.DO, use_default_val_on_failure=True
        )
        self.site = resource.Site()
        for path in (
            "sys",
            "sys/cfg",
            "sys/discover",
            "ui/1",
            "ui/1/cfg",
            "uoi/13",
            "uoi/13/cfg",
            "doi/9/cfg",
            "dor/1",
            "dor/1/cfg",
        ):
            self.site.add_resource(path.split("/"), FakeResource(self, path))

    async def handle(
        self, method: str, path: str, request: aiocoap.Message
    ) -> aiocoap.Message:
        """Dispatch a request."""
        if path in self.silent_paths:
            await asyncio.sleep(3600)
        if path in self.raw_responses:
            return aiocoap.Message(
                code=aiocoap.CONTENT, payload=self.raw_responses[path]
            )
        handler = getattr(self, f"_{method.lower()}_{path.replace('/', '_')}")
        decoded, response = handler(request.payload)
        self.requests.append((method, path, decoded))
        code = aiocoap.CONTENT if method == "GET" else aiocoap.CHANGED
        return aiocoap.Message(code=code, payload=response.SerializeToString())

    def _patch_sys(self, payload: bytes) -> tuple[Any, Any]:
        request: Any = proto.SysMessage.FromString(payload)
        response: Any = proto.SysMessage()
        match request.msg_type:
            case SysMsgType.REQ_READ_INFO:
                response.msg_type = SysMsgType.RESP_READ_INFO
                info = response.req_resp_info
                info.model_name = "CATAN C1"
                info.model_number = "1886438"
                info.serial_no = "1234567890"
                info.mac_id = bytes.fromhex("00a045123456")
                info.hardware_revision = 2
                info.model_revision = "01"
            case SysMsgType.REQ_READ_STATUS:
                response.msg_type = SysMsgType.RESP_READ_STATUS
                response.resp_status.points_in_failure = 2
                response.resp_status.ctrl_connected = True
                response.resp_status.button_pressed = True
            case SysMsgType.REQ_READ_FW_UPDATE_INFO:
                response.msg_type = SysMsgType.RESP_READ_FW_UPDATE_INFO
                image = response.resp_fw_update_info.fw_primary
                image.major, image.minor, image.revision, image.build = 1, 4, 2, 17
            case SysMsgType.REQ_REBOOT:
                response.msg_type = SysMsgType.RESP_REBOOT
                response.req_resp_empty.SetInParent()
            case _:
                response.req_resp_empty.SetInParent()
        if self.wrong_sys_response:
            response.msg_type = SysMsgType.RESP_REBOOT
        return request, response

    def _get_sys_cfg(self, payload: bytes) -> tuple[Any, Any]:
        return None, proto.SysCfgResp(name=" Boiler room ", password1=4711)

    def _patch_sys_discover(self, payload: bytes) -> tuple[Any, Any]:
        request: Any = proto.ReqDiscover.FromString(payload)
        response: Any = proto.RespDiscover()
        if request.option == DiscoverOption.GET_STATUS:
            self.discover_polls += 1
        busy = request.option == DiscoverOption.START_READ_ONLY or (
            request.option == DiscoverOption.GET_STATUS and self.discover_polls < 2
        )
        response.status = DiscoverStatus.BUSY if busy else DiscoverStatus.IDLE
        if request.option == DiscoverOption.GET_RESULT:
            response.discover_entries.add(ip_address=bytes([169, 254, 250, 10]))
            response.discover_entries.add(
                ip_address=bytes([169, 254, 250, 11]), error=1
            )
            response.discover_entries.add(ip_address=b"\x01")
            response.error = 1
        return request, response

    def _get_ui_1(self, payload: bytes) -> tuple[Any, Any]:
        return None, proto.UiResp(
            type=UiType.AI_TEMPERATURE_PT1000_DIN,
            status=0,
            analog_val=21.299999237060547,
            sensor_val=21.25,
        )

    def _get_ui_1_cfg(self, payload: bytes) -> tuple[Any, Any]:
        return None, proto.UiCfgResp(
            enabled=True,
            type=UiType.AI_TEMPERATURE_PT1000_DIN,
            name="Outdoor",
            unit="°C ",
            minimum=-50.0,
            maximum=150.0,
            configured=True,
        )

    def _get_uoi_13(self, payload: bytes) -> tuple[Any, Any]:
        return None, self.uoi13

    def _patch_uoi_13(self, payload: bytes) -> tuple[Any, Any]:
        request: Any = proto.UoiReq.FromString(payload)
        if request.analog_set_val.setting == Setting.VAL:
            value = request.analog_set_val.val
            self.uoi13.analog_set_val = value
            self.uoi13.analog_val = value
            self.uoi13.actuator_val = value
        return request, self.uoi13

    def _get_uoi_13_cfg(self, payload: bytes) -> tuple[Any, Any]:
        return None, proto.UoiCfgResp(enabled=True, type=UoiType.AO_VOLTAGE)

    def _patch_doi_9_cfg(self, payload: bytes) -> tuple[Any, Any]:
        request: Any = proto.UoiCfgReq.FromString(payload)
        config = self.doi9_cfg
        if request.type != UoiType.DONT_CHANGE:
            config.type = request.type
        for field in (
            "inverted",
            "debounced",
            "digital_default_val",
            "use_default_val_on_start",
            "use_default_val_on_failure",
            "configured",
        ):
            if (value := getattr(request, field)) != BooleanSetting.DONT_CHANGE:
                setattr(config, field, value == BooleanSetting.TRUE)
        return request, config

    def _get_dor_1(self, payload: bytes) -> tuple[Any, Any]:
        return None, self.dor1

    def _patch_dor_1(self, payload: bytes) -> tuple[Any, Any]:
        request: Any = proto.DorReq.FromString(payload)
        if request.digital_set_val != BooleanSetting.DONT_CHANGE:
            value = request.digital_set_val == BooleanSetting.TRUE
            self.dor1.digital_set_val = value
            self.dor1.digital_val = value
        return request, self.dor1

    def _get_dor_1_cfg(self, payload: bytes) -> tuple[Any, Any]:
        return None, proto.DorCfgResp(enabled=True, name="Relay", inverted=True)
