"""Pico runtime extended with BioCoreAgent domain and orchestration tools."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from pico import tools as pico_tools
from pico.prompt_prefix import PromptPrefix
from pico.runtime import Pico
from pico.workspace import clip

from .analysis_router import route_analysis_task
from .analysis_verifier import verify_final_answer
from .domain import build_domain_adapters
from .fallback_runner import run_fallback_analysis
from .result_exporter import export_result_table_to_csv, is_csv_export_request


DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s,;\"'<>]+")
PMID_PATTERN = re.compile(r"\bPMID[:\s]*([0-9]{5,12})\b", re.I)
REMEMBER_PATTERN = re.compile(r"(记住|记下来|保存这个|沉淀|写入wiki|存到wiki|remember this|save this|note this)", re.I)
SKILL_PATTERN = re.compile(r"(保存为skill|沉淀为skill|沉淀成skill|以后复用|复用流程|reusable skill|save.*skill)", re.I)


ROLE_TOOL_POLICIES = {
    "explorer": {
        "list_files", "read_file", "search", "bio_seq_inspect",
        "bio_sample_sheet_inspect", "bio_count_matrix_inspect", "file_hash",
        "skill_list", "skill_read", "skill_search", "wiki_search", "wiki_list",
        "kb_cross_search", "bio_query_evidence", "pubmed_search",
        "pubmed_fetch_details", "literature_red_blue_review",
        "code_literature_link_search", "code_literature_link_list",
        "workflow_preflight_check", "workflow_primitive_ledger",
        "transcriptome_capability_list", "transcriptome_state_inspect",
        "transcriptome_plan", "transcriptome_plan_verify", "transcriptome_omicverse_check",
    },
    "planner": {
        "list_files", "read_file", "search", "bio_workflow_sketch",
        "bio_pipeline_plan", "bio_pipeline_supported", "bio_experiment_plan",
        "bio_replication_plan", "skill_list", "skill_read", "skill_search",
        "wiki_search", "kb_cross_search", "pubmed_search",
        "pubmed_fetch_details", "literature_red_blue_review",
        "code_literature_link_search", "code_literature_link_list",
        "workflow_preflight_check", "workflow_primitive_ledger", "workflow_plan_prepare",
        "transcriptome_capability_list", "transcriptome_state_inspect",
        "transcriptome_plan", "transcriptome_plan_verify", "transcriptome_omicverse_check",
    },
    "executor": {"*"},
    "verifier": {
        "list_files", "read_file", "search", "run_shell", "file_hash",
        "bio_seq_inspect", "bio_sample_sheet_inspect",
        "bio_count_matrix_inspect", "bio_rnaseq_compare",
        "bio_contingency_test", "bio_regression",
        "bio_deseq2_tissue_vs_rest",
        "workflow_preflight_check", "workflow_primitive_ledger",
        "transcriptome_capability_list", "transcriptome_state_inspect",
        "transcriptome_plan", "transcriptome_plan_verify", "transcriptome_omicverse_check",
    },
    "bio_worker": {
        "list_files", "read_file", "search", "run_shell", "ssh_bash",
        "bio_seq_inspect", "bio_sample_sheet_inspect",
        "bio_count_matrix_inspect", "bio_rnaseq_compare", "bio_report",
        "bio_pipeline_plan", "bio_experiment_plan", "bio_rds_inspect",
        "bio_r_bridge", "bio_contingency_test", "bio_regression",
        "bio_deseq2_quick", "bio_deseq2_tissue_vs_rest", "file_hash", "skill_search", "skill_read",
        "wiki_search", "kb_cross_search", "bio_query_evidence",
        "pubmed_search", "pubmed_fetch_details", "pubmed_literature_review",
        "literature_red_blue_review", "literature_export_xlsx",
        "code_literature_link_save", "code_literature_link_search",
        "code_literature_link_list",
        "workflow_preflight_check", "workflow_primitive_ledger", "workflow_plan_prepare",
        "transcriptome_capability_list", "transcriptome_state_inspect",
        "transcriptome_plan", "transcriptome_plan_verify",
        "transcriptome_provenance_append", "transcriptome_omicverse_check",
        "transcriptome_omicverse_deg",
    },
}


class BioPico(Pico):
    def __init__(
        self,
        *args,
        role: str = "executor",
        orchestrator=None,
        allow_orchestration: bool = True,
        **kwargs,
    ):
        if role not in ROLE_TOOL_POLICIES:
            raise ValueError(f"unknown agent role: {role}")
        self.role = role
        self.orchestrator = orchestrator
        self.allow_orchestration = allow_orchestration
        self._domain_adapters = build_domain_adapters()
        self.last_auto_sedimentations = []
        super().__init__(*args, **kwargs)

    def build_tools(self):
        tools = pico_tools.build_tool_registry(self.tool_context())
        tools.pop("delegate", None)
        for name, adapter in self._domain_adapters.items():
            tools[name] = adapter.pico_spec(self.tool_context())
        if self.orchestrator is not None and self.allow_orchestration:
            tools.update(self.orchestrator.tool_registry(self))

        policy = ROLE_TOOL_POLICIES[self.role]
        if "*" not in policy:
            tools = {name: spec for name, spec in tools.items() if name in policy}
        return tools

    def _apply_tool_allowlist(self, tools):
        if self.allowed_tools is None:
            return tools
        unknown = sorted(set(self.allowed_tools) - set(tools))
        if unknown:
            raise ValueError(f"unknown or role-forbidden tool: {', '.join(unknown)}")
        allowed = set(self.allowed_tools)
        return {name: tool for name, tool in tools.items() if name in allowed}

    def validate_tool(self, name, args):
        if name in pico_tools.BASE_TOOL_SPECS:
            return pico_tools.validate_tool(self.tool_context(), name, args)
        if name in self._domain_adapters:
            return self._domain_adapters[name].validate(self.tool_context(), args or {})
        if (
            self.orchestrator is not None
            and self.allow_orchestration
            and name in self.orchestrator.tool_names
        ):
            return self.orchestrator.validate_tool(name, args or {})
        raise ValueError(f"unknown tool: {name}")

    def build_prefix(self) -> PromptPrefix:
        prefix = super().build_prefix()
        identity = (
            "You are BiocoreagentV2.0, an auditable multi-agent research and coding "
            "harness. You are built on the Pico execution kernel, but your user-facing "
            "identity is BioCoreAgent.\n\n"
            "Core responsibilities:\n"
            "- Help users inspect, modify, test, and package local projects with a safe tool harness.\n"
            "- Orchestrate role-based sub-agents for exploration, planning, execution, and verification.\n"
            "- Manage local skills, MCP extensions, durable project knowledge, and domain tools.\n"
            "- Support rigorous scientific and bioinformatics workflows when those domain tools are relevant.\n"
            "- Explain uncertainty, missing data, tool limits, and verification status explicitly.\n"
        )
        text = prefix.text.replace(
            "You are pico, a small local coding agent working inside a local repository.",
            identity,
            1,
        )
        bio_rules = (
            "\n\nBiocoreagentV2.0 domain contract:\n"
            f"- Active role: {self.role}.\n"
            "- Treat biological input data as immutable evidence.\n"
            "- Distinguish observed facts, computed results, assumptions, and missing information.\n"
            "- Record reference genome/build, sample groups, software parameters, and output provenance.\n"
            "- Never claim a biological analysis succeeded without inspecting its result artifact.\n"
            "- Multi-agent tasks are centrally scheduled; use team tools for genuinely independent work.\n"
            "- For literature reviews, evidence synthesis, mechanism claims, or research strategy, use the literature_red_blue_review tool when evidence rows are available. Red Agent attacks factuality, logical consistency, and citation quality; Blue Agent applies ADD/DELETE/MODIFY/VERIFY repairs; inspect score convergence, oscillation detection, and JSON fallback status before presenting a calibrated conclusion.\n"
            "- When writing or modifying scientific code based on papers, persist a code-literature provenance link with code_literature_link_save so future turns can find the code by DOI/PMID/title/purpose and modify it with the original evidence context.\n"
            "- For literature-review deliverables, prefer literature_export_xlsx over ad-hoc spreadsheet scripts.\n"
            "- For complex research tasks, use OmicOS-style governance: run workflow_preflight_check, inspect workflow_primitive_ledger, compare quick/standard/strict options, and emit workflow_plan_prepare artifacts before high-risk execution.\n"
            "- The CLI/runtime supports streaming final-answer text through provider SSE when the backend supports streaming. Do not claim streaming is impossible; tool-call markup is withheld from the user until parsed, while <final> content may stream to the terminal.\n"
            "- If tools fail repeatedly or no artifacts appear after substantial progress, stop blind retries and enter recovery: summarize failed tool calls, missing environment/data, available partial artifacts, and the smallest next action.\n"
        )
        text = text + bio_rules
        import hashlib

        return replace(prefix, text=text, hash=hashlib.sha256(text.encode("utf-8")).hexdigest())

    def ask(self, user_message, stream_callback=None):
        export_result = self._try_csv_export_shortcut(user_message)
        if export_result is not None:
            self.last_auto_sedimentations = []
            return export_result
        route = route_analysis_task(user_message)
        self.last_analysis_route = route.to_dict()
        if route.analysis_type == "bulk_rnaseq" and route.intent == "run_analysis":
            shortcut = self._try_bio_shortcut(user_message, force=True)
            if shortcut is not None:
                self.last_auto_sedimentations = []
                return verify_final_answer(shortcut)
        if route.analysis_type in {"proteomics", "single_cell", "generic_table"} and route.intent == "run_analysis":
            fallback = self._try_fallback_analysis(user_message, route)
            if fallback is not None:
                self.last_auto_sedimentations = []
                return verify_final_answer(fallback)
        final = super().ask(user_message, stream_callback=stream_callback)
        final = verify_final_answer(final)
        self.last_auto_sedimentations = self._auto_sediment(user_message, final)
        return final

    def _try_csv_export_shortcut(self, user_message: str) -> str | None:
        if not is_csv_export_request(user_message):
            return None
        self._emit_progress("识别为结果表 CSV 导出任务，使用确定性转换路径，不进入工具循环。")
        result = export_result_table_to_csv(self.root, user_message)
        if result.status != "completed":
            return (
                "CSV 导出未完成：没有进入模型工具循环，已在确定性导出层停止。\n\n"
                f"- 原因: {result.message}\n"
                "- 请明确提供源文件路径，例如：deseq2_el_vs_rest_results.txt 输出成 csv。"
            )
        return (
            "CSV 导出完成。\n\n"
            f"- 源文件: {result.source_path}\n"
            f"- CSV 文件: {result.output_path}\n"
            f"- 数据行数: {result.rows}\n"
            f"- 列数: {result.columns}\n"
            f"- 识别分隔符: {result.delimiter}\n\n"
            "这类格式转换现在会直接走确定性路径，不再反复 read_file 或拼 run_shell。"
        )

    def _try_bio_shortcut(self, user_message: str, force: bool = False) -> str | None:
        request = str(user_message)
        lowered = request.lower()
        if not force and not _is_bulk_rnaseq_request(request):
            return None
        self._emit_progress("识别为 bulk RNA-seq / 差异表达任务，进入固定工作流。")
        path = _extract_count_matrix_path(request)
        target = _extract_target_tissue(request)
        route = route_analysis_task(request)
        if not path:
            path = route.input_path
        if not target:
            target = route.target_group
        if path and not target:
            target = _infer_target_tissue_from_matrix_and_text(path, request)
        if not path:
            return (
                "Bulk RNA-seq deterministic workflow requires a count matrix path before execution.\n"
                "Please provide a .txt/.tsv/.csv count matrix and the target group, for example: "
                "C:\\path\\counts.txt, target group el, compare el vs rest."
            )
        if not target:
            return (
                "Bulk RNA-seq deterministic workflow found the count matrix but could not determine the target group.\n"
                f"Count matrix: {path}\n"
                "Please specify the comparison explicitly, for example: el vs rest."
            )
        plan_payload = {}
        transcriptome_plan = {}
        omicverse_payload = {}
        if "transcriptome_plan" in self.tools:
            self._emit_progress("生成轻量能力链计划：检查 count matrix、推断分组、检查 OmicVerse。")
            plan_result = self.execute_tool(
                "transcriptome_plan",
                {
                    "task": request,
                    "count_matrix_path": path,
                    "target_group": target,
                    "mode": "quick",
                },
            )
            try:
                transcriptome_plan = json.loads(plan_result.content)
            except Exception:
                transcriptome_plan = {"raw_result": plan_result.content}
        if "transcriptome_omicverse_check" in self.tools:
            self._emit_progress("检查 OmicVerse 后端是否可用。")
            check_result = self.execute_tool("transcriptome_omicverse_check", {})
            try:
                omicverse_payload = json.loads(check_result.content)
            except Exception:
                omicverse_payload = {"raw_result": check_result.content}
        if omicverse_payload.get("available") and "transcriptome_omicverse_deg" in self.tools:
            self._emit_progress("OmicVerse 可用，执行 OmicVerse pyDEG 差异分析。")
            result = self.execute_tool(
                "transcriptome_omicverse_deg",
                {
                    "count_matrix_path": path,
                    "target_group": target,
                    "output_dir": str(Path(path).resolve().parent),
                    "method": "DEseq2",
                    "alpha": 0.05,
                    "n_cpus": 2,
                },
            )
            try:
                omicverse_result = json.loads(result.content)
            except Exception:
                omicverse_result = {"raw_result": result.content}
            if omicverse_result.get("status") == "completed":
                return (
                    f"OmicVerse-backed bulk RNA-seq analysis completed for {target}-vs-rest.\n"
                    f"- transcriptome steps: {transcriptome_plan.get('steps', [])}\n"
                    f"- full results: {omicverse_result.get('full_results_path')}\n"
                    f"- significant results: {omicverse_result.get('significant_results_path')}\n"
                    f"- summary: {json.dumps(omicverse_result.get('summary', {}), ensure_ascii=False)}"
                )
        if "bio_deseq2_tissue_vs_rest" not in self.tools:
            return (
                "Bulk RNA-seq deterministic workflow was selected, but no executable DE backend is available.\n"
                f"- transcriptome plan: {json.dumps(transcriptome_plan.get('steps', []), ensure_ascii=False)}\n"
                f"- OmicVerse backend: {json.dumps(omicverse_payload, ensure_ascii=False)}"
            )
        if "workflow_plan_prepare" in self.tools:
            self._emit_progress("生成正式计划文档 plan.md / plan.json / delegation.json。")
            plan_result = self.execute_tool(
                "workflow_plan_prepare",
                {
                    "task": request,
                    "input_files": [path],
                    "analysis_type": "deseq2",
                    "target_group": target,
                    "mode": "quick",
                    "output_dir": str(Path(path).resolve().parent / ".biocoreagent" / "plans"),
                },
            )
            try:
                plan_payload = json.loads(plan_result.content)
            except Exception:
                plan_payload = {"raw_result": plan_result.content}
            if not self._approve_generated_plan(plan_payload):
                return _format_plan_rejected_result(
                    target=target,
                    transcriptome_plan=transcriptome_plan,
                    omicverse_payload=omicverse_payload,
                    plan_payload=plan_payload,
                )
        self._emit_progress("计划已通过，执行 DESeq2 fallback 并验证结果文件。")
        result = self.execute_tool(
            "bio_deseq2_tissue_vs_rest",
            {
                "count_matrix_path": path,
                "target_tissue": target,
                "output_dir": str(Path(path).resolve().parent),
                "padj_threshold": 0.05,
                "timeout": 600,
            },
        )
        try:
            payload = json.loads(result.content)
        except Exception:
            payload = {"raw_result": result.content}
        if payload.get("status") == "completed":
            return _format_bulk_rnaseq_result(
                target=target,
                payload=payload,
                transcriptome_plan=transcriptome_plan,
                omicverse_payload=omicverse_payload,
                plan_payload=plan_payload,
            )
        if payload.get("status") == "script_written":
            return _format_bulk_rnaseq_result(
                target=target,
                payload=payload,
                transcriptome_plan=transcriptome_plan,
                omicverse_payload=omicverse_payload,
                plan_payload=plan_payload,
            )
        return _format_bulk_rnaseq_result(
            target=target,
            payload=payload,
            transcriptome_plan=transcriptome_plan,
            omicverse_payload=omicverse_payload,
            plan_payload=plan_payload,
        )

    def _try_fallback_analysis(self, user_message: str, route) -> str | None:
        if not route.fallback_allowed:
            return None
        self._emit_progress(
            f"识别为 {route.analysis_type} 分析任务，当前没有专用封装能力，进入受控 fallback。"
        )
        if not route.input_path:
            return (
                "分析未完成：已进入受控 fallback，但没有找到输入文件路径。\n\n"
                f"- 路由结果: {json.dumps(route.to_dict(), ensure_ascii=False)}\n"
                "- 需要你提供 .csv/.tsv/.txt/.xlsx 等表格路径。\n"
                "- 示例：\"C:\\path\\protein_intensity.csv\" 做蛋白组差异分析。"
            )

        plan_payload = {
            "route": route.to_dict(),
            "preflight_status": "fallback",
            "artifacts": {},
            "message": (
                "No registered domain backend is available. BioCoreAgent will generate one "
                "controlled table-summary script, run it once, and stop on classified errors."
            ),
        }
        if route.requires_plan and not self._approve_generated_plan(plan_payload):
            return (
                "已停止：fallback 计划已生成，但用户未审批继续执行。\n\n"
                f"- 路由结果: {json.dumps(route.to_dict(), ensure_ascii=False)}\n"
                "- 没有运行脚本，也没有生成分析结果。"
            )

        self._emit_progress("写入一个主脚本并立即运行；不进入反复读脚本/改脚本循环。")
        result = run_fallback_analysis(self.root, route.analysis_type, route.input_path)
        payload = result.to_dict()
        if result.status == "completed":
            return (
                "受控 fallback 已完成：已生成表格结构与数值列摘要。\n\n"
                "注意：这不是正式领域分析结论；它用于在专用后端缺失时给出可交接的最小结果。\n\n"
                f"- 分析类型: {route.analysis_type}\n"
                f"- 输入文件: {result.input_path}\n"
                f"- 工作目录: {result.work_dir}\n"
                f"- 主脚本: {result.script_path}\n"
                f"- 摘要文件: {result.summary_path}\n"
                f"- stdout: {result.stdout_path}\n"
                f"- stderr: {result.stderr_path}"
            )
        return (
            "分析未完成：受控 fallback 已停止，并给出可诊断 blocker。\n\n"
            f"- 分析类型: {route.analysis_type}\n"
            f"- 输入文件: {result.input_path}\n"
            f"- 错误类型: {result.error_type}\n"
            f"- blocker: {result.blocker}\n"
            f"- 工作目录: {result.work_dir}\n"
            f"- 主脚本: {result.script_path}\n"
            f"- stdout: {result.stdout_path}\n"
            f"- stderr: {result.stderr_path}\n"
            f"- summary: {result.summary_path}\n\n"
            "下一步最小动作：根据 error_type 修复输入路径、数据格式或环境后重跑；不会继续盲目循环。"
        )

    def _emit_progress(self, message: str) -> None:
        callback = getattr(self, "progress_callback", None)
        if callable(callback):
            callback(message)

    def _approve_generated_plan(self, plan_payload: dict) -> bool:
        callback = getattr(self, "plan_approval_callback", None)
        if callable(callback):
            return bool(callback(plan_payload))
        return True

    def _approve_environment_repair(self, command: str, reason: str = "") -> bool:
        callback = getattr(self, "repair_approval_callback", None)
        if callable(callback):
            return bool(callback(command, reason))
        return False

    def maybe_recovery_diagnosis(self, task_state):
        domain_recovery = self._bio_recovery_diagnosis(task_state)
        if domain_recovery:
            return domain_recovery
        return super().maybe_recovery_diagnosis(task_state)

    def _bio_recovery_diagnosis(self, task_state):
        if int(getattr(task_state, "tool_steps", 0) or 0) < self.recovery_threshold():
            return None
        tool_events = [item for item in self.session.get("history", []) if item.get("role") == "tool"]
        recent_text = "\n".join(str(item.get("content", "")) for item in tool_events[-8:])
        recent_names = [str(item.get("name", "")) for item in tool_events[-8:]]
        if "rlang" in recent_text and "DESeq2" in recent_text:
            blocker = _summarize_bulk_rnaseq_blocker({"stderr_tail": recent_text}, {"status": "backend_missing"})
            return (
                "已进入 Recovery Mode：环境修复兜底。\n\n"
                "继续重复运行 R 脚本不会解决问题。\n\n"
                f"- 当前步数: {task_state.tool_steps}/{self.max_steps}\n"
                f"- 最近工具: {recent_names}\n"
                f"- 主要阻塞原因: {blocker}\n\n"
                "为什么没有自动修复：更新 R 包会修改当前 R 环境，属于外部环境变更，必须经过用户审批。\n\n"
                "建议的最小修复动作：\n"
                "1. 批准后运行：Rscript -e \"install.packages('rlang', repos='https://cloud.r-project.org')\"\n"
                "2. 验证：Rscript -e \"packageVersion('rlang'); packageVersion('DESeq2')\"\n"
                "3. 重新运行同一个转录组任务。\n\n"
                "注意：这不是 count 矩阵或 DESeq2 脚本逻辑错误，而是 R 包版本不满足 DESeq2 的加载要求。"
            )
        if any("invalid arguments for read_file" in str(item.get("content", "")) for item in tool_events[-8:]):
            return (
                "已进入 Recovery Mode：工具参数修复兜底。\n\n"
                "模型连续提交了错误的 read_file 参数。\n\n"
                "正确格式是：\n"
                '<tool>{"name":"read_file","args":{"path":"deseq2_analysis.R","start":1,"end":200}}</tool>\n\n'
                "已启用自动解包兜底：如果模型误传 {\"args\":\"{...}\"}，运行时会尝试解包成真正参数。\n"
                "下一步请不要重复读取同一文件；应运行确定性转录组工具或报告当前 blocker。"
            )
        return None

    def _auto_sediment(self, user_message: str, final_answer: str) -> list[dict]:
        events = []
        turn_tools = self._current_turn_tool_events()
        used_tools = {item.get("name", "") for item in turn_tools}

        if REMEMBER_PATTERN.search(user_message) and "wiki_save" not in used_tools:
            saved = self._auto_save_wiki(user_message, final_answer)
            if saved:
                events.append(saved)

        if SKILL_PATTERN.search(user_message) and "skill_save" not in used_tools:
            saved = self._auto_save_skill(user_message, final_answer)
            if saved:
                events.append(saved)

        if "code_literature_link_save" not in used_tools:
            events.extend(self._auto_save_code_literature_links(user_message, final_answer, turn_tools))

        if events:
            self.memory.append_note(
                "Auto-sedimentation: " + ", ".join(event["kind"] for event in events),
                tags=("auto-sedimentation",),
                source="BioCoreAgent",
                kind="process",
            )
            self.session["memory"] = self.memory.to_dict()
            self.session_path = self.session_store.save(self.session)
        return events

    def _current_turn_tool_events(self) -> list[dict]:
        history = list(self.session.get("history", []))
        start = 0
        for index in range(len(history) - 1, -1, -1):
            if history[index].get("role") == "user":
                start = index
                break
        return [item for item in history[start:] if item.get("role") == "tool"]

    def _auto_save_wiki(self, user_message: str, final_answer: str) -> dict | None:
        try:
            from corecoder.wiki import save_entry

            entry = save_entry(
                title=_title_from_text(user_message, "Auto Memory"),
                content=(
                    "## User request\n"
                    f"{clip(user_message, 600)}\n\n"
                    "## BioCoreAgent answer\n"
                    f"{clip(final_answer, 1800)}\n"
                ),
                tags=["auto", "memory"],
                source_session=str(self.session.get("id", "")),
                root=self.root,
            )
            return {"kind": "wiki", "id": entry["id"], "title": entry["title"]}
        except Exception as exc:
            return {"kind": "wiki_error", "error": str(exc)}

    def _auto_save_skill(self, user_message: str, final_answer: str) -> dict | None:
        try:
            from corecoder.skills import save_skill

            slug = _slug_from_text(user_message)
            meta = save_skill(
                slug=slug,
                title=_title_from_text(user_message, "Auto Skill"),
                summary=clip(final_answer.replace("\n", " "), 180) or "Auto-saved reusable workflow.",
                trigger=clip(user_message, 500),
                procedure=clip(final_answer, 2400),
                pitfalls="Auto-saved from user request; review before relying on it.",
                source_task=clip(user_message, 800),
                tags=["auto", "reusable"],
                overwrite=True,
                root=self.root,
            )
            return {"kind": "skill", "slug": meta.slug, "path": meta.path}
        except Exception as exc:
            return {"kind": "skill_error", "error": str(exc)}

    def _auto_save_code_literature_links(self, user_message: str, final_answer: str, turn_tools: list[dict]) -> list[dict]:
        literature = _extract_literature_mentions(user_message + "\n" + final_answer)
        if not literature:
            return []

        write_events = [
            item for item in turn_tools
            if item.get("name") in {"write_file", "patch_file"} and item.get("args", {}).get("path")
        ]
        if not write_events:
            return []

        results = []
        try:
            from corecoder.provenance import save_code_literature_link
        except Exception as exc:
            return [{"kind": "code_literature_error", "error": str(exc)}]

        for item in write_events:
            raw_path = str(item.get("args", {}).get("path", ""))
            code_path = Path(raw_path)
            absolute = code_path if code_path.is_absolute() else self.root / code_path
            try:
                entry = save_code_literature_link(
                    code_path=str(absolute),
                    code_symbol=_infer_symbol_from_path(raw_path),
                    purpose=clip(user_message, 500),
                    evidence_summary=clip(final_answer, 700),
                    literature=literature,
                    root=self.root,
                )
                results.append({"kind": "code_literature", "id": entry["id"], "code_path": raw_path})
            except Exception as exc:
                results.append({"kind": "code_literature_error", "code_path": raw_path, "error": str(exc)})
        return results

    def build_report(self, task_state):
        report = super().build_report(task_state)
        report["agent_role"] = self.role
        report["auto_sedimentations"] = list(self.last_auto_sedimentations)
        return report


def _title_from_text(text: str, fallback: str) -> str:
    clean = re.sub(r"\s+", " ", str(text)).strip()
    return (clean[:80] or fallback).strip()


def _format_bulk_rnaseq_result(
    target: str,
    payload: dict,
    transcriptome_plan: dict,
    omicverse_payload: dict,
    plan_payload: dict,
) -> str:
    status = str(payload.get("status") or "failed")
    artifacts = dict(plan_payload.get("artifacts", {}) or {})
    blocker = _summarize_bulk_rnaseq_blocker(payload, omicverse_payload)
    lines = []
    if status == "completed":
        lines.append(f"分析完成：{target} vs rest 的 bulk RNA-seq 差异表达分析已完成。")
    elif status == "script_written":
        lines.append("分析未完成：已生成可运行的 DESeq2 脚本，但当前环境还不能执行。")
    else:
        lines.append("分析未完成：固定转录组流程已经运行，但在执行后端时失败。")

    lines.extend(
        [
            "",
            "流程标签：DESeq2 tissue-vs-rest workflow",
            "",
            "本次执行路径：",
            f"- 任务类型：bulk RNA-seq / DESeq2 tissue-vs-rest",
            f"- 比较设计：{target} vs rest",
            f"- OmicVerse：{omicverse_payload.get('status', 'unknown')}",
            f"- DESeq2 fallback：{status}",
        ]
    )
    steps = transcriptome_plan.get("steps") or []
    if steps:
        lines.append(f"- 能力链：{' -> '.join(str(step) for step in steps)}")

    generated = [
        ("metadata", payload.get("metadata_path")),
        ("R script", payload.get("script_path")),
        ("plan.md", artifacts.get("plan_md")),
        ("plan.json", artifacts.get("plan_json")),
        ("delegation.json", artifacts.get("delegation_json")),
    ]
    if status == "completed":
        generated.extend(
            [
                ("full results", payload.get("full_results_path")),
                ("significant results", payload.get("significant_results_path")),
                ("summary", payload.get("summary_path")),
            ]
        )
    existing = [(name, path) for name, path in generated if path]
    if existing:
        lines.extend(["", "已生成："])
        lines.extend(f"- {name}: {path}" for name, path in existing)
    if artifacts:
        lines.append(f"Plan artifacts: {json.dumps(artifacts, ensure_ascii=False)}")

    if status != "completed":
        missing = [
            ("full results", payload.get("full_results_path")),
            ("significant results", payload.get("significant_results_path")),
            ("summary", payload.get("summary_path")),
        ]
        lines.extend(["", "尚未生成或尚未验证："])
        lines.extend(f"- {name}: {path}" for name, path in missing if path)

    if blocker:
        lines.extend(["", "主要阻塞原因：", f"- {blocker}"])

    if status == "completed":
        summary = payload.get("summary") or {}
        if summary:
            lines.extend(["", "结果摘要：", f"- {json.dumps(summary, ensure_ascii=False)}"])
        lines.extend(["", "下一步：", "- 检查 significant results 和 summary，再决定是否绘制火山图/富集分析。"])
    else:
        lines.extend(
            [
                "",
                "下一步：",
                "- 先修复上述环境问题，然后重新运行同一条任务。",
                "- 不需要手动改 R 脚本；当前脚本已经由确定性工具生成。",
            ]
        )
    return "\n".join(lines)


def _format_plan_rejected_result(
    target: str,
    transcriptome_plan: dict,
    omicverse_payload: dict,
    plan_payload: dict,
) -> str:
    artifacts = dict(plan_payload.get("artifacts", {}) or {})
    lines = [
        "已停止：计划已生成，但用户未审批继续执行。",
        "",
        "本次执行路径：",
        "- 任务类型：bulk RNA-seq / DESeq2 tissue-vs-rest",
        f"- 比较设计：{target} vs rest",
        f"- OmicVerse：{omicverse_payload.get('status', 'unknown')}",
    ]
    steps = transcriptome_plan.get("steps") or []
    if steps:
        lines.append(f"- 能力链：{' -> '.join(str(step) for step in steps)}")
    if artifacts:
        lines.extend(
            [
                "",
                "已生成计划：",
                f"- plan.md: {artifacts.get('plan_md')}",
                f"- plan.json: {artifacts.get('plan_json')}",
                f"- delegation.json: {artifacts.get('delegation_json')}",
            ]
        )
    lines.extend(
        [
            "",
            "下一步：",
            "- 检查 plan.md / plan.json。",
            "- 如果认可计划，重新运行同一任务并在审批提示处输入 y。",
        ]
    )
    return "\n".join(lines)


def _summarize_bulk_rnaseq_blocker(payload: dict, omicverse_payload: dict) -> str:
    stderr = str(payload.get("stderr_tail") or "")
    error = str(payload.get("error") or "")
    if "rlang" in stderr and ">=" in stderr:
        match = re.search(r"namespace 'rlang' ([^ ]+) .*>=\s*([0-9.]+)", stderr)
        if match:
            return f"R 包 rlang 版本过低：当前 {match.group(1)}，需要 >= {match.group(2)}。"
        return "R 包 rlang 版本过低，导致 DESeq2 无法加载。"
    if "DESeq2" in stderr and "there is no package" in stderr:
        return "R 环境缺少 DESeq2 包。"
    if "Rscript not found" in error:
        return "当前环境没有找到 Rscript。"
    if omicverse_payload.get("status") == "backend_missing":
        if error:
            return f"OmicVerse 未安装，且 DESeq2 fallback 失败：{error}"
        if stderr:
            return "OmicVerse 未安装，且 DESeq2 fallback 执行失败。"
        return "OmicVerse 未安装。"
    if error:
        return error
    if stderr:
        return stderr.strip().splitlines()[-1]
    return ""


def _slug_from_text(text: str) -> str:
    lowered = str(text).lower()
    tokens = re.findall(r"[a-z0-9]+", lowered)
    if tokens:
        slug = "-".join(tokens[:8])
    else:
        slug = "auto-skill-" + str(abs(hash(text)))[:8]
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug).strip("-")
    if len(slug) < 2:
        slug = "auto-skill"
    return slug[:64]


def _extract_literature_mentions(text: str) -> list[dict]:
    items = []
    seen = set()
    for doi in DOI_PATTERN.findall(text):
        clean = doi.rstrip(".。)")
        key = ("doi", clean.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append({"doi": clean})
    for pmid in PMID_PATTERN.findall(text):
        key = ("pmid", pmid)
        if key in seen:
            continue
        seen.add(key)
        items.append({"pmid": pmid})
    return items


def _infer_symbol_from_path(path: str) -> str:
    name = Path(path).stem
    return name if name else ""


def _extract_count_matrix_path(text: str) -> str:
    quoted = re.findall(r'"([^"]+\.(?:txt|tsv|csv))"', text, flags=re.I)
    if quoted:
        return quoted[0]
    unquoted = re.findall(r"([A-Za-z]:\\[^\s\"']+\.(?:txt|tsv|csv))", text, flags=re.I)
    if unquoted:
        return unquoted[0]
    relative = re.findall(r"([^\s\"']+\.(?:txt|tsv|csv))", text, flags=re.I)
    return relative[0] if relative else ""


def _is_bulk_rnaseq_request(text: str) -> bool:
    lowered = str(text or "").lower()
    if "inspect" in lowered and not any(term in lowered for term in ("deseq2", "差异", "比较", "分析", "vs", "与其余")):
        return False
    strong_keywords = (
        "deseq2",
        "rna-seq",
        "rnaseq",
        "bulk rna",
        "转录组",
        "差异表达",
        "表达矩阵",
        "基因表达",
    )
    if any(keyword in lowered for keyword in strong_keywords):
        return True
    count_keywords = ("count matrix", "counts", "count矩阵")
    action_keywords = ("分析", "比较", "计算", "差异", "运行", "run", "compare", "vs", "与其余")
    return any(keyword in lowered for keyword in count_keywords) and any(keyword in lowered for keyword in action_keywords)


def _extract_target_tissue(text: str) -> str:
    patterns = [
        r"计算\s*([A-Za-z]{1,12})\s*与",
        r"([A-Za-z]{1,12})\s*与其余",
        r"([A-Za-z]{1,12})\s*(?:vs|versus)\s*(?:rest|others)",
        r"target[_\s-]*tissue[:=]\s*([A-Za-z]{1,12})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).lower()
    return ""


def _extract_target_tissue(text: str) -> str:
    patterns = [
        r"计算\s*([A-Za-z]{1,12})\s*与",
        r"([A-Za-z]{1,12})\s*与其余",
        r"([A-Za-z]{1,12})\s*和其余",
        r"([A-Za-z]{1,12})\s*对其余",
        r"([A-Za-z]{1,12})\s*(?:vs|versus)\s*(?:rest|others)",
        r"target[_\s-]*group[:=]\s*([A-Za-z]{1,12})",
        r"target[_\s-]*tissue[:=]\s*([A-Za-z]{1,12})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).lower()
    return ""


def _infer_target_tissue_from_matrix_and_text(path: str, text: str) -> str:
    try:
        matrix = Path(path).resolve()
        header = matrix.read_text(encoding="utf-8-sig").splitlines()[0]
    except Exception:
        return ""
    columns = header.split("\t")
    if len(columns) < 3:
        return ""
    prefixes: set[str] = set()
    for sample in columns[1:]:
        match = re.match(r"([A-Za-z]+)", sample.strip())
        if match:
            prefixes.add(match.group(1).lower())
    lowered = str(text).lower()
    candidates = [prefix for prefix in sorted(prefixes, key=len, reverse=True) if re.search(rf"\b{re.escape(prefix)}\b", lowered)]
    return candidates[0] if len(candidates) == 1 else ""
