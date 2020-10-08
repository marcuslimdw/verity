import os
import random
import ssl
from logging import DEBUG as LOGGING_DEBUG, StreamHandler, getLogger
from sys import stdout
from typing import Optional

import asyncpg
from discord.ext import commands
from discord.ext.commands import Bot, Context

from exceptions import GameFull, GameNotFound
from game_storage import GameStorage
from utils import mention, username, valid_join_code

token = os.environ.get('VERITY_BOT_TOKEN')
assert token, "Couldn't get token from environment. Did you forget to set VERITY_BOT_TOKEN?"

bot = Bot(command_prefix='!')

logger = getLogger('verity')
logger.setLevel(LOGGING_DEBUG)
handler = StreamHandler(stdout)
logger.addHandler(handler)

game_storage: Optional[GameStorage] = None

dsn = os.environ.get('VERITY_DSN')
assert dsn, "Couldn't get DSN from environment. Did you forget to set VERITY_DSN?"

ssl_context = ssl.create_default_context(cafile='./rds-combined-ca-bundle.pem')
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


@bot.event
async def on_ready():
    global game_storage
    connection = await asyncpg.connect(dsn, ssl=ssl_context)
    game_storage = GameStorage(connection)
    logger.info('Verity is online!')


@bot.command()
async def healthcheck(ctx: Context):
    await ctx.send("Verity's doing just fine!")


@bot.command()
async def sign(ctx: Context, game_id: Optional[int] = None):
    sender_id = ctx.author.id
    sender_mention = mention(sender_id)
    if game_id is None:
        last_id = await game_storage.get_last_id()
        if last_id is None:
            last_id = await game_storage.create_game(sender_id)
            await ctx.send(f'{sender_mention} hosted new game {last_id}.')

        game_id = last_id

    try:
        signed_count = await game_storage.sign(game_id, sender_id)

    except asyncpg.UniqueViolationError:
        await ctx.send(f'You have already signed for a game, {sender_mention}.')

    except GameNotFound:
        await ctx.send(f"{sender_mention} couldn't sign for game {game_id} because it doesn't exist or isn't active.")

    except GameFull:
        await ctx.send(f"{sender_mention} couldn't sign for game {game_id} because it is full.")

    except Exception as exc:
        await ctx.send(f"{sender_mention} couldn't sign for game {game_id} because of some unknown error.")
        raise exc

    else:
        await ctx.send(f'{sender_mention} successfully signed for game {game_id} ({signed_count}/10).')


@bot.command()
async def leave(ctx: Context):
    sender_id = ctx.author.id
    game_id, new_host_id = await game_storage.remove_from_game(sender_id)
    if game_id is not None:
        await ctx.send(f'{mention(sender_id)} successfully left game {game_id}.')
        if new_host_id is not None:
            await ctx.send(f'{mention(new_host_id)} is now the host of game {game_id}.')

    else:
        await ctx.send(f'{mention(sender_id)} is not in a waiting or active game.')


@bot.command()
async def start(ctx: Context, join_code: Optional[str] = None):
    if join_code is None:
        await ctx.send('Could not start game because join code was not provided!')
        return

    elif not valid_join_code(join_code):
        await ctx.send(f'{join_code} is not a valid join code!')
        return

    game_id = await game_storage.start(ctx.author.id, join_code)
    signed_ids = await game_storage.get_signed_for_game(game_id)
    mentions = ' '.join(mention(user_id) for user_id in signed_ids)
    await ctx.send(f'Game {game_id} has started with join code: {join_code} {mentions}')


@bot.command()
async def setcode(ctx: Context, join_code: str):
    if not valid_join_code(join_code):
        await ctx.send(f'{join_code} is not a valid join code!')
        return

    game_id = await game_storage.set_code(ctx.author.id, join_code)
    signed_ids = await game_storage.get_signed_for_game(game_id)
    mentions = ' '.join(mention(user_id) for user_id in signed_ids)
    await ctx.send(f'New join code for game {game_id}: {join_code} {mentions}')


@bot.command()
async def evict(ctx: Context, user_id: Optional[int] = None):
    if user_id is None:
        await ctx.send(f'Which user do you want to evict, {mention(ctx.author.id)}?')
        return

    game_id, new_host_id = await game_storage.remove_from_game(user_id)
    if game_id is not None:
        await ctx.send(f'Successfully evicted {mention(user_id)} from game {game_id}.')
        if new_host_id is not None:
            await ctx.send(f'{mention(new_host_id)} is now the host of game {game_id}.')

    else:
        await ctx.send(f'{mention(user_id)} is not in a waiting or active game.')


@bot.command()
async def players(ctx: Context, game_id: Optional[int] = None):
    if game_id is None:
        await ctx.send(f'Which game do you want to get signed/active players for, {mention(ctx.author.id)}?')
        return

    signed_ids = set(await game_storage.get_signed_for_game(game_id))
    member_map = {member.id: member.name for member in ctx.guild.members}
    formatted = ', '.join(member_map[user_id] for user_id in signed_ids)
    await ctx.send(f'Signed/active players for game {game_id}: {formatted}')


@bot.command()
async def waiting(ctx: Context):
    queue = await game_storage.get_by_status('waiting')
    if queue:
        formatted = '\n'.join(f'ID: {game_id} Host: {username(ctx, host_id)} Players: {signed_count}/10 '
                              for game_id, host_id, _, signed_count in queue)
        await ctx.send(f'Games currently waiting for players:\n{formatted}')

    else:
        await ctx.send('There are no games currently waiting for players.')


@bot.command()
async def active(ctx: Context):
    queue = await game_storage.get_by_status('active')
    if queue:
        formatted = '\n'.join(f'ID: {game_id} Host: {username(ctx, host_id)} Players: {signed_count} / 10 '
                              f'Join code: {join_code}'
                              for game_id, host_id, join_code, signed_count in queue)
        await ctx.send(f'Active games:\n{formatted}')

    else:
        await ctx.send('There are no games currently active.')


@bot.command()
async def randommap(ctx: Context):
    maps = ['The Skeld', 'MIRA HQ', 'Polus']
    map_name = maps[random.randint(0, 2)]
    await ctx.send(f'The randomly chosen map is **{map_name}**.')


@bot.command()
@commands.has_permissions(administrator=True)
async def sql(ctx: Context, *query: str):
    try:
        result = await game_storage._connection.fetch(' '.join(query))
        message = '\n'.join(', '.join(str(value) for value in row) for row in result)

    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'

    await ctx.send(message or '<No result>')


bot.run(token)
