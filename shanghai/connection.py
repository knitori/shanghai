
import asyncio

from .event import Event
from .logging import current_logger


class Connection:

    def __init__(self, host, port, queue: asyncio.Queue, ssl=False, loop=None):
        self.host = host
        self.port = port
        self.queue = queue
        self.ssl = ssl
        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        self.writer = None

    def writeline(self, line, encoding):
        self.writer.write(line.encode(encoding) + b'\r\n')
        current_logger.debug("<", line)

    async def close(self):
        await self.writer.drain()
        self.writer.close()

    async def run(self):
        reader, writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl, loop=self.loop)
        self.writer = writer

        await self.queue.put(Event('connected', self))

        while not reader.at_eof():
            line = await reader.readline()
            line = line.strip()
            current_logger.debug(">", line)
            if line:
                await self.queue.put(Event('raw_line', line))

        self.writer.close()
        await self.queue.put(Event('disconnected', None))
