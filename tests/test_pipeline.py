"""Tests for pipeline modules: validator, digest, writer, summarizer, and renderer."""

from __future__ import annotations
import pytest
from src.core.models import Evidence, FinalReport, Idea, KeywordSignal, Niche, NicheReport, RankingItem
from src.llm.factory import get_llm
from src.pipeline.digest import balanced_subset, digest_step, programmatic_digest
from src.pipeline.summarizer import summarize_report
from src.pipeline.validator import ReportValidator
from src.pipeline.writer import write_niche_report
from src.render.renderer import ReportRenderer


@pytest.fixture
def sample_evidence():
    return [
        Evidence(
            source="google_suggest",
            kind="keyword_signal",
            keyword="christmas gift ideas",
            text="Gợi ý tìm kiếm phổ biến",
            value="Autocomplete suggestion",
            source_url="https://google.com/search?q=christmas+gift+ideas",
        ),
        Evidence(
            source="reddit",
            kind="complaint",
            keyword="christmas gift ideas",
            intent="pain",
            subreddit="gifts",
            post_id="123",
            title="What are the most useless gifts people keep buying?",
            snippet="Than phiền quà tặng vô dụng lặp đi lặp lại hàng năm khiến người nhận thất vọng.",
            text="Than phiền quà tặng vô dụng lặp đi lặp lại hàng năm khiến người nhận thất vọng.",
            value=None,
            source_url="https://www.reddit.com/r/gifts/comments/123/",
        ),
    ]


def test_programmatic_digest(sample_evidence):
    digested = programmatic_digest(sample_evidence)
    assert len(digested) == 2
    # Duplicate URLs should be removed
    sample_with_dup = sample_evidence + [sample_evidence[0]]
    assert len(programmatic_digest(sample_with_dup)) == 2


def _make_source_batch(source: str, count: int) -> list[Evidence]:
    """Builds `count` distinct Evidence items (unique source_url each) for a source."""
    return [
        Evidence(
            source=source,
            kind="keyword_signal",
            keyword=f"{source} keyword {i}",
            text=f"{source} evidence item #{i}",
            source_url=f"https://example.com/{source}/{i}",
        )
        for i in range(count)
    ]


def test_balanced_subset_reserves_room_for_every_source():
    """Regression test for the exact bug observed in production: google_suggest (18) +
    serpapi_trends (7) sum to exactly max_items=25, which used to crowd reddit (9) and
    web_search (5) out entirely because programmatic_digest cut off in arrival order."""
    raw_evidence = (
        _make_source_batch("google_suggest", 18)
        + _make_source_batch("serpapi_trends", 7)
        + _make_source_batch("reddit", 9)
        + _make_source_batch("web_search", 5)
    )

    result = balanced_subset(raw_evidence, max_items=25)

    sources_present = {e.source for e in result}
    assert "reddit" in sources_present
    assert "web_search" in sources_present
    assert "google_suggest" in sources_present
    assert "serpapi_trends" in sources_present
    assert len(result) == 25


def test_balanced_subset_prioritises_reddit():
    """When sources compete for a limited cap, reddit (high in source_priority) must
    get at least as many slots as google_suggest (low priority), even though
    google_suggest has far more raw items available."""
    raw_evidence = _make_source_batch("google_suggest", 20) + _make_source_batch("reddit", 5)

    result = balanced_subset(raw_evidence, max_items=10)

    reddit_count = sum(1 for e in result if e.source == "reddit")
    suggest_count = sum(1 for e in result if e.source == "google_suggest")
    assert reddit_count == 5  # all of reddit's items fit, since it's prioritized first
    assert reddit_count >= suggest_count


def test_balanced_subset_dedupes_by_url():
    raw_evidence = _make_source_batch("reddit", 1) * 2  # same object twice -> same source_url
    result = balanced_subset(raw_evidence, max_items=10)
    assert len(result) == 1


def test_balanced_subset_returns_all_when_under_cap():
    raw_evidence = _make_source_batch("reddit", 3) + _make_source_batch("google_suggest", 2)
    result = balanced_subset(raw_evidence, max_items=25)
    assert len(result) == 5


