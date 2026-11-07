# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""CopyArena: audited social copy trading on GenLayer Stable Studionet.

A trader stakes TEST GEN and submits a structured track record. GenLayer
validators independently audit the record's internal math (win rate vs
wins/trades, total PnL vs the sum of line-item PnLs) and its credibility;
only a consensus VERIFIED verdict earns the trader a VERIFIED badge.
Followers lock principal against a VERIFIED trader only, add copy
positions, and settle with a 20/80 profit split (trader/follower).
A rejected record can be appealed once; a verified record can be
disputed as fake and re-audited, which can revoke the badge and slash
the stake. Witness notes never change a standing verdict.

Category / mechanism / interaction / evolution (four lines):
- Category: social trading / copy trading.
- Mechanism: consensus audits a trader's claimed track record math and
  credibility; the verdict gates the badge, and the badge gates
  followers' money. Settlement splits realized PnL 20/80.
- Interaction model: trader lifecycle (claim -> stake/register ->
  submit record -> audit -> follow -> copy position -> settle), with
  appeal and fake-record dispute as second-order paths.
- Evolution state: trader reputation, badge, stake, followers and
  cumulative copy PnL, plus the platform pool, change with every audit,
  follow, settlement, appeal and dispute.

Money design (all integers, no floats anywhere):
- GEN is accounted in microGEN: 1 GEN = 1_000_000 microGEN.
- All amounts are stored as strings of integers and parsed back to int.
- GEN balances are a nominal in-contract TEST ledger.
  claim_test_gen() credits 1_000 GEN once per address; staking, copy
  principal, settlement payouts and slashing only move ledger entries.
  No real GEN is transferred by this contract.
- Minimum trader stake: 20 GEN. Follow principal: 1 GEN minimum,
  10_000 GEN maximum (total per copy, including added positions).
- On a REJECTED audit: 20% of the trader's current stake is slashed
  into the platform pool, reputation -100 (floor 0).
  On a VERIFIED audit: reputation +50 (cap 2000), badge VERIFIED.
  On a REJECTED dispute re-audit: badge REVOKED, 20% of stake slashed,
  reputation -200 (floor 0).
- Settlement: profit splits 20% to the trader, 80% to the follower
  (follower gets principal + 80% of profit); a loss is borne fully by
  the follower (principal + PnL, PnL negative), trader gets 0.
  Reputation: profit +20, loss -20 (floor 0, cap 2000).
  |realized PnL| may not exceed 200% of the copy principal.
- Reputation starts at 1000, floor 0, cap 2000.

Consensus (audit_record / adjudicate_appeal / audit_dispute):
- The leader asks an LLM to judge the stored track-record evidence
  and return exactly one line: "VERIFIED|<CODE>" or
  "REJECTED|<CODE>", where <CODE> is one of a fixed set of reason
  codes. Each validator independently re-runs the same prompt on the
  same stored evidence. Consensus requires strict equality on the
  DECISION token only (VERIFIED vs REJECTED): that token is what
  changes state. The reason code is leader-provided metadata and may
  legitimately differ between models; a code difference alone must
  not veto an agreed decision (B4 lesson).
- Any failure (empty evidence, unparsable verdict, consensus
  disagreement) raises before any write, so the record stays in its
  pre-audit status (PENDING / APPEALED / DISPUTED) and can be retried.
- A decided record can never be re-audited. An appeal is allowed
  exactly once, only after a REJECTED verdict, and the appeal verdict
  is final. A dispute re-audit is final for that dispute.
- New evidence submitted after a final verdict is kept as a witness
  entry in the record history while the standing verdict stays
  untouched.

No clock source:
- There is no wall-clock deadline anywhere in this contract. Copies
  are settled only by an explicit settle_copy call from the follower
  or the trader.
