import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox
import webbrowser
import os


# ============================================================
# Configuration
# ============================================================

APP_NAME = "Harmony3 Connect"

SSH_HOST = "harmony3-portainer"

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 19443

STARTUP_TIMEOUT = 10
CHECK_INTERVAL = 0.2


# ============================================================
# State
# ============================================================

tunnel_process = None
starting = False


# ============================================================
# SSH helpers
# ============================================================

def find_ssh():
    ssh = shutil.which("ssh.exe") or shutil.which("ssh")

    if not ssh:
        raise RuntimeError(
            "Windows OpenSSH could not be found.\n\n"
            "Make sure ssh.exe is installed and available "
            "in PATH."
        )

    return ssh


def port_is_open(LOCAL_HOST, LOCAL_PORT):
    try:
        with socket.create_connection(
            (LOCAL_HOST, LOCAL_PORT),
            timeout=0.5
        ):
            return True
    except OSError:
        return False


def get_existing_tunnel_pid():
    """Find the SSH process belonging to this tunnel."""

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "Get-CimInstance Win32_Process "
                    "-Filter \"Name = 'ssh.exe'\" | "
                    "Where-Object { "
                    "$_.CommandLine -like '*harmony3-portainer*' "
                    "} | "
                    "Select-Object -First 1 -ExpandProperty ProcessId"
                )
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        pid = result.stdout.strip()

        if pid.isdigit():
            return int(pid)

    except Exception:
        pass

    return None


def terminate_process(process):
    if process is None:
        return

    try:
        if process.poll() is None:
            process.terminate()

            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    except Exception:
        pass


# ============================================================
# SSH Agent
# ============================================================

def is_ssh_agent_running():
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "(Get-Service ssh-agent "
                    "-ErrorAction SilentlyContinue).Status"
                )
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        return result.stdout.strip().lower() == "running"

    except Exception:
        return False


def apply_agent_status(running):
    if running:
        agent_status_label.config(
            text="●  SSH Agent: Running",
            fg="#2ecc71"
        )

        start_agent_button.config(
            state="disabled"
        )

        stop_agent_button.config(
            state="normal"
        )

    else:
        agent_status_label.config(
            text="●  SSH Agent: Stopped",
            fg="#e74c3c"
        )

        start_agent_button.config(
            state="normal"
        )

        stop_agent_button.config(
            state="disabled"
        )


def refresh_agent_status():
    def worker():
        running = is_ssh_agent_running()

        root.after(
            0,
            lambda: apply_agent_status(running)
        )

    threading.Thread(
        target=worker,
        daemon=True
    ).start()

    root.after(
        1500,
        refresh_agent_status
    )


