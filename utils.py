from string import ascii_uppercase

from discord.ext.commands import Context


def mention(user_id: int) -> str:
    return f'<@{user_id}>'


def username(ctx: Context, user_id: int) -> str:
    member = ctx.guild.get_member(user_id)
    return member.name if member is not None else '<unknown user>'


def valid_join_code(join_code: str) -> bool:
    correct_length = len(join_code) == 6
    has_non_alphabetical = set(join_code.upper()) - set(ascii_uppercase)
    return correct_length and not has_non_alphabetical
