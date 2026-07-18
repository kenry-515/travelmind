# TravelMind Agent — Data Pipeline Scripts
# Run in order:
#   1. fetch_wikidata.py       — SPARQL queries for 10 cities
#   2. enrich_wikipedia.py     — Wikipedia extract fetcher
#   3. enrich_amap.py          — Amap POI supplement
#   4. ai_enrich.py            — DeepSeek batch tagging
#   5. build_knowledge_base.py — Merge → JSON → Chroma ingestion
