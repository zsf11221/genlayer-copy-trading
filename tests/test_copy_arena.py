"""Direct-mode tests for contracts/copy_arena.py (no simulator, no network).

LLM calls are mocked with direct_vm.mock_llm; the consensus validator is
exercised explicitly with direct_vm.run_validator().

Money is microGEN (1 GEN = 1_000_000 microGEN), stored as strings.
"""

import pytest

CONTRACT = "contracts/copy_arena.py"

GEN = 1_000_000
CLAIM = 1_000 * GEN
STAKE = 50 * GEN

# Consistent evidence: trades 10, wins 7, win_rate_bp 7000 = 7*10000//10.
# Line-item PnLs sum to 5_000_000 microGEN = total_pnl_microgen.
GOOD_EVIDENCE = (
    "Track record for trader Alice Chen, spot trading on Binance, "
    "period 2026-09-01 to 2026-10-31. trades: 10, wins: 7, losses: 3, "
    "win_rate_bp: 7000, total_pnl_microgen: 5000000. Representative trades: "
    "1) BTC long +2000000 microGEN; 2) ETH long +1500000 microGEN; "
    "3) SOL short +1000000 microGEN; 4) ARB long +500000 microGEN. "
    "Source: Binance trade history export CSV, statement ID STMT-2026-1042, "
    "verified against exchange account 8F3K2."
)

THIN_EVIDENCE = (
    "I am a great trader, trust me, I win a lot and make big money always."
)

GOOD_APPEAL_EVIDENCE = (
    "Appeal: corrected statement attached. trades: 10, wins: 7, losses: 3, "
    "win_rate_bp: 7000, total_pnl_microgen: 5000000. Representative trades: "
    "1) BTC long +2000000 microGEN; 2) ETH long +1500000 microGEN; "
    "3) SOL short +1000000 microGEN; 4) ARB long +500000 microGEN. "
    "Source: Binance trade history export CSV, statement ID STMT-2026-1042, "
    "audited by a third-party accountant, report ACC-77."
)


def _hex(addr):
    return addr.as_hex if hasattr(addr, "as_hex") else "0x" + bytes(addr).hex()


@pytest.fixture
def arena(direct_deploy):
    return direct_deploy(CONTRACT)


def _claim(direct_vm, contract, who):
    direct_vm.sender = who
    return contract.claim_test_gen()


def _register(direct_vm, contract, trader, name="Alice Chen", stake=STAKE):
    direct_vm.sender = trader
    return contract.register_trader(name, str(stake))


def _verified_trader(direct_vm, contract, trader, mock="VERIFIED|CONSISTENT"):
    """Claim, register, submit a record and audit it to VERIFIED."""
    owner = direct_vm.sender
    _claim(direct_vm, contract, trader)
    _register(direct_vm, contract, trader)
    direct_vm.sender = trader
    record_id = contract.submit_track_record(GOOD_EVIDENCE)
    direct_vm.mock_llm("audit a trader", mock)
    assert contract.audit_record(record_id) == mock
    assert direct_vm.run_validator() is True
    direct_vm.sender = owner
    return record_id


def _mock_verdict(direct_vm, verdict):
    direct_vm.mock_llm("audit a trader", verdict)


def _trader(direct_vm, contract, trader):
    return contract.get_trader(_hex(trader))


# ------------------------------------------------------------ claim / register
def test_claim_twice_reverts(direct_vm, arena):
    owner = direct_vm.sender
    assert _claim(direct_vm, arena, owner) == str(CLAIM)
    assert arena.get_balance(_hex(owner)) == str(CLAIM)
    with direct_vm.expect_revert("already claimed"):
        _claim(direct_vm, arena, owner)


