import json, os, subprocess, sys, threading, time
from pathlib import Path
log = Path(sys.argv[1]); args = sys.argv[2:]; started = time.monotonic()
log.parent.mkdir(parents=True, exist_ok=True)
print("COMMAND " + json.dumps(args), flush=True)
with log.open("w") as output:
    child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    def terminate():
        print("COMMAND TIMEOUT after 589 seconds", flush=True); child.terminate()
    timer = threading.Timer(589, terminate); timer.start()
    for line in child.stdout:
        output.write(line); output.flush(); print(line, end="", flush=True)
    code = child.wait(); timer.cancel()
meta = {"args":args,"cwd":os.getcwd(),"exit":code,"wallSeconds":time.monotonic()-started,"tail":"".join(log.read_text().splitlines(keepends=True)[-35:])}
log.with_suffix(".json").write_text(json.dumps(meta,indent=2)+"\n")
print("GATE EXIT " + str(code), flush=True); sys.exit(code)
