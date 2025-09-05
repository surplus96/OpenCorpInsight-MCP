#!/usr/bin/env python3
"""
MCP 서버 실행 래퍼 스크립트
가상환경과 경로 설정을 자동으로 처리합니다.
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
SRC_DIR = PROJECT_ROOT / "src"

# Python 경로에 프로젝트 디렉토리 추가
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_DIR))

# 작업 디렉토리를 프로젝트 루트로 변경
os.chdir(PROJECT_ROOT)

# 환경변수 설정
os.environ["PYTHONPATH"] = f"{PROJECT_ROOT}:{SRC_DIR}"

# 환경변수는 메인 서버 파일에서 로드됩니다
print("MCP 서버 시작 중...", file=sys.stderr)

# MCP 서버 실행
if __name__ == "__main__":
    try:
        from src.dart_mcp_server import main
        import asyncio
        asyncio.run(main())
    except Exception as e:
        print(f"MCP 서버 실행 오류: {e}", file=sys.stderr)
        sys.exit(1) 