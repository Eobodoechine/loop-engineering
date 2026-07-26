"""
P1: Transactional state machine for Cost of Delay (COD) operationalization.

Protected SQLite state machine for plan-check transition authorization.
Implements S5.1-S5.7 of the COD operationalization spec.

Exempt from the no-DB-in-hooks rule per spec S5.
"""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── S5.2: Schema v1 (literal from spec) ──────────────────────────────
SCHEMA_V1 = """
CREATE TABLE meta (schema_version INTEGER NOT NULL CHECK(schema_version=1));

CREATE TABLE families (
  family_id TEXT PRIMARY KEY,
  canonical_spec_path TEXT NOT NULL,
  root_spec_sha256 TEXT NOT NULL CHECK(length(root_spec_sha256)=64),
  tip_generation INTEGER NOT NULL CHECK(tip_generation>=0),
  tip_spec_sha256 TEXT NOT NULL CHECK(length(tip_spec_sha256)=64),
  next_logical_round INTEGER NOT NULL CHECK(next_logical_round>=1),
  state TEXT NOT NULL CHECK(state IN ('ACTIVE','SUPERSEDED')),
  created_at_ns INTEGER NOT NULL );

CREATE UNIQUE INDEX one_active_family_per_path
  ON families(canonical_spec_path) WHERE state='ACTIVE';

CREATE TABLE generations (
  family_id TEXT NOT NULL REFERENCES families(family_id),
  generation INTEGER NOT NULL CHECK(generation>=0),
  spec_sha256 TEXT NOT NULL CHECK(length(spec_sha256)=64),
  parent_spec_sha256 TEXT,
  cod TEXT NOT NULL CHECK(cod IN ('HIGH','MEDIUM','LOW')),
  cod_reason TEXT NOT NULL CHECK(length(trim(cod_reason))>0),
  change_kind TEXT NOT NULL CHECK(change_kind IN
    ('REGISTER','TARGETED','REWRITE','CUT','COD_CHANGE')),
  registered_event_id TEXT NOT NULL UNIQUE,
  PRIMARY KEY(family_id,generation),
  UNIQUE(family_id,spec_sha256) );

CREATE TABLE rounds (
  round_id TEXT PRIMARY KEY,
  family_id TEXT NOT NULL,
  generation INTEGER NOT NULL,
  spec_sha256 TEXT NOT NULL,
  logical_round INTEGER NOT NULL CHECK(logical_round>=1),
  expected_lenses_json TEXT NOT NULL,
  expected_lenses_sha256 TEXT NOT NULL CHECK(length(expected_lenses_sha256)=64),
  state TEXT NOT NULL CHECK(state IN ('OPEN','AWAITING_RESULTS','RETRYABLE','PASS','FAIL',
    'NO_VERDICT','DECISION_REQUIRED','ASK_PENDING','ACTION_SELECTED','ACTION_CONSUMED','APPROVED')),
  opened_at_ns INTEGER NOT NULL,
  FOREIGN KEY(family_id,generation) REFERENCES generations(family_id,generation),
  UNIQUE(family_id,logical_round) );

CREATE TABLE dispatches (
  dispatch_id TEXT PRIMARY KEY,
  runtime TEXT NOT NULL CHECK(runtime IN ('claude','codex','workflow')),
  runtime_call_id TEXT NOT NULL,
  round_id TEXT NOT NULL REFERENCES rounds(round_id),
  lens_id TEXT NOT NULL,
  attempt INTEGER NOT NULL CHECK(attempt>=1),
  role_route TEXT NOT NULL,
  runtime_promoted INTEGER NOT NULL CHECK(runtime_promoted IN (0,1)),
  state TEXT NOT NULL CHECK(state IN ('REGISTERED','STARTED','VALID_PASS','EXPLICIT_FAIL',
    'INVALID','TIMED_OUT','ABANDONED')),
  result_sha256 TEXT,
  support_sha256 TEXT,
  containment_receipt_sha256 TEXT NOT NULL CHECK(length(containment_receipt_sha256)=64),
  UNIQUE(runtime,runtime_call_id),
  UNIQUE(round_id,lens_id,attempt) );

CREATE TABLE source_outcomes (
  outcome_id TEXT PRIMARY KEY,
  round_id TEXT NOT NULL REFERENCES rounds(round_id),
  prior_event_id TEXT NOT NULL UNIQUE,
  outcome_kind TEXT NOT NULL CHECK(outcome_kind IN ('PASS','FAIL','NO_VERDICT',
    'DECISION_REQUIRED','RESEARCH_REPAIR_REQUIRED','GOVERNOR_CUT_REQUIRED',
    'SATURATION_REDIRECT_REQUIRED','ASK_ANSWERED','ASK_UNANSWERED','PLAN_APPROVED')),
  oracle_module TEXT,
  oracle_input_sha256 TEXT,
  oracle_output_sha256 TEXT,
  coder_note_sha256 TEXT,
  decided_event_id TEXT NOT NULL UNIQUE );

CREATE TABLE asks (
  ask_id TEXT PRIMARY KEY,
  round_id TEXT NOT NULL UNIQUE REFERENCES rounds(round_id),
  state TEXT NOT NULL CHECK(state IN ('PENDING','ANSWERED','UNANSWERED')),
  allowed_actions_json TEXT NOT NULL,
  fallback_action TEXT NOT NULL,
  human_event_sha256 TEXT,
  created_event_id TEXT NOT NULL UNIQUE,
  resolved_event_id TEXT UNIQUE );

CREATE TABLE action_receipts (
  action_id TEXT PRIMARY KEY,
  outcome_id TEXT NOT NULL REFERENCES source_outcomes(outcome_id),
  action TEXT NOT NULL CHECK(action IN ('RETRY','REPAIR','CUT','RESEARCH_REPAIR_REQUIRED',
    'GOVERNOR_CUT_REQUIRED','SATURATION_REDIRECT_REQUIRED','PLAN_APPROVED')),
  target_generation INTEGER,
  target_spec_sha256 TEXT,
  logical_round INTEGER NOT NULL,
  lens_id TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  runtime TEXT NOT NULL,
  role_route TEXT NOT NULL,
  capability_idempotency_key TEXT NOT NULL UNIQUE,
  decision_reason TEXT NOT NULL,
  ask_id TEXT REFERENCES asks(ask_id),
  human_event_sha256 TEXT,
  state TEXT NOT NULL CHECK(state IN ('ISSUED','CONSUMED','INVALIDATED')),
  consumed_by_dispatch_id TEXT UNIQUE REFERENCES dispatches(dispatch_id),
  UNIQUE(outcome_id,logical_round,lens_id,attempt,runtime,role_route,action) );

CREATE TABLE events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  idempotency_key TEXT NOT NULL UNIQUE,
  family_id TEXT NOT NULL REFERENCES families(family_id),
  generation INTEGER NOT NULL,
  logical_round INTEGER,
  event_type TEXT NOT NULL,
  actor_origin TEXT NOT NULL CHECK(actor_origin IN ('hook','hook_policy','human')),
  scheduler_meta_json TEXT,
  wall_time_ns INTEGER NOT NULL,
  monotonic_ns INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64),
  previous_event_sha256 TEXT,
  event_sha256 TEXT NOT NULL UNIQUE CHECK(length(event_sha256)=64) );
"""


