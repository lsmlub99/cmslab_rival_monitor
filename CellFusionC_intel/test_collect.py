"""
RSS 수집기 단독 테스트 (DB/API 키 불필요)
"""
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))

from collectors.google_rss import GoogleRSSCollector

collector = GoogleRSSCollector()

TEST_CASES = [
    ("Anua", "PL"),
    ("Anua", "US"),
    ("Skin1004", "US"),
]

for brand, country in TEST_CASES:
    print(f"\n{'='*60}")
    print(f"수집: {brand} / {country}")
    print("="*60)
    articles = collector.collect(brand, country)
    print(f"  → {len(articles)}건 수집")
    for i, a in enumerate(articles[:3]):
        print(f"  [{i+1}] {a.title[:80]}")
        print(f"       {a.source_name} | {a.published.strftime('%Y-%m-%d')}")
        print(f"       {a.url[:80]}")

print("\n수집 테스트 완료")
