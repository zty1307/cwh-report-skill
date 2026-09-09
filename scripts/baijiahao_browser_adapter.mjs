#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright-core');
const HERE = path.dirname(fileURLToPath(import.meta.url));

function argValues(name) {
  const values = [];
  for (let i = 2; i < process.argv.length; i += 1) {
    if (process.argv[i] === name && process.argv[i + 1]) values.push(process.argv[++i]);
    else if (process.argv[i].startsWith(`${name}=`)) values.push(process.argv[i].slice(name.length + 1));
  }
  return values;
}

function argValue(name, fallback = '') {
  const values = argValues(name);
  return values.length ? values[values.length - 1] : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function nowIso() {
  return new Date().toISOString();
}

function safeName(value) {
  return String(value || 'query').replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 80);
}

function findBrowser() {
  const candidates = [
    process.env.CWH_BROWSER,
    process.env.WSW_BROWSER,
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/microsoft-edge',
    '/usr/bin/microsoft-edge-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || '';
}

function defaultProfileDir() {
  if (process.env.CWH_BAIJIAHAO_PROFILE_DIR) return path.resolve(process.env.CWH_BAIJIAHAO_PROFILE_DIR);
  if (process.platform === 'win32') {
    return path.join(process.env.LOCALAPPDATA || os.homedir(), 'cwh-report-skill', 'baijiahao-browser-profile');
  }
  return path.join(process.env.XDG_STATE_HOME || path.join(os.homedir(), '.local', 'state'), 'cwh-report-skill', 'baijiahao-browser-profile');
}

function isCaptchaUrl(url) {
  return /wappass\.baidu\.com\/static\/captcha|captcha|verify|security-check|passport\.baidu\.com/i.test(url || '');
}

async function pageHasCaptcha(page) {
  if (isCaptchaUrl(page.url())) return true;
  const text = await page.locator('body').innerText({ timeout: 3000 }).catch(() => '');
  return /安全验证|请输入验证码|完成验证|拖动滑块|访问异常|网络不给力，请稍后重试/.test(text);
}

async function saveCheckpoint(page, outDir, queryId, phase) {
  const stem = `${queryId}_${phase}_${Date.now()}`;
  const screenshot = path.join(outDir, `${stem}.png`);
  const html = path.join(outDir, `${stem}.html`);
  await page.screenshot({ path: screenshot, fullPage: true }).catch(() => {});
  fs.writeFileSync(html, await page.content().catch(() => ''), 'utf8');
  const checkpoint = {
    status: 'waiting_login',
    terminal: false,
    resume_required: true,
    query_id: queryId,
    phase,
    url: page.url(),
    screenshot,
    html,
    created_at: nowIso(),
    next_action: '在同一浏览器配置目录中完成百度验证码或登录，然后使用相同命令重新运行。',
  };
  const checkpointPath = path.join(outDir, 'checkpoint.json');
  fs.writeFileSync(checkpointPath, JSON.stringify(checkpoint, null, 2), 'utf8');
  return { ...checkpoint, checkpoint: checkpointPath };
}

async function waitForHuman(page, seconds) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    if (!(await pageHasCaptcha(page))) return true;
    await page.waitForTimeout(1500);
  }
  return false;
}

async function handleCaptcha(page, outDir, queryId, phase, waitSeconds) {
  if (!(await pageHasCaptcha(page))) return null;
  const checkpoint = await saveCheckpoint(page, outDir, queryId, phase);
  if (waitSeconds > 0 && await waitForHuman(page, waitSeconds)) {
    return { ...checkpoint, status: 'resumed_after_human_verification', resume_required: false };
  }
  return checkpoint;
}

