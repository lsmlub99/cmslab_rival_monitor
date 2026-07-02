"""
CelFusion 경쟁사 모니터링 시스템 엔트리포인트

사용:
    python main.py --help
    python main.py init-db
    python main.py collect --brand Anua --country PL
    python main.py query --brand Anua --days 7
    python main.py run
"""

from cli import cli

if __name__ == "__main__":
    cli()
