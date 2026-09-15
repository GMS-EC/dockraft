import pytest
import asyncio
import time
from app.core.process_manager import ProcessManager

@pytest.mark.asyncio
async def test_silent_tps_suppression():
    pm = ProcessManager()
    pm.status = "RUNNING"

    # Simulate automated silent tps poll
    pm._silent_tps_time = time.time()
    
    # Fake stream with TPS line
    stream = asyncio.StreamReader()
    stream.feed_data(b"[13:46:13 INFO]: TPS from last 1m, 5m, 15m: 19.8, 19.9, 20.0\n")
    stream.feed_eof()

    await pm._read_stream(stream)

    # Must NOT be in log_buffer
    assert len(pm.log_buffer) == 0
    # But current_tps MUST be updated
    assert pm.current_tps["1m"] == 19.8
    assert pm.current_tps["5m"] == 19.9
    assert pm.current_tps["15m"] == 20.0

@pytest.mark.asyncio
async def test_manual_tps_not_suppressed():
    pm = ProcessManager()
    pm.status = "RUNNING"
    pm._silent_tps_time = 0.0  # User ran it manually

    stream = asyncio.StreamReader()
    stream.feed_data(b"[13:46:13 INFO]: TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0\n")
    stream.feed_eof()

    await pm._read_stream(stream)

    # Must be in log_buffer for user to see
    assert len(pm.log_buffer) == 1
    assert "TPS from last" in pm.log_buffer[0]

@pytest.mark.asyncio
async def test_silent_list_suppression():
    pm = ProcessManager()
    pm.status = "RUNNING"

    # Simulate automated silent list poll
    pm._silent_list_time = time.time()

    stream = asyncio.StreamReader()
    stream.feed_data(b"[13:46:13 INFO]: [Essentials] CONSOLE issued server command: /list\n")
    stream.feed_data(b"[13:46:13 INFO]: Hay 0 jugadores de un maximo de 8 jugadores en linea.\n")
    stream.feed_eof()

    await pm._read_stream(stream)

    # Neither line should be in log_buffer
    assert len(pm.log_buffer) == 0
    # Player list reconciled
    assert len(pm.online_players) == 0

@pytest.mark.asyncio
async def test_manual_list_not_suppressed():
    pm = ProcessManager()
    pm.status = "RUNNING"
    pm._silent_list_time = 0.0  # User ran it manually

    stream = asyncio.StreamReader()
    stream.feed_data(b"[13:46:13 INFO]: [Essentials] CONSOLE issued server command: /list\n")
    stream.feed_data(b"[13:46:13 INFO]: Hay 0 jugadores de un maximo de 8 jugadores en linea.\n")
    stream.feed_eof()

    await pm._read_stream(stream)

    # Both lines should be in log_buffer
    assert len(pm.log_buffer) == 2
