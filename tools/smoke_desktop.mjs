import { strict as assert } from "node:assert";
import { spawn } from "node:child_process";
import { access, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const appUrl = "tactical-board://app/";
const commandTimeout = 20_000;

async function waitFor(probe, description) {
  const deadline = Date.now() + commandTimeout;
  do {
    const result = await probe();
    if (result) return result;
    await delay(100);
  } while (Date.now() < deadline);
  throw new Error(`Timed out waiting for ${description}.`);
}

async function runDesktop(executable, profile, check) {
  const child = spawn(executable, ["--remote-debugging-pipe", `--user-data-dir=${profile}`], {
    stdio: ["ignore", "ignore", "inherit", "pipe", "pipe"],
  });
  const [, , , pipeIn, pipeOut] = child.stdio;
  const pending = new Map();
  let nextId = 0;
  let buffered = "";

  function rejectPending(error) {
    for (const reply of pending.values()) reply.reject(error);
  }

  const exited = new Promise(resolveExit => {
    child.once("error", error => {
      rejectPending(error);
      resolveExit(error);
    });
    child.once("exit", (code, signal) => {
      rejectPending(new Error(`Desktop app exited (${signal ?? code}).`));
      resolveExit(code);
    });
  });
  pipeIn.on("error", rejectPending);
  pipeOut.on("error", rejectPending);
  pipeOut.setEncoding("utf8").on("data", chunk => {
    buffered += chunk;
    const messages = buffered.split("\0");
    buffered = messages.pop();
    for (const message of messages) {
      const { id, result, error } = JSON.parse(message);
      const reply = pending.get(id);
      if (error) reply?.reject(new Error(error.message));
      else reply?.resolve(result);
    }
  });

  async function send(method, params = {}, sessionId) {
    const id = ++nextId;
    const timeout = setTimeout(() => {
      pending.get(id).reject(new Error(`Timed out running ${method}.`));
    }, commandTimeout);
    try {
      return await new Promise((resolveReply, reject) => {
        pending.set(id, { resolve: resolveReply, reject });
        pipeIn.write(`${JSON.stringify({ id, method, params, sessionId })}\0`, error => {
          if (error) reject(error);
        });
      });
    } finally {
      clearTimeout(timeout);
      pending.delete(id);
    }
  }

  let exitCode;
  try {
    const target = await waitFor(async () => {
      const { targetInfos } = await send("Target.getTargets");
      return targetInfos.find(item => item.type === "page" && item.url === appUrl);
    }, "the board window");
    const { sessionId } = await send("Target.attachToTarget", { targetId: target.targetId, flatten: true });
    async function evaluate(expression) {
      const { result, exceptionDetails } = await send("Runtime.evaluate", {
        expression, awaitPromise: true, returnByValue: true,
      }, sessionId);
      if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
      return result.value;
    }
    await waitFor(() => evaluate(`document.querySelector("#status")?.textContent === "Board ready"`),
      "the board to load its teams");
    assert.equal(await evaluate(`document.querySelectorAll("#pitch .player-token").length`), 22);
    await check(evaluate);
  } finally {
    exitCode = child.exitCode;
    if (child.pid && child.exitCode === null && child.signalCode === null) {
      const close = send("Browser.close").catch(() => {});
      exitCode = await Promise.race([exited, delay(5_000, null, { ref: false })]);
      if (exitCode === null) child.kill();
      await exited;
      await close;
    }
  }
  assert.equal(exitCode, 0, "Desktop app did not exit cleanly.");
}

const [filename] = process.argv.slice(2);
assert(filename, "Usage: node tools/smoke_desktop.mjs <path-to-packaged-app-executable>");
const executable = resolve(filename);
await access(executable);
const profile = await mkdtemp(join(tmpdir(), "football-board-smoke-"));

try {
  let savedFormation;
  await runDesktop(executable, profile, async evaluate => {
    const rejectedMatch = await evaluate(`(async () => {
      const response = await fetch("/api/match?url=https%3A%2F%2Fexample.invalid%2Fjogo%2Ftest%2F123");
      return { status: response.status, body: await response.json() };
    })()`);
    assert.equal(rejectedMatch.status, 400);
    assert.match(rejectedMatch.body.error, /only HTTPS zerozero\.pt match links/i);
    savedFormation = await evaluate(`(() => {
      const formation = document.querySelector("#formation-0");
      formation.selectedIndex = (formation.selectedIndex + 1) % formation.options.length;
      formation.dispatchEvent(new Event("change"));
      document.querySelector("#save").click();
      return formation.value;
    })()`);
    assert.equal(await evaluate(`document.querySelector("#status").textContent`), "Tactic saved in this browser");
  });
  await runDesktop(executable, profile, async evaluate => {
    assert.notEqual(await evaluate(`document.querySelector("#formation-0").value`), savedFormation);
    const loadedFormation = await evaluate(`(() => {
      document.querySelector("#load").click();
      return document.querySelector("#formation-0").value;
    })()`);
    assert.equal(loadedFormation, savedFormation);
  });
  console.log("Desktop smoke passed: board, match validation, and tactic persistence.");
} finally {
  await rm(profile, { recursive: true, force: true, maxRetries: 5 });
}
