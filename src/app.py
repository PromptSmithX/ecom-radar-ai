"""Streamlit Web UI for AI Product Trend Research Tool."""

from __future__ import annotations
import os
import sys
from datetime import datetime
from pathlib import Path

# Đảm bảo thư mục gốc dự án luôn nằm trong sys.path khi chạy bằng Streamlit
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from src.collectors.registry import collect_for_niche
from src.core.cache import cache
from src.core.config import BASE_DIR, load_niches, settings
from src.core.models import FinalReport, Niche
from src.pipeline.runner import PipelineRunner

# Page Configuration
st.set_page_config(
    page_title="AI Product Trend Research Tool",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 12px 16px;
        border: 1px solid #E2E8F0;
    }
</style>
""",
    unsafe_allow_html=True,
)


def init_session():
    if "final_report" not in st.session_state:
        st.session_state.final_report = None
    if "rendered_md" not in st.session_state:
        st.session_state.rendered_md = None
    if "report_file" not in st.session_state:
        st.session_state.report_file = None
    if "evidence_map" not in st.session_state:
        st.session_state.evidence_map = {}


init_session()

# Load default config
default_category, all_niches = load_niches()

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### 🛍️ Cấu hình nghiên cứu")

    category = st.selectbox(
        "Danh mục sản phẩm",
        options=[default_category, "Sách tô màu / Hoạt động", "Áo thun POD", "Đồ gia dụng nhà bếp", "Thú cưng"],
        index=0,
    )

    niche_names = [n.name for n in all_niches]
    selected_niche_names = st.multiselect(
        "Chọn Niches cần chạy:",
        options=niche_names,
        default=niche_names,
    )

    st.markdown("---")
    st.markdown("#### 🤖 Model & Provider")

    writer_provider = st.selectbox(
        "LLM Provider (Viết báo cáo):",
        options=["gemini", "openai", "mock"],
        index=0 if settings.gemini_api_key else (1 if settings.openai_api_key else 2),
        help="Chọn 'mock' nếu muốn test giao diện không cần API key.",
    )

    default_model = "gemini-2.5-flash" if writer_provider == "gemini" else ("gpt-4o-mini" if writer_provider == "openai" else "mock-model")
    writer_model = st.text_input("Tên Model:", value=default_model)

    with st.expander("🔑 Cấu hình API Keys"):
        gemini_key = st.text_input(
            "Gemini API Key:",
            value=settings.gemini_api_key or "",
            type="password",
            help="Lấy tại Google AI Studio",
        )
        openai_key = st.text_input(
            "OpenAI API Key:",
            value=settings.openai_api_key or "",
            type="password",
        )
        tavily_key = st.text_input(
            "Tavily API Key (Tùy chọn):",
            value=settings.tavily_api_key or "",
            type="password",
            help="Dùng cho Web Search thời gian thực. Bỏ trống sẽ dùng dữ liệu đối chuẩn có sẵn.",
        )

    use_cache = st.checkbox("Sử dụng Cache (Chạy nhanh & Tiết kiệm)", value=True)

    st.markdown("---")
    run_button = st.button("🚀 BẮT ĐẦU CHẠY NGHIÊN CỨU", type="primary", use_container_width=True)

    if st.button("🗑️ Xóa toàn bộ Cache", use_container_width=True):
        cache.clear()
        st.success("Đã dọn dẹp cache!")

# ==========================================
# MAIN INTERFACE
# ==========================================
st.markdown('<div class="main-header">📈 AI Product Trend Research Tool</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tự động thu thập tín hiệu xu hướng, phân tích thị trường & đề xuất ý tưởng sản phẩm e-commerce</div>', unsafe_allow_html=True)

# Handle Run Action
if run_button:
    if not selected_niche_names:
        st.error("Vui lòng chọn ít nhất 1 niche để tiến hành nghiên cứu.")
    else:
        selected_niches = [n for n in all_niches if n.name in selected_niche_names]

        # Check API key if not mock
        active_gemini_key = gemini_key.strip() if gemini_key else settings.gemini_api_key
        active_openai_key = openai_key.strip() if openai_key else settings.openai_api_key

        if writer_provider == "gemini" and not active_gemini_key:
            st.warning("⚠️ Chưa phát hiện Gemini API Key. Tự động chuyển sang chế độ Demo (Mock LLM) để minh họa.")
            writer_provider = "mock"
        elif writer_provider == "openai" and not active_openai_key:
            st.warning("⚠️ Chưa phát hiện OpenAI API Key. Tự động chuyển sang chế độ Demo (Mock LLM) để minh họa.")
            writer_provider = "mock"

        progress_container = st.container()
        with progress_container:
            st.markdown("#### ⏳ Tiến trình xử lý")
            progress_bar = st.progress(0.0)
            status_text = st.empty()

        def update_progress(stage: str, fraction: float, msg: str):
            progress_bar.progress(fraction)
            status_text.info(f"**[{stage}]** {msg}")

        runner = PipelineRunner(
            digest_provider=writer_provider,
            digest_model=writer_model,
            writer_provider=writer_provider,
            writer_model=writer_model,
            summary_provider=writer_provider,
            summary_model=writer_model,
            api_key_gemini=active_gemini_key,
            api_key_openai=active_openai_key,
            use_cache=use_cache,
        )

        try:
            final_report, report_path, rendered_md = runner.run(
                selected_niches=selected_niches,
                category=category,
                progress_cb=update_progress,
            )

            st.session_state.final_report = final_report
            st.session_state.rendered_md = rendered_md
            st.session_state.report_file = report_path

            # Also collect evidence map for raw data tab
            evidence_map = {}
            for n in selected_niches:
                evidence_map[n.name] = cache.get_raw("google_suggest", n.name) or []
            st.session_state.evidence_map = evidence_map

            status_text.success("🎉 Hoàn tất toàn bộ quy trình nghiên cứu thị trường!")
        except Exception as e:
            st.error(f"Đã xảy ra lỗi trong quá trình chạy pipeline: {e}")

# ==========================================
# DISPLAY REPORT TABS
# ==========================================
tab_report, tab_raw, tab_cost, tab_about = st.tabs(["📄 Báo cáo Thị trường", "🔍 Dữ liệu Thô (Evidence)", "💰 Thống kê Chi phí", "ℹ️ Hướng dẫn & Nguồn"])

with tab_report:
    if st.session_state.final_report is not None:
        fr = st.session_state.final_report

        # Summary KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Số lượng Niche", len(fr.niche_reports))
        with col2:
            st.metric("Top Ý tưởng", len(fr.top_ideas))
        with col3:
            st.metric("Chi phí ước tính", f"${fr.cost_usd:.4f}")
        with col4:
            st.metric("Tổng Tokens", f"{fr.total_input_tokens + fr.total_output_tokens:,}")

        st.markdown("---")

        # Download button
        st.download_button(
            label="⬇️ Tải báo cáo định dạng Markdown (.md)",
            data=st.session_state.rendered_md or "",
            file_name=st.session_state.report_file.name if st.session_state.report_file else "market_trend_report.md",
            mime="text/markdown",
            type="primary",
        )

        # Render report markdown
        st.markdown(st.session_state.rendered_md, unsafe_allow_html=True)
    else:
        st.info("👋 Chưa có báo cáo nào được tạo. Hãy chọn các niche ở thanh bên trái và bấm **'BẮT ĐẦU CHẠY NGHIÊN CỨU'**.")

with tab_raw:
    st.markdown("### 🗄️ Kiểm chứng Dữ liệu Thô (Anti-Hallucination)")
    st.caption("Mọi thông tin trong báo cáo được tổng hợp trực tiếp từ các bằng chứng có nguồn link dưới đây.")

    if st.session_state.final_report is not None:
        for nr in st.session_state.final_report.niche_reports:
            with st.expander(f"📦 Dữ liệu thô của Niche: {nr.niche}"):
                cached_ev = cache.get_evidence(nr.niche) or []
                if cached_ev:
                    for idx, e in enumerate(cached_ev, 1):
                        st.markdown(f"**{idx}. [{e.source.upper()}]** `{e.kind}` — {e.text}")
                        st.markdown(f"   - **Số liệu/Value:** `{e.value}` | **Link nguồn:** [{e.source_url}]({e.source_url})")
                else:
                    st.write("Không tìm thấy cache bằng chứng.")
    else:
        st.info("Chạy báo cáo để xem dữ liệu thô đã thu thập.")

with tab_cost:
    st.markdown("### 📊 Thống kê Token & Chi phí ước tính")
    if st.session_state.final_report is not None:
        fr = st.session_state.final_report
        st.write(f"- **Model viết chính:** `{fr.models_used.get('writer', 'N/A')}`")
        st.write(f"- **Model digest:** `{fr.models_used.get('digest', 'N/A')}`")
        st.write(f"- **Input Tokens:** `{fr.total_input_tokens:,}`")
        st.write(f"- **Output Tokens:** `{fr.total_output_tokens:,}`")
        st.write(f"- **Tổng chi phí (USD):** `${fr.cost_usd:.5f}` (~ {fr.cost_usd * 25400:.1f} VNĐ)")

        st.markdown("#### Bảng giá tham chiếu (USD / 1M tokens)")
        st.table([
            {"Model": "Gemini 2.5 Flash", "Input / 1M": "$0.075", "Output / 1M": "$0.30"},
            {"Model": "Gemini 1.5 Flash", "Input / 1M": "$0.075", "Output / 1M": "$0.30"},
            {"Model": "GPT-4o mini", "Input / 1M": "$0.150", "Output / 1M": "$0.60"},
        ])
    else:
        st.info("Dữ liệu chi phí sẽ hiển thị sau khi chạy báo cáo.")

with tab_about:
    st.markdown(
        """
### 📖 Về dự án: AI Product Trend Research Tool (MVP)
- **Mục tiêu:** Tự động hóa quá trình nghiên cứu xu hướng và tìm kiếm ý tưởng sản phẩm e-commerce.
- **Nguồn dữ liệu:**
  1. **Google Autocomplete:** Gợi ý từ khóa liên quan thời gian thực.
  2. **Google Trends:** Chỉ số mức độ quan tâm và các từ khóa đang bứt phá (breakout/rising).
  3. **Reddit Community:** Trích xuất các khó khăn, than phiền thực tế từ người dùng (`r/gifts`, `r/BuyItForLife`, `r/AskMen`...).
  4. **Web Search / Market Benchmarks:** Khảo sát đối thủ, mức giá thị trường.
- **Nguyên tắc chống bịa số:** Mọi số liệu trong báo cáo đều được trích xuất từ dữ liệu thô, nếu thiếu sẽ hiển thị *"Không có dữ liệu"*.
"""
    )
