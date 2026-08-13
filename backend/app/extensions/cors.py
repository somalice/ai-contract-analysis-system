"""
CORS 扩展(Sprint 2 - v0.4.0 前端 Admin Console 基础设施)

职责:
- 为 /api/* 接口启用 CORS,允许前端(Vite dev server / 生产域名)跨域访问
- Origin 白名单从 .env 读取(逗号分隔),禁止使用 "*" 通配符
- 正确处理 OPTIONS 预检请求(返回 Allow-Headers / Allow-Methods)
- 不影响 legacy "/" HTML 路由(仅 /api/* 开放)

约束:
- 不修改任何 Blueprint / Service / Model / AI 层
- 仅作为基础设施补全,与 db / jwt / logger 扩展同级
"""
from flask_cors import CORS


def init_cors(app):
    """
    初始化 CORS(仅对 /api/* 开放)

    配置来源:app.config['CORS_ORIGINS'](由 settings.py 从 .env 读取)
    格式:逗号分隔的 Origin 列表,如:
        CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

    安全:
    - 禁止 "*" 通配符(生产环境必须显式列出允许的域名)
    - supports_credentials=True 支持 Cookie / Authorization 头跨域

    注意:methods / allow_headers / supports_credentials 必须放在 resources
    字典内,否则 flask-cors 不会将其应用到对应路径(会导致 OPTIONS 预检
    响应缺失 Allow-Headers,浏览器报 net::ERR_FAILED)。
    """
    origins_raw = app.config.get('CORS_ORIGINS', '')
    origins = [o.strip() for o in origins_raw.split(',') if o.strip()]

    if not origins:
        # 未配置时不启用 CORS(安全失败:宁可拒绝跨域也不开放 "*")
        app.logger.warning('CORS_ORIGINS 未配置,CORS 未启用(/api/* 将拒绝跨域请求)')
        return

    # 仅对 /api/* 路径开放 CORS,不影响 legacy "/" HTML 路由
    # 关键:所有选项必须放在 resources 字典内,否则不生效
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": origins,
                "supports_credentials": True,
                "methods": ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
                "allow_headers": ['Content-Type', 'Authorization'],
            }
        },
    )
    app.logger.info('CORS 已启用 | 允许 Origin: %s | 路径: /api/*', ', '.join(origins))
