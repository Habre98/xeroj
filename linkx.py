import random
import string
from telegram import Update  # type: ignore
from telegram.ext import ContextTypes  # type: ignore
import os
import json

LINK_CODES_KEY = "link_codes"


def generate_code(length=8):
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


async def linkx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = generate_code()

    # Recuperar o crear diccionario de códigos
    link_codes = context.bot_data.get(LINK_CODES_KEY, {})
    link_codes[code] = user_id
    context.bot_data[LINK_CODES_KEY] = link_codes

    await context.bot.send_message(
        chat_id=user_id,
        text=f"🔗 To link your X account, comment the following in a tweet with your X account: X:\n\n"
        f"`@XeroAi_sol link {code}`\n\n"
        f"Once detected, I will confirm here that your account has been linked..",
        parse_mode="Markdown",
    )


LINKED_ACCOUNTS_FILE = os.path.join("data", "linked_accounts.json")


def load_linked_accounts() -> dict:
    if os.path.exists(LINKED_ACCOUNTS_FILE):
        with open(LINKED_ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    return {}


async def linked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = str(update.effective_user.id)
    linked_accounts = load_linked_accounts()
    user_id = update.effective_user.id
    # Buscar si algún username de X está vinculado con este ID
    for x_username, tg_id in linked_accounts.items():
        if str(tg_id) == telegram_user_id:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔗 You are linked to the account of X: @{x_username}",
            )
            return

    await context.bot.send_message(
        chat_id=user_id, text="❌ You don't have any X accounts linked yet."
    )


async def unlinkx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = str(update.effective_user.id)
    linked_accounts = load_linked_accounts()

    # Buscar qué username de X está vinculado con este Telegram ID
    x_to_unlink = None
    for x_username, tg_id in linked_accounts.items():
        if str(tg_id) == telegram_user_id:
            x_to_unlink = x_username
            break

    if x_to_unlink:
        del linked_accounts[x_to_unlink]
        await save_linked_accounts(linked_accounts)
        await context.bot.send_message(
            chat_id=telegram_user_id,
            text=f"❎ Your account has been unlinked from X: @{x_to_unlink}",
        )
    else:
        await context.bot.send_message(
            chat_id=telegram_user_id,
            text="❌ There is no X account linked to your user.",
        )


async def save_linked_accounts(linked_accounts: dict):
    with open(LINKED_ACCOUNTS_FILE, "w") as f:
        json.dump(linked_accounts, f)
