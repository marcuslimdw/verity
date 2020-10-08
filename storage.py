from abc import ABCMeta
from typing import Dict, Optional

import asyncpg
from asyncpg import Connection

from exceptions import AlreadyConnected


class Storage:

    def __init__(self, url: str):
        self._url = url
        self._connection: Optional[Connection] = None

    async def connect(self):
        if self._connection is not None:
            raise AlreadyConnected(self._connection)

        self._connection = await asyncpg.connect()

    def __getitem__(self, item: str):
        pass


class KeyHandler(metaclass=ABCMeta):

    def __init__(self):
        pass


