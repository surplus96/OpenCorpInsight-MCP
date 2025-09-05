import sys, os, asyncio
from pathlib import Path

# Ensure src on sys.path
ROOT = Path('/Users/choetaeyeong/projects/OpenCorpInsight')
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dart_mcp_server import handle_list_tools, get_financial_statements

async def run():
    tools = await handle_list_tools()
    print('TOOLS:', [t.name for t in tools])

    # MetaM cashflow 2024 (with XBRL/PDF fallback)
    res = await get_financial_statements(
        corp_name=None,
        bsns_year='2024',
        reprt_code='11014',
        fs_div='CFS',
        statement_type='현금흐름표',
        corp_code='00594934'
    )
    for i, r in enumerate(res, 1):
        print(f"\n--- RESULT {i} ---\n")
        print(getattr(r, 'text', r))

if __name__ == '__main__':
    asyncio.run(run())
