# VideoLingo — bản dịch tiếng Việt

Bản này giữ nội dung nguồn, dịch sang tiếng Việt và đọc bằng giọng nữ Việt Nam. Không trích facts để viết kịch bản mới, không thêm hook, xung đột hoặc câu kết ngoài nguồn.

## Chạy trên Windows

1. Cài Python 3.12 và FFmpeg có ffprobe, libass; kiểm tra `python --version` và `ffmpeg -version`.
2. Trong thư mục repository, chạy `python -m pip install -r requirements-upgrade.txt`.
3. Nhấp đúp `run-vietnamese.cmd`, rồi mở http://127.0.0.1:8510.

Hoặc chạy trực tiếp:

```powershell
python -m streamlit run upgrade_app_vi.py --server.address 127.0.0.1 --server.port 8510
```

Chọn font Arial trên Windows. `st.py` và `Dockerfile` gốc vẫn dành cho ứng dụng upstream; bản tiếng Việt dùng entrypoint ở trên. Bản này chạy localhost.

## Cấu hình dịch và giọng

- Trouter: nhập key vào ô mật khẩu trong sidebar, hoặc đặt `TROUTER_API_KEY` trong môi trường trước khi khởi động. Mặc định base `https://api.trouter.cloud/v1`; model có thể đổi trong sidebar.
- Genvoice: nhập key vào ô mật khẩu trong sidebar, hoặc đặt `GENVOICE_API_KEY` trong môi trường. Máy đã có credential Genvoice sẽ tiếp tục dùng credential đó khi base đúng `https://api.genvoice.pro`.
- Cấu hình giọng mặc định ở `upgrade_tts_vi_config.json`: Nhu — Calm and Confident, nữ bản ngữ Việt Nam, giọng Hà Nội; model `eleven_turbo_v2_5`, mã `vi`. Đây là cấu hình công khai, không chứa key.
- `.env.upgrade.example` là mẫu tên biến, không tự được nạp. Mã nguồn và lịch sử Git không chứa key. Repository công khai có secret `GENVOICE_API_KEY` được mã hóa trong GitHub Actions Secrets; chưa có key Trouter để lưu. Chủ repo quản lý tại Settings → Secrets and variables → Actions.
- GitHub Actions Secrets không được tải về khi clone và không tự điền vào ứng dụng local. Khi dùng máy khác cần cấu hình key tại máy đó; khi chạy workflow, phải truyền secret vào biến môi trường một cách rõ ràng. Bản này chưa có workflow dùng key.

## Luồng làm một video

1. Tạo job, nạp video hoặc tải link nếu extractor hỗ trợ.
2. Chọn và duyệt vùng che phụ đề cũ bằng khung kéo hoặc OCR.
3. Nạp SRT nguồn có timestamp. Qwen là lựa chọn bổ sung khi đã cài đủ dependency/model; không được cài kèm theo requirements-upgrade.
4. Bấm dịch bằng Trouter. Bản dịch giữ ID, thứ tự, thời gian, tên riêng, số liệu và ý nghĩa nguồn. Đọc lại và sửa caption/lời đọc nếu cần.
5. Tạo giọng. Tool đo thời lượng mỗi câu, dùng lại cache hợp lệ; lời quá dài bị chặn để sửa trước khi xuất.
6. Nghe/xem preview, duyệt nội dung và vùng che, rồi xuất MP4. Có thể tải riêng phụ đề và giọng đã tạo.

Mặc định giọng 100%, tiếng gốc 40%, tự hạ tiếng gốc xuống 15% khi có lời đọc. Các mức âm lượng độc lập, không phải tỷ lệ thời lượng. Nguồn có thoại/nhạc sẽ vẫn còn trong tiếng gốc; có thể nhập stem nền để thay thế.

Job có kịch bản viết lại từ bản tiếng Anh sẽ cần bấm khôi phục transcript nguồn trước khi dịch tiếng Việt. Thao tác này không xóa bản nháp kịch bản cũ. Bản tiếng Anh vẫn chạy qua `run-upgrade.cmd`.

## Dữ liệu và kiểm thử

Clone mới không có job sẵn. Có thể nạp video và SRT mẫu trong `demo/` để thử giao diện. Các thư mục `jobs/`, `runtime/`, file môi trường thật và credential không thuộc Git.

```powershell
python -m pip install pytest
python -m pytest upgrade_tests -q
```

Đọc `TEST_REPORT.md` để phân biệt test giả lập và request thực. Trouter chưa được thử trực tiếp khi chưa cấu hình key. Không khẳng định chất lượng dịch/đồng bộ trên video thật chỉ từ các test mẫu.

## Nguồn và giấy phép

Dựa trên Huanshere/VideoLingo, commit nền `01f843492759be9bbfd1a5cb697b799cc9de1609`. Giữ nguyên LICENSE Apache-2.0 và tài liệu upstream. Phần bổ sung nằm trong `upgrade/`, các entrypoint `upgrade_app*.py` và `upgrade_tests/`.