"""

from dataclasses import dataclass

from genlayer import *

# ---------------------------------------------------------------- units
MICRO_PER_GEN = 1_000_000

CLAIM_AMOUNT = 1_000 * MICRO_PER_GEN  # 1000 GEN test credit, once per address
MIN_STAKE = 20 * MICRO_PER_GEN  # 20 GEN minimum trader stake
MIN_PRINCIPAL = 1 * MICRO_PER_GEN  # 1 GEN minimum follow principal
MAX_PRINCIPAL = 10_000 * MICRO_PER_GEN  # 10_000 GEN maximum principal per copy

SLASH_BP = 2000  # 20% of stake slashed on a rejected audit / dispute
TRADER_SHARE_BP = 2000  # 20% of profit goes to the trader
MAX_PNL_BP_OF_PRINCIPAL = 20000  # |realized PnL| <= 200% of principal

REPUTATION_START = 1000
REPUTATION_MAX = 2000
REPUTATION_AUDIT_PASS_DELTA = 50
REPUTATION_AUDIT_FAIL_DELTA = 100
REPUTATION_DISPUTE_FAIL_DELTA = 200
REPUTATION_SETTLE_WIN_DELTA = 20
REPUTATION_SETTLE_LOSS_DELTA = 20

MIN_EVIDENCE_LEN = 50
MAX_EVIDENCE_LEN = 3000
MIN_NAME_LEN = 1
MAX_NAME_LEN = 100
MIN_REASON_LEN = 20
MAX_REASON_LEN = 1000
MAX_TEXT_LEN = 3000

BADGE_NONE = "NONE"
BADGE_VERIFIED = "VERIFIED"
BADGE_REVOKED = "REVOKED"

STATUS_PENDING = "PENDING"
STATUS_VERIFIED = "VERIFIED"
STATUS_REJECTED = "REJECTED"
STATUS_APPEALED = "APPEALED"
STATUS_DISPUTED = "DISPUTED"

COPY_ACTIVE = "ACTIVE"
COPY_SETTLED = "SETTLED"

VERIFIED_CODES = ("CONSISTENT", "STRONG_EVIDENCE")
REJECTED_CODES = (
    "MATH_MISMATCH",
    "THIN_EVIDENCE",
    "INCONSISTENT_SOURCE",
    "UNVERIFIABLE",
)


@allow_storage
@dataclass
class Trader:
    address: str
    name: str
    stake: str
    reputation: str
    followers: str
    copy_pnl: str
    badge: str


@allow_storage
@dataclass
class Record:
    id: str
    trader: str
    evidence: str
    status: str
    verdict: str
    verdict_reason: str
    history: str
    appeal_count: str
    appeal_evidence: str


@allow_storage
@dataclass
class Copy:
    id: str
    trader: str
    follower: str
    principal: str
    status: str
    pnl: str
    trader_share: str
    follower_return: str


def _parse_int(value: str, what: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        raise gl.vm.UserError("[EXPECTED] " + what + " must be a string integer, got: " + str(value))


def _parse_verdict(raw: str) -> str:
    """Normalize raw LLM output to the strict verdict string.

    Only "VERIFIED|<CODE>" / "REJECTED|<CODE>" with a code from the
    fixed sets is accepted. Anything else is an LLM error: raise
    before writing. Markdown fences and a leading "Verdict:" label
    are stripped first, because models sometimes add them despite
    being told not to.
    """
    if not isinstance(raw, str):
        raise gl.vm.UserError("[LLM_ERROR] Verdict is not a string")
    lines = []
    for line in raw.strip().split("\n"):
        stripped = line.strip()
        if stripped in ("```", "```json"):
            continue
        if stripped != "":
            lines.append(stripped)
    if len(lines) == 0:
        raise gl.vm.UserError("[LLM_ERROR] Verdict is empty")
    line = lines[0]
    if line.lower().startswith("verdict:"):
        line = line[len("verdict:"):].strip()
    parts = line.split("|")
    if len(parts) != 2:
        raise gl.vm.UserError("[LLM_ERROR] Verdict must be DECISION|CODE, got: " + line[:120])
    decision = parts[0].strip().upper()
    code = parts[1].strip().upper()
    if decision == "VERIFIED" and code in VERIFIED_CODES:
        return "VERIFIED|" + code
    if decision == "REJECTED" and code in REJECTED_CODES:
        return "REJECTED|" + code
    raise gl.vm.UserError("[LLM_ERROR] Unknown verdict: " + line[:120])


def _verdict_decision(verdict: str) -> str:
    return verdict.split("|")[0]


def _audit_prompt(evidence: str, extra_evidence: str) -> str:
    prompt = (
        "You audit a trader's claimed track record for a copy-trading arena. "
        "Judge ONLY the evidence below; do not use outside knowledge.\n"
        "Track record evidence:\n" + evidence + "\n"
    )
    if extra_evidence.strip() != "":
        prompt = prompt + "Additional evidence submitted on appeal:\n" + extra_evidence + "\n"
    prompt = prompt + (
        "The evidence must state: total trades, wins, win_rate_bp (win rate in "
        "basis points), total_pnl_microgen, at least one representative trade "
        "line with its own pnl value, and a source description.\n"
        "How to judge:\n"
        "1. Check the math: win_rate_bp should equal wins*10000//trades "
        "(allow +-50bp rounding). total_pnl_microgen should equal the sum of "
        "the line-item pnl values (allow +-1 percent). If the numbers do not "
        "add up, REJECT with MATH_MISMATCH.\n"
        "2. REJECT with THIN_EVIDENCE if the evidence is generic, empty of "
        "substance, or has no representative trade lines or no source.\n"
        "3. REJECT with INCONSISTENT_SOURCE if the source description "
        "contradicts the numbers or is self-contradictory.\n"
        "4. REJECT with UNVERIFIABLE if the claims cannot be checked from "
        "what is given.\n"
        "5. VERIFY with CONSISTENT when the math checks out and the evidence "
        "is complete and credible; VERIFY with STRONG_EVIDENCE when it is "
        "also detailed and well sourced.\n"
        "Reply with EXACTLY ONE LINE and nothing else, no markdown, no extra words:\n"
        "VERIFIED|CONSISTENT or VERIFIED|STRONG_EVIDENCE or "
        "REJECTED|MATH_MISMATCH or REJECTED|THIN_EVIDENCE or "
        "REJECTED|INCONSISTENT_SOURCE or REJECTED|UNVERIFIABLE"
    )
    return prompt


class CopyArena(gl.Contract):
    traders: TreeMap[Address, Trader]
    records: TreeMap[str, Record]
    copies: TreeMap[str, Copy]
    next_record_id: str
    next_copy_id: str
    gen_balances: TreeMap[Address, str]
    claimed: TreeMap[Address, str]
    platform_pool: str

    def __init__(self):
        self.next_record_id = "1"
        self.next_copy_id = "1"
        self.platform_pool = "0"

    # ------------------------------------------------------------ helpers
    def _get_trader(self, address: Address) -> Trader:
        if address not in self.traders:
            raise gl.vm.UserError("[EXPECTED] Unknown trader: " + address.as_hex)
        return self.traders[address]

    def _get_record(self, record_id: str) -> Record:
        if record_id not in self.records:
            raise gl.vm.UserError("[EXPECTED] Unknown record: " + record_id)
        return self.records[record_id]

    def _save_record(self, record: Record) -> None:
        self.records[record.id] = record

    def _get_copy(self, copy_id: str) -> Copy:
        if copy_id not in self.copies:
            raise gl.vm.UserError("[EXPECTED] Unknown copy: " + copy_id)
        return self.copies[copy_id]

    def _save_copy(self, copy: Copy) -> None:
        self.copies[copy.id] = copy

    def _gen_balance_of(self, address: Address) -> int:
        return _parse_int(self.gen_balances.get(address, "0"), "GEN balance")

    def _set_gen_balance(self, address: Address, amount: int) -> None:
        if amount < 0:
            raise gl.vm.UserError("[EXPECTED] GEN balance cannot be negative")
        self.gen_balances[address] = str(amount)

    def _slash_stake(self, trader_address: Address, trader: Trader) -> None:
        """Slash 20% of the trader's current stake into the platform pool."""
        stake = _parse_int(trader.stake, "stake")
        slash = stake * SLASH_BP // 10000
        trader.stake = str(stake - slash)
        self.platform_pool = str(_parse_int(self.platform_pool, "platform pool") + slash)

    def _run_consensus(self, prompt: str) -> str:
        def leader_fn():
            raw = gl.nondet.exec_prompt(prompt)
            return _parse_verdict(raw)

        def validator_fn(leaders_res):
            # Strict equality applies to the DECISION token: it is what
            # changes state. Reason codes may differ between models.
            # Never raise: under run_nondet_unsafe any validator error
            # counts as Disagree, so failures are explicit False votes.
            try:
                if not isinstance(leaders_res, gl.vm.Return):
                    # Leader errored: agree only if we fail the same way.
                    try:
                        leader_fn()
                    except gl.vm.UserError as e:
                        leader_msg = leaders_res.message if hasattr(leaders_res, "message") else ""
                        mine_msg = e.message if hasattr(e, "message") else str(e)
                        return mine_msg == leader_msg
                    except Exception:
                        return False
                    return False
                mine = leader_fn()
                return _verdict_decision(mine) == _verdict_decision(leaders_res.calldata)
            except Exception:
                return False

        return gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

    def _apply_verdict(
        self, record: Record, verdict: str, *, is_appeal: bool, is_dispute: bool
    ) -> None:
        """Write a consensus verdict's effects. Called only after the
        consensus has agreed, so no failure path here writes state."""
        decision, code = verdict.split("|")
        trader_address = Address(record.trader)
        trader = self._get_trader(trader_address)
        record.verdict = verdict
        record.verdict_reason = code
        if is_dispute:
            record.history = record.history + "\nDISPUTE_AUDITED|" + verdict
        elif is_appeal:
            record.history = record.history + "\nAPPEAL_ADJUDICATED|" + verdict
        else:
            record.history = record.history + "\nAUDITED|" + verdict
        rep = _parse_int(trader.reputation, "reputation")
        if decision == "VERIFIED":
            record.status = STATUS_VERIFIED
            if trader.badge in (BADGE_NONE, BADGE_REVOKED):
                trader.badge = BADGE_VERIFIED
            trader.reputation = str(min(REPUTATION_MAX, rep + REPUTATION_AUDIT_PASS_DELTA))
        else:
            record.status = STATUS_REJECTED
            if is_dispute:
                trader.badge = BADGE_REVOKED
                trader.reputation = str(max(0, rep - REPUTATION_DISPUTE_FAIL_DELTA))
            else:
                trader.reputation = str(max(0, rep - REPUTATION_AUDIT_FAIL_DELTA))
            self._slash_stake(trader_address, trader)
        self.traders[trader_address] = trader
        self._save_record(record)

    def _trader_dict(self, trader: Trader) -> dict:
        return {
            "address": trader.address,
            "name": trader.name,
            "stake": trader.stake,
            "reputation": trader.reputation,
            "followers": trader.followers,
            "copy_pnl": trader.copy_pnl,
            "badge": trader.badge,
        }

    def _record_dict(self, record: Record) -> dict:
        return {
            "id": record.id,
            "trader": record.trader,
            "evidence": record.evidence,
            "status": record.status,
            "verdict": record.verdict,
            "verdict_reason": record.verdict_reason,
            "history": record.history,
            "appeal_count": record.appeal_count,
            "appeal_evidence": record.appeal_evidence,
        }

    def _copy_dict(self, copy: Copy) -> dict:
        return {
            "id": copy.id,
            "trader": copy.trader,
            "follower": copy.follower,
            "principal": copy.principal,
            "status": copy.status,
            "pnl": copy.pnl,
            "trader_share": copy.trader_share,
            "follower_return": copy.follower_return,
        }

    # ------------------------------------------------------------ test GEN
    @gl.public.write
    def claim_test_gen(self) -> str:
        sender = gl.message.sender_address
        if self.claimed.get(sender, "0") == "1":
            raise gl.vm.UserError("[EXPECTED] Test GEN already claimed by this address")
        self.claimed[sender] = "1"
        self._set_gen_balance(sender, self._gen_balance_of(sender) + CLAIM_AMOUNT)
        return str(CLAIM_AMOUNT)

    # ------------------------------------------------------------ traders
    @gl.public.write
    def register_trader(self, name: str, stake: str) -> str:
        if len(name) < MIN_NAME_LEN or len(name) > MAX_NAME_LEN:
            raise gl.vm.UserError("[EXPECTED] Trader name must be 1 to 100 characters")
        stake_amount = _parse_int(stake, "stake")
        if stake_amount < MIN_STAKE:
            raise gl.vm.UserError("[EXPECTED] Stake must be at least 20 GEN")
        sender = gl.message.sender_address
        if self._gen_balance_of(sender) < stake_amount:
            raise gl.vm.UserError("[EXPECTED] Insufficient GEN balance for stake")
        self._set_gen_balance(sender, self._gen_balance_of(sender) - stake_amount)
        if sender in self.traders:
            # Re-registration tops up the stake; reputation, followers,
            # copy PnL and badge are kept.
            trader = self.traders[sender]
            trader.name = name
            trader.stake = str(_parse_int(trader.stake, "stake") + stake_amount)
            self.traders[sender] = trader
        else:
            self.traders[sender] = Trader(
                address=sender.as_hex,
                name=name,
                stake=str(stake_amount),
                reputation=str(REPUTATION_START),
                followers="0",
                copy_pnl="0",
                badge=BADGE_NONE,
            )
        return self.traders[sender].stake

    # ------------------------------------------------------------ records
    @gl.public.write
    def submit_track_record(self, evidence: str) -> str:
        sender = gl.message.sender_address
        if sender not in self.traders:
            raise gl.vm.UserError("[EXPECTED] Only a registered trader can submit a track record")
        if len(evidence) < MIN_EVIDENCE_LEN or len(evidence) > MAX_EVIDENCE_LEN:
            raise gl.vm.UserError("[EXPECTED] Evidence must be 50 to 3000 characters")
        record_id = self.next_record_id
        self.next_record_id = str(int(record_id) + 1)
        record = Record(
            id=record_id,
            trader=sender.as_hex,
            evidence=evidence,
            status=STATUS_PENDING,
            verdict="",
            verdict_reason="",
            history="SUBMITTED",
            appeal_count="0",
            appeal_evidence="",
        )
        self.records[record_id] = record
        return record_id

    @gl.public.write
    def audit_record(self, record_id: str) -> str:
        record = self._get_record(record_id)
        if record.status != STATUS_PENDING:
            raise gl.vm.UserError("[EXPECTED] Only a PENDING record can be audited: " + record.status)
        if record.evidence.strip() == "":
            raise gl.vm.UserError("[EXPECTED] Evidence is empty, cannot audit")
        prompt = _audit_prompt(record.evidence, "")
        verdict = self._run_consensus(prompt)
        # Consensus reached. Only now, after agreement, write the outcome.
        self._apply_verdict(record, verdict, is_appeal=False, is_dispute=False)
        return verdict

    @gl.public.write
    def appeal(self, record_id: str, new_evidence: str) -> str:
        record = self._get_record(record_id)
        if record.status != STATUS_REJECTED:
            raise gl.vm.UserError("[EXPECTED] Only a REJECTED record can be appealed: " + record.status)
        sender = gl.message.sender_address
        if record.trader != sender.as_hex:
            raise gl.vm.UserError("[EXPECTED] Only the record's trader can appeal it")
        if _parse_int(record.appeal_count, "appeal count") >= 1:
            raise gl.vm.UserError("[EXPECTED] This record has already been appealed once")
        if len(new_evidence) < MIN_EVIDENCE_LEN or len(new_evidence) > MAX_EVIDENCE_LEN:
            raise gl.vm.UserError("[EXPECTED] Appeal evidence must be 50 to 3000 characters")
        record.appeal_evidence = new_evidence
        record.appeal_count = "1"
        record.status = STATUS_APPEALED
        record.history = record.history + "\nAPPEAL_SUBMITTED"
        self._save_record(record)
        return record.status

    @gl.public.write
    def adjudicate_appeal(self, record_id: str) -> str:
        record = self._get_record(record_id)
        if record.status != STATUS_APPEALED:
            raise gl.vm.UserError("[EXPECTED] Only an APPEALED record can be re-audited: " + record.status)
        if record.evidence.strip() == "":
            raise gl.vm.UserError("[EXPECTED] Evidence is empty, cannot audit")
        prompt = _audit_prompt(record.evidence, record.appeal_evidence)
        verdict = self._run_consensus(prompt)
        # Consensus reached; the appeal verdict is final.
        self._apply_verdict(record, verdict, is_appeal=True, is_dispute=False)
        return verdict

    @gl.public.write
    def dispute_fake(self, record_id: str, reason: str) -> str:
        record = self._get_record(record_id)
        if record.status != STATUS_VERIFIED:
            raise gl.vm.UserError("[EXPECTED] Only a VERIFIED record can be disputed: " + record.status)
        if len(reason) < MIN_REASON_LEN or len(reason) > MAX_REASON_LEN:
            raise gl.vm.UserError("[EXPECTED] Dispute reason must be 20 to 1000 characters")
        record.status = STATUS_DISPUTED
        # The original VERIFIED verdict stays in history as a witness;
        # it is never deleted.
        record.history = record.history + "\nDISPUTED|" + reason
        self._save_record(record)
        return record.status

    @gl.public.write
    def audit_dispute(self, record_id: str) -> str:
        record = self._get_record(record_id)
        if record.status != STATUS_DISPUTED:
            raise gl.vm.UserError("[EXPECTED] Only a DISPUTED record can be re-audited: " + record.status)
        if record.evidence.strip() == "":
            raise gl.vm.UserError("[EXPECTED] Evidence is empty, cannot audit")
        prompt = _audit_prompt(record.evidence, record.appeal_evidence)
        verdict = self._run_consensus(prompt)
        # Consensus reached; the dispute verdict is final for this dispute.
        self._apply_verdict(record, verdict, is_appeal=False, is_dispute=True)
        return verdict

    @gl.public.write
    def submit_witness(self, record_id: str, note: str) -> str:
        """Attach a note after a final verdict. The standing verdict is
        never changed; the note is kept as a witness entry only."""
        if note.strip() == "" or len(note) > MAX_TEXT_LEN:
            raise gl.vm.UserError("[EXPECTED] Witness note must be non-empty and at most 3000 characters")
        record = self._get_record(record_id)
        if record.status not in (STATUS_VERIFIED, STATUS_REJECTED):
            raise gl.vm.UserError("[EXPECTED] Witness notes are only kept after a final verdict: " + record.status)
        record.history = record.history + "\nWITNESS|" + note
        self._save_record(record)
        return record.status

    # ------------------------------------------------------------ copying
    @gl.public.write
    def follow_trader(self, trader_address: str, principal: str) -> str:
        principal_amount = _parse_int(principal, "principal")
        if principal_amount < MIN_PRINCIPAL or principal_amount > MAX_PRINCIPAL:
            raise gl.vm.UserError("[EXPECTED] Principal must be between 1 and 10000 GEN")
        trader = self._get_trader(Address(trader_address))
        if trader.badge != BADGE_VERIFIED:
            raise gl.vm.UserError("[EXPECTED] Only a VERIFIED trader can be followed")
        sender = gl.message.sender_address
        if self._gen_balance_of(sender) < principal_amount:
            raise gl.vm.UserError("[EXPECTED] Insufficient GEN balance for copy principal")
        self._set_gen_balance(sender, self._gen_balance_of(sender) - principal_amount)
        copy_id = self.next_copy_id
        self.next_copy_id = str(int(copy_id) + 1)
        copy = Copy(
            id=copy_id,
            trader=trader.address,
            follower=sender.as_hex,
            principal=str(principal_amount),
            status=COPY_ACTIVE,
            pnl="0",
            trader_share="0",
            follower_return="0",
        )
        self.copies[copy_id] = copy
        trader.followers = str(_parse_int(trader.followers, "followers") + 1)
        self.traders[Address(trader_address)] = trader
        return copy_id

    @gl.public.write
    def copy_position(self, copy_id: str, amount: str) -> str:
        amount_int = _parse_int(amount, "amount")
        if amount_int <= 0:
            raise gl.vm.UserError("[EXPECTED] Copy amount must be positive")
        copy = self._get_copy(copy_id)
        if copy.status != COPY_ACTIVE:
            raise gl.vm.UserError("[EXPECTED] Only an ACTIVE copy can add a position: " + copy.status)
        sender = gl.message.sender_address
        if copy.follower != sender.as_hex:
            raise gl.vm.UserError("[EXPECTED] Only the follower can add to this copy")
        new_principal = _parse_int(copy.principal, "principal") + amount_int
        if new_principal > MAX_PRINCIPAL:
            raise gl.vm.UserError("[EXPECTED] Total principal must not exceed 10000 GEN")
        if self._gen_balance_of(sender) < amount_int:
            raise gl.vm.UserError("[EXPECTED] Insufficient GEN balance for copy amount")
        self._set_gen_balance(sender, self._gen_balance_of(sender) - amount_int)
        copy.principal = str(new_principal)
        self._save_copy(copy)
        return copy.principal

    @gl.public.write
    def settle_copy(self, copy_id: str, realized_pnl_microgen: str) -> str:
        copy = self._get_copy(copy_id)
        if copy.status != COPY_ACTIVE:
            raise gl.vm.UserError("[EXPECTED] Only an ACTIVE copy can be settled: " + copy.status)
        sender = gl.message.sender_address
        if sender.as_hex not in (copy.follower, copy.trader):
            raise gl.vm.UserError("[EXPECTED] Only the follower or the trader can settle this copy")
        pnl = _parse_int(realized_pnl_microgen, "realized pnl")
        principal = _parse_int(copy.principal, "principal")
        max_pnl = principal * MAX_PNL_BP_OF_PRINCIPAL // 10000
        if pnl < -max_pnl or pnl > max_pnl:
            raise gl.vm.UserError("[EXPECTED] Realized PnL exceeds 200% of principal")
        trader_address = Address(copy.trader)
        follower_address = Address(copy.follower)
        trader = self._get_trader(trader_address)
        rep = _parse_int(trader.reputation, "reputation")
        if pnl > 0:
            trader_share = pnl * TRADER_SHARE_BP // 10000
            follower_return = principal + pnl - trader_share
            trader.reputation = str(min(REPUTATION_MAX, rep + REPUTATION_SETTLE_WIN_DELTA))
        elif pnl < 0:
            trader_share = 0
            follower_return = principal + pnl
            trader.reputation = str(max(0, rep - REPUTATION_SETTLE_LOSS_DELTA))
        else:
            trader_share = 0
            follower_return = principal
        self._set_gen_balance(follower_address, self._gen_balance_of(follower_address) + follower_return)
        if trader_share > 0:
            self._set_gen_balance(trader_address, self._gen_balance_of(trader_address) + trader_share)
        trader.copy_pnl = str(_parse_int(trader.copy_pnl, "copy pnl") + pnl)
        self.traders[trader_address] = trader
        copy.pnl = str(pnl)
        copy.trader_share = str(trader_share)
        copy.follower_return = str(follower_return)
        copy.status = COPY_SETTLED
        self._save_copy(copy)
        return copy.status

    # ------------------------------------------------------------ views
    @gl.public.view
    def get_trader(self, address: str) -> dict:
        return self._trader_dict(self._get_trader(Address(address)))

    @gl.public.view
    def list_traders(self) -> list:
        rows = []
        for _addr, trader in self.traders.items():
            rows.append(self._trader_dict(trader))
        rows.sort(key=lambda r: int(r["reputation"]), reverse=True)
        return rows

    @gl.public.view
    def get_record(self, record_id: str) -> dict:
        return self._record_dict(self._get_record(record_id))

    @gl.public.view
    def list_records(self) -> dict:
        out = {}
        total = int(self.next_record_id)
        for n in range(1, total):
            record_id = str(n)
            if record_id in self.records:
                out[record_id] = self._record_dict(self.records[record_id])
        return out

    @gl.public.view
    def get_copy(self, copy_id: str) -> dict:
        return self._copy_dict(self._get_copy(copy_id))

    @gl.public.view
    def list_copies(self) -> list:
        out = []
        total = int(self.next_copy_id)
        for n in range(1, total):
            copy_id = str(n)
            if copy_id in self.copies:
                out.append(self._copy_dict(self.copies[copy_id]))
        return out

    @gl.public.view
    def get_balance(self, address: str) -> str:
        return str(self._gen_balance_of(Address(address)))

    @gl.public.view
    def get_platform_pool(self) -> str:
        return self.platform_pool

    @gl.public.view
    def get_next_record_id(self) -> str:
        return self.next_record_id

    @gl.public.view
    def get_next_copy_id(self) -> str:
        return self.next_copy_id
