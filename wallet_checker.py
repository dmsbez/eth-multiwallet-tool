import streamlit as st
from web3 import Web3
from eth_account import Account
from decimal import Decimal, getcontext
import json
import requests
import pandas as pd

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

# ====== TOKEN BUY / SELL UI ======
st.markdown("## 🛒 Giao dịch ERC20 Token")
if ERC20_CONTRACT:
    try:
        token_contract = web3.eth.contract(
            address=web3.to_checksum_address(ERC20_CONTRACT),
            abi=json.loads('[{"name":"symbol","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},' +
                           '{"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"}]')
        )
        symbol = token_contract.functions.symbol().call()
        decimals = token_contract.functions.decimals().call()
        st.success(f"📌 Token phát hiện: {symbol} (Decimals: {decimals})")

        with st.expander("🟢 MUA Token"):
            buy_priv = st.text_input("🔑 Private Key Ví Dùng Để Mua", type="password")
            buy_amount_eth = st.number_input("💰 Số ETH muốn dùng mua", min_value=0.00001, value=0.01, format="%.5f")
            dex_router = st.text_input("🧬 DEX Router (ví dụ UniswapV2)", value="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")
            if st.button("🚀 Gửi lệnh mua") and buy_priv:
                st.warning("⚙️ Tính năng này đang trong quá trình tích hợp (swapExactETHForTokens)")

        with st.expander("🔴 BÁN Token"):
            sell_priv = st.text_input("🔑 Private Key Ví Bán Token", type="password")
            sell_amount_token = st.number_input("📦 Số lượng token muốn bán", min_value=0.00001, value=1.0, format="%.5f")
            dex_router_sell = st.text_input("🧬 DEX Router (ví dụ UniswapV2)", value="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")
            if st.button("🚀 Gửi lệnh bán") and sell_priv:
                st.warning("⚙️ Tính năng này đang trong quá trình tích hợp (approve + swapExactTokensForETH)")

    except Exception as e:
        st.error(f"❌ Không thể load thông tin token: {str(e)}")
else:
    st.info("📌 Dán contract token để bắt đầu mua/bán.")

# ====== PHẦN CÒN LẠI CODE GỬI / KIỂM TRA VẪN GIỮ NGUYÊN PHÍA DƯỚI ======
# (Không đụng đến logic gốc để tránh gây lỗi thêm)
# Nếu muốn tích hợp swap thực tế (Uniswap/Pancake), hú tao tích hợp chuẩn ABIs + routes
