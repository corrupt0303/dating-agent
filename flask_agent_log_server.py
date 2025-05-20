from flask import Flask, Response, render_template_string, send_file
import time
import os
import re

app = Flask(__name__)

# Use /tmp/agent.log by default for read-only filesystems; allow override
LOG_FILE = os.environ.get("AGENT_LOG_FILE", "/tmp/agent.log")

HTML_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Agent Live Log</title>
  <style>
    body { background: #181818; color: #eee; font-family: monospace; }
    #log { background: #222; padding: 1em; border-radius: 8px; height: 70vh; overflow-y: scroll; white-space: pre-wrap; font-size: 15px; }
    .log-info { color: #eee; }
    .log-warning { color: #ffe066; }
    .log-error { color: #ff6b6b; }
    .log-debug { color: #aaa; }
    .search-bar { margin-bottom: 1em; }
    .filter-checkbox { margin-right: 1em; }
    .download-btn { margin-left: 1em; }
    .tail-btn { margin-left: 1em; }
  </style>
</head>
<body>
  <h2>Agent Live Log</h2>
  <div class="search-bar">
    <input id="search" type="text" placeholder="Search logs..." />
    <label class="filter-checkbox"><input type="checkbox" id="info" checked /> INFO</label>
    <label class="filter-checkbox"><input type="checkbox" id="warning" checked /> WARNING</label>
    <label class="filter-checkbox"><input type="checkbox" id="error" checked /> ERROR</label>
    <label class="filter-checkbox"><input type="checkbox" id="debug" checked /> DEBUG</label>
    <button class="download-btn" onclick="window.location='/download'">Download Log</button>
    <button class="tail-btn" id="tail-btn">Tail: On</button>
  </div>
  <div id="log"></div>
  <script>
    const logDiv = document.getElementById('log');
    const evtSource = new EventSource('/stream');
    let logLines = [];
    let tailing = true;
    document.getElementById('tail-btn').onclick = function() {
      tailing = !tailing;
      this.textContent = 'Tail: ' + (tailing ? 'On' : 'Off');
      if (tailing) scrollToBottom();
    };
    function scrollToBottom() {
      logDiv.scrollTop = logDiv.scrollHeight;
    }
    function renderLog() {
      const search = document.getElementById('search').value.toLowerCase();
      const showInfo = document.getElementById('info').checked;
      const showWarning = document.getElementById('warning').checked;
      const showError = document.getElementById('error').checked;
      const showDebug = document.getElementById('debug').checked;
      logDiv.innerHTML = logLines.filter(line => {
        if (search && !line.raw.toLowerCase().includes(search)) return false;
        if (line.level === 'info' && !showInfo) return false;
        if (line.level === 'warning' && !showWarning) return false;
        if (line.level === 'error' && !showError) return false;
        if (line.level === 'debug' && !showDebug) return false;
        return true;
      }).map(line => `<span class="log-${line.level}">${line.html}</span>`).join('\n');
      if (tailing) scrollToBottom();
    }
    evtSource.onmessage = function(e) {
      const lines = e.data.split('\n');
      for (const raw of lines) {
        let level = 'info';
        if (/\bWARNING\b/.test(raw)) level = 'warning';
        if (/\bERROR\b/.test(raw)) level = 'error';
        if (/\bDEBUG\b/.test(raw)) level = 'debug';
        const html = raw.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        logLines.push({ raw, html, level });
      }
      renderLog();
    };
    document.getElementById('search').oninput = renderLog;
    document.getElementById('info').onchange = renderLog;
    document.getElementById('warning').onchange = renderLog;
    document.getElementById('error').onchange = renderLog;
    document.getElementById('debug').onchange = renderLog;
  </script>
</body>
</html>
'''

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/stream")
def stream():
    def generate():
        last_size = 0
        while True:
            if not os.path.exists(LOG_FILE):
                yield f"data: [Log file {LOG_FILE} not found or not readable]\n\n"
                time.sleep(1)
                continue
            try:
                with open(LOG_FILE, "r") as f:
                    f.seek(last_size)
                    new = f.read()
                    if new:
                        f.seek(0, 2)
                        last_size = f.tell()
                        for line in new.splitlines():
                            yield f"data: {line}\n\n"
                time.sleep(1)
            except Exception as e:
                yield f"data: [Error reading log file: {e}]\n\n"
                time.sleep(2)
    return Response(generate(), mimetype="text/event-stream")

@app.route("/download")
def download():
    if os.path.exists(LOG_FILE):
        return send_file(LOG_FILE, as_attachment=True)
    return "Log file not found.", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True) 