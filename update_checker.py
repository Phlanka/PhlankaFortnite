import bpy
import requests
import re
import os
import zipfile
import tempfile
import threading
import addon_utils
import traceback
from bpy.app.handlers import persistent
import time

# Configuration
GITHUB_REPO = "Phlanka/PhlankaFortnite"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_DOWNLOAD_URL = f"https://github.com/{GITHUB_REPO}/releases/download/"

def log_error(message):
    """Log error to Blender's console and print to system console"""
    print(f"PhlankaFortnite ERROR: {message}")
    if bpy.app.debug:
        traceback.print_exc()

class PhlankaUpdateChecker:
    @staticmethod
    def get_addon_version():
        """Get the current addon version"""
        for mod in addon_utils.modules():
            if mod.bl_info.get('name') == "Phlanka Fortnite":  # Note the space in the name
                version_tuple = mod.bl_info.get('version', (0, 0, 0))
                return ".".join(str(x) for x in version_tuple)
        return "0.0.0"
    
    @staticmethod
    def get_latest_version():
        """Get the latest version from GitHub"""
        try:
            response = requests.get(GITHUB_API_URL, timeout=5)
            if response.status_code == 200:
                data = response.json()
                tag_name = data.get('tag_name', '')
                # Extract version number from tag (assuming format V*.*.*)
                match = re.search(r'V?(\d+\.\d+\.\d+)', tag_name)
                if match:
                    return match.group(1), tag_name  # Return both version number and full tag
            return None, None
        except Exception as e:
            print(f"Error checking for updates: {e}")
            return None, None
    
    @staticmethod
    def version_tuple(version_str):
        """Convert version string to tuple for comparison"""
        return tuple(map(int, version_str.split('.')))
    
    @staticmethod
    def is_update_available():
        """Check if an update is available"""
        current_version = PhlankaUpdateChecker.get_addon_version()
        latest_version, tag_name = PhlankaUpdateChecker.get_latest_version()
        
        print(f"Current version: {current_version}, Latest version: {latest_version}")
        
        if not latest_version:
            return False, None, None
        
        # Convert versions to tuples for proper comparison
        current_tuple = PhlankaUpdateChecker.version_tuple(current_version)
        latest_tuple = PhlankaUpdateChecker.version_tuple(latest_version)
        
        # Only return True if the latest version is GREATER than current version
        if latest_tuple > current_tuple:
            return True, latest_version, tag_name
        return False, None, None
    
    @staticmethod
    def download_and_install_update(version, tag_name=None):
        """Download and install the update"""
        # Capture tag_name in the outer function scope
        if not tag_name:
            tag_name = f"V{version}"
        
        # Create a closure that has access to tag_name
        def download_thread(tag_name=tag_name, version=version):
            try:
                # Download the update - use the direct asset URL
                download_url = f"{GITHUB_DOWNLOAD_URL}{tag_name}/PhlankaFortnite.zip"
                print(f"Downloading update from: {download_url}")
                response = requests.get(download_url, stream=True)
                
                if response.status_code != 200:
                    error_msg = f"Failed to download update: HTTP {response.status_code}"
                    log_error(error_msg)
                    bpy.app.timers.register(
                        lambda: show_message_box("Update failed", error_msg), 
                        first_interval=0.1
                    )
                    return
                
                # Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
                    temp_path = temp_file.name
                    print(f"Saving update to temporary file: {temp_path}")
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                
                # Get addon directory - improved method
                addon_dir = None
                
                # First try to get it from the module path
                for mod in addon_utils.modules():
                    if mod.__name__ == "PhlankaFortnite" or mod.__name__.endswith(".PhlankaFortnite"):
                        addon_dir = os.path.dirname(os.path.abspath(mod.__file__))
                        break
                
                # If that fails, try to find it in the addon paths
                if not addon_dir:
                    for path in bpy.utils.script_paths("addons"):
                        potential_path = os.path.join(path, "PhlankaFortnite")
                        if os.path.exists(potential_path):
                            addon_dir = potential_path
                            break
                
                # If still not found, try user addons
                if not addon_dir:
                    user_path = bpy.utils.user_resource('SCRIPTS', path="addons")
                    potential_path = os.path.join(user_path, "PhlankaFortnite")
                    if os.path.exists(potential_path):
                        addon_dir = potential_path
                
                if not addon_dir:
                    error_msg = "Could not locate addon directory. Please update manually."
                    log_error(error_msg)
                    bpy.app.timers.register(
                        lambda: show_message_box("Update failed", error_msg), 
                        first_interval=0.1
                    )
                    return
                
                print(f"Found addon directory: {addon_dir}")
                
                # Extract the zip file
                try:
                    with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                        # The GitHub zip has a root folder with the repo name and tag
                        # We need to extract only the contents to our addon directory
                        root_folder = zip_ref.namelist()[0]  # This is the root folder name
                        print(f"Root folder in zip: {root_folder}")
                        
                        for file in zip_ref.namelist():
                            if file.startswith(root_folder):
                                # Skip the root directory itself
                                if file == root_folder or file.endswith('/'):
                                    continue
                                    
                                # Get the relative path within the addon
                                rel_path = file[len(root_folder):]
                                # Extract to the addon directory
                                source = zip_ref.open(file)
                                target_path = os.path.join(addon_dir, rel_path)
                                
                                # Create directories if needed
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                
                                # Write the file
                                try:
                                    with open(target_path, 'wb') as target:
                                        target.write(source.read())
                                except PermissionError:
                                    error_msg = f"Permission denied when writing to {target_path}"
                                    log_error(error_msg)
                                    raise
                except zipfile.BadZipFile:
                    error_msg = "The downloaded file is not a valid zip file"
                    log_error(error_msg)
                    bpy.app.timers.register(
                        lambda: show_message_box("Update failed", error_msg), 
                        first_interval=0.1
                    )
                    return
                
                # Clean up - move this to after we're done with the zip file
                try:
                    # Close any open file handles to the zip
                    zip_ref.close()
                    # Wait a moment to ensure file handles are released
                    time.sleep(0.5)
                    os.unlink(temp_path)
                    print(f"Removed temporary file: {temp_path}")
                except Exception as e:
                    print(f"Warning: Could not remove temporary file {temp_path}: {str(e)}")
                    # Not critical, can continue
                
                # Show success message and reload addons
                print(f"Update to version {version} completed successfully")
                bpy.app.timers.register(
                    lambda: show_message_box("Update successful", f"PhlankaFortnite has been updated to version {version}. Please restart Blender to complete the update."), 
                    first_interval=0.1
                )
                
            except Exception as e:
                error_message = str(e)
                log_error(f"Error during update: {error_message}")
                traceback.print_exc()
                bpy.app.timers.register(
                    lambda: show_message_box("Update failed", f"Error during update: {error_message}"), 
                    first_interval=0.1
                )
        
        # Start download in a separate thread to avoid freezing Blender
        threading.Thread(target=download_thread).start()

