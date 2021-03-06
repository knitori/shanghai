
import asyncio

from .event import Event
from .logging import current_logger


class Connection:

    def __init__(self, host: str, port: int, queue: asyncio.Queue,
                 ssl: bool = False, loop: asyncio.AbstractEventLoop = None):
        self.host = host
        self.port = port
        self.queue = queue
        self.ssl = ssl
        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        self.writer = None  # type: asyncio.StreamWriter

    def writeline(self, line: bytes):
        current_logger.info("<", line)
        self.writer.write(line)
        self.writer.write(b'\r\n')

    def close(self):
        self.writer.close()

    async def run(self):
        reader, writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl, loop=self.loop)
        self.writer = writer

        await self.queue.put(Event('connected', self))

        try:
            while not reader.at_eof():
                line = await reader.readline()
                line = line.strip()
                current_logger.debug(">", line)
                if line:
                    await self.queue.put(Event('raw_line', line))
        except asyncio.CancelledError:
            current_logger.info("Connection.run cancelled")
        finally:
            self.close()
            await self.queue.put(Event('disconnected', None))
