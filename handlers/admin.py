from contextlib import suppress

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import db
from config import ADMIN_IDS

router = Router()


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in ADMIN_IDS


@router.message(Command("stats"))
async def stats(message: Message) -> None:
    if not _is_admin(message):
        return
    s = await db.global_stats()
    await message.answer(
        "<b>Статистика</b>\n"
        f"👤 Пользователей: {s['users']}\n"
        f"🎞 Кружков: {s['approved']} одобрено · {s['pending']} на проверке\n"
        f"👀 Просмотров: {s['views']}\n"
        f"⭐ Продано: {s['stars']}"
    )


@router.message(Command("give"))
async def give(message: Message, command: CommandObject) -> None:
    if not _is_admin(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer("/give &lt;user_id&gt; &lt;coins&gt;")
        return
    user_id, amount = int(parts[0]), int(parts[1])
    await db.add_coins(user_id, amount)
    balance = (await db.get_user(user_id))["coins"]
    await message.answer(f"Готово. Баланс {user_id}: {balance} 🪙")


@router.message(Command("ban", "unban"))
async def ban(message: Message, command: CommandObject) -> None:
    if not _is_admin(message):
        return
    if not (command.args or "").strip().isdigit():
        await message.answer(f"/{command.command} &lt;user_id&gt;")
        return
    user_id = int(command.args.strip())
    banned = command.command == "ban"
    await db.set_banned(user_id, banned)
    await message.answer(f"{user_id}: {'забанен' if banned else 'разбанен'}")


@router.message(Command("refund"))
async def refund(message: Message, command: CommandObject) -> None:
    """/refund <telegram_payment_charge_id> — returns Stars to the buyer."""
    if not _is_admin(message):
        return
    charge_id = (command.args or "").strip()
    if not charge_id:
        await message.answer("/refund &lt;charge_id&gt;")
        return

    payment = await db.get_payment(charge_id)
    if payment is None:
        await message.answer("Платёж не найден.")
        return
    if payment["refunded"]:
        await message.answer("Уже возвращён.")
        return

    try:
        await message.bot.refund_star_payment(
            user_id=payment["user_id"],
            telegram_payment_charge_id=charge_id,
        )
    except TelegramAPIError as error:
        await message.answer(f"Telegram отказал: {error}")
        return

    await db.mark_refunded(charge_id)
    await db.deduct_clamped(payment["user_id"], payment["coins"])
    with suppress(TelegramAPIError):
        await message.bot.send_message(
            payment["user_id"],
            f"⭐ Возврат {payment['stars']} — списал {payment['coins']} 🪙.",
        )
    await message.answer(f"Возвращено {payment['stars']} ⭐.")
