"""TCP reachability probes.

Deliberately TCP rather than ICMP. A connect to the ComIP port tests the
service you actually depend on, and it needs no raw socket privileges inside
a container, which ICMP does.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

_LOGGER = logging.getLogger(__name__)


async def async_tcp_probe(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection to host:port can be opened."""
    writer = None
    try:
        async with asyncio.timeout(timeout):
            _reader, writer = await asyncio.open_connection(host, port)
        return True
    except (TimeoutError, OSError) as err:
        _LOGGER.debug("Probe to %s:%s failed: %s", host, port, err)
        return False
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(OSError, asyncio.CancelledError):
                await writer.wait_closed()
