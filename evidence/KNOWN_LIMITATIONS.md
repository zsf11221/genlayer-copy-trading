# Known limitations

Scope and range statements for this contract. These describe what the contract does and does not cover.

- Nominal TEST units. All GEN in this contract is a nominal in-contract TEST ledger (`claim_test_gen` credits 1,000 GEN once per address). Staking, follow principal, payment, refund and slashing move ledger entries only; no real GEN is transferred by this contract.
- Track-record evidence is the stored evidence text. Validators judge the evidence text stored on-chain at submission time: they re-derive the win rate from wins and trades and check the total PnL against the listed trade lines. The source description is a statement supplied by the trader; the contract does not fetch any linked page itself.
- Copy settlement uses a caller-supplied realized PnL. `settle_copy` takes the realized PnL of the copy period as an input (bounded to 200% of principal) and splits it deterministically: 20% of a profit to the trader, the rest plus principal to the follower; losses are borne by the follower. The contract enforces the split; it does not independently observe market prices.
- No wall-clock deadlines. The contract has no clock source. Stale follows and pending records end only through explicit calls (`settle_copy`, `appeal`, `dispute_fake`).
- Script accounts only. The live run used temporary script-generated accounts.
- LLM verdicts are consensus decisions. Audit verdicts are produced by validators independently running the same prompt on the same stored evidence and agreeing on the decision token (`VERIFIED` / `REJECTED`). They are judgments about whether the evidence is internally consistent and complete, not deterministic measurements.
- Runner version. The contract pins runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`. The linter may report a newer runner is available; the deployed contract was verified against the pinned runner.
