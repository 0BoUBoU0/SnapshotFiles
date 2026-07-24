bl_info = {
    "name": "Snapshot Files",
    "author": 'Yannick -BoUBoU- Castaing',
    "description": "Make a snapshot of your main file",
    "location": "File menu",
    "doc_url": "",
    "warning": "",
    "category": "General",
    "blender": (4, 0, 0),
    "version": (1, 4, 0)
}

# get addon name and version to use them automaticaly in the addon
ADDON_NAME = str(bl_info["name"])
ADDON_VERSION = '. '.join([str(n) for n in bl_info["version"]])

# import modules
import bpy
import os
from getpass import getuser
from socket import gethostname
from shutil import copyfile
from pathlib import Path
from datetime import datetime
from sys import platform

from bpy.props import (
    EnumProperty,
    StringProperty,
    BoolProperty,
    PointerProperty,
    )

# define global variables
separator = "-" * 20

snap_folder = "Snap_Files"
snap_text = 'Snapshots_History'

# define menu
def snapshotFiles_menu_draw(self,context):
    version = int(get_version())
    display_text = f'Snapshot File v{version:03d} to v{version+1:03d}'
    self.layout.operator("file.snapshotfiles", text=display_text, icon="FILE_TICK")


## define addon preferences
class SNAPSHOTFILES_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__


    user_snap_type_props: EnumProperty(
        name="Snap type", description="choose selection type", default=1,
        items=(
            ("Copy Main File", "Copy Main File", "Copy last Main File version without saving", 0),
            ("Copy Main File then Save", "Copy Main File then Save", "Copy Main File then Save the current file", 1),
            ("Save then Copy Main File", "Save then Copy Main File", "Save then Copy Main File the current file", 2),
        )
    )
    user_snap_folder: StringProperty(name="Snapshot Folder", default=f"//{snap_folder}\\")
    user_snap_extension: StringProperty(
        name="Snapshot extension",
        default=".blendsnap",
        description="blendsnap files can be read as blender files, but they won't be scaned in the asset browser",
    )
    user_commentpref: BoolProperty(
        name="Add a comment", default=True, description="allow the user to add a comment for the current version"
    )
    user_fileversion_prop: BoolProperty(
        name="Create version file",
        default=True,
        description="create a fake version file in the same folder as the original file, to know which version we are",
    )
    user_compression_pref: BoolProperty(
        name="Compressed files", 
        default=True, 
        description="if checked, snap files and current file will be compressed",
    )
    user_updateoutputpath: BoolProperty(
        name="Update output path",
        default=True,
        description="if you own the set output path addon, it will automatically update it",
    )
    user_updateoutputnodes: BoolProperty(
        name="Update output nodes",
        default=True,
        description="if you own the view layers addon, it will automatically update it",
    )
    update_scene_prop: EnumProperty(
        name="Update", description="Update scenes", default=1,
        items=(
            ("Opened Scene", "Opened Scene", "Opened Scene", 0),
            ("All Scenes", "All Scenes", "All Scenes", 1),
        )
    )
    get_version_prop: EnumProperty(
        name="Version method", description="how to fetch version number", default=1,
        items=(
            ("Snapshot History", "Snapshot History", "Snapshot History", 0),
            ("Snap Folder (Default)", "Snap Folder (Default)", "Snap Folder (Default)", 1),
            ("Scene Property", "Scene Property", "Scene Property", 2),
        ) 
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "user_commentpref")
        row = layout.row()
        row.prop(self, "user_snap_type_props")
        row.prop(self, "user_compression_pref")
        layout.prop(self, "user_snap_folder")
        layout.prop(self, "user_snap_extension")
        layout.prop(self, "get_version_prop")
        layout.prop(self, "user_fileversion_prop")
        layout.separator()

        has_output_path = hasattr(bpy.types, "RENDER_OT_setoutputpath")
        has_vlayer_output = hasattr(bpy.types, "VLOUTPUTS_OT_createnodesoutput")

        if has_output_path or has_vlayer_output:
            box = layout.box()
            row = box.row()
            if has_output_path:
                row.prop(self, "user_updateoutputpath")
            if has_vlayer_output:
                row.prop(self, "user_updateoutputnodes")
            row = box.row()
            row.prop(self, "update_scene_prop")


class SNAPSHOTFILES_properties(bpy.types.PropertyGroup):
    file_version: StringProperty(name="", default="v001", description="current file version")

# region Functions
def get_snapfolder():
    prefs = bpy.context.preferences.addons[__package__].preferences
    blend_folder = os.path.dirname(bpy.data.filepath)
    if prefs.user_snap_folder[:2] == "//":
        cleaned_user_snap_folder = prefs.user_snap_folder.replace("//","").replace("\\","")
        # create snapshot folder
        snap_Folder = os.path.join(blend_folder, cleaned_user_snap_folder)
    else:
        snap_Folder = prefs.user_snap_folder
    if not os.path.exists(snap_Folder):
        os.makedirs(snap_Folder)

    #print(f'{snap_Folder=}')
    return snap_Folder


