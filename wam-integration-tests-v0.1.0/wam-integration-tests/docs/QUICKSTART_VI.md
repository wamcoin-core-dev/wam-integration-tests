# Hướng dẫn sử dụng tiếng Việt

Đây là bộ **kiểm thử hệ sinh thái WAM**, bổ sung cho những gì dev đã có.
`integration/` trong repo WAM chứa adapter/cấu hình kết nối với ví và sàn;
`test/functional/` đã có test lõi blockchain. Bộ này tập trung vào tương tác
WAM node → WAM Pay → Watchtower và các tiêu chí bảo vệ dữ liệu.

## Chạy kiểm tra bộ công cụ trên Windows

Giải nén ZIP, vào thư mục có `README.md`, mở PowerShell:

```powershell
py -3 -m wam_it selftest
```

Lệnh này chạy test với dữ liệu giả và máy chủ HTTP nội bộ. Nó chưa chứng minh
WAM node hoặc thanh toán thật trên regtest hoạt động. Xem kết quả chạy node thật
đã ghi trong `docs/VALIDATION.md`.

## Khi dev review

Các tệp nên đọc trước:

1. `README.md`: phạm vi và sự khác nhau với phần integration hiện tại.
2. `docs/THREAT_MODEL.md`: bảo vệ thông tin gì, kiểm tra đến đâu.
3. `docs/TEST_CATALOG.md`: ý nghĩa từng mã test.
4. `docs/FINDINGS.md`: tiêu chí chưa đạt của phiên bản công cụ đang kiểm tra.
5. `docs/VALIDATION.md`: kết quả đã chạy và phần chưa xác minh.

`targets/` giữ nguyên mã Pay/Watchtower đã cung cấp để kết quả có thể tái hiện.
Bộ test không tự sửa hai sản phẩm rồi ghi nhận rằng bản cũ đã đạt.

## Ý nghĩa kết quả

- `pass`: ca đó đã chạy và đáp ứng điều kiện kiểm tra.
- `fail`: đã chạy nhưng không đạt tiêu chí; đọc mã tương ứng trong tài liệu.
- `error` / `not_run`: thiếu điều kiện hoặc lỗi thực thi; không được coi là đạt.

Không nhập seed, private key, ví đào coin hoặc datadir đang giữ WAM vào bộ này.
Bộ test tự tạo ví regtest và tự đào coin thử. Coin thử không có giá trị và không
phải WAM trong ví thật của anh. Báo cáo công khai chỉ chứa mã test/kết quả.

Nếu chạy lại, chọn thư mục kết quả mới:

```powershell
py -3 -m wam_it selftest --report-dir reports/lan-02
```

Việc đưa repo lên tổ chức WAM cần quyền tương ứng trên GitHub. Bản ZIP này chưa
được đăng, chuyển quyền hay gửi cho dev thay anh.