def show_message_box(title, message):
    def draw(self, context):
        self.layout.label(text=message)
    
    bpy.context.window_manager.popup_menu(draw, title=title, icon='INFO')

class PHLANKA_OT_check_for_updates(bpy.types.Operator):
    bl_idname = "phlanka.check_for_updates"
    bl_label = "Check for Updates"
    bl_description = "Check for updates to the PhlankaFortnite addon"
    
    def execute(self, context):
        update_available, latest_version, tag_name = PhlankaUpdateChecker.is_update_available()
        if update_available:
            self.report({'INFO'}, f"Update available: {latest_version}")
            bpy.ops.phlanka.update_dialog('INVOKE_DEFAULT', version=latest_version, tag_name=tag_name)
        else:
            self.report({'INFO'}, "No updates available")
            show_message_box("No Updates", "You have the latest version of PhlankaFortnite")
        return {'FINISHED'}

class PHLANKA_OT_update_dialog(bpy.types.Operator):
    bl_idname = "phlanka.update_dialog"
    bl_label = "Update Available"
    bl_description = "A new version of PhlankaFortnite is available"
    
    version: bpy.props.StringProperty()
    tag_name: bpy.props.StringProperty()
    
    def execute(self, context):
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text=f"PhlankaFortnite Update V{self.version} is available!")
        row = layout.row()
        
        # Create the operator and set both properties at once
        install_op = row.operator("phlanka.install_update", text="Download Now")
        install_op.version = self.version
        install_op.tag_name = self.tag_name
        
        row.operator("phlanka.skip_update", text="Not Yet")

class PHLANKA_OT_install_update(bpy.types.Operator):
    bl_idname = "phlanka.install_update"
    bl_label = "Install Update"
    
    version: bpy.props.StringProperty()
    tag_name: bpy.props.StringProperty()
    
    def execute(self, context):
        PhlankaUpdateChecker.download_and_install_update(self.version, self.tag_name)
        return {'FINISHED'}

class PHLANKA_OT_skip_update(bpy.types.Operator):
    bl_idname = "phlanka.skip_update"
    bl_label = "Skip Update"
    
    def execute(self, context):
        return {'FINISHED'}

@persistent
def check_for_updates_on_startup(dummy):
    # Wait a bit to ensure Blender is fully loaded
    bpy.app.timers.register(check_for_updates_delayed, first_interval=3.0)

def check_for_updates_delayed():
    update_available, latest_version, tag_name = PhlankaUpdateChecker.is_update_available()
    if update_available:
        bpy.ops.phlanka.update_dialog('INVOKE_DEFAULT', version=latest_version, tag_name=tag_name)
    return None  # Don't repeat the timer

classes = (
    PHLANKA_OT_check_for_updates,
    PHLANKA_OT_update_dialog,
    PHLANKA_OT_install_update,
    PHLANKA_OT_skip_update,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add startup handler
    bpy.app.handlers.load_post.append(check_for_updates_on_startup)

def unregister():
    # Remove startup handler
    if check_for_updates_on_startup in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(check_for_updates_on_startup)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register() 