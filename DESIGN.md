# Product Trend Research Tool: Tài liệu thiết kế (MVP 3 ngày)

> Tool AI tự thu thập dữ liệu xu hướng, phân tích và viết báo cáo theo từng niche, kèm gợi ý sản phẩm nên bán.
> Mục tiêu: chạy được để demo, dễ dùng, code sạch dễ đọc lại. Không over-engineer.

---

## 1. Tool làm gì

**Input:** người dùng chọn danh mục, niche và bấm "Chạy".

**Output:** một báo cáo Markdown (xem được trên UI, tải về được) gồm, với mỗi niche:

1. **Keyword**: keyword chính và keyword liên quan đang hot, kèm tín hiệu và link nguồn.
2. **Phân tích**: niche tăng/ổn định/giảm và vì sao, khách hàng là ai và than phiền gì, cạnh tranh và khoảng giá.
3. **Idea sản phẩm**: 2–3 idea (bán gì, cho ai, vì sao bán bây giờ).

Cuối báo cáo có **Tổng kết**: xếp hạng niche theo mức đáng làm và chọn **top 3 idea tốt nhất**.

### Phạm vi MVP

| Làm | Không làm (cắt để kịp 3 ngày) |
| --- | --- |
| Chạy 1 lệnh CLI hoặc 1 nút bấm trên UI | Deploy, chạy theo lịch |
| 4 nguồn dữ liệu miễn phí / gói free | Crawl Amazon, Etsy, TikTok trực tiếp |
| Cache dữ liệu thô để chạy lại rẻ | Database, đăng nhập, multi-user |
| Log token và chi phí mỗi lần chạy | Dashboard phức tạp |
| Sparkline xu hướng từ Google Trends (nếu dư thời gian) | Ảnh minh họa sản phẩm |

---

## 2. Danh mục và niche đề xuất

**Danh mục:** Quà tặng theo mùa (đang tháng 10, tới Halloween, Black Friday, Giáng sinh nên tín hiệu xu hướng rõ).

| # | Niche | Seed keywords (ghi vào README) |
| --- | --- | --- |
| 1 | Christmas gift ideas | `christmas gift ideas`, `christmas gifts for mom`, `stocking stuffers` |
| 2 | Gift for him | `gifts for him`, `gifts for boyfriend`, `gifts for dad` |
| 3 | Personalized gift | `personalized gifts`, `custom name gift`, `engraved gift` |
| 4 | Valentine gift | `valentine gifts for her`, `valentine gifts for him`, `couple gift` |

Niche và seed keyword nằm trong `config/niches.yaml`, đổi niche không cần sửa code.

---

## 3. Luồng hoạt động

```
┌────────────┐
│ UI / CLI   │  chọn niche, model, bấm Chạy
└─────┬──────┘
      ▼
┌──────────────────────────────────────────────────────────┐
│ PIPELINE (chạy tuần tự cho từng niche)                   │
│                                                          │
│  [1] COLLECT   không dùng LLM, chi phí 0                 │
│      Google Suggest ─► mở rộng keyword                   │
│      Google Trends  ─► xu hướng + rising queries         │
│      Reddit         ─► khách hỏi / than phiền gì         │
│      Web Search     ─► link nguồn, giá, đối thủ          │
│            │                                             │
│            ▼  lưu raw JSON vào data/raw/ (cache)         │
│                                                          │
│  [2] DIGEST    model rẻ (gpt-4o-mini hoặc Gemini Flash)  │
│      Gom dữ liệu thô thành "evidence pack" gọn,          │
│      mỗi fact gắn source_url                             │
│            │                                             │
│            ▼                                             │
│  [3] WRITE     Gemini (model viết báo cáo)               │
│      Viết 3 phần của niche theo schema, chỉ dùng         │
│      evidence pack                                       │
│            │                                             │
│            ▼                                             │
│  [4] SUMMARIZE  1 lần cho cả báo cáo                     │
│      Xếp hạng niche + chọn top 3 idea                    │
│                                                          │
│  [5] RENDER    Jinja2 template ─► report.md              │
└──────────────────────────────────────────────────────────┘
      ▼
  reports/2026-10-22_quatang.md  (xem trên UI, tải về)
```

**Nguyên tắc cốt lõi chống bịa số:** LLM không tự tìm số liệu. Dữ liệu đến từ bước COLLECT, LLM chỉ được tổng hợp lại dữ liệu đó. Thiếu dữ liệu thì ghi `"Không có dữ liệu"`.

---

## 4. Tech stack

