"""Deterministic, offline-only PACE manifest and ledger primitives.

This module deliberately contains no provider imports, credential access, or
network behavior.  Cap reservations are deferred to micro-step 2B.
"""
import json
import hashlib
import math
import multiprocessing
import os
import re
import sqlite3
import sys
import uuid


PACE_ALPHA = 0.005
PACE_LAMBDA = 0.5
PACE_MIN_DISCORDANT = 16
PACE_MAX_UNITS = 24
HYPOTHESIS_IDS = tuple("H%02d" % number for number in range(1, 11))
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManifestValidationError(ValueError):
    pass


class CapReservationError(RuntimeError):
    pass


def _require(condition, message):
    if not condition:
        raise ManifestValidationError(message)


def _hashes(value, name):
    _require(isinstance(value, dict) and value, "%s must be a non-empty hash map" % name)
    _require(all(isinstance(item, str) and _SHA256.match(item) for item in value.values()),
             "%s values must be sha256 hashes" % name)


def validate_pace_manifest(manifest):
    """Fail closed unless the frozen manifest has exactly the ten PACE trials."""
    _require(isinstance(manifest, dict), "manifest must be an object")
    _require(manifest.get("schema") == "pace_manifest.v1", "wrong manifest schema")
    _require(isinstance(manifest.get("manifest_hash"), str) and
             _SHA256.match(manifest["manifest_hash"]), "manifest_hash must be sha256")
    _require(manifest.get("alpha") == PACE_ALPHA, "alpha must be .005")
    _require(manifest.get("lambda") == PACE_LAMBDA, "lambda must be .5")
    _require(manifest.get("min_discordant") == PACE_MIN_DISCORDANT,
             "min_discordant must be 16")
    _require(manifest.get("max_pace_units") == PACE_MAX_UNITS,
             "max_pace_units must be 24")
    hypotheses = manifest.get("hypotheses")
    _require(isinstance(hypotheses, list) and len(hypotheses) == len(HYPOTHESIS_IDS),
             "manifest must contain exactly H01-H10")
    ids = [item.get("hypothesis_id") for item in hypotheses if isinstance(item, dict)]
    _require(len(ids) == len(HYPOTHESIS_IDS) and set(ids) == set(HYPOTHESIS_IDS),
             "hypotheses must be exactly H01-H10")
    for item in hypotheses:
        hypothesis_id = item["hypothesis_id"]
        _require(bool(item.get("incumbent_policy_class")), "%s lacks incumbent" % hypothesis_id)
        _require(bool(item.get("challenger_policy_class")), "%s lacks challenger" % hypothesis_id)
        endpoint = "receipt_interpretation_success" if hypothesis_id in ("H09", "H10") else "case_success"
        _require(item.get("scalar_endpoint") == endpoint, "%s has wrong endpoint" % hypothesis_id)
        _require(bool(item.get("held_out_effect_threshold")), "%s lacks held-out threshold" % hypothesis_id)
        evaluation = item.get("evaluation_case_ids")
        held_out = item.get("held_out_case_ids")
        _require(isinstance(evaluation, list) and len(evaluation) == 24 and
                 len(set(evaluation)) == 24 and all(isinstance(case, str) and case for case in evaluation),
                 "%s requires 24 distinct evaluation case IDs" % hypothesis_id)
        _require(isinstance(held_out, list) and len(held_out) == 12 and
                 len(set(held_out)) == 12 and all(isinstance(case, str) and case for case in held_out),
                 "%s requires 12 distinct held-out case IDs" % hypothesis_id)
        _require(not set(evaluation).intersection(held_out),
                 "%s evaluation and held-out cases overlap" % hypothesis_id)
        _hashes(item.get("case_hashes"), "%s case_hashes" % hypothesis_id)
        _hashes(item.get("fixture_hashes"), "%s fixture_hashes" % hypothesis_id)
        _require(isinstance(item.get("oracle_hash"), str) and _SHA256.match(item["oracle_hash"]),
                 "%s oracle_hash must be sha256" % hypothesis_id)
    return manifest


