# Review path

Start here: [`README.md`](../README.md) (site link, contract, transactions, evidence, usage), then [`evidence/DEPLOYMENT.md`](DEPLOYMENT.md).

## Quickest re-check (read-only, no wallet needed)

1. Open the site: https://zsf11221.github.io/genlayer-copy-trading/ — the trader hall loads from the chain with no wallet.
2. Open the contract on the explorer: https://explorer-studio.genlayer.com/address/0x7a611A569a0668E992c438Bc0384657A493Ec3c8
3. Read the contract state with `genlayer-py` against `https://studio.genlayer.com/api` (chain 61999):
   - `get_trader("0xa55C0789a06A5Cc9AeBc2158F0F79EA01a8c697b")` — expect badge `VERIFIED`, reputation `1120`, followers `1`, copy PnL `30000000` microGEN.
   - `get_record("1")` — expect status `VERIFIED`, verdict `VERIFIED|STRONG_EVIDENCE`.
   - `get_record("2")` — expect status `VERIFIED` after appeal; history shows the first verdict `REJECTED|THIN_EVIDENCE`.
   - `get_copy("1")` — expect status `SETTLED`, principal `150000000`, PnL `30000000`, trader share `6000000`, follower return `174000000` (microGEN).
   - `get_platform_pool()` — expect `10000000` microGEN (10 GEN slashed from the rejected record).
4. Full receipts and read-back state: [`live-verification.json`](live-verification.json).

## Reproduce locally

```sh
python3 -m pytest tests/ -q        # 22 direct-mode tests, no network
python3 scripts/verify_studionet.py --contract-address 0x7a611A569a0668E992c438Bc0384657A493Ec3c8
```

Note: re-running the verify script sends new transactions from fresh ephemeral accounts against the same contract (new records, new copies); it does not repeat the recorded run.