| Lớp | Công nghệ | Lý do |
| --- | --- | --- |
| Ngôn ngữ | Python 3.11+ | Hệ sinh thái crawl và LLM đầy đủ |
| UI | **Streamlit** | Dựng UI trong vài giờ, có progress, tab, nút download |
| CLI | **Typer** | 1 lệnh chạy, hợp để quay demo và test nhanh |
| Models dữ liệu | **Pydantic v2** | Validate dữ liệu và output JSON của LLM |
| Config | `pydantic-settings` + YAML + `.env` | Tách key và cấu hình khỏi code |
| HTTP | `httpx` (+ `tenacity` để retry) | Gọi API, Reddit, Suggest |
| Google Trends | `pytrends` | Miễn phí, hay dính 429 nên cần cache và sleep |
| Web search | Tavily hoặc Serper (gói free) | Lấy link nguồn, giá, đối thủ |
| LLM Gemini | `google-genai` | Viết báo cáo |
| LLM OpenAI | `openai` (gpt-4o-mini) | Test và bước DIGEST rẻ |
| Template | **Jinja2** | Tách phần trình bày khỏi logic |
| Biểu đồ | Plotly hoặc `st.line_chart` | Sparkline xu hướng (optional) |
| Log | `loguru` hoặc `logging` | Debug pipeline |

> Tên model cụ thể (Gemini Flash/Pro bản nào) đặt trong config. Kiểm tra tên model hiện hành trên trang docs của Google trước khi chạy, tránh hard-code.

---

## 5. Cấu trúc thư mục

```
trend-research/
├── README.md
├── DESIGN.md
├── requirements.txt
├── .env.example
├── config/
│   ├── settings.yaml          # model, provider, số kết quả, sleep...
│   └── niches.yaml            # danh mục, niche, seed keywords
├── src/
│   ├── cli.py                 # entrypoint Typer
│   ├── app.py                 # entrypoint Streamlit
│   ├── core/
│   │   ├── config.py          # load settings
│   │   ├── models.py          # Pydantic: Niche, Evidence, NicheReport...
│   │   └── cache.py           # cache JSON theo (source, query, ngày)
│   ├── collectors/            # mỗi nguồn 1 file
│   │   ├── base.py            # interface Collector
│   │   ├── google_suggest.py
│   │   ├── google_trends.py
│   │   ├── reddit.py
│   │   ├── web_search.py
│   │   └── registry.py        # đăng ký danh sách collector
│   ├── llm/
│   │   ├── base.py            # interface LLMClient + Usage
│   │   ├── gemini_client.py
│   │   ├── openai_client.py
│   │   ├── factory.py         # tạo client theo tên
│   │   └── cost.py            # bảng giá + tính chi phí
│   ├── pipeline/
│   │   ├── runner.py          # điều phối các bước
│   │   ├── digest.py          # bước 2
│   │   ├── writer.py          # bước 3
│   │   └── summarizer.py      # bước 4
│   ├── prompts/
│   │   ├── digest.md
│   │   ├── niche_report.md
│   │   └── summary.md
│   └── render/
│       ├── renderer.py
│       └── report.md.j2
├── data/
│   ├── raw/                   # cache dữ liệu thô
│   └── evidence/              # evidence pack đã digest
├── reports/                   # báo cáo đầu ra
└── tests/
    ├── test_collectors.py
    └── test_llm_factory.py
```

Quy ước: `core` không import từ lớp khác. `pipeline` là nơi duy nhất biết cả collectors lẫn llm. UI và CLI chỉ gọi `pipeline.runner`.

---

## 6. Design pattern (vừa đủ, không thừa)

| Pattern | Dùng ở đâu | Lợi ích |
| --- | --- | --- |
| **Strategy + Factory** | `LLMClient` (Gemini / OpenAI), `get_llm("gemini")` | Đổi model bằng config, không sửa pipeline |
| **Plugin / Registry** | `Collector` | Thêm nguồn mới = thêm 1 file + 1 dòng đăng ký |
| **Pipeline** | `runner.py` gồm các step nối tiếp | Dễ đọc, dễ chạy lại riêng từng bước |
| **Cache-aside** | `core/cache.py` | Chỉnh prompt chỉ chạy lại bước LLM, tiết kiệm tiền |
| **DTO (Pydantic)** | Mọi dữ liệu đi qua lại giữa các bước | Lỗi dữ liệu bắt sớm, output LLM được validate |
| **Template** | Jinja2 cho báo cáo | Đổi giao diện báo cáo không đụng logic |

### 6.1 Interface Collector

