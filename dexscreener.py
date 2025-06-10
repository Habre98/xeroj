
import httpx
import json
import asyncio

async def fetch_token_info(contract_address: str):
    """
    Obtiene información de token desde Dexscreener con la estructura esperada por el bot
    """
    try:
        # Paso 1: Buscar el par por contract address
        search_url = f"https://api.dexscreener.com/latest/dex/search?q={contract_address}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            search_response = await client.get(search_url)
            search_data = search_response.json()

        pairs = search_data.get("pairs", [])
        if not pairs:
            print(f"⚠️ No se encontraron pares para {contract_address}")
            return None

        # Paso 2: Filtrar solo pares de Solana y encontrar el mejor
        solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        if not solana_pairs:
            print(f"⚠️ No se encontraron pares de Solana para {contract_address}")
            return None

        # Tomar el par con mayor liquidez
        pair = max(solana_pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0) or 0)
        pair_id = pair.get("pairAddress")
        
        if not pair_id:
            print(f"⚠️ No se encontró pairAddress para {contract_address}")
            return None

        # Paso 3: Obtener datos detallados del par
        pair_url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(pair_url)
            data = response.json()

        pair_data = data.get("pair")
        if not pair_data:
            print(f"⚠️ No se encontraron datos del par para {pair_id}")
            return None

        # Debug para revisar estructura real
        print("🔍 DEBUG pair_data keys:", list(pair_data.keys()))
        
        # Paso 4: Extraer información base del token
        base_token = pair_data.get("baseToken", {})
        quote_token = pair_data.get("quoteToken", {})
        
        # Determinar cuál es nuestro token objetivo
        target_token = base_token
        if base_token.get("address", "").lower() != contract_address.lower():
            if quote_token.get("address", "").lower() == contract_address.lower():
                target_token = quote_token
            else:
                # Usar baseToken por defecto
                target_token = base_token

        # Extraer datos principales
        token_name = target_token.get("name", "Unknown")
        token_symbol = target_token.get("symbol", "")
        
        # Market Cap (probar múltiples campos)
        market_cap = (
            pair_data.get("marketCap") or 
            pair_data.get("marketCapUsd") or 
            pair_data.get("fdv") or 
            pair_data.get("fdvUsd") or 
            0
        )
        
        # Liquidez
        liquidity_data = pair_data.get("liquidity", {})
        liquidity = 0
        if isinstance(liquidity_data, dict):
            liquidity = liquidity_data.get("usd", 0) or liquidity_data.get("base", 0) or 0
        elif isinstance(liquidity_data, (int, float)):
            liquidity = liquidity_data

        # URL de Dexscreener
        dex_url = pair_data.get("url") or f"https://dexscreener.com/solana/{contract_address}"

        # Paso 5: Procesar información adicional y redes sociales
        info = pair_data.get("info", {})
        
        # Websites
        websites = []
        if info.get("websites"):
            for site in info["websites"]:
                if isinstance(site, dict) and site.get("url"):
                    websites.append({"url": site["url"], "label": site.get("label", "website")})
                elif isinstance(site, str):
                    websites.append({"url": site, "label": "website"})

        # Socials - manejar diferentes formatos
        socials = []
        raw_socials = pair_data.get("socials") or info.get("socials") or []
        
        for social in raw_socials:
            if isinstance(social, dict):
                social_type = social.get("type") or social.get("platform", "").lower()
                social_url = social.get("url")
                
                if social_url and social_type:
                    socials.append({
                        "type": social_type,
                        "url": social_url
                    })

        # Si no hay socials en el formato esperado, intentar extraer de otras fuentes
        if not socials:
            # Intentar extraer de campos directos
            if info.get("twitter"):
                socials.append({"type": "twitter", "url": info["twitter"]})
            if info.get("telegram"):
                socials.append({"type": "telegram", "url": info["telegram"]})
            if info.get("discord"):
                socials.append({"type": "discord", "url": info["discord"]})

        # Crear estructura esperada por el bot
        token_info = {
            # Estructura base del token
            "baseToken": {
                "name": token_name,
                "symbol": token_symbol,
                "address": contract_address
            },
            
            # Market cap
            "marketCap": market_cap,
            "fdv": market_cap,  # Fallback
            
            # Liquidez
            "liquidity": {
                "usd": liquidity
            } if isinstance(liquidity, (int, float)) else liquidity,
            
            # URL de Dexscreener
            "url": dex_url,
            
            # Información adicional
            "info": {
                "websites": websites,
                "socials": socials
            }
        }

        print(f"✅ Token info extraída exitosamente para {token_name} ({token_symbol})")
        print(f"📊 Market Cap: ${market_cap:,.2f}, Liquidez: ${liquidity:,.2f}")
        
        return token_info

    except httpx.TimeoutException:
        print(f"⏰ Timeout al obtener información de {contract_address}")
        return None
    except httpx.RequestError as e:
        print(f"❌ Error de red al obtener información: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error parseando JSON: {e}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado obteniendo token info: {e}")
        import traceback
        traceback.print_exc()
        return None

# Función auxiliar para debug
async def debug_token_structure(contract_address: str):
    """
    Función para debuggear la estructura de datos de Dexscreener
    """
    try:
        search_url = f"https://api.dexscreener.com/latest/dex/search?q={contract_address}"
        async with httpx.AsyncClient() as client:
            search_response = await client.get(search_url)
            search_data = search_response.json()

        pairs = search_data.get("pairs", [])
        if pairs:
            pair = pairs[0]
            pair_id = pair.get("pairAddress")
            
            if pair_id:
                pair_url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_id}"
                async with httpx.AsyncClient() as client:
                    response = await client.get(pair_url)
                    data = response.json()
                
                print("🔍 ESTRUCTURA COMPLETA DE DEXSCREENER:")
                print(json.dumps(data, indent=2))
                
    except Exception as e:
        print(f"❌ Error en debug: {e}")

# Función de validación
def validate_contract_address(address: str) -> bool:
    """
    Valida que una dirección de contrato sea válida
    """
    if not address or not isinstance(address, str):
        return False
    
    # Verificar longitud típica de direcciones Solana
    if len(address) < 32 or len(address) > 44:
        return False
    
    # Verificar caracteres válidos (base58)
    import re
    if not re.match(r'^[1-9A-HJ-NP-Za-km-z]+$', address):
        return False
    
    return True

# Función con retry automático
async def fetch_token_info_with_retry(contract_address: str, max_retries: int = 3):
    """
    Versión con reintentos automáticos
    """
    if not validate_contract_address(contract_address):
        print(f"❌ Dirección de contrato inválida: {contract_address}")
        return None
    
    for attempt in range(max_retries):
        try:
            result = await fetch_token_info(contract_address)
            if result:
                return result
            
            if attempt < max_retries - 1:
                print(f"🔄 Reintentando... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(1)  # Esperar 1 segundo antes del siguiente intento
                
        except Exception as e:
            print(f"❌ Intento {attempt + 1} falló: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)  # Esperar más tiempo en caso de error
    
    print(f"❌ Falló después de {max_retries} intentos")
    return None

# Para usar en tu bot, importa así:
# from fetch_token_info import fetch_token_info_with_retry as fetch_token_info