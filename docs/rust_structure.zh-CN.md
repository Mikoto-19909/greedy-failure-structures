# 可选 Rust 计算内核

Rust 扩展提供结构原始计数、Greedy 和 Lazy Greedy。默认后端仍为 Python；
仅显式 `backend="rust"` 加载扩展。缺依赖、非法输入或计算错误直接报错，不静默回退。
模型、结果构造、覆盖量重算、浮点除法、`math.fsum` 和 Gini 汇总留在 Python。

## 构建与调用

需要 Python 3.11+、Rust 和平台链接器。当前本机验收为 Windows x64、Python 3.12.14、
Rust 1.95.0，扩展版本 0.3.0；远端工作流使用 Python 3.12。

```console
python -m pip install ./native/structure
```

```python
from maxcover.algorithms import greedy, lazy_greedy
from maxcover.model import MaximumCoverageInstance
from maxcover.structure import analyze_instance

instance = MaximumCoverageInstance(129, (0, 1, 1 << 128, (1 << 128) | 1), 3)
metrics = analyze_instance(instance, backend="rust")
dense = greedy(instance, backend="rust")
lazy = lazy_greedy(instance, backend="rust")
assert metrics == analyze_instance(instance)
assert dense.selected == greedy(instance).selected == lazy.selected
```

扩展是独立可选包 `maxcover_structure_native`。修改 Rust 源码后重新构建并安装。
主项目可在未安装扩展的环境中继续运行默认路径。

## 保持的行为

- 固定宽度小端掩码在 Rust 中使用多字 `u64`，支持超过 64 位的全集并拒绝非法尾位。
- 结构计数按输入顺序枚举非空并集的集合对。重复集合参与频数和 Jaccard；支配计数先去重，仅计严格包含。
- 原始 `counts` 接口保留。结构适配器使用 `counts_packed` 的 little-endian `<QQ>` bytes，
  每条16字节，记录交/并计数。Rust 直接写缓冲区，Python 按原顺序流式送入 `math.fsum`，
  不再保留完整 Rust 配对元组向量或 Python Jaccard 列表。旧 wheel 缺新接口时明确提示重建。
- Greedy 平局选择较小索引，覆盖饱和后仍选满预算；返回结果继续按索引排序。
- Lazy 保持选择轨迹、刷新/弹出次数、工作量和全部非计时字段，Python 生成标准 `Solution`。
- 算法注册表、默认调度、配置、CSV、身份、随机种子和续跑规则未改变。

当前结构计算仍保留二次复杂度和全部非空集合对的编码字节，不启用原生线程并行。
固定宽度转换和结果分配有成本，不保证每种输入都更快。

## 验证

```console
python scripts/check_rust.py
python scripts/check.py --profile full
```

严格 Rust 入口要求全部内核，零测试发现或出现跳过均失败；普通 Python 检查允许可选扩展缺失。
Windows 下单独检查 Rust 时指定解释器：

```powershell
$env:PYO3_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
cargo fmt --manifest-path native/structure/Cargo.toml --check
cargo clippy --manifest-path native/structure/Cargo.toml --locked -- -D warnings
```

`.github/workflows/rust.yml` 在 Ubuntu/Windows 构建 release wheel 后严格验收。
紧凑候选本地检查共 603 项：598 通过、5 项可选跳过；mypy 42 个文件通过。
24 项 Rust 专项在现有及仅安装 wheel 的干净环境均通过，覆盖独立定义、非法输入、
Windows spawn、CSV 身份和续跑。独立复核另检查 12,288 个穷举实例、225 个宽位实例、
48 个非法调用。远端执行状态以 PR 对应提交的 CI 为准。

## 统一计时入口

完整 Git 历史可直接重建固定 24 实例及原 Python 提交的参考答案；输出目录必须不存在：

```console
python scripts/benchmark_algorithms_rust.py --output results/rust_small
python scripts/benchmark_algorithms_rust.py --output results/rust_large --large
```

也可用 `--baseline results/greedy_small_python_v2` 重放先前输入与答案。
固定语料见 [小型基线](greedy_small_baseline.zh-CN.md)。三种组合为纯 Python、仅结构 Rust、
结构和两算法均 Rust；六种顺序各测两次，包含转换和结果构造。
不含生成、首次导入、验证、写盘、进程启动；不代表完整 benchmark runner 或 R2 流程。

2026-09-19 的 24 实例配对加速中位数为 2.824 倍，加入四个较大实例的混合批次为
8.124 倍；稀疏 `(65537,160,40)` 的 Lazy 慢约 3.37 倍。有限语料观察不作为默认切换依据。
历史归因见 [Rust 性能归因](rust_performance.zh-CN.md)。紧凑通道及流式求和现已形成生产候选，
保持默认 Python；测试方向、两阶段验收和局限见 [紧凑候选验收](rust_packed_acceptance.zh-CN.md)。

旧入口已归档到本机 `results/rust_closeout_20260920/history/pre_closeout_tools.zip`，
按原 `scripts/` 路径恢复后可重放历史命令。既有输入、答案、日志、源码快照和报告均保留；
`results/` 未发布，Git 提交不自动保存这些本地数据。
