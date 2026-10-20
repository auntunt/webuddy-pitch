"""Real SDK protocol over the running local workbench; no model call."""
import asyncio, json, sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/harness2-integration-20261019'

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

async def main():
    pid = json.loads((OUT / 'cli-probe-start.json').read_text())['probe_id']
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT/'tmh/workbench_entry.py'),
        'mcp', '--endpoint', 'http://127.0.0.1:8791', '--agent', 'codex-harness-review', '--allow-execution'], cwd='/tmp')
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            names = [t.name for t in (await session.list_tools()).tools]
            save('mcp-live-tools.json', {'server': initialized.model_dump(mode='json'), 'tools': names})
            assert len(names) == 27 and 'webuddy_candidate_decide' not in names
            for tool, args, filename in [
                ('webuddy_harness_recipes', {}, 'mcp-recipes.json'),
                ('webuddy_harness_probe_get', {'probe_id': pid}, 'mcp-probe-report.json'),
                ('webuddy_harness_library', {'project':'BOOTV2'}, 'mcp-library.json'),
                ('webuddy_ticket_get', {'ticket':'BOOTV2-3'}, 'mcp-task-packet.json'),
                ('webuddy_candidate_get', {'candidate_id':1}, 'mcp-candidate-before-assessment.json')]:
                result = await session.call_tool(tool, args)
                save(filename, result.model_dump(mode='json'))
                assert not result.isError, result
            probe = json.loads((OUT/'mcp-probe-report.json').read_text())['structuredContent']
            assert probe['passed'] and probe['source_current'] and probe['cleanup_complete']
            assert probe['result']['comparison']=='improved'
            assert probe['result']['improved_checks']==['A1','A2','A3']
            print(json.dumps({'probe':pid,'candidate_passed':probe['passed'],
                'improved_checks':probe['result']['improved_checks'], 'mcp_tools':len(names)}, ensure_ascii=False))

asyncio.run(main())
