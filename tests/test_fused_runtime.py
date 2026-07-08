from pathlib import Path
import json

from pico.providers.clients import FakeModelClient
from pico.run_store import RunStore
from pico.session_store import SessionStore
from pico.workspace import WorkspaceContext

from biocoreagent.runtime import BioPico
from biocoreagent.analysis_router import route_analysis_task


def build_agent(tmp_path: Path, outputs, role="executor"):
    return BioPico(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".biocoreagent" / "sessions"),
        run_store=RunStore(tmp_path / ".biocoreagent" / "runs"),
        approval_policy="auto",
        max_steps=4,
        role=role,
        allow_orchestration=False,
    )


def test_bio_tool_runs_through_pico_loop_and_persists_run(tmp_path):
    matrix = tmp_path / "counts.csv"
    matrix.write_text("gene,s1,s2\nA,10,12\nB,4,5\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"bio_count_matrix_inspect","args":{"file_path":"counts.csv"}}</tool>',
            "<final>Matrix inspected.</final>",
        ],
    )

    result = agent.ask("Inspect counts.csv")

    assert result == "Matrix inspected."
    assert agent.current_task_state.status == "completed"
    assert agent.current_task_state.tool_steps == 1
    assert agent.current_task_state.last_tool == "bio_count_matrix_inspect"
    assert (tmp_path / ".biocoreagent" / "runs" / agent.current_task_state.run_id / "trace.jsonl").exists()


def test_role_tool_boundaries_are_enforced_at_registry_level(tmp_path):
    explorer = build_agent(tmp_path, ["<final>done</final>"], role="explorer")
    planner = build_agent(tmp_path, ["<final>done</final>"], role="planner")
    executor = build_agent(tmp_path, ["<final>done</final>"], role="executor")

    assert "write_file" not in explorer.tools
    assert "run_shell" not in explorer.tools
    assert "bio_pipeline_plan" in planner.tools
    assert "bio_rnaseq_compare" not in planner.tools
    assert "bio_rnaseq_compare" in executor.tools
    assert "ssh_bash" in executor.tools
    assert "pubmed_search" in explorer.tools
    assert "literature_red_blue_review" in planner.tools
    assert "pubmed_literature_review" in executor.tools
    assert "literature_export_xlsx" in executor.tools
    assert "code_literature_link_save" in executor.tools
    assert "code_literature_link_search" in explorer.tools
    assert "bio_deseq2_tissue_vs_rest" in executor.tools
    assert "workflow_preflight_check" in explorer.tools
    assert "workflow_primitive_ledger" in planner.tools
    assert "workflow_plan_prepare" in executor.tools
    assert "transcriptome_omicverse_check" in explorer.tools
    assert "transcriptome_omicverse_deg" in executor.tools


def test_domain_adapter_rejects_workspace_escape(tmp_path):
    agent = build_agent(tmp_path, ["<final>done</final>"])
    result = agent.execute_tool("file_hash", {"file_path": "../outside.txt"})

    assert result.metadata["tool_status"] == "rejected"
    assert "path escapes workspace" in result.content


def test_prompt_identity_is_biocoreagent_not_pico(tmp_path):
    agent = build_agent(tmp_path, ["<final>done</final>"])
    prompt = agent.prefix_state.text

    assert "You are BiocoreagentV2.0" in prompt
    assert "user-facing identity is BioCoreAgent" in prompt
    assert "You are pico, a small local coding agent" not in prompt
    assert "literature_red_blue_review" in prompt


def test_tool_call_with_leading_prose_is_executed(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            'I will write it now.\n<tool name="write_file" path="note.txt"><content>ok</content></tool>',
            "<final>Created note.txt.</final>",
        ],
    )

    result = agent.ask("create a note")

    assert result == "Created note.txt."
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "ok"


def test_explicit_remember_auto_saves_wiki(tmp_path):
    agent = build_agent(tmp_path, ["<final>Important fact saved in answer.</final>"])

    agent.ask("请记住：BioCoreAgent 的文献任务需要红蓝对抗。")

    wiki_path = tmp_path / ".biocoreagent" / "wiki" / "entries.jsonl"
    assert wiki_path.exists()
    assert "红蓝对抗" in wiki_path.read_text(encoding="utf-8")
    assert any(event["kind"] == "wiki" for event in agent.last_auto_sedimentations)