def test_validator_anti_hallucination(sample_evidence):
    fake_url = "https://fake-hallucinated-site.com/xyz"
    niche_report = NicheReport(
        niche="Christmas gift ideas",
        keywords=[
            KeywordSignal(
                keyword="christmas gift ideas",
                signal="tăng",
                source_url=fake_url,  # Hallucinated URL!
            )
        ],
        trend="tăng",
        analysis="Phân tích...",
        customer="Khách hàng...",
        pain_points=["Than phiền 1"],
        competition="Cao",
        price_range="$10 - $20",
        ideas=[
            Idea(
                title="Ý tưởng 1",
                what="Sản phẩm 1",
                for_whom="Đối tượng 1",
                why_now="Lý do 1",
                evidence_refs=[fake_url],
            )
        ],
        score=8,
    )

    validated = ReportValidator.validate_niche_report(niche_report, sample_evidence)
    # The fake URL must be replaced with a legitimate evidence URL
    assert validated.keywords[0].source_url != fake_url
    assert validated.keywords[0].source_url in [e.source_url for e in sample_evidence]
    assert validated.ideas[0].evidence_refs[0] != fake_url
    # Ensure at least 2 ideas exist
    assert len(validated.ideas) >= 2


def test_validator_strips_fabricated_upvotes(sample_evidence):
    niche_report = NicheReport(
        niche="Christmas gift ideas",
        keywords=[
            KeywordSignal(
                keyword="christmas gift ideas",
                signal="Tín hiệu hot (420 upvotes)",
                source_url="https://google.com/search?q=christmas+gift+ideas",
            )
        ],
        trend="tăng",
        analysis="Thảo luận bùng nổ với 1500 upvotes trên mạng xã hội.",
        customer="Khách hàng than phiền (350 upvote)",
        pain_points=["Than phiền quà tặng vô dụng (500 upvotes)"],
        competition="Cao",
        price_range="$10 - $20",
        ideas=[
            Idea(
                title="Ý tưởng 1 (100 upvotes)",
                what="Sản phẩm 1",
                for_whom="Đối tượng 1",
                why_now="Lý do hot với 200 upvotes",
                evidence_refs=["https://google.com/search?q=christmas+gift+ideas"],
            )
        ],
        score=8,
        score_reason="Điểm cao do nhận được 900 upvotes",
    )

    validated = ReportValidator.validate_niche_report(niche_report, sample_evidence)
    # Ensure fabricated upvote counts are purged from all fields
    assert "420 upvotes" not in validated.keywords[0].signal
    assert "1500 upvotes" not in validated.analysis
    assert "350 upvote" not in validated.customer
    assert "500 upvotes" not in validated.pain_points[0]
    assert "100 upvotes" not in validated.ideas[0].title
    assert "200 upvotes" not in validated.ideas[0].why_now
    assert "900 upvotes" not in validated.score_reason


def test_validator_caps_score_without_trend_data(sample_evidence):
    """sample_evidence only has google_suggest + reddit (no serpapi_trends/google_trends),
    so a score of 9 from the LLM must be capped down to reflect the missing trend data."""
    niche_report = NicheReport(
        niche="Christmas gift ideas",
        keywords=[],
        trend="tăng",
        analysis="Phân tích...",
        customer="Khách hàng...",
        pain_points=["Than phiền 1"],
        competition="Cao",
        price_range="$10 - $20",
        ideas=[
            Idea(title="A", what="A", for_whom="A", why_now="A", evidence_refs=[sample_evidence[0].source_url]),
            Idea(title="B", what="B", for_whom="B", why_now="B", evidence_refs=[sample_evidence[1].source_url]),
        ],
        score=9,
    )

    validated = ReportValidator.validate_niche_report(niche_report, sample_evidence)
    assert validated.score <= 7
    assert "[Validator:" in validated.score_reason
    assert "SerpApi" in validated.score_reason or "Trends" in validated.score_reason


