import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { app, BrowserWindow, dialog, protocol } from "electron";

const scheme = "tactical-board";
const boardUrl = `${scheme}://app/`;
const webFiles = new Map([
  ["/index.html", "text/html"],
  ["/styles.css", "text/css"],
  ["/app.js", "text/javascript"],
  ["/state.js", "text/javascript"],
  ["/board-svg.js", "text/javascript"],
  ["/teams.json", "application/json"],
]);
const contentPolicy = "default-src 'self'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'";
const shutdown = new AbortController();

protocol.registerSchemesAsPrivileged([
  { scheme, privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

function runMatchBackend(url) {
  const root = app.getAppPath();
  const backendName = process.platform === "win32" ? "match_backend.exe" : "match_backend";
  const executable = app.isPackaged
    ? path.join(process.resourcesPath, "match-backend", backendName)
    : process.env.TACTICAL_BOARD_PYTHON || "python";
  const args = app.isPackaged ? [] : [path.join(root, "desktop", "match_backend.py")];

  return new Promise((resolve, reject) => {
    const child = execFile(executable, args, {
      windowsHide: true,
      timeout: 30_000,
      maxBuffer: 1024 * 1024,
      signal: shutdown.signal,
    }, (error, stdout, stderr) => {
      if (error) {
        reject(error);
        return;
      }
      if (stderr) console.warn(stderr.trim());
      resolve(stdout);
    });
    // A process that could not start or timed out may close its input early.
    child.stdin.on("error", () => {});
    child.stdin.end(url, "utf8");
  });
}

async function matchResponse(target) {
  const headers = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
  const urls = target.searchParams.getAll("url");
  if (target.search.length > 4097) {
    return Response.json({ error: "Match link is too long." }, { status: 414, headers });
  }
  if (urls.length !== 1 || target.searchParams.size !== 1) {
    return Response.json({ error: "Provide exactly one Zerozero match URL." }, { status: 400, headers });
  }
  try {
    const { status, body } = JSON.parse(await runMatchBackend(urls[0]));
    return Response.json(body, { status, headers });
  } catch (error) {
    console.error("Match importer failed:", error);
    return Response.json({ error: "The desktop match importer could not complete the request." }, {
      status: 502, headers,
    });
  }
}

async function serveBoard(request) {
  const target = new URL(request.url);
  if (target.host !== "app" || target.username || target.password) {
    return new Response(null, { status: 404 });
  }
  if (request.method !== "GET") return new Response(null, { status: 405 });
  if (target.pathname === "/api/match") return matchResponse(target);

  const file = target.pathname === "/" ? "/index.html" : target.pathname;
  const contentType = webFiles.get(file);
  if (!contentType) return new Response(null, { status: 404 });

  const contents = await readFile(path.join(app.getAppPath(), "web", file.slice(1)));
  return new Response(contents, {
    headers: {
      "Content-Type": `${contentType}; charset=utf-8`,
      "Content-Security-Policy": contentPolicy,
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function openBoard() {
  const window = new BrowserWindow({
    width: 1320,
    height: 920,
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    if (url !== boardUrl) event.preventDefault();
  });
  window.loadURL(boardUrl).catch(error => {
    console.error(error);
    dialog.showErrorBox("Football Tactical Board", "The board could not open. Try reinstalling the app.");
    app.quit();
  });
}

app.whenReady().then(() => {
  protocol.handle(scheme, serveBoard);
  openBoard();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) openBoard();
  });
});

app.on("before-quit", () => shutdown.abort());
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
