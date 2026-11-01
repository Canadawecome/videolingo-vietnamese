# Báo cáo kiểm thử — cập nhật 01/11/2026

## Bản dịch tiếng Việt — 01/11/2026

- Entry riêng `upgrade_app_vi.py` / `run-vietnamese.cmd`: mặc định dịch sát nguồn sang tiếng Việt và bật lồng tiếng; không có bước viết kịch bản mới. ID, nguồn, thứ tự và timestamp được khóa khi sửa bản dịch.
- Giọng Nhu — Calm and Confident, nữ Việt Nam, giọng Hà Nội theo catalog Genvoice; model `eleven_turbo_v2_5` có xác nhận `vi-VN`. Request thật 82 ký tự tạo MP3 4,754 giây, dùng 41 credit; đúng một request tạo giọng. Xem `demo/vietnamese-female-preview.json` và nghe `demo/vietnamese-female-preview.mp3`.
- Toàn bộ `upgrade_tests`: **138 passed, 30.54 giây**. Trong đó 16 test mới kiểm tra UI tiếng Việt, giọng mặc định, không hiển thị giọng mẫu Bella, khóa dữ kiện nguồn và khôi phục transcript có giữ bản sao.
- Bản tiếng Anh vẫn có entry riêng; test xác nhận lựa chọn viết kịch bản và cấu hình mặc định cũ vẫn hoạt động.
- Trouter chưa được gọi thật vì chưa có key cấu hình. Mã nguồn phát hành là snapshot hiện tại có LICENSE và attribution, không mang lịch sử Git upstream và không chứa key. Cập nhật sau phát hành: repo đã Public; `GENVOICE_API_KEY` đã được mã hóa và lưu trong GitHub Actions Secrets theo yêu cầu. Chưa tìm thấy key Trouter để lưu.
- Nguồn giọng nữ/bản ngữ/giọng Hà Nội là metadata của provider; mẫu tạo thành công không thay thế đánh giá bằng nghe. Các giới hạn OCR, Qwen, Demucs và đồng bộ trên video thật dưới đây vẫn áp dụng.

## Ghi nhận bản trước — 30/10/2026

## Kết luận

Bản local chạy được; **chưa nghiệm thu đủ spec V1.2**. Đã bổ sung luồng dữ kiện được duyệt → kịch bản tiếng Anh Hook 0–3 giây / Conflict / Punchline, lịch lời đọc có thể chỉnh, phối âm lượng độc lập và chia phụ đề theo khoảng giọng thực. Genvoice đã tạo giọng thật thành công ở lần cập nhật trước. Chưa có `TROUTER_API_KEY` hoặc video thật do người dùng cung cấp để kiểm thử LLM + dub end-to-end. Không khẳng định đạt độ phủ OCR 98% hoặc đồng bộ lời nói ≤200 ms trên tập video thực.

## Cập nhật kịch bản, âm lượng và phụ đề

- Transcript nguồn được giữ riêng với ID câu gốc. Lần gọi LLM thứ nhất trích facts và key takeaways có dẫn chứng; người dùng sửa/duyệt trước khi viết. Lần gọi thứ hai chỉ nhận dữ kiện và điểm chính đã duyệt, không nhận lại toàn bộ lời văn transcript, để viết trực tiếp bằng tiếng Anh tự nhiên.
- Cấu trúc là Hook 0–3 giây → Conflict/thách thức có căn cứ → Punchline được dữ kiện hỗ trợ. Prompt cấm bịa sự kiện, xung đột, số liệu hoặc kết quả; nếu không có xung đột thật thì dùng thách thức/câu hỏi có căn cứ. Xác thực ID và một số số liệu dạng chữ số không thay thế việc kiểm tra ngữ nghĩa với nguồn.
- Lịch tự tạo có thể chỉnh; các cửa sổ theo thời gian, không chồng nhau, giữ mốc kết thúc cho lời đọc. Có thể chừa khoảng nghỉ tự nhiên. **Không có quota 60% thuyết minh / 40% tiếng gốc theo thời lượng.** Bản duyệt gắn với nguồn, dữ kiện, lịch, kịch bản và cấu hình xuất; thay đổi sẽ chặn dùng bản duyệt hoặc audio cũ không còn khớp.
- Âm lượng mặc định độc lập: giọng 100%, tiếng gốc 40%, tiếng gốc dưới lời đọc 15%. Duck theo khoảng TTS thực, với fade chuyển mức 100 ms hai đầu. Các tỷ lệ là gain của từng lớp, không cần cộng thành 100%; gain không đồng nghĩa độ lớn cảm nhận. Nguồn có thể còn thoại/nhạc, và có tùy chọn stem nền.
- Phụ đề kịch bản chia thành các sự kiện tối đa 8 từ, hoặc ngắn hơn để vừa vùng. Sự kiện nằm trong khoảng TTS thực đã đo; mốc chữ ước lượng theo số từ, chưa có forced alignment. Một từ không vừa vùng vẫn chặn xuất và yêu cầu chỉnh.
- Chưa chạy LLM thật vì thiếu `TROUTER_API_KEY`; không có cuộc gọi trả phí mới trong cập nhật này. Các test mới dùng phản hồi LLM/TTS giả lập và audio tone FFmpeg. Mẫu Genvoice thật bên dưới là kết quả đã có từ trước.

