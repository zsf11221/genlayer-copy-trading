# CopyArena — Audited Social Copy Trading

**Live site: https://zsf11221.github.io/genlayer-copy-trading/**

Find a trader whose track record survived consensus audit, follow them, and copy their positions. Verified traders earn a share of the profit they generate for followers; faked track records get rejected, slashed, and lose their badge.

## How it works

1. A trader claims TEST GEN, stakes 20+ GEN, and submits a track record: total trades, wins, win rate, total PnL, every trade line, and a source description.
2. GenLayer validators independently re-derive the numbers — win rate from wins and trades, total PnL from the trade lines — and judge whether the evidence is complete and credible. Only a consensus `VERIFIED` verdict issues the followable badge.
3. Followers lock principal against a verified trader and copy positions proportionally. On settlement, a profit splits 20% to the trader and 80% to the follower (plus principal); losses are borne by the follower.
4. A rejected record slashes 20% of the trader's stake into the platform pool. The trader can appeal once with a complete record. Anyone can dispute a verified record as fake; a re-audit that rejects it revokes the badge and slashes again.

## Contract

- Network: Stable Studionet (Chain ID 61999), RPC https://studio.genlayer.com/api
- Contract: `0x7a611A569a0668E992c438Bc0384657A493Ec3c8`
- Explorer: https://explorer-studio.genlayer.com/address/0x7a611A569a0668E992c438Bc0384657A493Ec3c8
- Deploy transaction: `0xdc84a739a564cfefef68ff6849d0a0e09f2777cc244944307ff63047f5d29862`
- Source: [`contracts/copy_arena.py`](contracts/copy_arena.py) (SHA256 `52c2b125c39dc4abc2d5c8493de0523593bd84394a24da71af38140f64607678`)
- Runner: `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`

## Verified on-chain

17 transactions, all FINALIZED with execution `SUCCESS`. Highlights:

- Record 1 (Ava Chen): `VERIFIED|STRONG_EVIDENCE`, badge issued; a later fake-report re-audit confirmed `VERIFIED`.
- Record 2 (Ben Okafor): first verdict `REJECTED|THIN_EVIDENCE` (10 GEN slashed into the pool), appeal with a complete trade log adjudicated `VERIFIED|STRONG_EVIDENCE`.
- Copy 1: 150 GEN principal, +30 GEN realized PnL, settled — trader share 6 GEN, follower return 174 GEN.
- Final state: trader 1 reputation 1120, followers 1, copy PnL +30 GEN; trader 2 reputation 950, stake 40 GEN; platform pool 10 GEN.

Full receipts and read-back state: [`evidence/live-verification.json`](evidence/live-verification.json). Deployment record: [`evidence/DEPLOYMENT.md`](evidence/DEPLOYMENT.md). Scope: [`evidence/KNOWN_LIMITATIONS.md`](evidence/KNOWN_LIMITATIONS.md). Review path: [`evidence/REVIEW.md`](evidence/REVIEW.md).

## Use it

- No wallet needed to browse the trader hall, track records, and the pool — the site reads from the chain directly.
- To write (claim TEST GEN, register, submit a record, follow, settle, appeal, dispute), connect any injected EVM wallet (MetaMask, OKX, Rabby, Coinbase) on Studionet (Chain ID 61999), or use the in-browser temporary test account offered on the site. All GEN here is a nominal in-contract TEST ledger, not real GEN.

## Develop

```sh
pip install -r requirements.txt
python3 -m pytest tests/ -q        # 22 direct-mode tests, no network
python3 scripts/verify_studionet.py --contract-address 0x7a611A569a0668E992c438Bc0384657A493Ec3c8
```

Frontend (Vite + genlayer-js):

```sh
cd frontend && npm install && npm run build && npm run check:i18n
```

The built `dist/` is published to the `gh-pages` branch; GitHub Pages serves it at the live site above.
