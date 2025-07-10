"""
requirements: paramiko
"""
import paramiko
import os
import tempfile
import uuid
from typing import Literal, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- Global state for pending actions (for human validation) ---
_pending_actions: Dict[str, Dict[str, Any]] = {}

# --- Helper Functions ---
def _validate_path(path: str, allowed_prefixes: Optional[list] = None) -> bool:
    """Basic path validation to prevent directory traversal and unauthorized access."""
    if ".." in path or "\0" in path:
        return False
    if allowed_prefixes:
        if not any(path.startswith(p) for p in allowed_prefixes):
            return False
    return True

# --- Main Tools Class ---
class Tools:
    class Valves(BaseModel):
        """Configuration settings for the SSH Server Management Tool."""
        SSH_HOST: str = Field(default=os.environ.get("SSH_HOST", "your.remote.server.ip"), description="The hostname or IP address of the remote server.")
        SSH_USERNAME: str = Field(default=os.environ.get("SSH_USERNAME", "svc_llm_ssh"), description="The dedicated SSH username for this tool.")
        SSH_KEY_PATH: Optional[str] = Field(default=os.environ.get("SSH_KEY_PATH", "/app/backend/data/keys/id_rsa"), description="The absolute path to the SSH private key inside the OpenWebUI container.")

    def __init__(self):
        self.valves = self.Valves()

    def _get_ssh_client(self):
        """Establishes and returns an SSH client connection using valve settings."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            key_path_expanded = os.path.expanduser(self.valves.SSH_KEY_PATH)
            client.connect(hostname=self.valves.SSH_HOST, username=self.valves.SSH_USERNAME, key_filename=key_path_expanded, timeout=10)
            return client
        except Exception as e:
            raise Exception(f"Failed to establish SSH connection: {e}")

    def _run_remote_command(self, command: str, working_dir: Optional[str] = None) -> str:
        """Executes a command on the remote server, optionally in a specific directory."""
        try:
            client = self._get_ssh_client()
            if working_dir:
                command = f"cd {working_dir} && {command}"
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode("utf-8").strip()
            error = stderr.read().decode("utf-8").strip()
            client.close()
            if error and "sudo" not in error:
                return f"Error executing command:\nSTDOUT:\n{output}\nSTDERR:\n{error}"
            return output if output else error
        except Exception as e:
            return f"Failed to run command '{command}': {e}"

    def _read_remote_file_content(self, remote_path: str) -> str:
        """Reads content of a file from remote server via SFTP."""
        try:
            client = self._get_ssh_client()
            sftp = client.open_sftp()
            with sftp.open(remote_path, "r") as f:
                content = f.read().decode("utf-8")
            sftp.close()
            client.close()
            return content
        except Exception as e:
            return f"Error reading file '{remote_path}': {e}"

    def _write_remote_file_content(self, remote_path: str, content: str) -> str:
        """Writes content to a file on remote server via SFTP."""
        try:
            client = self._get_ssh_client()
            sftp = client.open_sftp()
            temp_remote_path = f"/tmp/{os.path.basename(remote_path)}.tmp_{uuid.uuid4().hex}"
            with sftp.open(temp_remote_path, "w") as f:
                f.write(content)
            sftp.close()
            move_command = f"sudo mv {temp_remote_path} {remote_path}"
            result = self._run_remote_command(move_command)
            if "Error" in result:
                self._run_remote_command(f"rm {temp_remote_path}")
                return f"Error moving temporary file: {result}"
            return f"Successfully updated {remote_path}."
        except Exception as e:
            return f"Error writing file {remote_path}: {e}"

    # --- Tool Definitions ---

    def read_docker_container_logs(self, container_name: str, lines: int = 100) -> str:
        """Reads the latest logs from a specified Docker container."""
        command = f"docker logs {container_name} --tail {lines}"
        return self._run_remote_command(command)

    def read_docker_compose_logs(self, service_name: str, lines: int = 100, compose_project_dir: str = "/opt/iot-stack") -> str:
        """Reads the latest logs for a specific service from docker-compose."""
        command = f"docker-compose logs --tail={lines} {service_name}"
        return self._run_remote_command(command, working_dir=compose_project_dir)

    def list_docker_compose_containers(self, compose_project_dir: str = "/opt/iot-stack") -> str:
        """Lists container status from a docker-compose file."""
        command = "docker-compose ps"
        return self._run_remote_command(command, working_dir=compose_project_dir)

    def docker_compose_action(self, action: Literal["up", "down", "restart", "pull"], compose_project_dir: str = "/opt/iot-stack") -> str:
        """Performs a docker-compose action."""
        command = f"docker-compose {action}"
        return self._run_remote_command(command, working_dir=compose_project_dir)

    def read_docker_compose_file(self, compose_project_dir: str = "/opt/iot-stack") -> str:
        """Reads the content of a docker-compose file."""
        compose_file_path = os.path.join(compose_project_dir, "docker-compose.yml")
        return self._read_remote_file_content(compose_file_path)

    def read_crontab(self, username: str) -> str:
        """Reads the crontab entries for a specific user."""
        command = f"sudo crontab -u {username} -l"
        return self._run_remote_command(command)
    
    def read_nginx_config(self, config_path: str = "/opt/iot-stack/volumes/nginx/conf/app.conf") -> str:
        """Reads a specified Nginx configuration file from the project volume."""
        return self._read_remote_file_content(config_path)

    def propose_nginx_config_update(self, proposed_content: str, config_path: str = "/opt/iot-stack/volumes/nginx/conf/app.conf") -> str:
        """Proposes an update for an Nginx configuration file."""
        action_id = str(uuid.uuid4())
        _pending_actions[action_id] = {"type": "nginx_config_update", "file_path": config_path, "content": proposed_content}
        return f"Proposed Nginx config update stored. To apply, say: 'Apply change {action_id}'."

    def apply_pending_change(self, action_id: str, nginx_container_name: str = "nginx") -> str:
        """
        Applies a pending proposed change.
        Args:
            action_id: The ID of the pending change to apply.
            nginx_container_name: The name of the Nginx container, required if applying an Nginx update.
        """
        if action_id not in _pending_actions:
            return f"Error: No pending change found with ID '{action_id}'."
        action_details = _pending_actions.pop(action_id)
        action_type = action_details.get("type")
        file_path = action_details.get("file_path")
        content = action_details.get("content")

        if action_type == "nginx_config_update":
            result = self._write_remote_file_content(file_path, content)
            if "Successfully updated" in result:
                validation_command = f"sudo docker exec {nginx_container_name} nginx -t"
                validation_output = self._run_remote_command(validation_command)
                if "syntax is ok" not in validation_output and "test is successful" not in validation_output:
                     return f"Nginx config updated, but validation failed: {validation_output}."
                reload_command = f"sudo docker exec {nginx_container_name} nginx -s reload"
                reload_output = self._run_remote_command(reload_command)
                if "Error" in reload_output:
                    return f"Nginx config updated and validated, but reload failed: {reload_output}."
                return f"Successfully applied update to '{file_path}', validated, and Nginx reloaded."
            return f"Failed to apply Nginx config update: {result}"
        else:
            # Handle other action types here if you add more
            return f"Unknown or unhandled action type '{action_type}'."
