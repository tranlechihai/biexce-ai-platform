---
name: eval-harness
description: Build reproducible evaluations for model-dependent behavior using versioned datasets, explicit metrics, baselines, slices, and failure analysis. Apply when shipping or changing AI behavior.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: plan, build, bx-plan, bx-code, bx-test, bx-review
  sources: NIST AI Risk Management Framework and Playbook; MLflow model evaluation documentation; OpenAI evaluation best practices
---

# AI evaluation harness

## Khi nào dùng

Dùng khi output phụ thuộc model/prompt/retrieval/tool routing hoặc khi đổi model/version. Eval đo contract của use case, không chỉ cảm nhận vài prompt đẹp.

## Nội dung

1. Định nghĩa task, population, harm/failure mode và tiêu chí go/no-go trước khi chọn metric.
2. Dataset versioned, có provenance/license/data-zone, tách dev/test và không chứa secret hoặc dữ liệu production chưa duyệt.
3. Case gồm input, expected property/reference, metadata slice và evaluator; ưu tiên assertion deterministic khi có thể.
4. Metric có threshold và direction; kết hợp task success, safety, latency/cost và human rubric cho output chủ quan.
5. Pin model/provider, prompt, tool/config, seed nếu hỗ trợ và environment; lưu raw trace đã redact đủ để tái hiện.
6. So sánh candidate với baseline trên cùng dataset; báo aggregate và slice, không để trung bình che nhóm failure.
7. Evaluator model cần version/rubric/calibration và spot-check con người; tránh dùng cùng model tự chấm không kiểm soát.
8. Phân tích failure, regression và uncertainty; promotion chỉ khi gate đạt, còn infra unavailable thì INCONCLUSIVE.

Ví dụ: routing eval có 100 case theo intent; metric đúng agent, tool denial, latency p95; so candidate với baseline và báo từng slice.

## Chống chỉ định / giới hạn

- Không dùng test set để tune rồi báo như đánh giá độc lập.
- Không coi một model-judge score là ground truth duy nhất.
- Không gửi Zone C hoặc raw Zone A lên evaluator cloud nếu policy chưa phê duyệt.
