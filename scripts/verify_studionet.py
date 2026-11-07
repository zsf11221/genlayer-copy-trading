"""Deploy CopyArena to Stable Studionet and verify the copy-trading flow live.

Ephemeral accounts are generated in memory only. Private keys are never
written to disk, logs, or the repository. Only addresses, transaction
hashes, and read-back state are recorded.

Run from the repository root:
    python3 scripts/verify_studionet.py [--contract-address 0x...]

Output: evidence/live-verification.json (updated after every step).
Requires: genlayer-py, eth-account. Network: Stable Studionet (61999).
"""

import hashlib
import json
import sys
import time
from pathlib import Path

from eth_account import Account

from genlayer_py import create_client
from genlayer_py.chains import studionet
from genlayer_py.types.transactions import TransactionStatus

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "contracts" / "copy_arena.py"
EVIDENCE_PATH = ROOT / "evidence" / "live-verification.json"
RPC = "https://studio.genlayer.com/api"
CHAIN_ID = 61999

GEN = 1_000_000
WAIT_INTERVAL_MS = 5000

# Trader 1 good record: 10 trades, 7 wins -> win_rate_bp 7000.
# Line pnl values sum to exactly 15,000,000 microGEN (15 GEN).
GOOD_RECORD = (
    "Track record for Ava Chen, spot trader, 2026-09-01 to 2026-11-01. "
    "Total trades: 10. Wins: 7. Losses: 3. win_rate_bp: 7000. "
    "total_pnl_microgen: 15000000. "
    "Representative trade lines (every trade, pnl in microGEN): "
    "1. BTC long +4000000; 2. ETH long +3000000; 3. SOL long -1000000; "
    "4. BTC short +2500000; 5. ETH long +1500000; 6. ARB long -500000; "
    "7. BTC long +3000000; 8. SOL short +2000000; 9. ETH short -1000000; "
    "10. BTC long +1500000. "
    "Source: exported trade history from the exchange account statements "
    "for September to October 2026, cross-checked against the on-chain "
    "deposit and withdrawal log for the same period."
)

THIN_RECORD = "I am a great trader, trust me, 100x returns guaranteed."

