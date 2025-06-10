import asyncio
import telegram # Not strictly needed here but often useful

from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    PicklePersistence,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)
# Wallet related imports
from wallets import (
    start,
    add_wallet_command,
    my_wallets_command,
    select_wallets_command, # Assuming this is for a different feature, keeping it.
    button_callback as wallet_button_callback, # Renamed to avoid confusion
    handle_slippage_input,
    # prompt_slippage_selection is not directly called by main, but by a button_callback
)
# Sell flow related imports
from sell import (
    sell_button_callback,
    handle_sell_text_input,
    # sell_tokens_entry_point_handler is now called via sell_button_callback
)

# X Monitor related imports (assuming these are for other features)
from x_monitor import (
    add_target_command,
    list_targets_command,
    removetarget_command,
    handle_remove_target_callback,
    monitor_users,
)
# LinkX related imports
from linkx import (
    linkx_command,
    linked_command,
    unlinkx_command,
)
# X Utils and Mention related imports
from x_utils import (
    fetch_bot_x_id,
)
from mention_linker import (
    mention_polling_loop, # If this is the unified loop, keep it.
    # mention_sniping_loop, # If unified_mention_loop replaces both, this might be obsolete.
                           # Assuming unified_mention_loop is the one to use based on previous logs.
    unified_mention_loop, # Preferred based on previous observations
)

import logging
import os
import tweepy  # type: ignore
from dotenv import load_dotenv  # type: ignore

# Logging config
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL")
DEFAULT_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"

if HELIUS_RPC_URL:
    final_rpc_url = HELIUS_RPC_URL
    logger.info(f"Using Helius RPC URL: {final_rpc_url}")
else:
    final_rpc_url = DEFAULT_SOLANA_RPC_URL
    logger.warning(f"HELIUS_RPC_URL not found in .env. Falling back to default public RPC: {final_rpc_url}. Performance may be limited; using a dedicated RPC like Helius is recommended.")

BOT_TOKEN = os.getenv("BOT_TOKEN")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")


if BOT_TOKEN is None:
    print("Please set the BOT_TOKEN environment variable.")
    exit(1)
if TWITTER_BEARER_TOKEN is None:
    print("Please set the TWITTER_BEARER_TOKEN environment variable.")
    exit(1)


twitter_client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN, wait_on_rate_limit=False # wait_on_rate_limit is often safer
)

background_tasks = set() # To keep track of asyncio tasks


async def start_monitoring_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to periodically monitor users/targets."""
    application = context.application
    def get_all_targets(): # Simplified, actual implementation might be more complex
        all_targets = []
        for chat_data in application.chat_data.values():
            for target in chat_data.get("targets", []):
                all_targets.append(target) # Assuming target includes chat_id
        return all_targets
    # Assuming monitor_users is correctly defined to accept these params
    # await monitor_users(context, get_all_targets, application)
    logger.info("Periodic monitoring job triggered (actual call commented out).")


async def initialize_bot_systems(app: telegram.ext.Application):
    """Initialize bot systems like Twitter client and start background tasks."""
    logger.info("🔧 Initializing bot systems...")
    app.bot_data["twitter_client"] = twitter_client
    try:
        await fetch_bot_x_id(app) # Pass application directly or context if fetch_bot_x_id expects context
        logger.info("✅ Twitter client initialized and bot X ID fetched.")

        # Start the unified mention system
        # Ensure unified_mention_loop is correctly defined to accept these params
        task = asyncio.create_task(unified_mention_loop(twitter_client, app.bot, app))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        logger.info("✅ Unified mention system (linking & sniping) started.")

    except Exception as e:
        logger.error(f"❌ Error initializing bot systems: {e}", exc_info=True)


async def combined_text_handler(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text inputs, trying sell input first, then slippage."""
    if await handle_sell_text_input(update, context):
        return
    
    # If not handled by sell input, try slippage input
    # handle_slippage_input from wallets.py should also return True/False
    if await handle_slippage_input(update, context):
        return
    
    # If no specific text input was handled, you can add a default behavior here if needed
    # logger.info(f"Generic text message received, not handled by specific input handlers: {update.message.text}")


def main():
    print(">>> Iniciando bot...")
    # Consider using a more descriptive name for the persistence file
    persistence = PicklePersistence(filepath="xerox_sniper_bot_data.pickle") 
    application = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()

    # Store the determined RPC URL in bot_data
    application.bot_data['solana_rpc_url'] = final_rpc_url

    # Initialize bot systems (e.g., Twitter client)
    # Schedule initialize_bot_systems to run once via the job queue
    application.job_queue.run_once(initialize_bot_systems, when=5) # Runs 5 seconds after scheduler starts

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addwallet", add_wallet_command))
    application.add_handler(CommandHandler("mywallets", my_wallets_command))
    application.add_handler(CommandHandler("selectwallets", select_wallets_command)) # If it's for scanner
    
    # X Monitor Command Handlers (if used)
    application.add_handler(CommandHandler("addtarget", add_target_command))
    application.add_handler(CommandHandler("listtargets", list_targets_command))
    application.add_handler(CommandHandler("removetarget", removetarget_command))

    # LinkX Command Handlers
    application.add_handler(CommandHandler("linkx", linkx_command))
    application.add_handler(CommandHandler("linked", linked_command))
    application.add_handler(CommandHandler("unlinkx", unlinkx_command))

    # Callback Query Handlers
    # Sell flow callbacks (specific, should come first)
    application.add_handler(CallbackQueryHandler(sell_button_callback, pattern=r"^sell_"))
    
    # X Monitor callbacks (specific)
    application.add_handler(CallbackQueryHandler(handle_remove_target_callback, pattern=r"^remove_target:"))
    
    # Wallet and other general callbacks (more generic, comes after specific ones)
    application.add_handler(CallbackQueryHandler(wallet_button_callback)) # Catches non-sell callbacks

    # Message Handlers
    # Combined text handler for slippage and sell inputs
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), combined_text_handler))
    
    # Job Queue for periodic tasks like monitoring
    # application.job_queue.run_repeating(start_monitoring_job, interval=60, first=10) # Example

    print(">>> Bot en ejecución...")
    application.run_polling()


if __name__ == "__main__":
    main()
