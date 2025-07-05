#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
import sys
import json
import socket
import traceback
import threading

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
from gi.repository import GLib

def N_(message): return message
def _(message): return GLib.dgettext(None, message)


def exec_and_get_results(command, context):
    buffer = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = buffer
    exec(command, context)
    sys.stdout = original_stdout
    output = buffer.getvalue()
    return output


class MCPPlugin(Gimp.PlugIn):
    def __init__(self, host='localhost', port=9877):
        super().__init__()
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        self.context = {}
        exec("from gi.repository import Gimp", self.context)
        self.auto_disconnect_client = True

    def do_query_procedures(self):
        """Register the plugin procedure."""
        return ["plug-in-mcp-server"]

    def do_create_procedure(self, name):
        """Define the procedure properties."""
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, self.run, None)
        procedure.set_menu_label(_("Start MCP Server"))
        procedure.set_documentation(_("Starts an MCP server to control GIMP externally"),
                                    _("Starts an MCP server to control GIMP externally"),
                                    name)
        procedure.set_attribution("Your Name", "Your Name", "2023")
        procedure.add_menu_path('<Image>/Tools/')
        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        """Run the plugin and start the server."""
        if self.running:
            print("MCP Server is already running")
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

        self.running = True

        try:
            print("Creating socket...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)

            print(f"GimpMCP server started on {self.host}:{self.port}")

            while self.running:
                client, address = self.socket.accept()
                print(f"Connected to client: {address}")

                # Handle client in a separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client,)
                )
                client_thread.daemon = True
                client_thread.start()
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

        except Exception as e:
            print(f"Error starting server: {str(e)}")
            self.running = False

            if self.socket:
                self.socket.close()
                self.socket = None

            if self.server_thread:
                self.server_thread.join(timeout=1.0)
                self.server_thread = None

            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    def _handle_client(self, client):
        """Handle connected client"""
        # print("Client handler started")
        buffer = b''

        data = client.recv(4096)
        # print(f"Received data: {data}")
        if not data:
            print("Client disconnected")
            return

        buffer += data
        if isinstance(data, (bytes, bytearray)):
            request = str(buffer, "utf-8")
        else:
            request = buffer.decode('utf-8')
        # print(f"Parsed request: {request}")
        response = self.execute_command(request)
        print(f"response: {response}")
        if isinstance(response, dict):
            response = json.dumps(response)
        client.sendall(response.encode('utf-8'))
        if self.auto_disconnect_client:
            client.close()
        return

    def execute_command(self, request):
        """Execute commands in GIMP's main thread."""
        try:
            # print("command", request)
            if request == "disable_auto_disconnect":
                self.auto_disconnect_client = False
                return {
                    "status": "success",
                    "results": "OK"
                }
            j = json.loads(request)
            if "cmds" in j:
                a = ['python-fu-exec', j["cmds"]]
            else:
                p = j["params"]
                a = p['args']
            if a[0] == 'python-fu-eval':
                if len(a) > 0:
                    print(f"evaluating exprs: {a[1]}")
                    vals = [str(eval(e)) for e in a[1]]
                    results = {
                        "status": "success",
                        "results": vals
                    }
                else:
                    results = {
                    "status": "success",
                    "results": "[NULL]"
                }
                print(f"expression result: {results}")
                return results
            else:
                outputs = ["OK"]
                if len(a) > 0:
                    print(f"Executing commands: {a[1]}")
                    outputs = [exec_and_get_results(c, self.context) for c in a[1]]
                else:
                    print(f"no command to execute")
                result = {
                    "status": "success",
                    "results": outputs
                }

                print(f"Command result: {result}")
                return result

        except Exception as e:
            error_msg = f"Error executing command: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            }

Gimp.main(MCPPlugin.__gtype__, sys.argv)