# Appeal record for trader 2: 8 trades, 6 wins -> win_rate_bp 7500.
# Line pnl values sum to exactly 7,000,000 microGEN (7 GEN).
APPEAL_RECORD = (
    "Corrected full track record for Ben Okafor, spot trader, "
    "2026-08-01 to 2026-10-31. The first submission was an incomplete "
    "summary; this appeal supplies the complete trade log. "
    "Total trades: 8. Wins: 6. Losses: 2. win_rate_bp: 7500. "
    "total_pnl_microgen: 7000000. "
    "Trade lines (every trade, pnl in microGEN): "
    "1. BTC long +2000000; 2. ETH long +1000000; 3. SOL long -500000; "
    "4. BTC short +1500000; 5. ETH long +500000; 6. ARB long -500000; "
    "7. BTC long +2000000; 8. SOL short +1000000. "
    "Source: exported trade history from the exchange account statements "
    "for August to October 2026, cross-checked against the on-chain "
    "deposit and withdrawal log for the same period."
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def tx_hash_str(tx) -> str:
    if isinstance(tx, bytes):
        return "0x" + tx.hex()
    return str(tx)


def leader_execution_result(receipt: dict):
    try:
        return receipt["consensus_data"]["leader_receipt"][0]["execution_result"]
    except (KeyError, IndexError, TypeError):
        return None


def receipt_summary(receipt: dict) -> dict:
    return {
        "hash": receipt.get("hash") or receipt.get("tx_id"),
        "status": str(receipt.get("status_name") or receipt.get("status")),
        "execution_result": leader_execution_result(receipt),
        "contract_address": (receipt.get("data") or {}).get("contract_address"),
    }


class Runner:
    def __init__(self, contract_address: str | None = None):
        self.trader1 = Account.create()
        self.trader2 = Account.create()
        self.follower = Account.create()
        self.contract_address = contract_address
        self.evidence = {
            "network": "Stable Studionet",
            "chain_id": CHAIN_ID,
            "rpc": RPC,
            "contract_address": contract_address,
            "deploy_tx": None,
            "deploy_source_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
            "accounts": {
                "trader1": self.trader1.address,
                "trader2": self.trader2.address,
                "follower": self.follower.address,
            },
            "steps": [],
            "final_readback": {},
            "notes": [],
        }
        self._save()

    def _save(self) -> None:
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(self.evidence, indent=2, sort_keys=False))

    def client_for(self, account):
        return create_client(chain=studionet, account=account, endpoint=RPC)

    def wait_finalized(self, client, tx_hash: str, label: str) -> dict:
        last_error = None
        for attempt in range(30):
            try:
                receipt = client.wait_for_transaction_receipt(
                    tx_hash,
                    status=TransactionStatus.FINALIZED,
                    interval=WAIT_INTERVAL_MS,
                    retries=12,
                )
                summary = receipt_summary(receipt)
                log(f"  -> {label}: status={summary['status']} execution={summary['execution_result']}")
                if summary["status"] != "FINALIZED":
                    raise RuntimeError(f"{label}: not FINALIZED: {summary}")
                if summary["execution_result"] != "SUCCESS":
                    raise RuntimeError(f"{label}: execution not SUCCESS: {json.dumps(receipt, default=str)[:2000]}")
                return summary
            except RuntimeError:
                raise
            except Exception as e:
                last_error = e
                log(f"  !! {label}: RPC poll failed (attempt {attempt + 1}/30): {str(e)[:200]}; retrying in 10s")
                time.sleep(10)
        raise RuntimeError(f"{label}: receipt poll kept failing: {last_error}")

    def write(self, account, method: str, args, label: str) -> dict:
        client = self.client_for(account)
        tx = client.write_contract(
            self.contract_address, method, account=account, args=list(args)
        )
        tx_hash = tx_hash_str(tx)
        step = {"step": label, "method": method, "args": [str(a)[:120] for a in args],
                "tx_hash": tx_hash, "status": "SENT", "execution_result": None}
        self.evidence["steps"].append(step)
        self._save()
        summary = self.wait_finalized(client, tx_hash, label)
        step.update(summary)
        self._save()
        return summary

    def read(self, method: str, args=None):
        last_error = None
        for attempt in range(10):
            try:
                client = self.client_for(self.trader1)
                return client.read_contract(self.contract_address, method, args=list(args or []))
            except Exception as e:
                last_error = e
                log(f"  !! read {method}: RPC failed (attempt {attempt + 1}/10): {str(e)[:200]}; retrying in 5s")
                time.sleep(5)
        raise RuntimeError(f"read {method} kept failing: {last_error}")

    def deploy(self) -> None:
        code = CONTRACT_PATH.read_bytes()
        client = self.client_for(self.trader1)
        log("deploying contract...")
        tx = client.deploy_contract(code, account=self.trader1)
        tx_hash = tx_hash_str(tx)
        summary = self.wait_finalized(client, tx_hash, "deploy")
        address = summary.get("contract_address")
        if not address:
            raise RuntimeError(f"deploy receipt has no contract address: {summary}")
        self.contract_address = address
        self.evidence["contract_address"] = address
        self.evidence["deploy_tx"] = tx_hash
        self.evidence["steps"].append(
            {"step": "deploy", "method": "__init__", "args": [],
             "tx_hash": tx_hash, **summary}
        )
        self._save()
        log(f"deployed at {address}")