```python
# src/collectors/base.py
from abc import ABC, abstractmethod
from core.models import Niche, Evidence

class Collector(ABC):
    name: str

    @abstractmethod
    def collect(self, niche: Niche) -> list[Evidence]:
        """Trả về danh sách bằng chứng, mỗi cái có source_url."""
```

```python
# src/collectors/registry.py
from .google_suggest import GoogleSuggestCollector
from .google_trends import GoogleTrendsCollector
from .reddit import RedditCollector
from .web_search import WebSearchCollector

COLLECTORS = [GoogleSuggestCollector, GoogleTrendsCollector,
              RedditCollector, WebSearchCollector]
```

Collector nào lỗi thì bắt exception, log cảnh báo và bỏ qua, các nguồn còn lại vẫn chạy (báo cáo ghi rõ nguồn nào thiếu).

### 6.2 Interface LLM (Gemini + OpenAI cùng một giao diện)

```python
# src/llm/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel

class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

class LLMResult(BaseModel):
    text: str
    usage: Usage

class LLMClient(ABC):
    model: str

    @abstractmethod
    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> LLMResult: ...
```

```python
# src/llm/factory.py
from core.config import settings
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient

def get_llm(provider: str, model: str | None = None):
    if provider == "gemini":
        return GeminiClient(settings.gemini_api_key, model or settings.gemini_model)
    if provider == "openai":
        return OpenAIClient(settings.openai_api_key, model or settings.openai_model)
    raise ValueError(f"Unknown provider: {provider}")
```

Cấu hình gợi ý: mỗi bước chọn provider riêng.

```yaml
# config/settings.yaml
llm:
  digest:  { provider: openai, model: gpt-4o-mini }   # bước rẻ
  writer:  { provider: gemini, model: <gemini-model> } # bước viết chính
  summary: { provider: gemini, model: <gemini-model> }
  # Khi test: đổi cả 3 sang openai/gpt-4o-mini
```

Nhờ vậy dev bằng gpt-4o-mini, demo thật bằng Gemini chỉ cần sửa YAML (hoặc chọn dropdown trên UI).

---

## 7. Data model chính

```python
# src/core/models.py (rút gọn)
class Niche(BaseModel):
    name: str
    seed_keywords: list[str]

class Evidence(BaseModel):
    source: str            # "google_trends" | "reddit" | "web_search" | "google_suggest"
    kind: str              # "keyword_signal" | "complaint" | "price" | "competitor"
    keyword: str | None
    text: str              # nội dung ngắn đã chuẩn hoá
    value: str | None      # số liệu gốc, ví dụ "+250% rising"
    source_url: str

class KeywordSignal(BaseModel):
    keyword: str
    signal: str            # lấy từ Evidence, không tự bịa
    source_url: str

class Idea(BaseModel):
    title: str
    what: str              # bán cái gì
    for_whom: str          # cho ai
    why_now: str           # vì sao bán bây giờ
    evidence_refs: list[str]

class NicheReport(BaseModel):
    niche: str
    keywords: list[KeywordSignal]
    trend: str             # "tăng" | "ổn định" | "giảm"
    analysis: str
    customer: str
    pain_points: list[str]
    competition: str
    price_range: str       # "Không có dữ liệu" nếu thiếu
    ideas: list[Idea]      # 2–3 idea
    score: int             # 1–10, dùng cho xếp hạng

class FinalReport(BaseModel):
    niche_reports: list[NicheReport]
    ranking: list[str]
    top_ideas: list[Idea]  # đúng 3 idea
    cost_usd: float
```

LLM trả JSON theo schema `NicheReport`, code validate bằng Pydantic. Sai schema thì retry 1–2 lần. Markdown được render từ JSON, không để LLM tự dựng markdown (đảm bảo mọi niche có đủ 3 phần).

---

## 8. Nguồn dữ liệu

| Nguồn | Cách lấy | Cho ra gì | Lưu ý |
| --- | --- | --- | --- |
| Google Suggest | `suggestqueries.google.com` (autocomplete công khai) | Keyword liên quan, long-tail | Không cần key |
| Google Trends | `pytrends`: `interest_over_time`, `related_queries` | Mức quan tâm và query "rising" | Sleep 2–5s giữa request, cache theo ngày, dễ gặp 429 |
| Reddit | JSON công khai (`/search.json?q=...`) hoặc PRAW | Câu hỏi và than phiền của khách | Đặt User-Agent riêng, giới hạn số request |
| Web Search | Tavily / Serper | Link bài viết, giá, đối thủ, bestseller | Dùng để "lách" Amazon/Etsy: tìm trang listicle/bestseller thay vì crawl |

