import json
import os
from solders.keypair import Keypair  # type: ignore
from datetime import datetime
import base58  # type: ignore
from mnemonic import Mnemonic  # type: ignore
import struct  # type: ignore
import hashlib  # type: ignore
import hmac  # type: ignore
from nacl.signing import SigningKey

def get_wallet_path(user_id: int, wallet_index: int) -> str:
    """Constructs and returns the file path for a user's wallet."""
    return os.path.join("wallets", str(user_id), f"wallet_{wallet_index}.json")


def derive_phantom_key(seed, path="m/44'/501'/0'/0'"):
    """
    Derives private key using Phantom's derivation method
    """
    # Convert path to list of integers
    path_components = []
    for component in path.split("/"):
        if component == "m":
            continue
        if component.endswith("'"):
            component = int(component[:-1]) + 0x80000000
        else:
            component = int(component)
        path_components.append(component)

    # Derive key using path
    key = seed
    for component in path_components:
        # Use proper HMAC-SHA512 for each derivation step
        data = bytearray([0x00]) + key + struct.pack(">L", component)
        hmac_obj = hmac.new(b"ed25519 seed", data, hashlib.sha512)
        key = hmac_obj.digest()[:32]

    return key


#async def create_solana_wallet():
    #keypair = Keypair()
    #print("Keypair:", keypair)

    # Get public key
    #public_key = str(keypair.pubkey())
    #print("Public Key:", public_key)
    #seed = keypair.secret()

    #mnemo = Mnemonic("english")
    #mnemonic = mnemo.to_mnemonic(seed)
    #print("Mnemonic:", mnemonic)
    # Generate seed from mnemonic with empty passphrase
    #seed = mnemo.to_seed(mnemonic, passphrase="")

    #private_key = derive_phantom_key(seed)
    #print("Private Key:", private_key)

    #mnemonic_phrase = mnemo.to_mnemonic(private_key)
    #print("Mnemonic Phrase:", mnemonic_phrase)

    # Encode private key in base58
    #private_key_bytes = bytes(keypair)
    #print("Private Key Bytes:", private_key_bytes)
    #private_key_b58 = base58.b58encode(private_key_bytes).decode("ascii")
    #print("Private Key Base58:", private_key_b58)

    #wallet_data = {
       # "address": public_key,
       # "private_key": private_key_b58,
       # "mnemonic": mnemonic_phrase,
        #"type": "solana",
    #}

    #print("Wallet Data:", json.dumps(wallet_data, indent=2))
    #return wallet_data


# Alternative method: Create from existing mnemonic
async def create_solana_wallet():
    """
    Create a Solana wallet with proper mnemonic derivation
    """
    # Method 1: Generate from random mnemonic (RECOMMENDED)
    mnemo = Mnemonic("english")

    # Generate a random mnemonic phrase
    mnemonic_phrase = mnemo.generate(strength=128)  # 12 words
    print("Generated Mnemonic:", mnemonic_phrase)

    # Convert mnemonic to seed
    seed = mnemo.to_seed(mnemonic_phrase, passphrase="")
    print("Seed length:", len(seed))

    # Derive keypair from seed using the correct method
    private_key_bytes = seed[:32]

    signing_key = SigningKey(private_key_bytes)

    # Create the full 64-byte keypair format (private + public key)
    full_keypair_bytes = private_key_bytes + bytes(signing_key.verify_key)
    keypair = Keypair.from_bytes(full_keypair_bytes)

    # Get public key
    public_key = str(keypair.pubkey())
    print("Public Key:", public_key)

    # Encode private key in base58
    private_key_b58 = base58.b58encode(bytes(keypair)).decode("ascii")

    wallet_data = {
        "address": public_key,
        "private_key": private_key_b58,
        "mnemonic": mnemonic_phrase,
        "type": "solana",
    }

    print("Wallet Data:", json.dumps(wallet_data, indent=2))


    return wallet_data


def save_wallet(user_id: int, private_key, wallet_index: int) -> bool:
    """Saves the wallet's private key to a JSON file."""
    directory_path = os.path.join("wallets", str(user_id))
    os.makedirs(directory_path, exist_ok=True)

    file_path = get_wallet_path(user_id, wallet_index)

    try:
        wallet_data = {"private_key": private_key}

        with open(file_path, "w") as f:
            json.dump(wallet_data, f)
        return True
    except Exception as e:
        print(f"Error saving wallet: {e}")  # Basic error handling
        return False


