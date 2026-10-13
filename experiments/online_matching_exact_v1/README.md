# 在线匹配精确值：已保存证据

本目录收录 2026-09-27／28 已完成计算的小型 JSON 记录，支撑[四请求精确值报告](../../independent_research/online_matching_recourse/extension_20260925/报告/四请求精确值.md)。文件从原结果目录复制，本次没有重跑查询或轨迹。

- `four_exact/`：八项单链上界的求解状态、两个原子下界对手树、独立下界核验、固定序列枚举及完整汇总。
- `budget2_policy/`：显式策略的下界和锚点执行样例、已有坏例对照、6,569 条序列的历史核验摘要。

求解编码见已跟踪的 `four_exact.py`；标准库独立核验器为 `verify_four_exact.py` 和 `verify_four_budget2_policy.py`。完整 SMT 公式、求解时源码副本、整批压缩轨迹与检查日志继续保存在本机的 `results/online_matching_closure_20260927/` 和 `results/online_matching_policy_20260928/`。
