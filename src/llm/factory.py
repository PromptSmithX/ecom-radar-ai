"""LLM Factory for selecting and instantiating LLM clients."""

from __future__ import annotations
import json
import logging
from typing import Optional
from src.core.config import settings
from .base import LLMClient, LLMResult, Usage
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class MockLLMClient(LLMClient):
    """Mock LLM client for offline development, dry-runs, and testing."""
    def __init__(self, model: str = "mock-model"):
        self.model = model

    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> LLMResult:
        logger.info(f"MockLLMClient generating response for prompt (len={len(prompt)})")
        if json_mode:
            prompt_lower = (prompt + " " + system).lower()
            if "ranking" in prompt_lower or "top_ideas" in prompt_lower or "summary" in prompt_lower:
                sample_data = {
                    "ranking": [
                        {"rank": 1, "niche": "Christmas gift ideas", "score": 9, "reason": "Tín hiệu xu hướng tăng mạnh +250% trong Q4, nhu cầu mua sắm đỉnh điểm"},
                        {"rank": 2, "niche": "Personalized gift", "score": 8, "reason": "Biên lợi nhuận cao (60-70%), giá trị cá nhân hóa vượt trội"},
                        {"rank": 3, "niche": "Gift for him", "score": 8, "reason": "Lượng tìm kiếm lớn, khách hàng sẵn sàng chi trả cho sản phẩm công nghệ/EDC"},
                        {"rank": 4, "niche": "Valentine gift", "score": 7, "reason": "Chu kỳ bán hàng ngắn, cần chuẩn bị sớm từ tháng 1"}
                    ],
                    "top_ideas": [
                        {
                            "title": "Hộp quà tất giáng sinh EDC tối giản (Minimalist EDC Stocking Stuffer)",
                            "what": "Bộ phụ kiện bỏ túi đa năng bằng hợp kim titan kết hợp móc khóa khắc tên cá nhân",
                            "for_whom": "Nam giới trẻ tuổi và người yêu thích đồ dùng công nghệ, tiện ích hàng ngày",
                            "why_now": "Từ khóa 'stocking stuffers' và 'gifts for him' tăng đột biến +250% dịp Giáng sinh",
                            "evidence_refs": ["https://trends.google.com/trends/explore?q=stocking+stuffers"]
                        },
                        {
                            "title": "Đèn ngủ mica khắc sóng âm & ảnh kỷ niệm (Soundwave Acrylic Lamp)",
                            "what": "Đèn LED acrylic đế gỗ cao cấp in mã nhạc Spotify và hình ảnh kỷ niệm theo yêu cầu",
                            "for_whom": "Các cặp đôi tìm kiếm quà tặng ý nghĩa, cảm xúc cho dịp Noel và Valentine",
                            "why_now": "Nhu cầu quà cá nhân hóa tăng cao trên Etsy với mức giá $28-$45",
                            "evidence_refs": ["https://www.etsy.com/blog/trends-personalized-gifts-forecast"]
                        },
                        {
                            "title": "Trạm sạc không dây 3-in-1 gỗ óc chó khắc laser (Wooden MagSafe Station)",
                            "what": "Đế sạc đa thiết bị cho điện thoại, đồng hồ thông minh từ gỗ óc chó tự nhiên",
                            "for_whom": "Bạn trai, chồng, nhân viên văn phòng yêu thích decor bàn làm việc gọn gàng",
                            "why_now": "Giải quyết than phiền trên Reddit về quà tặng ví/tất truyền thống nhàm chán",
                            "evidence_refs": ["https://www.reddit.com/r/AskMen/comments/gifts_men_actually_want"]
                        }
                    ]
                }
                text = json.dumps(sample_data, ensure_ascii=False)
            elif "digest" in prompt_lower or "chuẩn hóa evidence pack" in prompt_lower:
                sample_data = {
                    "evidence": [
                        {
                            "source": "google_trends",
                            "kind": "keyword_signal",
                            "keyword": "christmas gift ideas",
                            "text": "Google Trends ghi nhận lượt tìm kiếm tăng trưởng mạnh +250%",
                            "value": "+250% rising",
                            "source_url": "https://trends.google.com/trends/explore?q=christmas+gift+ideas"
                        },
                        {
                            "source": "reddit",
                            "kind": "complaint",
                            "keyword": "christmas gift ideas",
                            "text": "Người dùng Reddit than phiền về các món quà giáng sinh rẻ tiền, vô dụng sau dịp lễ",
                            "value": "420 upvotes",
                            "source_url": "https://www.reddit.com/r/BuyItForLife/comments/christmas_useful_gifts"
                        },
                        {
                            "source": "web_search",
                            "kind": "price",
                            "keyword": "christmas gift ideas",
                            "text": "Báo cáo Good Housekeeping khảo sát khoảng giá quà tặng phổ biến $18 - $32",
                            "value": "$18 - $32",
                            "source_url": "https://www.goodhousekeeping.com/holidays/gift-ideas/g1234/best-christmas-gifts-2026"
                        }
                    ]
                }
                text = json.dumps(sample_data, ensure_ascii=False)
            else:
                # Niche report prompt - detect niche name specifically from header
                niche_target = ""
                for line in prompt.splitlines():
                    if "TÊN NICHE:" in line:
                        niche_target = line.split("TÊN NICHE:")[1].strip().lower()
                        break

                if "christmas" in niche_target:
                    sample_data = {
                        "niche": "Christmas gift ideas",
                        "keywords": [
                            {"keyword": "christmas gifts for mom", "signal": "Top Google Autocomplete & +250% Google Trends", "source_url": "https://trends.google.com/trends/explore?q=christmas+gift+ideas"},
                            {"keyword": "stocking stuffers", "signal": "+350% breakout query dịp cận lễ", "source_url": "https://trends.google.com/trends/explore?q=stocking+stuffers"}
                        ],
                        "trend": "tăng",
                        "analysis": "Bước vào mùa cao điểm mua sắm lớn nhất năm, lưu lượng tìm kiếm tăng vọt từ giữa tháng 10 đến tuần thứ 3 của tháng 12.",
                        "customer": "Phụ huynh, con cái và các cặp đôi tìm kiếm quà tặng ý nghĩa nhưng thiết thực cho các thành viên trong gia đình.",
                        "pain_points": [
                            "Quà tặng đại trà dễ nhàm chán và bị vứt bỏ sau dịp lễ",
                            "Nỗi lo trễ hạn giao hàng cận Giáng sinh",
                            "Khó chọn quà cho người lớn tuổi (mẹ, bà) - những người luôn nói 'không thiếu thứ gì'"
                        ],
                        "competition": "Cạnh tranh phân khúc đồ lưu niệm rẻ tiền rất gay gắt, cơ hội nằm ở các hộp quà trọn gói (curated gift box) và đồ gia dụng ấm áp.",
                        "price_range": "$18 - $45",
                        "ideas": [
                            {
                                "title": "Hộp tất giáng sinh ấm áp kèm nến thơm thủ công",
                                "what": "Bộ quà tặng gồm vớ len phong cách Bắc Âu, nến thơm tinh dầu quế/thông và thiệp viết tay",
                                "for_whom": "Mẹ, bạn bè, đồng nghiệp nữ",
                                "why_now": "Đánh đúng tâm lý chuộng quà tặng ấm áp, dễ tặng và đóng gói sẵn lịch sự",
                                "evidence_refs": ["https://trends.google.com/trends/explore?q=christmas+gift+ideas"]
                            },
                            {
                                "title": "Bộ phụ kiện bỏ túi EDC Stocking Stuffer",
                                "what": "Hộp quà mini gồm móc khóa titan tích hợp khui chai, đèn pin bỏ túi siêu sáng",
                                "for_whom": "Thanh thiếu niên, nam giới trẻ",
                                "why_now": "Stocking stuffers thực dụng được đánh giá cao hơn hẳn đồ chơi novelty vô bổ",
                                "evidence_refs": ["https://trends.google.com/trends/explore?q=stocking+stuffers"]
                            }
                        ],
                        "score": 9,
                        "score_reason": "Niche có dung lượng thị trường và mức độ quan tâm bùng nổ nhất trong quý 4."
                    }
                elif "personalized" in niche_target or "custom" in niche_target:
                    sample_data = {
                        "niche": "Personalized gift",
                        "keywords": [
                            {"keyword": "custom name gift", "signal": "Xu hướng tìm kiếm tăng cao trên Etsy & Google", "source_url": "https://www.etsy.com/blog/trends-personalized-gifts-forecast"},
                            {"keyword": "engraved gift", "signal": "Nhu cầu quà kỷ niệm khắc laser đạt đỉnh mùa lễ", "source_url": "https://www.google.com/search?q=engraved+gift"}
                        ],
                        "trend": "tăng",
                        "analysis": "Khách hàng ngày càng ưu tiên quà tặng mang tính cá nhân hóa cao thay cho sản phẩm công nghiệp đại trà.",
                        "customer": "Các cặp đôi, bạn thân và gia đình tìm kiếm món quà lưu giữ kỷ niệm đặc biệt.",
                        "pain_points": [
                            "Chất lượng in ấn/khắc laser trên thị trường không đồng đều, dễ bong tróc",
                            "Thời gian sản xuất theo yêu cầu kéo dài khiến khách lo lắng không kịp nhận quà",
                            "Khó xem trước bản demo cá nhân hóa trước khi đặt hàng"
                        ],
                        "competition": "Cạnh tranh trung bình, biên lợi nhuận rất cao (60-70%), quyết định bởi tốc độ hoàn thiện và đóng gói.",
                        "price_range": "$28 - $65",
                        "ideas": [
                            {
                                "title": "Đèn ngủ mica khắc sóng âm & ảnh kỷ niệm (Soundwave Acrylic Lamp)",
                                "what": "Đèn ngủ LED đế gỗ cao cấp in mã nhạc Spotify và hình ảnh kỷ niệm theo yêu cầu",
                                "for_whom": "Các cặp đôi nhân dịp kỷ niệm, Noel và Valentine",
                                "why_now": "Sản phẩm bestseller trên Etsy với tỷ lệ chuyển đổi cao và biên lãi tốt",
                                "evidence_refs": ["https://www.etsy.com/blog/trends-personalized-gifts-forecast"]
                            },
                            {
                                "title": "Thớt gỗ óc chó khắc tên gia đình (Custom Engraved Cutting Board)",
                                "what": "Thớt nhà bếp gỗ tự nhiên khắc laser họ tên gia đình và năm thành lập",
                                "for_whom": "Quà tặng tân gia, quà Giáng sinh cho bố mẹ hoặc gia đình trẻ",
                                "why_now": "Vừa có tính sử dụng cao trong bếp vừa có giá trị trưng bày kỷ niệm",
                                "evidence_refs": ["https://www.shopify.com/blog/personalized-gifts-ecommerce-guide"]
                            }
                        ],
                        "score": 8,
                        "score_reason": "Biên lợi nhuận cực cao và tính độc bản giúp hạn chế cạnh tranh về giá."
                    }
                elif "valentine" in niche_target or "couple" in niche_target:
                    sample_data = {
                        "niche": "Valentine gift",
                        "keywords": [
                            {"keyword": "valentine gifts for her", "signal": "Tín hiệu chuẩn bị tìm kiếm từ cuối tháng 12", "source_url": "https://www.cosmopolitan.com/lifestyle/g9101/best-valentines-day-gifts"},
                            {"keyword": "couple gift", "signal": "Xu hướng mua sắm đồ đôi tăng trưởng ổn định", "source_url": "https://www.google.com/search?q=couple+gift"}
                        ],
                        "trend": "ổn định",
                        "analysis": "Thị trường bước vào giai đoạn chuẩn bị sản phẩm trước khi bùng nổ mạnh mẽ vào cuối tháng 1 và nửa đầu tháng 2.",
                        "customer": "Các cặp đôi trẻ yêu nhau, vợ chồng mới cưới tìm kiếm sự lãng mạn và bất ngờ.",
                        "pain_points": [
                            "Quà tặng hoa tươi và sô-cô-la quá rập khuôn và nhanh tàn",
                            "Giao hàng chậm trễ dịp sát ngày 14/2 làm hỏng kế hoạch hẹn hò",
                            "Khó tìm quà thể hiện sự thấu hiểu sâu sắc đối phương"
                        ],
                        "competition": "Cạnh tranh đỉnh điểm trong khung thời gian ngắn 2 tuần, phụ thuộc lớn vào marketing cảm xúc và cam kết vận chuyển.",
                        "price_range": "$20 - $55",
                        "ideas": [
                            {
                                "title": "Sổ tay cào 100 cuộc hẹn hò lãng mạn (Couple Date Scratch Book)",
                                "what": "Cuốn sách tương tác gồm 100 ý tưởng hẹn hò bí mật cần cào để khám phá",
                                "for_whom": "Các cặp đôi muốn tạo thêm trải nghiệm mới mẻ và gắn kết",
                                "why_now": "Trào lưu quà tặng trải nghiệm thay thế quà tặng vật chất đơn thuần",
                                "evidence_refs": ["https://www.cosmopolitan.com/lifestyle/g9101/best-valentines-day-gifts"]
                            },
                            {
                                "title": "Vòng tay đôi nam châm tối giản kết nối cảm xúc",
                                "what": "Bộ 2 vòng tay dây dù chống nước đính hạt nam châm tự hút khi nắm tay",
                                "for_whom": "Học sinh, sinh viên và cặp đôi yêu xa",
                                "why_now": "Mức giá hợp lý $20-$30, thông điệp cảm xúc mạnh mẽ",
                                "evidence_refs": ["https://www.retaildive.com/news/valentines-day-consumer-spending-trends"]
                            }
                        ],
                        "score": 7,
                        "score_reason": "Chu kỳ bán ngắn nhưng sức mua dồn dập, biên lợi nhuận mùa vụ hấp dẫn."
                    }
                else:
                    # Gift for him
                    sample_data = {
                        "niche": "Gift for him",
                        "keywords": [
                            {
                                "keyword": "gifts for boyfriend",
                                "signal": "Google Autocomplete xu hướng tìm kiếm hàng đầu",
                                "source_url": "https://www.google.com/search?q=gifts+for+boyfriend"
                            },
                            {
                                "keyword": "gifts for him",
                                "signal": "Từ khóa mùa vụ Q4 ghi nhận lượt quan tâm tăng",
                                "source_url": "https://trends.google.com/trends/explore?q=gifts+for+him"
                            }
                        ],
                        "trend": "tăng",
                        "analysis": "Nhu cầu mua quà tặng cho nam giới tăng mạnh trong quý 4, đặc biệt từ các bạn gái và người thân tìm kiếm quà sinh nhật và Noel.",
                        "customer": "Nữ giới độ tuổi 18-35 mua sắm cho bạn trai, chồng hoặc bố; ưu tiên sự tinh tế, hữu dụng thực tế.",
                        "pain_points": [
                            "Quà tặng đại trà dễ gây nhàm chán và bị bỏ xó",
                            "Khó đoán sở thích của nam giới nếu không rành về đồ công nghệ hay EDC"
                        ],
                        "competition": "Cạnh tranh phân khúc phổ thông cao, nhưng phân khúc quà tặng cá nhân hóa và EDC cao cấp còn nhiều khoảng trống.",
                        "price_range": "$25 - $50",
                        "ideas": [
                            {
                                "title": "Trạm sạc MagSafe 3-in-1 gỗ khắc tên",
                                "what": "Đế sạc không dây bằng gỗ óc chó tự nhiên tích hợp sạc iPhone, Apple Watch, AirPods",
                                "for_whom": "Bạn trai, chồng làm việc văn phòng",
                                "why_now": "Thiết thực, thẩm mỹ cao và giải quyết than phiền về quà tặng nhàm chán",
                                "evidence_refs": ["https://www.reddit.com/r/AskMen/comments/gifts_men_actually_want"]
                            },
                            {
                                "title": "Bộ dao đa năng Titanium bỏ túi kèm hộp quà khắc thông điệp",
                                "what": "Dụng cụ EDC mini cao cấp chống gỉ kèm móc khóa cá nhân hóa",
                                "for_whom": "Nam giới yêu thích dã ngoại, công nghệ bỏ túi",
                                "why_now": "Mức giá $25-$45 phù hợp ngân sách quà tặng, tỷ lệ hài lòng cao",
                                "evidence_refs": ["https://www.menshealth.com/technology/g5678/best-gadgets-gifts-for-men"]
                            }
                        ],
                        "score": 8,
                        "score_reason": "Nhu cầu tiêu dùng lớn, tính hữu dụng cao và biên lợi nhuận tốt."
                    }
                text = json.dumps(sample_data, ensure_ascii=False)
        else:
            text = "Báo cáo phân tích thị trường mẫu hoàn thành từ Mock LLM."

        return LLMResult(
            text=text,
            usage=Usage(input_tokens=150, output_tokens=300),
        )


def get_llm(
    provider: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None
) -> LLMClient:
    """Factory to retrieve the appropriate LLM client."""
    provider_clean = (provider or "").lower().strip()

    if provider_clean == "gemini":
        key = api_key or settings.gemini_api_key
        mod = model or settings.llm.writer.model or "gemini-2.5-flash"
        return GeminiClient(api_key=key, model=mod)

    if provider_clean == "openai":
        key = api_key or settings.openai_api_key
        mod = model or settings.llm.writer.model or "gpt-4o-mini"
        return OpenAIClient(api_key=key, model=mod)

    if provider_clean in ["mock", "test", "offline"]:
        return MockLLMClient(model=model or "mock-model")

    raise ValueError(f"Unknown LLM provider: '{provider}'. Supported providers: 'gemini', 'openai', 'mock'.")