Mọi `Evidence` bắt buộc có `source_url`. Không có URL thì không đưa vào báo cáo.

---

## 9. Prompt và cơ chế chống bịa

**Bước DIGEST** (model rẻ): nhận dữ liệu thô, trả `list[Evidence]` đã lọc trùng, bỏ nhiễu, tối đa N mục mỗi niche.

**Bước WRITE** (Gemini): system prompt có các luật cứng:

```
Bạn là chuyên gia nghiên cứu sản phẩm e-commerce. Viết bằng tiếng Việt, giữ keyword gốc tiếng Anh.
QUY TẮC:
1. CHỈ dùng thông tin trong EVIDENCE bên dưới. Không dùng kiến thức bên ngoài cho số liệu.
2. Mỗi keyword và mỗi nhận định có số liệu phải kèm source_url lấy từ EVIDENCE.
3. Không có dữ liệu thì ghi đúng chuỗi "Không có dữ liệu". Không ước đoán số.
4. Idea sản phẩm phải dẫn chiếu keyword hoặc evidence làm căn cứ.
5. Trả về JSON đúng schema, không thêm chữ nào ngoài JSON.
```

**Kiểm tra sau khi sinh (validator, không tốn token):**
- Mọi `source_url` trong output phải nằm trong tập URL của evidence, nếu không thì loại mục đó.
- Mọi con số trong `signal` phải xuất hiện trong `value` của evidence tương ứng.
- Đủ 2–3 idea mỗi niche, đủ 3 top idea ở tổng kết.

Hai validator này là điểm ăn tiền ở tiêu chí **Chính xác**.

**Bước SUMMARIZE:** nhận danh sách `NicheReport` (đã gọn), trả ranking kèm lý do ngắn và chọn top 3 idea.

---

## 10. Mẫu báo cáo đầu ra

```markdown
# Báo cáo xu hướng: Quà tặng theo mùa
Ngày chạy: 22/10/2026 | Model: Gemini (writer), gpt-4o-mini (digest) | Chi phí: $0.0X

## Tổng kết (đặt lên đầu cho dễ đọc)
| Hạng | Niche | Điểm | Lý do ngắn |
| ---  | ---   | ---  | ---        |
| 1 | Christmas gift ideas | 9/10 | ... |

### Top 3 idea
1. ...

---
## Niche 1: Christmas gift ideas
### 1. Keyword
| Keyword | Tín hiệu | Nguồn |
| --- | --- | --- |
| ... | +250% rising (Google Trends) | [link](...) |

### 2. Phân tích
- Xu hướng: Tăng, vì ...
- Khách hàng: ... | Than phiền: ...
- Cạnh tranh: ... | Giá tham khảo: ...

### 3. Idea sản phẩm
| Idea | Bán gì | Cho ai | Vì sao bây giờ |
| --- | --- | --- | --- |
```

Dù task yêu cầu "Tổng kết" ở cuối, có thể render thêm bản tóm tắt ngắn ở đầu trang cho dễ đọc, và vẫn giữ phần Tổng kết đầy đủ ở cuối.

---

## 11. UI/UX (Streamlit, 1 trang)

Người dùng là nhân viên kinh doanh/marketing, không cần biết code. Mục tiêu: **chọn → bấm → đọc → tải**.

```
┌─ Sidebar ───────────────┐  ┌─ Main ─────────────────────────────┐
│ Danh mục: [Quà tặng ▾]  │  │ Tabs: [Báo cáo] [Dữ liệu thô] [Chi phí] │
│ Niche (multiselect):    │  │                                    │
│  ☑ Christmas gift ideas │  │  Progress:                         │
│  ☑ Gift for him         │  │  ✔ Thu thập Google Trends          │
│  ☑ Personalized gift    │  │  ⏳ Đang viết niche 2/4 ...         │
│  ☐ Valentine gift       │  │                                    │
│ Model viết: [Gemini ▾]  │  │  Báo cáo markdown render ở đây     │
│ ☐ Dùng cache            │  │                                    │
│ [ ▶ Chạy nghiên cứu ]   │  │  [⬇ Tải .md]                       │
└─────────────────────────┘  └────────────────────────────────────┘
```

