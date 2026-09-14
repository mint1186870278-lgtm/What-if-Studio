from __future__ import annotations

import asyncio

from src.agents import langgraph_service as langgraph


class _Chunk:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    async def astream(self, messages):
        system = str(messages[0].content)
        if "Critic" in system or "总评导演" in system:
            yield _Chunk(
                'editing: ok\nFINAL_JSON {"final_script":"测试脚本",'
                '"edit_instructions":"剪辑", "audio_design":"配乐",'
                '"material_selection":"素材", "new_shot_description":"镜头"}'
            )
        else:
            yield _Chunk("JOIN: 继续讨论")


def test_native_interrupt_command_resume_with_sqlite(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoints.sqlite"
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(checkpoint_path))
    monkeypatch.setattr(langgraph, "_resolve_llm_config", lambda: {"api_key": "test", "base_url": "", "model": "fake"})
    monkeypatch.setattr(langgraph, "_get_llm", lambda *args, **kwargs: _FakeLLM())
    monkeypatch.setattr(langgraph, "_graph_instance", None)
    monkeypatch.setattr(langgraph, "_graph_checkpointer", None)

    async def run():
        first = []
        async for event in langgraph.run_langgraph_discussion_stream(
            "测试暂停恢复", session_id="native-test-thread"
        ):
            first.append(event)
        assert [event["type"] for event in first][-2:] == ["awaiting_input", "paused"]
        state = await langgraph.get_discussion_state("native-test-thread")
        assert state and state["paused"] is True

        resumed = []
        async for event in langgraph.resume_langgraph_discussion_stream(
            "native-test-thread", {"selected_option": "保持当前方向"}
        ):
            resumed.append(event)
        assert resumed[0]["type"] == "answer_applied"
        assert resumed[-2]["type"] == "script"
        assert resumed[-1]["type"] == "task_result"
        final_state = await langgraph.get_discussion_state("native-test-thread")
        assert final_state and final_state["paused"] is False
        assert final_state["script"] == "测试脚本"

    asyncio.run(run())