class PaceLedger(object):
    """Persist one immutable PACE observation per distinct frozen case ID."""

    def __init__(self, path, manifest):
        self.manifest = validate_pace_manifest(manifest)
        self.hypotheses = {item["hypothesis_id"]: item for item in manifest["hypotheses"]}
        self.connection = sqlite3.connect(path)
        self.connection.execute("""CREATE TABLE IF NOT EXISTS pace_pairs (
            hypothesis_id TEXT NOT NULL, case_id TEXT NOT NULL,
            incumbent_endpoint INTEGER NOT NULL, challenger_endpoint INTEGER NOT NULL,
            outcome TEXT NOT NULL, wealth_before REAL NOT NULL, wealth_after REAL NOT NULL,
            fixture_hashes TEXT NOT NULL, repeat_refs TEXT NOT NULL,
            PRIMARY KEY (hypothesis_id, case_id))""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS pace_terminal (
            hypothesis_id TEXT PRIMARY KEY, status TEXT NOT NULL, reason TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS held_out_pairs (
            hypothesis_id TEXT NOT NULL, case_id TEXT NOT NULL,
            incumbent_endpoint INTEGER NOT NULL, challenger_endpoint INTEGER NOT NULL,
            outcome TEXT NOT NULL, fixture_hashes TEXT NOT NULL,
            PRIMARY KEY (hypothesis_id, case_id))""")
        self.connection.commit()

    def _hypothesis(self, hypothesis_id):
        if hypothesis_id not in self.hypotheses:
            raise ManifestValidationError("unknown hypothesis %r" % hypothesis_id)
        return self.hypotheses[hypothesis_id]

    def record_pair(self, hypothesis_id, case_id, incumbent_endpoint, challenger_endpoint,
                    fixture_hashes, reliability_repeat_refs=None):
        hypothesis = self._hypothesis(hypothesis_id)
        if case_id not in hypothesis["evaluation_case_ids"]:
            raise ManifestValidationError("case is not a frozen PACE evaluation case")
        if incumbent_endpoint not in (0, 1) or challenger_endpoint not in (0, 1):
            raise ValueError("endpoints must be binary")
        terminal = self.connection.execute("SELECT 1 FROM pace_terminal WHERE hypothesis_id=?",
                                           (hypothesis_id,)).fetchone()
        if terminal:
            raise RuntimeError("hypothesis has already reached a terminal state")
        existing = self.connection.execute("SELECT wealth_after, repeat_refs FROM pace_pairs "
                                           "WHERE hypothesis_id=? AND case_id=?",
                                           (hypothesis_id, case_id)).fetchone()
        refs = list(reliability_repeat_refs or [])
        if existing:
            stored = json.loads(existing[1])
            merged = stored + [ref for ref in refs if ref not in stored]
            self.connection.execute("UPDATE pace_pairs SET repeat_refs=? WHERE hypothesis_id=? AND case_id=?",
                                    (json.dumps(merged, sort_keys=True), hypothesis_id, case_id))
            self.connection.commit()
            return {"created": False, "wealth_after": existing[0], "repeat_refs": merged}
        previous = self.connection.execute("SELECT wealth_after FROM pace_pairs WHERE hypothesis_id=? "
                                           "ORDER BY rowid DESC LIMIT 1", (hypothesis_id,)).fetchone()
        wealth_before = previous[0] if previous else 1.0
        outcome = "win" if challenger_endpoint > incumbent_endpoint else (
            "loss" if challenger_endpoint < incumbent_endpoint else "tie")
        wealth_after = wealth_before * (1.5 if outcome == "win" else 0.5 if outcome == "loss" else 1.0)
        self.connection.execute("INSERT INTO pace_pairs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (hypothesis_id, case_id, incumbent_endpoint, challenger_endpoint, outcome,
                                 wealth_before, wealth_after, json.dumps(fixture_hashes, sort_keys=True),
                                 json.dumps(refs, sort_keys=True)))
        self.connection.commit()
        return {"created": True, "outcome": outcome, "wealth_before": wealth_before,
                "wealth_after": wealth_after, "repeat_refs": refs}

    def row_count(self, hypothesis_id):
        self._hypothesis(hypothesis_id)
        return self.connection.execute("SELECT COUNT(*) FROM pace_pairs WHERE hypothesis_id=?",
                                       (hypothesis_id,)).fetchone()[0]

    def record_held_out_pair(self, hypothesis_id, case_id, incumbent_endpoint,
                             challenger_endpoint, fixture_hashes):
        """Persist confirmation evidence without changing PACE wealth."""
        hypothesis = self._hypothesis(hypothesis_id)
        if case_id not in hypothesis["held_out_case_ids"]:
            raise ManifestValidationError("case is not a frozen held-out case")
        if incumbent_endpoint not in (0, 1) or challenger_endpoint not in (0, 1):
            raise ValueError("endpoints must be binary")
        existing = self.connection.execute(
            "SELECT outcome FROM held_out_pairs WHERE hypothesis_id=? AND case_id=?",
            (hypothesis_id, case_id),
        ).fetchone()
        if existing:
            return {"created": False, "outcome": existing[0]}
        outcome = "win" if challenger_endpoint > incumbent_endpoint else (
            "loss" if challenger_endpoint < incumbent_endpoint else "tie")
        self.connection.execute(
            "INSERT INTO held_out_pairs VALUES (?, ?, ?, ?, ?, ?)",
            (hypothesis_id, case_id, incumbent_endpoint, challenger_endpoint,
             outcome, json.dumps(fixture_hashes, sort_keys=True)),
        )
        self.connection.commit()
        return {"created": True, "outcome": outcome}

    def held_out_row_count(self, hypothesis_id):
        self._hypothesis(hypothesis_id)
        return self.connection.execute(
            "SELECT COUNT(*) FROM held_out_pairs WHERE hypothesis_id=?",
            (hypothesis_id,),
        ).fetchone()[0]

    def kill(self, hypothesis_id, reason):
        """Persist a terminal KILL before PACE acceptance or later case execution."""
        self._hypothesis(hypothesis_id)
        if not isinstance(reason, str) or not reason:
            raise ValueError("terminal KILL reason is required")
        existing = self.connection.execute(
            "SELECT status, reason FROM pace_terminal WHERE hypothesis_id=?",
            (hypothesis_id,),
        ).fetchone()
        if existing:
            if existing[0] != "KILL":
                self.connection.execute(
                    "UPDATE pace_terminal SET status='KILL', reason=? WHERE hypothesis_id=?",
                    (reason, hypothesis_id),
                )
                self.connection.commit()
                return {"status": "KILL", "reason": reason,
                        "router_recommendation": None}
            return {"status": existing[0], "reason": existing[1],
                    "router_recommendation": None}
        self.connection.execute(
            "INSERT INTO pace_terminal VALUES (?, 'KILL', ?)",
            (hypothesis_id, reason),
        )
        self.connection.commit()
        return {"status": "KILL", "reason": reason,
                "router_recommendation": None}

    def finalize(self, hypothesis_id, terminal_reason=None, execution_mode="deterministic_offline"):
        self._hypothesis(hypothesis_id)
        existing = self.connection.execute("SELECT status, reason FROM pace_terminal WHERE hypothesis_id=?",
                                           (hypothesis_id,)).fetchone()
        if existing:
            return {"status": existing[0], "reason": existing[1], "router_recommendation": None}
        if terminal_reason:
            return self.kill(hypothesis_id, terminal_reason)
        else:
            rows = self.connection.execute("SELECT outcome, wealth_after FROM pace_pairs "
                                           "WHERE hypothesis_id=? ORDER BY rowid", (hypothesis_id,)).fetchall()
            discordant = sum(row[0] != "tie" for row in rows)
            wealth = rows[-1][1] if rows else 1.0
            if discordant < PACE_MIN_DISCORDANT:
                status, reason = "NO_PROMOTION", "too few discordant paired outcomes"
            elif wealth < 1.0 / PACE_ALPHA:
                status, reason = "NO_PROMOTION", "PACE budget exhausted"
            elif execution_mode in ("deterministic_offline", "synthetic_test"):
                status, reason = "NO_PROMOTION", "%s evidence cannot promote provider routing" % execution_mode
            else:
                status, reason = "NO_PROMOTION", "human promotion and held-out confirmation required"
        self.connection.execute("INSERT OR REPLACE INTO pace_terminal VALUES (?, ?, ?)",
                                (hypothesis_id, status, reason))
        self.connection.commit()
        return {"status": status, "reason": reason, "router_recommendation": None}


