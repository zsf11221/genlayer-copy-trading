# Copy Arena — frontend

Static Vite site for the CopyArena contract on GenLayer Stable
Studionet (Chain ID 61999). The hall is people, not charts: a trader
wall, a record room for each trader's evidence and verdict history,
and a desk for registering, submitting records, following, copying
and settling — all judged by consensus.

- Contract: `0x7a611A569a0668E992c438Bc0384657A493Ec3c8`
- Live site: https://zsf11221.github.io/genlayer-copy-trading/
- RPC: https://studio.genlayer.com/api
- Explorer: https://explorer-studio.genlayer.com

## Run

```sh
npm install
npm run dev
```

## Build and deploy (GitHub Pages)

```sh
npm run build
npm run check:i18n   # every UI string must exist in English and Chinese
```

The built `dist/` is published to the `gh-pages` branch (`dist/` is
git-ignored). `vite.config.js` uses `base: './'` so the build works
from any path. GitHub Pages serves it at the live site.

## How it talks to the chain

- Reads (`list_traders`, `list_records`, `list_copies`,
  `get_platform_pool`, `get_balance`, `get_trader`, `get_record`,
  `get_copy`, `get_next_record_id`, `get_next_copy_id`) use
  `genlayer-js` with no wallet — the hall, record room and copies
  ledger load without connecting.
- Writes use `genlayer-js` `writeContract` and wait for `FINALIZED`
  via `waitForTransactionReceipt`, then read the contract state back
  before showing a result. Every write shows three honest steps —
  submitted → validators judging → finalized — with the transaction
  hash and explorer link.
- Any injected EVM wallet can connect through `window.ethereum`
  (MetaMask, OKX, Rabby, Coinbase and others). Multiple injected
  providers are listed for the user to choose from (including EIP-6963
  announcements). The site checks the wallet is on Chain ID 61999 and
  asks it to switch if not.
- Without a wallet, the site offers a temporary in-browser test account
  (`createAccount()` from `genlayer-js`). Its key is generated in the
  browser, kept only in memory (never stored), and is discarded when
  the tab closes or the user presses "Discard test account". Requests
  made with it are labelled as test-account requests in the interface.
- Amounts are string integers only — GEN amounts are converted from
  decimal input to microGEN with string math, never floats. Track-record
  evidence is assembled from structured form fields into one English
  text before submission; chain-submitted values are always English.

## Design

See `DESIGN.md` for the token system (deep navy hall, paper-white type,
brass accent; Fraunces display serif, Public Sans body, JetBrains Mono
numbers), the ASCII layout sketch and the blacklist self-check.

## Known limits

- GEN balances are a nominal in-contract test ledger. No real GEN moves.
- PnL and splits come only from the contract — no external price feed.
