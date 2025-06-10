from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from helper_func import load_wallets # Ensure load_wallets returns solders.Keypair
from wallets import get_wallet_balance 
import logging
import math 
import base64 
from jupiter_client import get_jupiter_quote, get_jupiter_swap_transaction, SOL_MINT_ADDRESS

# Solana specific imports for transaction handling
from solders.keypair import Keypair as SoldersKeypair 
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.signature import Signature 
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts, Commitment # Removed TxSig
from solana.rpc.core import RPCException 
from solana.exceptions import SolanaRpcException 

# Typing and asyncio imports
import asyncio
import httpx 
from typing import Callable, Awaitable, TypeVar, Optional, Any, List, Dict 
import time 

T = TypeVar('T') 


logger = logging.getLogger(__name__)

# --- Sell Process State Cleanup ---
SELL_PROCESS_USER_DATA_KEYS = [
    'sell_selected_wallet_pubkey', 'sell_selected_wallet_index', 
    'sell_wallet_tokens_cache', 'sell_selected_token_mint', 
    'sell_selected_token_symbol', 'sell_selected_token_balance', 
    'sell_selected_token_decimals', 'awaiting_exact_token_input_for_sell',
    'awaiting_exact_sol_input_for_sell', 'sell_final_token_amount',
    'sell_final_sol_target_amount', 'sell_type',
    'jupiter_swap_tx_b64', 'jupiter_last_valid_block_height'
]

def clear_sell_session_data(context):
    for key in SELL_PROCESS_USER_DATA_KEYS:
        context.user_data.pop(key, None)
    logger.info("Sell session data cleared from user_data.")

# --- Navigation Buttons ---
def get_sell_navigation_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu")],
        [InlineKeyboardButton("🔄 Sell Another", callback_data="sell_tokens_entry")]
    ])

# --- Retry Helper for RPC Calls ---
async def async_rpc_call_with_retry(
    awaitable_rpc_call_func: Callable[[], Awaitable[T]],
    call_description: str,
    logger_instance: logging.Logger, 
    max_retries: int = 3
) -> Optional[T]:
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = await awaitable_rpc_call_func()
            logger_instance.info(f"Successfully called {call_description} on attempt {attempt + 1}/{max_retries}.")
            return response
        except SolanaRpcException as e_rpc:
            last_exception = e_rpc
            if isinstance(e_rpc.__cause__, httpx.HTTPStatusError) and e_rpc.__cause__.response.status_code == 429:
                if attempt < max_retries - 1:
                    delay_seconds = 11 
                    try:
                        retry_after_header = e_rpc.__cause__.response.headers.get('retry-after')
                        if retry_after_header and retry_after_header.isdigit():
                            parsed_delay = int(retry_after_header)
                            delay_seconds = parsed_delay + 1 
                            logger_instance.info(f"Received retry-after header for {call_description}: {parsed_delay}s.")
                    except Exception as header_ex:
                        logger_instance.warning(f"Could not parse retry-after header for {call_description}: {header_ex}")
                    if attempt > 0: 
                        delay_seconds += (attempt * 3) 
                    logger_instance.warning(f"Attempt {attempt + 1}/{max_retries} for {call_description}: Rate limit (429 via SolanaRpcException). Retrying in {delay_seconds}s...")
                    await asyncio.sleep(delay_seconds)
                else:
                    logger_instance.error(f"Max retries ({max_retries}) reached for {call_description} due to rate limiting (429 via SolanaRpcException). Last error: {e_rpc}")
            else:
                logger_instance.error(f"Attempt {attempt + 1}/{max_retries} for {call_description}: Non-429 SolanaRpcException encountered. Failing fast for this error. Exception: {e_rpc}", exc_info=True)
                return None 
        except httpx.RequestError as e_req: 
            last_exception = e_req
            if attempt < max_retries - 1:
                delay_seconds = 5 * (attempt + 1)
                logger_instance.warning(f"Attempt {attempt + 1}/{max_retries} for {call_description}: Network error: {e_req}. Retrying in {delay_seconds}s...")
                await asyncio.sleep(delay_seconds)
            else:
                logger_instance.error(f"Max retries ({max_retries}) reached for {call_description} due to network error. Last error: {e_req}")
        except Exception as e_other: 
            last_exception = e_other
            logger_instance.error(f"Attempt {attempt + 1}/{max_retries} for {call_description}: Unexpected error: {e_other}", exc_info=True)
            if attempt < max_retries - 1:
                delay_seconds = 5 * (attempt + 1) 
                await asyncio.sleep(delay_seconds)
            else:
                logger_instance.error(f"Max retries ({max_retries}) reached for {call_description} due to unexpected error. Last error: {e_other}")
    logger.error(f"All {max_retries} attempts failed for {call_description}. Last encountered exception: {last_exception}", exc_info=last_exception if last_exception else False)
    return None

