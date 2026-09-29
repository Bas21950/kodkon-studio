const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn, execFile } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { promisify } = require('node:util');

const execFileAsync = promisify(execFile);
const devRoot = path.resolve(__dirname, '..');
let mainWindow;
let serverProcess;
let updateInfo;
let updateReady = false;
const backendPort = 18765;
const backgroundMode = process.argv.includes('--background');
const backendPidPath = () => path.join(app.getPath('userData'), 'backend.pid');

async function stopBackgroundBackend() {
  if (!fs.existsSync(backendPidPath())) return;
  const pid = Number(fs.readFileSync(backendPidPath(), 'utf8').trim());
  if (!Number.isSafeInteger(pid) || pid <= 0) return;
  try {
    const { stdout } = await execFileAsync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', `(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').ExecutablePath`], { windowsHide: true });
    if (!stdout.toLowerCase().includes('kodkon-backend.exe')) return;
    process.kill(pid);
  } catch { /* Backend may already have exited. */ }
}

async function backendAvailable() {
  try {
    const response = await fetch(`http://127.0.0.1:${backendPort}/api/health`, { signal: AbortSignal.timeout(1200) });
    return response.ok;
  } catch { return false; }
}

async function registerBackgroundTask() {
  if (process.platform !== 'win32' || !app.isPackaged) return;
  const taskCommand = `"${app.getPath('exe')}" --background`;
  try {
    await execFileAsync('schtasks.exe', ['/Create', '/SC', 'ONLOGON', '/TN', 'KodKon Studio Background', '/TR', taskCommand, '/F'], { windowsHide: true });
  } catch (error) {
    dialog.showMessageBox({ type: 'warning', title: 'ตั้งเวลาโพสต์', message: 'ลงทะเบียนการทำงานหลังเข้าสู่ Windows ไม่สำเร็จ', detail: String(error.message || error) });
  }
}

function resourceRoot() {
  return app.isPackaged ? process.resourcesPath : devRoot;
}