def test_validator_keeps_high_score_with_full_sources():
    """When evidence covers trend data, community discussion, and search suggestions,
    the LLM's score of 9 must be left untouched."""
    full_evidence = [
        Evidence(
            source="serpapi_trends", kind="keyword_signal", keyword="kw",
            text="Trend tăng", source_url="https://trends.example.com/1",
        ),
        Evidence(
            source="reddit", kind="complaint", keyword="kw",
            text="Pain point thực tế", source_url="https://reddit.example.com/1",
        ),
        Evidence(
            source="google_suggest", kind="keyword_signal", keyword="kw",
            text="Gợi ý tìm kiếm", source_url="https://suggest.example.com/1",
        ),
        Evidence(
            source="web_search", kind="keyword_signal", keyword="kw",
            text="Kết quả tìm kiếm", source_url="https://web.example.com/1",
        ),
    ]
    niche_report = NicheReport(
        niche="Christmas gift ideas",
        keywords=[],
        trend="tăng",
        analysis="Phân tích...",
        customer="Khách hàng...",
        pain_points=["Than phiền 1"],
        competition="Cao",
        price_range="$10 - $20",
        ideas=[
            Idea(title="A", what="A", for_whom="A", why_now="A", evidence_refs=[full_evidence[0].source_url]),
            Idea(title="B", what="B", for_whom="B", why_now="B", evidence_refs=[full_evidence[1].source_url]),
        ],
        score=9,
    )

    validated = ReportValidator.validate_niche_report(niche_report, full_evidence)
    assert validated.score == 9
    assert validated.score_reason is None or "[Validator:" not in (validated.score_reason or "")


def test_validator_does_not_raise_low_score(sample_evidence):
    """The validator only caps scores downward — a low LLM score must never be raised
    even when evidence is plentiful."""
    niche_report = NicheReport(
        niche="Christmas gift ideas",
        keywords=[],
        trend="ổn định",
        analysis="Phân tích...",
        customer="Khách hàng...",
        pain_points=["Than phiền 1"],
        competition="Cao",
        price_range="$10 - $20",
        ideas=[
            Idea(title="A", what="A", for_whom="A", why_now="A", evidence_refs=[sample_evidence[0].source_url]),
            Idea(title="B", what="B", for_whom="B", why_now="B", evidence_refs=[sample_evidence[1].source_url]),
        ],
        score=3,
    )

    validated = ReportValidator.validate_niche_report(niche_report, sample_evidence)
    assert validated.score == 3


def test_score_reason_includes_gap_note(sample_evidence):
    """When the score is capped, score_reason must name which source is missing."""
    niche_report = NicheReport(
        niche="Christmas gift ideas",
        keywords=[],
        trend="tăng",
        analysis="Phân tích...",
        customer="Khách hàng...",
        pain_points=["Than phiền 1"],
        competition="Cao",
        price_range="$10 - $20",
        ideas=[
            Idea(title="A", what="A", for_whom="A", why_now="A", evidence_refs=[sample_evidence[0].source_url]),
            Idea(title="B", what="B", for_whom="B", why_now="B", evidence_refs=[sample_evidence[1].source_url]),
        ],
        score=10,
        score_reason="Tiềm năng tăng trưởng cao",
    )

    validated = ReportValidator.validate_niche_report(niche_report, sample_evidence)
    assert "[Validator:" in validated.score_reason
    assert "Tiềm năng tăng trưởng cao" in validated.score_reason  # original reason preserved


def test_writer_with_mock_llm(sample_evidence):
    niche = Niche(name="Christmas gift ideas", seed_keywords=["christmas gift ideas"])
    mock_llm = get_llm("mock")
    report, usage = write_niche_report(niche, sample_evidence, mock_llm)
    assert isinstance(report, NicheReport)
    assert report.niche == "Christmas gift ideas"
    assert len(report.ideas) >= 2
    assert usage.input_tokens > 0


def test_summarizer_with_mock_llm():
    nr = NicheReport(
        niche="Christmas gift ideas",
        keywords=[],
        trend="tăng",
        analysis="Phân tích...",
        customer="Khách hàng...",
        pain_points=[],
        competition="Trung bình",
        price_range="$20",
        ideas=[
            Idea(
                title="Ý tưởng A",
                what="Bán A",
                for_whom="Cho A",
                why_now="Vì A",
                evidence_refs=["https://google.com"],
            ),
            Idea(
                title="Ý tưởng B",
                what="Bán B",
                for_whom="Cho B",
                why_now="Vì B",
                evidence_refs=["https://google.com"],
            ),
        ],
        score=9,
    )
    mock_llm = get_llm("mock")
    rankings, top_ideas, usage = summarize_report([nr], mock_llm)
    assert len(rankings) >= 1
    assert len(top_ideas) <= 3
    assert usage.input_tokens > 0


