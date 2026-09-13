/* Read-only presentation of the Markdown constructs emitted by our reports.
 * Build DOM nodes rather than interpreting HTML. Unsupported syntax stays text;
 * the original Markdown is always available separately. No runtime dependency.
 */
(() => {
  "use strict";
  function inline(parent, text) {
    const tokens = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^\s)]+\))/g;
    let start = 0;
    for (const match of text.matchAll(tokens)) {
      parent.append(document.createTextNode(text.slice(start, match.index)));
      const token = match[0];
      if (token.startsWith("`")) {
        const code = document.createElement("code");
        code.textContent = token.slice(1, -1);
        parent.append(code);
      } else if (token.startsWith("**")) {
        const strong = document.createElement("strong");
        strong.textContent = token.slice(2, -2);
        parent.append(strong);
      } else {
        const parts = /^\[([^\]]+)\]\(([^\s)]+)\)$/.exec(token);
        if (/^https?:\/\//i.test(parts[2])) {
          const link = document.createElement("a");
          link.textContent = parts[1];
          link.href = parts[2];
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          parent.append(link);
        } else parent.append(document.createTextNode(token));
      }
      start = match.index + token.length;
    }
    parent.append(document.createTextNode(text.slice(start)));
  }

  function cells(line) {
    const values = [];
    let value = "", code = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === "\\" && line[i + 1] === "|") { value += "|"; i++; }
      else if (char === "`") { code = !code; value += char; }
      else if (char === "|" && !code) { values.push(value.trim()); value = ""; }
      else value += char;
    }
    values.push(value.trim());
    if (line.trim().startsWith("|")) values.shift();
    if (line.trim().endsWith("|")) values.pop();
    return values;
  }

  function render(text) {
    const root = document.createElement("div");
    root.className = "report-body";
    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    for (let i = 0; i < lines.length;) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      if (line.startsWith("```")) {
        const block = [];
        i++;
        while (i < lines.length && !lines[i].startsWith("```")) block.push(lines[i++]);
        if (i < lines.length) i++;
        const pre = document.createElement("pre");
        pre.textContent = block.join("\n");
        root.append(pre);
      } else if (/^#{1,6} /.test(line)) {
        const heading = /^(#{1,6}) (.*)$/.exec(line);
        const node = document.createElement(`h${Math.min(heading[1].length + 1, 6)}`);
        inline(node, heading[2]); root.append(node); i++;
      } else if (line.includes("|") && lines[i + 1]?.includes("|") &&
          cells(lines[i + 1]).every((cell) => /^:?-{3,}:?$/.test(cell))) {
        const table = document.createElement("table");
        const row = (values, tag) => {
          const tr = document.createElement("tr");
          for (const value of values) {
            const cell = document.createElement(tag);
            if (tag === "th") cell.scope = "col";
            inline(cell, value); tr.append(cell);
          }
          return tr;
        };
        const head = table.createTHead();
        head.append(row(cells(line), "th"));
        const body = table.createTBody(); i += 2;
        while (i < lines.length && lines[i].trim() && lines[i].includes("|"))
          body.append(row(cells(lines[i++]), "td"));
        const wrap = document.createElement("div");
        wrap.className = "table-wrap"; wrap.tabIndex = 0;
        wrap.append(table); root.append(wrap);
      } else if (/^\s*(?:[-*] |\d+\. )/.test(line)) {
        const ordered = /^\s*\d+\. /.test(line);
        const list = document.createElement(ordered ? "ol" : "ul");
        const pattern = ordered ? /^\s*\d+\. / : /^\s*[-*] /;
        while (i < lines.length && pattern.test(lines[i])) {
          const item = document.createElement("li");
          inline(item, lines[i++].replace(pattern, "")); list.append(item);
        }
        root.append(list);
      } else {
        const paragraph = document.createElement("p");
        inline(paragraph, line); root.append(paragraph); i++;
      }
    }
    return root;
  }

  function headline(text) {
    // Copy the whole existing section, including its limitations. Never infer claims.
    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    const start = lines.findIndex((line) => line === "## Headline checks");
    if (start < 0) return null;
    let end = start + 1;
    while (end < lines.length && !lines[end].startsWith("## ")) end++;
    return lines.slice(start + 1, end).join("\n").trim() || null;
  }
  window.MaxcoverReport = { render, headline };
})();
