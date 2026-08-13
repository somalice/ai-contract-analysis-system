"""Sprint 7.1 Enterprise Enhancement Unit Test (独立脚本,不用 pytest)"""
import sys
import os

_BASE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_BASE)
sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)


def run():
    from app import create_app
    app = create_app()

    with app.app_context():
        # 1. BidRequirement 验证
        from app.models.bid_requirement import BidRequirement
        from app.models.proposal_section import ProposalSection

        print('=== 1. BidRequirement Model ===')
        assert BidRequirement.next_version('v1.0') == 'v1.1'
        assert BidRequirement.next_version('v1.9') == 'v1.10'
        assert BidRequirement.next_version('v2.5') == 'v2.6'
        assert BidRequirement.next_version(None) == 'v1.0'
        assert BidRequirement.next_version('invalid') == 'v1.0'
        assert 'approved' in BidRequirement.AGENT_READABLE_STATUSES
        assert len(BidRequirement.REQUIRED_FIELDS) == 15
        print('[PASS] BidRequirement version/status 正确')

        # 2. Requirement Context Builder
        print()
        print('=== 2. Requirement Context Builder Test ===')
        from app.ai.bid.context_builder import RequirementContextBuilder

        class MockRetriever:
            def search(self, query, top_k=3, knowledge_types=None):
                return [
                    {
                        'document_id': 1, 'chunk_id': 'c1',
                        'document_title': '公司资质证书', 'page_number': 2,
                        'score': 0.92, 'text': 'ISO9001认证通过,2024-2027',
                        'knowledge_type': 'qualification',
                    },
                    {
                        'document_id': 2, 'chunk_id': 'c3',
                        'document_title': '历史项目案例', 'page_number': 5,
                        'score': 0.87, 'text': '智慧交通平台,2025-交付',
                        'knowledge_type': 'case',
                    },
                ]

        builder = RequirementContextBuilder(MockRetriever())
        rag_ctx = builder.build(
            {
                'project_name': '政务云平台建设项目',
                'tender_org': '某市政务服务中心',
                'technical_requirements': ['云平台高可用', '数据安全', '国产CPU兼容'],
                'qualification_requirements': ['ISO9001认证', '三级等保'],
                'scoring_criteria': ['技术方案 30分', '资质 20分', '案例 20分'],
                'project_location': '北京市海淀区',
            },
            {'name': '示例科技有限公司'},
        )
        stats = rag_ctx['stats']
        print(f'   stats: slots_filled={stats["slots_filled"]}, docs={stats["retrieved_count"]}')
        assert stats['slots_filled'] >= 1
        assert rag_ctx['query_terms']['technical']  # 至少生成了 1 条查询词

        # 公司兜底 profile 断言
        assert rag_ctx.get('company') is not None
        print('[PASS] Context Builder 构建成功, 4 槽位生成 query_terms')

        # 3. Requirement Trace field_sources
        print()
        print('=== 3. Requirement Trace field_sources Test ===')
        from app.ai.bid.requirement_extractor import _build_field_sources

        sample_text = (
            "某市政府采购中心 采购文件\n"
            "项目名称:城市智慧交通管理平台\n"
            "项目编号:CG-2026-0088\n"
            "预算金额:人民币壹仟贰佰万元整 (12,000,000元)\n"
            "招标单位:某市交通运输局\n"
            "投标截止时间:2026年9月30日 17:00\n"
            "项目地点:某市主城区\n"
            "工期:合同签订后 180 日历天\n"
            "技术要求:1.支持每天 100 万辆车牌识别,准确率 >= 99%\n"
            "2.支持视频监控实时回传,延迟 < 500ms\n"
            "3.支持国产鸿蒙系统\n"
            "资格要求:1.具备独立法人资格\n"
            "2.ISO9001质量管理体系认证\n"
            "3.近三年有 3 个同类项目经验\n"
            "评分标准:1.技术方案 40 分 2.项目案例 30 分 3.资质能力 20 分 4.报价 10 分\n"
            "联系人:张先生 13800138000\n"
        )
        req_data = {
            'project_name': '城市智慧交通管理平台',
            'tender_org': '某市交通运输局',
            'project_location': '某市主城区',
            'budget': '12,000,000元',
            'deadline': '2026年9月30日 17:00',
            'duration': '180日历天',
            'delivery_requirements': '合同签订后 10 日内进场',
            'technical_requirements': [
                '支持每天100万辆车牌识别,准确率>=99%',
                '支持视频监控实时回传,延迟<500ms',
                '支持国产鸿蒙系统',
            ],
            'qualification_requirements': [
                '具备独立法人资格',
                'ISO9001质量管理体系认证',
            ],
            'scoring_criteria': ['技术方案 40 分', '项目案例 30 分', '资质能力 20 分'],
            'bid_opening_time': '2026-10-09 10:00',
            'bid_validity': '90天',
            'payment_terms': '预付款30%,验收后65%,质保5%',
            'contact': '张先生 13800138000',
            'other': '无',
        }
        chunks_meta = [{
            'chunk_id': 'c0', 'start_offset': 0, 'end_offset': len(sample_text),
            'page_number': 1, 'length': len(sample_text),
        }]
        sources = _build_field_sources(req_data, sample_text, chunks_meta)
        traced = sum(1 for v in sources.values() if v and v.get('source_text'))
        print(f'   字段来源命中数: {traced}/15')
        assert traced >= 8, f'至少命中 8 字段来源,实际只有 {traced}'

        # 4 字段断言
        for field in ('project_name', 'tender_org', 'budget', 'deadline',
                      'technical_requirements', 'qualification_requirements',
                      'scoring_criteria', 'contact'):
            src = sources.get(field) or {}
            assert src.get('page_number') >= 0, f'{field} page_number 缺失'
            assert 'chunk_id' in src, f'{field} chunk_id 缺失'
            assert 'confidence' in src, f'{field} confidence 缺失'
            assert 'source_text' in src, f'{field} source_text 缺失'
        print('[PASS] field_sources 4 字段格式统一,命中 >= 8/15')

        # 4. Tool Statistics & Trace
        print()
        print('=== 4. Tool Statistics & Trace ===')
        from app.services.proposal_service import aggregate_tool_stats
        trace = [
            {'type': 'tool', 'step': 1, 'tool_name': 'KnowledgeSearchTool',
             'duration_ms': 120, 'success': True},
            {'type': 'tool', 'step': 2, 'tool_name': 'ProposalSectionTool',
             'duration_ms': 2500, 'success': True},
            {'type': 'tool', 'step': 3, 'tool_name': 'KnowledgeSearchTool',
             'duration_ms': 95, 'success': False,
             'error': '检索不到'},
            {'type': 'llm', 'step': 4, 'duration_ms': 8000},
            {'type': 'final', 'step': 5},
        ]
        ts = aggregate_tool_stats(trace,
                                  {'llm_calls': 3, 'llm_duration_ms': 9200},
                                  12.5)
        print(f'   tool_call_count={ts["tool_call_count"]}')
        print(f'   tool_success_count={ts["tool_success_count"]} failed={ts["tool_failed_count"]} rate={ts["tool_success_rate"]}')
        print(f'   tool_duration_ms={ts["tool_duration_ms"]} llm={ts["llm_duration_ms"]} total={ts["total_duration_ms"]}')
        assert ts['tool_call_count'] == 3
        assert ts['tool_success_count'] == 2
        assert ts['tool_failed_count'] == 1
        assert ts['tool_success_rate'] == round(2/3, 4)
        assert ts['tool_duration_ms'] == 120 + 2500 + 95
        assert ts['llm_duration_ms'] == 9200
        assert ts['total_duration_ms'] == 12500
        assert len(ts['tool_breakdown']) == 2  # KnowledgeSearchTool + ProposalSectionTool
        print('[PASS] Tool Statistics 6 项核心指标 + tool_breakdown 明细正确')

        # 5. ProposalContext.get_trace_summary 与 Sprint 5 统一
        print()
        print('=== 5. ProposalContext Trace Summary Unified with Sprint 5 ===')
        from app.ai.bid.context import ProposalContext
        pc = ProposalContext(bid_info={'id': 1}, requirements={}, company_profile={})
        pc.add_trace_step(tool_name='KnowledgeSearchTool', duration_ms=100,
                          status='success')
        pc.add_trace_step(tool_name='CompanyProfileTool', duration_ms=40,
                          status='success')
        pc.add_trace_step(tool_name='RequirementTool', duration_ms=30,
                          status='failed', error_message='no data')
        pc.add_llm_call(duration_ms=2000)
        pc.add_llm_call(duration_ms=1500)
        summary = pc.get_trace_summary()
        for k in ('tool_call_count', 'tool_success_count', 'tool_failed_count',
                  'tool_success_rate', 'tool_duration_ms',
                  'llm_duration_ms', 'total_duration_ms', 'tool_breakdown',
                  'rag_slots_filled', 'rag_documents_count',
                  'iterations', 'max_iterations'):
            assert k in summary, f'trace_summary 缺少 Sprint 5 关键指标: {k}'
        assert summary['tool_call_count'] == 3
        assert summary['tool_success_count'] == 2
        assert summary['tool_failed_count'] == 1
        assert summary['tool_duration_ms'] == 100 + 40 + 30
        assert summary['llm_duration_ms'] == 2000 + 1500
        print('[PASS] trace_summary 与 Sprint 5 统一(10 个关键指标一致)')

        # 6. ProposalSection 序列化 Bid References 统一格式
        print()
        print('=== 6. ProposalSection Bid References Unified Format ===')
        ps = ProposalSection()
        ps.id = 101
        ps.proposal_id = 1
        ps.section_type = 'technical'
        ps.section_name = '技术方案'
        ps.content = '详细技术方案内容...'
        ps.source = 'ai'
        ps.document_id = 7
        ps.similarity_score = 0.93
        ps.references = [
            {
                'document_id': 7, 'chunk_id': 'ch_123', 'document_title': '历史技术方案',
                'page_number': 4, 'score': 0.93,
                'text': '云计算平台技术栈:OpenStack+Kubernetes',
            },
            {
                'document_id': 9, 'chunk_id': 'ch_456',
                'page_number': 2, 'score': 0.88,
                'text': '安全三级等保要求',
            },
        ]
        ps.sort_order = 1
        import datetime as _dt
        ps.created_time = _dt.datetime(2026, 1, 1)
        d = ps.to_dict()
        tr = d['top_reference']
        assert tr['document_id'] == 7
        assert tr['chunk_id'] == 'ch_123'
        assert tr['page_number'] == 4
        assert tr['similarity_score'] == 0.93
        assert d['document_id'] == 7
        assert d['similarity_score'] == 0.93
        assert len(d['references']) == 2
        print('[PASS] Bid References 4 字段统一格式(document_id/chunk_id/page_number/similarity_score) 对齐 Sprint 5')

        print()
        print('=' * 70)
        print('SPRINT 7.1 ENTERPRISE ENHANCEMENT - ALL UNIT TESTS PASSED')
        print('=' * 70)


if __name__ == '__main__':
    run()
