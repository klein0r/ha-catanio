# CatanIO Protobuf schemas

The `.proto` files in this directory are copied unchanged from
[PLCnext/CatanIO](https://github.com/PLCnext/CatanIO) (`protobuf/`), commit
`6029888a686fda53ad4d8cf7042aa84a59eccc4f`. They are licensed under the MIT
license by Phoenix Contact GmbH & Co KG, see [LICENSE.md](LICENSE.md).

The integration does not ship generated `_pb2.py` modules. It loads a binary
`FileDescriptorSet` into a private descriptor pool at runtime instead, which
keeps it independent of the `protobuf` version pinned by Home Assistant.

Regenerate the descriptor set after updating the schemas:

```bash
pip install grpcio-tools
python script/generate_descriptor.py
```

The script strips the nanopb options (they only constrain embedded encoders)
and writes `custom_components/catanio/api/catanio.binpb`.
