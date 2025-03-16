bl_info = {
    "name": "Phlanka Fortnite",
    "author": "Phlanka",
    "version": (1, 0, 4),
    "blender": (4, 3, 0),
    "location": "Node Editor > Sidebar > Phlanka Fortnite",
    "description": "Replaces the main material node with PhlankaFortnite in all materials",
    "category": "Material",
}

import bpy
import os
from . import update_checker

# Function to replace the node connected to Material Output
def replace_node_group(context):
    # Define the node groups to replace
    replacements = {
        "PhlankaFortnite": "FPv3 Material",  # Will replace FPv3 Material nodes
        "PhlankaGlassFortnite": "FPv3 Glass",  # Will specifically replace FPv3 Glass nodes
        "PhlankaLayersFortnite": "FPv3 Layer"  # Will specifically replace FPv3 Layer nodes
    }

    # Load the node groups from Assets.blend
    addon_dir = os.path.dirname(__file__)
    assets_path = os.path.join(addon_dir, "Assets.blend")
    
    if not os.path.exists(assets_path):
        bpy.ops.error.message('INVOKE_DEFAULT', message="Assets.blend not found!")
        return {'CANCELLED'}

    # Load all required node groups
    with bpy.data.libraries.load(assets_path, link=False) as (data_from, data_to):
        groups_to_load = [name for name in replacements.keys() if name in data_from.node_groups]
        if not groups_to_load:
            bpy.ops.error.message('INVOKE_DEFAULT', message="Required node groups not found in Assets.blend!")
            return {'CANCELLED'}
        data_to.node_groups = groups_to_load

    # Check if we loaded the groups successfully
    loaded_groups = {name: bpy.data.node_groups.get(name) for name in replacements.keys()}
    if not any(loaded_groups.values()):
        return {'CANCELLED'}

    # Process all objects in the scene
    processed_materials = set()  # Track materials we've already processed
    
    for obj in bpy.data.objects:
        # Skip objects without materials
        if not hasattr(obj, 'material_slots') or len(obj.material_slots) == 0:
            continue
            
        for slot in obj.material_slots:
            material = slot.material
            
            # Skip if no material, no node tree, or already processed
            if not material or not material.node_tree or material.name in processed_materials:
                continue
                
            processed_materials.add(material.name)
            
            nodes = material.node_tree.nodes
            links = material.node_tree.links

            # Handle specific node replacements first
            for new_group_name, old_group_name in replacements.items():
                if loaded_groups[new_group_name]:
                    # Find all nodes of the specified type
                    nodes_to_replace = [n for n in nodes if n.type == 'GROUP' and 
                                       n.node_tree and n.node_tree.name == old_group_name]
                    
                    for node in nodes_to_replace:
                        replace_single_node(node, loaded_groups[new_group_name], nodes, links)
                        
            # Also handle the special case of nodes connected to Material Output
            # (in case they're not FPv3 Material but should still be replaced)
            if loaded_groups["PhlankaFortnite"]:
                output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                if output_node and output_node.inputs[0].is_linked:
                    main_node = output_node.inputs[0].links[0].from_node
                    # Only replace if it's a GROUP node and not already handled
                    if main_node.type == 'GROUP' and main_node.node_tree:
                        # Skip if it's already one of our nodes or if it's a specific node that should be replaced with something else
                        excluded_nodes = ["PhlankaFortnite", "PhlankaGlassFortnite", "PhlankaLayersFortnite", 
                                         "FPv3 Glass", "FPv3 Layer"]
                        if main_node.node_tree.name not in excluded_nodes:
                            replace_single_node(main_node, loaded_groups["PhlankaFortnite"], nodes, links)

    return {'FINISHED'}

# Helper function to replace a single node
def replace_single_node(old_node, new_group, nodes, links):
    # Create a new node
    new_node = nodes.new(type='ShaderNodeGroup')
    new_node.node_tree = new_group
    new_node.location = old_node.location

    # Transfer connections and default values
    for i, input_socket in enumerate(old_node.inputs):
        if i < len(new_node.inputs):
            if input_socket.is_linked:
                for link in input_socket.links:
                    links.new(link.from_socket, new_node.inputs[i])
            else:
                try:
                    # Get the expected dimensions for the target socket
                    target_socket = new_node.inputs[i]
                    source_value = input_socket.default_value
                    
                    # Check if both are single values (float/int)
                    if isinstance(source_value, (float, int)) and not hasattr(target_socket.default_value, "__len__"):
                        target_socket.default_value = source_value
                    # Check if both are vectors/colors with same dimensions
                    elif hasattr(source_value, "__len__") and hasattr(target_socket.default_value, "__len__"):
                        if len(source_value) == len(target_socket.default_value):
                            target_socket.default_value = source_value
                    # Skip if types don't match
                    else:
                        continue
                except (AttributeError, ValueError, TypeError):
                    # Skip any errors during value assignment
                    continue

    # Transfer the output connections
    for i, output_socket in enumerate(old_node.outputs):
        if i < len(new_node.outputs):
            if output_socket.is_linked:
                for link in output_socket.links:
                    links.new(new_node.outputs[i], link.to_socket)

    # Remove the old node
    nodes.remove(old_node)

# UI Panel in Material Node Editor
class PHLANKA_PT_MaterialPanel(bpy.types.Panel):
    bl_label = "Phlanka Fortnite"
    bl_idname = "PHLANKA_PT_material_panel"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Phlanka Fortnite"

    def draw(self, context):
        layout = self.layout
        layout.operator("phlanka.convert_to_dayz")
        
        # Add a separator and update section
        layout.separator()
        box = layout.box()
        box.label(text="Updates")
        box.operator("phlanka.check_for_updates", text="Check for Updates")


# Operator for button
class PHLANKA_OT_ConvertToDayZ(bpy.types.Operator):
    bl_idname = "phlanka.convert_to_dayz"
    bl_label = "Convert to DayZ Textures"
    bl_description = "Replace the main material node with PhlankaFortnite"
    
    def execute(self, context):
        return replace_node_group(context)


# Outliner right-click menu operator
class PHLANKA_OT_OutlinerConvertToDayZ(bpy.types.Operator):
    bl_idname = "phlanka.outliner_convert_to_dayz"
    bl_label = "Convert to DayZ Textures"
    bl_description = "Convert all materials in the scene to DayZ textures"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return replace_node_group(context)


# Function to add the menu item to the outliner context menu
def draw_outliner_context_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu("PHLANKA_MT_fortnite_menu", text="Fortnite")


# Submenu for Fortnite options
class PHLANKA_MT_FortniteMenu(bpy.types.Menu):
    bl_idname = "PHLANKA_MT_fortnite_menu"
    bl_label = "Fortnite"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("phlanka.outliner_convert_to_dayz", text="DayZ Texture Convert")


# Register and Unregister
classes = [
    PHLANKA_PT_MaterialPanel, 
    PHLANKA_OT_ConvertToDayZ,
    PHLANKA_OT_OutlinerConvertToDayZ,
    PHLANKA_MT_FortniteMenu
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add the menu item to the outliner context menu
    bpy.types.OUTLINER_MT_context_menu.append(draw_outliner_context_menu)
    
    # Register update checker
    update_checker.register()

def unregister():
    # Remove the menu item from the outliner context menu
    bpy.types.OUTLINER_MT_context_menu.remove(draw_outliner_context_menu)
    
    # Unregister update checker
    update_checker.unregister()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
