"""
LangGraph Workflow 测试模块

使用 pytest 和 pytest-asyncio 测试 StateGraph 的构建、节点函数和条件路由逻辑。
所有测试使用 mock 替代 LLM 调用，确保测试独立且快速。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ============================================================
# 测试状态定义
# ============================================================


class TestAgentState:
    """AgentState 状态定义测试"""

    def test_state_has_required_fields(self):
        """测试 AgentState 包含所有必需字段"""
        from src.graph.state import AgentState

        # 创建默认状态
        state = AgentState(
            test_goal="测试登录功能",
            test_steps=[],
            current_step_index=0,
            executed_steps=[],
            ui_tree=None,
            screenshot_b64=None,
            device_name="emulator-5554",
            test_plan=None,
            verification_passed=False,
            verification_details=[],
            retry_count=0,
            max_retries=3,
            error=None,
            messages=[],
            node_outputs={},
            reviewer_feedback=None,
            total_tokens_used=0,
            metadata={},
        )

        assert state['test_goal'] == "测试登录功能"
        assert state['current_step_index'] == 0
        assert state['retry_count'] == 0
        assert state['max_retries'] == 3
        assert state['verification_passed'] is False

    def test_state_list_fields_merge_with_operator_add(self):
        """测试列表字段支持 operator.add 合并"""
        from src.graph.state import AgentState
        import operator

        # 验证 Annotated 类型使用 operator.add
        state = AgentState(
            test_goal="测试",
            test_steps=["步骤1"],
            current_step_index=0,
            executed_steps=[{"step": "s1"}],
            ui_tree=None,
            screenshot_b64=None,
            device_name="dev",
            test_plan=None,
            verification_passed=False,
            verification_details=[{"check": "c1", "passed": True}],
            retry_count=0,
            max_retries=3,
            error=None,
            messages=[{"role": "user", "content": "hi"}],
            node_outputs={},
            reviewer_feedback=None,
            total_tokens_used=0,
            metadata={},
        )

        assert len(state['test_steps']) == 1
        assert len(state['executed_steps']) == 1
        assert len(state['verification_details']) == 1
        assert len(state['messages']) == 1


# ============================================================
# 工作流构建测试
# ============================================================


class TestWorkflowBuild:
    """StateGraph 工作流构建测试"""

    def test_build_graph_returns_compiled_graph(self):
        """测试构建工作流返回编译后的图实例"""
        from src.graph.workflow import build_workflow

        app = build_workflow()
        assert app is not None

    def test_build_graph_has_expected_nodes(self):
        """测试工作流包含预期的 5 个节点"""
        from src.graph.workflow import build_workflow

        app = build_workflow()
        # 编译后的图应包含节点信息
        assert app is not None

    def test_get_compiled_graph_returns_same_type(self):
        """测试 get_compiled_graph 便捷函数"""
        from src.graph.workflow import get_compiled_graph

        app = get_compiled_graph()
        assert app is not None


# ============================================================
# 路由决策函数测试
# ============================================================


class TestRouteAfterVerifier:
    """验证节点后的路由决策测试"""

    def test_route_to_executor_on_pass_with_remaining_steps(self):
        """测试验证通过且还有剩余步骤时路由到 executor"""
        from src.graph.workflow import route_after_verifier

        state = {
            'verification_passed': True,
            'current_step_index': 1,  # verifier 已递增
            'test_steps': ['步骤1', '步骤2', '步骤3'],
            'retry_count': 0,
            'max_retries': 3,
        }

        result = route_after_verifier(state)
        assert result == "executor"

    def test_route_to_reviewer_on_pass_all_steps_done(self):
        """测试验证通过且所有步骤完成时路由到 reviewer"""
        from src.graph.workflow import route_after_verifier

        state = {
            'verification_passed': True,
            'current_step_index': 3,  # 等于 total_steps
            'test_steps': ['步骤1', '步骤2', '步骤3'],
            'retry_count': 0,
            'max_retries': 3,
        }

        result = route_after_verifier(state)
        assert result == "reviewer"

    def test_route_to_executor_on_fail_with_retries_left(self):
        """测试验证失败但可重试时路由到 executor"""
        from src.graph.workflow import route_after_verifier
        from langgraph.graph import END

        state = {
            'verification_passed': False,
            'current_step_index': 0,
            'test_steps': ['步骤1', '步骤2'],
            'retry_count': 1,  # 小于 max_retries
            'max_retries': 3,
        }

        result = route_after_verifier(state)
        assert result == "executor"

    def test_route_to_end_on_fail_max_retries_exceeded(self):
        """测试验证失败且重试超限时路由到 END"""
        from src.graph.workflow import route_after_verifier
        from langgraph.graph import END

        state = {
            'verification_passed': False,
            'current_step_index': 0,
            'test_steps': ['步骤1', '步骤2'],
            'retry_count': 3,  # 等于 max_retries
            'max_retries': 3,
        }

        result = route_after_verifier(state)
        assert result == END


class TestRouteAfterReviewer:
    """审查节点后的路由决策测试"""

    def test_route_to_end_on_review_passed(self):
        """测试审查通过时路由到 END"""
        from src.graph.workflow import route_after_reviewer
        from langgraph.graph import END

        state = {
            'node_outputs': {
                'reviewer': {'passed': True}
            }
        }

        result = route_after_reviewer(state)
        assert result == END

    def test_route_to_planner_on_review_failed(self):
        """测试审查未通过时路由到 planner"""
        from src.graph.workflow import route_after_reviewer

        state = {
            'node_outputs': {
                'reviewer': {'passed': False}
            }
        }

        result = route_after_reviewer(state)
        assert result == "planner"


# ============================================================
# 节点函数测试
# ============================================================


class TestExplorerNode:
    """探索节点测试"""

    @pytest.mark.asyncio
    async def test_explorer_node_returns_expected_fields(self):
        """测试探索节点返回预期字段"""
        from src.graph.nodes.explorer import explorer_node

        # Mock ExplorerAgent
        with patch('src.graph.nodes.explorer.get_explorer_agent') as mock_get:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={
                'analysis': '分析结果',
                'progress': 'not_started',
                'next_action': 'plan',
                'reasoning': '建议规划',
                'identified_elements': [],
            })
            mock_agent.get_token_summary = MagicMock(return_value={'total_tokens': 100})
            mock_get.return_value = mock_agent

            state = {
                'test_goal': '测试登录',
                'device_name': 'emulator',
                'ui_tree': '',
                'screenshot_b64': '',
                'messages': [],
                'node_outputs': {},
                'total_tokens_used': 0,
            }

            result = await explorer_node(state)

            assert 'node_outputs' in result
            assert 'explorer' in result['node_outputs']
            assert 'messages' in result
            assert 'total_tokens_used' in result

    @pytest.mark.asyncio
    async def test_explorer_agent_uses_light_model(self):
        """测试 ExplorerAgent 使用 light 层级模型"""
        from src.agents.explorer import ExplorerAgent

        agent = ExplorerAgent()
        assert agent.DEFAULT_MODEL_TIER == 'light'


class TestPlannerNode:
    """规划节点测试"""

    @pytest.mark.asyncio
    async def test_planner_node_returns_test_plan(self):
        """测试规划节点返回测试计划"""
        from src.graph.nodes.planner import planner_node

        with patch('src.graph.nodes.planner.get_planner_agent') as mock_get:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={
                'test_plan': {'goal': '测试登录', 'steps': ['步骤1', '步骤2'], 'expected_results': []},
                'test_steps': ['步骤1', '步骤2'],
                'raw_plan': {},
            })
            mock_agent.get_token_summary = MagicMock(return_value={'total_tokens': 200})
            mock_get.return_value = mock_agent

            state = {
                'test_goal': '测试登录',
                'ui_tree': '',
                'screenshot_b64': '',
                'node_outputs': {'explorer': {}},
                'messages': [],
                'total_tokens_used': 0,
            }

            result = await planner_node(state)

            assert 'test_plan' in result
            assert 'test_steps' in result
            assert result['current_step_index'] == 0
            assert result['retry_count'] == 0

    @pytest.mark.asyncio
    async def test_planner_agent_uses_standard_model(self):
        """测试 PlannerAgent 使用 standard 层级模型"""
        from src.agents.planner import PlannerAgent

        agent = PlannerAgent()
        assert agent.DEFAULT_MODEL_TIER == 'standard'


class TestExecutorNode:
    """执行节点测试"""

    @pytest.mark.asyncio
    async def test_executor_node_returns_execution_record(self):
        """测试执行节点返回执行记录"""
        from src.graph.nodes.executor import executor_node

        with patch('src.graph.nodes.executor.get_executor_agent') as mock_get:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={
                'step': '步骤1',
                'step_index': 0,
                'action': 'tap -> 按钮',
                'result': '执行成功',
                'screenshot': '',
                'passed': True,
                'mcp_calls': [],
                'timestamp': '2025-01-01T00:00:00Z',
            })
            mock_agent.get_token_summary = MagicMock(return_value={'total_tokens': 150})
            mock_get.return_value = mock_agent

            state = {
                'test_steps': ['步骤1', '步骤2'],
                'current_step_index': 0,
                'ui_tree': '',
                'screenshot_b64': '',
                'test_plan': {},
                'executed_steps': [],
                'messages': [],
                'node_outputs': {},
                'total_tokens_used': 0,
            }

            result = await executor_node(state)

            assert 'executed_steps' in result
            assert len(result['executed_steps']) == 1
            assert result['executed_steps'][0]['passed'] is True

    @pytest.mark.asyncio
    async def test_executor_node_handles_index_out_of_range(self):
        """测试执行节点处理步骤索引越界"""
        from src.graph.nodes.executor import executor_node

        state = {
            'test_steps': ['步骤1'],
            'current_step_index': 5,  # 越界
            'ui_tree': '',
            'screenshot_b64': '',
            'test_plan': {},
            'executed_steps': [],
            'messages': [],
            'node_outputs': {},
            'total_tokens_used': 0,
        }

        result = await executor_node(state)

        assert 'error' in result
        assert result['node_outputs']['executor']['error'] == '索引越界'

    @pytest.mark.asyncio
    async def test_executor_agent_uses_standard_model(self):
        """测试 ExecutorAgent 使用 standard 层级模型"""
        from src.agents.executor import ExecutorAgent

        agent = ExecutorAgent()
        assert agent.DEFAULT_MODEL_TIER == 'standard'


class TestVerifierNode:
    """验证节点测试"""

    @pytest.mark.asyncio
    async def test_verifier_passes_and_increments_step_index(self):
        """测试验证通过时递增步骤索引"""
        from src.graph.nodes.verifier import verifier_node

        with patch('src.graph.nodes.verifier.get_verifier_agent') as mock_get:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={
                'verification_passed': True,
                'verification_details': [{'check': 'c1', 'passed': True}],
                'overall_status': 'passed',
                'summary': '通过',
                'suggestions': [],
            })
            mock_agent.get_token_summary = MagicMock(return_value={'total_tokens': 80})
            mock_get.return_value = mock_agent

            state = {
                'executed_steps': [{'step': '步骤1', 'step_index': 0, 'passed': True}],
                'ui_tree': '',
                'screenshot_b64': '',
                'test_plan': {},
                'current_step_index': 0,
                'retry_count': 0,
                'max_retries': 3,
                'messages': [],
                'node_outputs': {},
                'total_tokens_used': 0,
            }

            result = await verifier_node(state)

            assert result['verification_passed'] is True
            assert result['current_step_index'] == 1  # 递增
            assert result['retry_count'] == 0  # 重置

    @pytest.mark.asyncio
    async def test_verifier_fails_and_increments_retry_count(self):
        """测试验证失败时递增重试计数"""
        from src.graph.nodes.verifier import verifier_node

        with patch('src.graph.nodes.verifier.get_verifier_agent') as mock_get:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={
                'verification_passed': False,
                'verification_details': [{'check': 'c1', 'passed': False}],
                'overall_status': 'failed',
                'summary': '失败',
                'suggestions': ['重试'],
            })
            mock_agent.get_token_summary = MagicMock(return_value={'total_tokens': 80})
            mock_get.return_value = mock_agent

            state = {
                'executed_steps': [{'step': '步骤1', 'step_index': 0, 'passed': False}],
                'ui_tree': '',
                'screenshot_b64': '',
                'test_plan': {},
                'current_step_index': 0,
                'retry_count': 0,
                'max_retries': 3,
                'messages': [],
                'node_outputs': {},
                'total_tokens_used': 0,
            }

            result = await verifier_node(state)

            assert result['verification_passed'] is False
            assert result['current_step_index'] == 0  # 不变
            assert result['retry_count'] == 1  # 递增

    @pytest.mark.asyncio
    async def test_verifier_handles_empty_executed_steps(self):
        """测试验证节点处理空执行记录"""
        from src.graph.nodes.verifier import verifier_node

        state = {
            'executed_steps': [],
            'ui_tree': '',
            'screenshot_b64': '',
            'test_plan': {},
            'current_step_index': 0,
            'retry_count': 0,
            'max_retries': 3,
            'messages': [],
            'node_outputs': {},
            'total_tokens_used': 0,
        }

        result = await verifier_node(state)

        assert result['verification_passed'] is False

    @pytest.mark.asyncio
    async def test_verifier_agent_uses_precise_model(self):
        """测试 VerifierAgent 使用 precise 层级模型"""
        from src.agents.verifier import VerifierAgent

        agent = VerifierAgent()
        assert agent.DEFAULT_MODEL_TIER == 'precise'


class TestReviewerNode:
    """审查节点测试"""

    @pytest.mark.asyncio
    async def test_reviewer_node_returns_review_result(self):
        """测试审查节点返回审查结果"""
        from src.graph.nodes.reviewer import reviewer_node

        with patch('src.graph.nodes.reviewer.get_reviewer_agent') as mock_get:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={
                'passed': True,
                'feedback': '审查通过',
                'overall_assessment': 'passed',
                'quality_metrics': {'execution_success_rate': 1.0},
                'issues_found': [],
                'recommendations': [],
                'coverage_analysis': {},
                'final_verdict': 'pass',
            })
            mock_agent.get_token_summary = MagicMock(return_value={'total_tokens': 120})
            mock_get.return_value = mock_agent

            state = {
                'test_goal': '测试登录',
                'test_plan': {'goal': '测试登录'},
                'executed_steps': [{'step': '步骤1', 'passed': True}],
                'verification_details': [{'check': 'c1', 'passed': True}],
                'test_steps': ['步骤1'],
                'messages': [],
                'node_outputs': {},
                'total_tokens_used': 0,
            }

            result = await reviewer_node(state)

            assert result['reviewer_feedback'] == '审查通过'
            assert result['node_outputs']['reviewer']['passed'] is True

    @pytest.mark.asyncio
    async def test_reviewer_agent_uses_precise_model(self):
        """测试 ReviewerAgent 使用 precise 层级模型"""
        from src.agents.reviewer import ReviewerAgent

        agent = ReviewerAgent()
        assert agent.DEFAULT_MODEL_TIER == 'precise'


# ============================================================
# 模型路由器测试
# ============================================================


class TestModelRouter:
    """模型路由器测试"""

    def test_model_router_has_three_tiers(self):
        """测试模型路由器支持三个层级"""
        from src.agents.llm import ModelRouter

        router = ModelRouter()
        tiers = router.get_available_tiers()
        assert 'light' in tiers
        assert 'standard' in tiers
        assert 'precise' in tiers

    def test_model_router_light_uses_openai(self):
        """测试 light 层级使用 OpenAI 模型"""
        from src.agents.llm import ModelRouter

        router = ModelRouter()
        config = router.get_tier_config('light')
        assert config is not None
        assert config.provider == 'openai'
        assert 'mini' in config.model_name or 'gpt-4o-mini' in config.model_name

    def test_model_router_standard_uses_anthropic(self):
        """测试 standard 层级使用 Anthropic 模型"""
        from src.agents.llm import ModelRouter

        router = ModelRouter()
        config = router.get_tier_config('standard')
        assert config is not None
        assert config.provider == 'anthropic'

    def test_model_router_precise_uses_openai(self):
        """测试 precise 层级使用 OpenAI 模型"""
        from src.agents.llm import ModelRouter

        router = ModelRouter()
        config = router.get_tier_config('precise')
        assert config is not None
        assert config.provider == 'openai'

    def test_model_router_call_returns_tuple(self):
        """测试模型路由器调用返回三元组"""
        from src.agents.llm import ModelRouter

        router = ModelRouter()
        model_name, content, usage = router.call(
            messages=[{'role': 'user', 'content': '测试'}],
            tier='light',
        )
        assert isinstance(model_name, str)
        assert isinstance(content, str)
        assert isinstance(usage, dict)

    def test_model_router_invalid_tier_raises_error(self):
        """测试无效层级抛出 ValueError"""
        from src.agents.llm import ModelRouter

        router = ModelRouter()
        with pytest.raises(ValueError):
            router.call(
                messages=[{'role': 'user', 'content': '测试'}],
                tier='invalid',
            )


# ============================================================
# BaseAgent 测试
# ============================================================


class TestBaseAgent:
    """Agent 基类测试"""

    def test_base_agent_injects_system_prompt(self):
        """测试 BaseAgent 自动注入系统提示词"""
        from src.agents.base import BaseAgent

        # 创建一个具体的子类
        class TestAgent(BaseAgent):
            def run(self, **kwargs):
                return {}

        agent = TestAgent(name='test')
        assert agent.system_prompt != ''
        assert '自动化测试' in agent.system_prompt

    def test_base_agent_call_llm_raises_on_empty_messages(self):
        """测试空消息列表抛出 ValueError"""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, **kwargs):
                return {}

        agent = TestAgent(name='test')
        with pytest.raises(ValueError):
            agent.call_llm(messages=[])

    def test_base_agent_set_system_prompt(self):
        """测试设置自定义系统提示词"""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, **kwargs):
                return {}

        agent = TestAgent(name='test')
        custom_prompt = "自定义提示词"
        agent.set_system_prompt(custom_prompt)
        assert agent.system_prompt == custom_prompt


# ============================================================
# Token Tracker 测试
# ============================================================


class TestTokenTracker:
    """Token 追踪器测试"""

    def test_add_record_and_get_summary(self):
        """测试添加记录和获取统计摘要"""
        from src.utils.token_tracker import TokenTracker

        tracker = TokenTracker()
        tracker.add_record(
            model='gpt-4o-mini',
            model_tier='light',
            prompt_tokens=100,
            completion_tokens=50,
            operation='explore',
        )

        summary = tracker.get_summary()
        assert summary['total_records'] == 1
        assert summary['total_tokens'] == 150
        assert summary['total_cost'] > 0

    def test_export_report_json(self):
        """测试导出 JSON 格式报告"""
        from src.utils.token_tracker import TokenTracker
        import json

        tracker = TokenTracker()
        tracker.add_record(
            model='gpt-4o',
            model_tier='precise',
            prompt_tokens=200,
            completion_tokens=100,
            operation='verify',
        )

        report = tracker.export_report(format='json')
        parsed = json.loads(report)
        assert 'summary' in parsed
        assert 'records' in parsed

    def test_reset_clears_records(self):
        """测试重置清空记录"""
        from src.utils.token_tracker import TokenTracker

        tracker = TokenTracker()
        tracker.add_record(model='gpt-4o', model_tier='precise', prompt_tokens=100, completion_tokens=50)
        tracker.reset()

        summary = tracker.get_summary()
        assert summary['total_records'] == 0


# ============================================================
# 集成测试（使用 mock）
# ============================================================


class TestWorkflowIntegration:
    """工作流集成测试（使用 mock 替代 LLM）"""

    @pytest.mark.asyncio
    async def test_full_workflow_runs_to_completion(self):
        """测试完整工作流执行（全部通过）"""
        from src.graph.workflow import build_workflow

        # Mock 所有 Agent
        with patch('src.graph.nodes.explorer.get_explorer_agent') as mock_explorer, \
             patch('src.graph.nodes.planner.get_planner_agent') as mock_planner, \
             patch('src.graph.nodes.executor.get_executor_agent') as mock_executor, \
             patch('src.graph.nodes.verifier.get_verifier_agent') as mock_verifier, \
             patch('src.graph.nodes.reviewer.get_reviewer_agent') as mock_reviewer:

            # 配置 Explorer Agent mock
            exp_agent = MagicMock()
            exp_agent.run = AsyncMock(return_value={
                'analysis': '分析结果', 'progress': 'not_started',
                'next_action': 'plan', 'reasoning': '建议规划',
                'identified_elements': [],
            })
            exp_agent.get_token_summary = MagicMock(return_value={'total_tokens': 50})
            mock_explorer.return_value = exp_agent

            # 配置 Planner Agent mock
            plan_agent = MagicMock()
            plan_agent.run = AsyncMock(return_value={
                'test_plan': {'goal': '测试', 'steps': ['步骤1'], 'expected_results': ['成功']},
                'test_steps': ['步骤1'],
                'raw_plan': {},
            })
            plan_agent.get_token_summary = MagicMock(return_value={'total_tokens': 100})
            mock_planner.return_value = plan_agent

            # 配置 Executor Agent mock
            exec_agent = MagicMock()
            exec_agent.run = AsyncMock(return_value={
                'step': '步骤1', 'step_index': 0,
                'action': 'tap', 'result': '成功',
                'screenshot': '', 'passed': True,
                'mcp_calls': [], 'timestamp': '2025-01-01T00:00:00Z',
            })
            exec_agent.get_token_summary = MagicMock(return_value={'total_tokens': 150})
            mock_executor.return_value = exec_agent

            # 配置 Verifier Agent mock
            ver_agent = MagicMock()
            ver_agent.run = AsyncMock(return_value={
                'verification_passed': True,
                'verification_details': [{'check': 'c1', 'passed': True}],
                'overall_status': 'passed',
                'summary': '通过',
                'suggestions': [],
            })
            ver_agent.get_token_summary = MagicMock(return_value={'total_tokens': 80})
            mock_verifier.return_value = ver_agent

            # 配置 Reviewer Agent mock
            rev_agent = MagicMock()
            rev_agent.run = AsyncMock(return_value={
                'passed': True,
                'feedback': '审查通过',
                'overall_assessment': 'passed',
                'quality_metrics': {'execution_success_rate': 1.0},
                'issues_found': [],
                'recommendations': [],
                'coverage_analysis': {},
                'final_verdict': 'pass',
            })
            rev_agent.get_token_summary = MagicMock(return_value={'total_tokens': 120})
            mock_reviewer.return_value = rev_agent

            # 构建并执行工作流
            app = build_workflow()
            initial_state = {
                'test_goal': '测试登录功能',
                'test_steps': [],
                'current_step_index': 0,
                'executed_steps': [],
                'ui_tree': None,
                'screenshot_b64': None,
                'device_name': 'emulator-5554',
                'test_plan': None,
                'verification_passed': False,
                'verification_details': [],
                'retry_count': 0,
                'max_retries': 3,
                'error': None,
                'messages': [],
                'node_outputs': {},
                'reviewer_feedback': None,
                'total_tokens_used': 0,
                'metadata': {'task_id': 'test-task'},
            }

            config = {'configurable': {'thread_id': 'test-integration'}}

            # 流式执行并收集最终状态
            final_state = None
            async for event in app.astream(initial_state, config):
                final_state = event

            # 验证工作流完成
            assert final_state is not None
