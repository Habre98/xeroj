from telegram import InlineKeyboardMarkup, InlineKeyboardButton  # type: ignore
import asyncio 
import httpx 

from telegram.ext import (  # type: ignore
    CallbackContext,
)  # type: ignore
from helper_func import (
    load_wallets,
    create_solana_wallet,
    save_wallet,
    get_next_wallet_index,
)

from solders.pubkey import Pubkey  # type: ignore
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import  TokenAccountOpts
from solana.exceptions import SolanaRpcException # Added
from spl.token.constants import TOKEN_PROGRAM_ID 
import struct 
import os
import logging

from linkx import linkx_command
from get_symbol import get_token_symbol_from_api


logger = logging.getLogger(__name__)


async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("Manage Wallets", callback_data="manage_wallets")],
        [InlineKeyboardButton("Link your X account", callback_data="linkx_command")],
        [InlineKeyboardButton("Sell Tokens", callback_data="sell_tokens_entry")], 
        [InlineKeyboardButton("Set Slippage", callback_data="set_slippage")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(
                text="Welcome to the Xero X Sniper Bot! Please choose an option:",
                reply_markup=reply_markup,
            )
        except Exception as e: 
            logger.info(f"Failed to edit message in start, sending new: {e}")
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=open('media/BundlePro.mp4', 'rb'), 
                caption="Welcome to the Xero X Sniper Bot! Please choose an option:",
                reply_markup=reply_markup,
                width=640,
                height=360,
                supports_streaming=True
            )
    else:
        await context.bot.send_video(
             chat_id=update.effective_chat.id,
            video=open('media/BundlePro.mp4', 'rb'), 
            caption="Welcome to the Xero X Sniper Bot! Please choose an option:",
            reply_markup=reply_markup,
            width=640,
            height=360,
            supports_streaming=True
        )