def start_ssh_agent():
    """
    Create a temporary PowerShell script and run it elevated.
    The PowerShell window stays open so errors can be read.
    """

    import tempfile

    script = r'''
$ErrorActionPreference = "Stop"

try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Starting Windows SSH Agent" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    $service = Get-Service ssh-agent -ErrorAction Stop

    Write-Host "Current service status: $($service.Status)"
    Write-Host "Current startup type:   $($service.StartType)"
    Write-Host ""

    if ($service.StartType -ne "Automatic") {
        Write-Host "Setting startup type to Automatic..."
        Set-Service ssh-agent -StartupType Automatic -ErrorAction Stop
    }

    if ($service.Status -ne "Running") {
        Write-Host "Starting ssh-agent service..."
        Start-Service ssh-agent -ErrorAction Stop
    }

    $service = Get-Service ssh-agent -ErrorAction Stop

    if ($service.Status -ne "Running") {
        throw "ssh-agent service is still not running."
    }

    Write-Host ""
    Write-Host "ssh-agent service is running." -ForegroundColor Green

    # SSH key
    $key = "$env:USERPROFILE\.ssh\harmony3_vps"

    Write-Host ""
    Write-Host "Checking SSH key:"
    Write-Host $key

    if (-not (Test-Path $key)) {
        throw "SSH private key not found: $key"
    }

    if (-not (Test-Path "$key.pub")) {
        throw "SSH public key not found: $key.pub"
    }

    # Get key fingerprint
    $fingerprint = (
        ssh-keygen -lf "$key.pub" |
        ForEach-Object {
            ($_ -split '\s+')[1]
        }
    )

    Write-Host ""
    Write-Host "Key fingerprint: $fingerprint"

    # Check whether key is already loaded
    Write-Host ""
    Write-Host "Checking loaded SSH keys..."

    $loaded = ssh-add -l 2>$null

    if ($loaded -match [regex]::Escape($fingerprint)) {

        Write-Host ""
        Write-Host "SSH key is already loaded." -ForegroundColor Green

    }
    else {

        Write-Host ""
        Write-Host "SSH key is not loaded."
        Write-Host "Loading key..."

        ssh-add $key

        if ($LASTEXITCODE -ne 0) {
            throw "ssh-add failed with exit code $LASTEXITCODE."
        }

        Write-Host ""
        Write-Host "SSH key loaded successfully." -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "SSH agent is ready." -ForegroundColor Green
    Write-Host "Harmony3 Docker access is ready." -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "ERROR" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Detailed error:" -ForegroundColor Yellow
    Write-Host ($_ | Out-String) -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Press ENTER to close this window." -ForegroundColor Cyan
Write-Host "========================================"

Read-Host
'''

    try:
        # Create a temporary PowerShell script.
        fd, script_path = tempfile.mkstemp(
            suffix=".ps1",
            prefix="harmony3_ssh_agent_",
            text=True
        )

        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(script)

        # Launch the script elevated.
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "Start-Process powershell.exe "
                    "-Verb RunAs "
                    "-ArgumentList "
                    f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{script_path}'"
                )
            ]
        )

    except Exception as error:
        messagebox.showerror(
            "SSH Agent",
            f"Could not start elevated PowerShell.\n\n{error}"
        )



def stop_ssh_agent():
    """
    Stop the Windows SSH Authentication Agent service
    using an elevated PowerShell window.
    """

    command = r'''
try {
    Stop-Service ssh-agent -ErrorAction Stop

    Write-Host ""
    Write-Host "SSH agent has been stopped successfully." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "Failed to stop SSH agent:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host ""
'''

    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "Start-Process powershell.exe "
                    "-Verb RunAs "
                    "-ArgumentList "
                    "'-NoProfile','-ExecutionPolicy','Bypass','-Command',"
                    f"'{command.replace(chr(39), chr(39) + chr(39))}'"
                )
            ]
        )

    except Exception as error:
        messagebox.showerror(
            "SSH Agent",
            f"Could not start elevated PowerShell.\n\n{error}"
        )

# ============================================================
# Start tunnel
# ============================================================

def start_tunnel():
    print("=== START TUNNEL BUTTON CLICKED ===", flush=True)

    try:
        print("starting =", starting, flush=True)

        pid = get_existing_tunnel_pid()
        print("existing PID =", pid, flush=True)

        print("About to start worker...", flush=True)

        threading.Thread(
            target=start_tunnel_worker,
            daemon=True
        ).start()

        print("Worker thread created.", flush=True)

    except Exception as error:
        print("START_TUNNEL ERROR:", repr(error), flush=True)
        messagebox.showerror(
            "Start Tunnel Error",
            repr(error)
        )



