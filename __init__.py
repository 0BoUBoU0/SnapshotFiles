bl_info = {
    "name": "Snapshot Files",
    "author": 'Yannick -BoUBoU- Castaing',
    "description": "Make a snapshot of your main file",
    "location": "File menu",
    "doc_url": "",
    "warning": "",
    "category": "General",
    "blender": (5, 0, 0),
    "version": (2, 0, 0)
}

# get addon name and version to use them automaticaly in the addon
ADDON_NAME = str(bl_info["name"])
ADDON_VERSION = '. '.join([str(n) for n in bl_info["version"]])

# import modules
import bpy
import os
import re
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

snap_folder = "_snaps" # previously: Snap_Files
snap_text = 'Snapshots_History'

# define menu
def snapshotFiles_menu_draw(self,context):
    layout = self.layout
    ## nothing to snapshot yet: don't touch the disk, just tell the user
    if not bpy.data.filepath:
        row = layout.row()
        row.enabled = False
        row.operator("file.snapshotfiles", text='Snapshot File (save file first)', icon="FILE_TICK")
        return

    ## raising draw callback could partially or totally break File menu, so never let it
    try:
        version = int(get_version())
        display_text = f'Snapshot File v{version:03d} to v{version+1:03d}'
    except Exception as e:
        # print(f'{ADDON_NAME}: could not read snapshot version ({e})')
        display_text = 'Snapshot File (could not get version)'
    layout.operator("file.snapshotfiles", text=display_text, icon="FILE_TICK")


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
    user_snap_folder: StringProperty(name="Snapshot Folder", default=f"//{snap_folder}/")
    user_snap_extension: StringProperty(
        name="Snapshot extension",
        default=".blendsnap",
        description="blendsnap files can be read as blender files, but they won't be scaned in the asset browser",
    )
    user_comment: BoolProperty(
        name="Add a comment", default=True, description="allow the user to add a comment for the current version"
    )
    user_fileversion_prop: BoolProperty(
        name="Create version file",
        default=True,
        description="create a fake version file in the same folder as the original file, to know which version we are",
    )
    user_compression: BoolProperty(
        name="Compressed files", 
        default=True, 
        description="if checked, snap files and current file will be compressed",
    )
    user_update_output_path: BoolProperty(
        name="Update output path",
        default=True,
        description="if you own the set output path addon, it will automatically update it",
    )
    user_update_output_nodes: BoolProperty(
        name="Update output nodes",
        default=True,
        description="if you own the view layers addon, it will automatically update it",
    )
    update_scene_target: EnumProperty(
        name="Update", description="Update scenes", default=1,
        items=(
            ("Opened Scene", "Opened Scene", "Opened Scene", 0),
            ("All Scenes", "All Scenes", "All Scenes", 1),
        )
    )
    update_mode: EnumProperty(
        name="Update Mode", description="What to update: nothing, only version or trigger path and node tree rebuild", default=1,
        items=(
            ("NONE", "Nothing", "File content is untouched", 0),
            ("VERSION", "Only Update Versions", "Only update versions in output path and file output nodes paths", 1),
            ("REBUILD", "Path rebuild", "Update main path + node tree using addons set 'output path' + 'viewlayer outputs'", 2),
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
        layout.prop(self, "user_comment")
        row = layout.row()
        row.prop(self, "user_snap_type_props")
        row.prop(self, "user_compression")
        layout.prop(self, "user_snap_folder")
        layout.prop(self, "user_snap_extension")
        layout.prop(self, "get_version_prop")
        layout.prop(self, "user_fileversion_prop")
        layout.separator()

        box = layout.box()
        col = box.column()
        col.label(text='Path and nodes update:')
        col.prop(self, "update_mode")
        col.prop(self, "update_scene_target")

        has_output_path_addon = hasattr(bpy.types, "RENDER_OT_setoutputpath")
        has_vlayer_output_addon = hasattr(bpy.types, "VLOUTPUTS_OT_createnodesoutput")
        row = box.row()
        subrow1 = row.row()
        subrow1.prop(self, "user_update_output_path")
        subrow1.enabled = self.update_mode == 'VERSION' or (self.update_mode == 'REBUILD' and has_output_path_addon)

        subrow2 = row.row()
        subrow2.prop(self, "user_update_output_nodes")
        subrow2.enabled = self.update_mode == 'VERSION' or (self.update_mode == 'REBUILD' and has_vlayer_output_addon)


class SNAPSHOTFILES_properties(bpy.types.PropertyGroup):
    file_version: StringProperty(name="", default="v001", description="current file version")

# region Functions
def get_snapfolder(create=False) -> Path | None:
    """Return the snapshot folder path (None if it cannot be resolved yet).
    Only creates it on disk when create=True
    """
    prefs = bpy.context.preferences.addons[__package__].preferences
    raw_folder = prefs.user_snap_folder.strip() or f'//{snap_folder}/'
    ## a blend-relative folder is meaningless without a saved blend
    if raw_folder.startswith("//") and not bpy.data.filepath:
        return None
    ## abspath resolves both the "//" relative form and absolute paths.
    ## normalize backslashes ? -> # bpy.path.abspath(raw_folder).replace("\\", os.sep)
    snap_Folder = Path(os.path.normpath(bpy.path.abspath(raw_folder)))
    if create:
        snap_Folder.mkdir(parents=True, exist_ok=True)

    #print(f'{snap_Folder=}')
    return snap_Folder


# get version from the file
def get_version() -> str:
    snap_version = "001"
    prefs = bpy.context.preferences.addons[__package__].preferences
    # if folder method
    if prefs.get_version_prop == 'Snap Folder (Default)':
        #print("folder method")
        snap_Folder = get_snapfolder() # path only, folder is created when snapshotting
        ## find all snap existing for the file
        versions_list = []
        if snap_Folder and snap_Folder.is_dir():
            blend_filename = Path(bpy.data.filepath).stem # get name without extension
            for file in snap_Folder.iterdir():
                if file.name.startswith(blend_filename) and file.suffix == prefs.user_snap_extension:
                    ## skip unrelated files instead of raising on them
                    version_match = re.search(r'-v(\d+)$', file.stem)
                    if version_match:
                        versions_list.append(int(version_match.group(1)))
        # get last snap version
        if versions_list:
            snap_version = str(max(versions_list)+1).zfill(3)
    # if history method
    elif prefs.get_version_prop == 'Snapshot History':
        #print("history method")
        if snap_text in bpy.data.texts.keys():
            snap_history_1st_line = bpy.data.texts[snap_text].lines[0].body
            # last_version = int(snap_history_1st_line.replace("--","").split(":")[-1].replace("v",""))
            if found_version := re.search(r'v(\d+)', snap_history_1st_line):
                last_version = int(found_version.group(1))
            else:
                print('/!\\ Version not found in Snapshot History text data, falling back to v001')
                last_version = 1
            snap_version = str(last_version).zfill(3)
        else:
            ## explicit fallback (not needed cause already defined at function start) 
            snap_version = "001"
    ## TODO: add method based on local is_version
    elif prefs.get_version_prop == 'Scene Property':
        # remove trailing 'v'
        # note: this method is not robust in a multi-scene context
        snap_version = bpy.context.scene.snapshotfiles_props.file_version[1:]

    #print(f'{snap_version=}')
    return snap_version

# region version updater

## version match: lowercase 'v' followed by 3 digit.
## Anchors: 
##   - before: only if there is a separator before "-_/\" OR string start (can happen in output nodes).
##   - after : only with no subsequent digits (ex: v29400)
DEFAULT_VERSION_PATTERN = r'(?:(?<=[-_./\\ ])|^)v(\d{3})(?![0-9])'

## Simpler anchoring (preventing only match with subsequent digit)
## DEFAULT_VERSION_PATTERN = r'v(\d{3})(?![0-9])'

def update_version_string(string, version, version_pattern=None):
    """Update string with passed version on all occurence

    Args:
        string (str): the string to update
        version (str|int): version to apply (will get same padding as replaced string)
        version_pattern (str, optional): regex pattern for version
    """
    version_pattern = version_pattern or DEFAULT_VERSION_PATTERN
    re_version = re.compile(version_pattern)
    version = int(version)

    def replace(match):
        new = str(version).zfill(len(match.group(1)))
        offset = match.start()
        start, end = match.span(1)
        whole = match.group(0)
        return whole[:start - offset] + new + whole[end - offset:]

    return re_version.sub(replace, string)

def update_paths_version_only(new_version, update_output_main=True, update_output_nodes=True, version_pattern=None):
    """Soft path update, only update version in string, found with 'v' followed by 3 digits"""
    prefs = bpy.context.preferences.addons[__package__].preferences

    scenes = bpy.data.scenes if prefs.update_scene_target == "All Scenes" else [bpy.context.scene]
    ## get new version without passing ? (At this point, version has only been updated)
    # new_version = get_version())

    if update_output_main:
        for scn in scenes:
            cur_path = scn.render.filepath
            new_path = update_version_string(cur_path, new_version, version_pattern)
            if cur_path != new_path:
                print(f'update main output:\nold:{cur_path}\nnew:{new_path}')
                scn.render.filepath = new_path

    if update_output_nodes:
        for scn in scenes:
            if not (tree := scn.compositing_node_group):
                continue
            nodes = tree.nodes
            output_file_nodes = [n for n in nodes if n.type == 'OUTPUT_FILE']
            for out_node in output_file_nodes:
                ## directory
                cur_dir_name = out_node.directory
                new_dir_name = update_version_string(cur_dir_name, new_version, version_pattern)
                if cur_dir_name != new_dir_name:
                    print(f'node "{out_node}" directory:\nold:{cur_dir_name}\nnew:{new_dir_name}')
                    out_node.directory = new_dir_name

                ## filename (second field)
                cur_file_name = out_node.file_name
                new_file_name = update_version_string(cur_file_name, new_version, version_pattern)
                if cur_file_name != new_file_name:
                    print(f'node "{out_node}" file_name:\nold:{cur_file_name}\nnew:{new_file_name}')
                    out_node.file_name = new_file_name

                ## slots
                for i, item in enumerate(out_node.file_output_items):
                    cur_name = item.name
                    new_name = update_version_string(cur_name, new_version, version_pattern)
                    if cur_name != new_name:
                        print(f'node "{out_node}" item[{i}]:\nold:{cur_name}\nnew:{new_name}')
                        item.name = new_name

def update_paths_with_addon():
    """update output path and node path using external addons"""
    prefs = bpy.context.preferences.addons[__package__].preferences

    ## check external addons
    has_output_path = hasattr(bpy.types, "RENDER_OT_setoutputpath")
    has_vlayer_output = hasattr(bpy.types, "VLOUTPUTS_OT_createnodesoutput")

    current_scene = bpy.context.window.scene # store current scene
    current_layer = bpy.context.window.view_layer # store current view layer

    if has_output_path:
        update_output_main = prefs.user_update_output_path
    else:
        print('No addon "set output path"')
        update_output_main = False

    if has_vlayer_output:
        update_output_nodes = prefs.user_update_output_nodes
    else:
        print('No addon "view layer outputs"')
        update_output_nodes = False

    ## update output path
    if update_output_main:
        # print("update output path")
        print('\nsnap -> Run setoutputpath() (set_output_path addon)')
        if prefs.update_scene_target == "All Scenes": 
            for scene in bpy.data.scenes: 
                bpy.context.window.scene = scene
                bpy.ops.render.setoutputpath()
            bpy.context.window.scene = current_scene
        else:
            bpy.ops.render.setoutputpath()

    ## update output view layers
    if update_output_nodes:
        print('\nsnap -> Run createnodesoutput() (view_layer_toolbox addon)')
        # print("update node output")
        if prefs.update_scene_target == "All Scenes":
            for scene in bpy.data.scenes: 
                if not bpy.context.scene.render.image_settings.file_format == 'FFMPEG': ## avoid crash because of movie format
                    bpy.context.window.scene = scene
                    bpy.ops.vloutputs.createnodesoutput()

            # restore org scene/viewlayers
            bpy.context.window.scene = current_scene
            bpy.context.window.view_layer = current_layer
        else:
            bpy.ops.vloutputs.createnodesoutput()

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

        ## nothing to snapshot yet, cancel
        if not bpy.data.filepath:
            self.report({'ERROR'}, 'Save the file before making a snapshot')
            return {'CANCELLED'}

        snap_Folder = get_snapfolder() # not created yet, see below

        blend_filename = os.path.basename(bpy.data.filepath)
        blend_folder = os.path.dirname(bpy.data.filepath)

        ## get current time and date
        now = datetime.now()

        ## define snapshot filename
        snap_ext = prefs.user_snap_extension.replace(".","")
        filename_clue = blend_filename.replace('.blend', '')
        filename_snapped = f"{filename_clue}_snap-v"

        ## get version from the file
        snap_version = get_version()
        new_version = str(int(snap_version) + 1).zfill(3)

        snapfile_name = f"{filename_snapped}{snap_version}.{snap_ext}"
        print(f"{snapfile_name=}")
        snap_filepath = snap_Folder.joinpath(snapfile_name)

        original_file = bpy.data.filepath
        if prefs.user_snap_type_props == "Save then Copy Main File": # save current file
            bpy.ops.wm.save_mainfile(compress=prefs.user_compression)

        ## Create the snapshot folder now if needed
        folder_existed = snap_Folder.is_dir()
        try:
            snap_Folder.mkdir(parents=True, exist_ok=True)
            copyfile(original_file, snap_filepath) # copy file
        except OSError as e:
            ## don't leave an empty folder behind if the snapshot failed
            if not folder_existed and snap_Folder.is_dir() and not any(snap_Folder.iterdir()):
                snap_Folder.rmdir()
            self.report({'ERROR'}, f'Could not write snapshot: {e}')
            return {'CANCELLED'}

        #add history informations
        TextsListe = bpy.data.texts.keys()

        # create snap_files history
        if snap_text not in TextsListe:
            bpy.ops.text.new()
            bpy.data.texts["Text"].name = snap_text

        snap_history_text = bpy.data.texts[snap_text]

        blender_version = bpy.app.version_string

        snap_history_text.select_set(0, 0, 0, 1000)
        # Determine new first line content
        if snap_version != '001':
            new_first_line = "-- Current File version : v" + str(int(snap_version) + 1).zfill(3)
        else:
            new_first_line = "-- Current File version : v002"
        line_sep = " --\n \n---------------------------------------------- \n"
        snap_history_text.write(new_first_line + line_sep)

        # history details
        date_time = now.strftime("%A %d %B %Y" + " at " + "%H:%M:%S")

        user_comment = self.text_input
        if prefs.user_comment == False:
            user_comment = "Disabled by user"
        if user_comment == "":
            user_comment = "None"

        bpy.data.texts[snap_text].cursor_set(3)
        snap_history_text.write(f"Last snapshot made by: {getuser()} \n user comment: {user_comment} \n on: {gethostname()} ({platform}) \n Blender version: Blender {blender_version} \n the: {date_time} \n version based on: {prefs.get_version_prop} \n >>> {snap_filepath}")

        ## create a fake file version file
        if prefs.user_fileversion_prop:
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
            # print(f"matching_files=}")

        ## fill scene property
        for scene in bpy.data.scenes:
            setattr(scene.snapshotfiles_props, "file_version", f"v{new_version}")

        if prefs.update_mode == 'VERSION':
            update_paths_version_only(new_version, True, True)
        elif prefs.update_mode == 'REBUILD':
            update_paths_with_addon()

        ## save file if user wants
        if prefs.user_snap_type_props == "Copy Main File then Save": # save current file
            bpy.ops.wm.save_mainfile(compress=prefs.user_compression)

        # reset the comment
        self.text_input = ''

        print(f"snapshot saved : {str(snap_filepath)}")
        print(f"\n {separator} {ADDON_NAME} - {ADDON_VERSION} Finished {separator} \n")

        return {"FINISHED"}

    def draw(self, context):
        ## Added draw focus the field so the user can type right away
        ## Change in behavior, even to leave no comment, need to press enter twice
        layout = self.layout
        layout.activate_init = True
        layout.label(text='Add a comment:')
        ## TODO: maybe should explain here what happen ?
        ## ex: previous save file is copied while this one gets new version + ccmment
        layout.prop(self, 'text_input', text='')

    def invoke(self, context, event):
        ## nothing to snapshot yet, don't even ask for a comment
        if not bpy.data.filepath:
            self.report({'ERROR'}, 'Save the file before making a snapshot')
            return {'CANCELLED'}
        if bpy.context.preferences.addons[__package__].preferences.user_comment:
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)


classes = (
    FILE_OT_snapshotfiles,
    SNAPSHOTFILES_properties,
    SNAPSHOTFILES_preferences,
    )


addon_keymaps = []


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
