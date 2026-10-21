"""Pipeline Runner: Orchestrates collection, digestion, writing, summarization, and rendering."""

from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from src.collectors.registry import collect_for_niche
from src.core.config import load_niches, settings
from src.core.models import FinalReport, Niche, NicheReport
from src.llm.cost import calculate_cost
from src.llm.factory import get_llm
from src.render.renderer import ReportRenderer
from .digest import digest_step
from .summarizer import summarize_report
from .writer import write_niche_report

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, float, str], None]


class PipelineRunner:
    def __init__(
        self,
        digest_provider: Optional[str] = None,
        digest_model: Optional[str] = None,
        writer_provider: Optional[str] = None,
        writer_model: Optional[str] = None,
        summary_provider: Optional[str] = None,
        summary_model: Optional[str] = None,
        api_key_gemini: Optional[str] = None,
        api_key_openai: Optional[str] = None,
        use_cache: bool = True,
    ):
        self.digest_provider = digest_provider or settings.llm.digest.provider
        self.digest_model = digest_model or settings.llm.digest.model
        self.writer_provider = writer_provider or settings.llm.writer.provider
        self.writer_model = writer_model or settings.llm.writer.model
        self.summary_provider = summary_provider or (writer_provider if writer_provider == "mock" else settings.llm.summary.provider)
        self.summary_model = summary_model or settings.llm.summary.model

        self.api_key_gemini = api_key_gemini or settings.gemini_api_key
        self.api_key_openai = api_key_openai or settings.openai_api_key
        self.use_cache = use_cache

    def _resolve_llm(self, provider: str, model: str):
        key = self.api_key_gemini if provider == "gemini" else self.api_key_openai
        return get_llm(provider, model, api_key=key)

    def run(
        self,
        selected_niches: Optional[List[Niche]] = None,
        category: Optional[str] = None,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Tuple[FinalReport, Path, str]:
        """Executes the full pipeline for the specified niches."""
        default_cat, all_niches = load_niches()
        active_category = category or default_cat
        niches_to_run = selected_niches or all_niches

        if not niches_to_run:
            raise ValueError("No niches specified to run.")

        def notify(stage: str, fraction: float, msg: str):
            if progress_cb:
                progress_cb(stage, fraction, msg)
            logger.info(f"[{stage}] ({int(fraction*100)}%) {msg}")

        notify("INIT", 0.0, f"Bắt đầu pipeline cho {len(niches_to_run)} niche trong danh mục '{active_category}'...")

        # Initialize LLM clients
        digest_llm = self._resolve_llm(self.digest_provider, self.digest_model)
        writer_llm = self._resolve_llm(self.writer_provider, self.writer_model)
        summary_llm = self._resolve_llm(self.summary_provider, self.summary_model)

        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0

        niche_reports: List[NicheReport] = []
        niche_count = len(niches_to_run)

        # Process each niche
        for idx, niche in enumerate(niches_to_run):
            base_fraction = idx / (niche_count + 1)
            step_span = 1.0 / (niche_count + 1)

            # Step 1: Collect
            notify("COLLECT", base_fraction + (step_span * 0.1), f"[{idx+1}/{niche_count}] Đang thu thập dữ liệu thô: {niche.name}...")
            raw_evidence = collect_for_niche(niche)

            # Step 2: Digest
            notify("DIGEST", base_fraction + (step_span * 0.4), f"[{idx+1}/{niche_count}] Đang chuẩn hóa Evidence Pack: {niche.name}...")
            evidence_pack, digest_usage = digest_step(niche, raw_evidence, digest_llm, use_cache=self.use_cache)
            total_input_tokens += digest_usage.input_tokens
            total_output_tokens += digest_usage.output_tokens
            total_cost_usd += calculate_cost(self.digest_model, digest_usage.input_tokens, digest_usage.output_tokens)

            # Step 3: Write Niche Report
            notify("WRITE", base_fraction + (step_span * 0.8), f"[{idx+1}/{niche_count}] Đang viết báo cáo niche: {niche.name}...")
            n_report, write_usage = write_niche_report(niche, evidence_pack, writer_llm)
            total_input_tokens += write_usage.input_tokens
            total_output_tokens += write_usage.output_tokens
            total_cost_usd += calculate_cost(self.writer_model, write_usage.input_tokens, write_usage.output_tokens)

            niche_reports.append(n_report)

        # Step 4: Summarize & Rank
        notify("SUMMARIZE", 0.90, "Đang xếp hạng niche và tuyển chọn top 3 sản phẩm...")
        ranking, top_ideas, sum_usage = summarize_report(niche_reports, summary_llm)
        total_input_tokens += sum_usage.input_tokens
        total_output_tokens += sum_usage.output_tokens
        total_cost_usd += calculate_cost(self.summary_model, sum_usage.input_tokens, sum_usage.output_tokens)

        # Step 5: Render
        notify("RENDER", 0.96, "Đang kết xuất báo cáo Markdown...")
        final_report = FinalReport(
            category=active_category,
            date=datetime.now().strftime("%d/%m/%Y"),
            niche_reports=niche_reports,
            ranking=ranking,
            top_ideas=top_ideas,
            cost_usd=round(total_cost_usd, 4),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            models_used={
                "digest": f"{self.digest_provider}/{self.digest_model}",
                "writer": f"{self.writer_provider}/{self.writer_model}",
                "summary": f"{self.summary_provider}/{self.summary_model}",
            },
        )

        renderer = ReportRenderer()
        saved_path = renderer.save(final_report)
        rendered_md = renderer.render(final_report)

        notify("DONE", 1.0, f"Báo cáo hoàn tất! Đã lưu tại: {saved_path.name}")
        return final_report, saved_path, rendered_md
