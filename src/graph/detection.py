"""
detection.py — Detection rule runner.

run_rule() reads Cypher from the DetectionRule node in the graph
and executes it. This is the production architecture demo: rules
live in the graph as first-class entities; the runner is generic.

All detection Cypher is stored in detection_rules.yaml and loaded
into DetectionRule nodes by loader.load_detection_rules().
"""

from neo4j import Driver


def run_rule(rule_id: str, driver: Driver) -> int:
    """
    Execute a single detection rule by rule_id.
    Reads Cypher from the DetectionRule node, executes it,
    returns the number of Finding nodes created.
    """
    with driver.session() as session:
        # Retrieve Cypher from graph — this is what makes it a production architecture
        result = session.run(
            "MATCH (r:DetectionRule {rule_id: $id, active: true}) RETURN r.cypher AS cypher",
            id=rule_id,
        )
        record = result.single()
        if not record or not record["cypher"]:
            return 0

        cypher = record["cypher"]

    with driver.session() as session:
        result = session.run(cypher)
        record = result.single()
        if record and "findings_created" in record.keys():
            return record["findings_created"]
        return 0


def run_all_rules(driver: Driver) -> dict:
    """
    Run all active detection rules.
    Returns {rule_id: finding_count}.
    """
    with driver.session() as session:
        rules = session.run(
            "MATCH (r:DetectionRule {active: true}) RETURN r.rule_id AS rule_id"
        ).data()

    counts = {}
    for row in rules:
        rid = row["rule_id"]
        counts[rid] = run_rule(rid, driver)
    return counts


def get_finding_count(driver: Driver, status: str = "open") -> int:
    """Return the count of Finding nodes with the given status."""
    with driver.session() as session:
        result = session.run(
            "MATCH (f:Finding {status: $status}) RETURN count(f) AS n",
            status=status,
        )
        record = result.single()
        return record["n"] if record else 0


def get_finding_counts_by_rule(driver: Driver) -> dict:
    """Return {rule_id: finding_count} for all DetectionRule nodes."""
    with driver.session() as session:
        rows = session.run("""
            MATCH (r:DetectionRule)
            OPTIONAL MATCH (f:Finding)-[:TRIGGERED_BY]->(r)
            RETURN r.rule_id AS rule_id, count(f) AS finding_count
        """).data()
    return {row["rule_id"]: row["finding_count"] for row in rows}