# --- Custom Transaction Confirmation ---
async def custom_confirm_transaction(
    async_client: AsyncClient,
    signature: Signature, 
    desired_commitment: Commitment, 
    last_valid_block_height: int,
    logger_instance: logging.Logger, 
    polling_interval_secs: int = 3, 
    max_polling_duration_secs: int = 90 
) -> Dict[str, Any]:
    start_time = time.time()
    commitment_str = str(desired_commitment) 

    commitment_levels = {"processed": 0, "confirmed": 1, "finalized": 2}
    desired_level_val = commitment_levels.get(commitment_str.lower(), -1)
    if desired_level_val == -1:
        logger_instance.error(f"Invalid desired_commitment: {commitment_str} for signature {signature}")
        return {"status": "rpc_error", "error": f"Invalid desired_commitment: {commitment_str}", "signature": str(signature)}

    while True:
        if time.time() - start_time > max_polling_duration_secs:
            logger_instance.warning(f"Confirmation timeout for signature {signature} after {max_polling_duration_secs}s.")
            return {"status": "timeout", "signature": str(signature), "max_duration_secs": max_polling_duration_secs}

        logger_instance.debug(f"Polling signature status for {signature} (Attempt for {commitment_str})")
        
        get_statuses_call = lambda: async_client.get_signature_statuses([signature], search_transaction_history=True)
        
        status_response_wrapper = await async_rpc_call_with_retry(
            get_statuses_call,
            f"get_signature_statuses for {signature}",
            logger_instance 
        )

        if status_response_wrapper is None or status_response_wrapper.value is None:
            logger_instance.warning(f"Failed to get signature status for {signature} after retries, or empty response. Continuing polling.")
        else:
            status_info_list: Optional[List[Optional[Any]]] = status_response_wrapper.value # Changed TxSig to Any
            if not status_info_list or status_info_list[0] is None:
                logger_instance.debug(f"Signature {signature} not yet found or status is null. Continuing polling.")
            else:
                status_info = status_info_list[0]
                if status_info.err:
                    logger_instance.error(f"Transaction {signature} failed on-chain: {status_info.err}")
                    return {"status": "failed_on_chain", "error": status_info.err, "signature": str(signature)}
                
                current_commitment_str = str(status_info.confirmation_status).lower() if status_info.confirmation_status else "none"
                current_level_val = commitment_levels.get(current_commitment_str, -1)
                
                logger_instance.info(f"Signature {signature}: Current status = {current_commitment_str}, Desired = {commitment_str}")

                if current_level_val >= desired_level_val:
                    logger_instance.info(f"Transaction {signature} confirmed to {current_commitment_str} (met or exceeded {commitment_str}).")
                    return {"status": "success", "confirmation_response": status_info, "signature": str(signature)}
        
        logger_instance.debug(f"Checking block height for expiry for signature {signature}")
        get_bh_call = lambda: async_client.get_block_height(desired_commitment) 
        block_height_response_wrapper = await async_rpc_call_with_retry(
            get_bh_call,
            "get_block_height",
            logger_instance 
        )

        if block_height_response_wrapper is None or block_height_response_wrapper.value is None: 
            logger_instance.warning(f"Failed to get current block height for {signature} after retries. Cannot check for expiry. Continuing polling.")
        else:
            current_block_height = block_height_response_wrapper.value 
            if current_block_height > last_valid_block_height:
                logger_instance.warning(f"Transaction {signature} expired. Current block height {current_block_height} > LVBH {last_valid_block_height}.")
                return {"status": "expired", "signature": str(signature), "last_valid_block_height": last_valid_block_height}
        
        await asyncio.sleep(polling_interval_secs)

# --- Main Sell Flow Handlers (rest of the file remains the same) ---
async def sell_tokens_entry_point_handler(update, context):
    clear_sell_session_data(context) 
    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.edit_message_text(text="Sell process initiated. Fetching wallets...")
        except Exception as e: 
            logger.info(f"Note: Could not edit message in sell_tokens_entry_point_handler: {e}")
            if update.effective_chat:
                 await context.bot.send_message(chat_id=update.effective_chat.id, text="Sell process initiated. Fetching wallets...")
    else: 
        if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Sell process initiated. Fetching wallets...")
    await prompt_wallet_selection(update, context)


