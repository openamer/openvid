const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const API = 'http://127.0.0.1:8765';
let win = null, tray = null, quitting = false;

// start the backend if not already healthy (dev convenience; the scheduled
// task normally owns it)
function backendHealthy() {
  return new Promise(resolve => {
    http.get(API + '/health', r => resolve(r.statusCode === 200)).on('error', () => resolve(false));
  });
}

function startBackend() {
  const py = path.join(process.env.LOCALAPPDATA, 'openamer-laptop', 'venv', 'Scripts', 'python.exe');
  const child = spawn(py, ['-m', 'openvid.server', '--port', '8765'], {
    cwd: path.join(__dirname, '..'), detached: true, stdio: 'ignore'
  });
  child.unref();
}

async function waitForBackend(tries = 30) {
  for (let i = 0; i < tries; i++) {
    if (await backendHealthy()) return true;
    await new Promise(r => setTimeout(r, 1000));
  }
  return false;
}

function createWindow() {
  win = new BrowserWindow({
    width: 1100, height: 760,
    backgroundColor: '#fafafa',
    icon: path.join(__dirname, 'icon.png'),
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true }
  });
  win.loadURL(API + '/');
  win.on('close', e => {
    if (!quitting) { e.preventDefault(); win.hide(); }  // tray keep-alive
  });
}

app.whenReady().then(async () => {
  if (!(await backendHealthy())) {
    startBackend();
    await waitForBackend();
  }
  createWindow();
  // tray
  tray = new Tray(nativeImage.createEmpty());
  tray.setToolTip('OPENVID');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show', click: () => { win.show(); win.focus(); } },
    { label: 'Open in Browser', click: () => require('electron').shell.openExternal(API) },
    { type: 'separator' },
    { label: 'Quit', click: () => { quitting = true; app.quit(); } }
  ]));
  tray.on('click', () => { win.show(); win.focus(); });
  setInterval(async () => {
    const ok = await backendHealthy();
    tray.setToolTip(ok ? 'OPENVID — online' : 'OPENVID — backend offline');
  }, 10000);
});

app.on('before-quit', () => { quitting = true; });
app.on('window-all-closed', () => { /* stay in tray */ });
