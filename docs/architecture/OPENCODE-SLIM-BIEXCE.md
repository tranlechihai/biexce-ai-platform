# Kiến trúc OpenCode + Slim + BIEXCE

Quyết định kiến trúc: 2026-08-13  
Tài liệu này thay thế toàn bộ thiết kế Runtime V2/V3 trước đây.

## Phạm vi

Kiến trúc này áp dụng cho runtime agent, orchestration, workflow, quyền user,
quality gate, model routing, skill/knowledge và migration.

Ngoài phạm vi: dashboard, hạ tầng Bifrost/vLLM, fine-tune model, production
deployment và source của các project smoke cũ.

## Quyết định kiến trúc

Không tiếp tục sửa hoặc mở rộng custom scheduler hiện tại của BIEXCE. Không
viết thêm một scheduler BIEXCE mới.

Kiến trúc đích gồm đúng ba lớp:

```text
OpenCode = runtime authority
  -> Oh My OpenCode Slim = orchestration engine
     -> BIEXCE = workflow/agent/skill/knowledge/quality pack
```

- OpenCode sở hữu session, parent/child, trạng thái live, permission và model.
- Slim thực sự được tích hợp để điều phối background agents, theo dõi child,
  reconcile, chạy song song và phục hồi sau gián đoạn.
- BIEXCE chỉ sở hữu chuyên môn: bảy vai trò, workflow, skill, knowledge, gate,
  quality policy, model routing, báo cáo và CLI.

## Mục tiêu cuối

Người dùng mở một project trong OpenCode/OpenChamber, chọn BX Director và đưa
ra yêu cầu một lần. Hệ thống phải:

1. Hỏi lại khi yêu cầu thật sự thiếu hoặc mâu thuẫn.
2. Tự Explore, Plan, Review Plan và dừng tại Human Gate 1.
3. Sau khi user duyệt, tự Code, Test, Fix, Review và Integration.
4. Dừng tại Human Gate 2 với evidence và báo cáo cuối.
5. Hiển thị child agents trực tiếp trong giao diện.
6. Chạy song song các task độc lập mà không gây writer conflict.
7. Phát hiện đúng trạng thái sau khi UI/server/session bị restart, reconcile
   kết quả còn sống hoặc re-dispatch an toàn từ checkpoint; không bắt user sửa
   JSON, clear lock hoặc gọi từng agent.

## Hợp đồng cốt lõi

- User là người có quyền quyết định cao nhất đối với project.
- OpenCode live session là nguồn trạng thái runtime duy nhất.
- Slim điều phối child; job board chỉ là projection để quan sát.
- BIEXCE bảo vệ chất lượng bằng evidence, không bằng metadata hoặc lock cứng.
- Không tuyên bố PASS khi check thực tế FAIL hoặc chưa chạy.
- Không xóa runtime cũ trước khi prototype vượt toàn bộ acceptance bắt buộc.

## Bộ tài liệu

- [Baseline và ranh giới chuyển đổi](BASELINE.md)
- [Kiến trúc đích và workflow](TARGET-ARCHITECTURE.md)
- [Quyền user, quality và vận hành](POLICY-OPERATIONS.md)
- [Kế hoạch migration](MIGRATION.md)
- [Acceptance, rủi ro và Definition of Done](ACCEPTANCE.md)

Đọc `TARGET-ARCHITECTURE.md` để triển khai cấu trúc runtime. Đọc
`POLICY-OPERATIONS.md` trước khi thiết kế quyền, recovery hoặc quality gate.
Mọi quyết định xóa runtime cũ phải tuân theo `MIGRATION.md` và
`ACCEPTANCE.md`.
