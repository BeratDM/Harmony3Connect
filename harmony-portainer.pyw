import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox
import webbrowser


# ============================================================
# Configuration
# ============================================================

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


def port_is_open():
    try:
        with socket.create_connection(
            (LOCAL_HOST, LOCAL_PORT),
            timeout=0.3
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
# GUI
# ============================================================

root = tk.Tk()

root.title("Portainer Manager")
root.geometry("420x245")
root.resizable(False, False)

root.update_idletasks()

width = root.winfo_width()
height = root.winfo_height()

x = (root.winfo_screenwidth() - width) // 2
y = (root.winfo_screenheight() - height) // 2

root.geometry(f"{width}x{height}+{x}+{y}")


title_label = tk.Label(
    root,
    text="Portainer Manager",
    font=("Segoe UI", 16, "bold")
)

title_label.pack(pady=(18, 8))


status_label = tk.Label(
    root,
    text="●  Checking...",
    font=("Segoe UI", 11)
)

status_label.pack(pady=(0, 18))


button_frame = tk.Frame(root)
button_frame.pack()


start_button = tk.Button(
    button_frame,
    text="Start",
    width=13,
    height=2
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
    height=2
)

stop_button.grid(
    row=0,
    column=1,
    padx=5
)


open_button = tk.Button(
    root,
    text="Open Portainer",
    width=29,
    height=2
)

open_button.pack(pady=18)


# ============================================================
# Status
# ============================================================

def apply_status(pid):
    if pid is not None:

        status_label.config(
            text=f"●  Portainer tunnel is running  (PID {pid})",
            fg="#2ecc71"
        )

        start_button.config(state="disabled")
        stop_button.config(state="normal")
        open_button.config(state="normal")

    elif not starting:

        status_label.config(
            text="●  Portainer tunnel is stopped",
            fg="#e74c3c"
        )

        start_button.config(state="normal")
        stop_button.config(state="disabled")
        open_button.config(state="disabled")


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

    root.after(1500, refresh_status)


def update_status():
    apply_status(get_existing_tunnel_pid())


# ============================================================
# Start tunnel
# ============================================================

def start_tunnel():
    global starting

    if starting:
        return

    if get_existing_tunnel_pid() is not None:
        update_status()
        return

    starting = True

    start_button.config(state="disabled")
    stop_button.config(state="disabled")
    open_button.config(state="disabled")

    status_label.config(
        text="●  Starting SSH tunnel...",
        fg="#f39c12"
    )

    threading.Thread(
        target=start_tunnel_worker,
        daemon=True
    ).start()


def start_tunnel_worker():
    global tunnel_process
    global starting

    try:
        ssh = find_ssh()

        command = [
            ssh,
            "-N",
            "-o", "BatchMode=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            SSH_HOST
        ]

        tunnel_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        deadline = time.monotonic() + STARTUP_TIMEOUT

        while time.monotonic() < deadline:

            if port_is_open():
                starting = False

                root.after(
                    0,
                    update_status
                )

                return

            if tunnel_process.poll() is not None:

                error = tunnel_process.stderr.read().strip()

                if not error:
                    error = (
                        "SSH exited with code "
                        f"{tunnel_process.returncode}."
                    )

                tunnel_process = None
                starting = False

                root.after(
                    0,
                    lambda message=error:
                    show_error(
                        "SSH tunnel failed to start.\n\n"
                        + format_error(message)
                    )
                )

                return

            time.sleep(CHECK_INTERVAL)

        error = ""

        if tunnel_process is not None:

            try:
                error = tunnel_process.stderr.read().strip()
            except Exception:
                pass

            terminate_process(tunnel_process)

        tunnel_process = None
        starting = False

        if error:
            message = (
                "SSH tunnel failed to start.\n\n"
                + format_error(error)
            )
        else:
            message = (
                "SSH tunnel did not become available "
                f"within {STARTUP_TIMEOUT} seconds.\n\n"
                "Check:\n"
                "• ssh-agent is running\n"
                "• harmony3_vps is loaded\n"
                "• harmony3-portainer exists in SSH config\n"
                "• Portainer is running on the VPS\n"
                f"• Port {LOCAL_PORT} is not already in use"
            )

        root.after(
            0,
            lambda: show_error(message)
        )

    except Exception as error:

        tunnel_process = None
        starting = False

        root.after(
            0,
            lambda: show_error(
                "Could not start SSH tunnel.\n\n"
                + str(error)
            )
        )


# ============================================================
# Stop tunnel
# ============================================================

def stop_tunnel():
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

    start_button.config(state="normal")
    stop_button.config(state="disabled")
    open_button.config(state="disabled")

    messagebox.showerror(
        "Portainer SSH Tunnel",
        message
    )


# ============================================================
# Button bindings
# ============================================================

start_button.config(command=start_tunnel)
stop_button.config(command=stop_tunnel)
open_button.config(command=open_portainer)


# ============================================================
# Start
# ============================================================

root.after(100, refresh_status)

root.mainloop()

