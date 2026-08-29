(() => {
  "use strict";

  const state = { configs: [], algorithms: [], results: [], jobs: [], replays: [], currentConfig: null, currentResult: null, currentStage: "select", language: "zh", pollTimer: null, transitionTimer: null };
  const STAGE_ORDER = ["select", "preflight", "execute", "results", "replay"];
  const STATUS_LABELS = {
    zh: { queued: "排队中", running: "运行中", completed: "已完成", failed: "失败" },
    en: { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed" }
  };
  const FRIENDLY_LABELS = {
    zh: {
      algorithm: { brute_force: "穷举搜索", branch_and_bound: "分支定界", branch_and_bound_enhanced: "增强分支定界", bnb_baseline: "分支定界基线", bnb_enhanced: "增强分支定界", bnb_reference: "分支定界参考", cp_sat_oracle: "CP-SAT 精确求解", greedy: "贪心算法", greedy_baseline: "贪心算法基线", lazy_greedy: "惰性贪心", local_search: "局部搜索", multi_start_local_search: "多起点局部搜索", randomized_greedy: "随机贪心" },
      case: { uniform_sparse: "均匀分布 · 稀疏", uniform_dense: "均匀分布 · 稠密", overlap_core: "高重叠 · 核心", overlap_moderate: "高重叠 · 中等", overlap_extreme: "高重叠 · 极端", four_clusters: "四簇聚类", eight_clusters: "八簇聚类", greedy_trap: "贪心陷阱", greedy_trap_small: "贪心陷阱 · 小型", greedy_trap_large: "贪心陷阱 · 大型" },
      artifact: { "results_summary.md": "结果说明文档", "gap_by_family.svg": "按案例族查看覆盖差距", "runtime_by_algorithm.svg": "按算法查看运行耗时", "gap_by_case.svg": "按案例查看覆盖差距", "gap_vs_structural_parameter.svg": "差距与结构参数关系", "local_search_recovery.svg": "局部搜索恢复情况", "quality_runtime_pareto.svg": "质量与耗时权衡", "runtime_scaling.svg": "运行耗时扩展", "node_scaling.svg": "搜索节点扩展", "timeout_by_case.svg": "按案例查看超时" }
    },
    en: {
      algorithm: { brute_force: "Brute Force", branch_and_bound: "Branch and Bound", branch_and_bound_enhanced: "Enhanced Branch and Bound", bnb_baseline: "Branch and Bound Baseline", bnb_enhanced: "Enhanced Branch and Bound", bnb_reference: "Branch and Bound Reference", cp_sat_oracle: "CP-SAT Exact Solver", greedy: "Greedy", greedy_baseline: "Greedy Baseline", lazy_greedy: "Lazy Greedy", local_search: "Local Search", multi_start_local_search: "Multi-start Local Search", randomized_greedy: "Randomized Greedy" },
      case: { uniform_sparse: "Uniform · Sparse", uniform_dense: "Uniform · Dense", overlap_core: "High Overlap · Core", overlap_moderate: "High Overlap · Moderate", overlap_extreme: "High Overlap · Extreme", four_clusters: "Four Clusters", eight_clusters: "Eight Clusters", greedy_trap: "Greedy Trap", greedy_trap_small: "Greedy Trap · Small", greedy_trap_large: "Greedy Trap · Large" },
      artifact: { "results_summary.md": "Results summary", "gap_by_family.svg": "Coverage gap by family", "runtime_by_algorithm.svg": "Runtime by algorithm", "gap_by_case.svg": "Coverage gap by case", "gap_vs_structural_parameter.svg": "Gap vs. structural parameter", "local_search_recovery.svg": "Local-search recovery", "quality_runtime_pareto.svg": "Quality/runtime trade-off", "runtime_scaling.svg": "Runtime scaling", "node_scaling.svg": "Search-node scaling", "timeout_by_case.svg": "Timeouts by case" }
    }
  };
  const I18N = {
    zh: {
      "brand.title": "本地实验台", "topbar.localOnly": "仅限本机", "nav.overview": "总览", "nav.experiment": "实验工作台", "nav.results": "结果浏览", "nav.replay": "失败案例回放", "sidebar.note": "前端直接连接本地实验引擎。配置、运行和输出都保留在当前工作区。", "workflow.progress": "阶段进度", "workflow.config": "配置", "workflow.configHint": "选择实验", "workflow.preflight": "校验", "workflow.preflightHint": "生成计划", "workflow.execute": "执行", "workflow.executeHint": "运行 benchmark", "workflow.results": "结果", "workflow.resultsHint": "检查产物", "workflow.replay": "回放", "workflow.replayHint": "重现失败",
      "transition.startTitle": "准备开始", "transition.startDetail": "选择一个配置进入实验阶段。", "overview.title": "实验控制台", "overview.lede": "从一个小型预设开始，按步骤完成配置、运行、检查和回放。", "actions.newExperiment": "新建实验", "metrics.configs": "可用配置", "metrics.configsFoot": "来自 configs/", "metrics.results": "本地结果集", "metrics.resultsFoot": "来自 results/", "metrics.job": "当前任务", "metrics.jobFoot": "等待启动", "overview.recentJobs": "最近任务", "actions.openWorkbench": "查看工作台 →", "overview.noJobs": "还没有 dashboard 任务。", "overview.startTitle": "第一次使用？从 quick 开始", "overview.recommended": "推荐", "overview.startCopy": "quick.json 是适合第一次操作的预设。你可以先查看它会运行什么，再决定是否启动。", "overview.step1": "选择 quick.json", "overview.step1Hint": "载入并校验配置", "overview.step2": "确认执行计划", "overview.step2Hint": "先看实例和运行数量", "overview.step3": "启动并查看结果", "overview.step3Hint": "完成后可继续 replay", "actions.startQuick": "用 quick.json 开始", "topbar.connected": "引擎已连接", "topbar.offline": "离线",
      "experiment.title": "实验工作台", "experiment.lede": "先选一个配置。系统会自动校验并展示计划，确认后再启动或恢复本地 benchmark。", "experiment.tipTitle": "推荐上手路径", "experiment.tipCopy": "先用 quick.json 熟悉流程；大规模配置可以在确认计划后再运行。", "actions.chooseQuick": "选择 quick.json →", "experiment.configTitle": "实验配置", "status.notSelected": "未选择", "fields.configFile": "配置文件", "experiment.configHelp": "配置文件只读；选择后会自动显示可执行的实验计划。", "experiment.sourcePreview": "SOURCE PREVIEW", "config.noSource": "无法读取配置源文件。", "config.noConfigs": "暂无可用 JSON 配置", "config.invalidDetail": "请检查配置文件后重试。", "config.quickMissingTitle": "找不到 quick.json", "config.quickMissingDetail": "请从配置列表中选择一个可用的 JSON 文件。", "annotations.fieldsTitle": "字段说明", "annotations.rawHint": "原始字段名保留在括号内", "glossary.universe": "元素总数", "glossary.universeHint": "问题中可被覆盖的元素数量", "glossary.setCount": "候选集合数", "glossary.setCountHint": "可供算法选择的集合数量", "glossary.budget": "选择预算", "glossary.budgetHint": "最多可以选择的集合数", "glossary.repetitions": "重复次数", "glossary.repetitionsHint": "同一案例使用不同实例种子运行的次数", "experiment.planTitle": "执行计划", "actions.revalidate": "重新校验", "experiment.planEmpty": "选择配置后，这里会显示实例、重复次数和预计运行数。", "plan.instances": "实例总数", "plan.repetitions": "每个实例重复", "plan.runs": "预计算法运行", "experiment.planHint": "运行数量 = 实例数 × 启用算法及其重复次数。这里仅做计划校验，不会启动算法。", "experiment.executeTitle": "启动本地运行", "status.resumable": "可恢复", "fields.outputName": "结果文件夹名称", "fields.outputPlaceholder": "例如 quick-dashboard", "fields.outputHelp": "结果会写入 results/ 下。", "fields.workers": "并行 worker", "fields.workersHelp": "新手保持 1 即可。", "fields.forceRun": "清除后重跑", "actions.runBenchmark": "启动 benchmark", "run.nextLabel": "下一步", "run.selectFirst": "先选择并校验一个配置。", "run.planReady": "计划已确认，可以启动 benchmark。", "run.fixConfig": "请先修正配置，再继续后面的阶段。", "run.consoleEmpty": "任务状态会显示在这里。",
      "results.title": "结果浏览", "results.lede": "查看本机 results/ 中的运行汇总、报告图表和可回放案例。", "actions.refreshResults": "刷新结果列表", "results.selectLabel": "选择结果集", "results.empty": "运行完成后，结果集会出现在这里。你也可以先回到实验工作台启动 quick.json。", "actions.goWorkbench": "去实验工作台 →", "annotations.resultsTitle": "结果标注", "annotations.resultsHint": "中文含义为主，原始标识用于和 CSV / SVG 对照", "annotations.cases": "案例", "annotations.algorithms": "算法", "annotations.metrics": "指标", "results.noResult": "暂无结果", "results.summaryRecords": "汇总记录", "results.runRecords": "运行记录", "results.failureFiles": "失败案例文件", "results.failureFoot": "可继续 replay", "results.comparison": "算法对照", "results.reports": "生成的报告", "results.preview": "报告预览", "metrics.meanCoverage": "平均覆盖", "metrics.meanGap": "平均差距", "metrics.meanRuntime": "平均耗时", "metrics.timeouts": "超时", "table.case": "案例", "table.algorithm": "算法", "table.runs": "运行次数", "table.coverage": "平均覆盖", "table.gap": "平均差距", "table.runtime": "平均耗时", "table.timeouts": "超时",
      "replay.title": "失败案例回放", "replay.lede": "选择 results/ 下的序列化失败案例，用记录的算法重新运行并核对结果。", "replay.instanceTitle": "序列化失败案例", "replay.fileLabel": "失败案例文件", "replay.noFiles": "暂无失败案例文件", "replay.recordedAlgorithm": "使用记录算法", "replay.algorithmLabel": "替换算法（可选）", "replay.algorithmHelp": "留空会使用 artifact 中记录的算法；选择其他算法可做对照运行。", "actions.runReplay": "运行回放", "replay.outputTitle": "重现结果", "replay.outputEmpty": "运行后显示结果和匹配状态。", "footer": "Maximum Coverage · 本地 dashboard · CLI 仍可使用",
      "status.valid": "可运行", "status.invalid": "需修正", "status.idle": "空闲", "units.runs": "次运行", "results.rawRecords": "原始运行记录", "results.firstRows": "前 {count} 行", "results.updated": "更新时间 {time}", "results.noSummary": "没有汇总记录。", "results.noReports": "没有已生成的报告图表。", "results.noPreview": "没有 SVG 预览。", "replay.noCompare": "运行完成 · 没有记录可比较", "replay.match": "匹配 · 与记录结果一致", "replay.mismatch": "不匹配 · 与记录结果不同", "replay.algorithm": "算法", "replay.status": "状态", "replay.coverage": "覆盖", "replay.selected": "已选择",
      "view.experimentTitle": "进入实验工作台", "view.experimentReady": "配置已就绪，请确认执行计划。", "view.experimentNeedConfig": "先选择一个配置，系统会自动生成执行计划。", "view.resultsTitle": "进入结果浏览", "view.resultsDetail": "选择一个本地产物，查看汇总和报告图表。", "view.replayTitle": "进入失败案例回放", "view.replayDetail": "选择序列化实例，重现记录的算法结果。", "config.waitTitle": "等待实验配置", "config.waitDetail": "选择一个 JSON 配置开始校验。", "config.readingTitle": "正在读取配置", "config.planTitle": "执行计划已生成", "config.planDetail": "配置校验完成；确认计划后即可启动 benchmark。", "config.invalidTitle": "配置需要修正", "config.readErrorTitle": "配置读取失败", "workspace.connectedTitle": "工作区已连接", "workspace.connectedDetail": "选择配置开始一个新的实验流程。", "results.readingTitle": "正在读取结果", "results.loadedTitle": "结果已载入", "results.loadedDetail": "可以查看算法对照，也可以继续进入失败案例回放。", "results.failedTitle": "结果读取失败", "run.startingTitle": "正在启动 benchmark", "run.startingDetail": "任务已提交；页面会持续显示本地任务状态。", "run.queued": "任务已排队…", "run.startedTitle": "benchmark 已启动", "run.completedTitle": "benchmark 已完成", "run.completedDetail": "正在刷新本地产物并准备结果浏览。", "run.complete": "运行完成：results/{output}", "run.failed": "运行失败：{error}", "replay.runningTitle": "正在运行失败案例回放", "replay.running": "正在运行回放…", "replay.doneMessage": "回放完成。", "replay.doneTitle": "失败案例回放已完成", "replay.doneDetail": "结果已返回，请查看匹配状态。", "replay.doneMatch": "结果与记录一致。"
    },
    en: {
      "brand.title": "Local experiment lab", "topbar.localOnly": "LOCAL ONLY", "nav.overview": "Overview", "nav.experiment": "Experiment", "nav.results": "Results", "nav.replay": "Failure replay", "sidebar.note": "The frontend connects directly to the local experiment engine. Configurations, runs, and outputs stay in this workspace.", "workflow.progress": "Stage progress", "workflow.config": "Config", "workflow.configHint": "Choose experiment", "workflow.preflight": "Validate", "workflow.preflightHint": "Build plan", "workflow.execute": "Run", "workflow.executeHint": "Run benchmark", "workflow.results": "Results", "workflow.resultsHint": "Inspect outputs", "workflow.replay": "Replay", "workflow.replayHint": "Reproduce failure",
      "transition.startTitle": "Ready to begin", "transition.startDetail": "Choose a configuration to enter the experiment flow.", "overview.title": "Experiment console", "overview.lede": "Start with a small preset and move through configuration, execution, inspection, and replay.", "actions.newExperiment": "New experiment", "metrics.configs": "Available configs", "metrics.configsFoot": "From configs/", "metrics.results": "Local result sets", "metrics.resultsFoot": "From results/", "metrics.job": "Current job", "metrics.jobFoot": "Waiting to start", "overview.recentJobs": "Recent jobs", "actions.openWorkbench": "Open workbench →", "overview.noJobs": "No dashboard jobs yet.", "overview.startTitle": "New here? Start with quick", "overview.recommended": "Recommended", "overview.startCopy": "quick.json is the easiest preset for a first run. Review its plan before deciding whether to start.", "overview.step1": "Choose quick.json", "overview.step1Hint": "Load and validate the config", "overview.step2": "Review the execution plan", "overview.step2Hint": "Check instances and run count", "overview.step3": "Start and inspect results", "overview.step3Hint": "Replay failures when ready", "actions.startQuick": "Start with quick.json",
      "experiment.title": "Experiment workbench", "experiment.lede": "Choose a configuration first. The system validates it and shows the plan before you start or resume a local benchmark.", "experiment.tipTitle": "Recommended path", "experiment.tipCopy": "Use quick.json to learn the flow first; review larger configurations before running them.", "actions.chooseQuick": "Choose quick.json →", "experiment.configTitle": "Experiment configuration", "status.notSelected": "Not selected", "fields.configFile": "Configuration file", "experiment.configHelp": "Configuration files are read-only; selecting one loads its executable plan.", "experiment.sourcePreview": "SOURCE PREVIEW", "config.noSource": "Could not read the configuration source file.", "annotations.fieldsTitle": "Field guide", "annotations.rawHint": "Raw field names stay in parentheses", "glossary.universe": "Universe size", "glossary.universeHint": "Number of elements that can be covered", "glossary.setCount": "Candidate sets", "glossary.setCountHint": "Number of sets available to the algorithms", "glossary.budget": "Selection budget", "glossary.budgetHint": "Maximum number of sets that can be selected", "glossary.repetitions": "Repetitions", "glossary.repetitionsHint": "Runs per case using different instance seeds", "experiment.planTitle": "Execution plan", "actions.revalidate": "Validate again", "experiment.planEmpty": "Select a configuration to see instances, repetitions, and planned runs.", "plan.instances": "Total instances", "plan.repetitions": "Repetitions per instance", "plan.runs": "Planned algorithm runs", "experiment.planHint": "Run count = instances × enabled algorithms and their repetitions. This only validates the plan; it does not start algorithms.", "experiment.executeTitle": "Start local run", "status.resumable": "Resumable", "fields.outputName": "Result folder name", "fields.outputPlaceholder": "e.g. quick-dashboard", "fields.outputHelp": "Results are written under results/.", "fields.workers": "Parallel workers", "fields.workersHelp": "Keep this at 1 for a first run.", "fields.forceRun": "Clear and rerun", "actions.runBenchmark": "Start benchmark", "run.nextLabel": "Next step", "run.selectFirst": "Choose and validate a configuration first.", "run.planReady": "The plan is ready; you can start the benchmark.", "run.fixConfig": "Fix the configuration before continuing.", "run.consoleEmpty": "Job status will appear here.",
      "results.title": "Results browser", "results.lede": "Inspect local run summaries, report charts, and replayable cases under results/.", "actions.refreshResults": "Refresh result list", "results.selectLabel": "Choose result set", "results.empty": "Completed result sets appear here. You can also return to the workbench and start quick.json.", "actions.goWorkbench": "Go to workbench →", "annotations.resultsTitle": "Result labels", "annotations.resultsHint": "Readable names come first; raw IDs remain for CSV / SVG cross-reference", "annotations.cases": "Cases", "annotations.algorithms": "Algorithms", "annotations.metrics": "Metrics", "results.noResult": "No results", "results.summaryRecords": "Summary records", "results.runRecords": "Run records", "results.failureFiles": "Failure files", "results.failureFoot": "Available for replay", "results.comparison": "Algorithm comparison", "results.reports": "Generated reports", "results.preview": "Report preview", "metrics.meanCoverage": "Mean coverage", "metrics.meanGap": "Mean gap", "metrics.meanRuntime": "Mean runtime", "metrics.timeouts": "Timeouts", "table.case": "Case", "table.algorithm": "Algorithm", "table.runs": "Runs", "table.coverage": "Mean coverage", "table.gap": "Mean gap", "table.runtime": "Mean runtime", "table.timeouts": "Timeouts",
      "replay.title": "Failure replay", "replay.lede": "Choose a serialized failure case under results/ and rerun it with its recorded algorithm.", "replay.instanceTitle": "Serialized failure case", "replay.fileLabel": "Failure case file", "replay.noFiles": "No failure files", "replay.recordedAlgorithm": "Use recorded algorithm", "replay.algorithmLabel": "Replacement algorithm (optional)", "replay.algorithmHelp": "Leave this empty to use the recorded algorithm; choose another for a comparison run.", "actions.runReplay": "Run replay", "replay.outputTitle": "Replay result", "replay.outputEmpty": "The result and match status will appear here.", "footer": "Maximum Coverage · local dashboard · CLI remains available",
      "status.valid": "Ready", "status.invalid": "Needs fix", "status.idle": "Idle", "units.runs": "runs", "results.rawRecords": "Raw run records", "results.firstRows": "First {count} rows", "results.updated": "Updated {time}", "results.noSummary": "No summary records.", "results.noReports": "No generated report charts.", "results.noPreview": "No SVG previews.", "replay.noCompare": "Run complete · nothing to compare", "replay.match": "Match · same as recorded result", "replay.mismatch": "Mismatch · different from recorded result", "replay.algorithm": "Algorithm", "replay.status": "Status", "replay.coverage": "Coverage", "replay.selected": "Selected",
      "view.experimentTitle": "Opening experiment workbench", "view.experimentReady": "Configuration is ready; review the execution plan.", "view.experimentNeedConfig": "Choose a configuration first; the system will build its plan.", "view.resultsTitle": "Opening results browser", "view.resultsDetail": "Choose a local result set to inspect summaries and report charts.", "view.replayTitle": "Opening failure replay", "view.replayDetail": "Choose a serialized instance to reproduce its recorded result.", "config.waitTitle": "Waiting for configuration", "config.waitDetail": "Choose a JSON configuration to begin validation.", "config.readingTitle": "Reading configuration", "config.planTitle": "Execution plan ready", "config.planDetail": "Configuration validated; review the plan before starting the benchmark.", "config.invalidTitle": "Configuration needs attention", "config.readErrorTitle": "Could not read configuration", "workspace.connectedTitle": "Workspace connected", "workspace.connectedDetail": "Choose a configuration to start an experiment flow.", "results.readingTitle": "Reading results", "results.loadedTitle": "Results loaded", "results.loadedDetail": "Review the algorithm comparison or continue to failure replay.", "results.failedTitle": "Could not read results", "run.startingTitle": "Starting benchmark", "run.startingDetail": "The job is submitted; this page will keep showing local status.", "run.queued": "Job queued…", "run.startedTitle": "Benchmark started", "run.completedTitle": "Benchmark completed", "run.completedDetail": "Refreshing local outputs and preparing the results view.", "run.complete": "Run complete: results/{output}", "run.failed": "Run failed: {error}", "replay.runningTitle": "Running failure replay", "replay.running": "Running replay…", "replay.doneMessage": "Replay complete.", "replay.doneTitle": "Failure replay complete", "replay.doneDetail": "The result is back; review its match status.", "replay.doneMatch": "The result matches the recorded result."
    }
  };
  Object.assign(I18N.zh, {
    "document.title": "Maximum Coverage · 本地实验台", "topbar.connecting": "连接中…", "topbar.language": "语言", "nav.ariaLabel": "主导航", "workflow.ariaLabel": "实验流程", "kickers.overview": "工作区 / 总览", "kickers.recent": "最近活动", "kickers.startHere": "从这里开始", "kickers.experiment": "工作区 / 实验", "kickers.select": "01 · 选择", "kickers.preflight": "02 · 校验", "kickers.execute": "03 · 执行", "kickers.results": "工作区 / 结果", "kickers.summary": "汇总", "kickers.reports": "报告", "kickers.visualCheck": "可视化检查", "kickers.replay": "工作区 / 回放", "kickers.selectInstance": "选择实例", "kickers.output": "输出",
    "config.noSource": "无法读取配置源文件。",
    "config.noConfigs": "暂无可用 JSON 配置",
    "config.invalidDetail": "请检查配置文件后重试。",
    "config.quickMissingTitle": "找不到 quick.json",
    "config.quickMissingDetail": "请从配置列表中选择一个可用的 JSON 文件。",
    "run.inProgress": "任务运行中，请等待完成后进入结果浏览。", "actions.openWorkbench": "查看工作台"
  });
  Object.assign(I18N.en, {
    "document.title": "Maximum Coverage · Local experiment lab", "topbar.connecting": "Connecting…", "topbar.connected": "Engine connected", "topbar.offline": "Offline", "topbar.language": "Language", "nav.ariaLabel": "Primary navigation", "workflow.ariaLabel": "Experiment workflow", "kickers.overview": "WORKSPACE / OVERVIEW", "kickers.recent": "RECENT ACTIVITY", "kickers.startHere": "START HERE", "kickers.experiment": "WORKSPACE / EXPERIMENT", "kickers.select": "01 · SELECT", "kickers.preflight": "02 · PREFLIGHT", "kickers.execute": "03 · EXECUTE", "kickers.results": "WORKSPACE / RESULTS", "kickers.summary": "SUMMARY", "kickers.reports": "REPORTS", "kickers.visualCheck": "VISUAL CHECK", "kickers.replay": "WORKSPACE / REPLAY", "kickers.selectInstance": "SELECT INSTANCE", "kickers.output": "OUTPUT",
    "config.noSource": "Could not read the configuration source file.",
    "config.noConfigs": "No JSON configurations available",
    "config.invalidDetail": "Check the configuration file and try again.",
    "config.quickMissingTitle": "quick.json not found",
    "config.quickMissingDetail": "Choose another available JSON file from the list.",
    "run.inProgress": "The job is running; wait for completion before opening results.", "actions.openWorkbench": "Open workbench"
  });
  Object.assign(I18N.zh, {
    "experiment.sourcePreview": "配置预览",
    "overview.step3Hint": "完成后可继续回放",
    "results.failureFoot": "可继续回放",
    "replay.algorithmHelp": "留空会使用结果文件中记录的算法；选择其他算法可做对照运行。"
  });
  I18N.zh["workflow.kicker"] = "流程";
  I18N.en["workflow.kicker"] = "WORKFLOW";
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  async function api(path, options = {}) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function t(key, values = {}) {
    let template = I18N[state.language]?.[key] || I18N.en[key] || key;
    Object.entries(values).forEach(([name, value]) => { template = template.replaceAll(`{${name}}`, String(value)); });
    return template;
  }

  function initialLanguage() {
    try { return localStorage.getItem("maxcover-language") === "en" ? "en" : "zh"; }
    catch (_error) { return "zh"; }
  }

  function applyLanguage(language) {
    state.language = language === "en" ? "en" : "zh";
    try { localStorage.setItem("maxcover-language", state.language); }
    catch (_error) { /* Private browsing may disable localStorage. */ }
    document.documentElement.lang = state.language === "en" ? "en" : "zh-CN";
    $$("[data-language]").forEach((button) => button.classList.toggle("active", button.dataset.language === state.language));
    $$(`[data-i18n]`).forEach((element) => { element.textContent = t(element.dataset.i18n); });
    $$(`[data-i18n-placeholder]`).forEach((element) => { element.placeholder = t(element.dataset.i18nPlaceholder); });
    $$(`[data-i18n-aria]`).forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAria)); });
    if (state.currentConfig) renderConfig(state.currentConfig);
    renderJobs(); renderResults(); renderReplays();
    if (state.currentResult) loadResult(state.currentResult, false);
    const activeView = document.querySelector(".view.active")?.dataset.view;
    if (state.currentStage === "execute") announceTransition("execute", t("run.startingTitle"), t("run.inProgress"), 0);
    else if (activeView === "experiment") announceTransition(state.currentConfig?.valid ? "preflight" : "select", t("view.experimentTitle"), state.currentConfig?.valid ? t("view.experimentReady") : t("view.experimentNeedConfig"));
    else if (activeView === "results") announceTransition("results", t("view.resultsTitle"), t("view.resultsDetail"));
    else if (activeView === "replay") announceTransition("replay", t("view.replayTitle"), t("view.replayDetail"));
  }

  function friendlyLabel(value, kind) {
    if (!value) return "—";
    return FRIENDLY_LABELS[state.language]?.[kind]?.[value] || value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function annotatedNode(value, kind) {
    const wrapper = document.createElement("span"); wrapper.className = "annotated-value";
    const label = document.createElement("strong"); label.textContent = friendlyLabel(value, kind);
    const raw = document.createElement("code"); raw.textContent = value;
    wrapper.append(label, raw);
    return wrapper;
  }

  function appendAnnotationGroup(container, title, values, kind) {
    const uniqueValues = [...new Set(values.filter(Boolean))].sort();
    if (!uniqueValues.length) return;
    const group = document.createElement("div"); group.className = "annotation-group";
    const heading = document.createElement("strong"); heading.textContent = title;
    group.append(heading);
    uniqueValues.forEach((value) => {
      const item = document.createElement("span"); item.className = "annotation-item";
      item.append(annotatedNode(value, kind)); group.append(item);
    });
    container.append(group);
  }

  function updateStage(stage) {
    if (!STAGE_ORDER.includes(stage)) return;
    state.currentStage = stage;
    const stageIndex = STAGE_ORDER.indexOf(stage);
    $$(".workflow-step").forEach((step) => {
      const stepIndex = STAGE_ORDER.indexOf(step.dataset.stage);
      step.classList.toggle("current", stepIndex === stageIndex);
      step.classList.toggle("done", stepIndex < stageIndex);
    });
  }

  function announceTransition(stage, title, detail, duration = 5200) {
    updateStage(stage);
    const banner = $("#transition-banner");
    $("#transition-title").textContent = title;
    $("#transition-detail").textContent = detail;
    banner.classList.remove("hidden");
    if (state.transitionTimer) clearTimeout(state.transitionTimer);
    if (duration > 0) state.transitionTimer = setTimeout(() => banner.classList.add("hidden"), duration);
  }

  function showView(name, announce = true) {
    $$(".view").forEach((view) => view.classList.toggle("active", view.dataset.view === name));
    $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.viewTarget === name));
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (!announce) return;
    if (name === "experiment") announceTransition(state.currentConfig?.valid ? "preflight" : "select", t("view.experimentTitle"), state.currentConfig?.valid ? t("view.experimentReady") : t("view.experimentNeedConfig"));
    if (name === "results") announceTransition("results", t("view.resultsTitle"), t("view.resultsDetail"));
    if (name === "replay") announceTransition("replay", t("view.replayTitle"), t("view.replayDetail"));
  }

  function setMessage(selector, message, error = false) {
    const element = $(selector);
    element.textContent = message;
    element.classList.toggle("hidden", !message);
    element.classList.toggle("error", error);
  }

  function setSelect(selector, options, emptyLabel) {
    const select = $(selector);
    select.replaceChildren();
    if (!options.length) {
      select.append(new Option(emptyLabel, ""));
      select.disabled = true;
      return;
    }
    select.disabled = false;
    options.forEach((option) => select.append(new Option(option.label, option.value)));
  }

  function formatNumber(value, digits = 4) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return number.toLocaleString(state.language === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: digits });
  }

  function formatPercent(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : String(value);
  }

  function renderJobs() {
    const jobs = state.jobs;
    $("#metric-job").textContent = jobs[0] ? (STATUS_LABELS[state.language][jobs[0].status] || jobs[0].status) : t("status.idle");
    $("#metric-job-foot").textContent = jobs[0] ? `${jobs[0].config} → ${jobs[0].output}` : t("metrics.jobFoot");
    const list = $("#recent-jobs");
    if (!jobs.length) { list.className = "activity-list empty-state"; list.textContent = t("overview.noJobs"); return; }
    list.className = "activity-list";
    list.replaceChildren();
    jobs.slice(0, 6).forEach((job) => {
      const item = document.createElement("div"); item.className = "activity-item";
      const dot = document.createElement("span"); dot.className = `activity-dot ${job.status}`;
      const title = document.createElement("div"); title.className = "activity-title";
      const strong = document.createElement("strong"); strong.textContent = job.config;
      title.append(strong, `${job.output} · ${STATUS_LABELS[state.language][job.status] || job.status}`);
      const time = document.createElement("span"); time.className = "activity-time"; time.textContent = job.finished_at || job.started_at || job.created_at;
      item.append(dot, title, time); list.append(item);
    });
  }

  function renderConfig(configInfo) {
    state.currentConfig = configInfo;
    const chip = $("#config-validity");
    const source = $("#config-source");
    source.textContent = configInfo.source ? JSON.stringify(configInfo.source, null, 2) : t("config.noSource");
    chip.textContent = configInfo.valid ? t("status.valid") : t("status.invalid");
    chip.classList.toggle("invalid", !configInfo.valid);
    setMessage("#config-error", configInfo.valid ? "" : (configInfo.error || "配置无效。"), true);
    $("#plan-empty").classList.toggle("hidden", configInfo.valid);
    $("#plan-content").classList.toggle("hidden", !configInfo.valid);
    $("#run-button").disabled = !configInfo.valid;
    $("#run-next-step").textContent = configInfo.valid ? t("run.planReady") : t("run.fixConfig");
    if (!configInfo.valid) return;
    const plan = configInfo.plan;
    $("#plan-name").textContent = plan.name;
    $("#plan-instances").textContent = formatNumber(plan.instance_count, 0);
    $("#plan-repetitions").textContent = formatNumber(plan.repetitions, 0);
    $("#plan-runs").textContent = formatNumber(plan.algorithm_run_count, 0);
    $("#algorithm-plan").replaceChildren(...plan.runs_by_algorithm.map((entry) => {
      const row = document.createElement("div"); row.className = "algorithm-line";
      const name = annotatedNode(entry.algorithm, "algorithm");
      const count = document.createElement("span"); count.textContent = `${formatNumber(entry.runs, 0)} ${t("units.runs")}`;
      row.append(name, count); return row;
    }));
    $("#case-plan").replaceChildren(...plan.case_ids.map((name) => { const tag = document.createElement("span"); tag.className = "case-tag"; tag.append(annotatedNode(name, "case")); return tag; }));
    const output = $("#output-name"); if (!output.value) output.value = configInfo.path.replace(/\.json$/i, "");
  }

  async function loadConfig(path) {
    if (!path) { renderConfig({ valid: false, source: null }); announceTransition("select", t("config.waitTitle"), t("config.waitDetail"), 0); return; }
    announceTransition("select", t("config.readingTitle"), path);
    try {
      const configInfo = await api(`/api/config?path=${encodeURIComponent(path)}`);
      renderConfig(configInfo);
      if (configInfo.valid) announceTransition("preflight", t("config.planTitle"), t("config.planDetail"), 6500);
      else announceTransition("select", t("config.invalidTitle"), configInfo.error || t("config.invalidDetail"), 0);
    } catch (error) { renderConfig({ valid: false, error: error.message }); announceTransition("select", t("config.readErrorTitle"), error.message, 0); }
  }

  async function chooseQuickConfig() {
    const quick = state.configs.find((item) => item.path === "quick.json");
    if (!quick) { announceTransition("select", t("config.quickMissingTitle"), t("config.quickMissingDetail"), 0); return; }
    showView("experiment", false);
    $("#config-select").value = quick.path;
    await loadConfig(quick.path);
  }

  function renderResults() {
    $("#metric-configs").textContent = formatNumber(state.configs.length, 0);
    $("#metric-results").textContent = formatNumber(state.results.length, 0);
    setSelect("#result-select", state.results.map((item) => ({ label: item.name, value: item.name })), t("results.noResult"));
    const select = $("#result-select");
    if (state.results.length) { select.value = state.currentResult && state.results.some((item) => item.name === state.currentResult) ? state.currentResult : state.results[0].name; loadResult(select.value, false); }
  }

  function renderSummary(rows) {
    const body = $("#summary-table tbody"); body.replaceChildren();
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      const cells = [
        { value: row.case, kind: "case" },
        { value: row.algorithm_id || row.algorithm, kind: "algorithm" },
        { value: formatNumber(row.runs, 0) },
        { value: formatNumber(row.mean_coverage) },
        { value: formatPercent(row.mean_optimality_gap) },
        { value: `${formatNumber(row.mean_runtime_seconds, 5)} s` },
        { value: formatNumber(row.timeouts, 0) }
      ];
      cells.forEach((cell) => { const td = document.createElement("td"); if (cell.kind) td.append(annotatedNode(cell.value, cell.kind)); else td.textContent = cell.value; tr.append(td); });
      body.append(tr);
    });
    if (!rows.length) { const tr = document.createElement("tr"); const td = document.createElement("td"); td.colSpan = 7; td.textContent = t("results.noSummary"); tr.append(td); body.append(tr); }
  }

  function renderArtifacts(data) {
    const links = $("#artifact-list"); links.replaceChildren();
    const charts = $("#chart-grid"); charts.replaceChildren();
    data.artifacts.forEach((artifact) => {
      const link = document.createElement("a"); link.className = "artifact-link"; link.href = artifact.url; link.target = "_blank"; link.rel = "noreferrer";
      const label = document.createElement("span"); label.className = "artifact-name"; const friendly = document.createElement("strong"); friendly.textContent = FRIENDLY_LABELS[state.language].artifact[artifact.name] || friendlyLabel(artifact.name, "artifact"); const filename = document.createElement("code"); filename.textContent = artifact.name; label.append(friendly, filename); const arrow = document.createElement("span"); arrow.textContent = "↗"; link.append(label, arrow); links.append(link);
      if (artifact.name.endsWith(".svg")) { const card = document.createElement("div"); card.className = "chart-card"; const caption = document.createElement("div"); caption.className = "chart-caption"; const captionLabel = document.createElement("strong"); captionLabel.textContent = FRIENDLY_LABELS[state.language].artifact[artifact.name] || friendlyLabel(artifact.name, "artifact"); const captionFilename = document.createElement("code"); captionFilename.textContent = artifact.name; caption.append(captionLabel, captionFilename); const image = document.createElement("img"); image.src = artifact.url; image.alt = `${captionLabel.textContent} (${artifact.name})`; card.append(caption, image); charts.append(card); }
    });
    if (!data.artifacts.length) links.textContent = t("results.noReports");
    if (!charts.children.length) charts.textContent = t("results.noPreview");
  }

  function renderAnnotations(rows) {
    const container = $("#result-annotations"); container.replaceChildren();
    appendAnnotationGroup(container, t("annotations.cases"), rows.map((row) => row.case), "case");
    appendAnnotationGroup(container, t("annotations.algorithms"), rows.map((row) => row.algorithm_id || row.algorithm), "algorithm");
    const metricGroup = document.createElement("div"); metricGroup.className = "annotation-group";
    const metricHeading = document.createElement("strong"); metricHeading.textContent = t("annotations.metrics"); metricGroup.append(metricHeading);
    [[t("metrics.meanCoverage"), "mean_coverage"], [t("metrics.meanGap"), "mean_optimality_gap"], [t("metrics.meanRuntime"), "mean_runtime_seconds"], [t("metrics.timeouts"), "timeouts"]].forEach(([label, raw]) => { const item = document.createElement("span"); item.className = "annotation-item"; const value = document.createElement("span"); value.className = "annotated-value"; const friendly = document.createElement("strong"); friendly.textContent = label; const code = document.createElement("code"); code.textContent = raw; value.append(friendly, code); item.append(value); metricGroup.append(item); });
    container.append(metricGroup);
  }

  async function loadResult(name, notify = true) {
    if (!name) { $("#result-empty").classList.remove("hidden"); $("#result-content").classList.add("hidden"); return; }
    try {
      if (notify) announceTransition("results", t("results.readingTitle"), `${name} · summary.csv / raw_results.csv`);
      const data = await api(`/api/result?name=${encodeURIComponent(name)}`); state.currentResult = name;
      $("#result-empty").classList.add("hidden"); $("#result-content").classList.remove("hidden");
      $("#result-summary-count").textContent = formatNumber(data.summary.length, 0); $("#result-run-count").textContent = formatNumber(data.runs.length, 0); $("#result-run-foot").textContent = data.runs.length >= data.run_limit ? t("results.firstRows", { count: formatNumber(data.run_limit, 0) }) : t("results.rawRecords");
      const resultInfo = state.results.find((item) => item.name === name); $("#result-failure-count").textContent = formatNumber(resultInfo ? resultInfo.failure_count : 0, 0); $("#result-meta").textContent = resultInfo ? t("results.updated", { time: resultInfo.modified_at }) : "";
      renderAnnotations(data.summary); renderSummary(data.summary); renderArtifacts(data);
      if (notify) announceTransition("results", t("results.loadedTitle"), t("results.loadedDetail"), 6000);
    } catch (error) { setMessage("#result-message", error.message, true); if (notify) announceTransition("results", t("results.failedTitle"), error.message, 0); }
  }

  function renderReplays() {
    $("#replay-count").textContent = state.language === "en" ? `${state.replays.length} files` : `${state.replays.length} 个文件`;
    setSelect("#replay-select", state.replays.map((item) => ({ label: `${friendlyLabel(item.result, "case")} · ${friendlyLabel(item.algorithm_id || item.algorithm, "algorithm")}`, value: item.path })), t("replay.noFiles"));
    setSelect("#replay-algorithm", state.algorithms.map((item) => ({ label: `${friendlyLabel(item.name, "algorithm")} · ${item.name}`, value: item.name })), t("replay.recordedAlgorithm"));
  }

  async function refreshAll() {
    try {
      const [configs, algorithms, results, jobs, replays] = await Promise.all([api("/api/configs"), api("/api/algorithms"), api("/api/results"), api("/api/jobs"), api("/api/replay-files")]);
      state.configs = configs.configs; state.algorithms = algorithms.algorithms; state.results = results.results; state.jobs = jobs.jobs; state.replays = replays.replays;
      $("#api-status").textContent = t("topbar.connected"); $("#api-status").style.color = "var(--green)";
      const selectedConfigPath = state.currentConfig?.path || $("#config-select").value;
      setSelect("#config-select", state.configs.map((item) => ({ label: item.name, value: item.path })), t("config.noConfigs"));
      renderJobs(); renderResults(); renderReplays();
      if (state.configs.length) { const defaultConfig = state.configs.find((item) => item.path === "quick.json") || state.configs[0]; const nextConfigPath = state.configs.some((item) => item.path === selectedConfigPath) ? selectedConfigPath : defaultConfig.path; $("#config-select").value = nextConfigPath; if (!state.currentConfig || state.currentConfig.path !== nextConfigPath) await loadConfig(nextConfigPath); }
      if (!state.currentConfig) announceTransition("select", t("workspace.connectedTitle"), t("workspace.connectedDetail"), 6000);
    } catch (error) { $("#api-status").textContent = `${t("topbar.offline")} · ${error.message}`; $("#api-status").style.color = "var(--red)"; }
  }

  async function pollJob(jobId) {
    if (state.pollTimer) clearInterval(state.pollTimer);
    const tick = async () => {
      try {
        const job = await api(`/api/jobs/${jobId}`); state.jobs = [job, ...state.jobs.filter((item) => item.id !== job.id)]; renderJobs(); $("#job-console").innerHTML = `<span class="console-prompt">›</span> ${STATUS_LABELS[state.language][job.status] || job.status} · ${job.config} → results/${job.output}`;
        if (["completed", "failed"].includes(job.status)) { clearInterval(state.pollTimer); state.pollTimer = null; $("#run-button").disabled = false; setMessage("#run-message", job.status === "completed" ? t("run.complete", { output: job.output }) : t("run.failed", { error: job.error }), job.status === "failed"); if (job.status === "completed") announceTransition("results", t("run.completedTitle"), t("run.completedDetail"), 0); await refreshAll(); if (job.status === "completed") showView("results", false); }
      } catch (error) { clearInterval(state.pollTimer); state.pollTimer = null; setMessage("#run-message", error.message, true); $("#run-button").disabled = false; }
    };
    await tick(); state.pollTimer = setInterval(tick, 1000);
  }

  async function runBenchmark() {
    if (!state.currentConfig?.valid) return;
    const button = $("#run-button"); button.disabled = true; $("#run-next-step").textContent = t("run.inProgress"); announceTransition("execute", t("run.startingTitle"), t("run.startingDetail"), 0); setMessage("#run-message", t("run.queued"));
    try {
      const job = await api("/api/run", { method: "POST", body: JSON.stringify({ config: $("#config-select").value, output: $("#output-name").value, workers: Number($("#workers").value), force: $("#force-run").checked }) });
      announceTransition("execute", t("run.startedTitle"), `${job.config} → results/${job.output}`, 0);
      await pollJob(job.id);
    } catch (error) { button.disabled = false; setMessage("#run-message", error.message, true); }
  }

  async function replay() {
    const instance = $("#replay-select").value; if (!instance) return;
    const button = $("#replay-button"); button.disabled = true; announceTransition("replay", t("replay.runningTitle"), instance); setMessage("#replay-message", t("replay.running"));
    try {
      const algorithm = $("#replay-algorithm").value; const data = await api("/api/replay", { method: "POST", body: JSON.stringify({ instance, ...(algorithm ? { algorithm } : {}) }) });
      setMessage("#replay-message", t("replay.doneMessage")); announceTransition("replay", t("replay.doneTitle"), data.matches === true ? t("replay.doneMatch") : t("replay.doneDetail"), 6000); const output = $("#replay-output"); output.className = "replay-output replay-result";
      const status = document.createElement("div"); status.className = `result-status ${data.matches === false ? "mismatch" : ""}`; status.textContent = data.matches === true ? t("replay.match") : data.matches === false ? t("replay.mismatch") : t("replay.noCompare");
      const dl = document.createElement("dl"); dl.className = "replay-dl"; [[t("replay.algorithm"), data.algorithm], [t("replay.status"), data.status], [t("replay.coverage"), formatNumber(data.coverage, 0)], [t("replay.selected"), (data.selected || []).join(", ") || "—"]].forEach(([label, value]) => { const box = document.createElement("div"); const dt = document.createElement("dt"); dt.textContent = label; const dd = document.createElement("dd"); dd.textContent = value; box.append(dt, dd); dl.append(box); }); output.replaceChildren(status, dl);
    } catch (error) { setMessage("#replay-message", error.message, true); } finally { button.disabled = false; }
  }

  $$("[data-view-target]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.viewTarget)));
  $("#config-select").addEventListener("change", (event) => loadConfig(event.target.value));
  $("#choose-quick").addEventListener("click", chooseQuickConfig);
  $("#choose-quick-inline").addEventListener("click", chooseQuickConfig);
  $("#validate-button").addEventListener("click", () => loadConfig($("#config-select").value));
  $("#run-button").addEventListener("click", runBenchmark);
  $("#result-select").addEventListener("change", (event) => loadResult(event.target.value));
  $("#refresh-results").addEventListener("click", refreshAll);
  $("#replay-button").addEventListener("click", replay);
  $$('[data-language]').forEach((button) => button.addEventListener("click", () => { applyLanguage(button.dataset.language); refreshAll(); }));
  state.language = initialLanguage();
  applyLanguage(state.language);
  refreshAll();
})();
