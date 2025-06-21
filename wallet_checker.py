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
GAS_CUSTOM = st.sidebar.number_input("⚡ Gas Price (Gwei, 0 = auto)", min_value=0, value=0)

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
    col_price[1].metric("⚡ Gas (Gwei)", f"{gas_now:.0f}")
except:
    col_price[1].warning("Không lấy được gas")

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

col_action = st.columns(2)
check_trigger = col_action[0].button("🔍 Kiểm tra số dư")
send_trigger = col_action[1].button("🚀 Thực hiện gửi tiền")

# Luôn hiển giao diện chia đều
if mode == "Chia đều sang nhiều ví" and wallets:
    st.markdown("## 🌟 Gửi ETH chia đều")
    src_wallet_idx = st.selectbox("Chọn ví nguồn (số thứ tự)", range(1, len(wallets)+1))
    dst_input = st.text_area("📨 Danh sách địa chỉ nhận (1 dòng 1 ví)", height=150)
    dst_list = [line.strip() for line in dst_input.splitlines() if web3.is_address(line.strip())]
    amount_per_wallet = st.number_input("💰 Số ETH mỗi ví nhận", min_value=0.000001, value=0.02, step=0.001, format="%.6f")

    if send_trigger and dst_list:
        st.markdown("### 🔄 Đang gửi tiền...")
        sender_priv = wallets[src_wallet_idx-1]
        sender = Account.from_key(sender_priv)
        sender_address = sender.address
        gas_price = Decimal(web3.to_wei(GAS_CUSTOM, 'gwei')) if GAS_CUSTOM > 0 else Decimal(web3.eth.gas_price)
        gas_fee = gas_price * Decimal(21000) / Decimal(1e18)
        total_required = (Decimal(amount_per_wallet) + gas_fee) * Decimal(len(dst_list))

        balance_eth = Decimal(web3.eth.get_balance(sender_address)) / Decimal(1e18)

        if balance_eth < total_required:
            st.error(f"❌ Không đủ ETH. Cần {total_required:.6f} ETH, đang có {balance_eth:.6f} ETH")
        else:
            tx_results = []
            for idx, dst in enumerate(dst_list):
                try:
                    nonce = web3.eth.get_transaction_count(sender_address) + idx
                    tx = {
                        'nonce': nonce,
                        'to': dst,
                        'value': int(Decimal(amount_per_wallet) * Decimal(1e18)),
                        'gas': 21000,
                        'gasPrice': int(gas_price),
                        'chainId': 1
                    }
                    signed = Account.sign_transaction(tx, sender_priv)
                    raw_tx = getattr(signed, 'rawTransaction', getattr(signed, 'raw_transaction', None))
                    tx_hash = web3.eth.send_raw_transaction(raw_tx)
                    eth_tx_link = f"https://etherscan.io/tx/{tx_hash.hex()}"
                    tx_results.append({"Địa chỉ nhận": dst, "ETH": f"✅ [Link]({eth_tx_link})"})
                except Exception as e:
                    tx_results.append({"Địa chỉ nhận": dst, "ETH": f"❌ {str(e)}"})
            st.markdown("### ✅ Kết quả gửi tiền")
            st.dataframe(pd.DataFrame(tx_results), use_container_width=True, hide_index=True)

# Giao diện chuyển toàn bộ về 1 ví
if mode == "Chuyển toàn bộ về 1 ví" and wallets:
    st.markdown("## 📤 Gửi toàn bộ ETH về 1 ví")
    if send_trigger:
        st.markdown("### 🔄 Đang gửi tiền...")
        tx_results = []
        for priv_key in wallets:
            try:
                account = Account.from_key(priv_key)
                sender_address = account.address
                gas_price = Decimal(web3.to_wei(GAS_CUSTOM, 'gwei')) if GAS_CUSTOM > 0 else Decimal(web3.eth.gas_price)
                gas_fee = gas_price * Decimal(21000) / Decimal(1e18)
                balance = Decimal(web3.eth.get_balance(sender_address)) / Decimal(1e18)
                amount_to_send = balance - gas_fee
                if amount_to_send > 0:
                    tx = {
                        'nonce': web3.eth.get_transaction_count(sender_address),
                        'to': DEST_WALLET,
                        'value': int(amount_to_send * Decimal(1e18)),
                        'gas': 21000,
                        'gasPrice': int(gas_price),
                        'chainId': 1
                    }
                    signed_tx = Account.sign_transaction(tx, priv_key)
                    raw_tx = getattr(signed_tx, 'rawTransaction', getattr(signed_tx, 'raw_transaction'))
                    tx_hash = web3.eth.send_raw_transaction(raw_tx)
                    eth_tx_link = f"https://etherscan.io/tx/{tx_hash.hex()}"
                    tx_results.append({"Từ ví": sender_address, "Trạng thái": f"✅ [Link]({eth_tx_link})"})
                else:
                    tx_results.append({"Từ ví": sender_address, "Trạng thái": "⚠️ Không đủ ETH để gửi"})
            except Exception as e:
                tx_results.append({"Từ ví": "❌ Lỗi", "Trạng thái": str(e)})
        st.dataframe(pd.DataFrame(tx_results), use_container_width=True, hide_index=True)
