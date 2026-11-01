# VideoLingo Studio — bản triển khai cục bộ đầu tiên

Bản **dịch sát nội dung sang tiếng Việt, giọng nữ Việt Nam** chạy bằng `run-vietnamese.cmd`. Xem [VIETNAMESE_EDITION.md](VIETNAMESE_EDITION.md). Hướng dẫn bên dưới cũng mô tả bản tiếng Anh trước đó (`run-upgrade.cmd`), vẫn được giữ riêng.

Đây là bản chạy cục bộ cho luồng che sub → trích và duyệt dữ kiện → viết kịch bản tiếng Anh → tạo giọng, chỉnh âm lượng → preview → xuất. Chế độ sửa/dịch nội dung cũ vẫn dùng được. **Chưa đạt toàn bộ nghiệm thu V1.2**. Đọc TEST_REPORT.md để phân biệt tính năng đã thử thật, adapter chưa thử với tài khoản, và phần còn thiếu.

## Mở ứng dụng

Nhấp đúp `run-upgrade.cmd`, rồi mở http://127.0.0.1:8510. Máy hiện tại đã có Python 3.12, FFmpeg và các dependency UI/OCR. Server chỉ lắng nghe localhost, không triển khai ra Internet.

Nếu chuyển sang máy khác:

```powershell
python -m pip install -r requirements-upgrade.txt
python -m streamlit run upgrade_app.py --server.address 127.0.0.1 --server.port 8510
```

Cài FFmpeg có ffprobe và libass trong PATH. Chọn font Arial trên Windows. Để chạy Qwen, cài đầy đủ VideoLingo bằng `python installer.py` theo hướng dẫn upstream; đây là bước tải model/dependency lớn và chưa thực hiện trên máy này. Demucs là tùy chọn: có thể nhập stem nền WAV thay vì cài Demucs.

## Thử ngay không cần API

Máy phát triển có job demo đã nạp sẵn. Clone mới không chứa job; hãy tạo job rồi nạp `demo/before.mp4` và `demo/captions.srt` để thử.

1. Chọn tab Vùng che, kéo khung trên ảnh, rồi bấm Dùng vùng thủ công cho toàn video; hoặc sửa từng vùng trong bảng.
2. Tab Nội dung cho phép sửa bản dịch, lời đọc và thời gian; bấm Lưu nội dung.
3. Tab Giọng & xuất: để tắt Lồng tiếng; chọn solid, duyệt dữ liệu, bấm Xem trước hoặc Xuất MP4.
4. Tải video, ASS, SRT và báo cáo. Video demo trước/sau có tại `demo/before.mp4`, `demo/after.mp4`.

Tạo job mới cho mỗi video. Không thay nguồn trên job đã nạp để tránh tái sử dụng transcript/audio của nguồn cũ. Dừng tác vụ giữ lại bước đã xong và cache. Bấm lại bước để tiếp tục; chưa có tự động khôi phục worker sau khi đóng ứng dụng. Các job chạy tuần tự trong cùng server.

## Dịch và tạo giọng

Nhập key vào ô mật khẩu trong sidebar hoặc biến môi trường. Key Genvoice đã cấu hình được lưu trong Windows Credential Manager, target `VideoLingoStudio/Genvoice/api.genvoice.pro`; ứng dụng đọc ở server, không điền key đã lưu vào ô nhập trên browser. Key này chỉ tự nạp khi base URL đúng `https://api.genvoice.pro`. Không ghi key vào job, mã nguồn hoặc cache. File `.env.upgrade.example` là mẫu tham khảo, **không được tự động nạp**.

Trouter mặc định `https://api.trouter.cloud/v1`, model `gpt-5.6-sol` theo danh sách chính thức https://trouter.cloud/models. Nút kiểm tra model gọi `/models`; bước dịch và hai bước viết kịch bản gọi `/chat/completions` với JSON và xác thực ID. Chưa có `TROUTER_API_KEY`, nên chưa chạy LLM thật để kiểm chứng dữ kiện/kịch bản từ dịch vụ; kiểm thử hiện dùng phản hồi giả lập.

Genvoice đã xác minh qua tài liệu https://genvoice.pro/docs và request thực ngày 30/10/2026. Dùng `xi-api-key`, đọc `/v1/models` và `/v1/default-voices`; tạo `/v1/text-to-speech/{voice_id}` trả task ID, theo dõi `/v1/history/{id}`, rồi tải `result.audio_url` không kèm key, không theo redirect. Chỉ nhận URL audio HTTPS trên cùng host đã cấu hình.

