# OpenWebUI SSH Server Manager Tool 🤖

This is a powerful tool for [OpenWebUI](https://github.com/open-webui/open-webui) that allows an LLM to safely interact with a remote server via SSH to perform various system administration tasks.

---
## 📋 Features

-   **Docker Compose Management**: List services (`ps`), start (`up`), stop (`down`), `pull` images, and `restart` services.
-   **Log Reading**: Read logs from individual Docker containers or specific `docker-compose` services.
-   **Configuration Editing**: Read and propose changes to Nginx configuration files and user crontabs.
-   **Safe by Design**: Implements a human-in-the-loop confirmation step (`apply_pending_change`) for all write operations, preventing the LLM from making unauthorized changes.
-   **Secure**: Operates through a dedicated, low-privilege SSH user with very specific, passwordless `sudo` commands.

---
## ⚙️ Prerequisites

-   A running OpenWebUI instance (preferably via Docker).
-   A remote Linux server with SSH access and `sudo` privileges for the initial setup.
-   The following software installed on the remote server: `docker`, `docker-compose`, `nginx`.
-   A Docker Compose project you wish to manage, located on the remote server.

---
## 🚀 Setup Instructions

This setup is divided into two parts: configuring the remote server and configuring OpenWebUI.

### **Step 1: Remote Server Setup**

These commands create a dedicated service user and configure the exact permissions needed for the tool to function.

#### **1a. Create a Dedicated Service User and Group**
Create a group and a non-human service user named `svc_llm_ssh`. This user will have a real shell to execute commands but is secured by key-only authentication.

```bash
sudo groupadd svc_llm_group
sudo useradd -s /bin/bash -g svc_llm_group -m -d /home/svc_llm_ssh svc_llm_ssh
```

#### **1b. Configure Passwordless Sudo**
This is the most critical step. Use `sudo visudo` to open the `sudoers` file and add the following lines at the end. These rules grant the `svc_llm_ssh` user permission to run *only* the specific commands required by the tool, without a password.

**Note**: The paths to commands (`/usr/bin/docker`, etc.) and the project (`/opt/iot-stack`) should be adjusted to match your environment. Use `which <command>` to verify command paths.

```
# Command Aliases for the svc_llm_ssh user
Cmnd_Alias DOCKER_COMMANDS = /usr/bin/docker exec * cat /var/log/nginx/access.log, /usr/bin/docker exec * cat /var/log/nginx/error.log
Cmnd_Alias FILE_COMMANDS = /usr/bin/mv /tmp/* /opt/iot-stack/volumes/nginx/conf/app.conf
Cmnd_Alias CRON_COMMANDS = /usr/bin/crontab -u * -l, /usr/bin/crontab -u * /tmp/*
Cmnd_Alias NGINX_COMMANDS = /usr/bin/docker exec * nginx -t, /usr/bin/docker exec * nginx -s reload

# Allow the svc_llm_ssh user to run the specific commands without a password
svc_llm_ssh ALL=(ALL) NOPASSWD: DOCKER_COMMANDS, FILE_COMMANDS, CRON_COMMANDS, NGINX_COMMANDS
```

#### **1c. Set Up SSH Key Authentication**
Disable password login for this user and only allow SSH key access.

```bash
# Switch to the new user to create the files with the right ownership
sudo -u svc_llm_ssh bash

# Create the .ssh directory and authorized_keys file
mkdir ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# Now, paste the PUBLIC key you will use for OpenWebUI into this file
# For example: nano ~/.ssh/authorized_keys

# Exit back to your main user
exit
```

#### **1d. Configure Docker Group Permissions**
To allow the tool to run `docker` and `docker-compose` commands without `sudo`, add the `svc_llm_ssh` user to the `docker` group.

```bash
sudo usermod -aG docker svc_llm_ssh
sudo systemctl restart docker
```

#### **1e. Grant Access to Project Directory**
The service user needs permission to access your project folder. We recommend placing your project in `/opt` for system services.

```bash
# Example: Your project is in /opt/iot-stack
# Grant the service user's group ownership of the project
sudo chown -R $USER:svc_llm_group /opt/iot-stack
# Set permissions so the group can read/execute
sudo chmod -R 775 /opt/iot-stack
```

### **Step 2: OpenWebUI Setup**

#### **2a. Place the Tool Script**
In your OpenWebUI instance, navigate to the `data` volume. You can find its location by running `docker volume inspect open-webui`. Inside that volume, create a directory `tools/ssh_server_manager` and place the `tool.py` script from this repository inside it.

The final path should look something like: `.../_data/open-webui/data/tools/ssh_server_manager/tool.py`

ALTERNATIVE: Use the UI to add a Tool in the Workspace section, using the ssh_server_manager.py content

#### **2b. Place the SSH Private Key**
Place the **private** SSH key (e.g., `id_rsa` or `id_ed25519`) that corresponds to the public key you authorized in a location accessible to OpenWebUI. A recommended place is `.../_data/open-webui/data/keys/id_rsa`.

#### **2c. Configure the Tool in the UI**
1.  Restart OpenWebUI.
2.  Go to **Settings > Tools** and enable the "SSH Server Manager" tool.
3.  Click the gear icon to configure its "Valves" (settings):
    * **`SSH_HOST`**: The IP address of your remote server.
    * **`SSH_USERNAME`**: Set this to `svc_llm_ssh`.
    * **`SSH_KEY_PATH`**: The path *inside the container* to your private key. E.g., `/app/backend/data/keys/id_rsa`.

---
## 💬 How to Use

You can now chat with the LLM to manage your server.

**Examples:**
-   "List the containers in the `/opt/iot-stack` project."
-   "Read the crontab for the user `www-data`."
-   "Show me the last 50 lines of the nginx service logs in `/opt/iot-stack`."
-   "Read the nginx config file at `/opt/iot-stack/volumes/nginx/conf/app.conf`."
-   "Propose a change to my nginx config to add a new rate limit."
-   (LLM proposes a change and gives you an ID) -> "This looks good, apply change `[action_id]` for the `nginx` container."

---
## ⚠️ Security Considerations

-   **Principle of Least Privilege**: The `sudoers` configuration is intentionally specific. Do not broaden the rules unless necessary.
-   **Private Key Security**: The SSH private key is the key to this setup. Ensure its file permissions are strict and it is not publicly exposed.
-   **Review Changes**: Always carefully review changes proposed by the LLM before telling it to apply them.

---
## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
