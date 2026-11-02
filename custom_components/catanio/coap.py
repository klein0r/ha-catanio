"""CoAP context shared by all CatanIO config entries."""

import asyncio

import aiocoap

# Imported here so creating the context does not import it in the event loop.
import aiocoap.transports.udp6

from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE
from homeassistant.core import Event, HomeAssistant
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

DATA_COAP_CONTEXT: HassKey[aiocoap.Context] = HassKey(f"{DOMAIN}_coap_context")
DATA_COAP_LOCK: HassKey[asyncio.Lock] = HassKey(f"{DOMAIN}_coap_lock")


async def async_get_coap_context(hass: HomeAssistant) -> aiocoap.Context:
    """Return the CoAP client context, creating it on first use."""
    if (context := hass.data.get(DATA_COAP_CONTEXT)) is not None:
        return context
    async with hass.data.setdefault(DATA_COAP_LOCK, asyncio.Lock()):
        if (context := hass.data.get(DATA_COAP_CONTEXT)) is not None:
            return context
        context = await aiocoap.Context.create_client_context(transports=["udp6"])
        hass.data[DATA_COAP_CONTEXT] = context

        async def _async_shutdown(event: Event) -> None:
            hass.data.pop(DATA_COAP_CONTEXT, None)
            await context.shutdown()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_CLOSE, _async_shutdown)
        return context