def test_register_stake_too_low(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("at least 20 GEN"):
        arena.register_trader("Alice Chen", str(19 * GEN))
    assert arena.register_trader("Alice Chen", str(STAKE)) == str(STAKE)
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["stake"] == str(STAKE)
    assert trader["reputation"] == "1000"
    assert trader["badge"] == "NONE"
    assert trader["followers"] == "0"
    assert trader["copy_pnl"] == "0"
    assert arena.get_balance(_hex(direct_alice)) == str(CLAIM - STAKE)


def test_register_requires_balance(direct_vm, arena, direct_alice):
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Insufficient GEN"):
        arena.register_trader("Alice Chen", str(STAKE))


def test_submit_record_requires_registration(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Only a registered trader"):
        arena.submit_track_record(GOOD_EVIDENCE)


def test_submit_record_length_guards(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("50 to 3000"):
        arena.submit_track_record("too short")
    record_id = arena.submit_track_record(GOOD_EVIDENCE)
    assert record_id == "1"
    record = arena.get_record("1")
    assert record["status"] == "PENDING"
    assert record["trader"].lower() == _hex(direct_alice).lower()
    assert arena.get_next_record_id() == "2"


# ------------------------------------------------------------ audit happy path
def test_audit_verified_badge_and_reputation(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(GOOD_EVIDENCE)
    _mock_verdict(direct_vm, "VERIFIED|STRONG_EVIDENCE")
    verdict = arena.audit_record(record_id)
    assert verdict == "VERIFIED|STRONG_EVIDENCE"
    assert direct_vm.run_validator() is True
    record = arena.get_record(record_id)
    assert record["status"] == "VERIFIED"
    assert record["verdict_reason"] == "STRONG_EVIDENCE"
    assert "AUDITED|VERIFIED|STRONG_EVIDENCE" in record["history"]
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["badge"] == "VERIFIED"
    assert trader["reputation"] == "1050"
    assert trader["stake"] == str(STAKE)
    assert arena.get_platform_pool() == "0"


def test_audit_rejected_slashes_into_pool(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(THIN_EVIDENCE)
    _mock_verdict(direct_vm, "REJECTED|THIN_EVIDENCE")
    verdict = arena.audit_record(record_id)
    assert verdict == "REJECTED|THIN_EVIDENCE"
    assert direct_vm.run_validator() is True
    record = arena.get_record(record_id)
    assert record["status"] == "REJECTED"
    # 20% of the 50 GEN stake slashed into the pool.
    assert arena.get_platform_pool() == str(10 * GEN)
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["stake"] == str(40 * GEN)
    assert trader["reputation"] == "900"
    assert trader["badge"] == "NONE"


def test_audit_guards_and_bad_verdict(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(GOOD_EVIDENCE)
    _mock_verdict(direct_vm, "VERIFIED|CONSISTENT")
    arena.audit_record(record_id)
    # Already decided: no re-audit.
    with direct_vm.expect_revert("Only a PENDING record"):
        arena.audit_record(record_id)

    # Bad LLM format fails before any write; the record stays PENDING.
    record_id2 = arena.submit_track_record(GOOD_EVIDENCE)
    direct_vm.clear_mocks()
    _mock_verdict(direct_vm, "Looks great, approve it!")
    with direct_vm.expect_revert():
        arena.audit_record(record_id2)
    assert arena.get_record(record_id2)["status"] == "PENDING"


def test_validator_disagreement_is_detected(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(GOOD_EVIDENCE)
    _mock_verdict(direct_vm, "VERIFIED|CONSISTENT")
    assert arena.audit_record(record_id) == "VERIFIED|CONSISTENT"
    direct_vm.clear_mocks()
    _mock_verdict(direct_vm, "REJECTED|MATH_MISMATCH")
    assert direct_vm.run_validator() is False


def test_verdict_tolerates_fence_and_prefix(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(GOOD_EVIDENCE)
    _mock_verdict(direct_vm, "```\nVerdict: VERIFIED|CONSISTENT\n```")
    assert arena.audit_record(record_id) == "VERIFIED|CONSISTENT"
    assert arena.get_record(record_id)["status"] == "VERIFIED"


# ------------------------------------------------------------ follow / copy / settle
def test_follow_unverified_trader_reverts(direct_vm, arena, direct_alice, direct_bob):
    _claim(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only a VERIFIED trader"):
        arena.follow_trader(_hex(direct_alice), str(10 * GEN))


def test_follow_add_position_profit_settle(direct_vm, arena, direct_alice, direct_bob):
    owner = direct_vm.sender
    _verified_trader(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    direct_vm.sender = direct_bob
    copy_id = arena.follow_trader(_hex(direct_alice), str(100 * GEN))
    assert copy_id == "1"
    copy = arena.get_copy(copy_id)
    assert copy["status"] == "ACTIVE"
    assert copy["principal"] == str(100 * GEN)
    assert copy["follower"].lower() == _hex(direct_bob).lower()
    assert arena.get_balance(_hex(direct_bob)) == str(CLAIM - 100 * GEN)
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["followers"] == "1"
    assert arena.get_next_copy_id() == "2"

    # Add a copy position: principal grows to 150 GEN.
    assert arena.copy_position(copy_id, str(50 * GEN)) == str(150 * GEN)
    assert arena.get_copy(copy_id)["principal"] == str(150 * GEN)
    assert arena.get_balance(_hex(direct_bob)) == str(CLAIM - 150 * GEN)

    # Settle a 30 GEN profit on 150 GEN principal:
    # trader 20% = 6 GEN, follower gets 150 + 24 = 174 GEN.
    direct_vm.sender = direct_bob
    assert arena.settle_copy(copy_id, str(30 * GEN)) == "SETTLED"
    copy = arena.get_copy(copy_id)
    assert copy["status"] == "SETTLED"
    assert copy["pnl"] == str(30 * GEN)
    assert copy["trader_share"] == str(6 * GEN)
    assert copy["follower_return"] == str(174 * GEN)
    assert arena.get_balance(_hex(direct_bob)) == str(CLAIM - 150 * GEN + 174 * GEN)
    assert arena.get_balance(_hex(direct_alice)) == str(CLAIM - STAKE + 6 * GEN)
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["copy_pnl"] == str(30 * GEN)
    assert trader["reputation"] == "1070"  # 1000 + 50 audit + 20 win
    # Settling twice is refused.
    with direct_vm.expect_revert("Only an ACTIVE copy"):
        arena.settle_copy(copy_id, str(1 * GEN))
    # Adding to a settled copy is refused.
    with direct_vm.expect_revert("Only an ACTIVE copy"):
        arena.copy_position(copy_id, str(1 * GEN))
    direct_vm.sender = owner


def test_settle_loss_by_trader(direct_vm, arena, direct_alice, direct_bob):
    _verified_trader(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    direct_vm.sender = direct_bob
    copy_id = arena.follow_trader(_hex(direct_alice), str(100 * GEN))
    # The trader may settle too: a 40 GEN loss.
    # Follower gets back 100 - 40 = 60 GEN; trader gets 0.
    direct_vm.sender = direct_alice
    assert arena.settle_copy(copy_id, str(-40 * GEN)) == "SETTLED"
    copy = arena.get_copy(copy_id)
    assert copy["trader_share"] == "0"
    assert copy["follower_return"] == str(60 * GEN)
    assert arena.get_balance(_hex(direct_bob)) == str(CLAIM - 100 * GEN + 60 * GEN)
    assert arena.get_balance(_hex(direct_alice)) == str(CLAIM - STAKE)
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["copy_pnl"] == str(-40 * GEN)
    assert trader["reputation"] == "1030"  # 1000 + 50 audit - 20 loss


def test_settle_guards(direct_vm, arena, direct_alice, direct_bob):
    _verified_trader(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    direct_vm.sender = direct_bob
    copy_id = arena.follow_trader(_hex(direct_alice), str(100 * GEN))
    # |PnL| above 200% of principal is refused.
    with direct_vm.expect_revert("exceeds 200%"):
        arena.settle_copy(copy_id, str(201 * GEN))
    with direct_vm.expect_revert("exceeds 200%"):
        arena.settle_copy(copy_id, str(-201 * GEN))
    # Principal bounds on follow.
    with direct_vm.expect_revert("between 1 and 10000 GEN"):
        arena.follow_trader(_hex(direct_alice), str(GEN // 2))
    # Copy position must be the follower's own copy.
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Only the follower"):
        arena.copy_position(copy_id, str(1 * GEN))


def test_settle_third_party_reverts(direct_vm, arena, direct_alice, direct_bob):
    owner = direct_vm.sender
    _verified_trader(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    direct_vm.sender = direct_bob
    copy_id = arena.follow_trader(_hex(direct_alice), str(10 * GEN))
    direct_vm.sender = owner
    with direct_vm.expect_revert("Only the follower or the trader"):
        arena.settle_copy(copy_id, str(1 * GEN))


# ------------------------------------------------------------ appeal
def test_appeal_overturns_to_verified(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(THIN_EVIDENCE)
    _mock_verdict(direct_vm, "REJECTED|THIN_EVIDENCE")
    arena.audit_record(record_id)
    assert arena.appeal(record_id, GOOD_APPEAL_EVIDENCE) == "APPEALED"
    record = arena.get_record(record_id)
    assert record["appeal_count"] == "1"
    assert record["appeal_evidence"] == GOOD_APPEAL_EVIDENCE
    direct_vm.clear_mocks()
    _mock_verdict(direct_vm, "VERIFIED|STRONG_EVIDENCE")
    verdict = arena.adjudicate_appeal(record_id)
    assert verdict == "VERIFIED|STRONG_EVIDENCE"
    assert direct_vm.run_validator() is True
    record = arena.get_record(record_id)
    assert record["status"] == "VERIFIED"
    assert "APPEAL_ADJUDICATED|VERIFIED|STRONG_EVIDENCE" in record["history"]
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["badge"] == "VERIFIED"
    # -100 for the failed audit, +50 for the won appeal.
    assert trader["reputation"] == "950"
    # The appeal verdict is final: record is VERIFIED, so no second appeal.
    with direct_vm.expect_revert("Only a REJECTED record"):
        arena.appeal(record_id, GOOD_APPEAL_EVIDENCE)


def test_appeal_guards(direct_vm, arena, direct_alice, direct_bob):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(THIN_EVIDENCE)
    # No appeal before a verdict.
    with direct_vm.expect_revert("Only a REJECTED record"):
        arena.appeal(record_id, GOOD_APPEAL_EVIDENCE)
    _mock_verdict(direct_vm, "REJECTED|THIN_EVIDENCE")
    arena.audit_record(record_id)
    # Only the trader can appeal.
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only the record's trader"):
        arena.appeal(record_id, GOOD_APPEAL_EVIDENCE)
    direct_vm.sender = direct_alice
    arena.appeal(record_id, GOOD_APPEAL_EVIDENCE)
    # Appeal verdict stays REJECTED: final, no second appeal.
    direct_vm.clear_mocks()
    _mock_verdict(direct_vm, "REJECTED|UNVERIFIABLE")
    arena.adjudicate_appeal(record_id)
    assert arena.get_record(record_id)["status"] == "REJECTED"
    # Record is still REJECTED, so the appeal-count guard fires.
    with direct_vm.expect_revert("already been appealed"):
        arena.appeal(record_id, GOOD_APPEAL_EVIDENCE)


# ------------------------------------------------------------ dispute
def test_dispute_fake_revokes_badge_and_slashes(direct_vm, arena, direct_alice, direct_bob):
    _verified_trader(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    # Anyone may dispute a VERIFIED record.
    direct_vm.sender = direct_bob
    reason = "The Binance statement ID does not exist; the CSV was fabricated."
    assert arena.dispute_fake("1", reason) == "DISPUTED"
    record = arena.get_record("1")
    assert record["status"] == "DISPUTED"
    assert "DISPUTED|" + reason in record["history"]
    # The original VERIFIED verdict is kept in history as a witness.
    assert "AUDITED|VERIFIED|CONSISTENT" in record["history"]
    assert record["verdict"] == "VERIFIED|CONSISTENT"
    # Re-audit confirms the fake: badge revoked, stake slashed, rep -200.
    direct_vm.clear_mocks()
    _mock_verdict(direct_vm, "REJECTED|INCONSISTENT_SOURCE")
    verdict = arena.audit_dispute("1")
    assert verdict == "REJECTED|INCONSISTENT_SOURCE"
    assert direct_vm.run_validator() is True
    record = arena.get_record("1")
    assert record["status"] == "REJECTED"
    assert "DISPUTE_AUDITED|REJECTED|INCONSISTENT_SOURCE" in record["history"]
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["badge"] == "REVOKED"
    assert trader["stake"] == str(40 * GEN)  # 20% of 50 GEN slashed
    assert arena.get_platform_pool() == str(10 * GEN)
    assert trader["reputation"] == "850"  # 1000 + 50 audit - 200 dispute
    # A revoked trader can no longer be followed.
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only a VERIFIED trader"):
        arena.follow_trader(_hex(direct_alice), str(10 * GEN))


def test_dispute_cleared_restores_verified(direct_vm, arena, direct_alice, direct_bob):
    _verified_trader(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    direct_vm.sender = direct_bob
    arena.dispute_fake("1", "Suspicious numbers, please re-check this record.")
    direct_vm.clear_mocks()
    _mock_verdict(direct_vm, "VERIFIED|STRONG_EVIDENCE")
    assert arena.audit_dispute("1") == "VERIFIED|STRONG_EVIDENCE"
    record = arena.get_record("1")
    assert record["status"] == "VERIFIED"
    trader = _trader(direct_vm, arena, direct_alice)
    assert trader["badge"] == "VERIFIED"
    assert trader["reputation"] == "1100"  # 1000 + 50 audit + 50 dispute re-audit
    assert trader["stake"] == str(STAKE)
    assert arena.get_platform_pool() == "0"


def test_dispute_guards(direct_vm, arena, direct_alice, direct_bob):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(GOOD_EVIDENCE)
    # Only VERIFIED records can be disputed.
    with direct_vm.expect_revert("Only a VERIFIED record"):
        arena.dispute_fake(record_id, "This record looks fabricated to me.")
    _mock_verdict(direct_vm, "VERIFIED|CONSISTENT")
    arena.audit_record(record_id)
    # Reason too short is refused.
    with direct_vm.expect_revert("20 to 1000"):
        arena.dispute_fake(record_id, "fake!")
    # audit_dispute only works while DISPUTED.
    with direct_vm.expect_revert("Only a DISPUTED record"):
        arena.audit_dispute(record_id)


# ------------------------------------------------------------ witness / views
def test_witness_kept_after_verdict(direct_vm, arena, direct_alice):
    _claim(direct_vm, arena, direct_alice)
    _register(direct_vm, arena, direct_alice)
    direct_vm.sender = direct_alice
    record_id = arena.submit_track_record(THIN_EVIDENCE)
    _mock_verdict(direct_vm, "REJECTED|THIN_EVIDENCE")
    arena.audit_record(record_id)
    arena.submit_witness(record_id, "Follower note: the numbers never added up.")
    record = arena.get_record(record_id)
    assert record["status"] == "REJECTED"
    assert record["verdict"] == "REJECTED|THIN_EVIDENCE"
    assert "WITNESS|Follower note" in record["history"]
    # Witness notes are refused before a final verdict.
    record_id2 = arena.submit_track_record(GOOD_EVIDENCE)
    with direct_vm.expect_revert("only kept after a final verdict"):
        arena.submit_witness(record_id2, "Too early.")


def test_list_views(direct_vm, arena, direct_alice, direct_bob):
    _verified_trader(direct_vm, arena, direct_alice)
    _claim(direct_vm, arena, direct_bob)
    _register(direct_vm, arena, direct_bob)
    direct_vm.sender = direct_bob
    bob_record = arena.submit_track_record(GOOD_EVIDENCE)
    direct_vm.clear_mocks()
    _mock_verdict(direct_vm, "REJECTED|MATH_MISMATCH")
    arena.audit_record(bob_record)
    traders = arena.list_traders()
    assert [t["reputation"] for t in traders] == ["1050", "900"]
    records = arena.list_records()
    assert set(records.keys()) == {"1", "2"}
    assert records["1"]["status"] == "VERIFIED"
    assert records["2"]["status"] == "REJECTED"
    assert arena.list_copies() == []
    assert arena.get_platform_pool() == str(10 * GEN)
