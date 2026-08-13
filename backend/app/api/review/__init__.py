"""
合同审核 API 模块(Sprint 5 - v0.7.0)

提供审核报告查询接口(独立于 contracts 前缀):
- GET /api/v1/reviews/{id}  查询审核报告详情(含 risks)

另:POST /api/v1/contracts/{id}/review 与 GET /api/v1/contracts/{id}/reviews
   在 api/contract/routes.py 的 contract_api_bp 中注册(资源嵌套于合同)。
"""
