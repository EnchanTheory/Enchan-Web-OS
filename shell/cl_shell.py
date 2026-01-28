import json
import asyncio
import pyodide_http
import requests
from pyscript import document, window
from pyodide.ffi import create_proxy
from js import window as js_window
from js import FileReader

pyodide_http.patch_all()

state = {
    "h": {},
    "J": {},
    "N_max": 0,
    "history": [],
    "history_idx": 0,
    "docs_cache": None
}

# --- Constants for Safety ---
MAX_FILE_SIZE = 1024 * 1024
MAX_BATCH_LINES = 5000
MAX_RUN_DURATION = 120.0
ALLOWED_EXTENSIONS = (".enc", ".txt", ".py")

history_div = document.getElementById("history")
cmd_input = document.getElementById("cmd-input")
input_area = document.getElementById("input-area")
loading_msg = document.getElementById("loading")
terminal_container = document.getElementById("terminal-container")
file_loader = document.getElementById("file-loader")

# ==========================================
# Helpers
# ==========================================
def log(msg, style="text"):
    div = document.createElement("div")
    div.className = f"line {style}"
    div.textContent = str(msg)
    history_div.appendChild(div)
    terminal_container.scrollTop = terminal_container.scrollHeight

def load_docs():
    if state["docs_cache"]:
        return state["docs_cache"]
    try:
        target_url = f"{js_window.location.origin}/shell/docs.json"
        res = requests.get(target_url)
        if res.status_code == 200:
            data = res.json()
            state["docs_cache"] = data
            return data
    except Exception as e:
        log(f"Warning: Failed to load docs.json: {e}", "error")
    return None

def show_doc_section(section_name):
    data = load_docs()
    if not data or section_name not in data:
        log(f"Documentation for '{section_name}' not found.", "error")
        return

    for line in data[section_name]:
        log(line.get("text", ""), line.get("style", "text"))

def show_welcome():
    loading_msg.style.display = "none"
    input_area.style.display = "flex"
    
    load_docs()
    
    log("Research Preview", "system")
    log("System Ready.", "system")
    log("Type 'help' for commands.", "result")
    cmd_input.focus()

def decode_bits_to_text(bits):
    n_bytes = len(bits) // 8
    if n_bytes == 0: return ""
    chars = []
    for i in range(n_bytes):
        byte_bits = bits[i*8 : (i+1)*8]
        byte_str = "".join(str(b) for b in byte_bits)
        ascii_code = int(byte_str, 2)
        if 32 <= ascii_code <= 126:
            chars.append(chr(ascii_code))
        else:
            chars.append("?")
    return "".join(chars)

# ==========================================
# Batch Processor
# ==========================================
async def run_batch_script(script_text, source_name="Script"):
    if not script_text: return
    lines = script_text.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    total_lines = len(lines)
    if total_lines > MAX_BATCH_LINES:
        log(f"Security Alert: Script too long ({total_lines} lines).", "error")
        log(f"Limit is {MAX_BATCH_LINES} lines.", "system")
        return

    log(f"--- Loading {source_name} ({len(lines)} lines) ---", "system")
    count = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"): continue
        await process_single_line(line)
        count += 1
        await asyncio.sleep(0.005)
    log(f"--- Finished ({count} ops) ---", "system")

