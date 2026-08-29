(() => {
  "use strict";

  const state = { configs: [], algorithms: [], results: [], jobs: [], replays: [], currentConfig: null, currentResult: null, currentReplay: null, language: "zh", pollTimer: null, pollingJobId: null, configRequestId: 0, configLoading: false, resultRequestId: 0, outputEdited: false };
  const STATUS_LABELS = {
    zh: { queued: "排队中", running: "运行中", completed: "已完成", failed: "失败" },
    en: { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed" }
  };
  const GREEDY_IDS = new Set(["greedy", "greedy_baseline", "lazy_greedy"]);
  const FRIENDLY_LABELS = {
    zh: {
      algorithm: { brute_force: "穷举搜索", branch_and_bound: "分支定界", branch_and_bound_enhanced: "增强分支定界", bnb_baseline: "分支定界基线", bnb_enhanced: "增强分支定界", bnb_reference: "分支定界参考", cp_sat_oracle: "CP-SAT 精确求解", greedy: "贪心算法", greedy_baseline: "贪心算法基线", lazy_greedy: "惰性贪心", local_search: "局部搜索", multi_start_local_search: "多起点局部搜索", randomized_greedy: "随机贪心" },
      case: { uniform_sparse: "均匀分布 · 稀疏", uniform_dense: "均匀分布 · 稠密", overlap_core: "高重叠 · 核心", overlap_moderate: "高重叠 · 中等", overlap_extreme: "高重叠 · 极端", four_clusters: "四簇聚类", eight_clusters: "八簇聚类", greedy_trap: "贪心陷阱", greedy_trap_small: "贪心陷阱 · 小型", greedy_trap_large: "贪心陷阱 · 大型", uniform: "均匀分布", high_overlap: "高重叠", clustered: "聚类结构", fixed_size: "固定大小", long_tail: "长尾", duplicate_heavy: "重复密集", dominated_heavy: "支配密集", mixed_cluster: "混合聚类", adversarial: "对抗结构" },
      artifact: { "results_summary.md": "报告摘要", "gap_by_family.svg": "按案例族查看覆盖差距", "runtime_by_algorithm.svg": "按算法查看运行耗时", "gap_by_case.svg": "按案例查看覆盖差距", "gap_vs_structural_parameter.svg": "差距与结构参数关系", "local_search_recovery.svg": "局部搜索恢复情况", "quality_runtime_pareto.svg": "质量与耗时权衡", "runtime_scaling.svg": "运行耗时扩展", "node_scaling.svg": "搜索节点扩展", "timeout_by_case.svg": "按案例查看超时" }
    },
    en: {
      algorithm: { brute_force: "Brute Force", branch_and_bound: "Branch and Bound", branch_and_bound_enhanced: "Enhanced Branch and Bound", bnb_baseline: "Branch and Bound Baseline", bnb_enhanced: "Enhanced Branch and Bound", bnb_reference: "Branch and Bound Reference", cp_sat_oracle: "CP-SAT Exact Solver", greedy: "Greedy", greedy_baseline: "Greedy Baseline", lazy_greedy: "Lazy Greedy", local_search: "Local Search", multi_start_local_search: "Multi-start Local Search", randomized_greedy: "Randomized Greedy" },
      case: { uniform_sparse: "Uniform · Sparse", uniform_dense: "Uniform · Dense", overlap_core: "High Overlap · Core", overlap_moderate: "High Overlap · Moderate", overlap_extreme: "High Overlap · Extreme", four_clusters: "Four Clusters", eight_clusters: "Eight Clusters", greedy_trap: "Greedy Trap", greedy_trap_small: "Greedy Trap · Small", greedy_trap_large: "Greedy Trap · Large", uniform: "Uniform", high_overlap: "High Overlap", clustered: "Clustered", fixed_size: "Fixed Size", long_tail: "Long Tail", duplicate_heavy: "Duplicate Heavy", dominated_heavy: "Dominated Heavy", mixed_cluster: "Mixed Cluster", adversarial: "Adversarial" },
      artifact: { "results_summary.md": "Report summary", "gap_by_family.svg": "Coverage gap by family", "runtime_by_algorithm.svg": "Runtime by algorithm", "gap_by_case.svg": "Coverage gap by case", "gap_vs_structural_parameter.svg": "Gap vs. structural parameter", "local_search_recovery.svg": "Local-search recovery", "quality_runtime_pareto.svg": "Quality/runtime trade-off", "runtime_scaling.svg": "Runtime scaling", "node_scaling.svg": "Search-node scaling", "timeout_by_case.svg": "Timeouts by case" }
    }
  };
  const I18N = {
    zh: {
      "document.title": "Maximum Coverage · 成果展板", "brand.title": "实验成果展板", "topbar.localOnly": "仅限本机", "topbar.connecting": "连接中…", "topbar.connected": "引擎已连接", "topbar.offline": "离线", "topbar.language": "语言",
      "entry.ariaLabel": "实验入口", "entry.kicker": "入口 · 启动实验", "entry.title": "启动一个实验", "entry.lede": "选择配置，一键在本机运行。完成后，成果会挂上这面展墙。",
      "fields.configFile": "配置文件", "fields.outputName": "结果文件夹名称", "fields.outputPlaceholder": "例如 quick-dashboard", "fields.forceRun": "清除后重跑",
      "actions.runBenchmark": "启动 benchmark", "actions.refreshResults": "刷新", "actions.runReplay": "运行回放",
      "plan.instances": "实例总数", "plan.repetitions": "每个实例重复", "plan.runs": "预计算法运行",
      "run.idle": "空闲 · 任务状态会显示在这里。", "run.queued": "任务已排队…", "run.complete": "运行完成：results/{output}", "run.failed": "运行失败：{error}",
      "config.noConfigs": "暂无可用 JSON 配置",
      "gap.ariaLabel": "差距光谱", "gap.kicker": "差距光谱 · 贪心在哪里失败", "gap.title": "贪心在哪里失败", "gap.lede": "每条光带对应一个案例族，长度是该族上贪心算法与最优解的平均差距。光带越长，结构越会诱导贪心犯错。", "gap.noSource": "尚未选择结果集", "gap.empty": "运行一个 benchmark 之后，光谱会从这里长出来。", "gap.note": "条带长度 = 贪心类算法与最优解的平均差距（mean_optimality_gap），按差距从大到小排列。",
      "gallery.ariaLabel": "成果画廊", "gallery.kicker": "成果 · 结果画廊", "gallery.title": "结果画廊", "gallery.lede": "每张图是当前结果集的一份报告，装裱成作品挂在墙上。", "gallery.empty": "运行完成后，报告图表会挂上这面墙。先在上方启动一个实验。", "gallery.summaryKicker": "对照 · 摘要", "gallery.summaryTitle": "算法对照", "gallery.loadingSummary": "正在读取报告摘要…", "gallery.openReport": "打开完整报告 ↗", "gallery.zoomHint": "点击放大", "lightbox.close": "关闭", "lightbox.escHint": "Esc 关闭",
      "results.updated": "更新时间 {time}", "results.failureCount": "失败案例 {count} 个", "results.noResult": "暂无结果", "results.noSummary": "没有汇总记录。",
      "table.case": "案例", "table.algorithm": "算法", "table.runs": "运行次数", "table.coverage": "平均覆盖", "table.gap": "平均差距", "table.runtime": "平均耗时", "table.timeouts": "超时",
      "replay.ariaLabel": "失败案例回放", "replay.kicker": "回放 · 重现失败", "replay.title": "失败案例回放", "replay.lede": "用记录的算法重现失败，核对结果。", "replay.noFiles": "暂无失败案例文件", "replay.recordedAlgorithm": "使用记录算法", "replay.outputEmpty": "运行后显示结果和匹配状态。", "replay.running": "正在运行回放…", "replay.match": "匹配 · 与记录结果一致", "replay.mismatch": "不匹配 · 与记录结果不同", "replay.noCompare": "运行完成 · 没有记录可比较", "replay.algorithm": "算法", "replay.status": "状态", "replay.coverage": "覆盖", "replay.selected": "已选择",
      "footer": "Maximum Coverage · 本地成果展板 · CLI 仍可使用"
    },
    en: {
      "document.title": "Maximum Coverage · Result wall", "brand.title": "Result wall", "topbar.localOnly": "LOCAL ONLY", "topbar.connecting": "Connecting…", "topbar.connected": "Engine connected", "topbar.offline": "Offline", "topbar.language": "Language",
      "entry.ariaLabel": "Experiment entry", "entry.kicker": "ENTRY · START A RUN", "entry.title": "Start a run", "entry.lede": "Pick a configuration and run it locally. When it finishes, the results hang on this wall.",
      "fields.configFile": "Configuration", "fields.outputName": "Result folder name", "fields.outputPlaceholder": "e.g. quick-dashboard", "fields.forceRun": "Clear and rerun",
      "actions.runBenchmark": "Start benchmark", "actions.refreshResults": "Refresh", "actions.runReplay": "Run replay",
      "plan.instances": "Total instances", "plan.repetitions": "Repetitions per instance", "plan.runs": "Planned algorithm runs",
      "run.idle": "Idle · job status appears here.", "run.queued": "Job queued…", "run.complete": "Run complete: results/{output}", "run.failed": "Run failed: {error}",
      "config.noConfigs": "No JSON configurations available",
      "gap.ariaLabel": "Gap spectrum", "gap.kicker": "GAP SPECTRUM · WHERE GREEDY FAILS", "gap.title": "Where greedy fails", "gap.lede": "Each band is a case family; its length is the average gap between greedy and optimal. Longer bands mark structures that lead greedy astray.", "gap.noSource": "No result set selected", "gap.empty": "Run a benchmark and the spectrum grows here.", "gap.note": "Band length = mean optimality gap of greedy-family algorithms, sorted from the largest gap.",
      "gallery.ariaLabel": "Result gallery", "gallery.kicker": "GALLERY · RESULTS", "gallery.title": "Result gallery", "gallery.lede": "Each image is one report from the selected result set, framed and hung on the wall.", "gallery.empty": "After a run completes, report charts hang on this wall. Start a run above first.", "gallery.summaryKicker": "TABLE · COMPARISON", "gallery.summaryTitle": "Algorithm comparison", "gallery.loadingSummary": "Loading report summary…", "gallery.openReport": "Open full report ↗", "gallery.zoomHint": "Click to enlarge", "lightbox.close": "Close", "lightbox.escHint": "Esc to close",
      "results.updated": "Updated {time}", "results.failureCount": "{count} failure cases", "results.noResult": "No results", "results.noSummary": "No summary records.",
      "table.case": "Case", "table.algorithm": "Algorithm", "table.runs": "Runs", "table.coverage": "Mean coverage", "table.gap": "Mean gap", "table.runtime": "Mean runtime", "table.timeouts": "Timeouts",
      "replay.ariaLabel": "Failure replay", "replay.kicker": "REPLAY · REPRODUCE FAILURE", "replay.title": "Failure replay", "replay.lede": "Reproduce a recorded failure and verify the result.", "replay.noFiles": "No failure files", "replay.recordedAlgorithm": "Use recorded algorithm", "replay.outputEmpty": "The result and match status appear here.", "replay.running": "Running replay…", "replay.match": "Match · same as recorded result", "replay.mismatch": "Mismatch · different from recorded result", "replay.noCompare": "Run complete · nothing to compare", "replay.algorithm": "Algorithm", "replay.status": "Status", "replay.coverage": "Coverage", "replay.selected": "Selected",
      "footer": "Maximum Coverage · local result wall · CLI remains available"
    }
  };
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
    $$("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
    $$("[data-i18n-placeholder]").forEach((element) => { element.placeholder = t(element.dataset.i18nPlaceholder); });
    $$("[data-i18n-aria]").forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAria)); });
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

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat(state.language === "en" ? "en-US" : "zh-CN", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
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
    options.forEach((option) => select.append(new Option(option.label, option.value)));
  }

  /* ── Entry band ────────────────────────────────────── */

  function renderConfig(configInfo) {
    state.currentConfig = configInfo;
    const loading = configInfo.loading === true;
    setMessage("#run-message", loading || configInfo.valid ? "" : (configInfo.error || ""), !loading && !configInfo.valid);
    $("#run-button").disabled = loading || !configInfo.valid;
    const strip = $("#plan-strip");
    strip.classList.toggle("hidden", loading || !configInfo.valid);
    if (loading || !configInfo.valid) return;
    const plan = configInfo.plan;
    $("#plan-name").textContent = plan.name;
    $("#plan-instances").textContent = formatNumber(plan.instance_count, 0);
    $("#plan-repetitions").textContent = formatNumber(plan.repetitions, 0);
    $("#plan-runs").textContent = formatNumber(plan.algorithm_run_count, 0);
    $("#algorithm-plan").replaceChildren(...plan.runs_by_algorithm.map((entry) => {
      const tag = document.createElement("span"); tag.className = "case-tag";
      const name = annotatedNode(entry.algorithm, "algorithm");
      const count = document.createElement("span"); count.textContent = ` · ${formatNumber(entry.runs, 0)}`;
      tag.append(name, count); return tag;
    }));
    const output = $("#output-name"); if (!state.outputEdited) output.value = configInfo.path.replace(/\.json$/i, "");
  }

  async function loadConfig(path) {
    const requestId = ++state.configRequestId;
    state.configLoading = Boolean(path);
    if (!path) { state.configLoading = false; renderConfig({ path: "", valid: false, source: null }); return; }
    renderConfig({ path, valid: false, loading: true, source: null });
    try {
      const configInfo = await api(`/api/config?path=${encodeURIComponent(path)}`);
      if (requestId !== state.configRequestId || $("#config-select").value !== path) return;
      state.configLoading = false;
      renderConfig({ ...configInfo, path });
    } catch (error) {
      if (requestId !== state.configRequestId || $("#config-select").value !== path) return;
      state.configLoading = false;
      renderConfig({ path, valid: false, error: error.message });
    }
  }

  function renderJobLine() {
    const line = $("#job-line");
    const dot = document.createElement("span"); dot.className = "job-dot";
    if (!state.jobs.length) {
      dot.classList.add("idle");
      line.replaceChildren(dot, document.createTextNode(t("run.idle")));
      return;
    }
    const job = state.jobs[0];
    dot.classList.add(job.status);
    line.replaceChildren(dot, document.createTextNode(`${STATUS_LABELS[state.language][job.status] || job.status} · ${job.config} → results/${job.output}`));
  }

  async function runBenchmark() {
    const selectedConfigPath = $("#config-select").value;
    if (state.configLoading || !state.currentConfig?.valid || state.currentConfig.path !== selectedConfigPath || typeof state.currentConfig.config_hash !== "string") return;
    const button = $("#run-button"); button.disabled = true;
    setMessage("#run-message", t("run.queued"));
    try {
      const job = await api("/api/run", { method: "POST", body: JSON.stringify({ config: $("#config-select").value, config_hash: state.currentConfig.config_hash, output: $("#output-name").value, workers: 1, force: $("#force-run").checked }) });
      await pollJob(job.id);
    } catch (error) { button.disabled = !state.currentConfig?.valid; setMessage("#run-message", error.message, true); }
  }

  async function pollJob(jobId) {
    if (state.pollingJobId === jobId) return;
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
    state.pollingJobId = jobId;
    $("#run-button").disabled = true;
    const tick = async () => {
      try {
        const job = await api(`/api/jobs/${jobId}`);
        state.jobs = [job, ...state.jobs.filter((item) => item.id !== job.id)];
        renderJobLine();
        if (["completed", "failed"].includes(job.status)) {
          if (state.pollTimer) clearInterval(state.pollTimer);
          state.pollTimer = null; state.pollingJobId = null;
          $("#run-button").disabled = !state.currentConfig?.valid;
          setMessage("#run-message", job.status === "completed" ? t("run.complete", { output: job.output }) : t("run.failed", { error: job.error }), job.status === "failed");
          if (job.status === "completed" && job.result_name) state.currentResult = job.result_name;
          await refreshAll();
          return false;
        }
        return true;
      } catch (error) {
        if (state.pollTimer) clearInterval(state.pollTimer);
        state.pollTimer = null; state.pollingJobId = null;
        setMessage("#run-message", error.message, true);
        $("#run-button").disabled = !state.currentConfig?.valid;
        return false;
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
      if (current) { current.total += gap; current.count += 1; }
      else byFamily.set(family, { familyName: family, total: gap, count: 1 });
    });
    const entries = [...byFamily.values()]
      .map((entry) => ({ familyName: entry.familyName, gap: entry.total / entry.count }))
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
      const rowEl = document.createElement("div"); rowEl.className = "spectrum-row";
      const label = document.createElement("span"); label.className = "spectrum-case"; label.textContent = friendlyLabel(entry.familyName, "case");
      const track = document.createElement("div"); track.className = "spectrum-track";
      const bar = document.createElement("div"); bar.className = "spectrum-bar";
      track.append(bar);
      const value = document.createElement("span"); value.className = "spectrum-value"; value.textContent = formatPercent(entry.gap);
      rowEl.append(label, track, value);
      container.append(rowEl);
      const width = maxGap > 0 ? `${Math.max((entry.gap / maxGap) * 100, 1.5)}%` : "0%";
      requestAnimationFrame(() => { requestAnimationFrame(() => { bar.style.width = width; }); });
    });
    const note = document.createElement("p"); note.className = "spectrum-note"; note.textContent = t("gap.note");
    container.append(note);
  }

  /* ── Gallery ───────────────────────────────────────── */

  function frameCaption(artifact) {
    const caption = document.createElement("figcaption"); caption.className = "frame-caption";
    const title = document.createElement("strong");
    title.textContent = FRIENDLY_LABELS[state.language].artifact[artifact.name] || friendlyLabel(artifact.name, "artifact");
    const filename = document.createElement("code"); filename.textContent = artifact.name;
    caption.append(title, filename);
    return caption;
  }

  function summaryFrame(artifact, hero) {
    const frame = document.createElement("figure");
    frame.className = hero ? "frame frame-summary frame-hero" : "frame frame-summary";
    const pre = document.createElement("pre"); pre.textContent = t("gallery.loadingSummary");
    const link = document.createElement("a"); link.className = "text-link"; link.href = artifact.url; link.target = "_blank"; link.rel = "noreferrer"; link.textContent = t("gallery.openReport");
    frame.append(frameCaption(artifact), pre, link);
    fetch(artifact.url).then((response) => response.text()).then((text) => { pre.textContent = text.slice(0, 800); }).catch(() => { pre.textContent = ""; });
    return frame;
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
    const panel = document.createElement("div"); panel.className = "lightbox-panel";
    const close = document.createElement("button"); close.className = "lightbox-close"; close.type = "button"; close.textContent = "×";
    close.addEventListener("click", closeLightbox);
    const image = document.createElement("img"); image.className = "lightbox-image"; image.alt = "";
    const caption = document.createElement("div"); caption.className = "lightbox-caption";
    const title = document.createElement("strong");
    const filename = document.createElement("code");
    const hint = document.createElement("span"); hint.className = "lightbox-hint";
    caption.append(title, filename, hint);
    panel.append(close, image, caption);
    lightbox.append(panel);
    lightbox.addEventListener("click", (event) => { if (event.target === lightbox) closeLightbox(); });
    document.body.append(lightbox);
  }

  function openLightbox(artifact, trigger) {
    ensureLightbox();
    const title = FRIENDLY_LABELS[state.language].artifact[artifact.name] || friendlyLabel(artifact.name, "artifact");
    lightbox.querySelector(".lightbox-image").src = artifact.url;
    lightbox.querySelector(".lightbox-image").alt = title;
    lightbox.querySelector(".lightbox-caption strong").textContent = title;
    lightbox.querySelector(".lightbox-caption code").textContent = artifact.name;
    lightbox.querySelector(".lightbox-hint").textContent = t("lightbox.escHint");
    lightbox.querySelector(".lightbox-close").setAttribute("aria-label", t("lightbox.close"));
    lightboxTrigger = trigger;
    lightbox.hidden = false;
    document.body.classList.add("lightbox-open");
    lightbox.querySelector(".lightbox-close").focus();
  }

  function closeLightbox() {
    if (!lightbox || lightbox.hidden) return;
    lightbox.hidden = true;
    document.body.classList.remove("lightbox-open");
    if (lightboxTrigger) { lightboxTrigger.focus(); lightboxTrigger = null; }
  }

  function chartFrame(artifact, hero) {
    const frame = document.createElement("figure");
    frame.className = hero ? "frame frame-chart frame-hero" : "frame frame-chart";
    frame.tabIndex = 0;
    frame.setAttribute("role", "button");
    frame.setAttribute("aria-haspopup", "dialog");
    frame.setAttribute("aria-label", `${FRIENDLY_LABELS[state.language].artifact[artifact.name] || artifact.name} · ${t("gallery.zoomHint")}`);
    frame.addEventListener("click", () => openLightbox(artifact, frame));
    frame.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openLightbox(artifact, frame); }
    });
    const mat = document.createElement("div"); mat.className = "frame-mat";
    const image = document.createElement("img"); image.src = artifact.url; image.alt = `${FRIENDLY_LABELS[state.language].artifact[artifact.name] || artifact.name} (${artifact.name})`; image.loading = "lazy";
    const hint = document.createElement("span"); hint.className = "frame-zoom-hint"; hint.textContent = t("gallery.zoomHint");
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
    const docs = artifacts.filter((artifact) => !artifact.name.endsWith(".svg"));
    const charts = artifacts.filter((artifact) => artifact.name.endsWith(".svg"));
    docs.forEach((artifact, index) => grid.append(summaryFrame(artifact, index === 0)));
    charts.forEach((artifact, index) => grid.append(chartFrame(artifact, !docs.length && index === 0)));
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

  function renderResultMeta(name) {
    const info = state.results.find((item) => item.name === name);
    $("#result-meta").textContent = info ? `${t("results.updated", { time: formatDate(info.modified_at) })} · ${t("results.failureCount", { count: formatNumber(info.failure_count, 0) })}` : "";
  }

  async function loadResult(name) {
    const requestId = ++state.resultRequestId;
    if (!name) {
      $("#spectrum-source").textContent = t("gap.noSource");
      renderSpectrum([]);
      renderGallery({ artifacts: [] });
      renderSummary([]);
      renderResultMeta("");
      return;
    }
    try {
      const data = await api(`/api/result?name=${encodeURIComponent(name)}`);
      if (requestId !== state.resultRequestId || $("#result-select").value !== name) return;
      state.currentResult = name;
      $("#spectrum-source").textContent = name;
      renderSummary(data.summary);
      renderSpectrum(data.summary);
      renderGallery(data);
      renderResultMeta(name);
    } catch (error) {
      if (requestId !== state.resultRequestId || $("#result-select").value !== name) return;
      setMessage("#result-message", error.message, true);
    }
  }

  /* ── Replay ────────────────────────────────────────── */

  function renderReplays() {
    const selectedReplayPath = state.currentReplay || $("#replay-select").value;
    setSelect("#replay-select", state.replays.map((item) => ({ label: `${friendlyLabel(item.result, "case")} · ${friendlyLabel(item.algorithm_id || item.algorithm, "algorithm")}`, value: item.path })), t("replay.noFiles"));
    if (state.replays.length) {
      state.currentReplay = state.replays.some((item) => item.path === selectedReplayPath) ? selectedReplayPath : state.replays[0].path;
      $("#replay-select").value = state.currentReplay;
    } else state.currentReplay = null;
  }

  function renderReplayOutput(data) {
    const output = $("#replay-output");
    output.className = "replay-output replay-result";
    const status = document.createElement("div");
    status.className = `result-status ${data.matches === false ? "mismatch" : ""}`;
    status.textContent = data.matches === true ? t("replay.match") : data.matches === false ? t("replay.mismatch") : t("replay.noCompare");
    const dl = document.createElement("dl"); dl.className = "replay-dl";
    [[t("replay.algorithm"), data.algorithm], [t("replay.status"), data.status], [t("replay.coverage"), formatNumber(data.coverage, 0)], [t("replay.selected"), (data.selected || []).join(", ") || "—"]].forEach(([label, value]) => {
      const box = document.createElement("div");
      const dt = document.createElement("dt"); dt.textContent = label;
      const dd = document.createElement("dd"); dd.textContent = value;
      box.append(dt, dd); dl.append(box);
    });
    output.replaceChildren(status, dl);
  }

  async function replay() {
    const instance = $("#replay-select").value; if (!instance) return;
    const button = $("#replay-button"); button.disabled = true;
    setMessage("#replay-message", t("replay.running"));
    try {
      const algorithm = $("#replay-algorithm").value;
      const data = await api("/api/replay", { method: "POST", body: JSON.stringify({ instance, ...(algorithm ? { algorithm } : {}) }) });
      setMessage("#replay-message", "");
      renderReplayOutput(data);
    } catch (error) { setMessage("#replay-message", error.message, true); } finally { button.disabled = false; }
  }

  /* ── Refresh ───────────────────────────────────────── */

  async function refreshAll() {
    try {
      const [configs, algorithms, results, jobs, replays] = await Promise.all([api("/api/configs"), api("/api/algorithms"), api("/api/results"), api("/api/jobs"), api("/api/replay-files")]);
      state.configs = configs.configs; state.algorithms = algorithms.algorithms; state.results = results.results; state.jobs = jobs.jobs; state.replays = replays.replays;
      $("#api-status").textContent = t("topbar.connected"); $("#api-status").style.color = "var(--green)";
      const selectedConfigPath = state.currentConfig?.path || $("#config-select").value;
      setSelect("#config-select", state.configs.map((item) => ({ label: item.name, value: item.path })), t("config.noConfigs"));
      setSelect("#replay-algorithm", state.algorithms.map((item) => ({ label: `${friendlyLabel(item.name, "algorithm")} · ${item.name}`, value: item.name })), t("replay.recordedAlgorithm"), true);
      renderReplays();
      renderJobLine();
      const activeJob = state.jobs.find((job) => ["queued", "running"].includes(job.status));
      if (activeJob && !state.pollingJobId) pollJob(activeJob.id);
      if (state.configs.length) {
        const defaultConfig = state.configs.find((item) => item.path === "quick.json") || state.configs[0];
        const nextConfigPath = state.configs.some((item) => item.path === selectedConfigPath) ? selectedConfigPath : defaultConfig.path;
        $("#config-select").value = nextConfigPath;
        // Revalidate even when the path did not change: a corrected invalid
        // preflight or a hash conflict stays stale otherwise, and with a
        // single configuration there is no change event to trigger a reload.
        await loadConfig(nextConfigPath);
      }
      setSelect("#result-select", state.results.map((item) => ({ label: item.name, value: item.name })), t("results.noResult"));
      const select = $("#result-select");
      if (state.results.length) {
        select.value = state.currentResult && state.results.some((item) => item.name === state.currentResult) ? state.currentResult : state.results[0].name;
        loadResult(select.value);
      } else loadResult("");
    } catch (error) { $("#api-status").textContent = `${t("topbar.offline")} · ${error.message}`; $("#api-status").style.color = "var(--red)"; }
  }

  /* ── Wiring ────────────────────────────────────────── */

  $("#config-select").addEventListener("change", (event) => loadConfig(event.target.value));
  $("#run-button").addEventListener("click", runBenchmark);
  $("#output-name").addEventListener("input", () => { state.outputEdited = $("#output-name").value !== ""; });
  $("#result-select").addEventListener("change", (event) => loadResult(event.target.value));
  $("#refresh-results").addEventListener("click", refreshAll);
  $("#replay-select").addEventListener("change", (event) => { state.currentReplay = event.target.value || null; });
  $("#replay-button").addEventListener("click", replay);
  $$("[data-language]").forEach((button) => button.addEventListener("click", () => { applyLanguage(button.dataset.language); refreshAll(); }));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && lightbox && !lightbox.hidden) closeLightbox();
  });

  state.language = initialLanguage();
  applyLanguage(state.language);
  refreshAll();
})();