class CapLedger(object):
    """Durable, fail-closed capacity reservations for real-provider attempts.

    A reservation remains charged until a matching reconciliation or an auditable
    cancellation.  This module does not perform the network attempt itself; the
    caller must claim the returned reservation before making one.
    """

    _KEY_FIELDS = (
        "approval_hash", "manifest_hash", "hypothesis_id", "attempt_id",
        "dispatch_id", "retry_attempt", "idempotency_key",
    )
    _CHARGED_STATES = ("RESERVED", "NETWORK_IN_FLIGHT", "PENDING_RECONCILIATION", "RECONCILED")

    def __init__(self, path, caps=None, timeout_seconds=1.0):
        if not isinstance(path, str) or not path:
            raise CapReservationError("ledger path must be a non-empty string")
        if timeout_seconds <= 0:
            raise CapReservationError("timeout_seconds must be positive")
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._initialize(caps)

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=self.timeout_seconds)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _canonical_json(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _validate_amounts(cls, amounts, label, required_fields=None):
        if not isinstance(amounts, dict) or not amounts:
            raise CapReservationError("%s must be a non-empty object" % label)
        if required_fields is not None and set(amounts) != set(required_fields):
            raise CapReservationError("%s dimensions must exactly match configured caps" % label)
        normalized = {}
        for field, value in amounts.items():
            if not isinstance(field, str) or not field:
                raise CapReservationError("%s has an invalid capacity field" % label)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CapReservationError("%s.%s must be numeric" % (label, field))
            if not math.isfinite(value) or value < 0:
                raise CapReservationError("%s.%s must be finite and non-negative" % (label, field))
            normalized[field] = value
        return normalized

    @classmethod
    def _normalize_key(cls, key):
        if not isinstance(key, dict) or set(key) != set(cls._KEY_FIELDS):
            raise CapReservationError("reservation key must contain exactly the required fields")
        normalized = {}
        for field in cls._KEY_FIELDS:
            value = key[field]
            if field == "retry_attempt":
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise CapReservationError("retry_attempt must be a non-negative integer")
            elif not isinstance(value, str) or not value:
                raise CapReservationError("reservation key field %s must be non-empty" % field)
            normalized[field] = value
        return normalized

    @classmethod
    def _reservation_key(cls, key):
        return hashlib.sha256(cls._canonical_json(key).encode("utf-8")).hexdigest()

    @classmethod
    def _chain_key(cls, key):
        chain = {field: key[field] for field in cls._KEY_FIELDS
                 if field not in ("retry_attempt", "idempotency_key")}
        return hashlib.sha256(cls._canonical_json(chain).encode("utf-8")).hexdigest()

    def _initialize(self, caps):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE IF NOT EXISTS cap_ledger_config (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1), caps_json TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS cap_retry_chains (
                chain_key TEXT PRIMARY KEY, owner TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS cap_reservations (
                reservation_id TEXT PRIMARY KEY, reservation_key TEXT NOT NULL UNIQUE,
                chain_key TEXT NOT NULL, approval_hash TEXT NOT NULL, manifest_hash TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL, attempt_id TEXT NOT NULL, dispatch_id TEXT NOT NULL,
                retry_attempt INTEGER NOT NULL, idempotency_key TEXT NOT NULL,
                owner TEXT NOT NULL, requested_json TEXT NOT NULL, charged_json TEXT NOT NULL,
                state TEXT NOT NULL, raw_observation_id TEXT, cancellation_id TEXT,
                UNIQUE (chain_key, retry_attempt))""")
            stored = connection.execute("SELECT caps_json FROM cap_ledger_config WHERE singleton=1").fetchone()
            if stored is None:
                normalized = self._validate_amounts(caps, "caps")
                connection.execute("INSERT INTO cap_ledger_config VALUES (1, ?)",
                                   (self._canonical_json(normalized),))
                self.caps = normalized
            else:
                self.caps = json.loads(stored["caps_json"])
                self._validate_amounts(self.caps, "stored caps")
                if caps is not None:
                    supplied = self._validate_amounts(caps, "caps")
                    if supplied != self.caps:
                        raise CapReservationError("ledger already exists with different caps")
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise CapReservationError("could not initialize cap ledger") from exc
        finally:
            connection.close()

    @staticmethod
    def _as_dict(row, fields):
        return {field: row[field] for field in fields}

    def _row_response(self, row):
        return {
            "reservation_id": row["reservation_id"], "owner": row["owner"],
            "state": row["state"], "requested": json.loads(row["requested_json"]),
            "charged": json.loads(row["charged_json"]),
            "network_called": False,
        }

    def _charged_totals(self, connection):
        totals = {field: 0 for field in self.caps}
        rows = connection.execute("SELECT charged_json FROM cap_reservations WHERE state IN (%s)" %
                                  ",".join("?" for _ in self._CHARGED_STATES),
                                  self._CHARGED_STATES).fetchall()
        for row in rows:
            for field, value in json.loads(row["charged_json"]).items():
                totals[field] += value
        return totals

    def reserve(self, key, requested):
        """Atomically reserve conservative capacity before exactly one network attempt."""
        key = self._normalize_key(key)
        requested = self._validate_amounts(requested, "requested", self.caps)
        reservation_key = self._reservation_key(key)
        chain_key = self._chain_key(key)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM cap_reservations WHERE reservation_key=?",
                                          (reservation_key,)).fetchone()
            if existing is not None:
                if json.loads(existing["requested_json"]) != requested:
                    raise CapReservationError("duplicate idempotency key has different reservation")
                connection.commit()
                return self._row_response(existing)

            chain = connection.execute("SELECT owner FROM cap_retry_chains WHERE chain_key=?",
                                       (chain_key,)).fetchone()
            if key["retry_attempt"] == 0:
                if chain is not None:
                    raise CapReservationError("ambiguous retry-chain ownership")
                owner = uuid.uuid4().hex
                connection.execute("INSERT INTO cap_retry_chains VALUES (?, ?)", (chain_key, owner))
            else:
                if chain is None:
                    raise CapReservationError("retry has no original reservation owner")
                predecessor = connection.execute(
                    "SELECT 1 FROM cap_reservations WHERE chain_key=? AND retry_attempt=?",
                    (chain_key, key["retry_attempt"] - 1)).fetchone()
                if predecessor is None:
                    raise CapReservationError("retry must follow the preceding reservation")
                owner = chain["owner"]
            same_retry = connection.execute(
                "SELECT 1 FROM cap_reservations WHERE chain_key=? AND retry_attempt=?",
                (chain_key, key["retry_attempt"])).fetchone()
            if same_retry is not None:
                raise CapReservationError("retry attempt already has a reservation")

            totals = self._charged_totals(connection)
            if any(totals[field] + requested[field] > self.caps[field] for field in self.caps):
                raise CapReservationError("cap exhausted")
            reservation_id = uuid.uuid4().hex
            values = self._as_dict(key, self._KEY_FIELDS)
            connection.execute("""INSERT INTO cap_reservations (
                reservation_id, reservation_key, chain_key, approval_hash, manifest_hash,
                hypothesis_id, attempt_id, dispatch_id, retry_attempt, idempotency_key,
                owner, requested_json, charged_json, state, raw_observation_id, cancellation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESERVED', NULL, NULL)""",
                (reservation_id, reservation_key, chain_key, values["approval_hash"], values["manifest_hash"],
                 values["hypothesis_id"], values["attempt_id"], values["dispatch_id"],
                 values["retry_attempt"], values["idempotency_key"], owner,
                 self._canonical_json(requested), self._canonical_json(requested)))
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            connection.commit()
            return self._row_response(row)
        except CapReservationError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise CapReservationError("cap reservation blocked by ledger failure") from exc
        finally:
            connection.close()

    def retry_owner(self, key):
        key = self._normalize_key(key)
        connection = self._connect()
        try:
            row = connection.execute("SELECT owner FROM cap_retry_chains WHERE chain_key=?",
                                     (self._chain_key(key),)).fetchone()
            if row is None:
                raise CapReservationError("retry chain has no owner")
            return row["owner"]
        finally:
            connection.close()

    def claim_network_attempt(self, reservation_id, owner):
        """Grant the sole owner permission to make the already-reserved call once."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            if row is None or row["owner"] != owner or row["state"] != "RESERVED":
                raise CapReservationError("reservation is not eligible for a network attempt")
            if row["retry_attempt"]:
                predecessor = connection.execute(
                    "SELECT state FROM cap_reservations WHERE chain_key=? AND retry_attempt=?",
                    (row["chain_key"], row["retry_attempt"] - 1)).fetchone()
                if predecessor is None or predecessor["state"] not in ("RECONCILED", "CANCELLED"):
                    raise CapReservationError("retry cannot claim a network attempt before its predecessor is terminal")
            connection.execute("UPDATE cap_reservations SET state='NETWORK_IN_FLIGHT' WHERE reservation_id=?",
                               (reservation_id,))
            connection.commit()
            return True
        except CapReservationError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise CapReservationError("network claim blocked by ledger failure") from exc
        finally:
            connection.close()

    def mark_crashed(self, reservation_id):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            if row is None:
                raise CapReservationError("unknown reservation")
            if row["state"] not in ("RESERVED", "NETWORK_IN_FLIGHT", "PENDING_RECONCILIATION"):
                raise CapReservationError("reservation cannot be marked crashed")
            connection.execute("UPDATE cap_reservations SET state='PENDING_RECONCILIATION' WHERE reservation_id=?",
                               (reservation_id,))
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            connection.commit()
            return self._row_response(row)
        except CapReservationError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise CapReservationError("crash state blocked by ledger failure") from exc
        finally:
            connection.close()

    def reconcile(self, reservation_id, raw_observation_id, actual=None):
        """Settle at most the reserved amounts; repeated identical calls cannot credit twice."""
        if not isinstance(raw_observation_id, str) or not raw_observation_id:
            raise CapReservationError("raw_observation_id is required for reconciliation")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            if row is None:
                raise CapReservationError("unknown reservation")
            reserved = json.loads(row["requested_json"])
            actual = reserved if actual is None else self._validate_amounts(actual, "actual", self.caps)
            if any(actual[field] > reserved[field] for field in self.caps):
                raise CapReservationError("actual usage exceeds conservative reservation")
            if row["state"] == "RECONCILED":
                if row["raw_observation_id"] != raw_observation_id or json.loads(row["charged_json"]) != actual:
                    raise CapReservationError("reconciliation does not match the recorded settlement")
                connection.commit()
                return self._row_response(row)
            if row["state"] not in ("RESERVED", "NETWORK_IN_FLIGHT", "PENDING_RECONCILIATION"):
                raise CapReservationError("reservation cannot be reconciled")
            connection.execute("UPDATE cap_reservations SET state='RECONCILED', charged_json=?, raw_observation_id=? "
                               "WHERE reservation_id=?",
                               (self._canonical_json(actual), raw_observation_id, reservation_id))
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            connection.commit()
            return self._row_response(row)
        except CapReservationError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise CapReservationError("reconciliation blocked by ledger failure") from exc
        finally:
            connection.close()

    def cancel(self, reservation_id, cancellation_id):
        """Release a reservation only through an auditable terminal cancellation."""
        if not isinstance(cancellation_id, str) or not cancellation_id:
            raise CapReservationError("cancellation_id is required")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            if row is None:
                raise CapReservationError("unknown reservation")
            if row["state"] == "CANCELLED":
                if row["cancellation_id"] != cancellation_id:
                    raise CapReservationError("cancellation does not match recorded cancellation")
                connection.commit()
                return self._row_response(row)
            if row["state"] not in ("RESERVED", "PENDING_RECONCILIATION"):
                raise CapReservationError("reservation cannot be cancelled")
            cleared = {field: 0 for field in self.caps}
            connection.execute("UPDATE cap_reservations SET state='CANCELLED', charged_json=?, cancellation_id=? "
                               "WHERE reservation_id=?",
                               (self._canonical_json(cleared), cancellation_id, reservation_id))
            row = connection.execute("SELECT * FROM cap_reservations WHERE reservation_id=?",
                                     (reservation_id,)).fetchone()
            connection.commit()
            return self._row_response(row)
        except CapReservationError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise CapReservationError("cancellation blocked by ledger failure") from exc
        finally:
            connection.close()

    def remaining(self):
        connection = self._connect()
        try:
            totals = self._charged_totals(connection)
            return {field: self.caps[field] - totals[field] for field in self.caps}
        finally:
            connection.close()


def _reserve_final_unit_worker(path, key, requested, queue):
    try:
        reservation = CapLedger(path).reserve(key, requested)
        queue.put({"state": reservation["state"], "network_called": False,
                   "reservation_id": reservation["reservation_id"]})
    except CapReservationError:
        queue.put({"state": "BLOCKED_CAP", "network_called": False})


def reserve_final_unit_concurrently(path, keys, requested):
    """Exercise final-unit contention without invoking a provider or network client."""
    if not isinstance(keys, (list, tuple)) or len(keys) != 2:
        raise CapReservationError("final-unit contention requires exactly two keys")
    context = multiprocessing.get_context("fork" if os.name != "nt" else "spawn")
    queue = context.Queue()
    processes = [context.Process(target=_reserve_final_unit_worker,
                                 args=(path, key, requested, queue)) for key in keys]
    for process in processes:
        process.start()
    outcomes = [queue.get() for _ in processes]
    for process in processes:
        process.join()
        if process.exitcode != 0:
            raise CapReservationError("cap contender process failed")
    return outcomes


def compatibility_report(required_shared):
    """Report only the interpreter executing this call; absent versions remain open."""
    required = ["%d.%d" % tuple(version) for version in required_shared]
    current = "%d.%d" % sys.version_info[:2]
    executed = [current] if current in required else []
    return {"required_versions": required, "executed_versions": executed,
            "verified_versions": list(executed),
            "missing_versions": [version for version in required if version not in executed]}
