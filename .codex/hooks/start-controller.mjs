import { spawn, spawnSync } from 'node:child_process';
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { createServer } from 'node:net';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const cwd = resolve(root, 'agent-runtime/monorepo-controller');
const state = resolve(root, '.agent-state/cache/controller');
const logs = resolve(root, '.agent-state/logs/controller/startup');
mkdirSync(state, { recursive: true });
mkdirSync(logs, { recursive: true });
const lock = resolve(state, 'startup.lock');
const deadline = Date.now() + 110_000;
let locked = false;

async function ready(name) {
  try {
    const response = await fetch(name === 'backend'
      ? 'http://localhost:1002/api/controller/agents'
      : 'http://localhost:1001', { signal: AbortSignal.timeout(1500) });
    if (!response.ok) return false;
    return name === 'backend' ? Array.isArray(await response.json())
      : (await response.text()).includes('<app-root');
  } catch { return false; }
}

async function acquireLock() {
  while (Date.now() < deadline) {
    try {
      writeFileSync(lock, String(process.pid), { flag: 'wx' });
      locked = true;
      return;
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      // Reclaim a lock only when its owner has exited. Empty files can be
      // observed briefly while another process is writing its PID.
      try {
        const pid = Number(readFileSync(lock, 'utf8'));
        if (pid > 0) {
          try { process.kill(pid, 0); }
          catch (error) { if (error.code === 'ESRCH') unlinkSync(lock); }
        }
      } catch (error) { if (error.code !== 'ENOENT') throw error; }
      await delay(250);
    }
  }
  throw new Error('Timed out waiting for the controller startup lock.');
}

async function start(name, args) {
  if (await ready(name)) return;
  const port = name === 'backend' ? 1002 : 1001;
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', error => reject(new Error(
      `Cannot bind localhost:${port}: ${error.code}. ` +
      (error.code === 'EACCES'
        ? 'The operating system requires permission to use this low port.'
        : 'Check whether another service is occupying this port.'),
    )));
    server.listen(port, 'localhost', () => server.close(resolve));
  });
  if (name === 'backend') {
    const result = spawnSync('npm', ['run', 'backend:build'], {
      cwd, encoding: 'utf8', timeout: Math.max(1, deadline - Date.now()),
    });
    writeFileSync(resolve(logs, 'backend-build.log'), `${result.stdout ?? ''}${result.stderr ?? ''}`);
    if (result.error || result.status !== 0) throw new Error('Backend build failed; see backend-build.log.');
  }
  const fd = openSync(resolve(logs, `${name}.log`), 'a');
  let child;
  try {
    child = spawn(process.execPath, args, {
      cwd, detached: true, stdio: ['ignore', fd, fd],
      env: { ...process.env, PORT: '1002', HOST: 'localhost', CI: 'true', NG_CLI_ANALYTICS: 'false' },
    });
  } finally { closeSync(fd); }
  let failure;
  child.on('error', error => { failure = error; });
  child.unref();
  writeFileSync(resolve(state, `${name}.pid`), String(child.pid));
  while (Date.now() < deadline) {
    if (failure || child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`${name} exited during startup; see ${name}.log.`, { cause: failure });
    }
    if (await ready(name)) return;
    await delay(500);
  }
  throw new Error(`${name} did not become ready; see ${name}.log.`);
}

try {
  await acquireLock();
  if (!existsSync(resolve(cwd, 'node_modules/.bin/ng'))) {
    throw new Error(`Dependencies are missing. Run npm ci in ${cwd}.`);
  }
  await start('backend', ['backend-api-services/dist/main.js']);
  await start('frontend', ['node_modules/@angular/cli/bin/ng.js', 'serve', '--host', 'localhost', '--port', '1001']);
  console.log('Monorepo controller ready: http://localhost:1001 (backend: http://localhost:1002).');
} catch (error) {
  console.error(`${error.message}\nStartup logs: ${logs}`);
  process.exitCode = 1;
} finally {
  if (locked) unlinkSync(lock);
}