def start_tunnel_worker():
    global starting

    log_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "harmony3_tunnel.log"
    )

    process = None

    try:
        with open(log_path, "w", encoding="utf-8") as log:

            def log_write(text):
                log.write(text + "\n")
                log.flush()

            log_write("=== Harmony3 Connect SSH Tunnel ===")
            log_write(f"Python PID: {os.getpid()}")
            log_write("")

            # Find ssh.exe
            ssh_path = find_ssh()

            log_write(f"ssh.exe: {ssh_path}")

            if not ssh_path:
                raise RuntimeError(
                    "ssh.exe could not be found."
                )

            # Build command
            command = [
                ssh_path,
                "-N",
                "-o", "BatchMode=yes",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "harmony3-portainer",
            ]

            log_write("")
            log_write("Command:")
            log_write(" ".join(command))
            log_write("")

            # Start SSH
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            log_write(f"SSH PID: {process.pid}")
            log_write("SSH process started.")
            log_write("")

            deadline = time.time() + STARTUP_TIMEOUT

            while time.time() < deadline:

                # SSH exited
                if process.poll() is not None:

                    stdout, stderr = process.communicate()

                    log_write(
                        f"SSH exited with code: {process.returncode}"
                    )

                    log_write("")
                    log_write("STDOUT:")
                    log_write(stdout or "(empty)")

                    log_write("")
                    log_write("STDERR:")
                    log_write(stderr or "(empty)")

                    error = (
                        stderr.strip()
                        or stdout.strip()
                        or f"SSH exited with code {process.returncode}."
                    )

                    raise RuntimeError(
                        "SSH tunnel failed.\n\n"
                        + error
                    )

                # Check tunnel port
                if port_is_open(
                    LOCAL_HOST,
                    LOCAL_PORT
                ):
                    log_write(
                        f"Tunnel is listening on "
                        f"{LOCAL_HOST}:{LOCAL_PORT}"
                    )

                    log_write("SUCCESS")

                    root.after(
                        0,
                        lambda: status_label.config(
                            text="●  Portainer tunnel: Running",
                            fg="#2ecc71"
                        )
                    )

                    return

                time.sleep(CHECK_INTERVAL)

            # Timeout
            log_write("")
            log_write("SSH did not establish the tunnel before timeout.")

            if process.poll() is None:
                process.terminate()

            stdout, stderr = process.communicate()

            log_write("")
            log_write("STDOUT:")
            log_write(stdout or "(empty)")

            log_write("")
            log_write("STDERR:")
            log_write(stderr or "(empty)")

            error = (
                stderr.strip()
                or stdout.strip()
                or "No SSH error was reported."
            )

            raise RuntimeError(
                "SSH tunnel did not start within "
                f"{STARTUP_TIMEOUT} seconds.\n\n"
                + error
            )

    except Exception as error:

        error_text = str(error)

        try:
            with open(
                log_path,
                "a",
                encoding="utf-8"
            ) as log:
                log.write("")
                log.write("\n=== PYTHON ERROR ===\n")
                log.write(error_text)
                log.write("\n")
        except Exception:
            pass

        def show_tunnel_error():
            messagebox.showerror(
                "Harmony3 Connect - SSH Tunnel",
                error_text
                + "\n\n"
                + f"Full log:\n{log_path}"
            )

            status_label.config(
                text="●  Portainer tunnel: Stopped",
                fg="#e74c3c"
            )

        root.after(
            0,
            show_tunnel_error
        )

    finally:
        starting = False

        def finish_ui():
            update_status()

            start_button.config(
                state="normal"
            )

            stop_button.config(
                state="normal"
            )

            open_button.config(
                state="normal"
            )

        root.after(
            0,
            finish_ui
        )

# ============================================================
# Stop tunnel
# ============================================================

