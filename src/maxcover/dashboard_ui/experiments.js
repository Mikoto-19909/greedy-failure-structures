(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { config: null, busy: false, basicsDirty: false, textDirty: false,
    guidedDirty: false, formStale: false, guided: null, version: 0, checked: -1, request: 0 };
  const guidedKeys = ["universe_size", "set_count", "k", "density"];
  const algorithmLabels = { greedy: "贪心", lazy_greedy: "惰性贪心", brute_force: "穷举参考" };
  const el = (tag, text) => { const node = document.createElement(tag); node.textContent = text; return node; };
  function message(text = "", error = false) { $("config-message").textContent = text; $("config-message").className = error ? "error" : ""; }
  async function api(route, payload) {
    const response = await fetch(`/api/experiments/${route}`, payload === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(`${response.status === 409 ? "保存冲突：" : ""}${data.error || "请求失败"}`);
    return data;
  }
  function controls() {
    const editable = state.config?.editable;
    for (const name of ["select", "refresh", "reload", "copy", "preview", "apply", "save"]) {
      $("config-" + name).disabled = state.busy || (!["select", "refresh"].includes(name) && !state.config)
        || (["apply", "save"].includes(name) && !editable)
        || (["save", "preview"].includes(name) && (state.basicsDirty || state.guidedDirty))
        || (name === "apply" && state.formStale)
        || (name === "save" && state.checked !== state.version)
        || (name === "copy" && dirty());
    }
    for (const name of ["name", "seed", "repetitions"]) $("config-" + name).disabled = state.busy || !editable || state.formStale;
    $("config-text").disabled = state.busy || !editable || state.basicsDirty || state.guidedDirty;
    $("guided-fields").disabled = state.busy || !editable || !state.guided?.supported || state.formStale;
    const canRun = !state.busy && !dirty() && state.config?.valid && state.checked === state.version;
    $("config-run").setAttribute("aria-disabled", String(!canRun));
    $("config-run").tabIndex = canRun ? 0 : -1;
    if (canRun) $("config-run").href = '/research?' + new URLSearchParams({ config: state.config.path, config_hash: state.config.config_hash });
    else $("config-run").removeAttribute("href");
  }
  function dirty() { return state.basicsDirty || state.guidedDirty || state.textDirty; }
  function edited() {
    state.version++; state.request++; state.checked = -1; controls();
    $("config-plan").textContent = "当前修改尚未检查。";
  }
  function current(request, version = state.version) { return request === state.request && version === state.version; }
  async function action(task) {
    if (state.busy) return;
    const request = ++state.request;
    state.busy = true; controls(); message("正在处理…");
    try { await task(request); } catch (error) { if (current(request)) message(error.message, true); }
    finally { state.busy = false; controls(); }
  }
  function diffs(id, items) {
    $(id).replaceChildren();
    if (!items?.length) { $(id).append(el("p", "没有参数差异。")); return; }
    for (const item of items) {
      const row = el("div", ""); row.className = "config-diff";
      row.append(el("h4", item.path), el("pre", `原值：${item.before}`), el("pre", `新值：${item.after}`)); $(id).append(row);
    }
  }
  function preview(data) {
    $("config-plan").textContent = data.valid
      ? `${data.plan.case_ids.length} 个案例 · ${data.plan.repetitions} 次重复 · ${data.plan.instance_count} 个实例 · ${data.plan.algorithm_run_count} 次算法运行`
      : `配置无效：${data.error}`;
    $("config-warnings").textContent = (data.warnings || []).join("\n");
    diffs("config-changes", data.changes); diffs("config-origin-changes", data.origin_changes);
  }
  function basics(data) {
    $("config-name").value = data.basics?.name || "";
    $("config-seed").value = data.basics?.base_seed || "";
    $("config-repetitions").value = data.basics?.repetitions || "";
    state.basicsDirty = false;
  }
  function guided(data) {
    state.guided = data || { supported: false, reason: "请先修正并检查完整配置。" };
    $("guided-reason").textContent = state.guided.reason;
    for (const key of guidedKeys) $("guided-" + key).value = state.guided.case?.[key] || "";
    $("guided-algorithms").replaceChildren();
    for (const item of state.guided.algorithms || []) {
      const label = el("label", ""), input = document.createElement("input");
      input.type = "checkbox"; input.checked = item.enabled;
      input.addEventListener("change", () => { state.guidedDirty = true; edited(); message("算法选择已修改，请应用表单并检查。"); });
      label.append(input, document.createTextNode(`${algorithmLabels[item.name]} · ${item.id}`));
      $("guided-algorithms").append(label);
    }
  }
  function render(data) {
    state.config = data; state.textDirty = false; state.guidedDirty = false; state.formStale = false;
    state.version++; state.checked = data.valid ? state.version : -1;
    $("config-editor").hidden = false; $("config-select").value = data.path;
    $("config-source").textContent = `configs/${data.path}${data.origin_source ? ` · 复制自 ${data.origin_source}` : ""}`;
    $("config-permission").textContent = data.editable
      ? "此副本可以编辑；保存后，已排队任务继续使用提交时冻结的配置。"
      : "这是已有模板。点击“复制为本地配置”后即可编辑，新副本使用独立文件名。";
    $("config-text").value = data.text; basics(data); guided(data.guided); preview(data);
    controls();
  }
  async function list(selected, request) {
    const response = await fetch("/api/configs"); const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法读取配置列表");
    if (!current(request)) return;
    $("config-select").replaceChildren(new Option("选择一个模板或本地副本", ""),
      ...data.configs.map((item) => new Option(item.path, item.path)));
    if (selected) $("config-select").value = selected;
  }
  async function load(path, request) {
    if (!path) {
      state.config = null; state.basicsDirty = false; state.guidedDirty = false; state.textDirty = false;
      state.formStale = false; state.checked = -1; $("config-editor").hidden = true; message(); return;
    }
    const data = await api(`config?${new URLSearchParams({ path })}`);
    if (!current(request)) return;
    render(data);
    if (data.valid) {
      const version = state.version, result = await api("config-preview", { text: data.text, base_path: data.path });
      if (!current(request, version)) return;
      preview(result);
      message(data.editable ? "已载入本地配置。" : "已载入模板；可复制后修改。");
    } else message(data.error, true);
  }
  $("config-select").addEventListener("change", () => {
    if (dirty() && !window.confirm("当前修改尚未保存，是否放弃修改并切换配置？")) {
      $("config-select").value = state.config.path; return;
    }
    action((request) => load($("config-select").value, request));
  });
  $("config-refresh").addEventListener("click", () => action(async (request) => {
    await list(state.config?.path, request); if (current(request)) message("列表已刷新，当前编辑内容保留。");
  }));
  $("config-reload").addEventListener("click", () => action((request) => load(state.config.path, request)));
  $("config-copy").addEventListener("click", () => action(async (request) => {
    const data = await api("config-copy", { source: state.config.path, expected_revision: state.config.revision });
    if (!current(request)) return;
    await list(data.path, request);
    if (!current(request)) return;
    render(data); message("已创建独立本地配置，可编辑后保存。");
  }));
  for (const name of ["name", "seed", "repetitions"]) $("config-" + name).addEventListener("input", () => {
    state.basicsDirty = true; edited(); message("基本参数已修改，请应用表单并检查。");
  });
  for (const key of guidedKeys) $("guided-" + key).addEventListener("input", () => {
    state.guidedDirty = true; edited(); message("数据参数已修改，请应用表单并检查。");
  });
  $("config-text").addEventListener("input", () => { state.textDirty = true; state.formStale = true; edited(); message("JSON 已修改；先检查完整配置，再继续表单编辑。"); });
  async function inspect(applyBasics, request) {
    const version = state.version;
    const payload = { text: $("config-text").value, base_path: state.config.path };
    if (applyBasics) payload.basics = { name: $("config-name").value, base_seed: $("config-seed").value, repetitions: $("config-repetitions").value };
    if (applyBasics && state.guidedDirty) payload.guided = {
      case: Object.fromEntries(guidedKeys.map((key) => [key, $("guided-" + key).value])),
      enabled: [...$("guided-algorithms").querySelectorAll("input")].map((input) => input.checked)
    };
    const data = await api("config-preview", payload);
    if (!current(request, version)) return;
    if (applyBasics) { $("config-text").value = data.text; state.textDirty = true; }
    state.guidedDirty = false; state.formStale = false; state.checked = state.version;
    basics(data); guided(data.guided); preview(data); message("校验通过；预览不运行实验。");
  }
  $("config-apply").addEventListener("click", () => action((request) => inspect(true, request)));
  $("config-preview").addEventListener("click", () => action((request) => inspect(false, request)));
  $("config-save").addEventListener("click", () => action(async (request) => {
    if (state.checked !== state.version || state.basicsDirty || state.guidedDirty) return;
    const data = await api("config-save", { path: state.config.path, text: $("config-text").value, expected_revision: state.config.revision });
    if (!current(request)) return;
    render(data);
    const version = state.version, result = await api("config-preview", { text: data.text, base_path: data.path });
    if (!current(request, version)) return;
    preview(result); message("本地配置已保存，可到运行中心排队。");
  }));
  $("config-run").addEventListener("click", (event) => { if ($("config-run").getAttribute("aria-disabled") === "true") event.preventDefault(); });
  window.addEventListener("beforeunload", (event) => { if (dirty()) { event.preventDefault(); event.returnValue = ""; } });
  action(async (request) => {
    const path = new URLSearchParams(location.search).get("config"); await list(path, request);
    if (!current(request)) return;
    if (path) await load(path, request); else message("先选择一个模板；复制、编辑与预览均在本地进行。");
  });
})();
