"""Offline WhatsApp Timeline Demonstration for Recall.

Simulates 5 synthetic messages across 6 months demonstrating:
1. Initial fact ingestion & multi-valued preference.
2. Employer transition (single-valued conflict resolution).
3. Independent fact reinforcement.
4. Historical correction with explicit valid-time/knowledge-time semantics.
5. Contextual salience scoring and proactive relationship application cue.

Run offline without network or API keys:
    python examples/demo_whatsapp_timeline.py
"""

import os
import sys
from datetime import UTC, datetime

# Ensure recall package is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from recall.client import Recall
from recall.config import TestClock
from recall.engine.extractor import FixtureExtractor


def run_demo():
    print("=" * 80)
    print(" 🚀 RECALL: TEMPORAL ENTITY MEMORY ENGINE DEMONSTRATION")
    print("    Simulated 6-Month Timeline (Offline & Deterministic Fixture Driven)")
    print("=" * 80)

    # Injected test clock starting at Jan 1, 2026
    t_jan1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    clock = TestClock(t_jan1)

    # Temporary SQLite database
    db_path = "recall_demo.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        with Recall(db_path=db_path, clock=clock, extractor=FixtureExtractor()) as client:
            # -------------------------------------------------------------------------
            # MONTH 1: Jan 1, 2026 — Initial Ingestion
            # -------------------------------------------------------------------------
            print("\n----------------------------------------------------------------")
            print("📅 MONTH 1 (Jan 1, 2026): Message 1 & 2 Ingested")
            print("----------------------------------------------------------------")

            # Message 1
            client.ingest_turn(
                speaker="User",
                text="John works at Google",
                conversation_id="conv_m1",
                message_id="msg_001",
                timestamp=t_jan1,
            )

            # Message 2
            client.ingest_turn(
                speaker="User",
                text="John speaks Spanish",
                conversation_id="conv_m1",
                message_id="msg_002",
                timestamp=t_jan1,
            )

            # State query at Month 1
            q_m1 = client.query(about_entity="John", context="employment and language", valid_at=t_jan1)
            print("\n[Month 1 Memory Snapshot for 'John']:")
            for item in q_m1:
                fact = item.fact
                sal = item.salience
                print(
                    f"  • {fact.predicate}: {fact.object_value} | Salience Score: {sal.composite_score} (retention={sal.retention}, similarity={sal.similarity})"
                )

            # -------------------------------------------------------------------------
            # MONTH 3: March 1, 2026 — Independent Reinforcement & Language Addition
            # -------------------------------------------------------------------------
            t_mar1 = datetime(2026, 3, 1, 14, 30, 0, tzinfo=UTC)
            clock.set(t_mar1)

            print("\n----------------------------------------------------------------")
            print("📅 MONTH 3 (March 1, 2026): Message 3 (Reinforcement & Preference)")
            print("----------------------------------------------------------------")

            # Reinforce John speaks Spanish & add English
            client.ingest_turn(
                speaker="User",
                text="John speaks English",
                conversation_id="conv_m3",
                message_id="msg_003",
                timestamp=t_mar1,
            )

            # -------------------------------------------------------------------------
            # MONTH 5: May 1, 2026 — Employer Transition
            # -------------------------------------------------------------------------
            t_may1 = datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC)
            clock.set(t_may1)

            print("\n----------------------------------------------------------------")
            print("📅 MONTH 5 (May 1, 2026): Message 4 (Employer Transition)")
            print("----------------------------------------------------------------")

            res_may = client.ingest_turn(
                speaker="User",
                text="John started working at Amazon",
                conversation_id="conv_m5",
                message_id="msg_004",
                timestamp=t_may1,
            )
            amazon_logical_id = res_may.inserted_facts[0].logical_id

            # -------------------------------------------------------------------------
            # MONTH 6: June 1, 2026 — Late-Arriving Historical Correction
            # -------------------------------------------------------------------------
            t_jun1 = datetime(2026, 6, 1, 18, 0, 0, tzinfo=UTC)
            clock.set(t_jun1)

            print("\n----------------------------------------------------------------")
            print("📅 MONTH 6 (June 1, 2026): Message 5 (Explicit Correction)")
            print("----------------------------------------------------------------")
            print("   Correction Received: 'Actually, John's role at Amazon is in AWS'")

            client.correct_fact(
                logical_id=amazon_logical_id, new_object_value="AWS", source_ref="msg_005_correction", valid_from=t_may1
            )

            # -------------------------------------------------------------------------
            # BITEMPORAL COMPARISON & PROVENANCE INSPECTION
            # -------------------------------------------------------------------------
            print("\n" + "=" * 80)
            print(" 🔍 BITEMPORAL KNOWLEDGE-TIME AUDIT (Before vs After Correction)")
            print("=" * 80)

            # What did the system know BEFORE learning the correction at June 1?
            t_may31 = datetime(2026, 5, 31, 23, 59, 59, tzinfo=UTC)
            q_before_corr = client.query(about_entity="John", context="company", valid_at=t_may1, known_at=t_may31)
            print("\n1. Memory as understood on May 31 (known_at = May 31, valid_at = May 1):")
            for item in q_before_corr:
                print(
                    f"   - {item.fact.predicate}: {item.fact.object_value} (version_id={item.fact.version_id}, source={item.fact.source_ref})"
                )

            # What does the system know NOW at June 1?
            q_after_corr = client.query(about_entity="John", context="company", valid_at=t_may1, known_at=t_jun1)
            print("\n2. Memory as understood on June 1 (known_at = June 1, valid_at = May 1):")
            for item in q_after_corr:
                print(
                    f"   - {item.fact.predicate}: {item.fact.object_value} (version_id={item.fact.version_id}, source={item.fact.source_ref})"
                )

            # Historical Version Trace for Amazon/AWS assertion
            print(f"\n3. Complete Version History Trace for Logical Fact ID '{amazon_logical_id}':")
            history = client.inspect_history(amazon_logical_id)
            for ver in history:
                v_to_str = ver.valid_to.isoformat() if ver.valid_to else "∞ (Current)"
                t_to_str = ver.tx_to.isoformat() if ver.tx_to else "∞ (Current)"
                print(
                    f"   [Version {ver.version_id}] val={ver.object_value} | Valid: [{ver.valid_from.strftime('%Y-%m-%d')} to {v_to_str}) | Tx: [{ver.tx_from.strftime('%H:%M:%S')} to {t_to_str}) | Source: {ver.source_ref}"
                )

            # -------------------------------------------------------------------------
            # MONTH 6 SNAPSHOT & PROACTIVE APPLICATION CUE
            # -------------------------------------------------------------------------
            print("\n" + "=" * 80)
            print(" 💡 MONTH 6 SALIENCE SNAPSHOT & PROACTIVE RELATIONSHIP CUE")
            print("=" * 80)

            q_m6_all = client.query(
                about_entity="John",
                context="Where does John work and what languages does he speak?",
                valid_at=t_jun1,
                known_at=t_jun1,
            )

            print("\n[Ranked Salient Facts for 'John' at Month 6]:")
            for item in q_m6_all:
                f = item.fact
                s = item.salience
                print(f"  • Fact: John {f.predicate} -> {f.object_value}")
                print(
                    f"    Composite Salience: {s.composite_score} (Similarity: {s.similarity}, Retention R(t): {s.retention}, Confidence: {s.confidence})"
                )

            print("\n[PROACTIVE RELATIONSHIP APPLICATION CUE GROUNDED IN RETRIEVED MEMORY]:")
            employer_fact = next((item.fact for item in q_m6_all if item.fact.predicate == "primary_employer"), None)
            languages = [item.fact.object_value for item in q_m6_all if item.fact.predicate == "speaks_language"]

            if employer_fact and languages:
                print(f'  > ✨ PROACTIVE SUGGESTION: "John recently moved to {employer_fact.object_value} in May! ')
                print(f"       He also speaks {', '.join(languages)}. Consider sending a congratulatory message ")
                print('       referencing his role transition."')

            print("\n" + "=" * 80)
            print(" ✅ DEMONSTRATION COMPLETED SUCCESSFULLY")
            print("=" * 80)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    run_demo()
