# Rust 对照的小型固定语料

24 个实例由随机、高重叠、重复集合、严格包含四类生成器各产生 6 个。
种子为 1709、1710、1711；每类两个规模。前三类 `(n,m,k)` 为 `(64,32,8)`、
`(257,100,20)`，严格包含类为 `(64,32,8)`、`(260,100,20)`。
准确生成参数见 `scripts/benchmark_algorithms_rust.py::small_inputs`。

统一入口从完整 Git 历史读取提交 `29895c0bca44a9b0c6874e1abce5b73da96a1a91`
的原 Python 算法和结构实现，保存准确输入、答案、环境、源码及原始计时。
生成基础设施和模型由当前工作树提供；比较不同源码版本时优先重放同一份保存输入。
该参考来自主分支，其算法与结构源码已核对与初始参考 `076198f` 逐字节相同。

```console
python scripts/benchmark_algorithms_rust.py --output results/rust_small
python scripts/benchmark_algorithms_rust.py --baseline results/greedy_small_python_v2 --output results/rust_small_replay
```

原保存基线 `results/greedy_small_python_v2/inputs.json` 和 `expected.json` 保留；
统一入口重建的 24 个输入及全部非计时答案已逐项与之核对一致。
历史纯 Python 基线和结构组合结果保留在原目录；旧脚本恢复位置见
[Rust 使用说明](rust_structure.zh-CN.md)。固定生成语料不代表真实分布或最优性研究结果。
