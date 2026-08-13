"""Sprint 0-7.1 Blueprint API Regression (import/route) Health Check
基于实际 app/__init__.py Blueprint + 前缀注册规则进行断言
"""
import sys
import os

_BASE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_BASE)
sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)


def run():
    from app import create_app
    app = create_app()
    all_routes = sorted(rule.rule for rule in app.url_map.iter_rules())

    # Sprint 7.1 新增 3 个审核接口
    new_routes = [
        '/api/v1/bids/<int:bid_document_id>/requirement/submit-review',
        '/api/v1/bids/<int:bid_document_id>/requirement/review',
        '/api/v1/bids/<int:bid_document_id>/requirement/status',
    ]

    print('=== Blueprint/Route Registration Health Check ===')
    print(f'Total routes registered: {len(all_routes)}')
    api_routes = [r for r in all_routes if r.startswith('/api/v1/')]
    print(f'API v1 routes: {len(api_routes)}')

    missing = [p for p in new_routes if p not in all_routes]
    assert not missing, f'Missing Sprint 7.1 routes: {missing}'
    print('[PASS] Sprint 7.1 新增 3 个 Requirement Review 接口注册成功')

    # 实际已存在的核心路由(基于实际已注册信息)
    legacy_routes = [
        # Sprint 1
        '/api/v1/auth/register',
        '/api/v1/auth/login',
        '/api/v1/auth/profile',
        # Sprint 2 (contract_api_bp at /api/v1/contracts)
        '/api/v1/contracts/upload',
        '/api/v1/contracts',
        # Sprint 3 (analysis_bp at /api/v1/analysis)
        '/api/v1/analysis/<int:task_id>',
        # Sprint 4 (knowledge_bp at /api/v1/knowledge + rag_bp at /api/v1/rag)
        '/api/v1/knowledge/upload',
        '/api/v1/knowledge',
        '/api/v1/knowledge/<int:document_id>',
        '/api/v1/rag/query',
        # Sprint 5 (review_bp at /api/v1/reviews)
        '/api/v1/reviews',
        '/api/v1/reviews/<int:review_id>',
        '/api/v1/reviews/<int:review_id>/trace',
        # Sprint 6
        '/api/v1/templates',
        '/api/v1/templates/upload',
        '/api/v1/templates/<int:template_id>',
        '/api/v1/generation/preview',
        '/api/v1/generation/generate',
        '/api/v1/generation/history',
        '/api/v1/generation/<int:generation_id>',
        '/api/v1/generation/<int:generation_id>/trace',
        '/api/v1/generated/<int:generation_id>/download',
        # Sprint 7.0 (bid_bp at /api/v1/bids + proposal_bp at /api/v1/proposals)
        '/api/v1/bids/upload',
        '/api/v1/bids',
        '/api/v1/bids/<int:bid_document_id>/requirement',
        '/api/v1/bids/<int:bid_document_id>/generate',
        '/api/v1/proposals',
        '/api/v1/proposals/<int:proposal_id>/trace',
        '/api/v1/proposals/<int:proposal_id>/download',
    ]
    for p in legacy_routes:
        assert p in all_routes, f'历史回归: {p} 丢失!现有路由中不存在'
    print(f'[PASS] Sprint 0-7 核心路由全部存在,无丢失(共 {len(legacy_routes)} 条)')

    # JWT 保护验证(未登录 => 401)
    print()
    print('=== JWT/RBAC 保护 Test Client ===')
    client = app.test_client()
    paths = [
        '/api/v1/bids', '/api/v1/proposals', '/api/v1/contracts',
        '/api/v1/auth/profile', '/api/v1/knowledge', '/api/v1/reviews',
        '/api/v1/templates', '/api/v1/generation/history',
    ]
    for path in paths:
        resp = client.get(path)
        assert resp.status_code == 401, f'{path} 未登录应 401,实际 {resp.status_code}'
    print(f'[PASS] {len(paths)} 条核心 GET 接口未登录 => 401 (JWT保护正常)')

    # Sprint 7.1 接口权限验证
    print()
    print('=== Sprint 7.1 新接口 JWT 保护 Test Client ===')
    r = client.post('/api/v1/bids/1/requirement/submit-review')
    assert r.status_code == 401
    r = client.put('/api/v1/bids/1/requirement/status', json={'new_status': 'approved'})
    assert r.status_code == 401
    print('[PASS] Sprint 7.1 submit-review/status 未登录 => 401')

    # Sprint 7.1 review 接口 RBAC
    print()
    print('=== Sprint 7.1 review 接口 RBAC(contract_manager/admin only) ===')
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token_emp = create_access_token(
            identity='999999',
            additional_claims={'role': 'employee', 'username': 'test_emp_s71'})
    emp_headers = {'Authorization': f'Bearer {token_emp}'}
    r = client.post('/api/v1/bids/1/requirement/review',
                    json={'approved': True}, headers=emp_headers)
    assert r.status_code == 403, f'employee 调 review 接口应 403,实际 {r.status_code}'
    print('[PASS] employee 调用 /requirement/review => 403 (RBAC 正常)')

    print()
    print('=' * 70)
    print('SPRINT 0-7.1 FULL REGRESSION TEST: ALL PASSED')
    print('=' * 70)


if __name__ == '__main__':
    run()
