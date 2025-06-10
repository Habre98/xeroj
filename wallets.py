# from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update  # type: ignore

# from telegram.ext import (  # type: ignore
#     CallbackContext,
#     ContextTypes,
# )  # type: ignore
# from helper_func import (
#     load_wallets,
#     create_solana_wallet,
#     save_wallet,
#     get_next_wallet_index,
# )

# from solders.pubkey import Pubkey  # type: ignore
# from solana.rpc.async_api import AsyncClient  # type: ignore

# from linkx import linkx_command
# import os
# import logging

# logger = logging.getLogger(__name__)


# async def start(update, context):
#     #  Initialize slippage in chat_data if not already set
#     if 'slippage' not in context.chat_data:
#         context.chat_data['slippage'] = 50

#     keyboard = [
#         [InlineKeyboardButton("Manage Wallets", callback_data="manage_wallets")],
#         # [InlineKeyboardButton("Add target", callback_data="add_target_command")],
#         [InlineKeyboardButton("Link your X account", callback_data="linkx_command")],
#         [InlineKeyboardButton("Global Slippage", callback_data="set_slippage_")],
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     await context.bot.send_message(
#         chat_id=update.effective_chat.id,
#         text="Welcome to the Xero X Sniper Bot! Please choose an option:",
#         reply_markup=reply_markup,
#     )


# async def manage_wallets_command(update, context):
#     query = update.callback_query
#     keyboard = [
#         [InlineKeyboardButton("Add New Wallet", callback_data="request_add_wallet")],
#         [InlineKeyboardButton("View My Wallets", callback_data="request_my_wallets")],
#         [InlineKeyboardButton("⬅ Back", callback_data="back_to_main_menu")],
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     if query:
#         await query.edit_message_text(
#             text="Manage your wallets:", reply_markup=reply_markup
#         )
#     else:
#         # This case should ideally not be reached if triggered by a button from /start
#         await update.message.reply_text(
#             text="Manage your wallets:", reply_markup=reply_markup
#         )


# async def add_wallet_command(update, context):
#     keyboard = [
#         [
#             InlineKeyboardButton(
#                 "Generate New Wallet", callback_data="generate_new_wallet"
#             )
#         ],
#         # [InlineKeyboardButton("Import Existing Wallet", callback_data="import_existing_wallet")], # Optional for now
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     message_text = "To add a new Solana wallet, you can either generate a new one or import an existing one (not yet supported). Would you like to generate a new wallet?"

#     query = update.callback_query
#     if query:
#         await query.edit_message_text(text=message_text, reply_markup=reply_markup)
#     else:
#         await update.message.reply_text(text=message_text, reply_markup=reply_markup)


# async def my_wallets_command(update, context):
#     user_id = (
#         update.callback_query.from_user.id
#         if update.callback_query
#         else update.message.from_user.id
#     )

#     loaded_wallets = load_wallets(user_id)

#     if not loaded_wallets:
#         message_text = (
#             "You have no wallets. Use /addwallet or 'Add New Wallet' to create one."
#         )
#     else:
#         wallet_list_str = "Your Wallets:\n"
#         for i, wallet_kp in enumerate(loaded_wallets):
#             pubkey = wallet_kp.pubkey()
#             balance = await get_wallet_balance(str(pubkey))
#             wallet_list_str += f"\n🏦 Wallet {i}.\n  PubKey:\n`{str(pubkey)}`\nbalance: `{balance}`\n"  # Using backticks for mono-spaced font
#         wallet_list_str += "\nTo select wallets for scanning, use the /selectwallets command (e.g., /selectwallets 0 1 2). You can select up to 5 wallets. (Full selection UI to be implemented later)."
#         message_text = wallet_list_str

#     if update.callback_query:
#         await update.callback_query.edit_message_text(
#             text=message_text, parse_mode="Markdown"
#         )
#     else:
#         await update.message.reply_text(text=message_text, parse_mode="Markdown")


# async def select_wallets_command(update, context: CallbackContext):
#     if context.user_data is None:
#         context.user_data = {}
#     user_id = update.message.from_user.id
#     args = context.args

#     if not args:
#         await context.bot.send_message(
#             chat_id=user_id,
#             text="Usage: /selectwallets <index1> <index2> ... (e.g., /selectwallets 0 1). You can select up to 5 wallets.",
#         )
#         return

#     if len(args) > 5:
#         await context.bot.send_message(
#             chat_id=user_id,
#             text="You can select up to 5 wallets. Please provide a list of up to 5 indices.",
#         )
#         return

#     user_wallets = load_wallets(user_id)
#     if not user_wallets:
#         await update.message.reply_text(
#             "You have no wallets to select. Use /addwallet first."
#         )
#         return

#     selected_indices = []
#     selected_pubkeys_for_message = []

#     try:
#         for arg in args:
#             idx = int(arg)
#             if 0 <= idx < len(user_wallets):
#                 if idx not in selected_indices:
#                     selected_indices.append(idx)
#                 else:
#                     await context.bot.send_message(
#                         chat_id=user_id,
#                         text=f"Wallet index {idx} was already included. Ignoring duplicate.",
#                     )
#             else:
#                 await context.bot.send_message(
#                     chat_id=user_id,
#                     text=f"Invalid wallet index: {idx}. Please use indices from your /mywallets list.",
#                 )
#                 return
#     except ValueError:
#         await context.bot.send_message(
#             chat_id=user_id,
#             text="Invalid input. Please provide wallet indices as numbers (e.g., /selectwallets 0 1).",
#         )
#         return

#     if not selected_indices:
#         await context.bot.send_message(
#             chat_id=user_id,
#             text="No valid wallets selected. Please check indices from /mywallets.",
#         )
#         return

#     # Store the Keypair objects or just their pubkeys. Storing pubkeys is simpler for now.
#     context.user_data["selected_wallets"] = [
#         str(user_wallets[i].pubkey()) for i in selected_indices
#     ]

#     for i in selected_indices:
#         pubkey = user_wallets[i].pubkey()
#         # balance = await get_wallet_balance(str(pubkey))
#         selected_pubkeys_for_message.append(f"🏦 Wallet #{i})\n`{str(pubkey)}`\n")

#     await context.bot.send_message(
#         chat_id=user_id,
#         text="✅  Selected wallets for scanning:\n"
#         + "\n".join(selected_pubkeys_for_message)
#         + "\nUse /startscanner to begin.",
#         parse_mode="Markdown",
#     )


# async def prompt_generate_new_wallet(update, context: CallbackContext):
#     query = update.callback_query
#     user_id = query.from_user.id

#     try:
#         wallet_index = get_next_wallet_index(user_id)
#         wallet_data = await create_solana_wallet()
#         if wallet_data is None:
#             raise Exception("Failed to generate wallet data.")
#         private_key = wallet_data["private_key"]
#         public_key = wallet_data["address"]
#         logger.info(
#             f"Secret Key: `{private_key}`\nPublic Key: `{public_key}`\nWallet Index: `{wallet_index}`"
#         )

#         if save_wallet(user_id, private_key, wallet_index):
#             message_text = f"✅ Successfully generated new wallet #{wallet_index} \nPublic Key: `{public_key}`.\nPrivate Key: `{private_key}`.\n⚠️Store your keys safely and do not share with anyone"
#         else:
#             message_text = "Failed to save the new wallet. Please try again."

#     except Exception as e:
#         print(f"Error in prompt_generate_new_wallet: {e}")
#         message_text = (
#             "An error occurred while generating the wallet. Please try again."
#         )

#     await query.edit_message_text(text=message_text, parse_mode="Markdown")


# async def get_wallet_balance(wallet_address):
#     try:
#         # Validate wallet_address
#         if (
#             wallet_address is None
#             or not isinstance(wallet_address, str)
#             or wallet_address.strip() == ""
#         ):
#             logger.error("Invalid or None wallet address provided.")
#             return 0

#         # Log wallet address for debugging
#         logger.debug(f"Received wallet address: {wallet_address}")

#         # Convert Base58 wallet address to Pubkey object
#         pubkey = Pubkey.from_string(wallet_address)

#         # TODO: TOGGLE DEV/MAINNET
#         # Initialize Solana Async Client
#         async_client = AsyncClient("https://api.mainnet-beta.solana.com")
#         # async_client = AsyncClient("https://api.devnet.solana.com")

#         # Fetch balance
#         response = await async_client.get_balance(pubkey)
#         await async_client.close()  # Close connection to avoid resource leaks

#         # Extract balance value
#         if response.value is not None:
#             print(f"Wallet balance: {response.value} lamports")
#             return response.value / 1_000_000_000  # Convert lamports to SOL
#         else:
#             logger.error("Failed to fetch wallet balance: Balance value is None.")
#             return 0
#     except Exception as e:
#         logger.error(f"Exception in check_wallet_balance: {e}")
#         return 0






# # SLIPPAGE HANDLERS
# async def set_slippage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handles the /set_slippage command."""
#     print("🔥🔥🧫🔥🧫🔥🔥SET SLIPPAGE COMMAND")
#     query = update.callback_query
    
#     if context.user_data is None:
#         context.user_data = {}
#     context.user_data['awaiting_slippage'] = True
#     print(f"DEBUG - CallbackQuery received: {query.data}")
#     if query == "set_slippage_":
#         await update.message.reply_text(
#             "Please enter your desired slippage value (e.g., 50 for 50% or 0.5 for 0.5%)."
#         )


# async def set_slippage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handles the 'Set Slippage' button callback."""
#     print("🔥🔥🧫🔥🧫🔥🔥SET SLIPPAGE CALLBACK")

#     query = update.callback_query
#     await query.answer()
#     if context.user_data is None:
#         context.user_data = {}
#     context.user_data['awaiting_slippage'] = True
#     await query.edit_message_text(
#         text="Please enter your desired Global Slippage value (e.g., 50 for 50% or 0.5 for 0.5%)."
#     )


# async def handle_slippage_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handles the user's slippage input."""
#     if not context.user_data.get('awaiting_slippage'):
#         return

#     try:
#         slippage_input = float(update.message.text)
#         if not (0 <= slippage_input <= 100):
#             raise ValueError("Slippage must be between 0 and 100.")

#         context.chat_data['slippage'] = slippage_input
#         context.user_data['awaiting_slippage'] = False
#         await update.message.reply_text(
#             f"✅ Slippage updated to {slippage_input}%.\n"
#             "Note: This percentage is typically interpreted as basis points (BPS) by trading platforms (e.g., 50% = 5000 BPS)."
#         )
#     except ValueError:
#         await update.message.reply_text(
#             "Invalid input. Please enter a number between 0 and 100 for slippage (e.g., 50 or 0.5).\n"
#             "Try again:"
#         )
#     except Exception as e:
#         print(f"Error in handle_slippage_input: {e}")
#         await update.message.reply_text(
#             "An error occurred. Please try again."
#         )
#         context.user_data['awaiting_slippage'] = False  # Reset on unexpected error


# async def button_callback(update, context):
#     query = update.callback_query
#     await query.answer()

#     if query.data == "manage_wallets":
#         await manage_wallets_command(update, context)
#     elif query.data == "request_add_wallet":
#         await add_wallet_command(update, context)
#     elif query.data == "request_my_wallets":
#         await my_wallets_command(update, context)
#     elif query.data == "generate_new_wallet":
#         await prompt_generate_new_wallet(update, context)
#     elif query.data == "linkx_command":
#         await linkx_command(update, context)
#     elif query.data == "set_slippage_":
#         await set_slippage_callback(update, context)

#     elif query.data == "back_to_main_menu":
#         await start(update, context)



from telegram import InlineKeyboardMarkup, InlineKeyboardButton  # type: ignore

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
from solana.rpc.async_api import AsyncClient  # type: ignore
from solders.pubkey import Pubkey
from solana.rpc.types import  TokenAccountOpts
from spl.token._layouts import ACCOUNT_LAYOUT
from spl.token.constants import TOKEN_PROGRAM_ID
from solana.rpc.core import RPCException
from solders.account import Account
import struct
import base64

from linkx import linkx_command
from get_symbol import get_token_symbol_from_api
import os
import logging

logger = logging.getLogger(__name__)


async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("Manage Wallets", callback_data="manage_wallets")],
        # [InlineKeyboardButton("Add target", callback_data="add_target_command")],
        [InlineKeyboardButton("Link your X account", callback_data="linkx_command")],
        [InlineKeyboardButton("Set Slippage", callback_data="set_slippage")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_video(
         chat_id=update.effective_chat.id,
            video=open('media/BundlePro.mp4', 'rb'),  # Cambia esta ruta por la ubicación real
            caption="Welcome to the Xero X Sniper Bot! Please choose an option:",
            reply_markup=reply_markup,
            width=640,
            height=360,
            supports_streaming=True
    )


async def manage_wallets_command(update, context):
    query = update.callback_query
    await query.answer()  # Importante: siempre responder al callback query
    
    keyboard = [
        [InlineKeyboardButton("Add New Wallet", callback_data="request_add_wallet")],
        [InlineKeyboardButton("View My Wallets", callback_data="request_my_wallets")],
        [InlineKeyboardButton("⬅ Back", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Siempre enviar un nuevo mensaje
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Manage your wallets:", 
        reply_markup=reply_markup
    )


async def add_wallet_command(update, context):
    keyboard = [
        [
            InlineKeyboardButton(
                "Generate New Wallet", callback_data="generate_new_wallet"
            )
        ],
        # [InlineKeyboardButton("Import Existing Wallet", callback_data="import_existing_wallet")], # Optional for now
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "To add a new Solana wallet, you can either generate a new one or import an existing one (not yet supported). Would you like to generate a new wallet?"

    query = update.callback_query
    if query:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=message_text, reply_markup=reply_markup)


async def my_wallets_command(update, context):
    user_id = (
        update.callback_query.from_user.id
        if update.callback_query
        else update.message.from_user.id
    )
    
    loaded_wallets = load_wallets(user_id)
    
    if not loaded_wallets:
        message_text = "You have no wallets. Use /addwallet or 'Add New Wallet' to create one."
    else:
        wallet_list_str = "Your Wallets:\n"
        for i, wallet_kp in enumerate(loaded_wallets):
            pubkey = wallet_kp.pubkey()
            balance_info = await get_wallet_balance(str(pubkey))
            
            sol_balance = balance_info["sol_balance"]
            tokens = balance_info["tokens"]
            
            wallet_list_str += f"\n🏦 Wallet {i}.\n  PubKey:\n`{str(pubkey)}`\nSOL balance: `{sol_balance}`"
            
            if tokens:
                wallet_list_str += "\nTokens:"
                for token in tokens:
                    # Usar símbolo si está disponible, sino mostrar mint truncada
                    if token.get('symbol'):
                        token_display = token['symbol']
                    else:
                        token_display = f"{token['mint'][:4]}...{token['mint'][-4:]}"
                    
                    wallet_list_str += f"\n - {token_display}: `{token['amount']}`"
            else:
                wallet_list_str += "\nNo SPL tokens found."
        
        message_text = wallet_list_str
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=message_text, parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(text=message_text, parse_mode="Markdown")

async def select_wallets_command(update, context: CallbackContext):
    if context.user_data is None:
        context.user_data = {}
    user_id = update.message.from_user.id
    args = context.args

    if not args:
        await context.bot.send_message(
            chat_id=user_id,
            text="Usage: /selectwallets <index1> <index2> ... (e.g., /selectwallets 0 1). You can select up to 5 wallets.",
        )
        return

    if len(args) > 5:
        await context.bot.send_message(
            chat_id=user_id,
            text="You can select up to 5 wallets. Please provide a list of up to 5 indices.",
        )
        return

    user_wallets = load_wallets(user_id)
    if not user_wallets:
        await update.message.reply_text(
            "You have no wallets to select. Use /addwallet first."
        )
        return

    selected_indices = []
    selected_pubkeys_for_message = []

    try:
        for arg in args:
            idx = int(arg)
            if 0 <= idx < len(user_wallets):
                if idx not in selected_indices:
                    selected_indices.append(idx)
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"Wallet index {idx} was already included. Ignoring duplicate.",
                    )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Invalid wallet index: {idx}. Please use indices from your /mywallets list.",
                )
                return
    except ValueError:
        await context.bot.send_message(
            chat_id=user_id,
            text="Invalid input. Please provide wallet indices as numbers (e.g., /selectwallets 0 1).",
        )
        return

    if not selected_indices:
        await context.bot.send_message(
            chat_id=user_id,
            text="No valid wallets selected. Please check indices from /mywallets.",
        )
        return

    # Store the Keypair objects or just their pubkeys. Storing pubkeys is simpler for now.
    context.user_data["selected_wallets"] = [
        str(user_wallets[i].pubkey()) for i in selected_indices
    ]

    for i in selected_indices:
        pubkey = user_wallets[i].pubkey()
        # balance = await get_wallet_balance(str(pubkey))
        selected_pubkeys_for_message.append(f"🏦 Wallet #{i})\n`{str(pubkey)}`\n")

    await context.bot.send_message(
        chat_id=user_id,
        text="✅  Selected wallets for scanning:\n"
        + "\n".join(selected_pubkeys_for_message)
        + "\nUse /startscanner to begin.",
        parse_mode="Markdown",
    )


async def prompt_generate_new_wallet(update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    try:
        wallet_index = get_next_wallet_index(user_id)
        wallet_data = await create_solana_wallet()
        if wallet_data is None:
            raise Exception("Failed to generate wallet data.")
        private_key = wallet_data["private_key"]
        public_key = wallet_data["address"]
        logger.info(
            f"Secret Key: `{private_key}`\nPublic Key: `{public_key}`\nWallet Index: `{wallet_index}`"
        )

        if save_wallet(user_id, private_key, wallet_index):
            message_text = f"✅ Successfully generated new wallet #{wallet_index} \nPublic Key: `{public_key}`.\nPrivate Key: `{private_key}`.\n⚠️Store your keys safely and do not share with anyone"
        else:
            message_text = "Failed to save the new wallet. Please try again."

    except Exception as e:
        print(f"Error in prompt_generate_new_wallet: {e}")
        message_text = (
            "An error occurred while generating the wallet. Please try again."
        )

    await query.edit_message_text(text=message_text, parse_mode="Markdown")


async def get_wallet_balance(wallet_address):
    try:
        if not wallet_address or not isinstance(wallet_address, str):
            logger.error("Invalid or None wallet address provided.")
            return {"sol_balance": 0, "tokens": []}
        
        pubkey = Pubkey.from_string(wallet_address)
        async_client = AsyncClient("https://api.mainnet-beta.solana.com")
        
        # Get SOL balance
        response = await async_client.get_balance(pubkey)
        sol_balance = response.value / 1_000_000_000
        
        # Get SPL tokens usando get_token_accounts_by_owner
        token_infos = []
        
        try:
            # Obtener todas las cuentas de tokens
            token_accounts = await async_client.get_token_accounts_by_owner(
                pubkey,
                TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
            )
            
            logger.info(f"Found {len(token_accounts.value)} token accounts")
            
            # Para cada cuenta de token, obtenemos la información detallada
            for token_account in token_accounts.value:
                try:
                    # Obtener información detallada con jsonParsed
                    account_info = await async_client.get_account_info(
                        token_account.pubkey
                    )
                    
                    if account_info.value and account_info.value.data:
                        # Intentar decodificar los datos del token manualmente
                        data = account_info.value.data
                        
                        # Los datos del token account están en formato binario
                        # Estructura: mint(32) + owner(32) + amount(8) + ...
                        if len(data) >= 72:  # Tamaño mínimo de token account
                            # Extraer mint (primeros 32 bytes)
                            mint_bytes = data[:32]
                            mint = str(Pubkey(mint_bytes))
                            
                            # Extraer amount (bytes 64-72)
                            amount_bytes = data[64:72]
                            amount = struct.unpack('<Q', amount_bytes)[0]  # little-endian uint64
                            
                            if amount > 0:
                                # Para obtener decimales y símbolo, necesitamos consultar la mint
                                decimals = 6  # Default
                                symbol = None
                                
                                try:
                                    mint_info = await async_client.get_account_info(Pubkey.from_string(mint))
                                    if mint_info.value and mint_info.value.data:
                                        # Los decimales están en el byte 44 de la mint info
                                        decimals = mint_info.value.data[44] if len(mint_info.value.data) > 44 else 6
                                except:
                                    decimals = 6  # Default
                                
                                # Intentar obtener metadatos del token para el símbolo
                                try:
                                    # Derivar la PDA de metadatos
                                    metadata_program_id = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
                                    mint_pubkey = Pubkey.from_string(mint)
                                    
                                    # Encontrar la dirección de metadatos
                                    metadata_seeds = [
                                        b"metadata",
                                        bytes(metadata_program_id),
                                        bytes(mint_pubkey)
                                    ]
                                    
                                    # Calcular PDA manualmente (aproximación)
                                    import hashlib
                                    seed_str = b"metadata" + bytes(metadata_program_id) + bytes(mint_pubkey)
                                    
                                    # Intentar obtener metadatos usando una API externa
                                    # Como alternativa, podemos usar un servicio como Jupiter o CoinGecko
                                    symbol = await get_token_symbol_from_api(mint)
                                    
                                except Exception as meta_error:
                                    logger.debug(f"Could not get metadata for {mint}: {meta_error}")
                                    symbol = None
                                
                                ui_amount = amount / (10 ** decimals)
                                token_infos.append({
                                    "mint": mint,
                                    "amount": ui_amount,
                                    "symbol": symbol
                                })
                                
                                logger.info(f"Token: {mint[:8]}... Amount: {ui_amount} Symbol: {symbol}")
                                
                except Exception as e:
                    logger.error(f"Error processing individual token account: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error getting token accounts: {e}")
        
        await async_client.close()
        return {"sol_balance": sol_balance, "tokens": token_infos}
    
    except Exception as e:
        logger.error(f"Exception in get_wallet_balance: {e}")
        return {"sol_balance": 0, "tokens": []}

async def button_callback(update, context):
    query = update.callback_query
    await query.answer()

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



async def prompt_slippage_selection(update, context):
    query = update.callback_query
    await query.answer()  
    
    try:
        await query.edit_message_text(
            text="Please enter your desired slippage percentage (e.g., 1 for 1%, 0.5 for 0.5%). Valid range: 0.1% to 50%.",
        )
    except Exception as e:
        print(f"Error editing message: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,  
            text="Please enter your desired slippage percentage (e.g., 1 for 1%, 0.5 for 0.5%). Valid range: 0.1% to 50%.",
        )
    
    if context.user_data is None:
        context.user_data = {}
    context.user_data['awaiting_slippage_input'] = True


async def handle_slippage_input(update, context):
    if context.user_data and context.user_data.get('awaiting_slippage_input'):
        try:
            slippage_text = update.message.text
            slippage_value = float(slippage_text)
            if 0.1 <= slippage_value <= 50:
                context.user_data['slippage_percentage'] = slippage_value
                context.user_data['awaiting_slippage_input'] = False
                await update.message.reply_text(
                    f"✅ Slippage set to {slippage_value}%.",
                    # Optionally, show main menu again or a relevant next step
                    # reply_markup= # keyboard_for_main_menu_or_next_step
                )
                # Consider calling start(update, context) or another menu function
            else:
                await update.message.reply_text(
                    "Invalid input. Slippage must be between 0.1 and 50. Please try again or go back."
                )
        except ValueError:
            await update.message.reply_text(
                "Invalid format. Please enter a number for slippage (e.g., 1 or 0.5). Please try again or go back."
            )
        # If input is invalid, awaiting_slippage_input remains True, allowing user to retry
    # else:
        # This message is not a slippage input, ignore or pass to other handlers
        # logger.info("Message received, but not awaiting slippage input.")
