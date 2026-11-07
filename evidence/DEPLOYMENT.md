# Deployment record

- Network: Stable Studionet (Chain ID 61999)
- RPC: https://studio.genlayer.com/api
- Contract: `0x7a611A569a0668E992c438Bc0384657A493Ec3c8`
- Explorer: https://explorer-studio.genlayer.com/address/0x7a611A569a0668E992c438Bc0384657A493Ec3c8
- Deploy transaction: `0xdc84a739a564cfefef68ff6849d0a0e09f2777cc244944307ff63047f5d29862`
- Deployed source: `contracts/copy_arena.py`
- Source SHA256: `52c2b125c39dc4abc2d5c8493de0523593bd84394a24da71af38140f64607678`
- Source commit: `b97cd817e3435122701c6511ab35f3d10104c1a7` (the deployed file is byte-identical to the file in this repository — see the SHA256 above)
- Runner: `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (pinned; the network rejects the `latest`/`test` aliases)
- Live actors (ephemeral script accounts, addresses only): trader 1 `0xa55C0789a06A5Cc9AeBc2158F0F79EA01a8c697b`, trader 2 `0xB0AA469110EA0C6FbDF6d811569B4256F0b4c7dd`, follower `0xaDcdc54bB156dEa06549EADa9405854567b8bA7B`

## Transactions

Every transaction below reached FINALIZED with leader execution `SUCCESS`. Full receipts and read-back state: [`live-verification.json`](live-verification.json).

| Step | Transaction hash | Status | Execution |
| --- | --- | --- | --- |
| deploy | `0xdc84a739a564cfefef68ff6849d0a0e09f2777cc244944307ff63047f5d29862` | FINALIZED | SUCCESS |
| trader1 claim_test_gen | `0x02b35349aca04be3f6f241a3109f7c7fd8b0bfcbd7578706d4df0f20fc9aef06` | FINALIZED | SUCCESS |
| trader2 claim_test_gen | `0x79ee63d8eb592d1d6dd718428fc4ddee74e072a8390b5fc5084288c627823486` | FINALIZED | SUCCESS |
| follower claim_test_gen | `0xb5fd00e9d2671386c02504bfc437bbe68e3060247e66ee1d04bb9fb372cd2450` | FINALIZED | SUCCESS |
| trader1 register_trader 50 GEN | `0xa6c85dc39ea24f9962b2556fdd78f5a161d296ff4d6d3cbb8ee14b1fb6e2a40c` | FINALIZED | SUCCESS |
| trader2 register_trader 50 GEN | `0x214f03ba45958f2592336a330c2a1bf2376a08dda1b087507dd01f7cb02e2e29` | FINALIZED | SUCCESS |
| trader1 submit_track_record | `0x3fcef73928c3bf89bce2c443bb7369a240a6c8bdd0001c81ddb70856cb4e1683` | FINALIZED | SUCCESS |
| trader1 audit_record | `0x6ef1b4ecebbef0eda3f68d6e84fdc80c50519aa25e1a2754291e8c962f5e7677` | FINALIZED | SUCCESS |
| follower follow_trader 100 GEN | `0x3dfd843ae17dc6ca52511a4ce82f669284b992d20f1f336b800805e053d99ad6` | FINALIZED | SUCCESS |
| follower copy_position +50 GEN | `0xfcdca67ca6f3eb3b1409267b5789535564dd679459921fe5fd37c165de71ac6a` | FINALIZED | SUCCESS |
| follower settle_copy +30 GEN PnL | `0xeaefc4aaf9ba664b1cd4ad908b99a3761557e4e17a3e696004bd4aa32208e0fb` | FINALIZED | SUCCESS |
| trader2 submit_track_record (thin) | `0xcc48f8c8f149b93ce1a435e041775b66af1b56936f53781bedf723f594d64082` | FINALIZED | SUCCESS |
| trader2 audit_record | `0xc354ed78bcdb4142b67dc584e431ef1e07933679591aa6e5ded7c8ebe5ed50e8` | FINALIZED | SUCCESS |
| trader2 appeal | `0x25dd27138ad114e3d31aa2d84623a688d1505e3048a2d2185e05fce35b3ac3ab` | FINALIZED | SUCCESS |
| trader2 adjudicate_appeal | `0x8ffe60c8c9e5e134a40a40a7d155e37f43e4256d7579230c10f35ed8cf1eda04` | FINALIZED | SUCCESS |
| follower dispute_fake record 1 | `0x83a97721f5328c6e19d7964c9865815f0d1f7d5b97162ee8937cddf7487dc154` | FINALIZED | SUCCESS |
| follower audit_dispute record 1 | `0x5eb7ec54ab647a8215eb4eac0d344da3094b561d3261777741d0037f577a2a03` | FINALIZED | SUCCESS |

## Final read-back (after all transactions)

- Record 1 (Ava Chen): `VERIFIED`, verdict `VERIFIED|STRONG_EVIDENCE`; disputed once and re-audited `VERIFIED|STRONG_EVIDENCE`, badge stays `VERIFIED`.
- Record 2 (Ben Okafor): first verdict `REJECTED|THIN_EVIDENCE` (stake slashed 10 GEN into the pool); appeal with a complete trade log adjudicated `VERIFIED|STRONG_EVIDENCE`, badge `VERIFIED`.
- Copy 1: principal 150 GEN (100 follow + 50 added copy), realized PnL +30 GEN, `SETTLED`; trader share 6 GEN (20%), follower return 174 GEN (principal + 80% of profit).
- Trader 1 (Ava Chen): reputation 1120, stake 50 GEN, followers 1, copy PnL +30 GEN, badge `VERIFIED`.
- Trader 2 (Ben Okafor): reputation 950, stake 40 GEN, followers 0, badge `VERIFIED`.
- Platform pool: 10 GEN. Balances: trader 1 956 GEN, trader 2 950 GEN, follower 1024 GEN.

## Superseded deployment

This deployment is not the deliverable contract. It is recorded here rather than deleted.

- `0x9a4D3074C7D053E7e88a9a1F3F3272aD396E2930` — first live-run deployment, deploy tx `0x09328ab680b9639b4cc3505ed066e3908175bd99ee9e0ede12b69cba91ee40b2` (FINALIZED, SUCCESS). All 17 transactions of the same verification flow finalized with execution `SUCCESS` and produced the same final read-back (record 1 `VERIFIED|STRONG_EVIDENCE`, record 2 first `REJECTED|THIN_EVIDENCE` then appeal `VERIFIED|STRONG_EVIDENCE`, copy 1 settled 150 GEN principal / +30 GEN PnL / 6 GEN trader share / 174 GEN follower return, pool 10 GEN). Superseded because the deployed source contained an internal cross-project reference in a code comment; the comment was removed and the contract redeployed as `0x7a611A569a0668E992c438Bc0384657A493Ec3c8` with the identical flow re-run.
