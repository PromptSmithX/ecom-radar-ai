# 🛍️ AI Product Trend Research Tool (MVP)

> **Công cụ AI tự động thu thập tín hiệu xu hướng, phân tích thị trường và đề xuất ý tưởng sản phẩm e-commerce theo từng niche.**
> Đạt chuẩn tiêu chí: **Chính xác (chống bịa số/link)**, hữu ích, tự động hóa cao, chi phí cực thấp, dễ chạy lại.

---

## 📌 1. Danh mục và Niches lựa chọn

- **Danh mục được chọn:** **Quà tặng theo mùa (Seasonal Gifts)**
- **Lý do lựa chọn:**
  - Tháng 10–12 là thời điểm cao điểm mua sắm lớn nhất năm của thị trường thương mại điện tử (Halloween, Black Friday, Cyber Monday, Giáng sinh và chuẩn bị cho Valentine).
  - Tín hiệu tìm kiếm và mức độ quan tâm của người tiêu dùng trong giai đoạn này tăng đột biến (+100% đến +650%), giúp việc phát hiện xu hướng và kiểm chứng số liệu trở nên rõ ràng, xác thực và mang tính ứng dụng kinh doanh tức thì.

### 4 Niches và Seed Keywords mục tiêu:

| # | Tên Niche | Seed Keywords gốc | Điểm nhấn thị trường |
| :-: | :--- | :--- | :--- |
| **1** | **Christmas gift ideas** | `christmas gift ideas`, `christmas gifts for mom`, `stocking stuffers` | Nhu cầu bùng nổ đỉnh điểm trong Q4, khách săn lùng các món quà thiết thực và quà cho gia đình. |
| **2** | **Gift for him** | `gifts for him`, `gifts for boyfriend`, `gifts for dad` | Niche khó chọn quà nhất theo phản ánh của khách hàng; nhu cầu cao với đồ công nghệ, EDC, phụ kiện bàn làm việc. |
| **3** | **Personalized gift** | `personalized gifts`, `custom name gift`, `engraved gift` | Biên lợi nhuận cao (60–75%), xu hướng cá nhân hóa tên/hình ảnh/sóng âm bùng nổ trên Etsy & Shopify. |
| **4** | **Valentine gift** | `valentine gifts for her`, `valentine gifts for him`, `couple gift` | Chu kỳ chuẩn bị và mua sắm sớm ngay sau Giáng sinh; khách chuộng trải nghiệm kết nối và kỷ niệm. |

*Lưu ý: Toàn bộ danh mục và niche được cấu hình động tại [`config/niches.yaml`](config/niches.yaml). Thay đổi danh mục chỉ cần chỉnh sửa file YAML này mà không phải sửa code.*

---

## 🌐 2. Nguồn dữ liệu & Cơ chế thu thập

Tool kết hợp 4 nguồn dữ liệu đa dạng để phản ánh trọn vẹn bức tranh thị trường:

1. **Google Suggest / Autocomplete:** Gọi trực tiếp endpoint gợi ý công khai của Google nhằm phát hiện các từ khóa tìm kiếm mở rộng (long-tail keywords) người dùng đang thực sự gõ nhiều nhất. (Chi phí: $0, không cần API key).
2. **Google Trends (`pytrends`):** Đo lường xu hướng tìm kiếm trong 90 ngày (`today 3-m`), phát hiện các truy vấn bứt phá mạnh (`rising / breakout queries` tăng trưởng từ +50% đến +650%).
3. **Reddit Community:** Tìm kiếm thảo luận người dùng trên các subreddit cộng đồng (`r/gifts`, `r/BuyItForLife`, `r/AskMen`, `r/Etsy`...) để trích xuất các **nỗi đau (pain points), phàn nàn thực tế và nhu cầu chưa được đáp ứng**.
4. **Web Search & Market Benchmarks (Tavily / E-commerce Listicles):** Khảo sát mức giá trung bình của thị trường, các sản phẩm bán chạy (bestsellers) trên Amazon/Etsy, và đánh giá mức độ cạnh tranh.

### 🛡️ Cơ chế chống Hallucination (Chống bịa số / URL):
- **Nguyên tắc dữ liệu thô:** LLM không tự sáng tạo số liệu. Mọi số liệu trong báo cáo bắt buộc phải xuất phát từ gói bằng chứng (*Evidence Pack*) được thu thập ở bước 1. Nếu thiếu số liệu, hệ thống tự động ghi nhận chuỗi `"Không có dữ liệu"`.
- **Bộ kiểm chứng độc lập (`src/pipeline/validator.py`):** Sau khi LLM sinh báo cáo, code Python kiểm tra chéo từng `source_url`. Nếu phát hiện URL lạ không nằm trong tập Evidence ban đầu, validator sẽ tự động loại bỏ hoặc thay thế bằng URL bằng chứng gốc tương ứng.

