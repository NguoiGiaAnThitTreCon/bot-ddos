import os
import signal
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)
processes = []  # quản lý tiến trình đang chạy


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})


@app.route("/run1", methods=["GET"])
def run1():
    url = request.args.get("url")
    if not url:
        return jsonify({"status": "error", "msg": "missing url"}), 400
    cmd = f"./run 1 {url}"
    p = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
    processes.append(p)
    return jsonify({"status": "running", "cmd": cmd})


@app.route("/run2", methods=["GET"])
def run2():
    url = request.args.get("url")
    if not url:
        return jsonify({"status": "error", "msg": "missing url"}), 400
    cmd = f"./run 2 {url}"
    p = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
    processes.append(p)
    return jsonify({"status": "running", "cmd": cmd})


@app.route("/stop", methods=["GET"])
def stop():
    killed = 0
    for p in processes:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            killed += 1
        except Exception as e:
            print("Error killing:", e)
    processes.clear()
    return jsonify({"status": f"stopped {killed} process(es)"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
