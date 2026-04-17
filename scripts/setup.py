"""
setup.py — One-command setup: generate data → load baseline → load rules → verify.

Usage:
    python scripts/setup.py

Prerequisites:
    1. Neo4j Community 5.x running at bolt://localhost:7687
    2. .env file with NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    3. pip install -r requirements.txt
"""

import os
import sys
import time

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from src.graph.connection import get_driver, check_connection
from src.graph.loader import setup_schema, load_baseline, load_detection_rules


def main():
    print("=" * 60)
    print("KG Data Quality Demo — Setup")
    print("=" * 60)

    # Step 1: Check Neo4j
    print("\n[1/4] Checking Neo4j connection...", end=" ", flush=True)
    driver = get_driver()
    if not check_connection(driver):
        print("FAILED")
        print("\nNeo4j is not reachable. Ensure:")
        print("  1. Neo4j Community 5.x is installed and running")
        print("  2. Default URL: bolt://localhost:7687")
        print("  3. .env file has correct NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD")
        print("  4. Start Neo4j: C:\\neo4j\\bin\\neo4j console")
        sys.exit(1)
    print("OK")

    # Step 1b: Clear existing data (idempotent re-run)
    print("\n[1b/4] Clearing existing graph data...", end=" ", flush=True)
    from src.graph.loader import clear_database
    clear_database(driver)
    print("OK")

    # Step 2: Generate data
    gen_dir = os.path.join(PROJECT_ROOT, "data", "generated")
    claim_file = os.path.join(gen_dir, "system_b_claims", "claim_header.csv")

    if os.path.exists(claim_file):
        print("\n[2/4] Data already generated — skipping (delete data/generated/ to regenerate)")
    else:
        print("\n[2/4] Generating synthetic data...")
        t0 = time.time()
        from src.generate.generator import generate_all
        generate_all()
        print(f"  Generation time: {time.time() - t0:.1f}s")

    # Step 3: Load to Neo4j
    data_dir = gen_dir
    print("\n[3/4] Loading baseline to Neo4j...")
    t0 = time.time()

    print("  Creating schema (constraints + indexes)...")
    setup_schema(driver)

    counts = load_baseline(driver, data_dir)
    elapsed = time.time() - t0

    print("\n  Node counts:")
    for label, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {label:<20} {n:>6}")
    print(f"\n  Load time: {elapsed:.1f}s")

    if elapsed > 60:
        print("  WARNING: Load time exceeded 60s target. Check Neo4j heap configuration.")

    # Step 4: Load detection rules
    rules_path = os.path.join(PROJECT_ROOT, "data", "reference", "detection_rules.yaml")
    print("\n[4/4] Loading detection rules...")
    n_rules = load_detection_rules(driver, rules_path)
    print(f"  {n_rules} DetectionRule nodes loaded")

    # Verification
    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    with driver.session() as session:
        # Check DetectionRules
        rules = session.run("MATCH (r:DetectionRule) RETURN r.rule_id AS id, r.name AS name ORDER BY r.rule_id").data()
        print(f"\nDetectionRule nodes ({len(rules)}):")
        for r in rules:
            print(f"  {r['id']}: {r['name']}")

        # Check node totals
        total = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        print(f"\nTotal nodes:         {total:>8}")
        print(f"Total relationships: {rels:>8}")

        # Check no Finding nodes exist yet
        findings = session.run("MATCH (f:Finding) RETURN count(f) AS n").single()["n"]
        print(f"Finding nodes:       {findings:>8}  (expected: 0)")

    print("\n" + "=" * 60)
    print("Setup complete.")
    print("Run the app:  streamlit run src/app/main.py")
    print("=" * 60)
    driver.close()


if __name__ == "__main__":
    main()
