"""Protobuf message classes of the CatanIO API.

The classes are built at import time from ``catanio.binpb``, a descriptor set
compiled from the upstream schemas (see ``script/generate_descriptor.py``).
The upstream schemas do not declare a package, so they are loaded into a
private descriptor pool to avoid clashing with other users of the default pool.
"""

from pathlib import Path

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

_DESCRIPTOR_SET = Path(__file__).with_name("catanio.binpb")

POOL = descriptor_pool.DescriptorPool()
for _file in descriptor_pb2.FileDescriptorSet.FromString(
    _DESCRIPTOR_SET.read_bytes()
).file:
    POOL.Add(_file)


def _message_class(full_name: str) -> type[Message]:
    return message_factory.GetMessageClass(POOL.FindMessageTypeByName(full_name))


SysMessage = _message_class("SysMessage")
SysCfgResp = _message_class("SysCfgResp")
ReqDiscover = _message_class("ReqDiscover")
RespDiscover = _message_class("RespDiscover")

UiCfgResp = _message_class("UiCfgResp")
UiReq = _message_class("UiReq")
UiResp = _message_class("UiResp")

UoiCfgResp = _message_class("UoiCfgResp")
UoiReq = _message_class("UoiReq")
UoiResp = _message_class("UoiResp")

DorCfgResp = _message_class("DorCfgResp")
DorReq = _message_class("DorReq")
DorResp = _message_class("DorResp")
