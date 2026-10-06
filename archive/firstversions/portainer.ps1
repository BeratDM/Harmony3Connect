````powershell
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Configuration
$TunnelName = "harmony3-portainer"
$LocalPort = 19443

# Create window
$form = New-Object System.Windows.Forms.Form
$form.Text = "Portainer Manager"
$form.Size = New-Object System.Drawing.Size(360, 220)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox = $false

# Status label
$status = New-Object System.Windows.Forms.Label
$status.Location = New-Object System.Drawing.Point(20, 20)
$status.Size = New-Object System.Drawing.Size(310, 30)
$status.Font = New-Object System.Drawing.Font("Segoe UI", 11)
$form.Controls.Add($status)

# Find only our Portainer SSH tunnel
function Get-PortainerTunnel {
    Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" |
        Where-Object {
            $_.CommandLine -like "*$TunnelName*"
        }
}

function Update-Status {
    $process = Get-PortainerTunnel

    if ($process) {
        $status.Text = "● Portainer tunnel: RUNNING"
        $status.ForeColor = [System.Drawing.Color]::Green
    }
    else {
        $status.Text = "● Portainer tunnel: STOPPED"
        $status.ForeColor = [System.Drawing.Color]::Red
    }
}

# Start button
$start = New-Object System.Windows.Forms.Button
$start.Text = "Start"
$start.Location = New-Object System.Drawing.Point(20, 65)
$start.Size = New-Object System.Drawing.Size(145, 40)

$start.Add_Click({
    if (-not (Get-PortainerTunnel)) {
        Start-Process `
            -FilePath "ssh.exe" `
            -ArgumentList "-N", $TunnelName `
            -WindowStyle Hidden
    }

    Start-Sleep -Milliseconds 500
    Update-Status
})

$form.Controls.Add($start)

# Stop button
$stop = New-Object System.Windows.Forms.Button
$stop.Text = "Stop"
$stop.Location = New-Object System.Drawing.Point(185, 65)
$stop.Size = New-Object System.Drawing.Size(145, 40)

$stop.Add_Click({
    $process = Get-PortainerTunnel

    if ($process) {
        $process | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force
        }
    }

    Update-Status
})

$form.Controls.Add($stop)

# Open Portainer button
$open = New-Object System.Windows.Forms.Button
$open.Text = "Open Portainer"
$open.Location = New-Object System.Drawing.Point(20, 120)
$open.Size = New-Object System.Drawing.Size(310, 40)

$open.Add_Click({
    Start-Process "https://localhost:$LocalPort"
})

$form.Controls.Add($open)

# Initial status
Update-Status

# Keep status updated
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({
    Update-Status
})
$timer.Start()

# Show window
[void]$form.ShowDialog()

### Make it double-clickable

Windows may not execute `.ps1` files by double-clicking depending on your settings. The easiest solution is to create a shortcut.

Right-click your desktop → **New → Shortcut**, and use:

```text
powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\Portainer Manager.ps1"
````

Then name it:

**Portainer Manager**

You'll have a little window:

```text
┌──────────────────────────────────┐
│ Portainer Manager                │
│                                  │
│ ● Portainer tunnel: STOPPED     │
│                                  │
│ [       Start       ][   Stop   ]│
│                                  │
│ [       Open Portainer          ]│
└──────────────────────────────────┘
```

The important part is that the Stop button searches for an `ssh.exe` whose command line specifically contains **`harmony3-portainer`**, so it won't kill your normal `ssh harmony3` sessions.