Các điểm UX cần có (đều rẻ):
- `st.status` / `st.progress` hiển thị từng bước, người dùng biết tool đang chạy gì.
- Dropdown chọn provider (Gemini / OpenAI), hữu ích khi test.
- Checkbox "Dùng cache": bật thì chạy lại gần như tức thì và miễn phí.
- Tab **Dữ liệu thô**: bấm vào xem evidence và link gốc, giúp người chấm kiểm chứng số liệu.
- Tab **Chi phí**: token vào/ra và USD của lần chạy.
- Nút tải báo cáo `.md`.
- Báo lỗi thân thiện: nguồn nào lỗi thì hiện cảnh báo nhỏ, vẫn ra báo cáo.

CLI tương ứng, dùng để quay demo nhanh:

```bash
python -m src.cli run --niches all --writer gemini --digest openai
python -m src.cli run --niches "gift for him" --writer openai   # test rẻ
```

---

## 12. Chi phí (cách tính, ghi vào README)

- `llm/cost.py` giữ bảng giá (USD / 1M token) cho từng model, kiểm tra lại giá trên trang chính thức khi viết README.
- Mỗi `LLMResult.usage` được cộng dồn trong `runner`, cuối lần chạy in và lưu `cost_usd`.
- Ước lượng 1 báo cáo (4 niche): khoảng 4 lần DIGEST + 4 lần WRITE + 1 lần SUMMARIZE, tức vài chục nghìn token, thường chỉ vài cent. Ghi **con số đo thật** từ log, không ước đại.
- Collectors dùng nguồn miễn phí, Tavily/Serper dùng gói free nên chi phí ngoài LLM gần bằng 0.

Mẹo giảm chi phí: cache raw data, digest để giảm context trước khi đưa vào model viết, giới hạn số evidence mỗi niche (ví dụ 30–40 mục).

---

## 13. Cấu hình và chạy

`.env.example`
```
GEMINI_API_KEY=
OPENAI_API_KEY=
TAVILY_API_KEY=
REDDIT_USER_AGENT=trend-research/0.1
```

Cài đặt và chạy:
```bash
git clone <repo> && cd trend-research
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # điền key
streamlit run src/app.py    # UI
# hoặc
python -m src.cli run --niches all
```

---

## 14. Kế hoạch 3 ngày (có buffer)

| Ngày | Việc | Kết quả cuối ngày |
| --- | --- | --- |
| **20/10** | Chốt niche, tạo repo, khung thư mục, `models.py`, `config`, `cache`; viết 4 collector, lưu raw JSON | `python -m src.cli collect` ra dữ liệu thô sạch cho 4 niche |
| **21/10** | `llm/` (Gemini + OpenAI + factory + cost); digest, writer, summarizer, validator; Jinja template | Chạy end-to-end bằng CLI ra `report.md` đủ cấu trúc; đối chiếu ngẫu nhiên số liệu với nguồn |
| **22/10** | Streamlit UI; chạy 2–3 báo cáo mẫu (đổi niche hoặc ngày chạy); quay video 2–3 phút; hoàn thiện README (nguồn, model, cài đặt, chi phí, cấu hình niche) | Đủ bộ nộp |
| **23/10** | Buffer: sửa lỗi, nộp | Nộp |

**Nếu trễ tiến độ, cắt theo thứ tự:** sparkline/biểu đồ → tab Dữ liệu thô → Reddit (giữ Trends + Suggest + Web Search) → UI (dùng CLI để demo).

---

## 15. Checklist nộp bài

- [ ] README đầu trang: danh mục, 4 niche, lý do chọn, seed keywords
- [ ] README: nguồn dữ liệu, công cụ, model (Gemini + gpt-4o-mini), cài đặt, chạy, chi phí mỗi báo cáo
- [ ] 2–3 báo cáo mẫu trong `reports/`
- [ ] Video demo 2–3 phút (chạy → ra báo cáo)
- [ ] Người khác clone về chạy theo README được (thử trên một máy sạch hoặc venv mới)
- [ ] Kiểm ngẫu nhiên 5–10 số liệu/keyword với nguồn để chắc không bịa

---

## 16. Rủi ro và cách xử lý

| Rủi ro | Cách xử lý |
| --- | --- |
| `pytrends` bị 429 | Sleep, retry có backoff, cache theo ngày, giữ sẵn raw data mẫu để demo |
| Reddit chặn request | User-Agent riêng, giảm số request; bỏ nguồn này nếu cần |
| LLM bịa số / link | Validator sau sinh (mục 9) và prompt "Không có dữ liệu" |
| LLM trả JSON sai | Pydantic validate, retry tối đa 2 lần; dùng JSON mode của provider |
| Hết quota free API | Chuyển provider qua dropdown; dùng cache |
| Lỗi mạng khi quay demo | Quay sau khi đã có cache, bật "Dùng cache" |
