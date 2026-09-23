(() => {
  "use strict";

  const state = {
    configs: [],
    algorithms: [],
    results: [],
    jobs: [],
    replays: [],
    currentConfig: null,
    currentResult: null,
    currentReplay: null,
    language: "zh",
    pollTimer: null,
    pollingJobId: null,
    configRequestId: 0,
    configLoading: false,
    resultRequestId: 0,
    resultSelectionId: 0,
    refreshRequestId: 0,
    resultNotice: null,
    replayRequestId: 0,
    replayBusy: false,
    reportRequestId: 0,
    outputEdited: false,
  };
  const STATUS_LABELS = {
    zh: {
      queued: "排队中",
      running: "运行中",
      completed: "已完成",
      failed: "失败",
      paused: "已暂停",
      cancelled: "已取消",
      interrupted: "已中断",
    },
    en: {
      queued: "Queued",
      running: "Running",
      completed: "Completed",
      failed: "Failed",
      paused: "Paused",
      cancelled: "Cancelled",
      interrupted: "Interrupted",
    },
  };
  const GREEDY_IDS = new Set(["greedy", "greedy_baseline", "lazy_greedy"]);
  const SCENARIOS = {
    "quick.json": "quick",
    "p3_lazy_greedy.json": "lazy",
    "p4_long_tail.json": "tail",
  };
  const FRIENDLY_LABELS = {
    zh: {
      algorithm: {
        brute_force: "穷举搜索",
        branch_and_bound: "分支定界",
        branch_and_bound_enhanced: "增强分支定界",
        bnb_baseline: "分支定界基线",
        bnb_enhanced: "增强分支定界",
        bnb_reference: "分支定界参考",
        cp_sat_oracle: "CP-SAT 精确求解",
        greedy: "贪心算法",
        greedy_baseline: "贪心算法基线",
        lazy_greedy: "惰性贪心",
        local_search: "局部搜索",
        multi_start_local_search: "多起点局部搜索",
        randomized_greedy: "随机贪心",
      },
      case: {
        uniform_sparse: "均匀分布 · 稀疏",
        uniform_dense: "均匀分布 · 稠密",
        overlap_core: "高重叠 · 核心",
        overlap_moderate: "高重叠 · 中等",
        overlap_extreme: "高重叠 · 极端",
        four_clusters: "四簇聚类",
        eight_clusters: "八簇聚类",
        greedy_trap: "贪心陷阱",
        greedy_trap_small: "贪心陷阱 · 小型",
        greedy_trap_large: "贪心陷阱 · 大型",
        uniform: "均匀分布",
        high_overlap: "高重叠",
        clustered: "聚类结构",
        fixed_size: "固定大小",
        long_tail: "长尾",
        duplicate_heavy: "重复密集",
        dominated_heavy: "支配密集",
        mixed_cluster: "混合聚类",
        adversarial: "对抗结构",
      },
      artifact: {
        "reference_coverage_by_case.svg": "各案例最优参考覆盖情况",
        "results_summary.md": "报告摘要",
        "gap_by_family.svg": "按案例族查看覆盖差距",
        "runtime_by_algorithm.svg": "按算法查看运行耗时",
        "gap_by_case.svg": "按案例查看覆盖差距",
        "gap_vs_structural_parameter.svg": "差距与结构参数关系",
        "local_search_recovery.svg": "局部搜索恢复情况",
        "quality_runtime_pareto.svg": "质量与耗时权衡",
        "runtime_scaling.svg": "运行耗时扩展",
        "node_scaling.svg": "搜索节点扩展",
        "timeout_by_case.svg": "按案例查看超时",
      },
    },
    en: {
      algorithm: {
        brute_force: "Brute Force",
        branch_and_bound: "Branch and Bound",
        branch_and_bound_enhanced: "Enhanced Branch and Bound",
        bnb_baseline: "Branch and Bound Baseline",
        bnb_enhanced: "Enhanced Branch and Bound",
        bnb_reference: "Branch and Bound Reference",
        cp_sat_oracle: "CP-SAT Exact Solver",
        greedy: "Greedy",
        greedy_baseline: "Greedy Baseline",
        lazy_greedy: "Lazy Greedy",
        local_search: "Local Search",
        multi_start_local_search: "Multi-start Local Search",
        randomized_greedy: "Randomized Greedy",
      },
      case: {
        uniform_sparse: "Uniform · Sparse",
        uniform_dense: "Uniform · Dense",
        overlap_core: "High Overlap · Core",
        overlap_moderate: "High Overlap · Moderate",
        overlap_extreme: "High Overlap · Extreme",
        four_clusters: "Four Clusters",
        eight_clusters: "Eight Clusters",
        greedy_trap: "Greedy Trap",
        greedy_trap_small: "Greedy Trap · Small",
        greedy_trap_large: "Greedy Trap · Large",
        uniform: "Uniform",
        high_overlap: "High Overlap",
        clustered: "Clustered",
        fixed_size: "Fixed Size",
        long_tail: "Long Tail",
        duplicate_heavy: "Duplicate Heavy",
        dominated_heavy: "Dominated Heavy",
        mixed_cluster: "Mixed Cluster",
        adversarial: "Adversarial",
      },
      artifact: {
        "results_summary.md": "Report summary",
        "reference_coverage_by_case.svg": "Optimal-reference coverage by case",
        "gap_by_family.svg": "Coverage gap by family",
        "runtime_by_algorithm.svg": "Runtime by algorithm",
        "gap_by_case.svg": "Coverage gap by case",
        "gap_vs_structural_parameter.svg": "Gap vs. structural parameter",
        "local_search_recovery.svg": "Local-search recovery",
        "quality_runtime_pareto.svg": "Quality/runtime trade-off",
        "runtime_scaling.svg": "Runtime scaling",
        "node_scaling.svg": "Search-node scaling",
        "timeout_by_case.svg": "Timeouts by case",
      },
    },
  };
  const I18N = {
    zh: {
      "document.title": "Maximum Coverage · 成果展板",
      "brand.title": "实验成果展板",
      "topbar.localOnly": "仅限本机",
      "topbar.connecting": "连接中…",
      "topbar.connected": "引擎已连接",
      "topbar.offline": "离线",
      "topbar.language": "语言",
      "entry.ariaLabel": "实验入口",
      "entry.kicker": "入口 · 启动实验",
      "entry.title": "你这次想看什么？",
      "entry.lede": "不确定就选第一个。选择方案后，先看说明和运行规模，再决定是否开始。",
      "fields.configFile": "配置文件",
      "fields.outputName": "结果文件夹名称",
      "fields.outputPlaceholder": "例如 quick-dashboard",
      "fields.forceRun": "重新计算全部任务",
      "actions.runBenchmark": "运行实验",
      "actions.refreshResults": "刷新",
      "actions.runReplay": "运行回放",
      "plan.instances": "实例总数",
      "plan.repetitions": "每个案例重复数",
      "plan.runs": "预计算法运行",
      "run.idle": "准备就绪后，点击“运行实验”；进度会显示在这里。",
      "run.queued": "任务已排队…",
      "run.complete": "运行完成：results/{output}",
      "run.failed": "运行失败：{error}",
      "config.noConfigs": "暂无可用 JSON 配置",
      "gap.ariaLabel": "差距光谱",
      "gap.kicker": "差距光谱 · 贪心在哪里失败",
      "gap.title": "贪心在哪里失败",
      "gap.lede":
        "比较本次样本中贪心算法相对最优值的覆盖差距。数值越大，说明这批样本上损失的覆盖越多；不代表所有同类实例。",
      "gap.noSource": "尚未选择结果集",
      "gap.empty": "还没有可展示的差距。请先选择已有结果，或运行入门示例；缺少最优参考时也不显示差距。",
      "gap.note":
        "条带长度 = 贪心类算法与最优解的平均差距（mean_optimality_gap），按差距从大到小排列。",
      "gallery.ariaLabel": "成果画廊",
      "gallery.kicker": "成果 · 结果画廊",
      "gallery.title": "查看实验结果",
      "gallery.lede": "选择一次实验，先比较算法，再查看图表与完整报告。可以直接阅读已有结果。",
      "gallery.empty":
        "还没有实验结果。先选用入门示例，再运行实验；完成后这里会显示报告与图表。",
      "gallery.summaryKicker": "对照 · 摘要",
      "gallery.summaryTitle": "算法对照",
      "gallery.reportDescription": "完整报告包含配置与种子、统计口径、各案例结果和结论限制。下方图表可点击放大。",
      "gallery.openReport": "打开完整报告（Markdown）↗",
      "gallery.zoomHint": "点击放大",
      "lightbox.close": "关闭",
      "lightbox.escHint": "Esc 关闭",
      "results.updated": "结果文件更新时间 {time}",
      "results.loading": "正在加载 {name}…",
      "results.failed": "无法读取 {name}。请重试或选择其他结果。",
      "results.fallback": "原选择 {name} 已不存在或无法读取，已尝试其他结果。",
      "results.failureCount": "已保存异常案例文件 {count} 个",
      "results.noResult": "暂无结果",
      "results.noSummary": "没有汇总记录。",
      "table.case": "案例",
      "table.algorithm": "算法",
      "table.runs": "运行次数",
      "table.coverage": "平均覆盖",
      "table.gap": "平均差距",
      "table.runtime": "平均耗时",
      "table.timeouts": "超时",
      "replay.ariaLabel": "失败案例回放",
      "replay.kicker": "回放 · 重现失败",
      "replay.title": "已保存案例回放",
      "replay.lede": "运行超时或错误时会自动保存案例文件；贪心未达最优不一定生成文件。",
      "replay.noFiles": "此范围暂无可回放文件",
      "replay.recordedAlgorithm": "使用记录算法",
      "replay.outputEmpty": "有案例文件时可重现计算并核对结果；没有文件不影响查看报告。",
      "replay.running": "正在运行回放…",
      "replay.match": "匹配 · 与记录结果一致",
      "replay.mismatch": "不匹配 · 与记录结果不同",
      "replay.noCompare": "运行完成 · 没有记录可比较",
      "replay.algorithm": "算法",
      "replay.status": "状态",
      "replay.coverage": "覆盖",
      "replay.selected": "已选择",
      "welcome.kicker": "第一次使用",
      "welcome.title": "同样的选择次数，哪种算法覆盖更多？",
      "welcome.lede": "从候选集合中选出少数几个，让它们覆盖尽可能多的元素。这里可以比较贪心、局部搜索和精确算法的结果。",
      "welcome.step1": "选一个小例子",
      "welcome.detail1": "入门示例已配好参数，无需编辑文件。",
      "welcome.step2": "运行并等待完成",
      "welcome.detail2": "先确认运行规模，再点击“运行实验”。",
      "welcome.step3": "比较覆盖与差距",
      "welcome.detail3": "结果自动选中；先看算法对照，再看图表。",
      "welcome.useQuick": "选用入门示例",
      "welcome.viewResults": "查看已有结果",
      "welcome.note": "选择示例不会立即运行；查看已有结果也不会重新计算。",
      "welcome.steps": "查看三步操作流程",
      "scenario.group": "按目的选择方案",
      "scenario.quick.badge": "第一次用 · 推荐",
      "scenario.quick.title": "先看懂算法差别",
      "scenario.quick.description": "用几种小型实例比较贪心、局部搜索与精确算法，认识覆盖量和差距。",
      "scenario.lazy.badge": "下一步 · 算法比较",
      "scenario.lazy.title": "比较普通与惰性贪心",
      "scenario.lazy.description": "对照两种贪心实现的覆盖结果与耗时，并用精确算法作为参考。",
      "scenario.tail.badge": "进一步 · 结构探索",
      "scenario.tail.title": "观察长尾结构的影响",
      "scenario.tail.description": "改变元素被集合覆盖的偏斜程度，观察贪心差距与局部搜索恢复情况。",
      "scenario.custom": "自选方案：查看其他配置",
      "scenario.customHelp": "已有配置包括方法检查和更大规模扫描。请选择与你的问题匹配的配置，并核对下方预览；名称中的 full 不代表已完成研究的全套复现。",
      "scenario.selected": "当前方案",
      "scenario.customGoal": "这是自选配置。运行规模和算法来自当前文件；请确认它对应你想研究的问题。",
      "scenario.loading": "正在读取方案并核对规模…此时不会启动实验。",
      "scenario.ready": "方案可运行。以下数量来自当前配置；耗时取决于实例与机器，不作固定时长承诺。",
      "scenario.invalid": "方案尚不可运行，请查看下方错误信息或改选其他方案。",
      "scenario.none": "暂无可用方案",
      "config.quickLabel": "入门示例 · quick.json（推荐）",
      "fields.outputHelp": "结果保存在本机 results/ 下。同名且配置兼容时复用已完成计算；换个文件夹名称可保留独立的一次运行。",
      "fields.advanced": "高级选项",
      "fields.forceHelp": "忽略已有检查点并重建该目录的结果。首次使用无需勾选。",
      "results.selectLabel": "查看哪次实验",
      "guide.coverage": "覆盖的元素数，越多越好。",
      "guide.gap": "相对已证最优值的覆盖损失，越小越好；0% 表示达到最优，— 表示缺少参考。",
      "guide.runtime": "同一实例上越短越快，受本机和实例规模影响。",
      "guide.scope": "这些数值描述当前样本，不能直接推广到所有实例；入门示例用于熟悉操作。",
      "fields.nameRule": "1–81 个字符，以英文字母或数字开头；其余可用英文字母、数字、点、下划线、短横线。",
      "fields.nameInvalid": "本次未启动：请按上方规则填写结果名称。",
      "run.lastJob": "最近任务",
      "run.notStarted": "本次未启动：{error}",
      "replay.scope": "案例来源",
      "replay.current": "当前结果的案例",
      "replay.others": "其他已保存案例（包括没有报告的目录）",
      "replay.file": "选择案例文件",
      "replay.algorithmLabel": "回放算法",
      "replay.emptyHelp": "此范围没有案例文件，无法运行回放。可切换“其他已保存案例”；正常完成的实验没有异常文件也能查看报告。",
      "replay.failed": "案例无法回放，请检查文件或改选其他案例。详情：{error}",
      "report.open": "阅读完整报告",
      "report.close": "返回结果",
      "report.source": "下载原始 Markdown",
      "report.language": "报告保留原文语言；项目生成正文以英文为主，不随界面语言切换。",
      "report.loading": "正在读取报告…",
      "report.failed": "报告无法读取，请刷新结果后重试。",
      "nav.summary": "算法对照",
      "nav.charts": "图表与报告",
      "nav.replay": "案例回放",
      "nav.label": "结果内容导航",
      footer: "Maximum Coverage · 本地成果展板 · CLI 仍可使用",
    },
    en: {
      "document.title": "Maximum Coverage · Result wall",
      "brand.title": "Result wall",
      "topbar.localOnly": "LOCAL ONLY",
      "topbar.connecting": "Connecting…",
      "topbar.connected": "Engine connected",
      "topbar.offline": "Offline",
      "topbar.language": "Language",
      "entry.ariaLabel": "Experiment entry",
      "entry.kicker": "ENTRY · START A RUN",
      "entry.title": "What would you like to explore?",
      "entry.lede":
        "Not sure? Choose the first option. Read its purpose and planned size before deciding to run it.",
      "fields.configFile": "Configuration",
      "fields.outputName": "Result folder name",
      "fields.outputPlaceholder": "e.g. quick-dashboard",
      "fields.forceRun": "Recompute all tasks",
      "actions.runBenchmark": "Run experiment",
      "actions.refreshResults": "Refresh",
      "actions.runReplay": "Run replay",
      "plan.instances": "Total instances",
      "plan.repetitions": "Repetitions per case",
      "plan.runs": "Planned algorithm runs",
      "run.idle": "When ready, choose Run experiment. Progress appears here.",
      "run.queued": "Job queued…",
      "run.complete": "Run complete: results/{output}",
      "run.failed": "Run failed: {error}",
      "config.noConfigs": "No JSON configurations available",
      "gap.ariaLabel": "Gap spectrum",
      "gap.kicker": "GAP SPECTRUM · WHERE GREEDY FAILS",
      "gap.title": "Where greedy fails",
      "gap.lede":
        "Compare greedy's coverage gap to the optimum in this sample. Higher values mean more coverage was lost here; they do not describe every instance in that family.",
      "gap.noSource": "No result set selected",
      "gap.empty": "No gap to display yet. Select a saved result or run the introductory example. Gaps also require an optimal reference.",
      "gap.note":
        "Band length = mean optimality gap of greedy-family algorithms, sorted from the largest gap.",
      "gallery.ariaLabel": "Result gallery",
      "gallery.kicker": "GALLERY · RESULTS",
      "gallery.title": "Explore results",
      "gallery.lede":
        "Choose a run, compare algorithms, then explore charts and the full report. Saved results can be read without running anything.",
      "gallery.empty":
        "No results yet. Select the introductory example and run it; its report and charts will appear here.",
      "gallery.summaryKicker": "TABLE · COMPARISON",
      "gallery.summaryTitle": "Algorithm comparison",
      "gallery.reportDescription": "The full report includes configuration and seeds, metric definitions, case results, and limitations. Click a chart below to enlarge it.",
      "gallery.openReport": "Open full report (Markdown) ↗",
      "gallery.zoomHint": "Click to enlarge",
      "lightbox.close": "Close",
      "lightbox.escHint": "Esc to close",
      "results.updated": "Result files updated {time}",
      "results.loading": "Loading {name}…",
      "results.failed": "Cannot read {name}. Retry or select another result.",
      "results.fallback": "Previous selection {name} is missing or unreadable; other results were tried.",
      "results.failureCount": "{count} saved execution-issue files",
      "results.noResult": "No results",
      "results.noSummary": "No summary records.",
      "table.case": "Case",
      "table.algorithm": "Algorithm",
      "table.runs": "Runs",
      "table.coverage": "Mean coverage",
      "table.gap": "Mean gap",
      "table.runtime": "Mean runtime",
      "table.timeouts": "Timeouts",
      "replay.ariaLabel": "Failure replay",
      "replay.kicker": "REPLAY · REPRODUCE FAILURE",
      "replay.title": "Saved case replay",
      "replay.lede": "Timeouts and execution errors save case files automatically; a greedy optimality gap does not necessarily create a file.",
      "replay.noFiles": "No replay files in this scope",
      "replay.recordedAlgorithm": "Use recorded algorithm",
      "replay.outputEmpty": "Replay saved cases to check their results. No case files are needed to read the reports.",
      "replay.running": "Running replay…",
      "replay.match": "Match · same as recorded result",
      "replay.mismatch": "Mismatch · different from recorded result",
      "replay.noCompare": "Run complete · nothing to compare",
      "replay.algorithm": "Algorithm",
      "replay.status": "Status",
      "replay.coverage": "Coverage",
      "replay.selected": "Selected",
      "welcome.kicker": "FIRST VISIT",
      "welcome.title": "Same selection budget. Which algorithm covers more?",
      "welcome.lede": "Choose a few candidate sets to cover as many elements as possible. Compare greedy, local search, and exact algorithms here.",
      "welcome.step1": "Choose a small example",
      "welcome.detail1": "The introductory example is ready to use; no file editing needed.",
      "welcome.step2": "Run and wait for completion",
      "welcome.detail2": "Check the planned size, then choose Run experiment.",
      "welcome.step3": "Compare coverage and gap",
      "welcome.detail3": "Results are selected automatically. Start with the comparison, then the charts.",
      "welcome.useQuick": "Use introductory example",
      "welcome.viewResults": "View saved results",
      "welcome.note": "Selecting an example does not start it. Viewing saved results does not run calculations.",
      "welcome.steps": "Show the three-step workflow",
      "scenario.group": "Choose a plan by purpose",
      "scenario.quick.badge": "FIRST VISIT · RECOMMENDED",
      "scenario.quick.title": "Understand algorithm differences",
      "scenario.quick.description": "Compare greedy, local search, and exact algorithms on small instances to understand coverage and gap.",
      "scenario.lazy.badge": "NEXT · ALGORITHM COMPARISON",
      "scenario.lazy.title": "Compare ordinary and lazy greedy",
      "scenario.lazy.description": "Compare the coverage and runtime of two greedy implementations, with an exact algorithm as reference.",
      "scenario.tail.badge": "EXPLORE · INSTANCE STRUCTURE",
      "scenario.tail.title": "Explore long-tail structure",
      "scenario.tail.description": "Vary how unevenly elements are covered by sets, then inspect greedy gaps and local-search recovery.",
      "scenario.custom": "Choose another configuration",
      "scenario.customHelp": "Other files include method checks and larger scans. Match the configuration to your question and inspect the preview. The name full does not mean a complete reproduction of published research.",
      "scenario.selected": "SELECTED PLAN",
      "scenario.customGoal": "This is a custom selection. The size and algorithms come from the current file; check that it matches your question.",
      "scenario.loading": "Reading the plan and checking its size… No experiment starts during this step.",
      "scenario.ready": "Ready to run. Counts below come from the current configuration. Runtime depends on the instances and machine.",
      "scenario.invalid": "This plan is not ready to run. See the error below or choose another plan.",
      "scenario.none": "No plan available",
      "config.quickLabel": "Introductory example · quick.json (recommended)",
      "fields.outputHelp": "Results stay under the local results/ folder. A compatible run with the same name reuses completed calculations; use a new folder name for a separate run.",
      "fields.advanced": "Advanced options",
      "fields.forceHelp": "Ignore existing checkpoints and rebuild results in this folder. Leave unchecked on your first visit.",
      "results.selectLabel": "Choose a saved run",
      "guide.coverage": "Number of covered elements. Higher is better.",
      "guide.gap": "Coverage lost relative to a proven optimum. Lower is better: 0% is optimal; — means no reference.",
      "guide.runtime": "Lower is faster on the same instance. Depends on this machine and instance size.",
      "guide.scope": "These values describe this sample, not every possible instance. The introductory example helps you learn the workflow.",
      "fields.nameRule": "1–81 characters. Start with an ASCII letter or digit; then use letters, digits, dots, underscores or hyphens.",
      "fields.nameInvalid": "Not started: enter a result name following the rule above.",
      "run.lastJob": "Latest job",
      "run.notStarted": "Not started: {error}",
      "replay.scope": "Case source",
      "replay.current": "Cases from the current result",
      "replay.others": "Other saved cases (including folders without reports)",
      "replay.file": "Choose a case file",
      "replay.algorithmLabel": "Replay algorithm",
      "replay.emptyHelp": "No case files in this scope, so replay is unavailable. Try Other saved cases. Completed experiments can have reports without execution-issue files.",
      "replay.failed": "Cannot replay this case. Check the file or choose another case. Details: {error}",
      "report.open": "Read full report",
      "report.close": "Back to results",
      "report.source": "Download original Markdown",
      "report.language": "Original report language, mainly English for generated reports; changing the interface language does not translate the report.",
      "report.loading": "Loading report…",
      "report.failed": "Cannot read the report. Refresh results and retry.",
      "nav.summary": "Algorithm comparison",
      "nav.charts": "Charts and report",
      "nav.replay": "Case replay",
      "nav.label": "Result navigation",
      footer: "Maximum Coverage · local result wall · CLI remains available",
    },
  };
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function t(key, values = {}) {
    let template = I18N[state.language]?.[key] || I18N.en[key] || key;
    Object.entries(values).forEach(([name, value]) => {
      template = template.replaceAll(`{${name}}`, String(value));
    });
    return template;
  }

  function initialLanguage() {
    try {
      return localStorage.getItem("maxcover-language") === "en" ? "en" : "zh";
    } catch (_error) {
      return "zh";
    }
  }

  function savedResult() {
    try { return localStorage.getItem("maxcover-result"); }
    catch (_error) { return null; }
  }

  function rememberResult(name) {
    try { localStorage.setItem("maxcover-result", name); }
    catch (_error) { /* The current session still works without storage. */ }
  }

  function applyLanguage(language) {
    state.language = language === "en" ? "en" : "zh";
    try {
      localStorage.setItem("maxcover-language", state.language);
    } catch (_error) {
      /* Private browsing may disable localStorage. */
    }
    document.documentElement.lang = state.language === "en" ? "en" : "zh-CN";
    $$("[data-language]").forEach((button) =>
      button.classList.toggle(
        "active",
        button.dataset.language === state.language,
      ),
    );
    $$("[data-i18n]").forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    $$("[data-i18n-placeholder]").forEach((element) => {
      element.placeholder = t(element.dataset.i18nPlaceholder);
    });
    $$("[data-i18n-aria]").forEach((element) => {
      element.setAttribute("aria-label", t(element.dataset.i18nAria));
    });
    if (state.outputEdited) validateOutput();
  }

  function friendlyLabel(value, kind) {
    if (!value) return "—";
    return (
      FRIENDLY_LABELS[state.language]?.[kind]?.[value] ||
      value
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase())
    );
  }

  function annotatedNode(value, kind) {
    const wrapper = document.createElement("span");
    wrapper.className = "annotated-value";
    const label = document.createElement("strong");
    label.textContent = friendlyLabel(value, kind);
    const raw = document.createElement("code");
    raw.textContent = value;
    wrapper.append(label, raw);
    return wrapper;
  }

  function formatNumber(value, digits = 4) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return number.toLocaleString(state.language === "en" ? "en-US" : "zh-CN", {
      maximumFractionDigits: digits,
    });
  }

  function formatPercent(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    return Number.isFinite(number)
      ? `${(number * 100).toFixed(2)}%`
      : String(value);
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat(
      state.language === "en" ? "en-US" : "zh-CN",
      {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      },
    ).format(date);
  }

  function setMessage(selector, message, error = false) {
    const element = $(selector);
    element.textContent = message;
    element.classList.toggle("hidden", !message);
    element.classList.toggle("error", error);
  }

  function setSelect(selector, options, emptyLabel, includeEmpty = false) {
    const select = $(selector);
    select.replaceChildren();
    if (!options.length) {
      select.append(new Option(emptyLabel, ""));
      select.disabled = true;
      return;
    }
    select.disabled = false;
    if (includeEmpty) select.append(new Option(emptyLabel, ""));
    options.forEach((option) =>
      select.append(new Option(option.label, option.value)),
    );
  }

  /* ── Entry band ────────────────────────────────────── */

  function renderConfig(configInfo) {
    state.currentConfig = configInfo;
    const loading = configInfo.loading === true;
    const scenario = SCENARIOS[configInfo.path];
    $$('[data-scenario]').forEach((button) =>
      button.setAttribute("aria-pressed", String(button.dataset.scenario === configInfo.path)),
    );
    $("#selection-title").textContent = scenario
      ? t(`scenario.${scenario}.title`)
      : configInfo.plan?.name || configInfo.path || t("scenario.none");
    $("#selection-goal").textContent = scenario
      ? t(`scenario.${scenario}.description`)
      : t("scenario.customGoal");
    $("#selection-status").textContent = t(loading ? "scenario.loading" : configInfo.valid ? "scenario.ready" : "scenario.invalid");
    $("#selection-file").textContent = configInfo.path ? `configs/${configInfo.path}` : "";
    setMessage(
      "#run-message",
      loading || configInfo.valid ? "" : configInfo.error || "",
      !loading && !configInfo.valid,
    );
    $("#run-button").disabled = loading || !configInfo.valid || Boolean(state.pollingJobId);
    const strip = $("#plan-strip");
    strip.classList.toggle("hidden", loading || !configInfo.valid);
    if (loading || !configInfo.valid) return;
    const plan = configInfo.plan;
    $("#plan-name").textContent = plan.name;
    $("#plan-instances").textContent = formatNumber(plan.instance_count, 0);
    $("#plan-repetitions").textContent = formatNumber(plan.repetitions, 0);
    $("#plan-runs").textContent = formatNumber(plan.algorithm_run_count, 0);
    $("#algorithm-plan").replaceChildren(
      ...plan.runs_by_algorithm.map((entry) => {
        const tag = document.createElement("span");
        tag.className = "case-tag";
        const name = annotatedNode(entry.algorithm, "algorithm");
        const count = document.createElement("span");
        count.textContent = ` · ${formatNumber(entry.runs, 0)}`;
        tag.append(name, count);
        return tag;
      }),
    );
    const output = $("#output-name");
    if (!state.outputEdited)
      output.value = configInfo.path.replace(/\.json$/i, "");
    if (state.outputEdited) validateOutput();
  }

  async function loadConfig(path) {
    const requestId = ++state.configRequestId;
    state.configLoading = Boolean(path);
    if (!path) {
      state.configLoading = false;
      renderConfig({ path: "", valid: false, source: null });
      return;
    }
    renderConfig({ path, valid: false, loading: true, source: null });
    try {
      const configInfo = await api(
        `/api/config?path=${encodeURIComponent(path)}`,
      );
      if (
        requestId !== state.configRequestId ||
        $("#config-select").value !== path
      )
        return;
      state.configLoading = false;
      renderConfig({ ...configInfo, path });
    } catch (error) {
      if (
        requestId !== state.configRequestId ||
        $("#config-select").value !== path
      )
        return;
      state.configLoading = false;
      renderConfig({ path, valid: false, error: error.message });
    }
  }

  function renderJobLine() {
    const line = $("#job-line");
    const dot = document.createElement("span");
    dot.className = "job-dot";
    if (!state.jobs.length) {
      dot.classList.add("idle");
      line.replaceChildren(dot, document.createTextNode(t("run.idle")));
      return;
    }
    const job = state.jobs[0];
    dot.classList.add(job.status);
    line.replaceChildren(
      dot,
      document.createTextNode(
        `${t("run.lastJob")} · ${STATUS_LABELS[state.language][job.status] || job.status} · ${job.config} → results/${job.output}${job.progress ? ` · ${job.progress.saved_runs}/${job.progress.total_runs} ${state.language === "zh" ? "已写入检查点" : "checkpointed"}` : ""}`,
      ),
    );
  }

  function validateOutput() {
    const input = $("#output-name");
    const valid = /^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$/.test(input.value);
    input.setAttribute("aria-invalid", String(!valid));
    setMessage("#output-error", valid ? "" : t("fields.nameInvalid"), !valid);
    return valid;
  }

  async function runBenchmark() {
    if (!validateOutput()) { $("#output-name").focus(); return; }
    const selectedConfigPath = $("#config-select").value;
    if (
      state.configLoading ||
      !state.currentConfig?.valid ||
      state.currentConfig.path !== selectedConfigPath ||
      typeof state.currentConfig.config_hash !== "string"
    )
      return;
    const button = $("#run-button");
    button.disabled = true;
    setMessage("#run-message", t("run.queued"));
    try {
      const job = await api("/api/run", {
        method: "POST",
        body: JSON.stringify({
          config: $("#config-select").value,
          config_hash: state.currentConfig.config_hash,
          output: $("#output-name").value,
          workers: 1,
          force: $("#force-run").checked,
        }),
      });
      await pollJob(job.id);
    } catch (error) {
      button.disabled = !state.currentConfig?.valid;
      setMessage("#run-message", t("run.notStarted", { error: error.message }), true);
    }
  }

  async function pollJob(jobId) {
    if (state.pollingJobId === jobId) return;
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    state.pollingJobId = jobId;
    $("#run-button").disabled = true;
    let ticking = false;
    const tick = async () => {
      if (ticking || state.pollingJobId !== jobId) return false;
      ticking = true;
      try {
        const job = await api(`/api/jobs/${jobId}`);
        if (state.pollingJobId !== jobId) return false;
        state.jobs = [job, ...state.jobs.filter((item) => item.id !== job.id)];
        renderJobLine();
        if (["completed", "failed", "paused", "cancelled", "interrupted"].includes(job.status)) {
          if (state.pollTimer) clearInterval(state.pollTimer);
          state.pollTimer = null;
          state.pollingJobId = null;
          $("#run-button").disabled = !state.currentConfig?.valid;
          setMessage(
            "#run-message",
            job.status === "completed"
              ? t("run.complete", { output: job.output })
              : job.status === "failed" ? t("run.failed", { error: job.error })
              : `${STATUS_LABELS[state.language][job.status] || job.status} · ${state.language === "zh" ? "检查点保留，可在统一运行中心续跑。" : "Checkpoint preserved; resume from the run center."}`,
            job.status === "failed",
          );
          await refreshAll(job.status === "completed" ? job.result_name : null);
          return false;
        }
        return true;
      } catch (error) {
        if (state.pollingJobId !== jobId) return false;
        if (state.pollTimer) clearInterval(state.pollTimer);
        state.pollTimer = null;
        state.pollingJobId = null;
        setMessage("#run-message", error.message, true);
        $("#run-button").disabled = !state.currentConfig?.valid;
        return false;
      } finally {
        ticking = false;
      }
    };
    if (await tick()) state.pollTimer = setInterval(tick, 1000);
  }

  /* ── Gap spectrum ──────────────────────────────────── */

  function renderSpectrum(rows) {
    const container = $("#gap-spectrum");
    container.replaceChildren();
    const byFamily = new Map();
    rows.forEach((row) => {
      const algorithm = row.algorithm_id || row.algorithm;
      if (!GREEDY_IDS.has(algorithm)) return;
      const gap = row.mean_optimality_gap;
      // A missing optimum arrives as null from the API; Number(null) is 0,
      // which would drag every family average down instead of excluding the
      // row, so require a real number rather than a coercible one.
      if (typeof gap !== "number" || !Number.isFinite(gap)) return;
      const family = row.family || row.case;
      const current = byFamily.get(family);
      if (current) {
        current.total += gap;
        current.count += 1;
      } else byFamily.set(family, { familyName: family, total: gap, count: 1 });
    });
    const entries = [...byFamily.values()]
      .map((entry) => ({
        familyName: entry.familyName,
        gap: entry.total / entry.count,
      }))
      .sort((a, b) => b.gap - a.gap);
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "spectrum-empty";
      empty.textContent = t("gap.empty");
      container.append(empty);
      return;
    }
    const maxGap = Math.max(...entries.map((entry) => entry.gap), 0);
    entries.forEach((entry) => {
      const rowEl = document.createElement("div");
      rowEl.className = "spectrum-row";
      const label = document.createElement("span");
      label.className = "spectrum-case";
      label.textContent = friendlyLabel(entry.familyName, "case");
      const track = document.createElement("div");
      track.className = "spectrum-track";
      const bar = document.createElement("div");
      bar.className = "spectrum-bar";
      track.append(bar);
      const value = document.createElement("span");
      value.className = "spectrum-value";
      value.textContent = formatPercent(entry.gap);
      rowEl.append(label, track, value);
      container.append(rowEl);
      const width =
        maxGap > 0 ? `${Math.max((entry.gap / maxGap) * 100, 1.5)}%` : "0%";
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          bar.style.width = width;
        });
      });
    });
    const note = document.createElement("p");
    note.className = "spectrum-note";
    note.textContent = t("gap.note");
    container.append(note);
  }

  /* ── Gallery ───────────────────────────────────────── */

  function frameCaption(artifact) {
    const caption = document.createElement("figcaption");
    caption.className = "frame-caption";
    const title = document.createElement("strong");
    title.textContent =
      FRIENDLY_LABELS[state.language].artifact[artifact.name] ||
      friendlyLabel(artifact.name, "artifact");
    const filename = document.createElement("code");
    filename.textContent = artifact.name;
    caption.append(title, filename);
    return caption;
  }

  function summaryFrame(artifact, hero) {
    const frame = document.createElement("figure");
    frame.className = hero
      ? "frame frame-summary frame-hero"
      : "frame frame-summary";
    const description = document.createElement("div");
    description.className = "report-summary";
    description.textContent = t("report.loading");
    const language = document.createElement("p");
    language.className = "help-text";
    language.textContent = t("report.language");
    const button = document.createElement("button");
    button.className = "button button-secondary";
    button.textContent = t("report.open");
    button.addEventListener("click", () => openReport(artifact));
    frame.append(frameCaption(artifact), language, description, button);
    const resultRequest = state.resultRequestId;
    readReport(artifact).then((text) => {
      if (!frame.isConnected || resultRequest !== state.resultRequestId) return;
      const summary = window.MaxcoverReport.headline(text);
      if (summary) description.replaceChildren(window.MaxcoverReport.render(summary));
      else description.textContent = t("gallery.reportDescription");
    }).catch(() => {
      if (frame.isConnected && resultRequest === state.resultRequestId)
        description.textContent = t("report.failed");
    });
    return frame;
  }

  async function readReport(artifact) {
    const response = await fetch(artifact.url);
    if (!response.ok) throw new Error("Report unavailable");
    return response.text();
  }

  async function openReport(artifact) {
    const requestId = ++state.reportRequestId;
    const resultRequest = state.resultRequestId;
    const dialog = $("#report-dialog");
    $("#report-title").textContent = `${state.currentResult} · ${t("report.open")}`;
    $("#report-source").href = artifact.url;
    $("#report-content").textContent = t("report.loading");
    dialog.showModal();
    try {
      const text = await readReport(artifact);
      if (requestId !== state.reportRequestId || resultRequest !== state.resultRequestId || !dialog.open) return;
      $("#report-content").replaceChildren(window.MaxcoverReport.render(text));
      dialog.scrollTop = 0;
    } catch (_error) {
      if (requestId === state.reportRequestId && resultRequest === state.resultRequestId && dialog.open)
        $("#report-content").textContent = t("report.failed");
    }
  }

  let lightbox = null;
  let lightboxTrigger = null;

  function ensureLightbox() {
    if (lightbox) return;
    lightbox = document.createElement("div");
    lightbox.className = "lightbox";
    lightbox.hidden = true;
    lightbox.setAttribute("role", "dialog");
    lightbox.setAttribute("aria-modal", "true");
    const panel = document.createElement("div");
    panel.className = "lightbox-panel";
    const close = document.createElement("button");
    close.className = "lightbox-close";
    close.type = "button";
    close.textContent = "×";
    close.addEventListener("click", closeLightbox);
    const image = document.createElement("img");
    image.className = "lightbox-image";
    image.alt = "";
    const caption = document.createElement("div");
    caption.className = "lightbox-caption";
    const title = document.createElement("strong");
    const filename = document.createElement("code");
    const hint = document.createElement("span");
    hint.className = "lightbox-hint";
    caption.append(title, filename, hint);
    panel.append(close, image, caption);
    lightbox.append(panel);
    lightbox.addEventListener("click", (event) => {
      if (event.target === lightbox) closeLightbox();
    });
    document.body.append(lightbox);
  }

  function openLightbox(artifact, trigger) {
    ensureLightbox();
    const title =
      FRIENDLY_LABELS[state.language].artifact[artifact.name] ||
      friendlyLabel(artifact.name, "artifact");
    lightbox.querySelector(".lightbox-image").src = artifact.url;
    lightbox.querySelector(".lightbox-image").alt = title;
    lightbox.querySelector(".lightbox-caption strong").textContent = title;
    lightbox.querySelector(".lightbox-caption code").textContent =
      artifact.name;
    lightbox.querySelector(".lightbox-hint").textContent =
      t("lightbox.escHint");
    lightbox
      .querySelector(".lightbox-close")
      .setAttribute("aria-label", t("lightbox.close"));
    lightboxTrigger = trigger;
    lightbox.hidden = false;
    document.body.classList.add("lightbox-open");
    lightbox.querySelector(".lightbox-close").focus();
  }

  function closeLightbox() {
    if (!lightbox || lightbox.hidden) return;
    lightbox.hidden = true;
    document.body.classList.remove("lightbox-open");
    if (lightboxTrigger) {
      lightboxTrigger.focus();
      lightboxTrigger = null;
    }
  }

  function chartFrame(artifact, hero) {
    const frame = document.createElement("figure");
    frame.className = hero
      ? "frame frame-chart frame-hero"
      : "frame frame-chart";
    frame.tabIndex = 0;
    frame.setAttribute("role", "button");
    frame.setAttribute("aria-haspopup", "dialog");
    frame.setAttribute(
      "aria-label",
      `${friendlyLabel(artifact.name, "artifact")} · ${t("gallery.zoomHint")}`,
    );
    frame.addEventListener("click", () => openLightbox(artifact, frame));
    frame.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openLightbox(artifact, frame);
      }
    });
    const mat = document.createElement("div");
    mat.className = "frame-mat";
    const image = document.createElement("img");
    image.src = artifact.url;
    image.alt = `${friendlyLabel(artifact.name, "artifact")} (${artifact.name})`;
    image.loading = "lazy";
    const hint = document.createElement("span");
    hint.className = "frame-zoom-hint";
    hint.textContent = t("gallery.zoomHint");
    mat.append(image, hint);
    frame.append(frameCaption(artifact), mat);
    return frame;
  }

  function renderGallery(data) {
    const grid = $("#gallery-grid");
    grid.replaceChildren();
    const artifacts = data.artifacts || [];
    if (!artifacts.length) {
      const empty = document.createElement("div");
      empty.className = "frame frame-empty";
      empty.textContent = t("gallery.empty");
      grid.append(empty);
      return;
    }
    const docs = artifacts.filter(
      (artifact) => !artifact.name.endsWith(".svg"),
    );
    const charts = artifacts.filter((artifact) =>
      artifact.name.endsWith(".svg"),
    );
    docs.forEach((artifact, index) =>
      grid.append(summaryFrame(artifact, index === 0)),
    );
    charts.forEach((artifact, index) =>
      grid.append(chartFrame(artifact, !docs.length && index === 0)),
    );
  }

  function renderSummary(rows) {
    const body = $("#summary-table tbody");
    body.replaceChildren();
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      const cells = [
        { value: row.case, kind: "case" },
        { value: row.algorithm_id || row.algorithm, kind: "algorithm" },
        { value: formatNumber(row.runs, 0) },
        { value: formatNumber(row.mean_coverage) },
        { value: formatPercent(row.mean_optimality_gap) },
        { value: `${formatNumber(row.mean_runtime_seconds, 5)} s` },
        { value: formatNumber(row.timeouts, 0) },
      ];
      cells.forEach((cell) => {
        const td = document.createElement("td");
        if (cell.kind) td.append(annotatedNode(cell.value, cell.kind));
        else td.textContent = cell.value;
        tr.append(td);
      });
      body.append(tr);
    });
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.textContent = t("results.noSummary");
      tr.append(td);
      body.append(tr);
    }
  }

  function renderResultMeta(name) {
    const info = state.results.find((item) => item.name === name);
    $("#result-meta").textContent = info
      ? `${t("results.updated", { time: formatDate(info.modified_at) })} · ${t("results.failureCount", { count: formatNumber(info.failure_count, 0) })}`
      : "";
  }

  function clearResult() {
    state.currentResult = null;
    ++state.reportRequestId;
    $("#report-dialog").close();
    $("#report-content").replaceChildren();
    closeLightbox();
    $("#spectrum-source").textContent = t("gap.noSource");
    renderSpectrum([]);
    renderGallery({ artifacts: [] });
    renderSummary([]);
    renderResultMeta("");
    resetReplay();
    renderReplays();
  }

  async function loadResult(name, notice = null) {
    const requestId = ++state.resultRequestId;
    state.resultNotice = notice;
    clearResult();
    setMessage("#result-message", name ? t("results.loading", { name }) : "");
    setMessage("#result-notice", notice ? t("results.fallback", { name: notice }) : "");
    if (!name) return false;
    try {
      const data = await api(`/api/result?name=${encodeURIComponent(name)}`);
      if (
        requestId !== state.resultRequestId ||
        $("#result-select").value !== name
      )
        return null;
      state.currentResult = name;
      rememberResult(name);
      setMessage("#result-message", data.incomplete
        ? (state.language === "zh" ? "该目录最近一次任务尚未完成。当前只显示已有检查点；报告和图表将在完成后更新。" : "The latest attempt is incomplete. Only the saved checkpoint is available; reports and charts update after completion.")
        : "");
      $("#spectrum-source").textContent = name;
      renderSummary(data.summary);
      renderSpectrum(data.summary);
      renderGallery(data);
      renderResultMeta(name);
      renderReplays();
      return true;
    } catch (error) {
      if (
        requestId !== state.resultRequestId ||
        $("#result-select").value !== name
      )
        return null;
      setMessage("#result-message", t("results.failed", { name }), true);
      return false;
    }
  }

  /* ── Replay ────────────────────────────────────────── */

  function renderReplays() {
    const others = $("#replay-scope").value === "others";
    const visible = state.replays.filter((item) => others
      ? item.result !== state.currentResult : item.result === state.currentResult);
    const selectedReplayPath = state.currentReplay;
    setSelect(
      "#replay-select",
      visible.map((item) => ({
        label: `${item.result} · ${friendlyLabel(item.algorithm_id || item.algorithm, "algorithm")} · ${item.run_id || item.path}`,
        value: item.path,
      })),
      t("replay.noFiles"),
    );
    if (visible.length) {
      state.currentReplay = visible.some(
        (item) => item.path === selectedReplayPath,
      )
        ? selectedReplayPath
        : visible[0].path;
      $("#replay-select").value = state.currentReplay;
    } else state.currentReplay = null;
    $("#replay-button").disabled = !visible.length || state.replayBusy;
    $("#replay-algorithm").disabled = !visible.length || state.replayBusy;
    if ($("#replay-output").classList.contains("empty-state"))
      $("#replay-output").textContent = t(visible.length ? "replay.outputEmpty" : "replay.emptyHelp");
  }

  function resetReplay() {
    ++state.replayRequestId;
    state.currentReplay = null;
    $("#replay-output").className = "replay-output empty-state";
    $("#replay-output").textContent = t("replay.outputEmpty");
    setMessage("#replay-message", "");
  }

  function renderReplayOutput(data) {
    const output = $("#replay-output");
    output.className = "replay-output replay-result";
    const status = document.createElement("div");
    status.className = `result-status ${data.matches === false ? "mismatch" : ""}`;
    status.textContent =
      data.matches === true
        ? t("replay.match")
        : data.matches === false
          ? t("replay.mismatch")
          : t("replay.noCompare");
    const dl = document.createElement("dl");
    dl.className = "replay-dl";
    [
      [t("replay.algorithm"), data.algorithm],
      [t("replay.status"), data.status],
      [t("replay.coverage"), formatNumber(data.coverage, 0)],
      [t("replay.selected"), (data.selected || []).join(", ") || "—"],
    ].forEach(([label, value]) => {
      const box = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      box.append(dt, dd);
      dl.append(box);
    });
    output.replaceChildren(status, dl);
  }

  async function replay() {
    const instance = $("#replay-select").value;
    if (!instance || state.replayBusy) return;
    resetReplay();
    state.currentReplay = instance;
    const requestId = state.replayRequestId;
    state.replayBusy = true;
    renderReplays();
    setMessage("#replay-message", t("replay.running"));
    try {
      const algorithm = $("#replay-algorithm").value;
      const data = await api("/api/replay", {
        method: "POST",
        body: JSON.stringify({ instance, ...(algorithm ? { algorithm } : {}) }),
      });
      if (requestId !== state.replayRequestId) return;
      setMessage("#replay-message", "");
      renderReplayOutput(data);
    } catch (error) {
      if (requestId === state.replayRequestId)
        setMessage("#replay-message", t("replay.failed", { error: error.message }), true);
    } finally {
      state.replayBusy = false;
      renderReplays();
    }
  }

  /* ── Refresh ───────────────────────────────────────── */

  async function refreshAll(preferredResult = null) {
    const refreshId = ++state.refreshRequestId;
    const selectionAtStart = state.resultSelectionId;
    try {
      const [configs, algorithms, results, jobs, replays] = await Promise.all([
        api("/api/configs"),
        api("/api/algorithms"),
        api("/api/results"),
        api("/api/jobs"),
        api("/api/replay-files"),
      ]);
      if (refreshId !== state.refreshRequestId) return;
      state.configs = configs.configs;
      state.algorithms = algorithms.algorithms;
      state.results = [...results.results].sort((a, b) =>
        b.modified_at.localeCompare(a.modified_at) || a.name.localeCompare(b.name));
      $("#use-quick").disabled = !state.configs.some((item) => item.path === "quick.json");
      $$('[data-scenario]').forEach((button) => {
        button.disabled = !state.configs.some((item) => item.path === button.dataset.scenario);
      });
      $("#view-results").disabled = !state.results.length;
      state.jobs = jobs.jobs;
      state.replays = replays.replays;
      $("#api-status").textContent = t("topbar.connected");
      $("#api-status").style.color = "var(--green)";
      const selectedConfigPath =
        state.currentConfig?.path || $("#config-select").value;
      setSelect(
        "#config-select",
        [...state.configs]
          .sort((a, b) => Number(b.path === "quick.json") - Number(a.path === "quick.json"))
          .map((item) => ({ label: item.path === "quick.json" ? t("config.quickLabel") : item.name, value: item.path })),
        t("config.noConfigs"),
      );
      setSelect(
        "#replay-algorithm",
        state.algorithms.map((item) => ({
          label: `${friendlyLabel(item.name, "algorithm")} · ${item.name}`,
          value: item.name,
        })),
        t("replay.recordedAlgorithm"),
        true,
      );
      renderReplays();
      renderJobLine();
      const activeJob = state.jobs.find((job) =>
        ["queued", "running"].includes(job.status),
      );
      if (activeJob && !state.pollingJobId) pollJob(activeJob.id);
      if (state.configs.length) {
        const defaultConfig =
          state.configs.find((item) => item.path === "quick.json") ||
          state.configs[0];
        const nextConfigPath = state.configs.some(
          (item) => item.path === selectedConfigPath,
        )
          ? selectedConfigPath
          : defaultConfig.path;
        $("#config-select").value = nextConfigPath;
        // Revalidate even when the path did not change: a corrected invalid
        // preflight or a hash conflict stays stale otherwise, and with a
        // single configuration there is no change event to trigger a reload.
        await loadConfig(nextConfigPath);
      } else await loadConfig("");
      if (refreshId !== state.refreshRequestId) return;
      // Read the latest user selection after awaits, never the one at refresh start.
      const preferred = (selectionAtStart === state.resultSelectionId
        && typeof preferredResult === "string" && preferredResult)
        || $("#result-select").value || state.currentResult || savedResult();
      setSelect(
        "#result-select",
        state.results.map((item) => ({ label: item.name, value: item.name })),
        t("results.noResult"),
      );
      const select = $("#result-select");
      const candidates = state.results.map((item) => item.name);
      if (candidates.includes(preferred)) {
        candidates.splice(candidates.indexOf(preferred), 1);
        candidates.unshift(preferred);
      }
      let notice = preferred && !candidates.includes(preferred) ? preferred : null;
      if (!candidates.length) await loadResult("", notice);
      for (const name of candidates) {
        if (refreshId !== state.refreshRequestId) return;
        select.value = name;
        const loaded = await loadResult(name, notice);
        if (loaded !== false) break; // Success or superseded by a user action.
        notice ||= name;
      }
    } catch (error) {
      if (refreshId !== state.refreshRequestId) return;
      $("#api-status").textContent =
        `${t("topbar.offline")} · ${error.message}`;
      $("#api-status").style.color = "var(--red)";
    }
  }

  /* ── Wiring ────────────────────────────────────────── */

  $$('[data-scenario]').forEach((button) => button.addEventListener("click", () => {
    $("#config-select").value = button.dataset.scenario;
    $("#force-run").checked = false;
    loadConfig(button.dataset.scenario);
  }));

  $("#use-quick").addEventListener("click", async () => {
    if (!state.configs.some((item) => item.path === "quick.json")) return;
    $("#config-select").value = "quick.json";
    state.outputEdited = false;
    $("#force-run").checked = false;
    await loadConfig("quick.json");
    $("#experiment-entry").scrollIntoView({ block: "start" });
    $("#run-button").focus({ preventScroll: true });
  });
  $("#view-results").addEventListener("click", () => {
    $("#results-section").scrollIntoView({ block: "start" });
    $("#result-select").focus({ preventScroll: true });
  });

  $$(".result-nav a").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    const target = $(link.getAttribute("href"));
    target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
  }));

  $("#config-select").addEventListener("change", (event) =>
    loadConfig(event.target.value),
  );
  $("#run-button").addEventListener("click", runBenchmark);
  $("#output-name").addEventListener("input", () => {
    state.outputEdited = true;
    validateOutput();
  });
  $("#result-select").addEventListener("change", (event) => {
    ++state.resultSelectionId;
    loadResult(event.target.value);
  });
  $("#refresh-results").addEventListener("click", refreshAll);
  $("#replay-select").addEventListener("change", (event) => {
    resetReplay();
    state.currentReplay = event.target.value || null;
  });
  $("#replay-scope").addEventListener("change", () => {
    resetReplay();
    renderReplays();
  });
  $("#replay-algorithm").addEventListener("change", () => {
    const selected = state.currentReplay;
    resetReplay();
    state.currentReplay = selected;
  });
  $("#replay-button").addEventListener("click", replay);
  $("#report-close").addEventListener("click", () => $("#report-dialog").close());
  $("#report-dialog").addEventListener("close", () => { ++state.reportRequestId; });
  $$("[data-language]").forEach((button) =>
    button.addEventListener("click", () => {
      applyLanguage(button.dataset.language);
      refreshAll();
    }),
  );
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && lightbox && !lightbox.hidden) closeLightbox();
  });

  state.language = initialLanguage();
  applyLanguage(state.language);
  refreshAll();
})();
