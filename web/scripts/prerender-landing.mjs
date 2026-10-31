import { copyFile, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

/** Replaces the landing outlet in Vite's HTML template with the static landing markup. */
const webRoot = process.cwd();
const distRoot = resolve(webRoot, "dist");
const templatePath = resolve(distRoot, "index.html");
const appHtmlPath = resolve(distRoot, "app.html");
const serverEntryPath = resolve(
  webRoot,
  ".landing-ssr",
  "landing-server.js",
);
const outlet = "<!--landing-outlet-->";

const template = await readFile(templatePath, "utf8");

if (!template.includes(outlet)) {
  throw new Error("Landing outlet was not found in dist/index.html.");
}

// Keep an empty-root variant for authenticated application routes.
await copyFile(templatePath, appHtmlPath);

const { renderLanding } = await import(pathToFileURL(serverEntryPath).href);
const renderedLanding = renderLanding();

// React 19 prefixes server-rendered images with preload links. Keep those
// resource hints in the document head; leaving them inside #root makes the
// browser hydration tree differ from the client-rendered landing component.
const preloadMatch = renderedLanding.match(/^(?:<link rel="preload"[^>]*>)+/);
const preloads = preloadMatch?.[0] ?? "";
const landingMarkup = renderedLanding.slice(preloads.length);
const landingHtml = template
  .replace("</head>", `${preloads}</head>`)
  .replace(outlet, landingMarkup);

await writeFile(templatePath, landingHtml, "utf8");
