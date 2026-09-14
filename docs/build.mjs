import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import MarkdownIt from 'markdown-it';

const root = path.dirname(fileURLToPath(import.meta.url));
const repository = 'https://github.com/rfxmedia/vueio';
const pages = [
  ['GETTING_STARTED.md', 'get-started.html', 'Get started', 'Installation, first login, and your first review.'],
  ['REVIEW_WORKFLOW.md', 'review.html', 'Review & versions', 'Shots, revisions, annotations, and feedback in context.'],
  ['SHARING.md', 'sharing.html', 'Sharing & delivery', 'Client review links, downloads, and incoming files.'],
  ['STORAGE_OPERATIONS.md', 'storage.html', 'Storage & operations', 'Connect your media. Keep the workspace backed up.'],
  ['TROUBLESHOOTING.md', 'troubleshooting.html', 'Troubleshooting', 'Find the next step when something does not work.'],
  ['FAQ.md', 'faq.html', 'Common questions', 'Free self-hosting, platforms, licensing, and more.'],
  ['SELF_HOSTING.md', 'self-hosting.html', 'Administrator reference', 'The complete installation and maintenance reference.'],
];
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const slug = value => value.toLowerCase().replace(/[^\p{L}\p{N}_\-\s]/gu, '').trim().replace(/\s/g, '-');
const md = new MarkdownIt({ html: false, linkify: false });
md.core.ruler.push('headings', state => {
  const used = new Map();
  state.tokens.forEach((token, i) => {
    if (token.type !== 'heading_open') return;
    const base = slug(state.tokens[i + 1].content);
    const count = used.get(base) ?? 0; used.set(base, count + 1);
    token.attrSet('id', count ? `${base}-${count}` : base);
  });
});
const originalLink = md.renderer.rules.link_open ?? ((tokens, i, options, env, self) => self.renderToken(tokens, i, options));
md.renderer.rules.link_open = (tokens, i, options, env, self) => {
  const href = tokens[i].attrGet('href');
  if (href && !/^(https?:|#)/.test(href)) {
    const [file, anchor] = href.split('#');
    const target = pages.find(p => p[0] === file);
    if (target) tokens[i].attrSet('href', target[1] + (anchor ? `#${anchor}` : ''));
    else if (file === 'README.md') tokens[i].attrSet('href', 'index.html');
    else if (file.endsWith('.md')) tokens[i].attrSet('href', `${repository}/blob/stable/${path.posix.normalize('docs/' + file)}` + (anchor ? `#${anchor}` : ''));
  }
  return originalLink(tokens, i, options, env, self);
};
const nav = (current) => `<nav aria-label="Documentation"><p class="navlabel">EXPLORE VUE.IO</p><a href="index.html" ${current === 'index.html' ? 'aria-current="page"' : ''}>Overview</a><p class="navlabel">THE GUIDES</p>${pages.map(p => `<a href="${p[1]}" ${p[1] === current ? 'aria-current="page"' : ''}>${escape(p[2])}</a>`).join('')}</nav>`;
function shell(title, current, body, toc = [], source = 'README.md') {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><meta name="description" content="Vue.io documentation. A free, self-hosted alternative to Frame.io for review, version history, shot tracking, and delivery."><title>${escape(title)} · Vue.io Docs</title><link rel="stylesheet" href="site.css"><script src="site.js" defer></script></head>
<body><a class="skip" href="#content">Skip to content</a><header class="topbar"><a class="brand" href="index.html" aria-label="Vue.io documentation home"><span>v</span>vue.io</a><span class="divider"></span><span class="toplabel">Documentation</span><div class="toplinks"><span class="tag">PUBLIC ALPHA</span><a class="release-link" href="${repository}/releases">Releases ↗</a><a href="${repository}">GitHub ↗</a><button class="menu-toggle" aria-controls="sidebar" aria-expanded="false" aria-label="Toggle documentation navigation">Menu</button></div></header>
<div class="layout"><aside class="sidebar" id="sidebar"><label class="search-label" for="doc-search">Find an answer</label><input id="doc-search" class="search" type="search" placeholder="Search documentation…" autocomplete="off" aria-controls="search-results"><div class="results" id="search-results" aria-live="polite" hidden></div>${nav(current)}<div class="side-note">Your media. Your storage.<br>Your workflow.<br><br><a href="${repository}/issues">Report an issue ↗</a></div></aside>
<main class="article ${current === 'index.html' ? 'home' : ''}" id="content"><div class="eyebrow">VUE.IO / ${current === 'index.html' ? 'START HERE' : 'DOCUMENTATION'}</div>${body}<footer class="page-footer"><span>Vue.io · Free, self-hosted, source-available.</span><a href="${repository}/blob/stable/docs/${source}">View this guide on GitHub ↗</a></footer></main>
<aside class="on-page" aria-label="On this page"><strong>On this page</strong>${toc.map(t => `<a href="#${escape(t.id)}">${escape(t.label)}</a>`).join('')}<a href="${repository}/releases/latest">Latest release ↗</a></aside></div></body></html>\n`;
}
const search = [];
for (const [file, url, title] of pages) {
  const source = fs.readFileSync(path.join(root, file), 'utf8');
  const tokens = md.parse(source, {});
  const toc = [];
  tokens.forEach((token, i) => { if (token.type === 'heading_open' && token.tag === 'h2') toc.push({ id: token.attrGet('id'), label: tokens[i + 1].content }); });
  const rendered = md.renderer.render(tokens, md.options, {});
  fs.writeFileSync(path.join(root, url), shell(title, url, rendered, toc, file));
  const sections = source.split(/^## /m);
  sections.forEach((section, i) => {
    const heading = i ? section.split('\n')[0] : title;
    search.push({ title: `${title} · ${heading}`, url: url + (i ? '#' + slug(heading) : ''), text: title + ' ' + section });
  });
}
const body = `<h1>From first install<br>to <em>final delivery.</em></h1><p class="lead">A free, self-hosted alternative to Frame.io.<br>Review versions, track shots, and deliver from storage you control.</p><div class="actions"><a class="button" href="get-started.html">Get started <span aria-hidden="true">↗</span></a><a class="button secondary" href="review.html">Explore the workflow</a></div><div class="boundary"><strong>Public alpha.</strong> Linux is the primary host platform. Apple Silicon is experimental; native Windows is not supported. Start with trusted users and test media. <a href="${repository}/releases/latest">Read the release notes ↗</a></div><figure class="feature-visual"><a href="assets/tracker.png"><img src="assets/tracker.png" width="1920" height="1355" alt="Vue.io's LOW TIDE demo: shot versions, status, assignments, briefs, and latest notes in one tracker."></a></figure><p class="caption">Actual Vue.io interface. LOW TIDE is a fictional project with synthetic media and team profiles.</p><div class="section-head" id="guides"><h2>One workflow. Clear next steps.</h2><span>THE ESSENTIAL GUIDES</span></div><div class="guide-grid">${pages.slice(0,6).map((p,i) => `<a class="guide" href="${p[1]}"><span class="number">0${i+1} /</span><h3>${escape(p[2])} ↗</h3><p>${escape(p[3])}</p></a>`).join('')}</div><h2 id="your-infrastructure">Keep the media where it belongs.</h2><p>Selected local drives and mounted network storage become part of your review workspace. You manage the host and backups; teammates and clients work in their browsers.</p><img src="assets/storage-flow.svg" width="1400" height="370" alt="Selected storage connects to your Vue.io host, then to browser-based reviewers through your configured HTTPS connection."><p><a href="self-hosting.html">Open the complete administrator reference →</a></p>`;
fs.writeFileSync(path.join(root, 'index.html'), shell('Overview', 'index.html', body, [{id:'guides',label:'The essential guides'},{id:'your-infrastructure',label:'Your infrastructure'}]));
fs.writeFileSync(path.join(root, 'search.json'), JSON.stringify(search));
console.log(`Built ${pages.length + 1} static pages and ${search.length} searchable sections.`);
