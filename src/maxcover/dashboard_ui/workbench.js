(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { library: [], selected: new Set(), view: "library", request: 0,
    comparison: null, detail: null, step: 0, timer: null, page: 0 };
  const percent = (value) => value == null ? "—" : `${(100 * value).toFixed(2)}%`;
  const number = (value, digits = 2) => value == null ? "—" : Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  const population = (value) => ({ pilot: "pilot 实验样本", confirmation: "确认实验样本", experiment: "实验样本", fixture: "功能夹具" })[value] || value;
  const status = (value) => ({ saved: "保存的 R1 记录", feasible: "可行解", optimal: "已证最优", timeout: "超时", error: "错误" })[value] || value;
  const mechanism = (value) => ({ none: "未失效", tie_avoidable: "存在可避免失效的平局选择", one_step_limit: "最大边际候选均无法保持最优" })[value] || value || "未记录";
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function cell(row, text, note) {
    const td = el("td", text);
    if (note) td.append(el("small", note));
    row.append(td);
    return td;
  }
  function empty(id, message, columns) {
    const row = el("tr"); const td = cell(row, message); td.colSpan = columns;
    $(id).replaceChildren(row);
  }
  function message(text = "", error = false) {
    $("wb-message").textContent = text;
    $("wb-message").className = error ? "error" : "";
  }
  async function api(path, params = new URLSearchParams()) {
    const response = await fetch(`/api/workbench/${path}?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法读取数据");
    return data;
  }
  function stop() {
    clearInterval(state.timer); state.timer = null;
    $("step-play").textContent = "播放";
  }
  function show(view) {
    stop(); state.view = view;
    for (const name of ["library", "compare", "detail"]) {
      $(`view-${name}`).hidden = name !== view;
      $(`nav-${name}`).toggleAttribute("aria-current", name === view);
      if (name === view) $(`nav-${name}`).setAttribute("aria-current", "page");
    }
    $(`${view === "detail" ? "detail" : view}-title`).focus({ preventScroll: true });
  }
  function saveSelection() {
    try { sessionStorage.setItem("maxcover-workbench-sources", JSON.stringify([...state.selected])); } catch (_) { /* Storage is optional. */ }
    $("compare-selected").disabled = !state.selected.size;
    $("nav-compare").disabled = !state.selected.size;
    $("compare-selected").textContent = `比较所选实验（${state.selected.size}）`;
  }
  function renderLibrary() {
    const query = $("library-search").value.trim().toLowerCase();
    const kind = $("library-kind").value;
    const items = state.library.filter((item) => (!kind || item.kind === kind)
      && [item.source, ...(item.cases || []), ...(item.algorithms || [])].join(" ").toLowerCase().includes(query));
    $("library-body").replaceChildren();
    for (const item of items) {
      const row = el("tr");
      const box = el("input"); box.type = "checkbox"; box.checked = state.selected.has(item.source);
      box.disabled = Boolean(item.error); box.setAttribute("aria-label", `选择 ${item.source}`);
      box.addEventListener("change", () => {
        if (box.checked && state.selected.size >= 4) { box.checked = false; message("一次最多比较四份数据。", true); return; }
        box.checked ? state.selected.add(item.source) : state.selected.delete(item.source);
        state.detail = null; $("nav-detail").disabled = true; message(); saveSelection();
      });
      cell(row, "").append(box);
      cell(row, item.source.split("/").pop(), item.source);
      if (item.error) {
        const td = cell(row, `无法读取：${item.error}`); td.colSpan = 4; td.className = "wb-error";
      } else {
        cell(row, item.kind === "r1" ? "R1 轨迹" : "Benchmark", item.populations.map(population).join(" / "));
        cell(row, item.cases.join(" · "));
        cell(row, item.algorithms.join(" · "));
        cell(row, `${item.records} / ${item.instances}`);
      }
      $("library-body").append(row);
    }
    if (!items.length) empty("library-body", state.library.length ? "没有符合筛选条件的数据。" : "尚无原始数据。可返回实验入口运行小型示例，或在项目数据目录放入已有产物。", 6);
    $("library-count").textContent = `显示 ${items.length} / ${state.library.length} 份来源；选择在搜索时保留。`;
    saveSelection();
  }
  async function library() {
    const request = ++state.request; show("library"); message("正在读取实验库…");
    $("refresh-library").disabled = true;
    try {
      const data = await api("library"); if (request !== state.request) return;
      state.library = data.sources;
      const available = new Set(data.sources.filter((item) => !item.error).map((item) => item.source));
      state.selected = new Set([...state.selected].filter((source) => available.has(source)).slice(0, 4));
      renderLibrary(); message();
    } catch (error) { if (request === state.request) { empty("library-body", "读取失败，可点击刷新重试。", 6); message(error.message, true); } }
    finally { $("refresh-library").disabled = false; }
  }
  function options(id, values, caption) {
    const selected = $(id).value;
    $(id).replaceChildren(new Option(caption, ""), ...values.map((value) => new Option(value, value)));
    if (values.includes(selected)) $(id).value = selected;
  }
  function compareParams() {
    const params = new URLSearchParams();
    for (const source of state.selected) params.append("source", source);
    for (const name of ["case", "algorithm", "population", "outcome"]) {
      if ($(`compare-${name}`).value) params.set(name, $(`compare-${name}`).value);
    }
    params.set("page", state.page);
    return params;
  }
  function renderComparison(data) {
    state.comparison = data; state.page = data.page;
    options("compare-case", data.cases, "全部案例");
    options("compare-algorithm", data.algorithms, "全部算法");
    $("compare-sources").textContent = data.sources.join("  ·  ");
    $("summary-body").replaceChildren();
    $("comparison-chart").replaceChildren();
    const chartRows = data.summaries.filter((row) => row.mean_gap != null).slice(0, 12);
    if (chartRows.length) {
      $("comparison-chart").append(el("h3", "各组平均相对损失（%）"));
      const max = Math.max(...chartRows.map((row) => row.mean_gap), .01);
      for (const item of chartRows) {
        const row = el("div", null, "wb-bar-row");
        row.append(el("span", `${item.source.split("/").pop()} / ${item.case_id} / ${item.algorithm_id} / ${population(item.population)}`));
        const track = el("div", null, "wb-bar-track"); const bar = el("i");
        bar.style.width = `${item.mean_gap / max * 100}%`; track.append(bar);
        row.append(track, el("span", percent(item.mean_gap))); $("comparison-chart").append(row);
      }
      $("comparison-chart").append(el("p", "来源：所选文件的全部匹配记录；显示前 12 个有可用损失的分组，完整分组见下表。各条使用共同尺度，右侧为实际均值。", "help-text"));
    }
    for (const item of data.summaries) {
      const row = el("tr");
      const td = cell(row, item.case_id, `${item.source} · n=${item.universe_size}, m=${item.set_count}, k=${item.k}`);
      const details = el("details"); details.append(el("summary", "参数与算法选项"), el("pre", JSON.stringify({ parameters: item.parameters, algorithm_options: item.algorithm_options }, null, 2))); td.append(details);
      cell(row, item.algorithm_id, population(item.population));
      cell(row, item.records); cell(row, `${item.gap_records} / ${item.missing_gap}`);
      cell(row, `${item.losses} / ${percent(item.loss_rate)}`);
      cell(row, `${percent(item.mean_gap)} / ${percent(item.max_gap)}`);
      cell(row, number(item.mean_coverage)); cell(row, number(item.mean_runtime, 6));
      cell(row, `${item.errors} / ${item.timeouts}`); $("summary-body").append(row);
    }
    if (!data.summaries.length) empty("summary-body", "当前样本与案例筛选没有匹配记录。", 9);
    $("records-body").replaceChildren();
    for (const item of data.rows) {
      const row = el("tr");
      cell(row, item.case_id, item.source);
      cell(row, item.repetition ?? "—", item.seed == null ? "无种子" : `seed ${item.seed}`);
      cell(row, item.algorithm_id, population(item.population));
      cell(row, `${number(item.coverage, 0)} / ${number(item.optimum, 0)}`);
      cell(row, percent(item.optimality_gap)); cell(row, status(item.status));
      const button = el("button", "查看实例 →", "button button-secondary");
      button.addEventListener("click", () => openDetail(item.source, item.key));
      cell(row, "").append(button); $("records-body").append(row);
    }
    if (!data.rows.length) empty("records-body", "当前明细筛选没有匹配记录。可调整筛选条件。", 7);
    $("page-info").textContent = `第 ${data.page + 1} / ${data.pages} 页 · 明细 ${data.total} 条 · 汇总 ${data.filtered_records} / 输入 ${data.input_records} 条`;
    $("page-prev").disabled = data.page === 0; $("page-next").disabled = data.page + 1 >= data.pages;
  }
  async function compare(reset = false) {
    if (!state.selected.size) return;
    if (reset) state.page = 0;
    const request = ++state.request; show("compare"); message("正在读取完整输入并计算汇总…");
    $("compare-sources").textContent = [...state.selected].join("  ·  ");
    empty("summary-body", "正在读取…", 9); empty("records-body", "正在读取…", 7);
    $("comparison-chart").replaceChildren(); $("page-info").textContent = "";
    $("page-prev").disabled = true; $("page-next").disabled = true;
    try { const data = await api("compare", compareParams()); if (request !== state.request) return;
      renderComparison(data); message();
    } catch (error) { if (request === state.request) { empty("summary-body", "无法读取当前比较。", 9); empty("records-body", "修正来源或筛选后重试。", 7); message(error.message, true); } }
  }
  function svg(tag, attrs = {}, text) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    if (text != null) node.textContent = String(text);
    return node;
  }
  function drawMatrix(trace, step) {
    const matrix = $("instance-matrix"); matrix.replaceChildren();
    const unit = 19, left = 46, top = 40;
    const width = left + trace.universe_size * unit + 12, height = top + trace.sets.length * unit + 14;
    matrix.setAttribute("viewBox", `0 0 ${width} ${height}`); matrix.style.width = `${width}px`; matrix.style.height = `${height}px`;
    matrix.append(svg("title", {}, `第 ${state.step} 步，已选 ${step.prefix.map((s) => `S${s}`).join("、") || "无"}，覆盖 ${step.coverage} 个元素`));
    for (let index = 0; index < trace.universe_size; index++) {
      if (step.covered_elements.includes(index)) matrix.append(svg("rect", { x: left + index * unit - 8, y: top - 11, width: 17, height: trace.sets.length * unit, class: "matrix-covered" }));
      matrix.append(svg("text", { x: left + index * unit, y: 23, "text-anchor": "middle" }, index));
    }
    trace.sets.forEach((elements, index) => {
      const selected = step.prefix.includes(index), next = step.next_choice === index;
      if (selected || next) matrix.append(svg("rect", { x: 0, y: top + index * unit - 10, width, height: 18, class: selected ? "matrix-selected" : "matrix-next" }));
      matrix.append(svg("text", { x: 7, y: top + index * unit + 4 }, `S${index}`));
      for (const element of elements) {
        const dot = svg("circle", { cx: left + element * unit, cy: top + index * unit, r: 3.5,
          class: next ? "next-dot" : selected ? "selected-dot" : "matrix-hit" });
        dot.append(svg("title", {}, `S${index} 包含元素 ${element}`)); matrix.append(dot);
      }
    });
  }
  function drawChart(trace) {
    const chart = $("trajectory-chart"); chart.replaceChildren(); chart.setAttribute("viewBox", "0 0 340 200");
    const x = (step) => 35 + step / Math.max(1, trace.steps.length - 1) * 280;
    const y = (coverage) => 163 - coverage / Math.max(1, trace.optimum) * 125;
    chart.append(svg("line", { x1: 35, x2: 315, y1: 163, y2: 163, stroke: "var(--muted)" }));
    chart.append(svg("line", { x1: 35, x2: 35, y1: 30, y2: 163, stroke: "var(--muted)" }));
    chart.append(svg("text", { x: 5, y: 17 }, "覆盖元素数"), svg("text", { x: 240, y: 197 }, "选择步数"));
    chart.append(svg("text", { x: 8, y: 167 }, "0"), svg("text", { x: 8, y: 42 }, trace.optimum));
    chart.append(svg("line", { x1: 35, x2: 315, y1: y(trace.optimum), y2: y(trace.optimum), stroke: "var(--muted)", "stroke-dasharray": "4 4" }));
    for (const [field, color] of [["coverage", "var(--accent)"], ["optimal_completion", "var(--amber)"]]) {
      chart.append(svg("polyline", { points: trace.steps.map((step) => `${x(step.step)},${y(step[field])}`).join(" "), fill: "none", stroke: color, "stroke-width": 2 }));
    }
    for (const step of trace.steps) chart.append(svg("text", { x: x(step.step), y: 181, "text-anchor": "middle" }, step.step));
    chart.append(svg("line", { x1: x(state.step), x2: x(state.step), y1: 28, y2: 164, stroke: "var(--ink)", "stroke-dasharray": "2 3" }));
  }
  function renderStep() {
    const trace = state.detail.trace, step = trace.steps[state.step];
    $("step-range").value = state.step; $("step-range").max = trace.steps.length - 1;
    $("step-label").textContent = `${state.step} / ${trace.steps.length - 1}`;
    $("step-prev").disabled = state.step === 0; $("step-next").disabled = state.step === trace.steps.length - 1;
    const gain = state.step ? step.coverage - trace.steps[state.step - 1].coverage : 0;
    $("step-summary").replaceChildren(el("span", `已选：${step.prefix.map((s) => `S${s}`).join(" → ") || "尚未选择"}`),
      el("span", `已覆盖 ${step.coverage} / ${trace.universe_size} · 本步新增 ${gain}`),
      el("strong", `最优补全值 ${step.optimal_completion} / 全局最优 ${trace.optimum}`));
    $("gain-list").replaceChildren();
    step.gains.forEach((value, index) => $("gain-list").append(el("div",
      `S${index} · ${value == null ? "已选" : `+${value}`}${step.next_choice === index ? " ←下一步" : ""}`,
      `wb-gain${value == null ? " selected" : step.next_choice === index ? " next" : ""}`)));
    $("tie-witness").textContent = step.ties.length ? `下一步最大边际候选：${step.ties.map((tie) => `S${tie.candidate}（+${tie.marginal_gain}，补全值 ${tie.optimal_completion}${tie.preserves_optimum ? "，可保持最优" : ""}）`).join("；")}` : "Greedy 选择已结束。";
    drawMatrix(trace, step); drawChart(trace);
  }
  function renderDetail(data) {
    state.detail = data; state.step = 0; $("nav-detail").disabled = false;
    const row = data.record;
    $("detail-title").textContent = `${row.case_id} · ${row.repetition == null ? "功能夹具" : `重复 ${row.repetition}`}`;
    $("detail-source").textContent = `${row.source} · ${population(row.population)}`;
    $("record-metadata").replaceChildren();
    const facts = [["实例身份", row.instance_id], ["配置身份", row.config_hash || "未记录"],
      ["规模与种子", `n=${row.universe_size}, m=${row.set_count}, k=${row.k} · seed=${row.seed ?? "无"}`],
      ["所选算法记录", `${row.algorithm_id} · ${status(row.status)} · 覆盖 ${row.coverage ?? "—"} · 最优参考 ${row.optimum ?? "—"} · 损失 ${percent(row.optimality_gap)}`],
      ["记录的集合", row.selected.map((index) => `S${index}`).join(", ") || "无"],
      ["参数 / 选项", JSON.stringify({ parameters: row.parameters, algorithm_options: row.algorithm_options })]];
    if (row.error_message) facts.push(["运行错误", row.error_message]);
    for (const [name, value] of facts) $("record-metadata").append(el("dt", name), el("dd", value));
    $("trace-view").hidden = !data.trace; $("export-case").hidden = !data.trace;
    $("trace-message").textContent = data.trace
      ? `轨迹来源：${data.trace_source}。下方展示 Greedy 的保存诊断；已检查集合、覆盖与选择的一致性，没有重新证明最优性。${data.warnings.join(" ")}`
      : `此记录没有可关联的 R1 实际集合和轨迹，保留记录详情。只有完整实验身份匹配才关联轨迹，不用种子猜测。${data.warnings.join(" ")}`;
    if (!data.trace) { $("export-case").removeAttribute("href"); return; }
    const trace = data.trace;
    $("export-case").href = `/api/workbench/export?${new URLSearchParams({ source: row.source, key: row.key })}`;
    $("trace-outcome").textContent = trace.first_failure_step == null ? "此路径始终保留最优可达性" : `第 ${trace.first_failure_step} 步首次失去最优可达性`;
    $("optimum-witness").textContent = `保存的最优选择：${trace.optimum_selected.map((s) => `S${s}`).join(" + ")}，覆盖 ${trace.optimum}。机制标签：${mechanism(trace.mechanism)}。`;
    $("swap-summary").replaceChildren();
    for (const [name, label] of [["one_swap", "1-swap"], ["two_swap", "后续至多 2-swap"]]) {
      const swap = trace[name]; if (!swap) continue;
      $("swap-summary").append(el("p", `${label}：覆盖 ${swap.coverage}，选择 ${swap.selected.map((s) => `S${s}`).join(" + ")}；交换 ${swap.exchanges} 次；保存状态 ${swap.status}。`));
    }
    renderStep();
  }
  async function openDetail(source, key) {
    const request = ++state.request; show("detail"); message("正在读取实例与保存轨迹…");
    $("trace-view").hidden = true; $("export-case").hidden = true; $("export-case").removeAttribute("href");
    $("record-metadata").replaceChildren(); $("trace-message").textContent = ""; $("detail-source").textContent = "";
    $("detail-title").textContent = "实例详情"; state.detail = null; $("nav-detail").disabled = true;
    try { const data = await api("detail", new URLSearchParams({ source, key })); if (request !== state.request) return;
      renderDetail(data); message();
    } catch (error) { if (request === state.request) message(error.message, true); }
  }
  $("refresh-library").addEventListener("click", library);
  for (const id of ["library-search", "library-kind"]) $(id).addEventListener("input", renderLibrary);
  $("compare-selected").addEventListener("click", () => {
    for (const name of ["case", "algorithm"]) $(`compare-${name}`).value = "";
    $("compare-population").value = "research"; $("compare-outcome").value = "all"; compare(true);
  });
  for (const id of ["nav-library", "change-sources"]) $(id).addEventListener("click", () => { ++state.request; show("library"); message(); });
  for (const id of ["nav-compare", "back-compare"]) $(id).addEventListener("click", () => compare());
  $("nav-detail").addEventListener("click", () => { if (state.detail) { ++state.request; show("detail"); message(); } });
  for (const name of ["case", "algorithm", "population", "outcome"]) $(`compare-${name}`).addEventListener("change", () => compare(true));
  $("page-prev").addEventListener("click", () => { state.page--; compare(); });
  $("page-next").addEventListener("click", () => { state.page++; compare(); });
  $("step-range").addEventListener("input", () => { stop(); state.step = Number($("step-range").value); renderStep(); });
  $("step-reset").addEventListener("click", () => { stop(); state.step = 0; renderStep(); });
  $("step-prev").addEventListener("click", () => { stop(); state.step--; renderStep(); });
  $("step-next").addEventListener("click", () => { stop(); state.step++; renderStep(); });
  $("step-play").addEventListener("click", () => {
    if (state.timer) { stop(); return; }
    if (state.step === state.detail.trace.steps.length - 1) { state.step = 0; renderStep(); }
    $("step-play").textContent = "暂停";
    state.timer = setInterval(() => {
      state.step++; renderStep(); if (state.step === state.detail.trace.steps.length - 1) stop();
    }, 900);
  });
  try {
    const saved = JSON.parse(sessionStorage.getItem("maxcover-workbench-sources") || "[]");
    if (Array.isArray(saved)) state.selected = new Set(saved.filter((source) => typeof source === "string").slice(0, 4));
  } catch (_) { /* A fresh library remains usable without stored selections. */ }
  library();
})();