Mặc định đã chọn **Bella — Professional, Bright, Warm**, nữ Anh–Mỹ, `hpp4J3VqNfWAUOO0d1Us`, với `eleven_multilingual_v2`, mã ngôn ngữ `en`. Voice/model được xác minh từ catalog của Genvoice; có thể đổi qua dropdown rồi tạo lại giọng. Cấu hình không chứa secret ở `upgrade_tts_config.json`. Mẫu thật tại `demo/bella-english-preview.mp3`, video dub tại `demo/bella-english-dub.mp4`.

Task ID được lưu ngay sau khi provider chấp nhận. Bấm lại sau gián đoạn sẽ tiếp tục cùng task. Không tự gửi lại POST khi gặp lỗi mạng/5xx có thể đã tính phí. Nếu kết quả gửi chưa xác định hoặc provider báo failed, kiểm tra lịch sử Genvoice trước khi xử lý cache task; không xóa cache để thử liên tục. Đổi voice/model/ngôn ngữ/settings sẽ chặn xuất audio cũ, yêu cầu tạo lại.

Sau khi cấu hình, thử giọng ngắn trước, rồi tạo giọng toàn bộ. Câu quá dài hơn mức tăng tốc 1.15x sẽ xuất hiện trong báo cáo và chặn render; sửa lời đọc rồi tạo lại. Audio hợp lệ có cache theo nội dung/provider/model/voice/settings. Hiện dùng sửa lời đọc thủ công, chưa tự gọi LLM rút gọn hai vòng.

## Viết kịch bản tiếng Anh từ dữ kiện

Ở tab Nội dung, chọn chế độ viết kịch bản mới. Video cần dài ít nhất 10 giây. Transcript nguồn và ID câu được giữ riêng để truy ngược; bản viết mới không ghi đè transcript nguồn.

1. Bấm **Trích Facts & Key Takeaways**. Lần gọi LLM thứ nhất chỉ trích dữ kiện có dẫn ID câu nguồn và những điểm chính có dẫn ID dữ kiện.
2. Đối chiếu tên, số liệu, mức độ chắc chắn và kết luận với transcript; sửa nội dung nếu cần, rồi bấm **Lưu & duyệt dữ kiện**. ID chỉ giúp truy nguồn, không tự chứng minh một diễn giải đúng.
3. Bấm **Tạo / đặt lại lịch lời đọc**. Hook giữ ở 0–3 giây, tiếp đến Conflict và Punchline ở cuối. Có thể sửa các mốc còn lại để phù hợp nhịp video hoặc chừa khoảng nghỉ cho tiếng động. Các cửa sổ phải theo thứ tự và không chồng nhau; không có hạn mức 60% lời đọc / 40% tiếng gốc theo thời gian.
4. Bấm **Viết Hook → Conflict → Punchline**. Lần gọi LLM thứ hai nhận dữ kiện và điểm chính đã duyệt, không nhận lại toàn bộ lời văn transcript. Kịch bản được viết trực tiếp bằng tiếng Anh tự nhiên, không dịch từng câu qua ngôn ngữ trung gian. Nếu nguồn không có xung đột thật, phần giữa dùng thách thức hoặc câu hỏi có căn cứ; câu kết mạnh phải được dữ kiện hỗ trợ, không thêm sự kiện hay số liệu.
5. Sửa caption/lời đọc, rồi bấm **Lưu & duyệt kịch bản để tạo giọng**. Giới hạn dự kiến khoảng 2,5 từ/giây cho từng cửa sổ; giọng thực được đo sau khi tạo và không được tràn mốc kết thúc đã duyệt. Sửa nguồn, dữ kiện hoặc lịch sẽ yêu cầu viết/duyệt lại phiên bản tương ứng.
6. Sang **Giọng & xuất**, tạo giọng tiếng Anh, chọn nguồn nền và chỉnh âm lượng. Xem trước toàn bộ kịch bản, nghe lại rồi đánh dấu duyệt trước khi xuất MP4. Đổi kịch bản, âm thanh, vùng che hoặc cấu hình phối sẽ yêu cầu duyệt lại bản xuất.

Phụ đề của chế độ kịch bản tự chia thành các đoạn tối đa 8 từ, ngắn hơn nếu cần để vừa vùng chữ. Mỗi đoạn nằm trong khoảng giọng TTS thực đã đo; mốc chuyển chữ được ước lượng theo số từ, **chưa có căn chỉnh cưỡng bức từng từ theo âm thanh (forced alignment)**. Vì vậy cần xem/nghe preview để kiểm tra nhịp chữ. Nếu một từ vẫn không vừa vùng, ứng dụng chặn và yêu cầu chỉnh vùng/cỡ chữ.