def main() -> int:
    contract_address = None
    if len(sys.argv) > 2 and sys.argv[1] == "--contract-address":
        contract_address = sys.argv[2]
    runner = Runner(contract_address)
    log(f"trader1:  {runner.trader1.address}")
    log(f"trader2:  {runner.trader2.address}")
    log(f"follower: {runner.follower.address}")

    if not runner.contract_address:
        runner.deploy()

    # Fund all three actors with TEST GEN (nominal in-contract ledger).
    runner.write(runner.trader1, "claim_test_gen", [], "trader1 claim_test_gen")
    runner.write(runner.trader2, "claim_test_gen", [], "trader2 claim_test_gen")
    runner.write(runner.follower, "claim_test_gen", [], "follower claim_test_gen")

    # Register both traders with 50 GEN stake each.
    runner.write(runner.trader1, "register_trader", ["Ava Chen", str(50 * GEN)], "trader1 register_trader 50 GEN")
    runner.write(runner.trader2, "register_trader", ["Ben Okafor", str(50 * GEN)], "trader2 register_trader 50 GEN")

    demos = {"verified_badge": False, "copy_settled": False,
             "rejected_slashed": False, "appeal_adjudicated": False,
             "dispute_adjudicated": False}

    # --- Record 1: good evidence, expect VERIFIED + badge ---
    rec1 = runner.read("get_next_record_id")
    runner.write(runner.trader1, "submit_track_record", [GOOD_RECORD], "trader1 submit_track_record")
    runner.write(runner.trader1, "audit_record", [rec1], "trader1 audit_record")
    r1 = runner.read("get_record", [rec1])
    log(f"record1: status={r1['status']} verdict={r1['verdict']}")
    t1 = runner.read("get_trader", [runner.trader1.address])
    log(f"trader1 after audit: badge={t1['badge']} reputation={t1['reputation']}")
    if r1["status"] == "VERIFIED" and t1["badge"] == "VERIFIED":
        demos["verified_badge"] = True
    else:
        runner.evidence["notes"].append("record1 was NOT verified; copy flow cannot proceed as planned.")

    # --- Copy flow: follow 100 GEN, add 50 GEN, settle +30 GEN profit ---
    if demos["verified_badge"]:
        copy1 = runner.read("get_next_copy_id")
        runner.write(runner.follower, "follow_trader", [runner.trader1.address, str(100 * GEN)],
                     "follower follow_trader 100 GEN")
        runner.write(runner.follower, "copy_position", [copy1, str(50 * GEN)],
                     "follower copy_position +50 GEN")
        c1 = runner.read("get_copy", [copy1])
        log(f"copy1 before settle: principal={c1['principal']} status={c1['status']}")
        runner.write(runner.follower, "settle_copy", [copy1, str(30 * GEN)],
                     "follower settle_copy +30 GEN pnl")
        c1 = runner.read("get_copy", [copy1])
        log(f"copy1 after settle: status={c1['status']} pnl={c1['pnl']} "
            f"trader_share={c1['trader_share']} follower_return={c1['follower_return']}")
        if c1["status"] == "SETTLED":
            demos["copy_settled"] = True

    # --- Record 2: thin evidence, expect REJECTED + slash ---
    rec2 = runner.read("get_next_record_id")
    runner.write(runner.trader2, "submit_track_record", [THIN_RECORD], "trader2 submit_track_record (thin)")
    runner.write(runner.trader2, "audit_record", [rec2], "trader2 audit_record")
    r2 = runner.read("get_record", [rec2])
    log(f"record2: status={r2['status']} verdict={r2['verdict']}")
    t2 = runner.read("get_trader", [runner.trader2.address])
    log(f"trader2 after audit: stake={t2['stake']} reputation={t2['reputation']}")
    if r2["status"] == "REJECTED":
        demos["rejected_slashed"] = True

    # --- Appeal: trader2 appeals with complete evidence ---
    if r2["status"] == "REJECTED":
        runner.write(runner.trader2, "appeal", [rec2, APPEAL_RECORD], "trader2 appeal")
        runner.write(runner.trader2, "adjudicate_appeal", [rec2], "trader2 adjudicate_appeal")
        r2 = runner.read("get_record", [rec2])
        log(f"record2 after appeal: status={r2['status']} verdict={r2['verdict']}")
        demos["appeal_adjudicated"] = True
        t2 = runner.read("get_trader", [runner.trader2.address])
        log(f"trader2 after appeal: badge={t2['badge']} reputation={t2['reputation']}")

    # --- Dispute: follower disputes trader1's verified record, re-audit ---
    if r1["status"] == "VERIFIED":
        runner.write(runner.follower, "dispute_fake", [rec1, "The win rate in this record looks too smooth; requesting a re-audit of the trade lines."],
                     "follower dispute_fake record1")
        runner.write(runner.follower, "audit_dispute", [rec1], "follower audit_dispute record1")
        r1 = runner.read("get_record", [rec1])
        log(f"record1 after dispute: status={r1['status']} verdict={r1['verdict']}")
        demos["dispute_adjudicated"] = True

    # --- Final read-back ---
    final = {
        "traders": {},
        "records": {},
        "copies": {},
        "platform_pool_microgen": runner.read("get_platform_pool"),
        "balances": {
            "trader1": runner.read("get_balance", [runner.trader1.address]),
            "trader2": runner.read("get_balance", [runner.trader2.address]),
            "follower": runner.read("get_balance", [runner.follower.address]),
        },
        "demos": demos,
    }
    for addr_key, addr in [("trader1", runner.trader1.address),
                           ("trader2", runner.trader2.address)]:
        try:
            final["traders"][addr_key] = runner.read("get_trader", [addr])
        except Exception as e:
            log(f"get_trader {addr_key}: {e}")
    for rid in ["1", "2"]:
        try:
            final["records"][rid] = runner.read("get_record", [rid])
        except Exception as e:
            log(f"get_record {rid}: {e}")
    try:
        final["copies"]["1"] = runner.read("get_copy", ["1"])
    except Exception as e:
        log(f"get_copy 1: {e}")
    runner.evidence["final_readback"] = final
    runner.evidence["notes"].append(f"demos demonstrated: {demos}")
    runner._save()
    log("DONE")
    log(json.dumps(final, indent=2)[:4000])
    if not all(demos.values()):
        log(f"WARNING: not all demos were demonstrated: {demos}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
