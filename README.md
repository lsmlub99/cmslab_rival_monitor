# K-뷰티 경쟁사 인텔리전스 모니터링 시스템

CellFusion C 팀을 위한 경쟁사(Anua, Mediheal, By Wishtrend, Cos de Baha, Dalba) 동향 자동 수집·분류·대시보드 시스템.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 자동 수집 | Google RSS · BeautyMatter · WWD · 장업신문 · PRTimes JP |
| AI 분류 | Claude API — 활동유형·중요도·한국어 번역 자동 분류 |
| 중복 제거 | URL 해시 + 제목 유사도 이중 필터 |
| HTML 대시보드 | 히트맵·스택바·인사이트 카드·기간별 토글(7/30/90일) |
| CLI | 즉시 수집·보고서 생성·DB 조회 |
| Slack 알림 | HIGH importance 기사 실시간 알림 |

## 프로젝트 구조

```
CellFusionC_intel/
├── config/          # 브랜드 목록, DB/API 설정
├── collectors/      # Google RSS, 미디어 RSS, 장업신문, PRTimes 수집기
├── classifier/      # Claude API 기반 분류 (활동유형 · 중요도 · 번역)
├── deduplication/   # URL 해시 · 제목 유사도 중복 제거
├── analytics/       # DB 집계 쿼리, Claude API 전략 인사이트 요약
├── dashboard/       # HTML 대시보드 생성기
├── storage/         # SQLAlchemy 모델 · Repository
├── scheduler/       # 수집 파이프라인 · 스케줄러
├── notifications/   # Slack Webhook 알림
├── cli.py           # CLI 진입점
└── main.py          # 스케줄러 진입점
```

## 설치

```bash
cd CellFusionC_intel
pip install -r requirements.txt
cp .env.example .env
# .env 편집 — API 키 · DB 정보 입력
```

### .env 설정

```env
OPENAI_API_KEY=sk-...          # OpenAI API 키 (분류기용)
ANTHROPIC_API_KEY=sk-ant-...   # Claude API 키 (인사이트 요약용)

DB_HOST=...                    # Supabase / PostgreSQL 호스트
DB_PORT=5432
DB_USER=...
DB_PASSWORD=...
DB_NAME=postgres

SLACK_WEBHOOK_URL=             # 선택사항 — HIGH 기사 알림
```

## 사용법

### CLI

```bash
cd CellFusionC_intel

# 특정 브랜드 즉시 수집
python cli.py collect --brand Anua --country JP

# 전체 브랜드 × 국가 수집
python cli.py collect-all

# HTML 보고서 생성 (최근 30일)
python cli.py report --days 30 --output report.html

# DB 현황 확인
python cli.py stats

# HIGH importance 기사 목록
python cli.py high --days 7
```

### 스케줄러 (24시간 자동 수집)

```bash
python main.py
```

### DB 마이그레이션

```bash
python -c "from storage.models import create_tables, migrate_tables; create_tables(); migrate_tables()"
```

## 대시보드 기능

- **기간 토글**: 최근 7일 / 30일 / 90일 전환 — KPI·히트맵·차트 동시 갱신
- **히트맵 드릴다운**: 브랜드×국가 셀 클릭 → 전체 기사 HIGH/MEDIUM/LOW 분류 슬라이딩 패널
- **브랜드 인사이트 카드**: Claude API 자동 생성 전략 요약 + 근거 기사 3건
- **스택바 클릭**: 해당 브랜드 인사이트 카드로 스크롤

## 수집 대상

| 브랜드 | 모니터링 국가 |
|--------|-------------|
| Anua | US · JP · KR · SG · PL · TH · CA · GB |
| Mediheal | US · JP · KR · SG |
| By Wishtrend | US · JP · KR · SG |
| Cos de Baha | US · JP · SG |
| Dalba | JP · KR |

## 기술 스택

- **Backend**: Python 3.11 · SQLAlchemy · PostgreSQL (Supabase)
- **AI**: Claude API (분류·번역·인사이트) · OpenAI GPT-4o (보조)
- **수집**: feedparser · requests · BeautifulSoup4
- **대시보드**: Vanilla JS · Canvas API (Chart.js 없이 custom 렌더링)