async def prompt_wallet_selection(update, context):
    user_id = update.effective_user.id
    loaded_wallets = load_wallets(user_id)
    message_text = "Please select a wallet to sell from:\n\n"
    keyboard_buttons = []
    rpc_url = context.bot_data.get('solana_rpc_url', "https://api.mainnet-beta.solana.com")

    if not loaded_wallets:
        message_text = "You have no wallets. Please add a wallet first using the main menu."
        keyboard_buttons.append([InlineKeyboardButton("⬅ Back to Main Menu", callback_data="back_to_main_menu")])
    else:
        for index, wallet_kp in enumerate(loaded_wallets):
            pubkey = str(wallet_kp.pubkey())
            try:
                balance_info = await get_wallet_balance(pubkey, rpc_url) # Pass rpc_url
                sol_balance = balance_info.get("sol_balance", 0)
            except Exception as e:
                logger.error(f"Error fetching balance for {pubkey} in prompt_wallet_selection: {e}")
                sol_balance = 0 
            message_text += f"Wallet {index}: `{pubkey}` (SOL: {sol_balance:.4f})\n"
            keyboard_buttons.append(
                [InlineKeyboardButton(f"Wallet {index} (SOL: {sol_balance:.4f})", callback_data=f"sell_wallet_selected_{index}")]
            )
        keyboard_buttons.append([InlineKeyboardButton("⬅ Back to Main Menu", callback_data="back_to_main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e: 
            logger.info(f"Failed to edit message in prompt_wallet_selection, sending new: {e}")
            if update.effective_chat:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
         if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_wallet_selection_for_sell(update, context):
    query = update.callback_query
    await query.answer()
    try:
        wallet_index_str = query.data.split("sell_wallet_selected_")[-1]
        wallet_index = int(wallet_index_str)
    except (IndexError, ValueError) as e:
        logger.error(f"Error extracting wallet_index from callback data: {query.data} - {e}")
        await query.edit_message_text("Error: Could not process your selection.", reply_markup=get_sell_navigation_buttons())
        return
    user_id = str(query.from_user.id)
    user_wallets = load_wallets(user_id)
    if not 0 <= wallet_index < len(user_wallets):
        logger.warning(f"Invalid wallet_index {wallet_index} for user {user_id}")
        await query.edit_message_text("Error: Invalid wallet selection.", reply_markup=get_sell_navigation_buttons())
        return
    selected_wallet_kp = user_wallets[wallet_index]
    pubkey = str(selected_wallet_kp.pubkey())
    context.user_data['sell_selected_wallet_pubkey'] = pubkey
    context.user_data['sell_selected_wallet_index'] = wallet_index
    logger.info(f"User {user_id} selected wallet {wallet_index} ({pubkey}) for selling.")
    await query.edit_message_text(text=f"Fetching tokens for wallet `{pubkey[:4]}...{pubkey[-4:]}`...")
    try:
        rpc_url = context.bot_data.get('solana_rpc_url', "https://api.mainnet-beta.solana.com")
        balance_info = await get_wallet_balance(pubkey, rpc_url) # Pass rpc_url
        tokens_on_wallet = balance_info.get("tokens", [])
    except Exception as e:
        logger.error(f"Error fetching balance for {pubkey} in handle_wallet_selection_for_sell: {e}")
        await query.edit_message_text("Error: Could not fetch token balances.", reply_markup=get_sell_navigation_buttons())
        return
    context.user_data['sell_wallet_tokens_cache'] = tokens_on_wallet
    if not tokens_on_wallet:
        await query.edit_message_text(f"This wallet (`{pubkey[:4]}...{pubkey[-4:]}`) has no SPL tokens to sell.", reply_markup=get_sell_navigation_buttons())
        return
    keyboard_buttons = []
    message_text = f"Selected Wallet: `{pubkey}`\n\nPlease select a token to sell:\n\n"
    for token in tokens_on_wallet:
        token_symbol = token.get('symbol', 'Unknown')
        token_mint = token.get('mint')
        token_amount = token.get('amount', 0)
        if not token_mint:
            logger.warning(f"Token with symbol {token_symbol} for wallet {pubkey} has no mint address. Skipping.")
            continue
        button_text = f"{token_symbol} ({token_amount:.6f})"
        callback_data = f"sell_token_selected_{token_mint}"
        keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    if not keyboard_buttons:
        await query.edit_message_text(f"Found tokens in wallet `{pubkey[:4]}...{pubkey[-4:]}`, but could not prepare them for selection.", reply_markup=get_sell_navigation_buttons())
        return
    keyboard_buttons.append([InlineKeyboardButton("⬅ Back to Wallets", callback_data="sell_tokens_entry")])
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_token_selection_for_sell(update, context):
    query = update.callback_query
    await query.answer()
    try:
        token_mint = query.data.split("sell_token_selected_")[-1]
        if not token_mint: raise ValueError("Token mint is empty")
    except (IndexError, ValueError) as e:
        logger.error(f"Error extracting token_mint from callback data: {query.data} - {e}")
        await query.edit_message_text("Error: Could not process token selection.", reply_markup=get_sell_navigation_buttons())
        return
    tokens_cache = context.user_data.get('sell_wallet_tokens_cache', [])
    selected_token_info = next((t for t in tokens_cache if t.get('mint') == token_mint), None)
    wallet_idx = context.user_data.get('sell_selected_wallet_index')
    back_to_tokens_cb = f"sell_wallet_selected_{wallet_idx}" if wallet_idx is not None else "sell_tokens_entry"
    if not selected_token_info:
        logger.warning(f"Token {token_mint} not found in cache for user {query.from_user.id}.")
        await query.edit_message_text("Error: Token details outdated. Please select token again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Tokens", callback_data=back_to_tokens_cb)]]))
        return
    context.user_data['sell_selected_token_mint'] = selected_token_info['mint']
    context.user_data['sell_selected_token_symbol'] = selected_token_info.get('symbol', 'Unknown')
    context.user_data['sell_selected_token_balance'] = float(selected_token_info.get('amount', 0))
    context.user_data['sell_selected_token_decimals'] = int(selected_token_info.get('decimals', 6))
    logger.info(f"User {query.from_user.id} selected token {context.user_data['sell_selected_token_symbol']} ({token_mint}). Balance: {context.user_data['sell_selected_token_balance']}")
    message_text = (
        f"Selected Token: {context.user_data['sell_selected_token_symbol']} "
        f"(`{context.user_data['sell_selected_token_mint'][:4]}...{context.user_data['sell_selected_token_mint'][-4:]}`)\n"
        f"Your Balance: {context.user_data['sell_selected_token_balance']:.6f}\n\n"
        "Choose amount to sell or specify target:"
    )
    keyboard_buttons = [
        [InlineKeyboardButton("10%", callback_data="sell_amount_percent_10"), InlineKeyboardButton("25%", callback_data="sell_amount_percent_25")],
        [InlineKeyboardButton("50%", callback_data="sell_amount_percent_50"), InlineKeyboardButton("100%", callback_data="sell_amount_percent_100")],
        [InlineKeyboardButton("Enter Exact Token #", callback_data="sell_enter_token_amount")],
        [InlineKeyboardButton("Set SOL Target", callback_data="sell_enter_sol_amount")],
    ]
    keyboard_buttons.append([InlineKeyboardButton("⬅ Back to Tokens", callback_data=back_to_tokens_cb)])
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_sell_amount_percent(update, context):
    query = update.callback_query
    await query.answer()
    try:
        percentage_str = query.data.split("sell_amount_percent_")[-1]
        percentage = int(percentage_str)
        if not (0 < percentage <= 100): raise ValueError("Percentage out of range")
    except (IndexError, ValueError) as e:
        logger.error(f"Error extracting percentage from {query.data}: {e}")
        token_mint = context.user_data.get('sell_selected_token_mint')
        cb = f"sell_token_selected_{token_mint}" if token_mint else "sell_tokens_entry"
        await query.edit_message_text("Error: Invalid percentage.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=cb)]]))
        return
    balance = context.user_data.get('sell_selected_token_balance')
    if balance is None: 
        logger.warning("Missing balance for percentage calculation.")
        await query.edit_message_text("Error: Token details missing. Please restart.", reply_markup=get_sell_navigation_buttons())
        return
    token_amount_to_sell = balance * (percentage / 100.0)
    context.user_data['sell_final_token_amount'] = token_amount_to_sell
    context.user_data['sell_type'] = 'tokens'
    logger.info(f"User {query.from_user.id} selected {percentage}% of token, amount: {token_amount_to_sell}")
    await confirm_and_execute_sell(update, context, from_query=True)


async def prompt_exact_token_amount(update, context):
    query = update.callback_query
    await query.answer()
    token_symbol = context.user_data.get('sell_selected_token_symbol', 'token')
    token_mint = context.user_data.get('sell_selected_token_mint')
    if not token_mint:
        await query.edit_message_text("Error: Selected token details lost.", reply_markup=get_sell_navigation_buttons())
        return
    message_text = f"Please reply with the exact amount of {token_symbol} you want to sell:"
    cancel_callback = f"sell_token_selected_{token_mint}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=cancel_callback)]])
    await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    context.user_data['awaiting_exact_token_input_for_sell'] = True
    context.user_data.pop('awaiting_exact_sol_input_for_sell', None)


async def prompt_exact_sol_amount(update, context):
    query = update.callback_query
    await query.answer()
    token_symbol = context.user_data.get('sell_selected_token_symbol', 'token')
    token_mint = context.user_data.get('sell_selected_token_mint')
    if not token_mint:
        await query.edit_message_text("Error: Selected token details lost.", reply_markup=get_sell_navigation_buttons())
        return
    message_text = f"Please reply with the amount of SOL you wish to receive for your {token_symbol}:"
    cancel_callback = f"sell_token_selected_{token_mint}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=cancel_callback)]])
    await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    context.user_data['awaiting_exact_sol_input_for_sell'] = True
    context.user_data.pop('awaiting_exact_token_input_for_sell', None)


async def handle_sell_text_input(update, context):
    if not update.message or not update.message.text: return False
    user_input_text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    token_mint_for_cancel = context.user_data.get('sell_selected_token_mint')
    cancel_cb = f"sell_token_selected_{token_mint_for_cancel}" if token_mint_for_cancel else "sell_tokens_entry"
    cancel_button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=cancel_cb)]])

    if context.user_data.get('awaiting_exact_token_input_for_sell'):
        balance = context.user_data.get('sell_selected_token_balance')
        token_symbol = context.user_data.get('sell_selected_token_symbol', 'tokens')
        try:
            amount = float(user_input_text)
            if amount <= 0:
                await context.bot.send_message(chat_id, f"Amount must be positive. Your balance: {balance:.6f} {token_symbol}. Try again or Cancel.", reply_markup=cancel_button_markup)
                return True 
            if balance is not None:
                if amount > balance and not math.isclose(amount, balance):
                    await context.bot.send_message(chat_id, f"Amount exceeds balance of {balance:.6f} {token_symbol}. Try again or Cancel.", reply_markup=cancel_button_markup)
                    return True
                elif amount > balance and math.isclose(amount, balance):
                    amount = balance 
            context.user_data['sell_final_token_amount'] = amount
            context.user_data['sell_type'] = 'tokens'
            context.user_data.pop('awaiting_exact_token_input_for_sell', None)
            logger.info(f"User {user_id} entered exact token amount: {amount}")
            await confirm_and_execute_sell(update, context, from_query=False)
            return True
        except ValueError:
            await context.bot.send_message(chat_id, f"Invalid number format. Your balance: {balance:.6f} {token_symbol}. Try again or Cancel.", reply_markup=cancel_button_markup)
            return True

    elif context.user_data.get('awaiting_exact_sol_input_for_sell'):
        try:
            sol_amount = float(user_input_text)
            if sol_amount <= 0:
                await context.bot.send_message(chat_id, "SOL amount must be positive. Try again or Cancel.", reply_markup=cancel_button_markup)
                return True
            context.user_data['sell_final_sol_target_amount'] = sol_amount
            context.user_data['sell_type'] = 'sol_target'
            context.user_data.pop('awaiting_exact_sol_input_for_sell', None)
            logger.info(f"User {user_id} entered SOL target amount: {sol_amount}")
            await confirm_and_execute_sell(update, context, from_query=False)
            return True
        except ValueError:
            await context.bot.send_message(chat_id, "Invalid number format for SOL amount. Try again or Cancel.", reply_markup=cancel_button_markup)
            return True
    return False