# ── Helpers ───────────────────────────────────────────────────────────

def canonical_json(obj: Any) -> str:
    """S5.1: canonical UTF-8 JSON with sorted keys, no newline."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


# ── Exception hierarchy ───────────────────────────────────────────────

class CODError(Exception):
    """Base for all COD state machine errors."""


class InvalidCODDirective(CODError):
    """Spec frontmatter missing or malformed COD directives."""


class FamilyExistsError(CODError):
    """Active family with different root bytes already exists for this path."""


class FamilyNotFoundError(CODError):
    """Family ID not found."""


class FamilyNotActiveError(CODError):
    """Family is not in ACTIVE state."""


class CASFailureError(CODError):
    """Compare-and-swap failure — stale tip or wrong parent."""


class RoundNotFoundError(CODError):
    """Round ID not found."""


class CapabilityNotFoundError(CODError):
    """Capability not found or already consumed."""


class CapabilityConsumedError(CODError):
    """Capability already consumed."""


class DispatchNotFoundError(CODError):
    """Dispatch ID not found."""


class ResultImmutableError(CODError):
    """Dispatch result is immutable — different bytes conflict."""


class ReconciliationBarrierError(CODError):
    """Expected lens set not yet satisfied."""


class InvalidTransitionError(CODError):
    """Invalid state transition."""


# ── Main state machine ────────────────────────────────────────────────

class CODState:
    """Hook-owned transactional SQLite state machine (S5.2-S5.7)."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        if not self._table_exists("meta"):
            self._init_schema()

    def _table_exists(self, name: str) -> bool:
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        )
        return cur.fetchone() is not None

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA_V1)
        self._conn.execute("INSERT INTO meta(schema_version) VALUES(1)")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── S5.3: register_family ─────────────────────────────────────────
    def register_family(
        self,
        spec_path: Path,
        spec_bytes: bytes,
        cod: str,
        cod_reason: str,
        idempotency_key: str,
    ) -> dict:
        """Register a new family. Idempotent for identical bytes."""
        canonical_path = str(spec_path.resolve())
        root_hash = sha256_hex(spec_bytes)
        assert len(cod_reason.strip()) > 0, "cod_reason must be non-empty"
        assert cod in ("HIGH", "MEDIUM", "LOW"), "cod must be HIGH/MEDIUM/LOW"

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            # Check for existing active family on this path
            cur = self._conn.execute(
                "SELECT family_id, root_spec_sha256 FROM families "
                "WHERE canonical_spec_path=? AND state='ACTIVE'",
                (canonical_path,),
            )
            row = cur.fetchone()
            if row:
                existing_id, existing_root = row
                if existing_root != root_hash:
                    raise FamilyExistsError(
                        f"Active family {existing_id} has root {existing_root}, "
                        f"not the provided {root_hash}"
                    )
                # Idempotent: same root bytes → return existing
                cur2 = self._conn.execute(
                    "SELECT tip_generation, tip_spec_sha256, state FROM families WHERE family_id=?",
                    (existing_id,),
                )
                r = cur2.fetchone()
                self._conn.execute("COMMIT")
                return {"family_id": existing_id, "generation": r[0],
                        "spec_sha256": r[1], "state": r[2]}

            family_id = uuid.uuid4().hex
            now_ns = time.time_ns()
            gen0_sha = root_hash
            ev_id = self._new_event_id()

            self._conn.execute(
                "INSERT INTO families(family_id,canonical_spec_path,root_spec_sha256,"
                "tip_generation,tip_spec_sha256,next_logical_round,state,created_at_ns)"
                "VALUES(?,?,?,0,?,1,'ACTIVE',?)",
                (family_id, canonical_path, root_hash, gen0_sha, now_ns),
            )
            gen0_event_id = self._new_event_id()
            self._conn.execute(
                "INSERT INTO generations(family_id,generation,spec_sha256,parent_spec_sha256,"
                "cod,cod_reason,change_kind,registered_event_id)"
                "VALUES(?,0,?,NULL,?,?,'REGISTER',?)",
                (family_id, gen0_sha, cod, cod_reason, gen0_event_id),
            )
            self._write_event(
                family_id=family_id, generation=0, logical_round=None,
                event_type="FAMILY_REGISTERED", actor_origin="hook",
                payload={"canonical_spec_path": canonical_path, "root_spec_sha256": root_hash},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"family_id": family_id, "generation": 0,
                    "spec_sha256": root_hash, "state": "ACTIVE"}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: advance_generation ───────────────────────────────────────
    def advance_generation(
        self,
        family_id: str,
        parent_generation: int,
        parent_spec_sha256: str,
        new_spec_bytes: bytes,
        cod: str,
        cod_reason: str,
        change_kind: str,
        consuming_action_id: str,
        idempotency_key: str,
    ) -> dict:
        """CAS-advance generation from exact tip. Invalidates prior capability."""
        new_hash = sha256_hex(new_spec_bytes)
        assert change_kind in ("TARGETED","REWRITE","CUT","COD_CHANGE"), "invalid change_kind"

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT tip_generation, tip_spec_sha256, state FROM families WHERE family_id=?",
                (family_id,),
            )
            row = cur.fetchone()
            if not row:
                raise FamilyNotFoundError(family_id)
            tip_gen, tip_hash, state = row
            if state != "ACTIVE":
                raise FamilyNotActiveError(family_id)
            if tip_gen != parent_generation or tip_hash != parent_spec_sha256:
                raise CASFailureError(
                    f"CAS fail: tip gen={tip_gen} hash={tip_hash}, "
                    f"parent gen={parent_generation} hash={parent_spec_sha256}"
                )

            new_gen = tip_gen + 1
            reg_ev_id = self._new_event_id()
            self._conn.execute(
                "INSERT INTO generations(family_id,generation,spec_sha256,parent_spec_sha256,"
                "cod,cod_reason,change_kind,registered_event_id)"
                "VALUES(?,?,?,?,?,?,?,?)",
                (family_id, new_gen, new_hash, parent_spec_sha256,
                 cod, cod_reason, change_kind, reg_ev_id),
            )
            # Consume the action receipt — verify it exists, is ISSUED, and belongs to this family
            cur2 = self._conn.execute(
                "SELECT ar.state, o.round_id, r.family_id FROM action_receipts ar "
                "JOIN source_outcomes o ON ar.outcome_id = o.outcome_id "
                "JOIN rounds r ON o.round_id = r.round_id "
                "WHERE ar.action_id=?",
                (consuming_action_id,),
            )
            receipt_row = cur2.fetchone()
            if not receipt_row:
                raise CapabilityNotFoundError(
                    f"Action receipt {consuming_action_id} not found or does not belong to family {family_id}"
                )
            receipt_state, _, receipt_family = receipt_row
            if receipt_family != family_id:
                raise CapabilityNotFoundError(
                    f"Action receipt {consuming_action_id} belongs to family {receipt_family}, not {family_id}"
                )
            if receipt_state == 'CONSUMED':
                raise CapabilityConsumedError(
                    f"Action receipt {consuming_action_id} already consumed"
                )
            if receipt_state == 'INVALIDATED':
                raise CapabilityConsumedError(
                    f"Action receipt {consuming_action_id} was invalidated (generation advance)"
                )
            if receipt_state != 'ISSUED':
                raise CapabilityConsumedError(
                    f"Action receipt {consuming_action_id} in unexpected state {receipt_state}"
                )
            self._conn.execute(
                "UPDATE action_receipts SET state='CONSUMED' WHERE action_id=? AND state='ISSUED'",
                (consuming_action_id,),
            )
            # Invalidate prior-generation receipts
            self._conn.execute(
                "UPDATE action_receipts SET state='INVALIDATED' "
                "WHERE outcome_id IN (SELECT outcome_id FROM source_outcomes WHERE round_id IN "
                "(SELECT round_id FROM rounds WHERE family_id=? AND generation<?)) "
                "AND state='ISSUED'",
                (family_id, parent_generation),
            )
            # CAS-update the tip
            self._conn.execute(
                "UPDATE families SET tip_generation=?,tip_spec_sha256=? WHERE family_id=? "
                "AND tip_generation=? AND tip_spec_sha256=?",
                (new_gen, new_hash, family_id, tip_gen, tip_hash),
            )
            self._write_event(
                family_id=family_id, generation=new_gen, logical_round=None,
                event_type="GENERATION_ADVANCED", actor_origin="hook",
                payload={"parent_generation": tip_gen, "parent_hash": tip_hash,
                         "new_hash": new_hash, "change_kind": change_kind},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"family_id": family_id, "generation": new_gen, "spec_sha256": new_hash}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: open_round ───────────────────────────────────────────────
    def open_round(
        self,
        family_id: str,
        generation: int,
        spec_sha256: str,
        expected_lens_ids: List[str],
        idempotency_key: str,
    ) -> dict:
        """Open a new logical round with a frozen, sorted, deduped lens set."""
        sorted_lenses = sorted(set(expected_lens_ids))
        assert len(sorted_lenses) > 0, "must have at least one lens"
        lenses_json = canonical_json(sorted_lenses)
        lenses_hash = sha256_hex(lenses_json.encode("utf-8"))

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT tip_generation,tip_spec_sha256,next_logical_round,state "
                "FROM families WHERE family_id=?",
                (family_id,),
            )
            row = cur.fetchone()
            if not row:
                raise FamilyNotFoundError(family_id)
            tip_gen, tip_hash, nlr, state = row
            if state != "ACTIVE":
                raise FamilyNotActiveError(family_id)
            if tip_gen != generation or tip_hash != spec_sha256:
                raise CASFailureError(
                    f"Round tip mismatch: family tip gen={tip_gen} hash={tip_hash}, "
                    f"requested gen={generation} hash={spec_sha256}"
                )

            round_id = uuid.uuid4().hex
            logical_round = nlr
            now_ns = time.time_ns()

            self._conn.execute(
                "INSERT INTO rounds(round_id,family_id,generation,spec_sha256,logical_round,"
                "expected_lenses_json,expected_lenses_sha256,state,opened_at_ns)"
                "VALUES(?,?,?,?,?,?,?,'OPEN',?)",
                (round_id, family_id, generation, spec_sha256, logical_round,
                 lenses_json, lenses_hash, now_ns),
            )
            self._conn.execute(
                "UPDATE families SET next_logical_round=next_logical_round+1 WHERE family_id=?",
                (family_id,),
            )
            self._write_event(
                family_id=family_id, generation=generation, logical_round=logical_round,
                event_type="ROUND_OPENED", actor_origin="hook",
                payload={"round_id": round_id, "expected_lenses": sorted_lenses,
                         "lenses_sha256": lenses_hash},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"round_id": round_id, "logical_round": logical_round,
                    "expected_lenses": sorted_lenses}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: register_dispatch ────────────────────────────────────────
    def register_dispatch(
        self,
        round_id: str,
        runtime: str,
        runtime_call_id: str,
        lens_id: str,
        attempt: int,
        role_route: str,
        containment_receipt_sha256: str,
        runtime_promoted: int,
        consuming_action_id: Optional[str],
        idempotency_key: str,
    ) -> dict:
        """Register a dispatch AND atomically consume its capability."""
        assert runtime in ("claude", "codex", "workflow")
        assert attempt >= 1
        assert runtime_promoted in (0, 1)

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT family_id,generation,spec_sha256,logical_round,state,"
                "expected_lenses_json FROM rounds WHERE round_id=?",
                (round_id,),
            )
            row = cur.fetchone()
            if not row:
                raise RoundNotFoundError(round_id)
            family_id, gen, spec_hash, lr, state, lenses_json = row
            if state not in ("OPEN", "RETRYABLE"):
                raise InvalidTransitionError(
                    f"Cannot register dispatch on round in state {state}"
                )

            expected_lenses = json.loads(lenses_json)
            if lens_id not in expected_lenses:
                raise InvalidTransitionError(
                    f"Lens {lens_id} not in frozen expected set {expected_lenses}"
                )

            # Check attempt succession
            cur2 = self._conn.execute(
                "SELECT MAX(attempt) FROM dispatches WHERE round_id=? AND lens_id=?",
                (round_id, lens_id),
            )
            max_att = cur2.fetchone()[0]
            if max_att is not None and attempt != max_att + 1:
                raise InvalidTransitionError(
                    f"Attempt {attempt} out of order; max existing is {max_att}"
                )

            dispatch_id = uuid.uuid4().hex

            # Consume capability if provided — verify it exists, is ISSUED, and belongs to this round's family
            if consuming_action_id:
                cur3 = self._conn.execute(
                    "SELECT ar.state, r.family_id FROM action_receipts ar "
                    "JOIN source_outcomes o ON ar.outcome_id = o.outcome_id "
                    "JOIN rounds r ON o.round_id = r.round_id "
                    "WHERE ar.action_id=? AND r.round_id=?",
                    (consuming_action_id, round_id),
                )
                receipt_row = cur3.fetchone()
                if not receipt_row:
                    raise CapabilityNotFoundError(
                        f"Action receipt {consuming_action_id} not found for round {round_id}"
                    )
                receipt_state, receipt_family = receipt_row
                if receipt_family != family_id:
                    raise CapabilityNotFoundError(
                        f"Action receipt {consuming_action_id} belongs to family {receipt_family}, not {family_id}"
                    )
                if receipt_state == 'CONSUMED':
                    raise CapabilityConsumedError(
                        f"Action receipt {consuming_action_id} already consumed"
                    )
                if receipt_state == 'INVALIDATED':
                    raise CapabilityConsumedError(
                        f"Action receipt {consuming_action_id} was invalidated (generation advance)"
                    )
                if receipt_state != 'ISSUED':
                    raise CapabilityConsumedError(
                        f"Action receipt {consuming_action_id} in unexpected state {receipt_state}"
                    )
                self._conn.execute(
                    "UPDATE action_receipts SET state='CONSUMED', "
                    "consumed_by_dispatch_id=? WHERE action_id=? AND state='ISSUED'",
                    (dispatch_id, consuming_action_id),
                )

            self._conn.execute(
                "INSERT INTO dispatches(dispatch_id,runtime,runtime_call_id,round_id,"
                "lens_id,attempt,role_route,runtime_promoted,state,containment_receipt_sha256)"
                "VALUES(?,?,?,?,?,?,?,?,'STARTED',?)",
                (dispatch_id, runtime, runtime_call_id, round_id, lens_id, attempt,
                 role_route, runtime_promoted, containment_receipt_sha256),
            )
            # Advance round to AWAITING_RESULTS
            self._conn.execute(
                "UPDATE rounds SET state='AWAITING_RESULTS' WHERE round_id=? AND state='OPEN'",
                (round_id,),
            )
            self._write_event(
                family_id=family_id, generation=gen, logical_round=lr,
                event_type="DISPATCH_STARTED", actor_origin="hook",
                payload={"dispatch_id": dispatch_id, "lens_id": lens_id,
                         "attempt": attempt, "runtime": runtime},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"dispatch_id": dispatch_id, "state": "STARTED",
                    "lens_id": lens_id, "attempt": attempt}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: record_result ────────────────────────────────────────────
    def record_result(
        self,
        dispatch_id: str,
        raw_result: str,
        result_origin: str,
        idempotency_key: str,
    ) -> dict:
        """Record a dispatch result. Immutable; same-UID replay returns SAME_UID_OBSERVED_ONLY."""
        result_hash = sha256_hex(raw_result.encode("utf-8"))

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT d.result_sha256, d.state, d.round_id, d.lens_id, d.attempt "
                "FROM dispatches d WHERE d.dispatch_id=?",
                (dispatch_id,),
            )
            row = cur.fetchone()
            if not row:
                raise DispatchNotFoundError(dispatch_id)
            existing_hash, state, round_id, lens_id, attempt = row

            if state not in ("STARTED",):
                # Already has a result
                if existing_hash == result_hash:
                    self._conn.execute("COMMIT")
                    return {"dispatch_id": dispatch_id, "state": state,
                            "note": "SAME_UID_OBSERVED_ONLY"}
                raise ResultImmutableError(
                    f"Dispatch {dispatch_id} already has result {existing_hash}, "
                    f"cannot overwrite with {result_hash}"
                )

            # Determine classification: VALID_PASS or EXPLICIT_FAIL
            new_state = "VALID_PASS" if "LOOP_GATE: PLAN_PASS" in raw_result else "EXPLICIT_FAIL"

            self._conn.execute(
                "UPDATE dispatches SET state=?, result_sha256=? WHERE dispatch_id=?",
                (new_state, result_hash, dispatch_id),
            )
            cur2 = self._conn.execute(
                "SELECT family_id,generation,logical_round FROM rounds WHERE round_id=?",
                (round_id,),
            )
            fam_id, gen, lr = cur2.fetchone()
            self._write_event(
                family_id=fam_id, generation=gen, logical_round=lr,
                event_type="DISPATCH_COMPLETED", actor_origin="hook",
                payload={"dispatch_id": dispatch_id, "state": new_state,
                         "result_sha256": result_hash, "lens_id": lens_id,
                         "attempt": attempt},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"dispatch_id": dispatch_id, "state": new_state,
                    "result_sha256": result_hash}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: reconcile_round ──────────────────────────────────────────
    def reconcile_round(self, round_id: str, idempotency_key: str) -> dict:
        """Project dispatches through the fixed expected-lens barrier."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT family_id,generation,spec_sha256,logical_round,state,"
                "expected_lenses_json FROM rounds WHERE round_id=?",
                (round_id,),
            )
            row = cur.fetchone()
            if not row:
                raise RoundNotFoundError(round_id)
            family_id, gen, spec_hash, lr, state, lenses_json = row
            if state not in ("AWAITING_RESULTS",):
                raise InvalidTransitionError(
                    f"Cannot reconcile round in state {state}"
                )

            expected_lenses = set(json.loads(lenses_json))

            cur2 = self._conn.execute(
                "SELECT lens_id,state FROM dispatches WHERE round_id=?",
                (round_id,),
            )
            disp_states = {lens: st for lens, st in cur2.fetchall()}

            effective = set(disp_states.keys())
            if effective != expected_lenses:
                missing = expected_lenses - effective
                raise ReconciliationBarrierError(
                    f"Expected lenses {sorted(expected_lenses)}, "
                    f"have {sorted(effective)}, missing {sorted(missing)}"
                )

            all_pass = all(st == "VALID_PASS" for st in disp_states.values())
            any_fail = any(st == "EXPLICIT_FAIL" for st in disp_states.values())

            if all_pass:
                outcome_kind = "PASS"
                new_round_state = "PASS"
            elif any_fail:
                outcome_kind = "FAIL"
                new_round_state = "FAIL"
            else:
                outcome_kind = "NO_VERDICT"
                new_round_state = "RETRYABLE"

            outcome_id = uuid.uuid4().hex
            prior_ev_id = self._new_event_id()
            decided_ev_id = self._new_event_id()

            self._conn.execute(
                "INSERT INTO source_outcomes(outcome_id,round_id,prior_event_id,"
                "outcome_kind,decided_event_id)"
                "VALUES(?,?,?,?,?)",
                (outcome_id, round_id, prior_ev_id, outcome_kind, decided_ev_id),
            )
            self._conn.execute(
                "UPDATE rounds SET state=? WHERE round_id=?",
                (new_round_state, round_id),
            )
            self._write_event(
                family_id=family_id, generation=gen, logical_round=lr,
                event_type="ROUND_RECONCILED", actor_origin="hook",
                payload={"round_id": round_id, "outcome_kind": outcome_kind,
                         "lens_states": disp_states},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"outcome_id": outcome_id, "outcome_kind": outcome_kind,
                    "round_state": new_round_state}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: select_action ────────────────────────────────────────────
    def select_action(
        self,
        outcome_id: str,
        oracle_evidence: dict,
        decision_reason: str,
        idempotency_key: str,
    ) -> List[dict]:
        """Mint one-use capabilities from a source-outcome. Fan-out for N-lens PASS."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT o.outcome_kind, o.round_id, r.family_id, r.generation, "
                "r.spec_sha256, r.logical_round, r.expected_lenses_json, r.state "
                "FROM source_outcomes o JOIN rounds r ON o.round_id=r.round_id "
                "WHERE o.outcome_id=?",
                (outcome_id,),
            )
            row = cur.fetchone()
            if not row:
                raise CODError(f"Outcome {outcome_id} not found")
            outcome_kind, round_id, family_id, gen, spec_hash, lr, lenses_json, rstate = row

            # Bug 4 fix: idempotent replay — if receipts already exist for this outcome, return them
            cur_existing = self._conn.execute(
                "SELECT action_id, action, lens_id, attempt, capability_idempotency_key "
                "FROM action_receipts WHERE outcome_id=? AND state='ISSUED'",
                (outcome_id,),
            )
            existing = cur_existing.fetchall()
            if existing:
                self._conn.execute("COMMIT")
                return [
                    {
                        "action_id": r[0],
                        "action": r[1],
                        "lens_id": r[2],
                        "attempt": r[3],
                        "capability_idempotency_key": r[4],
                    }
                    for r in existing
                ]

            if rstate in ("APPROVED", "ACTION_SELECTED", "ACTION_CONSUMED"):
                raise InvalidTransitionError(
                    f"Round {round_id} in state {rstate} — cannot select actions"
                )

            # Map outcome_kind → actions
            action_map = {
                "PASS": ["PLAN_APPROVED"],
                "FAIL": ["REPAIR", "CUT"],
                "NO_VERDICT": ["RETRY"],
                "DECISION_REQUIRED": ["REPAIR", "CUT"],
                "RESEARCH_REPAIR_REQUIRED": ["RESEARCH_REPAIR_REQUIRED"],
                "GOVERNOR_CUT_REQUIRED": ["GOVERNOR_CUT_REQUIRED"],
                "SATURATION_REDIRECT_REQUIRED": ["SATURATION_REDIRECT_REQUIRED"],
                "ASK_ANSWERED": ["REPAIR", "CUT"],
                "ASK_UNANSWERED": ["RETRY", "REPAIR", "CUT"],
            }
            actions = action_map.get(outcome_kind, [])
            if not actions:
                raise InvalidTransitionError(
                    f"No legal actions for outcome_kind {outcome_kind}"
                )

            receipts = []
            for action in actions:
                # For N-lens fan-out, one receipt per expected lens
                lenses = json.loads(lenses_json) if outcome_kind == "PASS" else ["generalist"]
                for lens_id in lenses:
                    attempt = 1
                    receipt_id = uuid.uuid4().hex
                    cap_key_data = {
                        "action": action, "family_id": family_id,
                        "generation": gen, "spec_sha256": spec_hash,
                        "logical_round": lr, "lens_id": lens_id,
                        "attempt": attempt, "outcome_id": outcome_id,
                    }
                    cap_key_str = canonical_json(cap_key_data)
                    cap_key = sha256_hex(cap_key_str.encode("utf-8"))

                    self._conn.execute(
                        "INSERT INTO action_receipts(action_id,outcome_id,action,"
                        "target_generation,target_spec_sha256,logical_round,lens_id,"
                        "attempt,runtime,role_route,capability_idempotency_key,"
                        "decision_reason,state)"
                        "VALUES(?,?,?,?,?,?,?,?,'claude','verifier',?,?,'ISSUED')",
                        (receipt_id, outcome_id, action, gen, spec_hash, lr,
                         lens_id, attempt, cap_key, decision_reason),
                    )
                    receipts.append({
                        "action_id": receipt_id, "action": action,
                        "lens_id": lens_id, "attempt": attempt,
                        "capability_idempotency_key": cap_key,
                    })

            # Bug 5 fix: PASS outcomes transition round to APPROVED terminal state
            if outcome_kind == "PASS":
                self._conn.execute(
                    "UPDATE rounds SET state='APPROVED' WHERE round_id=?",
                    (round_id,),
                )
            else:
                self._conn.execute(
                    "UPDATE rounds SET state='ACTION_SELECTED' WHERE round_id=?",
                    (round_id,),
                )
            self._write_event(
                family_id=family_id, generation=gen, logical_round=lr,
                event_type="ACTIONS_SELECTED", actor_origin="hook",
                payload={"outcome_id": outcome_id, "actions": actions,
                         "receipt_count": len(receipts)},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return receipts
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: consume_action ───────────────────────────────────────────
    def consume_action(self, action_id: str, idempotency_key: str) -> dict:
        """Consume a single capability receipt. Called inside register_dispatch."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT state, consumed_by_dispatch_id FROM action_receipts WHERE action_id=?",
                (action_id,),
            )
            row = cur.fetchone()
            if not row:
                raise CapabilityNotFoundError(action_id)
            st, consumed_by = row
            if st == "CONSUMED":
                raise CapabilityConsumedError(
                    f"Capability {action_id} already consumed by {consumed_by}"
                )
            if st == "INVALIDATED":
                raise CapabilityConsumedError(
                    f"Capability {action_id} was invalidated (generation advance)"
                )
            self._conn.execute(
                "UPDATE action_receipts SET state='CONSUMED' WHERE action_id=? AND state='ISSUED'",
                (action_id,),
            )
            cur2 = self._conn.execute(
                "SELECT family_id, logical_round FROM rounds r JOIN source_outcomes o "
                "ON r.round_id=o.round_id JOIN action_receipts a ON a.outcome_id=o.outcome_id "
                "WHERE a.action_id=?",
                (action_id,),
            )
            fam_id, lr = cur2.fetchone()
            self._write_event(
                family_id=fam_id, logical_round=lr, generation=0,
                event_type="CAPABILITY_CONSUMED", actor_origin="hook",
                payload={"action_id": action_id},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"action_id": action_id, "state": "CONSUMED"}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── S5.3: open_ask / resolve_ask / resolve_unanswered ──────────────
    def open_ask(
        self,
        round_id: str,
        allowed_actions: List[str],
        fallback_action: str,
        idempotency_key: str,
    ) -> dict:
        """Open a human ASK. Hook derives allowed/fallback actions from S2.1/S3.2."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT family_id,generation,logical_round,state FROM rounds WHERE round_id=?",
                (round_id,),
            )
            row = cur.fetchone()
            if not row:
                raise RoundNotFoundError(round_id)
            family_id, gen, lr, state = row
            if state not in ("DECISION_REQUIRED", "FAIL"):
                raise InvalidTransitionError(
                    f"Cannot open ask on round in state {state}"
                )

            ask_id = uuid.uuid4().hex
            created_ev_id = self._new_event_id()
            self._conn.execute(
                "INSERT INTO asks(ask_id,round_id,state,allowed_actions_json,"
                "fallback_action,created_event_id)"
                "VALUES(?,?,'PENDING',?,?,?)",
                (ask_id, round_id, canonical_json(allowed_actions),
                 fallback_action, created_ev_id),
            )
            self._conn.execute(
                "UPDATE rounds SET state='ASK_PENDING' WHERE round_id=?",
                (round_id,),
            )
            self._write_event(
                family_id=family_id, generation=gen, logical_round=lr,
                event_type="ASK_OPENED", actor_origin="hook",
                payload={"ask_id": ask_id, "allowed_actions": allowed_actions,
                         "fallback_action": fallback_action},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"ask_id": ask_id, "state": "PENDING"}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def resolve_ask(
        self,
        ask_id: str,
        trusted_transcript_event: dict,
        idempotency_key: str,
    ) -> dict:
        """Resolve an ask with a runtime-authenticated human reply (S3.1)."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT a.round_id,a.state,a.fallback_action,"
                "r.family_id,r.generation,r.logical_round "
                "FROM asks a JOIN rounds r ON a.round_id=r.round_id "
                "WHERE a.ask_id=?",
                (ask_id,),
            )
            row = cur.fetchone()
            if not row:
                raise CODError(f"Ask {ask_id} not found")
            round_id, state, fallback_action, family_id, gen, lr = row
            if state != "PENDING":
                raise InvalidTransitionError(
                    f"Cannot resolve ask {ask_id} in state {state}"
                )

            # Validate trusted transcript event (origin.kind must be "human")
            origin = trusted_transcript_event.get("origin", {})
            if origin.get("kind") != "human":
                raise InvalidTransitionError(
                    "trusted_transcript_event origin.kind must be 'human'"
                )

            human_ev_hash = sha256_hex(
                canonical_json(trusted_transcript_event).encode("utf-8")
            )
            resolved_ev_id = self._new_event_id()
            self._conn.execute(
                "UPDATE asks SET state='ANSWERED',human_event_sha256=?,"
                "resolved_event_id=? WHERE ask_id=? AND state='PENDING'",
                (human_ev_hash, resolved_ev_id, ask_id),
            )
            # Create source-outcome for ASK_ANSWERED
            outcome_id = uuid.uuid4().hex
            prior_ev_id = self._new_event_id()
            decided_ev_id = self._new_event_id()
            self._conn.execute(
                "INSERT INTO source_outcomes(outcome_id,round_id,prior_event_id,"
                "outcome_kind,decided_event_id)"
                "VALUES(?,?,?,'ASK_ANSWERED',?)",
                (outcome_id, round_id, prior_ev_id, decided_ev_id),
            )
            self._conn.execute(
                "UPDATE rounds SET state='DECISION_REQUIRED' WHERE round_id=?",
                (round_id,),
            )
            self._write_event(
                family_id=family_id, generation=gen, logical_round=lr,
                event_type="ASK_ANSWERED", actor_origin="human",
                payload={"ask_id": ask_id, "outcome_id": outcome_id},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"ask_id": ask_id, "state": "ANSWERED",
                    "outcome_id": outcome_id}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def resolve_unanswered(
        self,
        ask_id: str,
        transition_attempt: dict,
        idempotency_key: str,
    ) -> dict:
        """Resolve unanswered ask with deterministic fallback."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT a.round_id,a.state,a.fallback_action,"
                "r.family_id,r.generation,r.logical_round "
                "FROM asks a JOIN rounds r ON a.round_id=r.round_id "
                "WHERE a.ask_id=?",
                (ask_id,),
            )
            row = cur.fetchone()
            if not row:
                raise CODError(f"Ask {ask_id} not found")
            round_id, state, fallback_action, family_id, gen, lr = row

            # Bug 3 fix: reject already-answered ASKs
            if state == 'ANSWERED':
                raise InvalidTransitionError(
                    f"Ask {ask_id} is already ANSWERED, cannot resolve as unanswered"
                )

            resolved_ev_id = self._new_event_id()
            self._conn.execute(
                "UPDATE asks SET state='UNANSWERED',resolved_event_id=? WHERE ask_id=? AND state='PENDING'",
                (resolved_ev_id, ask_id),
            )
            outcome_id = uuid.uuid4().hex
            prior_ev_id = self._new_event_id()
            decided_ev_id = self._new_event_id()
            self._conn.execute(
                "INSERT INTO source_outcomes(outcome_id,round_id,prior_event_id,"
                "outcome_kind,decided_event_id)"
                "VALUES(?,?,?,'ASK_UNANSWERED',?)",
                (outcome_id, round_id, prior_ev_id, decided_ev_id),
            )
            self._conn.execute(
                "UPDATE rounds SET state='DECISION_REQUIRED' WHERE round_id=?",
                (round_id,),
            )
            # Mint fallback capability
            receipt_id = uuid.uuid4().hex
            cap_key_str = canonical_json({
                "action": fallback_action, "ask_id": ask_id,
                "outcome_id": outcome_id, "kind": "fallback",
            })
            cap_key = sha256_hex(cap_key_str.encode("utf-8"))
            self._conn.execute(
                "INSERT INTO action_receipts(action_id,outcome_id,action,"
                "target_generation,target_spec_sha256,logical_round,lens_id,"
                "attempt,runtime,role_route,capability_idempotency_key,"
                "decision_reason,state)"
                "VALUES(?,?,?,0,'',0,'generalist',1,'claude','verifier',?,"
                "'ASK_UNANSWERED fallback','ISSUED')",
                (receipt_id, outcome_id, fallback_action, cap_key),
            )
            self._write_event(
                family_id=family_id, generation=gen, logical_round=lr,
                event_type="ASK_UNANSWERED", actor_origin="hook",
                payload={"ask_id": ask_id, "outcome_id": outcome_id,
                         "fallback_action": fallback_action},
                idempotency_key=idempotency_key,
            )
            self._conn.execute("COMMIT")
            return {"ask_id": ask_id, "state": "UNANSWERED",
                    "outcome_id": outcome_id,
                    "fallback_receipt_id": receipt_id}
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── Read APIs ──────────────────────────────────────────────────────
    def get_family(self, family_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT family_id,canonical_spec_path,root_spec_sha256,tip_generation,"
            "tip_spec_sha256,next_logical_round,state,created_at_ns FROM families "
            "WHERE family_id=?",
            (family_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip(
            ["family_id","canonical_spec_path","root_spec_sha256","tip_generation",
             "tip_spec_sha256","next_logical_round","state","created_at_ns"], row))

    def get_round(self, round_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT round_id,family_id,generation,spec_sha256,logical_round,"
            "expected_lenses_json,expected_lenses_sha256,state,opened_at_ns "
            "FROM rounds WHERE round_id=?",
            (round_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(
            ["round_id","family_id","generation","spec_sha256","logical_round",
             "expected_lenses_json","expected_lenses_sha256","state","opened_at_ns"], row))
        d["expected_lenses"] = json.loads(d["expected_lenses_json"])
        return d

    def get_dispatch(self, dispatch_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT dispatch_id,runtime,runtime_call_id,round_id,lens_id,attempt,"
            "role_route,runtime_promoted,state,result_sha256,support_sha256,"
            "containment_receipt_sha256 FROM dispatches WHERE dispatch_id=?",
            (dispatch_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip(
            ["dispatch_id","runtime","runtime_call_id","round_id","lens_id","attempt",
             "role_route","runtime_promoted","state","result_sha256","support_sha256",
             "containment_receipt_sha256"], row))

    # ── Internal helpers ───────────────────────────────────────────────
    def _new_event_id(self) -> str:
        return uuid.uuid4().hex

    def _previous_event_sha256(self, family_id: str) -> Optional[str]:
        cur = self._conn.execute(
            "SELECT event_sha256 FROM events WHERE family_id=? ORDER BY seq DESC LIMIT 1",
            (family_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def _write_event(
        self,
        family_id: str,
        generation: int,
        logical_round: Optional[int],
        event_type: str,
        actor_origin: str,
        payload: Any,
        idempotency_key: str,
        scheduler_meta: Optional[dict] = None,
    ) -> str:
        event_id = self._new_event_id()
        wall_ns = time.time_ns()
        prev_hash = self._previous_event_sha256(family_id)
        payload_json_str = canonical_json(payload)
        payload_hash = sha256_hex(payload_json_str.encode("utf-8"))

        # event_sha256 chains previous_event_sha256
        chain_data = canonical_json({
            "event_id": event_id,
            "family_id": family_id,
            "generation": generation,
            "logical_round": logical_round,
            "event_type": event_type,
            "actor_origin": actor_origin,
            "wall_time_ns": wall_ns,
            "payload_sha256": payload_hash,
            "previous_event_sha256": prev_hash,
        })
        event_sha = sha256_hex(chain_data.encode("utf-8"))

        # scheduler_meta only for hook/hook_policy
        scheduler_meta_json = canonical_json(scheduler_meta) if scheduler_meta else None
        if actor_origin == "human" and scheduler_meta_json is not None:
            raise InvalidTransitionError("human actor may not carry scheduler_meta")

        self._conn.execute(
            "INSERT INTO events(event_id,idempotency_key,family_id,generation,"
            "logical_round,event_type,actor_origin,scheduler_meta_json,"
            "wall_time_ns,monotonic_ns,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256)"
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, idempotency_key, family_id, generation, logical_round,
             event_type, actor_origin, scheduler_meta_json,
             wall_ns, time.monotonic_ns(), payload_json_str, payload_hash,
             prev_hash, event_sha),
        )
        return event_id