function notifyUpdate(status) {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('updates:status', status);
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function knownDataFolder() {
  if (process.env.KODKON_DATA_DIR) return process.env.KODKON_DATA_DIR;
  const saved = path.join(app.getPath('userData'), 'data-path.txt');
  if (fs.existsSync(saved)) {
    const folder = fs.readFileSync(saved, 'utf8').trim();
    if (fs.existsSync(folder)) return folder;
  }
  const candidates = [process.cwd(), devRoot, path.dirname(app.getPath('exe'))];
  for (const candidate of candidates) {
    let current = candidate;
    for (let depth = 0; depth < 5; depth += 1) {
      const folder = path.join(current, 'Data');
      if (fs.existsSync(path.join(folder, 'kodkon-studio.sqlite3'))) return folder;
      const parent = path.dirname(current);
      if (parent === current) break;
      current = parent;
    }
  }
  return null;
}

async function chooseDataFolder() {
  let folder = knownDataFolder();
  if (!folder && app.isPackaged) {
    const answer = await dialog.showMessageBox({
      type: 'question', buttons: ['เลือกโฟลเดอร์ Data เดิม', 'เริ่มใหม่โดยไม่ลบข้อมูลเดิม'], defaultId: 0,
      title: 'ข้อมูล กดก่อนคิดทีหลัง Studio',
      message: 'ถ้าเคยใช้โปรแกรมรุ่นเดิม ให้เลือกโฟลเดอร์ Data เดิมเพื่อให้โพสต์และการตั้งค่ายังอยู่',
    });
    if (answer.response === 0) {
      const selection = await dialog.showOpenDialog({ properties: ['openDirectory'], title: 'เลือกโฟลเดอร์ Data เดิม' });
      if (selection.canceled) throw new Error('ยังไม่ได้เลือกโฟลเดอร์ข้อมูลเดิม · เปิดโปรแกรมใหม่เพื่อเลือกอีกครั้ง');
      folder = selection.filePaths[0];
      if (!fs.existsSync(path.join(folder, 'kodkon-studio.sqlite3'))) throw new Error('โฟลเดอร์ที่เลือกไม่มีฐานข้อมูลเดิม กรุณาเลือกโฟลเดอร์ Data');
    }
  }
  if (!folder) folder = path.join(app.getPath('userData'), 'Data');
  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(path.join(app.getPath('userData'), 'data-path.txt'), folder, 'utf8');
  return folder;
}

async function run(command, args, cwd) {
  await execFileAsync(command, args, { cwd, windowsHide: true, timeout: 10 * 60 * 1000, maxBuffer: 1024 * 1024 });
}

async function pythonRuntime(backendRoot) {
  const existing = path.join(backendRoot, '.venv', 'Scripts', 'pythonw.exe');
  if (!app.isPackaged && fs.existsSync(existing)) return existing;
  const runtime = path.join(app.getPath('userData'), 'python-runtime');
  const pythonExe = path.join(runtime, 'Scripts', 'python.exe');
  const pythonwExe = path.join(runtime, 'Scripts', 'pythonw.exe');
  if (!fs.existsSync(pythonExe)) {
    notifyUpdate({ status: 'preparing', message: 'กำลังเตรียมระบบ Python ครั้งแรก' });
    await run('python', ['-m', 'venv', runtime], backendRoot);
  }
  const requirements = path.join(backendRoot, 'requirements.txt');
  const digest = createHash('sha256').update(fs.readFileSync(requirements)).digest('hex');
  const stamp = path.join(runtime, '.requirements.sha256');
  if (!fs.existsSync(stamp) || fs.readFileSync(stamp, 'utf8').trim() !== digest) {
    notifyUpdate({ status: 'preparing', message: 'กำลังติดตั้งส่วนประกอบ Python ครั้งแรก' });
    await run(pythonExe, ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', requirements], backendRoot);
    fs.writeFileSync(stamp, digest, 'utf8');
  }
  return pythonwExe;
}

async function startBackend() {
  const url = `http://127.0.0.1:${backendPort}`;
  if (await backendAvailable()) return url;
  const backendRoot = path.join(resourceRoot(), 'backend');
  const dataFolder = await chooseDataFolder();
  const packagedServer = path.join(resourceRoot(), 'kodkon-backend', 'kodkon-backend.exe');
  const bundled = app.isPackaged && fs.existsSync(packagedServer);
  if (app.isPackaged && !bundled) throw new Error('ตัวติดตั้งไม่มีระบบเบื้องหลัง กรุณาติดตั้งโปรแกรมใหม่');
  const python = bundled ? packagedServer : await pythonRuntime(backendRoot);
  const port = app.isPackaged ? backendPort : await getFreePort();
  const log = fs.openSync(path.join(app.getPath('userData'), 'backend.log'), 'a');
  serverProcess = spawn(python, bundled ? [] : ['-m', 'app.server'], {
    cwd: backendRoot,
    windowsHide: true,
    detached: app.isPackaged,
    env: { ...process.env, KODKON_DATA_DIR: dataFolder, KODKON_PORT: String(port), KODKON_DESKTOP_SHELL: 'electron', KODKON_BACKEND_ROOT: backendRoot, KODKON_RESOURCE_ROOT: resourceRoot() },
    stdio: ['ignore', log, log],
  });
  fs.closeSync(log);
  if (app.isPackaged) {
    fs.writeFileSync(backendPidPath(), String(serverProcess.pid), 'utf8');
    serverProcess.unref();
  }
  let serverError = null;
  serverProcess.on('error', (error) => { serverError = error; });
  const serverUrl = `http://127.0.0.1:${port}`;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (app.isPackaged && await backendAvailable()) return serverUrl;
    if (serverError) throw serverError;
    if (serverProcess.exitCode !== null) throw new Error('ระบบเบื้องหลังเปิดไม่สำเร็จ กรุณาดู backend.log');
    try {
      const response = await fetch(`${serverUrl}/api/health`, { signal: AbortSignal.timeout(1000) });
      if (response.ok) return serverUrl;
    } catch { /* Backend still starting. */ }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error('ระบบเบื้องหลังเริ่มไม่ทันเวลา กรุณาดู backend.log');
}

function createWindow() {
  mainWindow = new BrowserWindow({
    title: 'กดก่อนคิดทีหลัง Studio', width: 1440, height: 920, minWidth: 980, minHeight: 680,
    icon: path.join(resourceRoot(), app.isPackaged ? 'kodkon-studio.ico' : 'frontend/public/kodkon-studio.ico'),
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent('<!doctype html><html lang="th"><meta charset="utf-8"><style>body{font-family:Segoe UI,Tahoma,sans-serif;background:#f7f8fa;color:#263248;display:grid;place-items:center;height:100vh;margin:0}.box{text-align:center}.dot{color:#fb6b53;font-size:36px}</style><div class="box"><div class="dot">●</div><h2>กำลังเปิด กดก่อนคิดทีหลัง Studio</h2><p>รอสักครู่ ระบบกำลังเตรียมพร้อม</p></div></html>'));
}

function showApplication(url) {
  mainWindow.loadURL(url);
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    if (target.startsWith('https://')) void shell.openExternal(target);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, target) => {
    if (!target.startsWith(`${url}/`)) event.preventDefault();
  });
}

autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = false;
autoUpdater.on('download-progress', (progress) => notifyUpdate({ status: 'downloading', progress: Math.round(progress.percent), message: `ดาวน์โหลดแล้ว ${Math.round(progress.percent)}%` }));
autoUpdater.on('update-downloaded', () => { updateReady = true; notifyUpdate({ status: 'ready', progress: 100, message: 'ดาวน์โหลดเสร็จแล้ว · พร้อมเปิดโปรแกรมใหม่' }); });
autoUpdater.on('error', (error) => notifyUpdate({ status: 'failed', message: `อัปเดตไม่สำเร็จ: ${error.message}` }));

ipcMain.handle('updates:check', async () => {
  if (!app.isPackaged) return { available: false, currentVersion: app.getVersion() };
  const result = await autoUpdater.checkForUpdates();
  updateInfo = result?.updateInfo ?? null;
  let notes = updateInfo?.releaseNotes ?? '';
  if (updateInfo?.version && !notes) {
    try {
      const response = await fetch(`https://api.github.com/repos/Bas21950/kodkon-studio/releases/tags/v${encodeURIComponent(updateInfo.version)}`, {
        headers: { 'User-Agent': 'KodKonStudio-Desktop', Accept: 'application/vnd.github+json' },
        signal: AbortSignal.timeout(8000),
      });
      if (response.ok) notes = (await response.json()).body ?? '';
    } catch { /* Updating still works when release notes cannot be loaded. */ }
  }
  return { available: !!updateInfo && updateInfo.version !== app.getVersion(), currentVersion: app.getVersion(), version: updateInfo?.version, notes };
});
ipcMain.handle('updates:download', async () => {
  if (!updateInfo) throw new Error('ยังไม่มีอัปเดตให้ดาวน์โหลด');
  updateReady = false;
  await autoUpdater.downloadUpdate();
  return true;
});
ipcMain.handle('updates:install', async () => {
  if (!updateReady) throw new Error('ยังดาวน์โหลดอัปเดตไม่ครบ');
  await stopBackgroundBackend();
  autoUpdater.quitAndInstall();
});

if (backgroundMode) {
  app.whenReady().then(async () => {
    if (knownDataFolder()) await startBackend();
    app.quit();
  }).catch(() => app.quit());
} else if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } });
  app.whenReady().then(async () => {
    try { createWindow(); showApplication(await startBackend()); await registerBackgroundTask(); }
    catch (error) { await dialog.showMessageBox({ type: 'error', title: 'เปิดโปรแกรมไม่สำเร็จ', message: String(error.message || error) }); app.quit(); }
  });
}
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { if (!app.isPackaged && serverProcess && serverProcess.exitCode === null) serverProcess.kill(); });
