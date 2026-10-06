# Start Windows SSH Agent
$service = Get-Service ssh-agent

if ($service.StartType -ne "Automatic") {
    Set-Service ssh-agent -StartupType Automatic
}

if ($service.Status -ne "Running") {
    Start-Service ssh-agent
}

# SSH key
$key = "$env:USERPROFILE\.ssh\harmony3_vps"

# Check whether the key is already loaded
$loaded = ssh-add -l 2>$null
if ($loaded -notmatch [regex]::Escape((ssh-keygen -lf "$key.pub" | ForEach-Object { ($_ -split ' ')[1] }))) {
    ssh-add $key
}

Write-Host "SSH agent is ready. Harmony3 Docker access is ready."
Read-Host "Press a button to continue"