def load_wallets(user_id: int) -> list[Keypair]:
    """Loads all wallets for a given user from the wallets directory."""

    directory_path = os.path.join("wallets", str(user_id))
    loaded_keypairs = []

    # Ensure directory exists
    if not os.path.exists(directory_path):
        print(f"No wallets found for user {user_id}.")
        return loaded_keypairs

    try:
        # Iterate through all wallet JSON files
        for filename in os.listdir(directory_path):
            if filename.startswith("wallet_") and filename.endswith(".json"):
                file_path = os.path.join(directory_path, filename)

                # Load wallet data
                with open(file_path, "r") as f:
                    wallet_data = json.load(f)
                    private_key = wallet_data.get("private_key")
                    print(f"Private_key loaded: {private_key}")

                    # Convert private key list to bytes and create Keypair

                    if private_key:
                        try:
                            private_key_bytes = base58.b58decode(private_key)
                            private_key_bytes = private_key_bytes[
                                :32
                            ]  # Keep only first 32 bytes

                            # Ensure correct length
                            if len(private_key_bytes) != 32:
                                print(
                                    f"❌ Error: Decoded key length is {len(private_key_bytes)}, expected 32 bytes."
                                )
                            else:
                                # Create Keypair from the private key bytes
                                keypair = Keypair.from_seed(private_key_bytes)
                                print(f"🎃 Keypair successfully created: {keypair}")
                                loaded_keypairs.append(keypair)

                        except Exception as e:
                            print(f"❌ Decoding error: {e}")

                    else:
                        print(f"Invalid private key format in {filename}")

    except Exception as e:
        print(f"Error loading wallets: {e}")  # Basic error handling

    # Return all loaded keypairs
    return loaded_keypairs