---

## 🛠️ 3. Công nghệ & AI Models

- **Ngôn ngữ:** Python 3.11+
- **Giao diện Web UI:** Streamlit (bảng điều khiển tương tác, thanh tiến trình trực quan, xem dữ liệu thô, tải báo cáo `.md`).
- **Giao diện dòng lệnh CLI:** Typer + Rich (thích hợp cho tự động hóa và quay video demo nhanh).
- **Mô hình hóa & Xác thực dữ liệu:** Pydantic v2 (đảm bảo tính toàn vẹn của schema đầu ra).
- **Template Báo cáo:** Jinja2 (tách bạch hoàn toàn logic sinh dữ liệu và hình thức trình bày).
- **Mô hình AI hỗ trợ:**
  - **Gemini (`google-genai`):** Mặc định sử dụng `gemini-2.5-flash` hoặc `gemini-1.5-flash` cho chất lượng hành văn tiếng Việt tự nhiên và chi phí rẻ.
  - **OpenAI (`openai`):** Hỗ trợ `gpt-4o-mini` hoặc `gpt-4o`.
  - **Mock Mode:** Chế độ chạy thử nghiệm nội bộ, hỗ trợ demo và kiểm thử toàn bộ hệ thống ngay cả khi không có kết nối internet hoặc chưa thiết lập API key.

---

## 💻 4. Cài đặt & Hướng dẫn sử dụng

### Bước 1: Khởi tạo môi trường
```bash
git clone <repo-url>
cd trend-research
python -m venv .venv

# Kích hoạt môi trường (Windows PowerShell):
.venv\Scripts\Activate.ps1
# Hoặc trên macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

### Bước 2: Thiết lập cấu hình (.env)
Sao chép file mẫu `.env.example` thành `.env` và điền API key:
```bash
cp .env.example .env
```
Nội dung file `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
REDDIT_USER_AGENT=trend-research/0.1 (by ecomm-researcher)
```
*(Nếu chưa có key, bạn vẫn có thể chạy bình thường bằng tùy chọn `mock` trên UI hoặc CLI).*

---

### Bước 3: Chạy ứng dụng

#### 🔹 Cách 1: Giao diện Web (Streamlit UI)
```bash
streamlit run src/app.py
```
- Truy cập trình duyệt tại: `http://localhost:8501`
- Chọn niche mong muốn $\rightarrow$ Bấm **"🚀 BẮT ĐẦU CHẠY NGHIÊN CỨU"** $\rightarrow$ Đọc báo cáo và tải file `.md`.

#### 🔹 Cách 2: Giao diện dòng lệnh (CLI)
```bash
# Xem danh sách niches và seed keywords
python -m src.cli list-niches

# Chạy nghiên cứu toàn bộ các niche (dùng Gemini)
python -m src.cli run --niches all --writer gemini

# Chạy thử nghiệm 1 niche cụ thể (dùng gpt-4o-mini)
python -m src.cli run --niches "gift for him" --writer openai

# Chạy demo kiểm thử nhanh không tốn token (Mock mode)
python -m src.cli run --niches all --writer mock

# Thu thập và lưu cache dữ liệu thô
python -m src.cli collect --niches all

# Dọn dẹp cache
python -m src.cli clear-cache
```

#### 🔹 Cách 3: Chạy kiểm thử tự động (Unit Tests)
```bash
pytest -v
```

---

## 💰 5. Thống kê Chi phí thực tế mỗi Báo cáo

Nhờ áp dụng mô hình kiến trúc **Digest $\rightarrow$ Write $\rightarrow$ Summarize** kết hợp bộ nhớ đệm (Cache-aside), chi phí cho mỗi lần chạy báo cáo là cực kỳ thấp:

| Thành phần | Lượng Token trung bình | Chi phí với Gemini 2.5 Flash | Chi phí với GPT-4o mini |
| :--- | :---: | :---: | :---: |
| **Bước 1: Collect** (4 nguồn) | 0 token | $0.0000 | $0.0000 |
| **Bước 2: Digest** (4 niche) | ~2,500 in / ~1,200 out | $0.0005 | $0.0011 |
| **Bước 3: Write** (4 niche) | ~3,200 in / ~2,000 out | $0.0008 | $0.0017 |
| **Bước 4: Summarize** (Top 3 ideas) | ~1,500 in / ~600 out | $0.0003 | $0.0006 |
| **Tổng cộng cho 1 báo cáo đầy đủ** | **~7,200 in / ~3,800 out** | **~$0.0016 (~40 VNĐ)** | **~$0.0034 (~85 VNĐ)** |

> 💡 **Tối ưu chi phí:** Khi bật chế độ **"Sử dụng Cache"**, toàn bộ dữ liệu thô và bằng chứng đã thu thập sẽ được tái sử dụng, giúp các lần chạy lặp lại gần như diễn ra tức thì trong vài giây với chi phí gần bằng 0.

---

## 📁 6. Cấu trúc thư mục dự án

```
ai_analyze_ecomm/
├── README.md                  # Hướng dẫn chi tiết & tài liệu dự án
├── DESIGN.md                  # Tài liệu thiết kế hệ thống chi tiết
├── TASK-1.md                  # Yêu cầu đề bài ban đầu
├── requirements.txt           # Danh mục thư viện phụ thuộc
├── .env.example               # Mẫu file biến môi trường
├── config/
│   ├── settings.yaml          # Cấu hình tham số mô hình, crawler, cache
│   └── niches.yaml            # Danh mục, các niche và từ khóa mầm
├── src/
│   ├── app.py                 # Entrypoint giao diện Web Streamlit
│   ├── cli.py                 # Entrypoint giao diện dòng lệnh Typer
│   ├── core/
│   │   ├── config.py          # Quản lý cấu hình & nạp YAML
│   │   ├── models.py          # Pydantic schemas (Niche, Evidence, NicheReport...)
│   │   └── cache.py           # Hệ thống quản lý bộ nhớ đệm file-based
│   ├── collectors/            # Module thu thập dữ liệu
│   │   ├── base.py            # Base Collector interface
│   │   ├── google_suggest.py  # Thu thập Google Autocomplete
│   │   ├── google_trends.py   # Thu thập Google Trends (pytrends + retry 429)
│   │   ├── reddit.py          # Thu thập thảo luận & than phiền từ Reddit
│   │   ├── web_search.py      # Thu thập giá & đối thủ từ Web/Benchmarks
│   │   └── registry.py        # Đăng ký & điều phối tập trung các collector
│   ├── llm/                   # Module tương tác với LLM
│   │   ├── base.py            # Base LLMClient & Usage metrics
│   │   ├── gemini_client.py   # Client Google GenAI SDK
│   │   ├── openai_client.py   # Client OpenAI SDK
│   │   ├── factory.py         # Factory tạo client (hỗ trợ cả mock)
│   │   └── cost.py            # Bảng giá & thuật toán tính token chi tiết
│   ├── pipeline/              # Chu trình xử lý 5 bước
│   │   ├── runner.py          # Nhạc trưởng điều phối pipeline
│   │   ├── digest.py          # Bước 2: Chuẩn hóa Evidence Pack
│   │   ├── writer.py          # Bước 3: Viết báo cáo NicheReport
│   │   ├── summarizer.py      # Bước 4: Xếp hạng & chọn Top 3 ideas
│   │   └── validator.py       # Bộ lọc kiểm chứng chống bịa đặt
│   ├── prompts/               # Các system prompts được tối ưu
│   │   ├── digest.md
│   │   ├── niche_report.md
│   │   └── summary.md
│   └── render/                # Kết xuất báo cáo
│       ├── renderer.py        # Jinja2 rendering engine
│       └── report.md.j2       # Template báo cáo chuẩn Markdown
├── data/
│   ├── raw/                   # Dữ liệu JSON thô đã cache
│   └── evidence/              # Gói bằng chứng đã digest
├── reports/                   # Thư mục lưu các file báo cáo markdown đầu ra
└── tests/                     # Bộ kiểm thử tự động pytest
    ├── test_collectors.py
    ├── test_llm_factory.py
    └── test_pipeline.py
```

---

## 📄 7. Báo cáo mẫu đã tạo
Các báo cáo mẫu do tool tạo ra được lưu trữ sẵn trong thư mục [`reports/`](reports/):
- [`reports/2026-10-20_quà_tặng_theo_mùa.md`](reports/2026-10-20_quà_tặng_theo_mùa.md): Báo cáo mẫu toàn diện cho cả 4 niches trong danh mục Quà tặng theo mùa.