## Cập nhật Genvoice

- Xác minh tài liệu tại https://genvoice.pro/docs (các trang endpoint được website tải động), cùng API `/v1/models` và `/v1/default-voices` trên đúng host `api.genvoice.pro`.
- Chọn Bella — Professional, Bright, Warm; female, en, American theo catalog. Model `eleven_multilingual_v2` có trong catalog model và danh sách verified_languages của Bella.
- Tạo một request thực 124 ký tự; Genvoice báo characters_used=124, credits_deducted=124. Audio MP3 đọc được, thời lượng 8.986 giây.
- Tạo video 12.000 giây với giọng thật đã cache, timeline/ASS/narration mix thành công. Không có request tạo giọng trả phí thứ hai trong bước render này.
- Key lưu bằng Windows Credential Manager, không đưa vào config, source hoặc báo cáo. Key không được chuyển sang host khác khi redirect. Audio tải không kèm header key.
- Mốc lịch sử sau cập nhật Genvoice: 30 tests passed. Khi đó thêm 16 test offline cho async task/resume, URL audio, cache identity, metadata lỗi, POST 500 và không gửi key lúc tải audio; đây không phải tổng số test của bản hiện tại.
- AppTest không exception; dropdown mặc định đúng Bella + Multilingual v2; ô key browser để trống khi dùng Credential Manager. Kiểm tra tích hợp đổi voice chặn stale dub thành công.
- Mẫu nghe thử `demo/bella-english-preview.mp3`; video `demo/bella-english-dub.mp4`. Chưa đánh giá chất lượng giọng bằng nghe người dùng; đây là lựa chọn theo mô tả catalog và mẫu để duyệt.

## Kết quả thực tế

| Kiểm tra | Kết quả |
|---|---|
| pytest `upgrade_tests` tại mốc 30/10 | 122 passed; lượt chạy toàn bộ 19.90 giây trên máy này |
| Test hợp đồng dữ kiện/kịch bản | 65 passed, 0.43 giây; mock API, không đọc key hoặc gọi dịch vụ thật |
| Tích hợp kịch bản và phối âm | 16 test pipeline/mix passed, gồm render MP4 và đo PCM: giọng tắt thì nền giữ 40%, có giọng thì duck về 15%; không áp tỷ lệ thời lượng |
| Compile Python | Không lỗi cú pháp |
| Streamlit AppTest | Không exception ở lượt mở và lượt kiểm tra cuối; slider giọng/gốc/duck mặc định 100% / 40% / 15%, tự hạ tiếng gốc bật |
| Giao diện browser thật | Server localhost:8510 mở thành công, tab vùng che và canvas hiển thị |
| FFmpeg che solid / blur / blur+nền | Render thực thành công ở cả ba chế độ |
| Demo 960×540, 30 FPS | Trước 6.000 s / sau 6.000 s |
| Tiếng Việt ASS | Xem trực tiếp frame demo: dấu đúng, vừa vùng, không crop |
| OCR CPU EasyOCR | Clip demo 6 s, lấy mẫu 500 ms: 12 detection, gom một vùng; lưu `demo/ocr_benchmark.json` |
| API 301/401/402/404 | Mock: không retry, không gửi key theo redirect, không lộ key trong lỗi |
| API 429 | Mock: retry có giới hạn, đọc Retry-After |
| JSON dịch | Chặn thiếu/trùng ID và nội dung rỗng |
| JSON dữ kiện/kịch bản | Chặn ID thiếu/trùng/không tồn tại, nội dung rỗng, NaN/Infinity, số mới dạng chữ số không có trong dữ kiện dẫn, sai vai trò/mốc khóa và vượt ngân sách từ; giữ liên kết về nguồn |
| Cache TTS | Mock provider + audio thật: cache hit không gọi lại; file hỏng/text đổi gọi lại |
| Audio timeline | Audio test thật: giữ 3 giây, trộn narration thành công; chặn lời tràn và text sửa sau tạo giọng |
| Checkpoint | Thay nội dung file làm checkpoint không hợp lệ |
| Region validation | Chặn ngoài khung, NaN và chưa duyệt |

