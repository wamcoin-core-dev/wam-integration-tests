# Bắt đầu với WAM Pay

## 1. Chạy thử ngay trên Mac

Giải nén file, mở Terminal tại thư mục `wam-pay`, chạy:

```bash
python3 --version
python3 scripts/demo.py
```

Cần Python 3.11 trở lên. Trên Windows dùng `py -3` thay cho `python3`.
Mở http://127.0.0.1:8787, nhập token vừa hiện trong Terminal.

1. Tạo hóa đơn `10` WAM, nội dung `Đơn thử số 1`.
2. Bấm **Xem**, nhập khoản mô phỏng `3` WAM với `6 xác nhận` → trả một phần.
3. Thêm `7` WAM với `0 xác nhận` → chờ xác nhận.
4. Bấm **Đủ xác nhận** ở giao dịch thứ hai → đã thanh toán.
5. Bấm **Loại giao dịch** → trạng thái hạ xuống, yêu cầu kiểm tra thủ công.

Chữ **DEMO** nghĩa là hoàn toàn mô phỏng. Địa chỉ dạng `DEMO_NOT_A_WAM_ADDRESS_...`
không dùng nhận coin thật. Nhấn Ctrl+C tại Terminal để dừng.

## 2. Kết nối node WAM của anh

Node WAM đã có trên Mac có thể dùng làm nguồn đối soát nếu bật RPC, đồng bộ xong
và tải đúng ví nhận. Em chưa kết nối trực tiếp vào Mac của anh trong lần viết repo
này; cần kiểm tra thực tế theo [SETUP.md](SETUP.md).

Chuẩn bị **ví riêng cho WAM Pay**, sao lưu ví đó bằng công cụ WAM. Không nhập seed
hoặc private key vào ứng dụng này. Có thể dùng ví watch-only nếu đã thiết lập
descriptor nhận tiền hợp lệ và đủ địa chỉ dự phòng ở node.

```bash
python3 scripts/init_config.py
```

Mở `config.json`, đổi:

```json
{
  "mode": "rpc",
  "database": "data/wam-main.sqlite3",
  "rpc_url": "http://127.0.0.1:9554",
  "rpc_wallet": "wam-pay",
  "rpc_cookie_file": "/duong-dan-that-den-datadir/.cookie"
}
```

Đây là **các trường cần sửa** trong file đầy đủ, không cần xóa các trường còn lại.
Đường dẫn cookie là đường dẫn của node đang chạy. Với datadir anh tự chỉ định,
hãy tìm cookie trong đúng datadir/network đó, không suy đoán từ thư mục chứa binary.
Nếu dùng testnet/regtest phải sửa cả cổng, `expected_chain`, `expected_genesis`
và dùng database riêng. Genesis sai sẽ bị chặn.

Mac/Linux, trong cùng cửa sổ Terminal:

```bash
export WAM_PAY_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '%s\n' "$WAM_PAY_API_TOKEN"
python3 -m src --check
python3 -m src
```

Token in ra là mật khẩu truy cập bảng điều khiển cục bộ; không gửi token cho ai.
Lần chạy sau đặt lại biến môi trường như trên. Có hướng dẫn PowerShell và tài
khoản RPC riêng trong [SETUP.md](SETUP.md).

## 3. Đọc trạng thái

| Hiển thị | Cách hiểu |
|---|---|
| Chờ thanh toán | Chưa thấy khoản nhận đang có hiệu lực |
| Đã trả một phần | Chưa đủ số tiền hóa đơn |
| Chờ xác nhận | Đã thấy đủ tiền nhưng chưa đủ xác nhận |
| Đã thanh toán | Đủ tiền và đủ xác nhận theo cấu hình hóa đơn |
| Hết hạn / Thiếu tiền · hết hạn | Hóa đơn quá thời hạn, vẫn tiếp tục theo dõi địa chỉ |
| Trả muộn · cần xem | Có phần cần thiết để đủ tiền được app phát hiện sau hạn |
| Dữ liệu cũ / chưa xác minh node | Chưa được dùng kết quả cũ để quyết định giao hàng |

Nếu app tắt lúc khách trả tiền, khoản đó có thể bị xếp là trả muộn khi app bật lại.
Đây là cách xử lý thận trọng: người bán kiểm tra giao dịch và quyết định thủ công.
Tiền trả dư được hiển thị; app không tự hoàn tiền. Cờ kiểm tra sau reorg được giữ
lại kể cả khi giao dịch đủ xác nhận trở lại.

## 4. Sao lưu

```bash
python3 scripts/backup.py data/wam-main.sqlite3 /duong-dan-sao-luu/wam-pay-2026-09-28.sqlite3
```

File này lưu hóa đơn và lịch sử đối soát, **không chứa bản sao ví hoặc khóa**.
Cần sao lưu ví WAM riêng. Không chỉ copy một file SQLite đang chạy vì dữ liệu
còn có thể nằm trong WAL. Hướng dẫn phục hồi có trong [SETUP.md](SETUP.md).
