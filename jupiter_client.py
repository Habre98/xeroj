import httpx
import logging
from typing import Optional, Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

JUPITER_QUOTE_API_URL = "https://lite-api.jup.ag/swap/v1/quote"
JUPITER_SWAP_API_URL = "https://lite-api.jup.ag/swap/v1/swap"
SOL_MINT_ADDRESS = "So11111111111111111111111111111111111111112" # Wrapped SOL

async def get_jupiter_quote(
    input_mint: str,
    output_mint: str,
    amount: int, # Amount in atomic units
    slippage_bps: int,
    restrict_intermediate_tokens: bool = True,
    only_direct_routes: bool = False,
    swap_mode: Optional[str] = "ExactIn", # Added swap_mode
    # Add other relevant optional params from docs if needed, e.g., platformFeeBps
) -> Optional[Dict[str, Any]]:
    """
    Fetches a swap quote from the Jupiter API.
    """
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
        "slippageBps": slippage_bps,
        "restrictIntermediateTokens": restrict_intermediate_tokens,
        "onlyDirectRoutes": only_direct_routes,
        "swapMode": swap_mode, # Added swap_mode to params
    }
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Requesting Jupiter quote: {JUPITER_QUOTE_API_URL} with params {params}")
            response = await client.get(JUPITER_QUOTE_API_URL, params=params)
            response.raise_for_status()  # Raises an exception for 4XX/5XX responses
            quote_response = response.json()
            logger.info(f"Received Jupiter quote response: {quote_response}")
            return quote_response
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching Jupiter quote: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error fetching Jupiter quote: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching Jupiter quote: {e}", exc_info=True)
        return None

async def get_jupiter_swap_transaction(
    quote_response: Dict[str, Any],
    user_public_key: str,
    dynamic_compute_unit_limit: bool = True,
    #wrap_and_unwrap_sol: bool = True, # Recommended to keep True if dealing with SOL
    # prioritization_fee_lamports: Optional[Dict[str, Any]] = None # Advanced: allow full object
    # For simplicity, let's use a simpler priority fee setting
    priority_fee_level: str = "VeryHigh", # Changed default
    max_priority_fee_cap_lamports: Optional[int] = 200000 # Changed default, e.g. 0.0002 SOL
) -> Optional[Dict[str, Any]]:
    """
    Fetches a swap transaction from the Jupiter API using a prior quote.
    """
    payload = {
        "quoteResponse": quote_response,
        "userPublicKey": user_public_key,
        "wrapAndUnwrapSol": True, # Default and recommended
        "dynamicComputeUnitLimit": dynamic_compute_unit_limit,
        # "asLegacyTransaction": False, # Defaults to False (Versioned Tx)
    }

    # Define mapping for priority levels
    priority_level_map = {
        "Low": "low",
        "Medium": "medium",
        "High": "high",
        "VeryHigh": "veryHigh"
        # "Turbo": "veryHigh", # Example for future mapping
        # "Extreme": "veryHigh" # Example for future mapping
    }
    valid_input_levels = list(priority_level_map.keys())

    if priority_fee_level != "Default":
        if max_priority_fee_cap_lamports is not None and priority_fee_level in valid_input_levels:
            mapped_priority_level = priority_level_map[priority_fee_level]
            payload["prioritizationFeeLamports"] = {
                "priorityLevelWithMaxLamports": {
                    "maxLamports": max_priority_fee_cap_lamports,
                    "priorityLevel": mapped_priority_level, # Use the mapped value
                    "global": False # Add the 'global' parameter
                }
            }
        elif priority_fee_level == "None": # Explicitly no priority fee, even if cap is set (though cap wouldn't be used)
            # Do not add the prioritizationFeeLamports key for "None"
            pass 
        # else: Default behavior (Jupiter decides) if level is "Default" or an unmapped value with no cap.
        # If max_priority_fee_cap_lamports is None, or priority_fee_level is not in valid_input_levels (and not "None" or "Default"),
        # Jupiter's default fee mechanism will apply.

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Requesting Jupiter swap transaction: {JUPITER_SWAP_API_URL} with payload {payload}")
            response = await client.post(JUPITER_SWAP_API_URL, json=payload)
            response.raise_for_status()
            swap_response = response.json()
            logger.info(f"Received Jupiter swap transaction response: {swap_response}")
            return swap_response
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching Jupiter swap transaction: {e.response.status_code} - {e.response.text}")
        # Try to parse error from Jupiter if available
        try:
            error_details = e.response.json()
            logger.error(f"Jupiter API error details: {error_details}")
        except:
            pass # Ignore if error response is not JSON
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error fetching Jupiter swap transaction: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching Jupiter swap transaction: {e}", exc_info=True)
        return None