Audio tổng hợp trong test tự động là tone FFmpeg, **không phải kết quả ElevenLabs/Genvoice**; mẫu Bella ở mục lịch sử Genvoice là audio thật riêng. Video demo là test pattern với sub cứng do FFmpeg tạo, không phải phim thật. OCR lượt đầu tải model gặp lỗi; thử lại với model storage trong runtime của dự án thành công.

## Chưa xác minh / còn thiếu so với đặc tả

- Genvoice đã xác minh và thử thành công như mục cập nhật. Chưa thử lỗi quota/auth thực, task failed thực hoặc nhiều job dài; các nhánh này mới có kiểm thử offline.
- Trouter model ID đối chiếu danh sách công khai; thiếu `TROUTER_API_KEY`, chưa kiểm thử key thật, Chat Completions, trích dữ kiện hay viết kịch bản bằng JSON thực từ dịch vụ. Chưa đánh giá chất lượng diễn đạt tiếng Anh hoặc độ đúng ngữ nghĩa của LLM trên video thật.
- Qwen bridge và Demucs đã có nút chạy nhưng dependency/model chưa cài và chưa chạy e2e trên máy này. Luồng nhập SRT và stem nền là đường dùng được không cần ASR/tách giọng.
- Chưa benchmark OCR trên tập gán nhãn: fade, chữ nhỏ, không sub, VFR, clip dọc/ngang, scene cut; chưa adaptive scan/hysteresis theo scene. Không coi demo một clip là tiêu chí 98%.
- Chưa có feather mask, chưa tự rút gọn lời đọc bằng LLM tối đa hai vòng; câu quá dài yêu cầu sửa thủ công. Chế độ kịch bản đã tự chia caption tối đa 8 từ theo vùng chữ, nhưng chưa forced alignment; một từ vẫn tràn thì chặn và yêu cầu sửa. Chế độ dịch thường vẫn chặn caption tràn để sửa thủ công.
- Chưa kiểm thử tải link Bilibili/Douyin/Kuaishou/YouTube; phân loại lỗi downloader hiện ở mức thông báo tổng hợp. Chưa chọn từng format chi tiết; chỉ preset chất lượng.
- Chưa có HTTP API dùng chung schema hoặc lớp SSRF/redirect guard cho public server. Ứng dụng chỉ bind localhost; không dùng làm dịch vụ mạng.
- Checkpoint/hash và cache giữ bước hoàn tất; chưa có lịch trình DAG/invalidation toàn diện hay tự resume worker sau restart. Sửa dữ liệu phải bấm chạy lại bước phụ thuộc. Nguồn video bị khóa sau nạp; muốn đổi video hãy tạo job mới.
- Chưa chạy hồi quy toàn bộ pipeline upstream do dependency lớn chưa cài. Các file pipeline cũ không bị chỉnh sửa; chưa thể coi đây là bằng chứng đầy đủ về tương thích runtime.
- Font ASS cố định Arial, font đo nên giữ Arial; chưa kiểm nghiệm đổi font/fallback. Chưa đo clipping trên giọng/nền thực, mới có limiter và test kỹ thuật.

## Nguồn xác minh

- Repository/README/config và code đã clone tại commit nền, LICENSE Apache-2.0.
- https://trouter.cloud/models: công bố `gpt-5.6-sol`.
- https://elevenlabs.io/docs/api-reference/text-to-speech/convert: giao thức ElevenLabs chính thức được đối chiếu; không suy ra Genvoice tương thích.
- https://genvoice.pro/docs: đã đọc endpoint từ tài liệu tải động; xác minh thêm bằng request thực đến https://api.genvoice.pro.