def test_explicit_skill_request_auto_saves_skill(tmp_path):
    agent = build_agent(tmp_path, ["<final>Step 1 inspect evidence. Step 2 run Red Blue review.</final>"])

    agent.ask("把这个文献调研流程沉淀为skill，以后复用。")

    skills = list((tmp_path / ".biocoreagent" / "skills").glob("*.md"))
    assert skills
    assert "Step 1 inspect evidence" in skills[0].read_text(encoding="utf-8")
    assert any(event["kind"] == "skill" for event in agent.last_auto_sedimentations)


def test_scientific_code_with_doi_auto_saves_code_literature_link(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="folding_demo.py"><content>def score():\n    return 1\n</content></tool>',
            "<final>Created code based on DOI 10.1000/fold-demo.</final>",
        ],
    )

    agent.ask("Create folding code using DOI 10.1000/fold-demo.")

    path = tmp_path / ".biocoreagent" / "provenance" / "code_literature_links.jsonl"
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["code_path"].endswith("folding_demo.py")
    assert rows[0]["literature"][0]["doi"] == "10.1000/fold-demo"
    assert any(event["kind"] == "code_literature" for event in agent.last_auto_sedimentations)


def test_deseq2_tissue_shortcut_prepares_workflow_without_model_loop(tmp_path):
    matrix = tmp_path / "counts.txt"
    matrix.write_text(
        "gene\tel1\tel2\tel3\tbr1\tbr2\tbr3\n"
        "g1\t10\t12\t11\t4\t5\t6\n"
        "g2\t1\t2\t3\t20\t19\t18\n",
        encoding="utf-8",
    )
    agent = build_agent(tmp_path, [])

    result = agent.ask(f'"{matrix}"这个是转录组不同组织count，请用deseq2的方法计算el与其余组织的比较结果。')

    assert (
        "DESeq2 tissue-vs-rest workflow" in result
        or "DESeq2 el-vs-rest analysis completed" in result
        or "Preflight/EDA Gate failed" in result
    )
    assert "Plan artifacts:" in result
    assert list((tmp_path / ".biocoreagent" / "plans").glob("*/plan.md"))
    assert agent.current_task_state is None


def test_workflow_governance_tools_emit_preflight_ledger_and_plan(tmp_path):
    matrix = tmp_path / "counts.txt"
    matrix.write_text(
        "gene\tel1\tel2\tbr1\tbr2\n"
        "g1\t10\t12\t4\t5\n"
        "g2\t1\t2\t20\t19\n",
        encoding="utf-8",
    )
    agent = build_agent(tmp_path, [])

    preflight = json.loads(agent.execute_tool(
        "workflow_preflight_check",
        {
            "task": "run deseq2 el vs rest",
            "input_files": [str(matrix)],
            "analysis_type": "deseq2",
            "target_group": "el",
        },
    ).content)
    assert any(check["name"] == "target_replicates" for check in preflight["checks"])

    ledger = json.loads(agent.execute_tool(
        "workflow_primitive_ledger",
        {"task": "run deseq2 el vs rest", "analysis_type": "deseq2", "pick_count": 3},
    ).content)
    assert any(item["id"] == "run_deseq2_tissue_vs_rest" for item in ledger["recommended_primitives"])

    plan = json.loads(agent.execute_tool(
        "workflow_plan_prepare",
        {
            "task": "run deseq2 el vs rest",
            "input_files": [str(matrix)],
            "analysis_type": "deseq2",
            "target_group": "el",
            "output_dir": str(tmp_path / ".biocoreagent" / "plans"),
        },
    ).content)
    assert Path(plan["artifacts"]["plan_md"]).exists()
    assert Path(plan["artifacts"]["plan_json"]).exists()
    assert Path(plan["artifacts"]["delegation_json"]).exists()


