# Healthcare RCM Knowledge Graph — Data Quality Demo

A interactive demo built by **xVector** showing how a knowledge graph detects healthcare Revenue Cycle Management (RCM) data quality problems that flat-file systems and standard claim edits cannot find.

---

## What this demonstrates

Standard claim processing systems validate fields in isolation — they check whether an authorization number exists in the claim header, but cannot verify whether that authorization is actually valid, unexpired, or linked to the right procedure. A knowledge graph traverses relationships across entities and catches what flat-file edits miss.

This app injects six real-world RCM data quality scenarios into a synthetic graph of 13,000+ nodes and detects each one using graph traversal rules — before a single claim is worked.

---

## The six scenarios

| # | Scenario | Category | Why standard tools miss it |
|---|----------|----------|---------------------------|
| S-01 | Unverifiable Prior Authorization Chain | Prior Auth | Claim edits check for an auth number in the header — not whether the auth chain is intact, covers the right CPT, or is unexpired |
| S-02 | Rendering Provider Not Credentialed with Billed Payer | Credentialing | Clearinghouses look up providers by NPI in a table — they don't traverse the contract graph to verify the specific payer relationship |
| S-03 | Claim Resolved Against Superseded Contract Version | Contract | Contract version is stored as a field on the claim — the supersession relationship between versions is not modeled in flat-file systems |
| S-04 | Authorization Unit Exhaustion Across Claims | Auth Units | Claim-level edits check units on a single claim — cross-claim aggregation against a shared authorization requires graph traversal |
| S-05 | Duplicate Patient Identity Across Source Systems | Entity Integrity | MPI matching works on demographics in isolation — graph proximity (same provider, payer, zip) is not considered |
| S-06 | Invalid HMO Referral Chain | Referral | Pre-bill edits check for a referral number — not date sequence, PCP credential, or referral-to-provider match |

---

## App structure

```
Five panels navigated from the sidebar:

1. Ontology Explorer   — Full schema: 14 node types, 21 relationship types
2. Rule Library        — Six detection rules with live finding counts
3. KG Foundation       — Search and explore the baseline claim graph
4. Scenario Loader     — Inject a flaw, watch detection fire in real time
5. Findings Dashboard  — Review, acknowledge, and resolve findings with audit trail
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Graph database | Neo4j Community 5.x |
| App framework | Streamlit |
| Graph visualization | pyvis (rendered via `st.components.v1.html`) |
| Data generation | Faker + custom RCM domain model |
| Language | Python 3.11 |

---

## How it works

```
Baseline load (setup.py)
  └── 13,555 nodes: Patients, Visits, Claims, Providers,
      Payers, Contracts, Authorizations, Referrals, CPT/ICD codes

Inject scenario (Panel 4)
  └── Modifies existing graph in place — severs relationships,
      changes property values, swaps relationship targets
  └── Tags affected Claims with flaw_scenario='S-XX'
  └── Runs detection Cypher → creates Finding nodes

Findings Dashboard (Panel 5)
  └── Reads Finding nodes from graph
  └── Shows diagnostic facts: exact dates, units, NPIs, contract versions
  └── Split-pane graph view: actual (with flaw) vs expected (clean ontology)
  └── Lifecycle: open → acknowledged → resolved (written to graph with note)

Clear All Flaws (Panel 4)
  └── Reverses every injected change using stored inventory
  └── Deletes all Finding nodes
  └── Restores baseline — graph identical to post-setup state
```

---

## Detection rules

Rules are stored as `DetectionRule` nodes in the graph — not hardcoded in application logic. The runner is generic: it reads the Cypher from the graph and executes it. Adding a new rule means adding a node, not changing application code.

```cypher
// Example: how DR-S01 is executed at runtime
MATCH (r:DetectionRule {rule_id: 'DR-S01'})
RETURN r.cypher AS cypher
// → execute result against graph
```

---

## Running locally

**Prerequisites:** Neo4j Community 5.x running at `bolt://localhost:7687`

```bash
git clone https://github.com/kiri01-dev/DEMO-Healthcare-KnowledgeGraphExplorer.git
cd DEMO-Healthcare-KnowledgeGraphExplorer

python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Create .env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# Load graph (generates synthetic data + loads to Neo4j)
python scripts/setup.py

# Run app
streamlit run src/app/main.py
```

---

## Deploying to Streamlit Cloud

1. Fork or clone this repo to your GitHub account
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Set **Main file path:** `src/app/main.py`
4. Under **Advanced settings → Secrets**, add:
```toml
NEO4J_URI = "neo4j+s://your-instance.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your-auradb-password"
```
5. Deploy — first boot takes ~2 minutes

A cloud Neo4j instance (AuraDB or self-hosted) is required for deployment. The app reads connection parameters from Streamlit secrets, falling back to `.env` for local runs.

---

*Built by xVector — Healthcare RCM Intelligence*
