from telegram.ext import ContextTypes  # type: ignore
from mention_linker import mention_polling_loop
import tweepy  # type: ignore


# async def fetch_bot_x_id(context):
#     twitter_client = context.bot_data.get("twitter_client")
#     if not twitter_client:
#         print("❌ Twitter client no está en context.bot_data")
#         return

#     try:
#         user_data = twitter_client.get_user(username="xeroai_sol")
#         if user_data.data:
#             context.bot_data["xeroai_sol_user_id"] = user_data.data["id"]
#             print(f"✅ ID del bot de X: {user_data.data['id']}")
#         else:
#             print("❌ No se pudo obtener el ID del bot de X")
#     except tweepy.TooManyRequests as e_rate_limit:
#         print(
#             f"CRITICAL: Rate limit hit while fetching bot's own X ID (xeroAi_sol) in x_utils.py: {e_rate_limit}. This may affect bot functionality."
#         )
#     except Exception as e:
#         print(f"❌ Error fetching bot's X ID: {e}")


async def fetch_bot_x_id(context):
    try:
        # Our main account
        XeroAi_sol_id = "1907969641865162753"

        if XeroAi_sol_id:
            context.bot_data["XeroAi_sol_user_id"] = XeroAi_sol_id
            print(f"✅ ID del bot de X: {XeroAi_sol_id}")
        else:
            print("❌ El ID del bot de X es incorrecto")
    except tweepy.TooManyRequests as e_rate_limit:
        print(
            f"CRITICAL: Rate limit hit while fetching bot's own X ID (XeroAi_sol) in x_utils.py: {e_rate_limit}. This may affect bot functionality."
        )
    except Exception as e:
        print(f"❌ Error fetching bot's X ID: {e}")


async def start_mention_watcher(context):
    bot = context.bot
    bot_x_id = context.bot_data.get("XeroAi_sol_user_id") # Changed key
    twitter_client = context.bot_data.get("twitter_client")

    if not twitter_client:
        print("❌ Cliente de Twitter no proporcionado.")
        return

    if not bot_x_id:
        print("❌ No se encontró XeroAi_sol_user_id en context.bot_data.") # Updated message
        return

    print("🚀 Iniciando watcher de menciones con comando de vinculación")

    await mention_polling_loop(client=twitter_client, bot=bot, context=context)