async function extractSearchResults(page, limit) {
  return page.evaluate((maxResults) => {
    const rows = [];
    const seen = new Set();
    const selectors = ['#content_left .c-container', '#content_left .result', '.result-op', 'main .result'];
    const containers = Array.from(document.querySelectorAll(selectors.join(',')));
    for (const container of containers) {
      const anchor = container.querySelector('h3 a, a[href]');
      if (!anchor || !anchor.href) continue;
      const title = (anchor.textContent || '').trim();
      if (!title || seen.has(anchor.href)) continue;
      const snippet = (container.innerText || '').trim().slice(0, 1000);
      seen.add(anchor.href);
      rows.push({ title, search_result_url: anchor.href, snippet });
      if (rows.length >= maxResults) break;
    }
    return rows;
  }, limit);
}

async function extractArticle(page) {
  return page.evaluate(() => {
    const meta = (selector) => document.querySelector(selector)?.getAttribute('content')?.trim() || '';
    const text = (selectors) => {
      for (const selector of selectors) {
        const value = document.querySelector(selector)?.textContent?.trim();
        if (value) return value;
      }
      return '';
    };
    const body = text(['article', '.article-content', '.mainContent', '.content', '#article', 'main']) || document.body?.innerText || '';
    const publishedText = meta('meta[property="article:published_time"]')
      || meta('meta[name="publishdate"]')
      || meta('meta[name="date"]')
      || text(['.date', '.time', '.publish-time', '.article-time']);
    return {
      title: meta('meta[property="og:title"]') || text(['h1', '.article-title', '.title']) || document.title,
      creator: meta('meta[name="author"]') || text(['.author-name', '.author', '.account-name', '.source']),
      published_at_source_text: publishedText,
      content: body.replace(/\s+/g, ' ').trim().slice(0, 30000),
    };
  });
}

