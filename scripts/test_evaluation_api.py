"""Sprint 8.5 评估 API 端到端验证脚本。

验证:
- POST /api/v1/auth/login            登录获取 token
- GET  /api/v1/evaluation/summary    读取最新评估 summary
- GET  /api/v1/evaluation/history    历史评估列表
- GET  /api/v1/evaluation/history/{id}  历史详情
- (不触发 POST /run,避免重复消耗资源;run 已通过 test_evaluation_run.py 验证)

依赖:后端服务需在 127.0.0.1:5001 运行。
"""
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE = 'http://127.0.0.1:5001/api/v1'


def http_call(method, path, token=None, body=None):
    url = BASE + path
    data = None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode('utf-8'))
        except Exception:
            payload = {'raw': str(e)}
        return e.code, payload
    except urllib.error.URLError as e:
        return -1, {'error': f'连接失败(后端服务未启动?): {e}'}


def main():
    print('===== Sprint 8.5 评估 API 端到端验证 =====\n')

    # 1. 登录
    print('[1] 登录 admin ...')
    code, res = http_call('POST', '/auth/login', body={
        'username': 'admin', 'password': '123456'
    })
    print(f'    登录响应: HTTP={code}')
    print(f'    完整响应: {json.dumps(res, ensure_ascii=False)[:500]}')
    if code != 200 or res.get('code') != 200:
        print(f'    登录失败: code={code} res={res}')
        sys.exit(1)
    data = res.get('data', {}) or {}
    token = data.get('token') or data.get('access_token')
    if not token and isinstance(data, dict):
        # 兼容 {user: {...}, token: ...} 或嵌套结构
        token = data.get('user', {}).get('token') if isinstance(data.get('user'), dict) else None
    if not token:
        print(f'    未找到 token, data keys={list(data.keys()) if isinstance(data, dict) else type(data)}')
        sys.exit(1)
    print(f'    登录成功, token={token[:20]}...')

    # 2. /summary
    print('\n[2] GET /evaluation/summary ...')
    code, res = http_call('GET', '/evaluation/summary', token=token)
    print(f'    HTTP={code} biz_code={res.get("code")}')
    if res.get('code') == 200 and res.get('data'):
        d = res['data']
        print(f'    status={d.get("status")} ({d.get("status_label")})')
        print(f'    total_questions={d.get("total_questions")} '
              f'context_hit_count={d.get("context_hit_count")} '
              f'hit_rate={d.get("context_hit_rate")}')
        print(f'    faithfulness={d.get("faithfulness")} '
              f'relevancy={d.get("answer_relevancy")} '
              f'precision={d.get("context_precision")} '
              f'recall={d.get("context_recall")}')
        print(f'    ai_success_rate={d.get("ai_success_rate")} '
              f'p95={d.get("ai_p95_latency_ms")}ms')
        env = d.get('test_environment', {}) or {}
        print(f'    knowledge_docs={env.get("knowledge_total_documents")} '
              f'hit_docs={env.get("knowledge_hit_documents")}')
    else:
        print(f'    响应: {res}')

    # 3. /history
    print('\n[3] GET /evaluation/history ...')
    code, res = http_call('GET', '/evaluation/history?page=1&size=5', token=token)
    print(f'    HTTP={code} biz_code={res.get("code")}')
    if res.get('code') == 200 and res.get('data'):
        d = res['data']
        items = d.get('items', []) or []
        print(f'    total={d.get("total")} 返回 {len(items)} 条')
        for it in items[:3]:
            print(f'      - id={it.get("id")} report_no={it.get("report_no")} '
                  f'status={it.get("status")} created={it.get("created_time")}')

        # 4. /history/{id} 详情(取第一条)
        if items:
            first_id = items[0].get('id')
            print(f'\n[4] GET /evaluation/history/{first_id} ...')
            code, res = http_call('GET', f'/evaluation/history/{first_id}', token=token)
            print(f'    HTTP={code} biz_code={res.get("code")}')
            if res.get('code') == 200 and res.get('data'):
                d = res['data']
                m = d.get('metrics', {}) if isinstance(d.get('metrics'), dict) else {}
                print(f'    report_no={d.get("report_no")} '
                      f'metrics.status={m.get("status")}')

    # 5. 权限验证:无 token 调 /summary 应 401
    print('\n[5] 权限验证:无 token 调 /summary ...')
    code, res = http_call('GET', '/evaluation/summary')
    print(f'    HTTP={code} (期望 401) biz_code={res.get("code")}')

    print('\n===== 验证完成 =====')


if __name__ == '__main__':
    main()