def get_next_wallet_index(user_id: int) -> int:
    """Determines the next available wallet index for a user."""
    directory_path = os.path.join("wallets", str(user_id))

    if not os.path.exists(directory_path):
        return 0

    max_index = -1
    try:
        for filename in os.listdir(directory_path):
            if filename.startswith("wallet_") and filename.endswith(".json"):
                try:
                    # Extract index from filename like "wallet_0.json"
                    index_str = filename.split("_")[1].split(".")[0]
                    index = int(index_str)
                    if index > max_index:
                        max_index = index
                except (IndexError, ValueError) as e:
                    print(
                        f"Could not parse wallet index from filename: {filename} due to {e}"
                    )
                    # Continue to next file if parsing fails for one
                    continue
    except Exception as e:
        print(f"Error listing or parsing wallet files: {e}")  # Basic error handling
        return 0  # Fallback to 0 in case of broader error

    return max_index + 1

    # import json
    # import os
    # from solders.keypair import Keypair  # type: ignore
    # from datetime import datetime
    # import base58  # type: ignore
    # from mnemonic import Mnemonic  # type: ignore
    # import struct  # type: ignore
    # import hashlib  # type: ignore
    # import hmac  # type: ignore

    # def get_wallet_path(user_id: int, wallet_index: int) -> str:
    #     """Constructs and returns the file path for a user's wallet."""
    #     return os.path.join("wallets", str(user_id), f"wallet_{wallet_index}.json")

    # def derive_key_from_mnemonic(mnemonic_phrase: str, derivation_path: str = "m/44'/501'/0'/0'") -> bytes:
    #     """
    #     Deriva una clave privada de 32 bytes a partir de un mnemonic usando BIP32/BIP44
    #     """
    #     mnemo = Mnemonic("english")
    #     seed = mnemo.to_seed(mnemonic_phrase, passphrase="")

    #     # Parsear el path de derivación
    #     path_components = []
    #     for component in derivation_path.split("/"):
    #         if component == "m":
    #             continue
    #         if component.endswith("'"):
    #             component = int(component[:-1]) + 0x80000000
    #         else:
    #             component = int(component)
    #         path_components.append(component)

    #     # Derivar usando HMAC-SHA512
    #     key = seed
    #     chain_code = hashlib.sha512(b"ed25519 seed" + seed).digest()[32:]

    #     for component in path_components:
    #         if component >= 0x80000000:  # Hardened derivation
    #             data = b'\x00' + key[:32] + struct.pack(">L", component)
    #         else:  # Non-hardened derivation
    #             # Para ed25519, siempre usamos hardened derivation
    #             data = b'\x00' + key[:32] + struct.pack(">L", component)

    #         hmac_result = hmac.new(chain_code, data, hashlib.sha512).digest()
    #         key = hmac_result[:32]
    #         chain_code = hmac_result[32:]

    #     return key

    # async def create_solana_wallet():
    #     """
    #     Crea una nueva cartera Solana con mnemonic y deriva correctamente las claves
    #     """
    #     # Generar mnemonic
    #     mnemo = Mnemonic("english")
    #     mnemonic_phrase = mnemo.generate(strength=128)  # 12 palabras
    #     print("Mnemonic:", mnemonic_phrase)

    #     # Derivar la clave privada del mnemonic
    #     private_key_bytes = derive_key_from_mnemonic(mnemonic_phrase)

    #     # Crear keypair desde la clave derivada
    #     keypair = Keypair.from_seed(private_key_bytes)

    #     # Obtener la dirección pública
    #     public_key = str(keypair.pubkey())
    #     print("Public Key:", public_key)

    #     # Codificar la clave privada completa (64 bytes) en base58
    #     # La clave completa incluye tanto la parte privada como la pública
    #     private_key_full = bytes(keypair)  # Esto devuelve 64 bytes
    #     private_key_b58 = base58.b58encode(private_key_full).decode("ascii")
    #     print("Private Key Base58:", private_key_b58)

    #     wallet_data = {
    #         "address": public_key,
    #         "private_key": private_key_b58,
    #         "mnemonic": mnemonic_phrase,
    #         "type": "solana",
    #         "derivation_path": "m/44'/501'/0'/0'"
    #     }

    #     print("Wallet Data:", json.dumps(wallet_data, indent=2))
    #     return wallet_data

    # def save_wallet(user_id: int, wallet_data: dict, wallet_index: int) -> bool:
    #     """Guarda toda la información de la cartera en un archivo JSON."""
    #     directory_path = os.path.join("wallets", str(user_id))
    #     os.makedirs(directory_path, exist_ok=True)

    #     file_path = get_wallet_path(user_id, wallet_index)

    #     try:
    #         # Agregar timestamp
    #         wallet_data["created_at"] = datetime.now().isoformat()

    #         with open(file_path, "w") as f:
    #             json.dump(wallet_data, f, indent=2)
    #         print(f"✅ Cartera guardada en: {file_path}")
    #         return True
    #     except Exception as e:
    #         print(f"❌ Error guardando cartera: {e}")
    #         return False

    # def load_wallets(user_id: int) -> list[dict]:
    #     """Carga todas las carteras de un usuario y devuelve la información completa."""
    #     directory_path = os.path.join("wallets", str(user_id))
    #     loaded_wallets = []

    #     if not os.path.exists(directory_path):
    #         print(f"No se encontraron carteras para el usuario {user_id}.")
    #         return loaded_wallets

    #     try:
    #         for filename in os.listdir(directory_path):
    #             if filename.startswith("wallet_") and filename.endswith(".json"):
    #                 file_path = os.path.join(directory_path, filename)

    #                 with open(file_path, "r") as f:
    #                     wallet_data = json.load(f)

    #                     # Validar que tenemos la información necesaria
    #                     if "private_key" in wallet_data and "address" in wallet_data:
    #                         try:
    #                             # Verificar que podemos recrear el keypair
    #                             private_key_bytes = base58.b58decode(wallet_data["private_key"])
    #                             keypair = Keypair.from_bytes(private_key_bytes)

    #                             # Verificar que la dirección coincide
    #                             if str(keypair.pubkey()) == wallet_data["address"]:
    #                                 wallet_info = {
    #                                     "keypair": keypair,
    #                                     "address": wallet_data["address"],
    #                                     "mnemonic": wallet_data.get("mnemonic"),
    #                                     "file_path": file_path,
    #                                     "wallet_data": wallet_data
    #                                 }
    #                                 loaded_wallets.append(wallet_info)
    #                                 print(f"✅ Cartera cargada: {wallet_data['address']}")
    #                             else:
    #                                 print(f"❌ Error: La dirección no coincide en {filename}")

    #                         except Exception as e:
    #                             print(f"❌ Error procesando {filename}: {e}")
    #                     else:
    #                         print(f"❌ Datos incompletos en {filename}")

    #     except Exception as e:
    #         print(f"❌ Error cargando carteras: {e}")

    #     return loaded_wallets

    # def load_keypairs(user_id: int) -> list[Keypair]:
    #     """Carga solo los keypairs de las carteras (compatibilidad con código anterior)."""
    #     wallets = load_wallets(user_id)
    #     return [wallet["keypair"] for wallet in wallets]

    # def get_next_wallet_index(user_id: int) -> int:
    #     """Determina el siguiente índice disponible para una cartera de usuario."""
    #     directory_path = os.path.join("wallets", str(user_id))

    #     if not os.path.exists(directory_path):
    #         return 0

    #     max_index = -1
    #     try:
    #         for filename in os.listdir(directory_path):
    #             if filename.startswith("wallet_") and filename.endswith(".json"):
    #                 try:
    #                     index_str = filename.split("_")[1].split(".")[0]
    #                     index = int(index_str)
    #                     if index > max_index:
    #                         max_index = index
    #                 except (IndexError, ValueError) as e:
    #                     print(f"No se pudo parsear el índice del archivo: {filename} - {e}")
    #                     continue
    #     except Exception as e:
    #         print(f"Error listando archivos de carteras: {e}")
    #         return 0

    #     return max_index + 1

    # def restore_wallet_from_mnemonic(mnemonic_phrase: str, derivation_path: str = "m/44'/501'/0'/0'") -> dict:
    #     """
    #     Restaura una cartera desde un mnemonic existente
    #     """
    #     try:
    #         # Validar mnemonic
    #         mnemo = Mnemonic("english")
    #         if not mnemo.check(mnemonic_phrase):
    #             raise ValueError("Mnemonic inválido")

    #         # Derivar clave privada
    #         private_key_bytes = derive_key_from_mnemonic(mnemonic_phrase, derivation_path)

    #         # Crear keypair
    #         keypair = Keypair.from_seed(private_key_bytes)

    #         # Obtener información de la cartera
    #         public_key = str(keypair.pubkey())
    #         private_key_full = bytes(keypair)
    #         private_key_b58 = base58.b58encode(private_key_full).decode("ascii")

    #         wallet_data = {
    #             "address": public_key,
    #             "private_key": private_key_b58,
    #             "mnemonic": mnemonic_phrase,
    #             "type": "solana",
    #             "derivation_path": derivation_path
    #         }

    #         return wallet_data

    #     except Exception as e:
    #         print(f"❌ Error restaurando cartera: {e}")
    #         return None

    # # Función de ejemplo para usar el módulo
    # async def example_usage():
    #     """Ejemplo de cómo usar el módulo corregido"""
    #     user_id = 123

    #     # Crear nueva cartera
    #     print("=== Creando nueva cartera ===")
    #     wallet_data = await create_solana_wallet()

    #     # Guardar cartera
    #     wallet_index = get_next_wallet_index(user_id)
    #     success = save_wallet(user_id, wallet_data, wallet_index)

    #     if success:
    #         print(f"Cartera guardada con índice: {wallet_index}")

    #         # Cargar carteras
    #         print("\n=== Cargando carteras ===")
    #         wallets = load_wallets(user_id)

    #         for i, wallet in enumerate(wallets):
    #             print(f"Cartera {i}: {wallet['address']}")

    #         # Probar restauración desde mnemonic
    #         print("\n=== Restaurando desde mnemonic ===")
    #         restored = restore_wallet_from_mnemonic(wallet_data["mnemonic"])
    #         if restored:
    #             print(f"Cartera restaurada: {restored['address']}")
    #             print(f"¿Coincide con la original? {restored['address'] == wallet_data['address']}")

    # if __name__ == "__main__":
    #     import asyncio
    #     asyncio.run(example_usage())