# get version from the file
def get_version() -> str:
    snap_version = "001"
    prefs = bpy.context.preferences.addons[__package__].preferences
    # if folder method
    if prefs.get_version_prop == 'Snap Folder (Default)':
        #print("folder method")
        snap_Folder = get_snapfolder()
        blend_filename = str(os.path.basename(bpy.data.filepath)).split(".")[0] # get name without extension
        ## find all snap existing for the file
        versions_list = []
        for file in os.listdir(snap_Folder):
            file_name = str(os.path.basename(file))
            #print(f"{blend_filename=}")
            #print(f"{file_name=}")
            if file_name.startswith(blend_filename) and file_name.endswith(prefs.user_snap_extension):
                num_version = int(file_name.split('.')[0].split('-')[-1][1:])
                versions_list.append(num_version)
        # get last snap version
        if versions_list:
            snap_version = str(max(versions_list)+1).zfill(3)
    # if history method
    elif prefs.get_version_prop == 'Snapshot History':
        #print("history method")
        if snap_text in bpy.data.texts.keys():
            snap_history_1st_line = bpy.data.texts[snap_text].lines[0].body
            last_version = int(snap_history_1st_line.replace("--","").split(":")[-1].replace("v",""))
            snap_version = str(last_version).zfill(3)
        else:
            snap_version = str(1).zfill(3)
    elif prefs.get_version_prop == 'Scene Property':
        snap_version = bpy.context.scene.snapshotfiles_props.file_version[1:]

    #print(f'{snap_version=}')
    return snap_version