def test_transcriptome_capability_layer_prefers_omicverse_backend(tmp_path):
    matrix = tmp_path / "counts.txt"
    matrix.write_text(
        "gene\tel1\tel2\tbr1\tbr2\n"
        "g1\t10\t12\t4\t5\n"
        "g2\t1\t2\t20\t19\n",
        encoding="utf-8",
    )
    agent = build_agent(tmp_path, [])

    contracts = json.loads(agent.execute_tool("transcriptome_capability_list", {}).content)
    names = {item["name"] for item in contracts["capabilities"]}
    assert "check_omicverse_bulk_backend" in names
    assert "omicverse_pydge_tissue_vs_rest" in names

    plan = json.loads(agent.execute_tool(
        "transcriptome_plan",
        {
            "task": "use omicverse / deseq2 for differential expression",
            "count_matrix_path": str(matrix),
            "target_group": "el",
            "mode": "quick",
        },
    ).content)
    assert "check_omicverse_bulk_backend" in plan["steps"]
    assert "omicverse_pydge_tissue_vs_rest" in plan["steps"]
    assert plan["capabilities"][1]["tool"] == "transcriptome_state_inspect"

    check = json.loads(agent.execute_tool("transcriptome_omicverse_check", {}).content)
    assert check["backend"] == "omicverse"

    result = json.loads(agent.execute_tool(
        "transcriptome_omicverse_deg",
        {
            "count_matrix_path": str(matrix),
            "target_group": "el",
            "output_dir": str(tmp_path),
        },
    ).content)
    assert result["status"] in {"backend_missing", "completed", "error"}
    if result["status"] == "backend_missing":
        assert result["backend_check"]["status"] == "backend_missing"


def test_recovery_gate_stops_repeated_invalid_tool_loop(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"run_shell","args":{"args":"command","content":"print(1)"}}</tool>',
            '<tool>{"name":"read_file","args":{"path":"missing.txt"}}</tool>',
            '<tool>{"name":"read_file","args":{"path":"missing.txt"}}</tool>',
            '<tool>{"name":"read_file","args":{"path":"missing.txt"}}</tool>',
        ],
    )
    agent.max_steps = 6

    result = agent.ask("run a complex analysis")

    assert "Recovery Mode" in result
    assert agent.current_task_state.stop_reason == "recovery_gate_triggered"


def test_analysis_router_keeps_inspect_out_of_analysis_execution():
    route = route_analysis_task("Inspect counts.csv")

    assert route.intent == "inspect"
    assert route.analysis_type == "coding"


def test_proteomics_request_uses_controlled_fallback(tmp_path):
    table = tmp_path / "protein_intensity.csv"
    table.write_text(
        "protein,el1,el2,br1,br2\n"
        "P1,10,11,5,6\n"
        "P2,3,4,9,10\n",
        encoding="utf-8",
    )
    agent = build_agent(tmp_path, [])

    result = agent.ask(f'"{table}" 做蛋白组差异分析')

    assert "受控 fallback 已完成" in result
    assert "正式领域分析结论" in result
    fallback_dirs = list(tmp_path.glob("proteomics_fallback_*"))
    assert fallback_dirs
    assert (fallback_dirs[0] / "analysis_script.py").exists()
    assert (fallback_dirs[0] / "summary.json").exists()
    assert (fallback_dirs[0] / "logs" / "run_1.stdout.txt").exists()


def test_final_answer_verifier_rewrites_false_success(tmp_path):
    agent = build_agent(
        tmp_path,
        ["<final>分析完成：脚本已经运行。\n但 stderr 显示 Error: execution halted, exit code 1。</final>"],
    )

    result = agent.ask("summarize failed analysis")

    assert "最终答案校验" in result
    assert "分析未完成" in result


def test_csv_export_shortcut_converts_latest_result_without_tool_loop(tmp_path):
    result_table = tmp_path / "deseq2_el_vs_rest_results.txt"
    result_table.write_text("gene\tlog2FoldChange\tpadj\ng1\t1.2\t0.01\n", encoding="utf-8")
    agent = build_agent(tmp_path, [])

    result = agent.ask("输出成一个csv文件吧")

    csv_path = tmp_path / "deseq2_el_vs_rest_results.csv"
    assert "CSV 导出完成" in result
    assert csv_path.exists()
    assert "gene,log2FoldChange,padj" in csv_path.read_text(encoding="utf-8-sig")
    assert agent.current_task_state is None
