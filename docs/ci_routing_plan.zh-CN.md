# CI 分流实施计划

状态：计划已归档，尚未实施。
审查日期：2026-09-05。
审查基线：`main` 提交 `ddf6a8a9a9c2e6928c45aa158fb97da13b24e654`。

## 目的与范围

给明确的计划归档和文档索引 PR 减少无关检查，同时保留代码改动的完整验证。
本计划只设计 `docs`（轻量）和 `full`（完整）两个档位，不增加人工标签流程、
新 CI 平台、定时任务或新的合并门槛。研究检查点和源码拆分不以本计划落地为前提。

最初归档只新增本文、更新文档索引并重新生成许可证清单；下文的脚本、条件和测试
尚未实施。本轮将 CI 分流安排在记录类型拆分之后，作为
[统一实施顺序](README.md#implementation-plans) 的最后一项。

## 已核实的背景

当前工作流在 PR、推送到 `main` 和手动触发时执行。PR #22 的一次更新仅涉及计划
文档、文档索引和许可证清单，仍启动了全部检查。该次全部工作流约用 2 分 37 秒，
可读取的生效规则集所要求的检查约在 1 分 23 秒时完成。两者不是同一个等待指标。
这些是 CI 运维观察，不是算法性能或研究结论，也不是实施后的节省实测。

- [PR #22 的改动](https://github.com/Mikoto-19909/greedy-failure-structures/pull/22/files)
- [对应测试运行](https://github.com/Mikoto-19909/greedy-failure-structures/actions/runs/33951698890)
- [对应复现矩阵运行](https://github.com/Mikoto-19909/greedy-failure-structures/actions/runs/33951698933)
- [审查时的生效规则集](https://github.com/Mikoto-19909/greedy-failure-structures/rules/21541937)

传统分支保护接口在审查时返回 403；已读取的 ruleset 不能用来证明不存在另一层
附加要求。实施前重新核对实际合并门槛，保留现有必需检查名称。

跨环境复现、并行执行和独立输出校验承担不同职责。本计划保留它们在完整档位中的
覆盖，不合并验证逻辑，也不改变 timeout、确定性、配置身份或输出契约。

## 分类规则

默认档位为 `full`。只有 PR 的完整累计改动满足以下全部条件时，才输出 `docs`：

1. 至少改动一个允许进入轻量档位的文档。
2. 所有受影响路径都属于下表中的轻量文档或配套许可证清单。
3. 改动列表完整、路径可识别，且没有模式变化、符号链接或子模块等特殊变更。

| 路径或事件 | 判定 |
| --- | --- |
| `docs/README.md` | 允许进入轻量档位 |
| `docs/` 直属目录中以 `_plan.zh-CN.md` 结尾的普通文件 | 允许进入轻量档位 |
| `LICENSE_MANIFEST.json` | 仅作为上述文档改动的配套文件允许；完整许可证校验仍必跑 |
| 仅修改 `LICENSE_MANIFEST.json` | `full` |
| 根 README、贡献说明、技术契约文档、研究分析及证据 | `full` |
| 源码、测试、实验配置、依赖、工作流、脚本及其他路径 | `full` |
| 文档与代码混合修改 | `full` |
| 推送到 `main` 或手动触发 | `full` |
| 无改动、未知事件、路径解析异常、比较失败或改动列表不完整 | `full` |

这是一份窄范围允许清单，不能扩展为 `docs/**` 或所有 Markdown 文件。分类依据是
Git 中的改动，不使用 PR 标题、分支名、标签或提交信息来决定减少检查。

获取改动时比较 PR 的 base/head 的共同祖先与 head，即 PR 累计差异；不能只比较
最后一个提交。要取得相关提交对象并确认比较成功。初版可在分类任务中使用完整
历史 checkout，以减少浅克隆造成的判断分支。

用 NUL 分隔的 Git 输出处理路径，避免空格、换行和中文文件名被拆错。重命名必须
同时判断旧路径和新路径；实现上可关闭重命名识别，按删除加新增处理。已有文件的
模式变化一律走 `full`；普通文档的正常新增、删除不因此被误判为模式变化。
例如把源码重命名为计划文件，旧源码路径仍会使整个 PR 进入 `full`。

许可证清单只是分类时允许的配套路径，不是校验豁免。无效或过期清单仍必须使
现有内容边界任务失败。

## 两个档位的检查范围

下表中的名称以审查基线为准，实施前核对最新工作流。

| 检查 | `docs` | `full` |
| --- | --- | --- |
| `unit tests (ubuntu-latest, Python 3.12)` | 完整单元测试套件 | 完整单元测试套件 |
| `static type check` | 执行 | 执行 |
| `content boundary (claim mode evidence_backed_claims)`，含许可证校验 | 执行 | 执行 |
| `commit messages and authorship` | 执行 | 执行 |
| 其余系统与 Python 组合的单元测试 | 跳过 | 保留原有组合 |
| `entry points and bundled configurations` | 跳过 | 执行 |
| Starter 与 Lazy Greedy 的双系统冒烟检查 | 跳过 | 执行，保留 `workers=2` 和独立 validator |
| 复现矩阵及跨环境比较 | 跳过 | 执行，保留六组环境及 `workers=1` |

轻量档位仍运行完整的一套单元测试，包括文档声明与实现的一致性测试。分流不会
扩大 mypy 的实际覆盖范围；已有豁免的处理仍属于源码拆分计划。

## 文件改动与执行方式

| 后续实施文件 | 最小改动 |
| --- | --- |
| `.github/scripts/classify_ci_changes.py`（拟新增） | 读取事件与 Git 累计差异，执行上述固定规则，输出 `profile` 和简短原因；仅使用标准库与 Git |
| `.github/workflows/tests.yml` | 新增 `detect`；把固定 Ubuntu / Python 3.12 单元测试与其余矩阵拆开；额外任务按档位执行 |
| `.github/workflows/reproducibility-matrix.yml` | 新增 `detect`，调用同一脚本；按档位控制 benchmark 和 compare |
| `tests/test_ci_routing.py`（拟新增） | 验证分类行为、累计差异和异常回退，不冻结 YAML 排版 |
| 本文 | 实施并完成验收后更新状态和实际结果 |
| `LICENSE_MANIFEST.json` | 按暂存区重新生成 |

内容边界与提交规则工作流保持现有执行方式。固定单元测试及 mypy 不依赖 `detect`，
以便基础检查并行开始，也避免分类任务失败导致必需检查被连带跳过。

固定单元测试保留名称 `unit tests (ubuntu-latest, Python 3.12)`。额外矩阵排除这一
组合，保留其他五组环境及原来的检查名称，防止同一组合重复执行。

`detect` 将脚本输出通过 `$GITHUB_OUTPUT` 暴露为 job output。事件的 base/head 等
字段通过环境变量或结构化事件文件传给脚本，不直接插入 shell 命令。日志仅报告
档位和理由，例如“包含源码改动，执行完整检查”，不输出整个事件或环境。

额外任务使用以下条件片段。它不是完整工作流，不能单独复制后宣称实施完成：

```yaml
needs: detect
if: >-
  ${{
    !cancelled() &&
    (
      needs.detect.result != 'success' ||
      needs.detect.outputs.profile != 'docs'
    )
  }}
```

只有分类任务成功且明确输出 `docs` 时才减少检查。分类任务失败、跳过、输出缺失
或出现未知值，都使额外任务按完整档位执行；用户取消运行时停止。可恢复的读取
异常由脚本输出 `full` 并说明原因。真正的任务失败也由上述条件保留完整验证。

两个工作流分别调用同一个分类脚本；`needs` 不能跨工作流读取输出。不增加
`workflow_run` 接力、跨工作流缓存或集中调度器。由此会有两个分类任务，不能将
“四项基础检查”写成“轻量运行总共只有四个 job”。

复现工作流的 `compare` 同时依赖 `detect` 和 `benchmark`：只有档位需要完整检查
且 benchmark 矩阵成功时才比较产物。文档档位下比较任务跳过；矩阵运行失败时保留
失败状态，不下载不存在的产物或伪造比较通过。手动运行和 `main` 推送始终执行
完整路径。保留现有权限、Action 固定版本和并发取消设置。

不能用工作流级 `paths-ignore` 跳过含必需检查的工作流，否则相关检查可能一直
Pending。任务级跳过通常不会阻止合并，因此不能用“显示绿色”证明基础测试真的
执行；验收要核对步骤和实际命令。

## 实施顺序与验收

1. 从最新 `main` 建独立实现分支，核对必需检查名称和最新文件布局。
2. 先实现分类函数及 Git 差异读取，再按下表做有针对性的行为测试。
3. 修改测试和复现两个工作流；基础检查保持独立，额外矩阵共享同一判定规则。
4. 暂存变更后生成许可证清单，再运行仓库规定的检查。
5. 在实际 Actions 中验证文档 PR、混合改动 PR、手动运行和分类失败回退；记录档位、执行任务
   及跳过任务。条件与实现配对的修改按 `AGENTS.md` 做独立审查后再合并。

| 验收场景 | 必须观察到的结果 |
| --- | --- |
| 计划文档、索引及有效配套许可证清单 | `docs`；四项基础检查实际执行，额外检查跳过 |
| 仅修改技术契约文档或根 README | `full` |
| 文档 PR 中加入源码、配置、测试或工作流改动 | `full` |
| 前一提交修改代码，最后一提交只改文档 | `full`，证明读取整个 PR 的累计差异 |
| 源码重命名到允许的计划路径 | `full`，旧路径仍参与判定 |
| 允许路径内的普通文档新增、删除或重命名 | 按所有受影响路径判定，基础检查继续处理断链和清单问题 |
| 模式变化、符号链接、子模块或路径解析失败 | `full`；已有校验仍可拒绝不合法内容 |
| 仅清单变更、空列表或未知事件 | `full` |
| Git 比较失败、输出缺失、未知档位或分类 job 失败 | 完整检查运行，不能因 `needs` 默认行为全部跳过 |
| 文档改动附带过期许可证清单 | 基础许可证校验失败，不能合并 |
| 手动触发、合并后 `main` 推送 | 执行完整检查 |
| 用户取消运行 | 不再因无条件 `always()` 继续启动额外任务 |

路径分类和 Git 差异用小型临时 Git 仓库验证即可，不增加通用测试框架。调度条件
要做至少一次实际 Actions 验证，不能只测试 Python 分类函数便宣称工作流正确。

实施验证命令沿用仓库要求：

```console
python -m unittest discover -s tests -v
python .github/scripts/check_content_boundary.py --claim-mode evidence_backed_claims
python .github/scripts/build_license_manifest.py --check
python -m mypy
```

若其他计划已经合并，保留它们的文档索引条目。许可证清单冲突通过合并后的暂存
区重新生成解决，不手工拼接单行 JSON，也不覆盖其他 PR 的记录。

## 完成条件与回退

完成条件是：明确的计划归档 PR 执行轻量检查；代码、混合、未知改动及 `main`
仍执行完整检查；既有必需检查名称保留且真实运行；分类失败不会漏检；上述验收
有实际记录。达到这些条件后停止扩展，不继续增加更多档位或配置语言。

比较实施前后相同类型 PR 的全套完成时间和累计 job 时长；分类任务自身的开销
也计入，不把潜在节省写成实测。本项已纳入本轮完整交付，耗时观察不能替代
分流正确性与真实 Actions 验收，也不构成自行取消本项的条件。

发生错误分流时，通过普通 PR 回退两个工作流的分流条件，恢复全部检查，并清理
不再使用的分类脚本及测试；重新生成许可证清单。不通过删除必需检查、强推主分支
或跳过 CI 来恢复合并。

## 参考

- [现有测试工作流](../.github/workflows/tests.yml)
- [现有复现工作流](../.github/workflows/reproducibility-matrix.yml)
- [复现矩阵的验证边界](reproducibility_matrix.md)
- [任务输出与依赖](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/pass-job-outputs)
- [GitHub Actions 条件与矩阵语义](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions)
- [必需检查与跳过工作流的区别](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
