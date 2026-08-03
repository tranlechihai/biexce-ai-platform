---
name: codebase-brief
description: Sanitized codebase summary format. Apply when BX Explore distills a repo for planning, and when BX Plan/BX Director consume repo knowledge on a cloud model - the Brief is the only repo-derived artifact allowed to cross to cloud.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-explore, bx-plan, bx-director
  sources: thiết kế Zone A/B Biexce; oh-my-openagent Librarian (ý tưởng, chưng cất)
---

# Codebase Brief

Mục đích: cho phép planner (có thể chạy model cloud) hiểu repo mà **nội dung
source không rời hạ tầng công ty**. Brief là bản chưng cất — cấu trúc và chữ
ký, không phải code.

## Định dạng `.biexce/CODEBASE_BRIEF.md`

```markdown
# Codebase Brief — <repo> @ <mốc thời gian>

## 1. Bản đồ thư mục (2 cấp, kèm 1 dòng công dụng mỗi mục)
## 2. Module & trách nhiệm (module → làm gì, phụ thuộc module nào)
## 3. Public interfaces (CHỮ KÝ ONLY)
   - `POST /api/users` → tạo user (handlers/user.go:42)
   - `class AuthService { login(u,p): Token; refresh(t): Token }`
## 4. Conventions quan sát được (naming, cấu trúc test, style, framework)
## 5. Entry points & luồng chính (mô tả lời, tham chiếu path:line)
## 6. Lệnh build/test TÌM THẤY trong repo docs/CI (nguyên văn + nguồn)
## 7. Vùng rủi ro/nợ kỹ thuật thấy được · 8. Điều CHƯA xác minh
```

## Luật cứng

- **Cấm chép thân hàm/lớp** vào Brief — chỉ chữ ký + 1 dòng mô tả; snippet
  tối đa 3 dòng và chỉ khi là khai báo/config không nhạy cảm.
- Cấm secrets, connection string, token, dữ liệu người dùng.
- Mọi mục có tham chiếu `path[:line]`; điều không chắc ghi vào mục 8, không
  đoán.
- Brief dài quá ~300 dòng là dấu hiệu chưa chưng cất — tóm tắt tiếp.
