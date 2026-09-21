"""Live retrieval and chat tests. Pass --chat to exercise the real Qwen model."""
import asyncio
import json
from pathlib import Path
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.chat import validate_answer


def ask(client, message, **scope):
    events = []
    with client.stream('POST', '/chat', json={"message": message, **scope}, timeout=600) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith('data: '):
                payload = json.loads(line[6:])
                events.append(payload)
                if 'answer' in payload:
                    print(json.dumps(payload, ensure_ascii=False), flush=True)
                    return payload
    raise AssertionError(events)


async def mcp_check(old, new):
    async with streamablehttp_client('http://mcp-server:8001/mcp') as (read,write,_):
        async with ClientSession(read,write) as session:
            await session.initialize()
            result = await session.call_tool('compare_document_versions', {"version_ids": [old,new]})
            assert not result.isError, result
            payload = result.structuredContent or json.loads(next(item.text for item in result.content if item.type == 'text'))
            assert len(payload['sources']) == 20


def main():
    manifest = json.loads(Path('/data/files/demo/manifest.json').read_text())
    old = manifest['hr_policy_v0.1']['version_id']
    new = manifest['hr_policy_v0.2']['version_id']
    with httpx.Client(base_url='http://app:8000', timeout=180) as client:
        for mode in ('keyword','vector','hybrid'):
            query = "Nhân viên được nghỉ phép bao nhiêu ngày mỗi năm?" if mode == 'vector' else "HR-01"
            response = client.post('/search',json={"query": query, "mode": mode,"version_ids": [old]})
            response.raise_for_status()
            sources = response.json()['sources']
            assert sources and sources[0]['page_number'] == 1, (mode,sources)
            assert all(source['version_id']==old for source in sources)
        response = client.post('/search',json={"query": "nghi phep", "mode": "keyword"})
        response.raise_for_status()
        assert any(item['version_id']==new and item['page_number']==1 for item in response.json()['sources'])
        assert all(item['version_id']!=old for item in response.json()['sources'])
        assert client.post('/chat',json={"message":"so sánh","compare":True}).status_code==422
        answer,citations=validate_answer('Thông tin [C999999]',[{"chunk_id":1}])
        assert not citations and 'Chưa đủ' in answer
        asyncio.run(mcp_check(old,new))
        # One old version is enough: the server resolves the latest ready version.
        response = client.post('/chat',json={"message":"so sánh HR-01", "version_ids": [old], "compare": True})
        assert response.status_code == 200, response.text
        print('PASS: retrieval modes, Vietnamese unaccent, scope/latest-ready, MCP comparison, citation guard',flush=True)
        if '--chat' in sys.argv:
            result=ask(client,'Theo HR-01, nhân viên được nghỉ phép bao nhiêu ngày mỗi năm?',version_ids=[new],mode='keyword')
            assert '15' in result['answer'],result
            assert result['citations'] and all(source['version_id']==new for source in result['citations'])
            assert result['tools'][0]['model_called'],result
            compared=ask(client,'HR-01 và HR-02 thay đổi thế nào giữa hai bản?',version_ids=[old,new],compare=True)
            assert {source['version_id'] for source in compared['citations']}=={old,new},compared
            assert '12' in compared['answer'] and '15' in compared['answer'],compared
            missing=ask(client,'Công ty có chính sách cấp tàu vũ trụ cho nhân viên không?',version_ids=[new],mode='keyword')
            assert not missing['citations'],missing
            history=client.get(f"/conversations/{result['conversation_id']}/messages")
            history.raise_for_status()
            assert len(history.json())==2
            print('PASS: real Qwen tool calling, answer/citations, version comparison, unknown question, persisted history')


if __name__=='__main__':
    main()
