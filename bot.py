import os
import json
import time
from web3 import Web3 # type: ignore
from dotenv import load_dotenv # type: ignore

load_dotenv()

# --- CONFIGURACOES ---
INFURA_URL = os.getenv("INFURA_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = Web3.to_checksum_address(os.getenv("WALLET_ADDRESS"))

# --- CONEXAO COM A REDE ---
w3 = Web3(Web3.HTTPProvider(INFURA_URL))
assert w3.is_connected(), "Erro ao conectar ao nó Ethereum."

# --- UNISWAP V2 FACTORY ---
FACTORY_ADDRESS = Web3.to_checksum_address("0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f")
WETH_ADDRESS = Web3.to_checksum_address("0xC02aaA39b223FE8D0A0E5C4F27eAD9083C756Cc2")
ROUTER_ADDRESS = Web3.to_checksum_address("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")

# ABI do evento PairCreated
factory_abi = [{
    "anonymous": False,
    "inputs": [
        {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "pair", "type": "address"}
    ],
    "name": "PairCreated",
    "type": "event"
}]

# ABI do Uniswap Router e ERC20
with open("uniswap_router_abi.json", "r") as f:
    router_abi = json.load(f)

ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[{"name":"owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},{"constant":false,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"}]')

factory = w3.eth.contract(address=FACTORY_ADDRESS, abi=factory_abi)
router = w3.eth.contract(address=ROUTER_ADDRESS, abi=router_abi)

AMOUNT_ETH = 0.05
GAS_PRICE_GWEI = 100
LIQUIDITY_MIN_ETH = 1.0
SLIPPAGE = 0.3

# --- VERIFICACAO INTELIGENTE ---
def verificar_token(token_address, pair_address):
    token = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    pair = w3.eth.contract(address=pair_address, abi=ERC20_ABI)

    try:
        name = token.functions.name().call()
        symbol = token.functions.symbol().call()
        print(f"[i] Token: {name} ({symbol})")
    except:
        print("[!] Nome ou símbolo do token não disponível.")
        return False

    # Verificar liquidez ETH no par
    eth_in_pair = w3.eth.get_balance(pair_address) / 1e18
    print(f"[i] Liquidez ETH: {eth_in_pair:.4f}")
    if eth_in_pair < LIQUIDITY_MIN_ETH:
        print("[!] Liquidez insuficiente.")
        return False

    # Testar transferência (honeypot)
    try:
        test_tx = token.functions.transfer(WALLET_ADDRESS, 1).call({'from': WALLET_ADDRESS})
    except:
        print("[!] Token parece ser honeypot (não permite transferências).")
        return False

    return True

# --- FUNCAO DE COMPRA ---
def snipe_token(token_address):
    print(f"[+] Comprando token: {token_address}")
    nonce = w3.eth.get_transaction_count(WALLET_ADDRESS)
    deadline = int(time.time()) + 60

    tx = router.functions.swapExactETHForTokens(
        0,
        [WETH_ADDRESS, token_address],
        WALLET_ADDRESS,
        deadline
    ).build_transaction({
        'from': WALLET_ADDRESS,
        'value': w3.to_wei(AMOUNT_ETH, 'ether'),
        'gas': 300000,
        'gasPrice': w3.to_wei(GAS_PRICE_GWEI, 'gwei'),
        'nonce': nonce
    })

    signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print(f"[+] TX enviada: https://etherscan.io/tx/{tx_hash.hex()}")

# --- MONITORAR NOVOS PARES ---
def monitor_pairs():
    print("\n🔎 Monitorando novos pares...")
    retry_delay = 5

    while True:
        try:
            latest_block = w3.eth.block_number
            time.sleep(3)
            to_block = w3.eth.block_number

            if to_block > latest_block:
                logs = w3.eth.get_logs({
                    'fromBlock': latest_block + 1,
                    'toBlock': to_block,
                    'address': FACTORY_ADDRESS,
                    'topics': ['0x' + w3.keccak(text="PairCreated(address,address,address)").hex()]
                })
                for log in logs:
                    topics = log['topics']
                    token0 = Web3.to_checksum_address('0x' + topics[1].hex()[-40:])
                    token1 = Web3.to_checksum_address('0x' + topics[2].hex()[-40:])
                    pair = Web3.to_checksum_address('0x' + log['data'][-40:])

                    if WETH_ADDRESS in [token0, token1]:
                        new_token = token1 if token0 == WETH_ADDRESS else token0
                        print(f"\n🆕 Novo par com WETH: {new_token} | Pair: {pair}")
                        if verificar_token(new_token, pair):
                            snipe_token(new_token)
                retry_delay = 5
        except Exception as e:
            print(f"[!] Erro ao monitorar pares: {e}")
            print(f"[i] A tentar novamente em {retry_delay} segundos...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay + 5, 30)

if __name__ == '__main__':
    print("Bot de sniping automático pronto. Monitorando Uniswap V2...")
    monitor_pairs()