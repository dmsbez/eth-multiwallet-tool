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

st.sidebar.header("⚙️ Cấu hình RPC & Ví Nhận")
RPC_URL = st.sidebar.text_input("🌐 RPC URL", value="https://eth.llamarpc.com")
DEST_WALLET = st.sidebar.text_input("📥 Ví nhận ETH", value="0x...", max_chars=42)
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

if wallets and check_trigger:
    total_eth = Decimal(0)
    total_token = Decimal(0)
    st.markdown("## 📊 Kết quả kiểm tra")

    token_symbol = "Token"
    token_decimals = 18
    token_total_supply = None

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
            token_total_supply = Decimal(token_contract.functions.totalSupply().call()) / Decimal(10 ** token_decimals)
        except:
            token_symbol = "Token"
            token_decimals = 18

    rows = []

    for idx, priv_key in enumerate(wallets, 1):
        try:
            account = Account.from_key(priv_key)
            address = account.address
            eth_balance = Decimal(web3.eth.get_balance(address)) / Decimal(1e18)
            total_eth += eth_balance

            token_balance = None
            token_error = ""
            token_percent = "-"

            if ERC20_CONTRACT:
                try:
                    token_balance_raw = token_contract.functions.balanceOf(address).call()
                    token_balance = Decimal(token_balance_raw) / Decimal(10 ** token_decimals)
                    total_token += token_balance
                    if token_total_supply:
                        token_percent = f"{(token_balance / token_total_supply * Decimal(100)):.6f}%"
                    else:
                        token_percent = f"{token_balance:.4f}"
                except Exception as token_err:
                    token_error = str(token_err)

            rows.append({
                "#": idx,
                "Ví": address,
                "ETH": f"{eth_balance:.6f}",
                token_symbol: token_percent if not token_error else token_error,
                "Trạng thái": "✅ OK"
            })

        except Exception as e:
            rows.append({
                "#": idx,
                "Ví": "❌ Lỗi",
                "ETH": "-",
                token_symbol: "-",
                "Trạng thái": str(e)
            })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### 📈 Tổng kết")
    col_summary = st.columns(2)
    col_summary[0].metric("💵 Tổng ETH", f"{total_eth:.6f} ETH")
    if ERC20_CONTRACT:
        col_summary[1].metric(f"📦 Tổng {token_symbol}", f"{total_token:.4f}")

# Chế độ chuyển toàn bộ về 1 ví
if mode == "Chuyển toàn bộ về 1 ví" and wallets:
    st.markdown("## 📤 Chuyển toàn bộ ETH")
    send_trigger_merge = st.button("🚀 Chuyển toàn bộ ETH")
    if send_trigger_merge:
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
                    }
                    signed_tx = Account.sign_transaction(tx, priv_key)
                    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
                    eth_tx_link = f"https://etherscan.io/tx/{tx_hash.hex()}"
                    tx_results.append({"Từ ví": sender_address, "Trạng thái": f"✅ [Link]({eth_tx_link})"})
                else:
                    tx_results.append({"Từ ví": sender_address, "Trạng thái": "⚠️ Không đủ ETH để gửi"})
            except Exception as e:
                tx_results.append({"Từ ví": "❌ Lỗi", "Trạng thái": str(e)})
        st.dataframe(pd.DataFrame(tx_results), use_container_width=True, hide_index=True)

# Chế độ chia đều ETH sang nhiều ví
if mode == "Chia đều sang nhiều ví" and wallets:
    st.markdown("## 🎯 Gửi tiền đến nhiều ví")
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
            for idx, dst in enumerate(dst_list, 1):
                try:
                    nonce = web3.eth.get_transaction_count(sender_address) + idx - 1
                    tx = {
                        'nonce': nonce,
                        'to': dst,
                        'value': int(Decimal(amount_per_wallet) * Decimal(1e18)),
                        'gas': 21000,
                        'gasPrice': int(gas_price),
                    }
                    signed = Account.sign_transaction(tx, sender_priv)
                    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
                    eth_tx_link = f"https://etherscan.io/tx/{tx_hash.hex()}"
                    tx_results.append({"Địa chỉ nhận": dst, "ETH": f"✅ [Link]({eth_tx_link})"})
                except Exception as e:
                    tx_results.append({"Địa chỉ nhận": dst, "ETH": f"❌ {str(e)}"})
            st.markdown("### ✅ Kết quả gửi tiền")
            st.dataframe(pd.DataFrame(tx_results), use_container_width=True, hide_index=True)

elif not wallets:
    st.info("📌 Nhập hoặc tải danh sách ví để bắt đầu.")
