import random
from typing import List, Literal, Optional, Tuple

from asyncpg import Connection

from exceptions import GameFull, GameNotFound


class GameStorage:

    def __init__(self, connection: Connection):
        self._connection = connection

    async def get_last_id(self) -> Optional[int]:
        select_sql = "SELECT id FROM game WHERE status = 'waiting' ORDER BY when_created"
        return await self._connection.fetchval(select_sql)

    async def create_game(self, host_id: int) -> int:
        insert_sql = "INSERT INTO game (host_id) VALUES ($1) RETURNING id"
        return await self._connection.fetchval(insert_sql, host_id)

    async def sign(self, game_id: int, user_id: int) -> int:
        connection = self._connection
        async with connection.transaction():
            signed_count = await self.get_signed_count(game_id)
            if signed_count is None:
                raise GameNotFound(game_id)

            elif signed_count >= 10:
                raise GameFull(signed_count)

            insert_sql = "INSERT INTO signed_user (game_id, user_id) VALUES ($1, $2)"
            await self._connection.execute(insert_sql, game_id, user_id)
            return signed_count + 1

    async def remove_from_game(self, user_id: int) -> Tuple[int, Optional[int]]:
        connection = self._connection
        async with connection.transaction():
            delete_sql = ("DELETE FROM signed_user "
                          "USING game "
                          "WHERE signed_user.user_id = $1 "
                          "AND signed_user.game_id = game.id "
                          "AND game.status IN ('waiting', 'active') "
                          "RETURNING game.id")
            maybe_game_id: Optional[int] = await connection.fetchval(delete_sql, user_id)
            if maybe_game_id is None:
                raise GameNotFound()

            if not await self.get_signed_for_game(maybe_game_id):
                await self.delete_game(maybe_game_id)
                new_host_id = None

            else:
                new_host_id = await self.transfer_host_if_needed(maybe_game_id)

            return maybe_game_id, new_host_id

    async def transfer_host_if_needed(self, game_id: int) -> Optional[int]:
        connection = self._connection
        select_sql = ("SELECT COUNT(*) FROM game "
                      "WHERE id = $1 "
                      "AND host_id NOT IN (SELECT user_id FROM signed_user WHERE game_id = $1)")
        if await connection.fetchval(select_sql, game_id):
            signed_ids = await self.get_signed_for_game(game_id)
            new_host_id = random.choice(signed_ids)
            update_sql = "UPDATE game SET host_id = $1 WHERE id = $2"
            await connection.execute(update_sql, new_host_id, game_id)
            return new_host_id

        else:
            return None

    async def delete_game(self, game_id: int) -> Optional[int]:
        update_sql = "UPDATE game SET status = 'inactive' WHERE id = $1"
        return await self._connection.fetchval(update_sql, game_id)

    async def get_by_status(self, status: Literal['waiting', 'active']) -> List:
        assert status in {'waiting', 'active'}
        select_sql = ("SELECT game.id, game.host_id, game.join_code, COUNT(user_id) AS signed_count "
                      "FROM game "
                      "INNER JOIN signed_user "
                      "ON game.id = signed_user.game_id "
                      "WHERE game.status = $1 "
                      "GROUP BY game.id")
        return await self._connection.fetch(select_sql, status)

    async def get_signed_count(self, game_id: int) -> Optional[int]:
        select_sql = ("SELECT COUNT(*) FROM signed_user "
                      "LEFT JOIN game ON signed_user.game_id = game.id "
                      "WHERE signed_user.game_id = $1 "
                      "AND game.status = 'waiting' "
                      "GROUP BY game.id")
        return await self._connection.fetchval(select_sql, game_id)

    async def get_signed_for_game(self, game_id: int) -> List[int]:
        select_sql = "SELECT user_id FROM signed_user WHERE game_id = $1"
        result = await self._connection.fetch(select_sql, game_id)
        return [row for row, *_ in result]

    async def start(self, user_id: int, join_code: str) -> int:
        update_sql = ("UPDATE game "
                      "SET status = 'active', join_code = $1 "
                      "WHERE id = (SELECT game_id FROM signed_user WHERE user_id = $2) "
                      "AND status = 'waiting'"
                      "RETURNING id")
        game_id = await self._connection.fetchval(update_sql, join_code, user_id)
        return game_id

    async def set_code(self, user_id: int, join_code: str) -> int:
        update_sql = ("UPDATE game "
                      "SET join_code = $1 "
                      "WHERE id = (SELECT game_id FROM signed_user WHERE user_id = $2) "
                      "AND status != 'inactive'"
                      "RETURNING id")
        game_id = await self._connection.fetchval(update_sql, join_code, user_id)
        return game_id
