import aiohttp
import logging


logger = logging.getLogger(__name__)


async def get_token_symbol_from_api(mint_address):
    try:
        # 1: Jupiter API
        async with aiohttp.ClientSession() as session:
            url = f"https://token.jup.ag/strict"
            async with session.get(url) as response:
                if response.status == 200:
                    tokens = await response.json()
                    for token in tokens:
                        if token.get('address') == mint_address:
                            return token.get('symbol')
        
        # 2: Solana Token List
        async with aiohttp.ClientSession() as session:
            url = "https://raw.githubusercontent.com/solana-labs/token-list/main/src/tokens/solana.tokenlist.json"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for token in data.get('tokens', []):
                        if token.get('address') == mint_address:
                            return token.get('symbol')
        
        return None
        
    except Exception as e:
        logger.debug(f"Error getting token symbol from API: {e}")
        return None