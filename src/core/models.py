"""Pydantic data models for the Trend Research Tool."""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class Niche(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., description="Tên của niche")
    seed_keywords: List[str] = Field(default_factory=list, description="Danh sách từ khóa mầm")


class Evidence(BaseModel):
    source: str = Field(..., description="Nguồn: google_trends | reddit | web_search | google_suggest")
    kind: str = Field(..., description="Loại tín hiệu: keyword_signal | complaint | price | competitor | general")
    keyword: Optional[str] = Field(None, description="Từ khóa liên quan")
    text: str = Field(..., description="Nội dung tóm tắt/trích dẫn đã chuẩn hóa")
    value: Optional[str] = Field(None, description="Số liệu cụ thể nếu có, ví dụ +250% rising, 85/100 interest")
    source_url: str = Field(..., description="URL nguồn kiểm chứng bắt buộc")


class KeywordSignal(BaseModel):
    keyword: str = Field(..., description="Từ khóa hot")
    signal: str = Field(..., description="Tín hiệu xu hướng lấy từ evidence")
    source_url: str = Field(..., description="Link nguồn kiểm chứng")


class Idea(BaseModel):
    title: str = Field(..., description="Tên ý tưởng sản phẩm")
    what: str = Field(..., description="Bán cái gì")
    for_whom: str = Field(..., description="Bán cho ai (khách hàng mục tiêu)")
    why_now: str = Field(..., description="Vì sao nên bán bây giờ")
    evidence_refs: List[str] = Field(default_factory=list, description="Dẫn chiếu evidence hoặc keyword liên quan")


class NicheReport(BaseModel):
    niche: str = Field(..., description="Tên niche")
    keywords: List[KeywordSignal] = Field(default_factory=list, description="Danh sách keyword hot và tín hiệu")
    trend: str = Field(..., description="Đánh giá xu hướng: tăng | ổn định | giảm")
    analysis: str = Field(..., description="Phân tích nguyên nhân xu hướng (mùa vụ, sự kiện...)")
    customer: str = Field(..., description="Chân dung khách hàng và nhu cầu đang tìm kiếm")
    pain_points: List[str] = Field(default_factory=list, description="Các vấn đề/than phiền thường gặp của khách hàng")
    competition: str = Field(..., description="Mức độ cạnh tranh và đối thủ")
    price_range: str = Field("Không có dữ liệu", description="Khoảng giá tham khảo trên thị trường")
    ideas: List[Idea] = Field(default_factory=list, description="2-3 ý tưởng sản phẩm cụ thể")
    score: int = Field(default=5, ge=1, le=10, description="Điểm đánh giá tiềm năng niche từ 1 đến 10")
    score_reason: Optional[str] = Field(None, description="Lý do chấm điểm")


class RankingItem(BaseModel):
    rank: int = Field(..., description="Thứ hạng")
    niche: str = Field(..., description="Tên niche")
    score: int = Field(..., description="Điểm đánh giá")
    reason: str = Field(..., description="Lý do ngắn gọn")


class FinalReport(BaseModel):
    category: str = Field("Quà tặng theo mùa", description="Danh mục sản phẩm")
    date: str = Field(..., description="Ngày tạo báo cáo")
    niche_reports: List[NicheReport] = Field(default_factory=list, description="Báo cáo chi tiết từng niche")
    ranking: List[RankingItem] = Field(default_factory=list, description="Bảng xếp hạng tiềm năng các niche")
    top_ideas: List[Idea] = Field(default_factory=list, description="Đúng 3 ý tưởng sản phẩm tốt nhất")
    cost_usd: float = Field(0.0, description="Tổng chi phí LLM ước tính (USD)")
    total_input_tokens: int = Field(0, description="Tổng input tokens")
    total_output_tokens: int = Field(0, description="Tổng output tokens")
    models_used: dict[str, str] = Field(default_factory=dict, description="Các model đã sử dụng cho từng bước")