## Chỉnh âm lượng độc lập với lịch lời đọc

Mức khởi đầu được đề xuất là **giọng thuyết minh 100%, tiếng gốc 40%, tiếng gốc dưới lời đọc 15%**. Khi bật tự hạ tiếng gốc, nền chuyển từ 40% xuống 15% trong khoảng giọng thực, với chuyển mức 100 ms ở hai đầu. Khi không có lời đọc, nền trở về 40%; có thể tắt tự hạ hoặc chỉnh từng mức. Nếu đặt âm lượng giọng về 0%, nền giữ nguyên mức đã chọn.

Các phần trăm là hệ số khuếch đại riêng so với tín hiệu ban đầu của từng lớp âm thanh, **không cần cộng thành 100% và không chia thời lượng video theo tỷ lệ 60/40**. Hệ số này không tương đương độ lớn cảm nhận: nguồn thu to/nhỏ khác nhau vẫn cần nghe và cân lại qua preview. Mức nền khi có lời đọc được giới hạn không cao hơn mức nền bình thường.

Tiếng gốc có thể chứa cả lời thoại và nhạc, không chỉ tiếng động. Nếu muốn hạn chế lời thoại cũ, chọn stem nền đã chuẩn bị; có thể nhập WAV hoặc dùng Demucs khi đã cài dependency. Stem phải khớp thời lượng nguồn và cần nghe kiểm tra chất lượng tách.

## OCR, ASR, tải link và âm thanh

- OCR EasyOCR lấy mẫu 250 ms bằng timestamp decoder trong ROI, gom vùng và bắt buộc duyệt. Model nằm ở `runtime/easyocr`. Quét mẫu không bảo đảm bắt caption cực ngắn; chưa có scene-cut và quét tăng mật độ tự động. Không dùng confidence làm chứng nhận độ phủ.
- Qwen gọi backend upstream trong tiến trình riêng, thư mục/cấu hình job riêng; thiếu dependency sẽ báo rõ. Có thể nhập SRT từ VideoLingo cũ hoặc công cụ khác ngay.
- yt-dlp khóa 2026.10.26, không tự cập nhật. Phân tích link trước tải, chọn một mục của playlist; xác minh bằng ffprobe. Chưa kiểm thử link thực của Bilibili/Douyin/Kuaishou, không cam kết các nền tảng này đã hỗ trợ.
- Thuyết minh: chỉnh riêng giọng, tiếng gốc và mức duck như trên; chỉ giọng mới: bỏ tiếng gốc theo lựa chọn; thay thoại: dùng stem nền. Chế độ kịch bản cũng cho chọn tiếng gốc hoặc stem nền.
- SRT không giữ vị trí. ASS giữ vị trí và nền chữ. Font đo mặc định Arial, renderer hiện dùng Arial; không đổi sang font khác nếu chưa sửa đồng bộ tên font ASS.

## Lỗi thường gặp

| Thông báo | Cách xử lý |
|---|---|
| Thiếu key/model/voice/route | Hoàn tất cấu hình sidebar trước khi gọi API |
| Model không có trong provider | Kiểm tra `/models`, dùng ID đúng với tài khoản |
| 401 / 402 / 429 | Kiểm tra key / số dư / đợi hạn mức; retry tự động có giới hạn |
| Timeout | Request có thể đã tính phí; kiểm tra provider trước khi thử lại |
| Chữ tràn vùng | Mở rộng vùng, giảm cỡ chữ hoặc chia/rút gọn câu; không cắt chữ |
| Bản dịch đã thay đổi | Tạo lại giọng; cache giữ audio các câu không đổi |
| Qwen/Demucs thiếu module | Cài dependency tương ứng hoặc dùng SRT/stem có sẵn |
| OCR tải model lỗi | Kiểm tra mạng, chạy lại; có thể dùng vùng thủ công |
| Tải link lỗi | Kiểm tra extractor/cookie/quyền truy cập hoặc nhập video local |

## Mã nguồn và attribution

Nền: Huanshere/VideoLingo, commit `01f843492759be9bbfd1a5cb697b799cc9de1609`, Apache-2.0. LICENSE được giữ nguyên. Các module mới nằm trong `upgrade/`, giao diện mới `upgrade_app.py`; upstream `st.py` không bị sửa. `.gitignore` được bổ sung loại trừ dữ liệu runtime/secret. Bản này không publish hoặc fork trên GitHub.

Chạy kiểm thử: `python -m pytest upgrade_tests -q`. Tạo lại demo: `python -m upgrade_tests.make_demo`.
