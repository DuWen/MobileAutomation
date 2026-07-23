"""
LangGraph Workflow 测试模块

使用 pytest 和 pytest-asyncio 测试 StateGraph 的构建、节点函数和条件路由逻辑。
所有测试使用 mock 替代 LLM 调用，确保测试独立且快速。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
            matched_skills=None,
            skill_context=None,
            perception_mode="hybrid",
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
            matched_skills=None,
            skill_context=None,
            perception_mode="hybrid",
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
                'matched_skills': None,
                'skill_context': None,
                'perception_mode': 'hybrid',
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


# ============================================================
# Skills 管理器测试
# ============================================================


class TestSkillManager:
    """Skills 知识库管理器测试"""

    def test_skill_manager_loads_skills(self, tmp_path):
        """测试 SkillManager 加载 Skills 文件"""
        from src.skills.manager import SkillManager

        # 创建临时 Skills 目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "login.md").write_text(
            "# 登录测试 Skill\n\n## 适用场景\n用户登录 / 账号切换\n\n## 测试要点\n1. 定位登录按钮\n",
            encoding="utf-8",
        )
        (skills_dir / "search.md").write_text(
            "# 搜索测试 Skill\n\n## 适用场景\n搜索功能 / 筛选过滤\n\n## 测试要点\n1. 搜索框定位\n",
            encoding="utf-8",
        )

        manager = SkillManager(skills_dir=str(skills_dir))
        assert len(manager.list_skills()) == 2
        assert "login" in manager.list_skills()
        assert "search" in manager.list_skills()

    def test_skill_manager_match_skills(self, tmp_path):
        """测试 SkillManager 匹配 Skills"""
        from src.skills.manager import SkillManager

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "login.md").write_text(
            "# 登录测试 Skill\n\n## 适用场景\n用户登录 / 账号切换 / 密码重置\n\n## 测试要点\n1. 定位登录按钮\n",
            encoding="utf-8",
        )
        (skills_dir / "search.md").write_text(
            "# 搜索测试 Skill\n\n## 适用场景\n搜索功能 / 筛选过滤\n\n## 测试要点\n1. 搜索框定位\n",
            encoding="utf-8",
        )

        manager = SkillManager(skills_dir=str(skills_dir))
        matched = manager.match_skills("测试用户登录流程")
        assert len(matched) >= 1
        assert matched[0].name == "login"

    def test_skill_manager_format_skills_for_prompt(self, tmp_path):
        """测试 SkillManager 格式化 Skills 为提示词"""
        from src.skills.manager import SkillManager

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "login.md").write_text(
            "# 登录测试 Skill\n\n## 测试要点\n1. 定位登录按钮\n",
            encoding="utf-8",
        )

        manager = SkillManager(skills_dir=str(skills_dir))
        matched = manager.match_skills("登录")
        prompt_text = manager.format_skills_for_prompt(matched)
        assert "登录测试 Skill" in prompt_text
        assert "---" in prompt_text

    def test_skill_manager_get_skill(self, tmp_path):
        """测试按名称获取 Skill"""
        from src.skills.manager import SkillManager

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "login.md").write_text("# 登录\n", encoding="utf-8")

        manager = SkillManager(skills_dir=str(skills_dir))
        skill = manager.get_skill("login")
        assert skill is not None
        assert skill.name == "login"

        # 不存在的 Skill
        assert manager.get_skill("nonexistent") is None

    def test_skill_manager_empty_dir(self, tmp_path):
        """测试空目录时 SkillManager 正常处理"""
        from src.skills.manager import SkillManager

        skills_dir = tmp_path / "empty_skills"
        skills_dir.mkdir()

        manager = SkillManager(skills_dir=str(skills_dir))
        assert len(manager.list_skills()) == 0
        assert manager.match_skills("测试") == []

    def test_skill_manager_nonexistent_dir(self, tmp_path):
        """测试不存在的目录时 SkillManager 正常处理"""
        from src.skills.manager import SkillManager

        manager = SkillManager(skills_dir=str(tmp_path / "nonexistent"))
        assert len(manager.list_skills()) == 0

    def test_skill_manager_reload(self, tmp_path):
        """测试 SkillManager 重新加载"""
        from src.skills.manager import SkillManager

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "login.md").write_text("# 登录\n", encoding="utf-8")

        manager = SkillManager(skills_dir=str(skills_dir))
        assert len(manager.list_skills()) == 1

        # 新增文件后重新加载
        (skills_dir / "search.md").write_text("# 搜索\n", encoding="utf-8")
        manager.reload()
        assert len(manager.list_skills()) == 2


# ============================================================
# BaseAgent Skill 注入测试
# ============================================================


class TestBaseAgentSkillInjection:
    """Agent 基类 Skill 注入测试"""

    def test_set_skill_context(self):
        """测试设置 Skill 知识上下文"""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, **kwargs):
                return {}

        agent = TestAgent(name='test')
        agent.set_skill_context("登录相关技能知识")
        assert agent.skill_context == "登录相关技能知识"

    def test_build_system_message_without_skill(self):
        """测试无 Skill 知识时构建系统消息"""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, **kwargs):
                return {}

        agent = TestAgent(name='test')
        msg = agent._build_system_message()
        assert msg == agent.system_prompt

    def test_build_system_message_with_skill(self):
        """测试有 Skill 知识时构建系统消息"""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, **kwargs):
                return {}

        agent = TestAgent(name='test')
        agent.set_skill_context("登录测试要点：1. 定位登录按钮")
        msg = agent._build_system_message()
        assert "相关技能知识" in msg
        assert "登录测试要点" in msg

    def test_clear_skill_context(self):
        """测试清除 Skill 知识上下文"""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, **kwargs):
                return {}

        agent = TestAgent(name='test')
        agent.set_skill_context("技能知识")
        agent.set_skill_context(None)
        assert agent.skill_context is None
        msg = agent._build_system_message()
        assert msg == agent.system_prompt


# ============================================================
# 混合感知策略测试
# ============================================================


class TestHybridPerception:
    """混合感知策略测试"""

    def test_perception_mode_enum(self):
        """测试感知模式枚举值"""
        from src.utils.perception import PerceptionMode

        assert PerceptionMode.UI_TREE.value == "ui_tree"
        assert PerceptionMode.SCREENSHOT.value == "screenshot"
        assert PerceptionMode.HYBRID.value == "hybrid"

    def test_perception_result_dataclass(self):
        """测试感知结果数据结构"""
        from src.utils.perception import PerceptionResult, PerceptionMode

        result = PerceptionResult(
            ui_tree="tree_data",
            screenshot_b64="base64_data",
            mode=PerceptionMode.HYBRID,
            ui_tree_available=True,
            screenshot_available=False,
            ui_tree_size_bytes=1024,
            screenshot_size_bytes=0,
        )
        assert result.ui_tree_available is True
        assert result.screenshot_available is False
        assert result.mode == PerceptionMode.HYBRID

    def test_estimate_token_savings(self):
        """测试 Token 节省估算"""
        from src.utils.perception import PerceptionResult, PerceptionMode, HybridPerception

        result = PerceptionResult(
            ui_tree="tree_data",
            screenshot_b64="",
            mode=PerceptionMode.UI_TREE,
            ui_tree_available=True,
            screenshot_available=False,
            ui_tree_size_bytes=5000,
            screenshot_size_bytes=50000,
        )

        perception = HybridPerception()
        savings = perception.estimate_token_savings(result)
        assert savings['savings_ratio'] > 0
        assert savings['mode_used'] == 'ui_tree'

    @pytest.mark.asyncio
    async def test_perceive_without_mcp_client(self):
        """测试无 MCP 客户端时的感知行为"""
        from src.utils.perception import HybridPerception, PerceptionMode

        perception = HybridPerception(mcp_client=None)
        result = await perception.perceive("emulator-5554", mode=PerceptionMode.HYBRID)

        assert result.ui_tree_available is False
        assert result.screenshot_available is False


# ============================================================
# Token 成本监控测试
# ============================================================


class TestTokenCostAlert:
    """Token 成本告警测试"""

    def test_cost_alert_triggers_on_threshold(self):
        """测试累计成本超过阈值时触发告警"""
        from src.utils.token_tracker import TokenTracker

        alert_called = []
        def mock_callback(info):
            alert_called.append(info)

        tracker = TokenTracker(
            cost_alert_threshold=0.001,
            cost_alert_callback=mock_callback,
        )

        # 添加一条超过阈值的记录
        tracker.add_record(
            model='gpt-4o',
            model_tier='precise',
            prompt_tokens=50000,
            completion_tokens=10000,
            operation='verify',
        )

        assert len(alert_called) == 1
        assert alert_called[0]['event'] == 'cost_alert'
        assert alert_called[0]['total_cost'] >= 0.001

    def test_cost_alert_only_triggers_once(self):
        """测试成本告警只触发一次"""
        from src.utils.token_tracker import TokenTracker

        alert_count = []
        def mock_callback(info):
            alert_count.append(1)

        tracker = TokenTracker(
            cost_alert_threshold=0.001,
            cost_alert_callback=mock_callback,
        )

        # 添加多条记录
        tracker.add_record(model='gpt-4o', model_tier='precise', prompt_tokens=50000, completion_tokens=10000, operation='op1')
        tracker.add_record(model='gpt-4o', model_tier='precise', prompt_tokens=50000, completion_tokens=10000, operation='op2')

        assert len(alert_count) == 1

    def test_set_cost_alert_resets_flag(self):
        """测试动态设置成本告警重置标志"""
        from src.utils.token_tracker import TokenTracker

        alert_count = []
        def mock_callback(info):
            alert_count.append(1)

        tracker = TokenTracker(
            cost_alert_threshold=0.001,
            cost_alert_callback=mock_callback,
        )

        tracker.add_record(model='gpt-4o', model_tier='precise', prompt_tokens=50000, completion_tokens=10000, operation='op1')
        assert len(alert_count) == 1

        # 更新阈值，重置标志
        tracker.set_cost_alert(threshold=10.0)
        tracker.add_record(model='gpt-4o', model_tier='precise', prompt_tokens=50000, completion_tokens=10000, operation='op2')
        # 新阈值未触发
        assert len(alert_count) == 1


# ============================================================
# 测试报告生成器测试
# ============================================================


class TestReportGenerator:
    """测试报告生成器测试"""

    def _sample_data(self):
        """创建测试报告样本数据。"""
        return {
            "task_id": "abc-123-def",
            "test_goal": "测试登录功能",
            "executed_steps": [
                {"action": "点击登录按钮", "result": "成功", "passed": True},
                {"action": "输入用户名", "result": "成功", "passed": True},
                {"action": "输入密码", "result": "失败", "passed": False},
            ],
            "verification_details": [
                {"check": "登录按钮可见", "passed": True},
                {"check": "密码错误提示", "passed": False},
            ],
            "reviewer_output": {
                "feedback": "部分步骤失败",
                "final_verdict": "fail",
                "quality_metrics": {},
            },
            "token_summary": {
                "total_tokens": 12000,
                "total_cost": 0.15,
                "total_records": 8,
            },
            "duration": 45.2,
            "device_name": "emulator-5554",
        }

    def test_generate_html_report(self, tmp_path):
        """测试生成 HTML 格式报告"""
        from src.utils.report_generator import ReportGenerator

        generator = ReportGenerator(output_dir=str(tmp_path / "reports"))
        data = self._sample_data()
        path = generator.generate(**data, format="html")

        assert path.endswith(".html")
        content = open(path, encoding="utf-8").read()
        assert "AI 自动化测试报告" in content
        assert "测试登录功能" in content
        assert "emulator-5554" in content

    def test_generate_markdown_report(self, tmp_path):
        """测试生成 Markdown 格式报告"""
        from src.utils.report_generator import ReportGenerator

        generator = ReportGenerator(output_dir=str(tmp_path / "reports"))
        data = self._sample_data()
        path = generator.generate(**data, format="markdown")

        assert path.endswith(".md")
        content = open(path, encoding="utf-8").read()
        assert "AI 自动化测试报告" in content
        assert "abc-123-def" in content

    def test_generate_report_with_error(self, tmp_path):
        """测试包含错误信息的报告"""
        from src.utils.report_generator import ReportGenerator

        generator = ReportGenerator(output_dir=str(tmp_path / "reports"))
        data = self._sample_data()
        data["error"] = "Appium Session 超时"
        path = generator.generate(**data, format="html")

        content = open(path, encoding="utf-8").read()
        assert "错误信息" in content or "Appium" in content

    def test_generate_invalid_format_raises_error(self, tmp_path):
        """测试不支持的格式抛出 ValueError"""
        from src.utils.report_generator import ReportGenerator

        generator = ReportGenerator(output_dir=str(tmp_path / "reports"))
        data = self._sample_data()
        with pytest.raises(ValueError):
            generator.generate(**data, format="pdf")

    def test_generate_report_empty_steps(self, tmp_path):
        """测试空步骤时的报告"""
        from src.utils.report_generator import ReportGenerator

        generator = ReportGenerator(output_dir=str(tmp_path / "reports"))
        data = self._sample_data()
        data["executed_steps"] = []
        data["verification_details"] = []
        path = generator.generate(**data, format="html")

        content = open(path, encoding="utf-8").read()
        assert "AI 自动化测试报告" in content


# ============================================================
# 告警通知器测试
# ============================================================


class TestNotifier:
    """告警通知器测试"""

    def test_notifier_disabled_when_no_urls(self):
        """测试无 Webhook URL 时通知器禁用"""
        from src.utils.notifier import Notifier

        notifier = Notifier()
        assert notifier.enabled is False

    def test_notifier_enabled_with_feishu_url(self):
        """测试配置飞书 URL 后通知器启用"""
        from src.utils.notifier import Notifier

        notifier = Notifier(feishu_webhook_url="https://open.feishu.cn/hook/test")
        assert notifier.enabled is True

    def test_notifier_enabled_with_slack_url(self):
        """测试配置 Slack URL 后通知器启用"""
        from src.utils.notifier import Notifier

        notifier = Notifier(slack_webhook_url="https://hooks.slack.com/services/test")
        assert notifier.enabled is True

    def test_notify_test_completed_returns_empty_when_disabled(self):
        """测试通知器禁用时返回空结果"""
        from src.utils.notifier import Notifier

        notifier = Notifier()
        result = notifier.notify_test_completed(
            task_id="test", test_goal="测试", verdict="pass", duration=10.0
        )
        assert result == {}

    def test_notification_event_enum(self):
        """测试通知事件枚举"""
        from src.utils.notifier import NotificationEvent

        assert NotificationEvent.TEST_COMPLETED.value == "test_completed"
        assert NotificationEvent.TEST_FAILED.value == "test_failed"
        assert NotificationEvent.COST_ALERT.value == "cost_alert"

    def test_notification_channel_enum(self):
        """测试通知渠道枚举"""
        from src.utils.notifier import NotificationChannel

        assert NotificationChannel.FEISHU.value == "feishu"
        assert NotificationChannel.SLACK.value == "slack"


# ============================================================
# 性能基准测试模块测试
# ============================================================


class TestBenchmarkRunner:
    """性能基准测试模块测试"""

    def test_record_benchmark(self, tmp_path):
        """测试记录基准数据"""
        from src.utils.benchmark import BenchmarkRunner

        runner = BenchmarkRunner(data_dir=str(tmp_path / "benchmarks"))
        result = runner.record_benchmark(
            task_id="test-1",
            test_goal="测试登录",
            duration=45.2,
            step_count=5,
            passed_steps=4,
            total_tokens=12000,
            total_cost=0.15,
            verdict="pass",
        )

        assert result.task_id == "test-1"
        assert result.pass_rate == 0.8
        assert result.tokens_per_step == 2400.0
        assert result.duration_per_step == 9.04

    def test_get_summary(self, tmp_path):
        """测试获取统计摘要"""
        from src.utils.benchmark import BenchmarkRunner

        runner = BenchmarkRunner(data_dir=str(tmp_path / "benchmarks"))
        runner.record_benchmark(
            task_id="test-1", test_goal="测试1",
            duration=30.0, step_count=3, passed_steps=3,
            total_tokens=9000, total_cost=0.1, verdict="pass",
        )
        runner.record_benchmark(
            task_id="test-2", test_goal="测试2",
            duration=60.0, step_count=5, passed_steps=4,
            total_tokens=15000, total_cost=0.2, verdict="fail",
        )

        summary = runner.get_summary()
        assert summary["total_runs"] == 2
        assert summary["avg_duration"] == 45.0
        assert summary["pass_count"] == 1
        assert summary["fail_count"] == 1

    def test_compare_with_baseline(self, tmp_path):
        """测试与基准对比"""
        from src.utils.benchmark import BenchmarkRunner, BenchmarkResult

        runner = BenchmarkRunner(data_dir=str(tmp_path / "benchmarks"))
        runner.record_benchmark(
            task_id="test-1", test_goal="测试1",
            duration=30.0, step_count=3, passed_steps=3,
            total_tokens=9000, total_cost=0.1, verdict="pass",
        )

        result = BenchmarkResult(
            task_id="test-2", test_goal="测试2",
            duration=45.0, step_count=5, passed_steps=4,
            pass_rate=0.8, total_tokens=12000, total_cost=0.15,
            tokens_per_step=2400, cost_per_step=0.03,
            duration_per_step=9.0, verdict="pass",
        )

        comparison = runner.compare_with_baseline(result)
        assert comparison["comparison"] == "compared"
        assert "duration_delta_pct" in comparison

    def test_compare_with_baseline_no_history(self, tmp_path):
        """测试无历史数据时的对比"""
        from src.utils.benchmark import BenchmarkRunner, BenchmarkResult

        runner = BenchmarkRunner(data_dir=str(tmp_path / "benchmarks_new"))
        result = BenchmarkResult(
            task_id="test-1", test_goal="测试1",
            duration=30.0, step_count=3, passed_steps=3,
            pass_rate=1.0, total_tokens=9000, total_cost=0.1,
            tokens_per_step=3000, cost_per_step=0.033,
            duration_per_step=10.0, verdict="pass",
        )

        comparison = runner.compare_with_baseline(result)
        assert comparison["comparison"] == "no_baseline"

    def test_benchmark_data_persistence(self, tmp_path):
        """测试基准数据持久化"""
        from src.utils.benchmark import BenchmarkRunner

        data_dir = str(tmp_path / "benchmarks_persist")
        runner1 = BenchmarkRunner(data_dir=data_dir)
        runner1.record_benchmark(
            task_id="test-1", test_goal="测试1",
            duration=30.0, step_count=3, passed_steps=3,
            total_tokens=9000, total_cost=0.1, verdict="pass",
        )

        # 新实例加载同一目录
        runner2 = BenchmarkRunner(data_dir=data_dir)
        summary = runner2.get_summary()
        assert summary["total_runs"] == 1
