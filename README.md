# Harmony3 Connect

An app for opening SSH tunnel to a server using preconfigured SSH Keys. The app starts or stops the Windows OpenSSH Authentication Agent which starts and maintains the SSH tunnels and port-forwarding used by the connection. The Portainer web interface of the server is mapped to a specific port and accesibble through localhost. [Portainer](https://github.com/portainer/portainer)

*Useful for not having to activate tunnelling manually and for moderating Docker containers in the remote server.*

## Requirements

- Windows with OpenSSH Client (`ssh.exe`) installed and available in `PATH`
- Python 3
- An SSH host config entry and SSH keys ready in `%USERPROFILE%\.ssh\`.
- Portainer reachable from the localhost on `LOCAL_PORT` using the SSH tunneling

### SSH configuration

Example entry of `%USERPROFILE%\.ssh\config` (create the file if it does not exist):

```sshconfig
Host harmony3
    HostName [server ip]
    User [server user]
    IdentityFile ~/.ssh/harmony3_vps
    IdentitiesOnly yes

Host harmony3-portainer
    HostName [server ip]
    User [server user]
    IdentityFile ~/.ssh/harmony3_vps
    IdentitiesOnly yes
    LocalForward 19443 localhost:9443
```

`LocalForward` maps your computer's `localhost:19443` to `localhost:9443` as seen from the SSH server. If Portainer listens on a different address or port on the server, adjust the destination in `LocalForward` accordingly.

The private keys must be located inside the `~/.ssh/` and `IdentityFile` must be adjusted for your use-case; The app connects using the alias `SSH_HOST` which is `harmony3-portainer` in the example. the app's SSH Agent controls can start the Windows `ssh-agent` service and load that key. The Start Tunnel action uses non-interactive SSH authentication, so make sure the key is available to OpenSSH before starting the tunnel.

The `SSH_HOST` and `LOCAL_PORT` environment variables are stored inside the pyw file for modularity and can be adjusted to your use-case.

## Run

You can open `harmony-portainer.pyw` directly if `.pyw` files are associated with Python on your system.

Or from terminal:

```powershell
python .\harmony-portainer.pyw
```

![Harmony3 Connect screenshot](https://pub-55a8605bd8ee494ab002c0bb70e15fed.r2.dev/Harmony3%20Connect/pythonw_FkJ8GZiX38.png)

## Use

1. Start the SSH Agent and load the key if it is not already running and loaded. These actions may request administrator permission.
2. Select **Start** to establish the SSH tunnel.
3. Select **Open Portainer** to open `https://localhost:19443` in your browser.
4. Select **Stop** to close the tunnel process.

The app periodically checks the agent and tunnel status. Tunnel startup diagnostics are written to `harmony3_tunnel.log` beside the application.

## Troubleshooting

- **Could not resolve hostname:** Check the `harmony3-portainer` entry in your SSH config.
- **Permission denied:** Confirm the key path is correct and the key is loaded in `ssh-agent`.
- **Local port is already in use:** Close the process using port `19443`, or change the local port in both `LocalForward` and the app's `LOCAL_PORT` setting.
- **Tunnel starts but Portainer does not load:** Verify Portainer is reachable from the SSH server at the destination configured by `LocalForward` and that it uses HTTPS as expected.

## Security

The SSH client uses the normal host-key verification configured on your machine.
