import streamlit as st
from web3 import Web3
from eth_account import Account
from decimal import Decimal, getcontext
import json
import requests
import pandas as pd
import time

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
REFRESH = st.sidebar.button("🔁 Làm mới số dư")

mode = st.sidebar.radio("🔁 Chế độ gửi tiền", ["Chuyển toàn bộ về 1 ví", "Chia đều sang nhiều ví"])

selected_wallets_to_receive = []
send_amount = Decimal(0)
source_wallet = None

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

if mode == "Chia đều sang nhiều ví":
    with st.sidebar.expander("📤 Tùy chọn chia đều"):
        wallet_selection_input = st.text_area("📥 Dán danh sách ví nhận (1 ví mỗi dòng)")
        if wallet_selection_input.strip():
            selected_wallets_to_receive = [line.strip() for line in wallet_selection_input.splitlines() if line.strip()]
        send_amount_float = st.number_input("💰 Tổng số ETH cần chia", min_value=0.0, format="%.6f")
        send_amount = Decimal(str(send_amount_float))
        if wallets:
            source_wallet_options = [f"{i+1}: {Account.from_key(pk).address}" for i, pk in enumerate(wallets)]
            source_wallet_display = st.selectbox("📤 Chọn ví nguồn", options=source_wallet_options)
            source_wallet_index = int(source_wallet_display.split(":")[0]) - 1
            source_wallet = wallets[source_wallet_index]

send_trigger = st.button("🚀 Thực hiện chuyển tiền")

@st.cache_data(ttl=60)
def fetch_token_info(contract_addr):
    token_contract = web3.eth.contract(
        address=web3.to_checksum_address(contract_addr),
        abi=json.loads('[{"name":"symbol","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},' +
                       '{"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"},' +
                       '{"name":"totalSupply","outputs":[{"type":"uint256"}],"inputs":[],"stateMutability":"view","type":"function"},' +
                       '{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]')
    )
    symbol = token_contract.functions.symbol().call()
    decimals = token_contract.functions.decimals().call()
    supply = Decimal(token_contract.functions.totalSupply().call()) / Decimal(10 ** decimals)
    try:
        dex_data = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{contract_addr}").json()
        if 'pairs' in dex_data and len(dex_data['pairs']) > 0:
            pair = dex_data['pairs'][0]
            price = pair.get("priceUsd", "N/A")
            marketcap = pair.get("fdv", "N/A")
            return symbol, decimals, supply, price, marketcap
    except:
        pass
    return symbol, decimals, supply, "N/A", "N/A"

# ==== HIỂN THỊ BẢNG KIỂM TRA SỐ DƯ ====
if wallets:
    st.markdown("## 📊 Kết quả kiểm tra số dư")
    table_rows = []
    for i, pk in enumerate(wallets):
        try:
            acct = Account.from_key(pk)
            addr = acct.address
            eth_bal = Decimal(web3.eth.get_balance(addr)) / Decimal(1e18)
            token_info = "-"
            if ERC20_CONTRACT:
                try:
                    symbol, decimals, _, _, _ = fetch_token_info(ERC20_CONTRACT)
                    token_contract = web3.eth.contract(
                        address=web3.to_checksum_address(ERC20_CONTRACT),
                        abi=json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]')
                    )
                    token_raw = token_contract.functions.balanceOf(addr).call()
                    token_bal = Decimal(token_raw) / Decimal(10 ** decimals)
                    token_info = f"{token_bal:.4f} {symbol}"
                except:
                    token_info = "❌"
            table_rows.append({"#": i+1, "Địa chỉ": addr, "ETH": f"{eth_bal:.6f}", "Token": token_info})
        except Exception as e:
            table_rows.append({"#": i+1, "Địa chỉ": "Lỗi", "ETH": "-", "Token": str(e)})

    df = pd.DataFrame(table_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if REFRESH:
        st.rerun()

    if send_trigger and mode == "Chia đều sang nhiều ví" and source_wallet and selected_wallets_to_receive:
        st.markdown("### 🔄 Đang gửi tiền...")
        results = []
        try:
            acct = Account.from_key(source_wallet)
            from_addr = acct.address
            gas_price = Decimal(web3.to_wei(GAS_CUSTOM, 'gwei')) if GAS_CUSTOM > 0 else Decimal(web3.eth.gas_price)
            gas_fee = gas_price * Decimal(21000) / Decimal(1e18)
            value_each = (send_amount / Decimal(len(selected_wallets_to_receive))).quantize(Decimal('0.000000000000000001'))

            for to_wallet in selected_wallets_to_receive:
                try:
                    tx = {
                        'nonce': web3.eth.get_transaction_count(from_addr),
                        'to': to_wallet,
                        'value': int(value_each * Decimal(1e18)),
                        'gas': 21000,
                        'gasPrice': int(gas_price),
                        'chainId': 1
                    }
                    signed = Account.sign_transaction(tx, source_wallet)
                    raw_tx = getattr(signed, 'rawTransaction', getattr(signed, 'raw_transaction', None))
                    tx_hash = web3.eth.send_raw_transaction(raw_tx)
                    results.append({"Ví": to_wallet, "Trạng thái": f"✅ [TX](https://etherscan.io/tx/{tx_hash.hex()})"})
                except Exception as ex:
                    results.append({"Ví": to_wallet, "Trạng thái": str(ex)})
        except Exception as err:
            results.append({"Ví": "❌ Lỗi", "Trạng thái": str(err)})

        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

    if send_trigger and mode == "Chuyển toàn bộ về 1 ví":
        st.markdown("### 🔄 Đang gửi tiền...")
        results = []
        for priv_key in wallets:
            try:
                acct = Account.from_key(priv_key)
                address = acct.address
                gas_price = Decimal(web3.to_wei(GAS_CUSTOM, 'gwei')) if GAS_CUSTOM > 0 else Decimal(web3.eth.gas_price)
                gas_fee = gas_price * Decimal(21000) / Decimal(1e18)
                balance = Decimal(web3.eth.get_balance(address)) / Decimal(1e18)
                amount_to_send = balance - gas_fee
                if amount_to_send > 0:
                    tx = {
                        'nonce': web3.eth.get_transaction_count(address),
                        'to': DEST_WALLET,
                        'value': int(amount_to_send * Decimal(1e18)),
                        'gas': 21000,
                        'gasPrice': int(gas_price),
                        'chainId': 1
                    }
                    signed = Account.sign_transaction(tx, priv_key)
                    raw_tx = getattr(signed, 'rawTransaction', getattr(signed, 'raw_transaction', None))
                    tx_hash = web3.eth.send_raw_transaction(raw_tx)
                    results.append({"Ví": address, "Trạng thái": f"✅ [TX](https://etherscan.io/tx/{tx_hash.hex()})"})
                else:
                    results.append({"Ví": address, "Trạng thái": "⚠️ Không đủ ETH"})
            except Exception as e:
                results.append({"Ví": "❌ Lỗi", "Trạng thái": str(e)})
        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
