import streamlit as st
from web3 import Web3
from eth_account import Account
from decimal import Decimal, getcontext
import json
import requests
import pandas as pd
import time
import threading

getcontext().prec = 28

st.set_page_config(page_title="🔍 ETH & Token Tracker", layout="wide")
st.title("🧠 ETH & ERC20 Multi-Wallet Tool")

# List RPC fallback
POSSIBLE_RPCS = [
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
    "https://ethereum.publicnode.com",
    "https://mainnet.infura.io/v3/YOUR_INFURA_KEY",
    "https://cloudflare-eth.com"
]

def get_working_rpc():
    for rpc in POSSIBLE_RPCS:
        w3 = Web3(Web3.HTTPProvider(rpc))
        try:
            if w3.is_connected():
                return rpc
        except:
            continue
    return None

DEFAULT_RPC = get_working_rpc()
if not DEFAULT_RPC:
    st.error("❌ Không tìm được RPC khả dụng.")
    st.stop()

st.sidebar.header("⚙️ Cấu hình RPC & Ví Nhận")
RPC_URL = st.sidebar.text_input("🌐 RPC URL", value=DEFAULT_RPC)
DEST_WALLET = st.sidebar.text_input("🛅 Ví nhận ETH", value="0x...", max_chars=42)
ERC20_CONTRACT = st.sidebar.text_input("📦 Contract Token (nếu có)", value="")
GAS_CUSTOM = st.sidebar.number_input("⚡ Gas Price (Gwei, 0 = auto)", min_value=0.0, value=0.0, format="%.3f")

mode = st.sidebar.radio("🔁 Chế độ gửi tiền", ["Chuyển toàn bộ về 1 ví", "Chia đều sang nhiều ví"])

web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    st.error("❌ Không kết nối được RPC.")
    st.stop()

# Hiện giá ETH và Gas
col_price = st.columns(2)
try:
    eth_price = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd").json()['ethereum']['usd']
    col_price[0].metric("💸 Giá ETH", f"${eth_price:.2f}")
except:
    col_price[0].warning("Không lấy được giá ETH")

try:
    gas_now = Decimal(web3.eth.gas_price) / Decimal(1e9)
    col_price[1].metric("⚡ Gas (Gwei)", f"{gas_now:.3f}")
except:
    col_price[1].warning("Không lấy được gas")

# ========== CHECK BALANCE GIAO DIỆN CHÍNH ============
st.markdown("## 📂 Nhập danh sách Private Key")
input_keys = st.text_area("✍️ Dán private key (1 dòng 1 key)", height=150)
with st.expander("📁 Hoặc tải file .txt"):
    uploaded = st.file_uploader("Tải file chứa private key", type=["txt"])

wallets = []
if input_keys.strip():
    wallets = [line.strip() for line in input_keys.splitlines() if line.strip()]
elif uploaded:
    content = uploaded.read().decode("utf-8").splitlines()
    wallets = [line.strip() for line in content if line.strip()]

if wallets:
    st.markdown("### 📊 Kết quả kiểm tra")
    total_eth = Decimal(0)
    total_token = Decimal(0)
    rows = []
    token_symbol = "Token"
    token_decimals = 18
    market_info = ""
    realtime_price = st.empty()

    if ERC20_CONTRACT:
        try:
            token_contract = web3.eth.contract(
                address=web3.to_checksum_address(ERC20_CONTRACT),
                abi=json.loads('[{"name":"symbol","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},' +
                               '{"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"},' +
                               '{"name":"totalSupply","outputs":[{"type":"uint256"}],"inputs":[],"stateMutability":"view","type":"function"},' +
                               '{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]')
            )
            token_symbol = token_contract.functions.symbol().call()
            token_decimals = token_contract.functions.decimals().call()
            total_supply = Decimal(token_contract.functions.totalSupply().call()) / Decimal(10 ** token_decimals)

            def update_realtime():
                while True:
                    try:
                        dex_url = f"https://api.dexscreener.com/latest/dex/tokens/{ERC20_CONTRACT}"
                        dex_data = requests.get(dex_url).json()
                        if 'pairs' in dex_data and len(dex_data['pairs']) > 0:
                            pair_info = dex_data['pairs'][0]
                            price_usd = pair_info.get('priceUsd', 'N/A')
                            marketcap = pair_info.get('fdv', 'N/A')
                            realtime_price.success(f"💲Giá: ${price_usd}, 🧢 FDV: {marketcap}")
                    except:
                        realtime_price.warning("Không lấy được giá token.")
                    time.sleep(10)

            threading.Thread(target=update_realtime, daemon=True).start()

        except:
            st.warning("❌ Không thể load thông tin token.")

    for idx, priv in enumerate(wallets, 1):
        try:
            acct = Account.from_key(priv)
            address = acct.address
            eth_bal = Decimal(web3.eth.get_balance(address)) / Decimal(1e18)
            total_eth += eth_bal
            token_bal = "-"

            if ERC20_CONTRACT:
                try:
                    token_balance_raw = token_contract.functions.balanceOf(address).call()
                    token_bal = Decimal(token_balance_raw) / Decimal(10 ** token_decimals)
                    total_token += token_bal
                except:
                    token_bal = "Lỗi"

            rows.append({"#": idx, "Ví": address, "ETH": f"{eth_bal:.6f}", token_symbol: token_bal})
        except Exception as e:
            rows.append({"#": idx, "Ví": "Lỗi", "ETH": "-", token_symbol: "-"})

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("### 📈 Tổng kết")
    cols = st.columns(2)
    cols[0].metric("💵 Tổng ETH", f"{total_eth:.6f}")
    if ERC20_CONTRACT:
        cols[1].metric(f"📦 Tổng {token_symbol}", f"{total_token:.4f}")

    if st.button("🔄 Làm mới"):
        st.experimental_rerun()
