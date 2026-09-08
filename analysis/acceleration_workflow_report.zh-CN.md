# CPU/CUDA 加速工作记录

2026-09-08。本轮已完成原型、可选 CPU 验证后端接入、大批量测量与全量端到端验收。
代码提交为 `b17a226`；本次只将已完成工作的资料保存到本地 Git，没有发布远端证据。

## 已完成与实测结果

- CUDA 和编译 CPU 原型在 9 张固定 R2 图及边界样例上通过独立枚举对照。
  CUDA 对 20 个候选集合的批量穷举有明显收益，小任务的编译 CPU 更快。
  此原型尚未接入正式生产端；[原始报告](../experiments/acceleration_v1/cuda_pilot/REPORT.zh-CN.md)
  区分首次调用、预热计时和数据传输成本。
- 正式接入的是可选 CPU 前缀补全验证：`python` 默认、`auto` 可回退、`numba` 严格要求可用。
  完整检查 512 项测试通过（2 项未安装可选依赖的跳过），mypy 现有 38 个源码文件通过；
  独立代理复核与额外有效/无效输入检查通过。
- 36 次批量测量覆盖 90、360、1,800 张图，每配置三次。
  全量快速验证中位数为：1 进程 175.092 s、
  2 进程 95.698 s、4 进程 55.162 s；
  原始 Python 四进程为 106.747 s。
  [批量报告](../experiments/acceleration_v1/batch_scaling/REPORT.zh-CN.md)保留全部范围和输入构成。
- 两组各三次全新 R2 工作流：原始 CPU 四进程生产、独立验证与分析、汇总校验。
  Python 验证组总中位数 291.299 s，Numba 验证组 216.028 s，减少 25.84%。
  三对优化组均更快；全部非计时图字段与归档一致，三个 CSV 在六次中逐字节一致。
  [端到端报告](../experiments/acceleration_v1/e2e_ab/REPORT.zh-CN.md)及
  [原始计时](../experiments/acceleration_v1/e2e_ab/timings.csv)给出完整记录。

## 使用与限制

正式命令见 [R2 使用说明](r2_usage.zh-CN.md#可选的快速-cpu-验证)。目前的全量证据支持
`--verification-backend numba --workers 4`；分析命令使用 `--verification-workers 4`。
默认仍为 Python，原始研究配置、种子和输出身份保持不变。

所有倍率都属于所声明的本机、固定样本、缓存和计时边界。批量验证与无绘图完整流程的
倍率不能互换；重复执行不构成新独立样本。生产端 CPU/CUDA 后端化仍是后续工作。

完整分阶段资料见 [归档说明](../experiments/acceleration_v1/README.md)。运行输出按阶段
压缩保存，脚本保留历史路径和当时的执行语义；源码快照不是新的通用 CLI。