def test_report_renderer():
    from src.core.config import BASE_DIR
    tmp_out = BASE_DIR / "data" / "test_reports"
    tmp_out.mkdir(parents=True, exist_ok=True)
    renderer = ReportRenderer(output_dir=tmp_out)
    final_report = FinalReport(
        category="Quà tặng theo mùa",
        date="20/10/2026",
        niche_reports=[],
        ranking=[RankingItem(rank=1, niche="Christmas gift ideas", score=9, reason="Lý do tốt")],
        top_ideas=[
            Idea(
                title="Ý tưởng Top 1",
                what="Mô tả",
                for_whom="Khách hàng",
                why_now="Thời điểm",
                evidence_refs=["https://test.com"],
            )
        ],
        cost_usd=0.005,
    )
    saved_file = renderer.save(final_report, filename="test_report.md")
    assert saved_file.exists()
    content = saved_file.read_text(encoding="utf-8")
    assert "# Báo cáo xu hướng: Quà tặng theo mùa" in content
    assert "Ý tưởng Top 1" in content
    # Clean up
    try:
        saved_file.unlink()
        tmp_out.rmdir()
    except Exception:
        pass


def test_validator_sanitizes_idea_opportunity_fields(sample_evidence):
    """Ensures validator properly sanitizes fabricated upvote counts across all new Idea fields."""
    idea = Idea(
        title="Custom Wallet (50 upvotes)",
        what="Ví da thật khắc tên",
        for_whom="Nam giới",
        why_now="Mùa giáng sinh (100 upvotes)",
        differentiation="Chất da vegetable-tanned bền bỉ (200 upvotes)",
        target_price="$29 - $39",
        suggested_channel="Etsy & TikTok Shop",
        demand_proof="Google Trends tăng 150% (300 upvotes)",
        pain_proof="Khách Reddit than phiền da PU bị bong tróc",
        competitor_benchmark="Amazon bán $19 nhưng da PU chất lượng kém",
        evidence_refs=[sample_evidence[0].source_url],
    )
    nr = NicheReport(
        niche="Christmas gift ideas",
        keywords=[],
        trend="tăng",
        analysis="Phân tích...",
        customer="Khách hàng...",
        pain_points=["Than phiền..."],
        competition="Cao",
        price_range="$20",
        ideas=[idea],
        score=7,
    )
    validated = ReportValidator.validate_niche_report(nr, sample_evidence)
    v_idea = validated.ideas[0]

    assert "50 upvotes" not in v_idea.title
    assert "100 upvotes" not in v_idea.why_now
    assert "200 upvotes" not in v_idea.differentiation
    assert "300 upvotes" not in v_idea.demand_proof
    assert v_idea.target_price == "$29 - $39"
    assert v_idea.suggested_channel == "Etsy & TikTok Shop"
    assert "da PU bị bong tróc" in v_idea.pain_proof


def test_renderer_renders_product_opportunity_card():
    """Validates that ReportRenderer includes all 3 validation pillars and USP sections."""
    renderer = ReportRenderer()
    final_report = FinalReport(
        category="Quà tặng theo mùa",
        date="03/11/2026",
        niche_reports=[],
        ranking=[RankingItem(rank=1, niche="Personalized Gift", score=9, reason="Nhu cầu cao")],
        top_ideas=[
            Idea(
                title="Ví da nam khắc tên cá nhân",
                what="Ví da bò thật kèm hộp quà sang trọng",
                for_whom="Người mua quà tặng bạn trai, chồng",
                why_now="Cao điểm mua sắm quà tặng Giáng sinh",
                differentiation="Khắc tên miễn phí bằng công nghệ laser",
                target_price="$35 (Margin 65%)",
                suggested_channel="Etsy & TikTok Shop",
                demand_proof="Keyword 'custom wallet' tăng +140% trên Trends",
                pain_proof="Reddit r/gifts than phiền ví giá rẻ bị nổ da sau vài tuần",
                competitor_benchmark="Amazon đối thủ bán $24.99 nhưng chỉ là da PU nhân tạo",
                evidence_refs=["https://reddit.com/r/gifts/comments/123/"],
            )
        ],
        cost_usd=0.01,
    )
    rendered = renderer.render(final_report)
    assert "Ví da nam khắc tên cá nhân" in rendered
    assert "Điểm khác biệt / Cải tiến (USP):" in rendered
    assert "Khắc tên miễn phí bằng công nghệ laser" in rendered
    assert "Kiểm chứng 3 trụ cột (Validation Dossier):" in rendered
    assert "Keyword 'custom wallet' tăng +140% trên Trends" in rendered
    assert "r/gifts than phiền ví giá rẻ bị nổ da" in rendered
    assert "da PU nhân tạo" in rendered
