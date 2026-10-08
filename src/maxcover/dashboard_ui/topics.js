/* Shared topic cards and navigation. Topic data does not configure experiments. */
(() => {
  'use strict';
  const text = {
    zh: {
      title: '研究与实验工作台', local: '本地工作台', kicker: '研究专题与平台案例',
      heading: '从一个研究问题开始', intro: '选择专题，阅读已有成果，再进入对应的实验与回放工具。',
      note: '进入专题不会启动计算。每项研究保留自己的评价指标与核验方法。',
      topics: '选择研究入口', footer: '最大覆盖研究及其可复现实验平台',
      home: '研究首页', switch: '切换专题', enter: '进入专题', count: '个研究入口',
      error: '研究入口暂时无法读取，请刷新页面重试。', loading: '正在读取研究入口…', empty: '暂无研究入口。',
    },
    en: {
      title: 'Research Workspace', local: 'Local workspace', kicker: 'Research and platform cases',
      heading: 'Start with a research question', intro: 'Choose a study, read its results, then explore its experiment and replay tools.',
      note: 'Opening a study starts no computation. Each study keeps its own metrics and verification methods.',
      topics: 'Choose a study', footer: 'Maximum Coverage research and its reproducible experiment platform',
      home: 'Research home', switch: 'Switch study', enter: 'Open study', count: 'research entries',
      error: 'Research entries could not be loaded. Refresh the page to retry.', loading: 'Loading research entries…', empty: 'No research entries yet.',
    },
  };
  let language = 'zh', topics = [], failed = false, loaded = false;
  try { language = localStorage.getItem('maxcover-language') === 'en' ? 'en' : 'zh'; } catch (_) { /* Optional preference. */ }
  const make = (tag, value, className) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  const local = value => value[language] || value.zh;
  function render() {
    const labels = text[language];
    if (document.body.hasAttribute('data-topic-home')) {
      document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
      document.title = labels.title;
    }
    document.querySelectorAll('[data-topic-text]').forEach(node => { node.textContent = labels[node.dataset.topicText]; });
    document.querySelectorAll('[data-topic-language]').forEach(button => {
      const selected = button.dataset.topicLanguage === language;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    document.querySelectorAll('[data-topic-count]').forEach(node => { node.textContent = topics.length ? `${topics.length} ${labels.count}` : ''; });
    document.querySelectorAll('[data-topic-message]').forEach(node => {
      node.textContent = failed ? labels.error : !loaded ? labels.loading : topics.length ? '' : labels.empty;
      node.classList.toggle('error', failed);
      node.hidden = !failed && topics.length > 0;
    });
    document.querySelectorAll('[data-topic-cards]').forEach(container => {
      container.replaceChildren(...topics.map(topic => {
        const card = make('article', undefined, 'topic-card');
        const header = make('div', undefined, 'topic-card-header');
        const mark = make('span', topic.mark, 'brand-mark'); mark.setAttribute('aria-hidden', 'true');
        header.append(mark, make('span', local(topic.role), 'section-kicker'));
        const features = make('ul', undefined, 'topic-features');
        features.append(...local(topic.features).map(feature => make('li', feature)));
        const link = make('a', `${labels.enter} →`, 'button button-primary');
        link.href = topic.href; link.setAttribute('aria-label', `${labels.enter} · ${local(topic.title)}`);
        card.append(header, make('h3', local(topic.title)), make('p', local(topic.summary), 'topic-card-summary'), features, link);
        return card;
      }));
    });
    document.querySelectorAll('[data-topic-nav]').forEach(nav => {
      nav.classList.add('topic-nav'); nav.setAttribute('aria-label', labels.switch);
      const home = make('a', `← ${labels.home}`, 'topic-home-link'); home.href = '/';
      nav.replaceChildren(home);
      if (!topics.length) return;
      const label = make('label', undefined, 'topic-switch-label');
      const select = make('select'); select.setAttribute('aria-label', labels.switch);
      topics.forEach(topic => {
        const option = make('option', local(topic.title)); option.value = topic.id;
        option.selected = topic.id === nav.dataset.topicCurrent; select.append(option);
      });
      select.addEventListener('change', () => {
        const topic = topics.find(item => item.id === select.value);
        if (topic) window.location.assign(topic.href);
      });
      label.append(make('span', labels.switch), select); nav.append(label);
    });
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-topic-language], [data-language]');
    if (!button) return;
    language = (button.dataset.topicLanguage || button.dataset.language) === 'en' ? 'en' : 'zh';
    try { localStorage.setItem('maxcover-language', language); } catch (_) { /* Optional preference. */ }
    render();
  });
  render();
  fetch('/topics.json').then(response => {
    if (!response.ok) throw new Error('Topic list unavailable');
    return response.json();
  }).then(data => { topics = data; loaded = true; render(); }).catch(() => { topics = []; failed = true; render(); });
})();
