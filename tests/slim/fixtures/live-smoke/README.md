# Slim live acceptance fixture

Đây là seed read-only để kiểm tra OpenCode/Slim, không phải project sản phẩm.
Mỗi lần chạy phải copy toàn bộ thư mục này sang một workspace tạm sạch.

- `module-a/input.txt` và `module-b/input.txt`: hai lane đọc độc lập.
- `shared.txt`: canary để kiểm tra hai writer trùng ownership được tuần tự hóa.
- `outputs/` và mọi file `.biexce/` chỉ được tạo trong bản copy, không tạo trong
  seed này.

