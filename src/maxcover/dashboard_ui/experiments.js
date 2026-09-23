(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { config: null, busy: false, basicsDirty: false, textDirty: false };
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
        || (["apply", "save"].includes(name) && !editable) || (["save", "preview"].includes(name) && state.basicsDirty)
        || (name === "copy" && (state.basicsDirty || state.textDirty));
    }
    for (const name of ["name", "seed", "repetitions", "text"]) $("config-" + name).disabled = state.busy || !editable;
  }
  async function action(task) {
    if (state.busy) return;
    state.busy = true; controls(); message("正在处理…");
    try { await task(); } catch (error) { message(error.message, true); }
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
  function render(data) {
    state.config = data; state.textDirty = false;
    $("config-editor").hidden = false; $("config-select").value = data.path;
    $("config-source").textContent = `configs/${data.path}${data.origin_source ? ` · 复制自 ${data.origin_source}` : ""}`;
    $("config-permission").textContent = data.editable
      ? "此副本可以编辑；保存后，已排队任务继续使用提交时冻结的配置。"
      : "这是已有模板。点击“复制为本地配置”后即可编辑，新副本使用独立文件名。";
    $("config-text").value = data.text; basics(data); preview(data);
    $("config-run").href = `/research?config=${encodeURIComponent(data.path)}`;
    controls();
  }
  async function list(selected) {
    const response = await fetch("/api/configs"); const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法读取配置列表");
    $("config-select").replaceChildren(new Option("选择一个模板或本地副本", ""),
      ...data.configs.map((item) => new Option(item.path, item.path)));
    if (selected) $("config-select").value = selected;
  }
  async function load(path) {
    if (!path) { state.config = null; $("config-editor").hidden = true; message(); return; }
    const data = await api(`config?${new URLSearchParams({ path })}`); render(data);
    if (data.valid) {
      preview(await api("config-preview", { text: data.text, base_path: data.path }));
      message(data.editable ? "已载入本地配置。" : "已载入模板；可复制后修改。");
    } else message(data.error, true);
  }
  $("config-select").addEventListener("change", () => {
    if ((state.basicsDirty || state.textDirty) && !window.confirm("当前修改尚未保存，是否放弃修改并切换配置？")) {
      $("config-select").value = state.config.path; return;
    }
    action(() => load($("config-select").value));
  });
  $("config-refresh").addEventListener("click", () => action(async () => { await list(state.config?.path); message("列表已刷新，当前编辑内容保留。"); }));
  $("config-reload").addEventListener("click", () => action(() => load(state.config.path)));
  $("config-copy").addEventListener("click", () => action(async () => {
    const data = await api("config-copy", { source: state.config.path, expected_revision: state.config.revision });
    await list(data.path); render(data); message("已创建独立本地配置，可编辑后保存。");
  }));
  for (const name of ["name", "seed", "repetitions"]) $("config-" + name).addEventListener("input", () => {
    state.basicsDirty = true; controls(); message("基本参数尚未应用，请点击“应用基本参数并预览”。");
  });
  $("config-text").addEventListener("input", () => { state.textDirty = true; controls(); message("JSON 已修改；预览与差异需要重新校验。"); $("config-plan").textContent = "待校验当前 JSON。"; });
  async function inspect(applyBasics) {
    const payload = { text: $("config-text").value, base_path: state.config.path };
    if (applyBasics) payload.basics = { name: $("config-name").value, base_seed: $("config-seed").value, repetitions: $("config-repetitions").value };
    const data = await api("config-preview", payload);
    if (applyBasics) { $("config-text").value = data.text; state.textDirty = true; }
    basics(data); preview(data); message("校验通过；预览不运行实验。");
  }
  $("config-apply").addEventListener("click", () => action(() => inspect(true)));
  $("config-preview").addEventListener("click", () => action(() => inspect(false)));
  $("config-save").addEventListener("click", () => action(async () => {
    const data = await api("config-save", { path: state.config.path, text: $("config-text").value, expected_revision: state.config.revision });
    render(data); preview(await api("config-preview", { text: data.text, base_path: data.path })); message("本地配置已保存，可到运行中心排队。");
  }));
  window.addEventListener("beforeunload", (event) => { if (state.basicsDirty || state.textDirty) { event.preventDefault(); event.returnValue = ""; } });
  action(async () => {
    const path = new URLSearchParams(location.search).get("config"); await list(path);
    if (path) await load(path); else message("先选择一个模板；复制、编辑与预览均在本地进行。");
  });
})();