async function openArticle(context, result, outDir, queryId, waitSeconds) {
  const page = await context.newPage();
  try {
    const response = await page.goto(result.search_result_url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
    await page.waitForTimeout(1200);
    const captcha = await handleCaptcha(page, outDir, queryId, 'article', waitSeconds);
    if (captcha && captcha.status === 'waiting_login') {
      return { ...result, status: 'waiting_login', blocker: 'baidu_captcha_or_login', checkpoint: captcha };
    }
    const finalUrl = page.url();
    const article = await extractArticle(page);
    const isBaijiahao = /(^|\.)baijiahao\.baidu\.com$|(^|\.)mbd\.baidu\.com$/i.test(new URL(finalUrl).hostname);
    const contentUsable = article.content.length >= 120;
    return {
      ...result,
      status: isBaijiahao && contentUsable ? 'verified' : 'excluded',
      decision_reason: isBaijiahao ? (contentUsable ? 'original_page_opened_and_body_extracted' : 'article_body_too_short') : 'redirected_outside_baijiahao',
      url: finalUrl,
      http_status: response?.status() || null,
      source: article.creator,
      title: article.title || result.title,
      published_at_source_text: article.published_at_source_text,
      published_at_verified_from_source: Boolean(article.published_at_source_text),
      content: article.content,
    };
  } catch (error) {
    return { ...result, status: 'access_failed', blocker: String(error?.message || error), url: page.url() };
  } finally {
    await page.close().catch(() => {});
  }
}

function loadQueries() {
  const direct = argValues('--query');
  const file = argValue('--queries-file');
  if (!file) return direct;
  const payload = JSON.parse(fs.readFileSync(path.resolve(file), 'utf8'));
  const rows = Array.isArray(payload) ? payload : payload.queries;
  return direct.concat((rows || []).map((row) => typeof row === 'string' ? row : row.query).filter(Boolean));
}

async function main() {
  const queries = loadQueries();
  if (!queries.length) throw new Error('至少提供一个 --query 或 --queries-file');
  const outDir = path.resolve(argValue('--out-dir', path.join(process.cwd(), 'baijiahao_research')));
  const profileDir = path.resolve(argValue('--profile-dir', defaultProfileDir()));
  const maxResults = Math.max(1, Number(argValue('--max-results', '10')) || 10);
  const waitSeconds = Math.max(0, Number(argValue('--wait-for-human-seconds', '0')) || 0);
  const headless = hasFlag('--headless');
  fs.mkdirSync(outDir, { recursive: true });
  fs.mkdirSync(profileDir, { recursive: true });
  const browserPath = findBrowser();
  if (!browserPath) throw new Error('未找到 Edge/Chrome；可用 CWH_BROWSER 指定浏览器路径');

  const context = await chromium.launchPersistentContext(profileDir, {
    executablePath: browserPath,
    headless,
    viewport: { width: 1440, height: 1000 },
    args: ['--no-first-run', '--no-default-browser-check'],
  });
  const audit = {
    schema_version: '1.0',
    platform: 'baijiahao',
    execution_mode: 'browser_platform_search',
    started_at: nowIso(),
    browser: browserPath,
    headless,
    profile_dir: profileDir,
    waiting_login_terminal: false,
    executions: [],
    candidates: [],
  };
  try {
    for (let index = 0; index < queries.length; index += 1) {
      const query = queries[index];
      const queryId = `baijiahao-q${index + 1}`;
      const page = await context.newPage();
      const startedAt = nowIso();
      const execution = { query_id: queryId, query, backend: 'baidu_visible_browser', route: 'public_platform', started_at: startedAt };
      try {
        const searchQuery = `site:baijiahao.baidu.com ${query}`;
        const searchUrl = `https://www.baidu.com/s?wd=${encodeURIComponent(searchQuery)}`;
        await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(1200);
        const captcha = await handleCaptcha(page, outDir, queryId, 'search', waitSeconds);
        if (captcha && captcha.status === 'waiting_login') {
          Object.assign(execution, { status: 'waiting_login', terminal: false, blocker: 'baidu_captcha_or_login', checkpoint: captcha, result_count: 0, result_urls: [] });
          audit.executions.push(execution);
          continue;
        }
        const results = await extractSearchResults(page, maxResults);
        const candidates = [];
        for (const result of results) candidates.push(await openArticle(context, result, outDir, queryId, waitSeconds));
        audit.candidates.push(...candidates.map((candidate, candidateIndex) => ({ ...candidate, candidate_id: `${queryId}-${candidateIndex + 1}`, discovery_query_id: queryId })));
        const verified = candidates.filter((candidate) => candidate.status === 'verified');
        const waiting = candidates.filter((candidate) => candidate.status === 'waiting_login');
        Object.assign(execution, {
          status: waiting.length ? 'waiting_login' : 'completed',
          terminal: false,
          result_count: results.length,
          result_urls: results.map((result) => result.search_result_url),
          verified_count: verified.length,
          verified_urls: verified.map((candidate) => candidate.url),
          blocker: waiting.length ? 'baidu_captcha_or_login_during_article_verification' : '',
        });
      } catch (error) {
        Object.assign(execution, { status: 'access_failed', terminal: false, blocker: String(error?.message || error), result_count: 0, result_urls: [] });
      } finally {
        execution.finished_at = nowIso();
        if (!audit.executions.includes(execution)) audit.executions.push(execution);
        await page.close().catch(() => {});
      }
    }
  } finally {
    await context.close().catch(() => {});
  }
  const waiting = audit.executions.some((row) => row.status === 'waiting_login') || audit.candidates.some((row) => row.status === 'waiting_login');
  const verified = audit.candidates.filter((row) => row.status === 'verified').length;
  audit.status = waiting ? 'partial_waiting_login' : 'completed';
  audit.terminal = false;
  audit.resume_required = waiting;
  audit.verified_candidates = verified;
  audit.finished_at = nowIso();
  const output = path.join(outDir, 'baijiahao_browser_audit.json');
  fs.writeFileSync(output, JSON.stringify(audit, null, 2), 'utf8');
  console.log(JSON.stringify({ status: audit.status, verified_candidates: verified, output }, null, 2));
  process.exitCode = waiting ? 2 : 0;
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
