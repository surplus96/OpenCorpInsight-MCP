import os
import requests
import pandas as pd

# Load .env if exists to get DART_API_KEY
try:
    from dotenv import load_dotenv
    from pathlib import Path
    for p in [Path('/Users/choetaeyeong/projects/OpenCorpInsight/.env'), Path.cwd()/'.env']:
        if p.exists():
            load_dotenv(p, override=True)
            break
except Exception:
    pass

API_KEY = os.getenv("DART_API_KEY")
CORP_CODE = "01630808"  # 신세계 corp_code
YEAR = "2025"

def check_regular_filings():
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": API_KEY,
        "corp_code": CORP_CODE,
        "bgn_de": f"{YEAR}0101",
        "end_de": f"{YEAR}1231",
        "pblntf_ty": "A",         # 정기공시
        "last_reprt_at": "Y",     # 최종보고서 위주
        "page_count": 100,
        "sort": "date",
        "sort_mth": "desc",
    }
    r = requests.get(url, params=params, timeout=15)
    j = r.json()
    if j.get("status") != "000":
        print(f"[list] 오류: {j.get('status')} {j.get('message')}")
        return []
    items = j.get("list", [])
    biz = [it for it in items if "사업보고서" in (it.get("report_nm") or "")]
    print(f"[list] {YEAR} 정기공시(A) 총 {len(items)}건, 사업보고서 {len(biz)}건")
    return items


def fetch_cashflow_bsns_report():
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": API_KEY,
        "corp_code": CORP_CODE,
        "bsns_year": YEAR,
        "reprt_code": "11014",    # 사업보고서(연간)
        "fs_div": "CFS",          # 연결
    }
    r = requests.get(url, params=params, timeout=20)
    j = r.json()
    if j.get("status") != "000":
        print(f"[fs] 오류: {j.get('status')} {j.get('message')}")
        return None
    df = pd.DataFrame(j.get("list", []))
    if df.empty:
        print("[fs] 데이터 없음")
        return None
    cf = df[df["sj_nm"] == "현금흐름표"].copy()
    if cf.empty:
        print("[fs] 현금흐름표 섹션 없음")
        return None
    cols = [c for c in ["account_nm","thstrm_amount","frmtrm_amount","bfefrmtrm_amount"] if c in cf.columns]
    out = cf[cols].rename(columns={
        "account_nm": "계정",
        "thstrm_amount": "당기",
        "frmtrm_amount": "전기",
        "bfefrmtrm_amount": "전전기",
    })
    return out

if __name__ == "__main__":
    if not API_KEY:
        raise RuntimeError("환경변수 DART_API_KEY가 필요합니다.")
    check_regular_filings()
    result = fetch_cashflow_bsns_report()
    if result is not None:
        print("\n[현금흐름표] 신세계 2025 (연결, 사업보고서)")
        print(result.to_string(index=False))
    else:
        print("\n[현금흐름표] 조회 실패(사업보고서 11014, CFS)")