async def confirm_and_execute_sell(update, context, from_query: bool):
    # This function now only presents the confirmation before Jupiter calls
    wallet_pubkey = context.user_data.get('sell_selected_wallet_pubkey')
    token_symbol = context.user_data.get('sell_selected_token_symbol')
    token_mint_str = context.user_data.get('sell_selected_token_mint')
    final_amount_ui = context.user_data.get('sell_final_token_amount')
    sol_target_ui = context.user_data.get('sell_final_sol_target_amount')
    sell_type = context.user_data.get('sell_type')

    if not all([wallet_pubkey, token_symbol, token_mint_str, sell_type]):
        # ... (error handling as before, using get_sell_navigation_buttons)
        logger.error("confirm_and_execute_sell: Missing critical data.")
        text_to_send = "Error: Critical sell info missing. Please restart."
        if from_query and update.callback_query: await update.callback_query.edit_message_text(text_to_send, reply_markup=get_sell_navigation_buttons())
        elif update.effective_chat: await context.bot.send_message(chat_id=update.effective_chat.id, text=text_to_send, reply_markup=get_sell_navigation_buttons())
        clear_sell_session_data(context)
        return

    text = f"Please confirm your sell order:\n\n"
    text += f"Wallet: `{wallet_pubkey}`\n"
    text += f"Token: {token_symbol} (`{token_mint_str[:4]}...{token_mint_str[-4:]}`)\n"
    if sell_type == 'tokens':
        text += f"Amount to Sell: {final_amount_ui:.6f} {token_symbol}\n"
    elif sell_type == 'sol_target':
        text += f"Amount of SOL to Receive (approx.): {sol_target_ui:.4f} SOL\n"
    
    keyboard = [[
        InlineKeyboardButton("Confirm ✅", callback_data="sell_execute_final_confirm"),
        InlineKeyboardButton("Cancel ❌", callback_data="sell_execute_final_cancel")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if from_query and update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.effective_chat: 
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_sell_execute_final_confirm(update, context):
    query = update.callback_query
    await query.answer("Processing your order...") # More generic initial answer

    user_id = str(query.from_user.id)
    user_pubkey_str = context.user_data.get('sell_selected_wallet_pubkey')
    input_token_mint_str = context.user_data.get('sell_selected_token_mint')
    input_token_symbol = context.user_data.get('sell_selected_token_symbol', 'Token')
    input_token_decimals = context.user_data.get('sell_selected_token_decimals')
    sell_type = context.user_data.get('sell_type')
    wallet_index = context.user_data.get('sell_selected_wallet_index')
    final_ui_amount_tokens = context.user_data.get('sell_final_token_amount')
    final_ui_amount_sol_target = context.user_data.get('sell_final_sol_target_amount')
    slippage_percentage = context.chat_data.get('slippage_percentage', 0.5)
    slippage_bps = int(slippage_percentage * 100)

    # RPC endpoint - use the one from bot_data
    rpc_url_to_use = context.bot_data.get('solana_rpc_url', "https://api.mainnet-beta.solana.com")
    logger.info(f"Using RPC URL for swap: {rpc_url_to_use}")
    async_client = AsyncClient(rpc_url_to_use)

    try:
        critical_data_check = {
            "User Public Key": user_pubkey_str, "Input Token Mint": input_token_mint_str,
            "Input Token Decimals": input_token_decimals, "Sell Type": sell_type,
            "Wallet Index": wallet_index
        }
        missing_data = [name for name, val in critical_data_check.items() if val is None]
        if missing_data:
            err_msg = f"Error: Missing critical data ({', '.join(missing_data)}). Please restart."
            logger.error(f"handle_sell_execute_final_confirm: {err_msg}")
            await query.edit_message_text(err_msg, reply_markup=get_sell_navigation_buttons())
            return # clear_sell_session_data is called in finally

        jupiter_input_mint: str
        jupiter_output_mint: str
        jupiter_amount_atomic: int
        jupiter_swap_mode: str

        if sell_type == 'tokens':
            if final_ui_amount_tokens is None: raise ValueError("Sell amount for tokens is missing.")
            jupiter_input_mint = input_token_mint_str
            jupiter_output_mint = SOL_MINT_ADDRESS
            jupiter_amount_atomic = int(final_ui_amount_tokens * (10**input_token_decimals))
            jupiter_swap_mode = "ExactIn"
        elif sell_type == 'sol_target':
            if final_ui_amount_sol_target is None: raise ValueError("SOL target amount is missing.")
            jupiter_input_mint = input_token_mint_str
            jupiter_output_mint = SOL_MINT_ADDRESS
            sol_decimals = 9
            jupiter_amount_atomic = int(final_ui_amount_sol_target * (10**sol_decimals))
            jupiter_swap_mode = "ExactOut"
        else:
            raise ValueError("Unknown sell type.")

        await query.edit_message_text(text=f"🔄 Getting best quote for your {input_token_symbol} swap...", reply_markup=None)
        quote_response = await get_jupiter_quote(
            input_mint=jupiter_input_mint, output_mint=jupiter_output_mint,
            amount=jupiter_amount_atomic, slippage_bps=slippage_bps, swap_mode=jupiter_swap_mode
        )
        if not quote_response:
            raise Exception("Failed to get swap quote from Jupiter.")

        await query.edit_message_text(text=f"🔄 Building transaction for {input_token_symbol}...", reply_markup=None)
        swap_api_response = await get_jupiter_swap_transaction(
            quote_response=quote_response, user_public_key=user_pubkey_str
        )
        if not swap_api_response:
            raise Exception("Failed to build swap transaction with Jupiter.")

        swap_transaction_b64 = swap_api_response.get('swapTransaction')
        last_valid_block_height = swap_api_response.get('lastValidBlockHeight')
        if not swap_transaction_b64:
            raise Exception("Invalid swap response from Jupiter: Transaction data missing.")

        user_wallets = load_wallets(user_id)
        if not user_wallets or wallet_index >= len(user_wallets):
            raise Exception("Selected wallet not found or invalid index.")
        
        signer_keypair: SoldersKeypair = user_wallets[wallet_index] # Already SoldersKeypair from helper_func

        tx_bytes = base64.b64decode(swap_transaction_b64)
        versioned_tx = VersionedTransaction.from_bytes(tx_bytes)
        
        # Get the message from the transaction
        message = versioned_tx.message 
        
        # Sign the message bytes using the signer's keypair
        # signer_keypair is already loaded as a SoldersKeypair
        # sign_message returns a solders.signature.Signature object
        signature_from_user = signer_keypair.sign_message(bytes(message)) 
        
        # Create the signed transaction using populate.
        signed_tx = VersionedTransaction.populate(message, [signature_from_user])
        
        await query.edit_message_text(text=f"🚀 Sending transaction for {input_token_symbol} swap...", reply_markup=None)
        serialized_signed_tx = bytes(signed_tx) # Corrected serialization
        opts = TxOpts(skip_preflight=True, preflight_commitment=Commitment("confirmed"))
        
        signature_response = await async_client.send_raw_transaction(serialized_signed_tx, opts=opts)
        # Assuming SendTransactionResp is an RpcResponse, the actual signature is in .value
        # The type of .value should be solders.signature.Signature
        actual_tx_signature = signature_response.value 
        
        logger.info(f"Transaction sent with signature: {actual_tx_signature}") # Log the actual signature
        await query.edit_message_text(text=f"🔗 Transaction sent! Waiting for confirmation for {input_token_symbol} swap...\nSignature: `{str(actual_tx_signature)}`", reply_markup=None, parse_mode="Markdown") # Display the string of the actual signature

        # Use custom_confirm_transaction
        desired_commitment_level = Commitment("confirmed")
        max_polling_duration = 90 # seconds
        
        confirmation_result = await custom_confirm_transaction(
            async_client=async_client,
            signature=actual_tx_signature,
            desired_commitment=desired_commitment_level,
            last_valid_block_height=last_valid_block_height,
            logger_instance=logger, # Pass the module-level logger
            polling_interval_secs=3,
            max_polling_duration_secs=max_polling_duration
        )

        final_message_text = ""
        # success = False # Not strictly needed if we directly edit message

        if confirmation_result["status"] == "success":
            # success = True
            final_message_text = (
                f"✅ Swap successful for {input_token_symbol}!\n"
                f"Signature: `{str(actual_tx_signature)}`\n"
                f"[View on Solscan](https://solscan.io/tx/{str(actual_tx_signature)})"
            )
        elif confirmation_result["status"] == "failed_on_chain":
            on_chain_error = confirmation_result.get("error", "Unknown on-chain error")
            error_detail = str(on_chain_error)
            max_len = 250
            if len(error_detail) > max_len:
                error_detail = error_detail[:max_len] + "..."
            final_message_text = (
                f"❌ Transaction failed on-chain for {input_token_symbol}.\n"
                f"Error: {error_detail}\n"
                f"Signature: `{str(actual_tx_signature)}`"
            )
        elif confirmation_result["status"] == "expired":
            final_message_text = (
                f"⌛ Transaction expired for {input_token_symbol}.\n"
                f"Not confirmed before LVBH {last_valid_block_height}.\n"
                f"Signature: `{str(actual_tx_signature)}`"
            )
        elif confirmation_result["status"] == "timeout":
            final_message_text = (
                f"⌛ Confirmation timed out for {input_token_symbol} after {max_polling_duration}s.\n"
                f"Please check status manually on Solscan.\n"
                f"Signature: `{str(actual_tx_signature)}`"
            )
        elif confirmation_result["status"] == "rpc_error":
            rpc_error_detail = confirmation_result.get("error", "Unknown RPC error")
            max_len_rpc = 250
            if len(rpc_error_detail) > max_len_rpc:
                rpc_error_detail = rpc_error_detail[:max_len_rpc] + "..."
            final_message_text = (
                f"❌ RPC error during confirmation for {input_token_symbol}.\n"
                f"Error: {rpc_error_detail}\n"
                f"Please check status manually on Solscan.\n"
                f"Signature: `{str(actual_tx_signature)}`"
            )
        else: # Should not happen
            unknown_error_detail = str(confirmation_result.get("error", "Unknown state"))
            max_len_unknown = 250
            if len(unknown_error_detail) > max_len_unknown:
                unknown_error_detail = unknown_error_detail[:max_len_unknown] + "..."
            final_message_text = (
                f"❓ Unknown confirmation status for {input_token_symbol}: {unknown_error_detail}\n"
                f"Please check status manually on Solscan.\n"
                f"Signature: `{str(actual_tx_signature)}`"
            )
        
        try:
            await query.edit_message_text(
                text=final_message_text, 
                parse_mode="Markdown", 
                reply_markup=get_sell_navigation_buttons(),
                disable_web_page_preview=True
            )
        except Exception as edit_err:
            logger.error(f"Error editing message for final confirmation status: {edit_err}")
            if update.effective_chat: # Check if effective_chat exists
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, # Use effective_chat.id
                    text=final_message_text,
                    parse_mode="Markdown",
                    reply_markup=get_sell_navigation_buttons(),
                    disable_web_page_preview=True
                )
            else: # Fallback if no effective_chat on update (very unlikely for query)
                 logger.error("No effective_chat to send final confirmation message to.")


    except Exception as e:
        logger.error(f"handle_sell_execute_final_confirm error: {e}", exc_info=True) # Keep full log

        error_detail_to_show = ""
        if hasattr(e, '__cause__') and e.__cause__ is not None:
            # Prioritize the cause if it exists, as it's often more specific
            error_detail_to_show = str(e.__cause__)
        
        if not error_detail_to_show: # If no cause, or cause stringified to empty
            error_detail_to_show = str(e) # Fall back to the main exception string

        if not error_detail_to_show: # If both are empty for some reason
            error_detail_to_show = "An unspecified error occurred. Please check bot logs."

        # Truncate for Telegram message
        max_len = 300 
        if len(error_detail_to_show) > max_len:
            error_detail_to_show = error_detail_to_show[:max_len] + "..."
        
        user_facing_error_text = f"❌ Swap failed.\nError: {error_detail_to_show}"
        
        # Ensure query object is valid before trying to edit
        if query and query.message:
             await query.edit_message_text(text=user_facing_error_text, reply_markup=get_sell_navigation_buttons())
        elif update.effective_chat: # Fallback if query edit fails
            await context.bot.send_message(chat_id=update.effective_chat.id, text=user_facing_error_text, reply_markup=get_sell_navigation_buttons())
    finally:
        await async_client.close()
        clear_sell_session_data(context)


async def handle_sell_execute_final_cancel(update, context):
    query = update.callback_query
    await query.answer()
    text = "❌ Sell order cancelled."
    logger.info(f"User {query.from_user.id} cancelled final sell order.")
    await query.edit_message_text(text=text, reply_markup=get_sell_navigation_buttons())
    clear_sell_session_data(context)


async def sell_button_callback(update, context):
    query = update.callback_query
    data = query.data
    if data == "sell_tokens_entry":
        await sell_tokens_entry_point_handler(update, context)
    elif data.startswith("sell_wallet_selected_"):
        await handle_wallet_selection_for_sell(update, context)
    elif data.startswith("sell_token_selected_"):
        await handle_token_selection_for_sell(update, context)
    elif data.startswith("sell_amount_percent_"):
        await handle_sell_amount_percent(update, context)
    elif data == "sell_enter_token_amount":
        await prompt_exact_token_amount(update, context)
    elif data == "sell_enter_sol_amount":
        await prompt_exact_sol_amount(update, context)
    elif data == "sell_execute_final_confirm":
        await handle_sell_execute_final_confirm(update, context)
    elif data == "sell_execute_final_cancel":
        await handle_sell_execute_final_cancel(update, context)
    else:
        logger.warning(f"Unhandled sell callback query with data: {data}")
        try: 
            await query.answer("Action not recognized.")
        except Exception as e:
            logger.debug(f"Query answer failed in sell_button_callback fallback: {e}")
