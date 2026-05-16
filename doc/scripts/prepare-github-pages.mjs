#!/usr/bin/env node

import { readdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";

const [siteDir, rawBasePath] = process.argv.slice(2);

if (!siteDir || !rawBasePath) {
  console.error("Usage: prepare-github-pages.mjs <site-dir> <base-path>");
  process.exit(2);
}

const basePath = `/${rawBasePath.replace(/^\/+|\/+$/g, "")}`;
const textExtensions = new Set([
  ".css",
  ".html",
  ".js",
  ".json",
  ".svg",
  ".txt",
  ".xml",
]);

function extname(path) {
  const index = path.lastIndexOf(".");
  return index === -1 ? "" : path.slice(index);
}

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(path);
    } else {
      yield path;
    }
  }
}

function rewrite(text) {
  // GitHub Pages is static-only. Mintlify's export includes pre-rendered HTML,
  // but its runtime expects local server-only props routes that Pages cannot serve.
  const withoutRuntimeScripts = text.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
  const withStaticThemeToggle = withoutRuntimeScripts.replace(
    "</body>",
    `<script data-local-whisper-static-theme>
(function () {
  var key = "local-whisper-docs-theme";
  function applyTheme(theme) {
    var isDark = theme === "dark";
    document.documentElement.classList.toggle("dark", isDark);
    document.documentElement.classList.toggle("light", !isDark);
    document.documentElement.style.colorScheme = isDark ? "dark" : "light";
    try { localStorage.setItem(key, theme); } catch (_) {}
  }
  try {
    var saved = localStorage.getItem(key);
    if (saved === "light" || saved === "dark") applyTheme(saved);
  } catch (_) {}
  document.addEventListener("click", function (event) {
    var target = event.target.closest && event.target.closest('button[aria-label="Toggle dark mode"]');
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    applyTheme(document.documentElement.classList.contains("dark") ? "light" : "dark");
  }, true);
})();
</script></body>`
  );

  return withStaticThemeToggle
    .replaceAll('href="/', `href="${basePath}/`)
    .replaceAll('src="/', `src="${basePath}/`)
    .replaceAll('content="/', `content="${basePath}/`)
    .replaceAll('action="/', `action="${basePath}/`)
    .replaceAll('url(/', `url(${basePath}/`)
    .replaceAll('"/_next/', `"${basePath}/_next/`)
    .replaceAll("'/_next/", `'${basePath}/_next/`)
    .replaceAll('`/_next/', `\`${basePath}/_next/`)
    .replaceAll('\\"/_next/', `\\"${basePath}/_next/`)
    .replaceAll("\\'/_next/", `\\'${basePath}/_next/`)
    .replaceAll('href:\\"/', `href:\\"${basePath}/`)
    .replaceAll('href:"/', `href:"${basePath}/`)
    .replaceAll("href:'/", `href:'${basePath}/`)
    .replaceAll('href: \\"/', `href: \\"${basePath}/`)
    .replaceAll('href: "/', `href: "${basePath}/`)
    .replaceAll("href: '/", `href: '${basePath}/`)
    .replaceAll('c.p="/_next/"', `c.p="${basePath}/_next/"`)
    .replaceAll("c.p='/_next/'", `c.p='${basePath}/_next/'`);
}

let changed = 0;

for await (const path of walk(siteDir)) {
  if (!textExtensions.has(extname(path))) {
    continue;
  }

  const original = await readFile(path, "utf8");
  const updated = rewrite(original);

  if (updated !== original) {
    await writeFile(path, updated);
    changed += 1;
  }
}

await rm(join(siteDir, ".mintignore"), { force: true });

console.log(`Prepared ${changed} exported files for ${basePath}`);