async def manage_wallets_command(update, context):
    query = update.callback_query
    if query:
        await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Add New Wallet", callback_data="request_add_wallet")],
        [InlineKeyboardButton("View My Wallets", callback_data="request_my_wallets")],
        [InlineKeyboardButton("⬅ Back", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "Manage your wallets:"
    if query:
        try:
            await query.edit_message_text(text=message_text, reply_markup=reply_markup)
        except Exception as e:
            logger.info(f"Failed to edit message in manage_wallets_command, sending new: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup)


async def add_wallet_command(update, context):
    keyboard = [
        [InlineKeyboardButton("Generate New Wallet", callback_data="generate_new_wallet")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "To add a new Solana wallet, you can generate a new one."

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    elif update.message: 
        await update.message.reply_text(text=message_text, reply_markup=reply_markup)
    else: 
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup)


async def my_wallets_command(update, context):
    query = update.callback_query
    user_id_for_wallets = None
    chat_id_for_message = None

    if query:
        await query.answer()
        user_id_for_wallets = str(query.from_user.id)
        chat_id_for_message = query.message.chat_id
        try:
            await query.edit_message_text(text="Fetching your wallet balances, please wait...")
        except Exception as e:
            logger.info(f"Could not edit message in my_wallets_command (query): {e}")
    elif update.message:
        user_id_for_wallets = str(update.message.from_user.id)
        chat_id_for_message = update.message.chat_id
        await context.bot.send_message(chat_id=chat_id_for_message, text="Fetching your wallet balances, please wait...")
    else:
        logger.warning("my_wallets_command called without query or message.")
        return

    loaded_wallets = load_wallets(user_id_for_wallets)
    final_message_text = ""

    if not loaded_wallets:
        final_message_text = "You have no wallets. Use /addwallet or 'Add New Wallet' to create one."
    else:
        wallet_list_str = "Your Wallets:\n"
        for i, wallet_kp in enumerate(loaded_wallets):
            pubkey_str = str(wallet_kp.pubkey())
            wallet_list_str += f"\n🏦 Wallet {i} (`{pubkey_str[:4]}...{pubkey_str[-4:]}`):\n"
            try:
                balance_info = await get_wallet_balance(pubkey_str) 
                sol_balance = balance_info.get("sol_balance", 0)
                tokens = balance_info.get("tokens", [])
                
                wallet_list_str += f"  SOL: `{sol_balance:.4f}`\n"
                
                if tokens:
                    wallet_list_str += "  Tokens:\n"
                    for token in tokens:
                        token_display = token.get('symbol', f"{token['mint'][:4]}...{token['mint'][-4:]}")
                        wallet_list_str += f"    - {token_display}: `{token['amount']:.4f}`\n"
                else:
                    wallet_list_str += "  No SPL tokens found.\n"
            except Exception as e:
                logger.error(f"Failed to get balance for wallet {pubkey_str}: {e}")
                wallet_list_str += "  Could not fetch balance.\n"
        final_message_text = wallet_list_str
    
    back_button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Wallet Management", callback_data="manage_wallets")]])
    
    # Determine the RPC URL to use
    rpc_url = context.bot_data.get('solana_rpc_url', "https://api.mainnet-beta.solana.com")

    if not loaded_wallets:
        final_message_text = "You have no wallets. Use /addwallet or 'Add New Wallet' to create one."
    else:
        wallet_list_str = "Your Wallets:\n"
        for i, wallet_kp in enumerate(loaded_wallets):
            pubkey_str = str(wallet_kp.pubkey())
            wallet_list_str += f"\n🏦 Wallet {i} (`{pubkey_str[:4]}...{pubkey_str[-4:]}`):\n"
            try:
                # Pass rpc_url to get_wallet_balance
                balance_info = await get_wallet_balance(pubkey_str, rpc_url) 
                sol_balance = balance_info.get("sol_balance", 0)
                tokens = balance_info.get("tokens", [])
                
                wallet_list_str += f"  SOL: `{sol_balance:.4f}`\n"
                
                if tokens:
                    wallet_list_str += "  Tokens:\n"
                    for token in tokens:
                        token_display = token.get('symbol', f"{token['mint'][:4]}...{token['mint'][-4:]}")
                        wallet_list_str += f"    - {token_display}: `{token['amount']:.4f}`\n"
                else:
                    wallet_list_str += "  No SPL tokens found.\n"
            except Exception as e:
                logger.error(f"Failed to get balance for wallet {pubkey_str}: {e}")
                wallet_list_str += "  Could not fetch balance.\n"
        final_message_text = wallet_list_str
    
    if query: 
        try:
            await query.edit_message_text(text=final_message_text, parse_mode="Markdown", reply_markup=back_button_markup)
        except Exception as e: 
            logger.info(f"Failed to edit message in my_wallets_command (query) after fetching, sending new: {e}")
            await context.bot.send_message(chat_id=chat_id_for_message, text=final_message_text, parse_mode="Markdown", reply_markup=back_button_markup)
    elif update.message: 
         await context.bot.send_message(chat_id=chat_id_for_message, text=final_message_text, parse_mode="Markdown", reply_markup=back_button_markup)


async def select_wallets_command(update, context: CallbackContext):
    if context.user_data is None: context.user_data = {}
    user_id = update.message.from_user.id
    args = context.args
    if not args:
        await context.bot.send_message(chat_id=user_id, text="Usage: /selectwallets <index1> <index2> ...")
        return
    await context.bot.send_message(chat_id=user_id, text="select_wallets_command (original logic retained)")


async def prompt_generate_new_wallet(update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    try:
        wallet_index = get_next_wallet_index(user_id)
        await query.edit_message_text(text=f"Generating new wallet #{wallet_index}...")
        wallet_data = await create_solana_wallet()

        if wallet_data is None: raise Exception("Failed to generate wallet data.")
        private_key_b58 = wallet_data["private_key"] 
        public_key_str = wallet_data["address"]
        
        if save_wallet(user_id, private_key_b58, wallet_index):
            message_text = f"✅ Successfully generated new wallet #{wallet_index}\n\nPublic Key:\n`{public_key_str}`\n\nPrivate Key (Base58 of full keypair):\n`{private_key_b58}`\n\n⚠️ Store your keys safely and do not share them!"
        else:
            message_text = "Failed to save the new wallet. Please try again."
    except Exception as e:
        logger.error(f"Error in prompt_generate_new_wallet: {e}")
        message_text = "An error occurred while generating the wallet. Please try again."

    back_button = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Wallet Management", callback_data="manage_wallets")]])
    await query.edit_message_text(text=message_text, parse_mode="Markdown", reply_markup=back_button)


async def get_wallet_balance(wallet_address: str, solana_rpc_url: str): # Added solana_rpc_url parameter
    async_client = None 
    try:
        if not wallet_address or not isinstance(wallet_address, str):
            logger.error("Invalid or None wallet address provided.")
            return {"sol_balance": 0, "tokens": []}
        
        pubkey = Pubkey.from_string(wallet_address)
        # Use the passed solana_rpc_url
        async_client = AsyncClient(solana_rpc_url) 
        
        sol_balance = 0
        try:
            response = await async_client.get_balance(pubkey)
            sol_balance = response.value / 1_000_000_000 if response.value else 0
        except Exception as e: # Catching broadly here for SOL balance, can be more specific if needed
            logger.error(f"Error getting SOL balance for {wallet_address}: {e}")
            # Continue to try fetching token balances even if SOL balance fails

        token_infos = []
        token_accounts_result = None
        MAX_RETRIES = 3
        RETRY_DELAY_BASE = 1.5 

        for attempt in range(MAX_RETRIES):
            try:
                token_accounts_result = await async_client.get_token_accounts_by_owner(
                    pubkey,
                    TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
                )
                logger.info(f"Successfully fetched token accounts for {wallet_address} on attempt {attempt + 1}")
                break 
            except SolanaRpcException as e_rpc:
                # Check if the cause is an HTTPStatusError and specifically a 429
                if isinstance(e_rpc.__cause__, httpx.HTTPStatusError) and e_rpc.__cause__.response.status_code == 429:
                    if attempt < MAX_RETRIES - 1:
                        delay_seconds = 11  # Default for 429
                        retry_after_header = e_rpc.__cause__.response.headers.get('retry-after')
                        if retry_after_header and retry_after_header.isdigit():
                            parsed_delay = int(retry_after_header)
                            delay_seconds = parsed_delay + 1 # Add a 1-second buffer
                            logger.info(f"Received retry-after header: {parsed_delay}s. Base delay for retry: {delay_seconds}s.")
                        
                        if attempt > 0: # If this is the 2nd or 3rd actual attempt (attempt index 1 or 2)
                            additional_delay = attempt * 3 # e.g. 3s for 2nd attempt, 6s for 3rd.
                            delay_seconds += additional_delay
                            logger.info(f"Adding incremental delay of {additional_delay}s for attempt {attempt + 1}.")

                        logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} for {wallet_address}: Rate limit (429 via SolanaRpcException) for get_token_accounts_by_owner. Retrying in {delay_seconds}s...")
                        await asyncio.sleep(delay_seconds)
                    else:
                        logger.error(f"Max retries reached for {wallet_address} (get_token_accounts_by_owner) due to rate limiting via SolanaRpcException.")
                        raise # Re-raise SolanaRpcException
                else:
                    logger.error(f"Attempt {attempt + 1}/{MAX_RETRIES} for {wallet_address}: Non-429 SolanaRpcException (get_token_accounts_by_owner): {e_rpc}", exc_info=True)
                    raise # Re-raise other SolanaRpcExceptions immediately
            except httpx.RequestError as e_req: 
                if attempt < MAX_RETRIES - 1:
                    delay_seconds = 5 * (attempt + 1)
                    logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} for {wallet_address}: Network error (get_token_accounts_by_owner): {e_req}. Retrying in {delay_seconds}s...")
                    await asyncio.sleep(delay_seconds)
                else:
                    logger.error(f"Max retries reached for {wallet_address} (get_token_accounts_by_owner) due to network error.")
                    raise # Re-raise RequestError
            except Exception as e_other: # Catch any other unexpected error during an attempt
                if attempt < MAX_RETRIES - 1:
                    delay_seconds = 5 * (attempt + 1)
                    logger.error(f"Attempt {attempt + 1}/{MAX_RETRIES} for {wallet_address}: Unexpected error during get_token_accounts_by_owner attempt: {e_other}. Retrying in {delay_seconds}s...", exc_info=True)
                    await asyncio.sleep(delay_seconds) 
                else:
                    logger.error(f"Max retries reached for {wallet_address} (get_token_accounts_by_owner) due to unexpected error.")
                    raise # Re-raise if last attempt

        # This outer try-except is for processing token_accounts_result if it was successfully fetched.
        # Exceptions raised from the retry loop above will be caught by the main get_wallet_balance try-except.
        if token_accounts_result and token_accounts_result.value:
            logger.info(f"Found {len(token_accounts_result.value)} token accounts for {wallet_address}")
            for acc_info in token_accounts_result.value:
                try:
                    acc_data = acc_info.account.data
                    if len(acc_data) >= 165: 
                        mint_bytes = acc_data[:32]
                        amount_bytes = acc_data[64:72]
                        mint_address = str(Pubkey(mint_bytes))
                        token_amount_raw = struct.unpack('<Q', amount_bytes)[0]

                        if token_amount_raw > 0:
                            decimals = 6 
                            symbol = "Unknown"
                            try:
                                mint_account_info_res = await async_client.get_account_info(Pubkey.from_string(mint_address))
                                if mint_account_info_res.value and mint_account_info_res.value.data:
                                    if len(mint_account_info_res.value.data) > 44:
                                       decimals = mint_account_info_res.value.data[44]
                                symbol = await get_token_symbol_from_api(mint_address) or symbol
                            except Exception as e_mint_details:
                                logger.debug(f"Could not fetch extended details for mint {mint_address}: {e_mint_details}")

                            ui_amount = token_amount_raw / (10**decimals)
                            token_infos.append({
                                "mint": mint_address, "amount": ui_amount,
                                "symbol": symbol, "decimals": decimals,
                                "raw_amount": token_amount_raw
                            })
                except Exception as e_token_proc:
                    logger.error(f"Error processing one token account for {wallet_address}: {e_token_proc}")
                    continue 
        elif not token_accounts_result: # Only if retry loop somehow exited without success and without raising an error
             logger.warning(f"Token accounts result was None for {wallet_address} after retries, but no exception was propagated from retry loop.")
        # If token_accounts_result is not None but .value is empty, it's handled (no tokens).

        return {"sol_balance": sol_balance, "tokens": token_infos}
    
    except Exception as e_outer: 
        # This catches errors from get_balance, re-raised errors from the retry loop,
        # or errors from processing token_infos if token_accounts_result was valid.
        logger.error(f"Error getting token accounts or processing for {wallet_address}: {e_outer}", exc_info=True)
        # The original log was "Critical error in get_wallet_balance..."
        # The current one is more specific to token accounts if an error is re-raised from the loop.
        # If SOL balance failed, that's logged separately.
        return {"sol_balance": sol_balance, "tokens": []} # Return SOL balance if fetched, empty tokens.
    finally:
        if async_client:
            await async_client.close()


async def button_callback(update, context): 
    query = update.callback_query
    if query.data == "manage_wallets":
        await manage_wallets_command(update, context)
    elif query.data == "request_add_wallet":
        await add_wallet_command(update, context)
    elif query.data == "request_my_wallets":
        await my_wallets_command(update, context)
    elif query.data == "generate_new_wallet":
        await prompt_generate_new_wallet(update, context)
    elif query.data == "linkx_command":
        await linkx_command(update, context) 
    elif query.data == "set_slippage":
        await prompt_slippage_selection(update, context) 
    elif query.data == "back_to_main_menu":
        await start(update, context) 
    else:
        logger.info(f"Unhandled generic callback query: {query.data}")
        try:
            await query.answer("Action not recognized or already processed.")
        except Exception as e:
            logger.debug(f"Failed to answer unhandled callback {query.data}: {e}")


async def prompt_slippage_selection(update, context):
    query = update.callback_query
    await query.answer()  
    message_text = "Please enter your desired slippage percentage (e.g., 1 for 1%, 0.5 for 0.5%). Valid range: 0.1% to 50%."
    try:
        await query.edit_message_text(text=message_text)
    except Exception as e:
        logger.info(f"Error editing message in prompt_slippage_selection: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text)
    if context.user_data is None: context.user_data = {}
    context.user_data['awaiting_slippage_input'] = True


async def handle_slippage_input(update, context):
    if not context.user_data or not context.user_data.get('awaiting_slippage_input'):
        return False

    try:
        slippage_text = update.message.text
        slippage_value = float(slippage_text)
        if not (0.1 <= slippage_value <= 50):
            await update.message.reply_text("Invalid input. Slippage must be between 0.1 and 50. Please try again or /cancel.")
            return True 

        context.user_data['slippage_percentage'] = slippage_value 
        context.user_data['awaiting_slippage_input'] = False
        await update.message.reply_text(f"✅ Global Slippage set to {slippage_value}%.")
        return True 
    except ValueError:
        await update.message.reply_text("Invalid format. Please enter a number for slippage (e.g., 1 or 0.5). Try again or /cancel.")
        return True 
    except Exception as e:
        logger.error(f"Error in handle_slippage_input: {e}")
        await update.message.reply_text("An error occurred processing slippage. Please try again or /cancel.")
        context.user_data['awaiting_slippage_input'] = False 
        return True