# ==========================================
# Core Logic
# ==========================================
async def process_single_line(line):
    line = line.strip()
    if not line: return
    if line.startswith("#"): return

    log(f"Enchan> {line}", "text")
    if not state["history"] or state["history"][-1] != line:
        state["history"].append(line)
    state["history_idx"] = len(state["history"])

    parts = line.split()
    cmd = parts[0].lower()
    args = parts[1:]

    try:
        if cmd == "help":
            show_doc_section("help")

        elif cmd == "docs":
            show_doc_section("docs")

        elif cmd == "reset":
            state["h"] = {}
            state["J"] = {}
            state["N_max"] = 0
            log("Memory cleared.", "system")

        elif cmd == "node":
            if len(args) < 2: raise Exception("Usage: node <index> <bias>")
            i, bias = int(args[0]), float(args[1])
            state["h"][i] = bias
            state["N_max"] = max(state["N_max"], i + 1)

        elif cmd == "edge":
            if len(args) < 3: raise Exception("Usage: edge <i> <j> <weight>")
            u, v, w = int(args[0]), int(args[1]), float(args[2])
            if u > v: u, v = v, u
            key = f"{u},{v}"
            state["J"][key] = {"u": u, "v": v, "w": w}
            state["N_max"] = max(state["N_max"], u + 1, v + 1)
            log(f"Link[{u}-{v}] set to {w}", "system")
        
        elif cmd == "source":
            file_loader.value = ""
            file_loader.click()
            log("Select .enc file...", "system")

        elif cmd == "run":
            if state["N_max"] == 0: raise Exception("No data in memory.")
            duration = max(5.0, state["N_max"] * 0.2)
            if args: duration = float(args[0])
            if duration < 35.0: duration = 35.0
            if duration > MAX_RUN_DURATION:
                duration = MAX_RUN_DURATION
                log(f"Warning: Duration capped at {MAX_RUN_DURATION}s", "system")

            core_N = state["N_max"]
            has_bias = len(state["h"]) > 0
            ghost_idx = core_N
            final_N = core_N + (1 if has_bias else 0)

            edges_list = []
            weights_list = []
            for k, v in state["J"].items():
                edges_list.append([v["u"], v["v"]])
                weights_list.append(v["w"])

            if has_bias:
                for idx, bias in state["h"].items():
                    if idx < core_N:
                        edges_list.append([idx, ghost_idx])
                        weights_list.append(bias) 

            init_state = [0.0] * final_N
            if has_bias:
                init_state[ghost_idx] = 1.0

            payload = {
                "graph": { 
                    "N": final_N, 
                    "edges": edges_list, 
                    "weights": weights_list, 
                    "density": 0.0 
                },
                "control": { "total_time": duration },
                "initial_state": init_state,
                "seed": 314
            }

            log(f"Computing (N={core_N}, t={duration}s)...", "result")
            
            headers = {"Content-Type": "application/json"}
            target_url = f"{js_window.location.origin}/v1/solve"
            
            response = requests.post(target_url, json=payload, headers=headers)
            
            if response.status_code != 200:
                raise Exception(f"Error ({response.status_code}): {response.text}")

            res = response.json()

            audit_pub = res.get("audit_public", {})
            res_hash = audit_pub.get("result_hash", "no-signature")

            spins = res.get("outputs", {}).get("spins", [])
            
            if has_bias:
                ghost_spin = spins[ghost_idx]
                bits = []
                for i in range(core_N):
                    bits.append(1 if (spins[i] * ghost_spin > 0) else 0)
            else:
                bits = [1 if s > 0 else 0 for s in spins[:core_N]]
            
            timing = res.get("TIMING", {})
            wall_time = timing.get("total_wall_time", 0.0)

            log(f"Done ({wall_time:.4f}s)", "result")
            log(f"Binary: {bits}", "audit")
            
            log(f"Hash: [{res_hash}]", "system")
            
            decoded_text = decode_bits_to_text(bits)
            if decoded_text:
                log(f"String: \"{decoded_text}\"", "result")

        else:
            log(f"Unknown: {cmd}", "error")

    except Exception as e:
        log(f"Error: {str(e)}", "error")

# --- Events ---
show_welcome()

async def on_keydown(event):
    if event.key == "Enter":
        line = cmd_input.value
        cmd_input.value = ""
        await process_single_line(line)
    elif event.key == "ArrowUp":
        event.preventDefault()
        if state["history_idx"] > 0:
            state["history_idx"] -= 1
            cmd_input.value = state["history"][state["history_idx"]]
    elif event.key == "ArrowDown":
        event.preventDefault()
        if state["history_idx"] < len(state["history"]):
            state["history_idx"] += 1
            cmd_input.value = "" if state["history_idx"] == len(state["history"]) else state["history"][state["history_idx"]]

async def on_paste(event):
    event.preventDefault()
    clipboard_text = event.clipboardData.getData('text')

    line_count = clipboard_text.count('\n')
    if line_count > MAX_BATCH_LINES:
         log(f"Security Alert: Paste too large ({line_count} lines).", "error")
         return

    await run_batch_script(clipboard_text, "Paste")

async def on_file_selected(event):
    files = file_loader.files
    if files.length == 0: return
    file = files.item(0)

    valid_ext = False
    for ext in ALLOWED_EXTENSIONS:
        if file.name.lower().endswith(ext):
            valid_ext = True
            break
    
    if not valid_ext:
        log(f"Security Alert: Invalid file extension '{file.name}'.", "error")
        allowed_str = ", ".join(ALLOWED_EXTENSIONS)
        log(f"Allowed: {allowed_str}", "system")
        return

    if file.size > MAX_FILE_SIZE:
        log(f"Security Alert: File too large ({file.size} bytes).", "error")
        log(f"Limit is {MAX_FILE_SIZE} bytes (1MB).", "system")
        return

    reader = FileReader.new()
    def on_load_end(e):
        asyncio.ensure_future(run_batch_script(e.target.result, file.name))
    reader.onload = create_proxy(on_load_end)
    reader.readAsText(file)

def keep_focus(event):
    if not js_window.getSelection().toString():
        cmd_input.focus()

proxy_keydown = create_proxy(on_keydown)
cmd_input.addEventListener("keydown", proxy_keydown)
proxy_paste = create_proxy(on_paste)
cmd_input.addEventListener("paste", proxy_paste)
proxy_focus = create_proxy(keep_focus)
terminal_container.addEventListener("click", proxy_focus)
proxy_file_select = create_proxy(on_file_selected)
file_loader.addEventListener("change", proxy_file_select)