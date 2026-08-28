from __future__ import annotations

from smart_serial.transport import SerialTransport


async def test_connect_and_disconnect_lifecycle() -> None:
    """Exercises the real serial_asyncio_fast connection path end to end.

    Uses pySerial's built-in ``loop://`` virtual port so no real hardware
    is needed. Note: this doesn't do an actual write/read round-trip --
    combined with the non-blocking write timeout that serial_asyncio_fast
    configures, pyserial's loop:// handler treats *any* non-empty write as
    exceeding it (it estimates transmission time from the baud rate and
    compares it against a write_timeout of 0), which is a quirk of that
    test-only virtual port rather than of real hardware. Command
    formatting/response handling in :meth:`SerialTransport.send_command` is
    covered instead via the ``fake_transport`` fixture in the device tests.
    """
    transport = SerialTransport("loop://")
    assert not transport.is_connected

    await transport.connect()
    assert transport.is_connected

    await transport.connect()  # calling connect() again should be a no-op
    assert transport.is_connected

    await transport.disconnect()
    assert not transport.is_connected

    await transport.disconnect()  # calling disconnect() again should be a no-op