# region Operator
class FILE_OT_snapshotfiles(bpy.types.Operator):
    bl_idname = 'file.snapshotfiles'
    bl_label = ADDON_NAME
    bl_description = "make a snapshot of your main file in a subfolder"
    
    text_input: StringProperty(name=f'Add a Comment ?', default='')

    # now the addon
    def execute(self, context):
        print(f"\n {separator} Begin {ADDON_NAME} - {ADDON_VERSION} {separator} \n")
        prefs = bpy.context.preferences.addons[__package__].preferences
        ## get addon preferences
        user_snap_type_props = prefs.user_snap_type_props
        # user_snap_folder = prefs.user_snap_folder
        user_snap_extension = prefs.user_snap_extension
        
        
        user_commentpref = prefs.user_commentpref
        user_fileversion_prop = prefs.user_fileversion_prop
        update_scene_prop = prefs.update_scene_prop
        user_compression_pref = prefs.user_compression_pref
        
        ## check external addons
        has_output_path = hasattr(bpy.types, "RENDER_OT_setoutputpath")
        has_vlayer_output = hasattr(bpy.types, "VLOUTPUTS_OT_createnodesoutput")

        if has_output_path:
            user_updateoutputpath = prefs.user_updateoutputpath
        else:
            print('No addon "set output path"')
            user_updateoutputpath = False

        if has_vlayer_output:
            user_updateoutputnodes = prefs.user_updateoutputnodes
        else:
            print('No addon "view layer outputs"')
            user_updateoutputnodes = False

        if bpy.data.filepath != '':
            snap_Folder = Path(get_snapfolder())

            blend_filename = os.path.basename(bpy.data.filepath)
            blend_folder = os.path.dirname(bpy.data.filepath)
            
            #get current time and date
            now = datetime.now()

            #define snapshot filename
            # snap_files = os.listdir(path = snap_Folder)

            snap_ext = user_snap_extension.replace(".","")
            filename_clue = blend_filename.replace('.blend', '')
            filename_snapped = f"{filename_clue}_snap-v"
            

            ## get version from the file
            snap_version = get_version()

            snapfile_name = f"{filename_snapped}{snap_version}.{snap_ext}"
            print(f"{snapfile_name=}")
            snap_filepath = snap_Folder.joinpath(snapfile_name)
            
            original_file = bpy.data.filepath
            if user_snap_type_props == "Save then Copy Main File": # save current file
                bpy.ops.wm.save_mainfile(
                                        compress=user_compression_pref    
                                        )
            
            copyfile(original_file, snap_filepath) # copy file      

            #add history informations
            TextsListe = bpy.data.texts.keys()

            # create snap_files history
            if snap_text not in TextsListe:
                bpy.ops.text.new()
                bpy.data.texts["Text"].name = snap_text

            SnapHistoryText = bpy.data.texts[snap_text]

            blender_version = bpy.app.version_string

            SnapHistoryText.select_set(0, 0, 0, 1000)   
            if snap_version != '001':
                SnapHistoryText.write("-- Current File version : v" + str(int(snap_version) + 1).zfill(3) + " --\n \n---------------------------------------------- \n")
            else:
                SnapHistoryText.write("-- Current File version : v002 --\n \n---------------------------------------------- \n")

            # history details
            date_time = now.strftime("%A %d %B %Y" + " at " + "%H:%M:%S")

            user_comment = self.text_input
            if user_commentpref == False:
                user_comment = "Disabled by user"
            if user_comment == "":
                user_comment = "None"

            bpy.data.texts[snap_text].cursor_set(3)
            SnapHistoryText.write(f"Last snapshot made by: {getuser()} \n user comment: {user_comment} \n on: {gethostname()} ({platform}) \n Blender version: Blender {blender_version} \n the: {date_time} \n version based on: {bpy.context.preferences.addons[__name__].preferences.get_version_prop} \n >>> {snap_filepath}")

            ## create a fake file version file
            if user_fileversion_prop:
                print("create a fake file version")

                snap_history_lines = []
                for line in bpy.data.texts[snap_text].lines:
                    snap_history_lines.append(line.body)

                clue = [".","is_v"] # separator, clue
                def create_versioned_file(original_filename, version, target_directory):
                    # Ensure the target directory exists
                    os.makedirs(target_directory, exist_ok=True)
                    # Create the new filename based on the template
                    new_filename = f"{original_filename}{clue[0]}{clue[1]}{version}"
                    # Combine the target directory with the new filename
                    full_path = os.path.join(target_directory, new_filename)
                    # Create the new file
                    with open(full_path, 'w', encoding="utf-8") as file:
                        #file.write("")
                        for line in snap_history_lines:
                            file.write(f'{line}\n')
                    return full_path

                # variables
                #original_filename = filename_clue
                original_filename = blend_filename
                new_version = str(int(snap_version) + 1).zfill(3)
                target_directory = blend_folder

                _file_path = create_versioned_file(original_filename, new_version, target_directory)

                ## clean previous versions
                # List to store matching files
                matching_files = []
                # Scan the directory for files
                for filename in os.listdir(target_directory):
                    # Check if the file contains the original_filename and its extension starts with clue
                    if original_filename in filename and filename.split(clue[0])[-1].startswith(clue[1]):
                        if str(filename).split(clue[0])[-1] == f"{clue[1]}{new_version}":
                            pass 
                        else:
                            full_path = os.path.join(target_directory, filename)
                            os.remove(full_path)
                        matching_files.append(filename)
                #print("Matching files:", matching_files)

            ## fill scene property
            for scene in bpy.data.scenes:
                setattr(scene.snapshotfiles_props, "file_version", f"v{new_version}")

            del snap_version

            ## save file if user wants
            if user_snap_type_props == "Copy Main File then Save": # save current file
                bpy.ops.wm.save_mainfile(
                                        compress=user_compression_pref    
                                        )

            ### update output path and node path regarding preferences
            # print("update outputs ")
            current_scene = bpy.context.window.scene # store current scene
            current_layer = bpy.context.window.view_layer # store current view layer

            ## update output path
            if user_updateoutputpath:
                # print("update output path")
                print('\nsnap -> Run setoutputpath() (set_output_path addon)')
                if update_scene_prop == "All Scenes": 
                    for scene in bpy.data.scenes: 
                        bpy.context.window.scene = scene
                        bpy.ops.render.setoutputpath()
                    bpy.context.window.scene = current_scene
                else:
                    bpy.ops.render.setoutputpath()

            ## update output view layers
            if user_updateoutputnodes:
                print('\nsnap -> Run createnodesoutput() (view_layer_toolbox addon)')
                # print("update node output")
                if update_scene_prop == "All Scenes":
                    for scene in bpy.data.scenes: 
                        if not bpy.context.scene.render.image_settings.file_format == 'FFMPEG': ## avoid crash because of movie format
                            bpy.context.window.scene = scene
                            bpy.ops.vloutputs.createnodesoutput()
                            bpy.context.window.scene = current_scene
                            bpy.context.window.view_layer = current_layer
                else:
                    bpy.ops.vloutputs.createnodesoutput()

            # reset the comment
            self.text_input = ''#f'v{get_version()} to v{str(int(get_version())+1).zfill(3)}'

            print(f"snapshot saved : {str(snap_filepath)}")
            print(f"\n {separator} {ADDON_NAME} - {ADDON_VERSION} Finished {separator} \n")
            
            return {"FINISHED"}

    def invoke(self, context, event):
        if bpy.context.preferences.addons[__package__].preferences.user_commentpref:
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

# list all classes
classes = (
    FILE_OT_snapshotfiles,
    SNAPSHOTFILES_properties,
    SNAPSHOTFILES_preferences,
    )

# create keymap list
addon_keymaps = []

# register classes
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file.append(snapshotFiles_menu_draw)
    bpy.types.Scene.snapshotfiles_props = PointerProperty (type=SNAPSHOTFILES_properties)
    # add keymap
    if bpy.context.window_manager.keyconfigs.addon:
        keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.new(name="Window", space_type="EMPTY")
        keymapitem = keymap.keymap_items.new('file.snapshotfiles', #operator
                                             "S", #key
                                            "PRESS", # value
                                            ctrl=True, alt=True
                                            )
        addon_keymaps.append((keymap, keymapitem))

# unregister classes
def unregister():    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file.remove(snapshotFiles_menu_draw)
    # remove keymap
    for keymap, keymapitem in addon_keymaps:
        keymap.keymap_items.remove(keymapitem)
    addon_keymaps.clear()

if __name__ == "__main__":
    register()