def stop_tunnel():
    
    print("START_TUNNEL_WORKER CALLED", flush=True)
    
    global tunnel_process

    pid = get_existing_tunnel_pid()

    if pid is None:
        update_status()
        return

    try:

        subprocess.run(
            [
                "taskkill",
                "/PID",
                str(pid),
                "/T",
                "/F"
            ],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

    except Exception as error:

        messagebox.showerror(
            "Stop failed",
            str(error)
        )

        return

    tunnel_process = None

    time.sleep(0.3)

    update_status()


# ============================================================
# Open Portainer
# ============================================================

def open_portainer():

    if get_existing_tunnel_pid() is None:

        messagebox.showwarning(
            "Tunnel is stopped",
            "Start the Portainer tunnel first."
        )

        return

    webbrowser.open(
        f"https://localhost:{LOCAL_PORT}"
    )


# ============================================================
# Error handling
# ============================================================

def format_error(error):

    error = error.strip()

    if "Permission denied" in error:

        return (
            error
            + "\n\n"
            "SSH authentication failed.\n"
            "Make sure harmony3_vps is loaded "
            "in ssh-agent."
        )

    if "Could not resolve hostname" in error:

        return (
            error
            + "\n\n"
            "Check the harmony3-portainer entry "
            "in your SSH config."
        )

    if "bind" in error.lower():

        return (
            error
            + "\n\n"
            f"Local port {LOCAL_PORT} may already "
            "be in use."
        )

    if "Connection refused" in error:

        return (
            error
            + "\n\n"
            "The VPS refused the SSH connection."
        )

    if "Host key verification failed" in error:

        return (
            error
            + "\n\n"
            "The VPS host key could not be verified."
        )

    return error


def show_error(message):

    status_label.config(
        text="●  Failed",
        fg="#e74c3c"
    )

    start_button.config(
        state="normal"
    )

    stop_button.config(
        state="disabled"
    )

    open_button.config(
        state="disabled"
    )

    messagebox.showerror(
        f"{APP_NAME} - Error",
        message
    )



# ============================================================
# GUI
# ============================================================

root = tk.Tk()

root.title(APP_NAME)
root.geometry("460x350")
root.resizable(False, False)

root.update_idletasks()

width = root.winfo_width()
height = root.winfo_height()

x = (root.winfo_screenwidth() - width) // 2
y = (root.winfo_screenheight() - height) // 2

root.geometry(
    f"{width}x{height}+{x}+{y}"
)


# ============================================================
# Title
# ============================================================

title_label = tk.Label(
    root,
    text=APP_NAME,
    font=("Segoe UI", 16, "bold")
)

title_label.pack(
    pady=(18, 8)
)


# ============================================================
# SSH Agent section
# ============================================================

agent_frame = tk.Frame(root)

agent_frame.pack(
    pady=(0, 15)
)


agent_status_label = tk.Label(
    agent_frame,
    text="●  SSH Agent: Checking...",
    font=("Segoe UI", 10)
)

agent_status_label.pack(
    pady=(0, 7)
)


agent_button_frame = tk.Frame(agent_frame)

agent_button_frame.pack()


start_agent_button = tk.Button(
    agent_button_frame,
    text="Start SSH Agent",
    width=16,
    height=2,
    command=start_ssh_agent
)

start_agent_button.grid(
    row=0,
    column=0,
    padx=3
)


stop_agent_button = tk.Button(
    agent_button_frame,
    text="Stop SSH Agent",
    width=16,
    height=2,
    command=stop_ssh_agent
)

stop_agent_button.grid(
    row=0,
    column=1,
    padx=3
)


# ============================================================
# Portainer status
# ============================================================

status_label = tk.Label(
    root,
    text="●  Checking...",
    font=("Segoe UI", 11)
)

status_label.pack(
    pady=(0, 15)
)


# ============================================================
# Tunnel buttons
# ============================================================

button_frame = tk.Frame(root)

button_frame.pack()


start_button = tk.Button(
    button_frame,
    text="Start",
    width=13,
    height=2,
    command=start_tunnel
)

start_button.grid(
    row=0,
    column=0,
    padx=5
)


stop_button = tk.Button(
    button_frame,
    text="Stop",
    width=13,
    height=2,
    command=stop_tunnel
)

stop_button.grid(
    row=0,
    column=1,
    padx=5
)

# ============================================================
# Open Portainer
# ============================================================

open_button = tk.Button(
    root,
    text="Open Portainer",
    width=29,
    height=2,
    command=open_portainer
)

open_button.pack(
    pady=18
)


# ============================================================
# Tunnel status
# ============================================================

def apply_status(pid):

    if pid is not None:

        status_label.config(
            text=f"●  Portainer tunnel is running  (PID {pid}) (PORT:{LOCAL_PORT})",
            fg="#2ecc71"
        )

        start_button.config(
            state="disabled"
        )

        stop_button.config(
            state="normal"
        )

        open_button.config(
            state="normal"
        )

    elif not starting:

        status_label.config(
            text="●  Portainer tunnel is stopped",
            fg="#e74c3c"
        )

        start_button.config(
            state="normal"
        )

        stop_button.config(
            state="disabled"
        )

        open_button.config(
            state="disabled"
        )


def refresh_status():

    def worker():

        pid = get_existing_tunnel_pid()

        root.after(
            0,
            lambda: apply_status(pid)
        )

    threading.Thread(
        target=worker,
        daemon=True
    ).start()

    root.after(
        1500,
        refresh_status
    )


def update_status():
    apply_status(
        get_existing_tunnel_pid()
    )


# ============================================================
# Start
# ============================================================

root.after(
    100,
    refresh_status
)

root.after(
    100,
    refresh_agent_status
)

root.mainloop()
