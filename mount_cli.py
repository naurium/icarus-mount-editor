#!/usr/bin/env python3
"""
Icarus Mount Editor CLI

Command-line interface for editing Icarus mount save data.

Usage:
    python mount_cli.py list
    python mount_cli.py info 0
    python mount_cli.py clone 0 "New Mount"
    python mount_cli.py --help
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from mount_editor import MountEditor, find_property, estimate_xp_for_level
from mount_types import MOUNT_TYPES


# =============================================================================
# Constants
# =============================================================================

VERSION = "1.0.0"


# =============================================================================
# Utility Functions
# =============================================================================

def find_steam_ids() -> List[str]:
    """Find all Steam IDs with Icarus save data."""
    base_path = Path(os.path.expandvars(r'%LOCALAPPDATA%\Icarus\Saved\PlayerData'))
    if not base_path.exists():
        return []
    return [d.name for d in base_path.iterdir() if d.is_dir() and d.name.isdigit()]


def auto_detect_steam_id() -> Optional[str]:
    """Auto-detect Steam ID if only one exists."""
    steam_ids = find_steam_ids()
    if len(steam_ids) == 1:
        return steam_ids[0]
    return None


def resolve_steam_id(args) -> Optional[str]:
    """Resolve Steam ID from args or auto-detect."""
    # If --file is specified, steam_id is not needed
    if hasattr(args, 'file') and args.file:
        return None

    if args.steam_id:
        return args.steam_id

    steam_id = auto_detect_steam_id()
    if steam_id:
        return steam_id

    steam_ids = find_steam_ids()
    if not steam_ids:
        print("ERROR: No Icarus save data found.")
        print("Make sure you have played Icarus and have mount data.")
        sys.exit(1)

    print("ERROR: Multiple Steam IDs found. Please specify one with --steam-id:")
    for sid in steam_ids:
        print(f"  {sid}")
    sys.exit(1)


def load_editor(args) -> MountEditor:
    """Create and load a MountEditor based on args."""
    if hasattr(args, 'file') and args.file:
        # Use explicit file path
        editor = MountEditor()
        editor.load(args.file)
        return editor
    else:
        # Use steam_id to find file
        steam_id = resolve_steam_id(args)
        editor = MountEditor(steam_id=steam_id)
        editor.load()
        return editor


def resolve_mount(editor: MountEditor, mount_arg: str) -> int:
    """
    Resolve mount argument to index.

    Accepts:
        - Integer index (e.g., "0", "5")
        - Mount name (e.g., "Shadow")
    """
    # Try as integer index
    try:
        index = int(mount_arg)
        if 0 <= index < len(editor.mounts):
            return index
        print(f"ERROR: Mount index {index} out of range (0-{len(editor.mounts)-1})")
        sys.exit(1)
    except ValueError:
        pass

    # Try as name
    mount = editor.find_mount_by_name(mount_arg)
    if mount:
        return mount.index

    print(f"ERROR: Mount not found: '{mount_arg}'")
    print("Use 'mount_cli.py list' to see available mounts.")
    sys.exit(1)


def confirm(message: str, skip: bool = False) -> bool:
    """Ask for user confirmation."""
    if skip:
        return True
    response = input(f"{message} [y/N]: ").strip().lower()
    return response in ('y', 'yes')


def print_separator(char: str = '-', width: int = 60):
    """Print a separator line."""
    print(char * width)


def format_number(n: int) -> str:
    """Format number with thousands separator."""
    return f"{n:,}"


# =============================================================================
# Table Formatting
# =============================================================================

def print_table(headers: List[str], rows: List[List[str]], min_widths: List[int] = None):
    """Print a formatted table."""
    if not rows:
        print("(no data)")
        return

    # Calculate column widths
    widths = []
    for i in range(len(headers)):
        col_width = max(
            len(str(headers[i])),
            max(len(str(row[i])) for row in rows) if rows else 0
        )
        if min_widths and i < len(min_widths):
            col_width = max(col_width, min_widths[i])
        widths.append(col_width)

    # Build separator
    separator = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'

    # Print header
    print(separator)
    header_row = '|' + '|'.join(f" {h.ljust(w)} " for h, w in zip(headers, widths)) + '|'
    print(header_row)
    print(separator)

    # Print rows
    for row in rows:
        row_str = '|' + '|'.join(f" {str(v).ljust(w)} " for v, w in zip(row, widths)) + '|'
        print(row_str)

    print(separator)


# =============================================================================
# Information Commands
# =============================================================================

def cmd_list(args):
    """List all mounts."""
    try:
        editor = load_editor(args)
    except FileNotFoundError:
        print("ERROR: No mount save file found.")
        print("Make sure you have tamed at least one mount in Icarus.")
        sys.exit(1)

    print()
    print(f"Mounts ({len(editor.mounts)} total):")
    print()

    if not editor.mounts:
        print("No mounts found.")
        return

    # Build table data
    headers = ['#', 'Name', 'Type', 'Level', 'AI Setup']
    rows = []

    for mount in editor.mounts:
        ai_setup = mount.get_value('AISetupRowName') or 'Unknown'
        rows.append([
            str(mount.index),
            mount.name,
            mount.mount_type,
            str(mount.level),
            ai_setup
        ])

    print_table(headers, rows, min_widths=[3, 20, 15, 5, 25])
    print()
    print(f"Total: {len(editor.mounts)} mount(s)")


def cmd_info(args):
    """Show detailed mount information."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)

    print()
    print_separator('=')
    print(f"Mount Details: {mount.name} (Index {mount.index})")
    print_separator('=')
    print()

    # Basic info
    print(f"{'Name:':<20} {mount.name}")
    print(f"{'Type:':<20} {mount.mount_type}")

    ai_setup = mount.get_value('AISetupRowName') or 'Unknown'
    print(f"{'AI Setup:':<20} {ai_setup}")

    actor_class = mount.get_value('ActorClassName') or 'Unknown'
    print(f"{'Blueprint:':<20} {actor_class}")

    print()

    # Level and XP
    exp = mount.get_value('Experience') or 0
    print(f"{'Level:':<20} {mount.level}")
    print(f"{'Experience:':<20} {format_number(exp)}")

    print()

    # IDs
    guid = mount.json_data.get('DatabaseGUID', 'Unknown')
    print(f"{'GUID:':<20} {guid}")

    obj_fname = mount.get_value('ObjectFName') or 'Unknown'
    print(f"{'ObjectFName:':<20} {obj_fname}")

    icarus_guid = mount.get_value('IcarusActorGUID')
    if icarus_guid:
        print(f"{'IcarusActorGUID:':<20} {icarus_guid}")

    print()

    # Stats (from CharacterRecord)
    print("Stats:")
    print_separator()

    stats = [
        ('CurrentHealth', 'CharacterRecord.CurrentHealth'),
        ('MaxHealth', 'CharacterRecord.MaxHealth'),
        ('CurrentStamina', 'Stamina'),
        ('MaxStamina', 'MaxStamina'),
        ('CurrentFood', 'CurrentFood'),
        ('MaxFood', 'MaxFood'),
        ('CurrentWater', 'CurrentWater'),
        ('MaxWater', 'MaxWater'),
    ]

    for label, path in stats:
        value = mount.get_value(path)
        if value is not None:
            if isinstance(value, float):
                print(f"  {label:<20} {value:.1f}")
            else:
                print(f"  {label:<20} {value}")

    print()

    # Flags
    print("Flags:")
    print_separator()

    wild_tame = mount.get_value('bIsWildTame')
    if wild_tame is not None:
        print(f"  {'bIsWildTame:':<20} {wild_tame}")

    skin_idx = mount.get_value('CosmeticSkinIndex')
    if skin_idx is not None:
        print(f"  {'CosmeticSkinIndex:':<20} {skin_idx}")

    print()


def cmd_types(args):
    """List available mount types."""
    print()
    print("Available Mount Types")
    print_separator('=')
    print()

    headers = ['Key', 'Rideable', 'Description']
    rows = []

    for key, mt in MOUNT_TYPES.items():
        rideable = 'Yes' if mt.rideable else 'No'
        desc = mt.description[:50] + '...' if len(mt.description) > 50 else mt.description
        rows.append([key, rideable, desc])

    print_table(headers, rows, min_widths=[15, 8, 50])

    if args.detailed:
        print()
        print("Detailed Information:")
        print_separator()
        for key, mt in MOUNT_TYPES.items():
            print()
            print(f"  {key}:")
            print(f"    Blueprint: {mt.blueprint}")
            print(f"    AI Setup:  {mt.ai_setup}")
            print(f"    Rideable:  {'Yes' if mt.rideable else 'No'}")
            if mt.skins:
                print(f"    Skins:")
                for skin in mt.skins:
                    print(f"      [{skin.index}] {skin.name}: {skin.description}")

    print()


def cmd_validate(args):
    """Validate mount data integrity."""
    editor = load_editor(args)

    print()
    print("Mount Validation")
    print_separator('=')
    print()

    if args.mount:
        indices = [resolve_mount(editor, args.mount)]
    else:
        indices = range(len(editor.mounts))

    all_valid = True
    for idx in indices:
        mount = editor.get_mount(idx)
        issues = editor.validate_mount(idx)

        if issues:
            all_valid = False
            print(f"[{idx}] {mount.name}: INVALID")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print(f"[{idx}] {mount.name}: OK")

    print()
    if all_valid:
        print("All mounts are valid.")
    else:
        print("Some mounts have issues. See above for details.")


# =============================================================================
# Modification Commands
# =============================================================================

def cmd_rename(args):
    """Rename a mount."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)
    old_name = mount.name

    print()
    print(f"Renaming mount [{index}] '{old_name}' to '{args.name}'")

    editor.set_mount_name(index, args.name)
    editor.save(backup=not args.no_backup)

    print()
    print("Done!")


def cmd_level(args):
    """Set mount level."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)

    level = args.level
    if level < 1 or level > 50:
        print("ERROR: Level must be between 1 and 50.")
        sys.exit(1)

    print()
    print(f"Setting mount [{index}] '{mount.name}' to level {level}")

    old_level = mount.level
    old_exp = mount.get_value('Experience') or 0
    new_exp = estimate_xp_for_level(level)

    print(f"  Level: {old_level} -> {level}")
    print(f"  Experience: {format_number(old_exp)} -> {format_number(new_exp)}")

    editor.set_mount_level(index, level)
    editor.save(backup=not args.no_backup)

    print()
    print("Done!")


def cmd_type(args):
    """Change mount type."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)

    target_type = args.type
    if target_type not in MOUNT_TYPES:
        print(f"ERROR: Unknown mount type: '{target_type}'")
        print("Use 'mount_cli.py types' to see available types.")
        sys.exit(1)

    print()
    print(f"Changing mount [{index}] '{mount.name}' from {mount.mount_type} to {target_type}")

    if not confirm("This will transform the mount type. Continue?", args.confirm):
        print("Aborted.")
        return

    editor.change_mount_type(index, target_type, new_name=args.name)
    editor.save(backup=not args.no_backup)

    print()
    print("Done!")


def cmd_clone(args):
    """Clone a mount."""
    editor = load_editor(args)

    source_index = resolve_mount(editor, args.mount)
    source = editor.get_mount(source_index)

    print()
    print(f"Cloning mount [{source_index}] '{source.name}' as '{args.name}'")

    if args.type and args.type not in MOUNT_TYPES:
        print(f"ERROR: Unknown mount type: '{args.type}'")
        print("Use 'mount_cli.py types' to see available types.")
        sys.exit(1)

    new_index = editor.clone_mount(source_index, args.name, new_type=args.type)
    editor.save(backup=not args.no_backup)

    print()
    print(f"Created new mount at index {new_index}")
    print("Done!")


def cmd_delete(args):
    """Delete a mount."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)

    print()
    print(f"Deleting mount [{index}] '{mount.name}' ({mount.mount_type})")

    if not confirm("This will permanently delete the mount. Continue?", args.confirm):
        print("Aborted.")
        return

    editor.delete_mount(index)
    editor.save(backup=not args.no_backup)

    print()
    print("Done!")


def cmd_variant(args):
    """Change horse variant (A1/A2/A3)."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)

    variant = args.variant.upper()

    print()
    print(f"Changing horse variant for [{index}] '{mount.name}'")
    print()
    print("Variant colors:")
    print("  A1 = Brown")
    print("  A2 = Black")
    print("  A3 = White")
    print()

    try:
        # Use editor method (handles validation and modification)
        editor.set_horse_variant(index, variant)
        editor.save(backup=not args.no_backup)
        print()
        print("Done!")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def cmd_reset_talents(args):
    """Reset mount talents (refund all talent points)."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)

    print()
    print(f"Resetting talents for [{index}] '{mount.name}'")

    # Check talent count before prompting (editor method handles the reset)
    talents_prop = find_property(mount.properties, 'Talents')
    talent_count = len(talents_prop.nested) if talents_prop and talents_prop.nested else 0

    if talent_count == 0:
        print("  No talents allocated")
        return

    print(f"  Found {talent_count} talent(s) allocated")

    if not confirm("This will reset all talents. Continue?", args.confirm):
        print("Aborted.")
        return

    # Use editor method to reset talents
    reset_count = editor.reset_mount_talents(index)
    editor.save(backup=not args.no_backup)

    print()
    print(f"Reset {reset_count} talent(s). Points refunded.")
    print("Done!")


def cmd_skin(args):
    """Set cosmetic skin index."""
    editor = load_editor(args)

    index = resolve_mount(editor, args.mount)
    mount = editor.get_mount(index)

    skin_index = args.skin

    print()
    print(f"Setting skin for [{index}] '{mount.name}'")

    try:
        editor.set_cosmetic_skin(index, skin_index)
        editor.save(backup=not args.no_backup)
        print()
        print("Done!")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


# =============================================================================
# Utility Commands
# =============================================================================

def cmd_backup(args):
    """Create a manual backup."""
    editor = load_editor(args)

    source = editor.file_path

    if args.output:
        backup_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = source.with_suffix(f'.backup_{timestamp}.json')

    shutil.copy(source, backup_path)

    print()
    print(f"Backup created: {backup_path}")
    print(f"  Mounts: {len(editor.mounts)}")


def cmd_restore(args):
    """Restore from a backup."""
    steam_id = resolve_steam_id(args)
    base_path = Path(os.path.expandvars(
        rf'%LOCALAPPDATA%\Icarus\Saved\PlayerData\{steam_id}'
    ))
    mounts_file = base_path / 'Mounts.json'

    # Find backups
    backups = sorted(base_path.glob('Mounts.backup_*.json'), reverse=True)
    backups += sorted(base_path.glob('Mounts.json.backup_*.json'), reverse=True)

    if args.backup:
        # Restore specific backup
        backup_path = base_path / args.backup
        if not backup_path.exists():
            print(f"ERROR: Backup not found: {backup_path}")
            sys.exit(1)

        print()
        print(f"Restoring from: {backup_path}")

        if not confirm("This will overwrite your current mounts. Continue?"):
            print("Aborted.")
            return

        # Create safety backup of current file
        if mounts_file.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safety_backup = mounts_file.with_suffix(f'.pre_restore_{timestamp}.json')
            shutil.copy(mounts_file, safety_backup)
            print(f"  Safety backup: {safety_backup}")

        shutil.copy(backup_path, mounts_file)
        print()
        print("Restored successfully!")

    else:
        # List available backups
        print()
        print("Available Backups:")
        print_separator()

        if not backups:
            print("No backups found.")
            return

        for i, backup in enumerate(backups[:10]):
            stat = backup.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            size = stat.st_size // 1024
            print(f"  [{i}] {backup.name}")
            print(f"      Modified: {mtime}, Size: {size} KB")

        if len(backups) > 10:
            print(f"  ... and {len(backups) - 10} more")

        print()
        print("To restore a backup:")
        print(f"  python mount_cli.py restore <backup_filename>")


def cmd_config(args):
    """Show configuration."""
    print()
    print("Configuration")
    print_separator('=')
    print()

    # Steam IDs
    steam_ids = find_steam_ids()
    print("Steam IDs found:")
    if steam_ids:
        for sid in steam_ids:
            mounts_path = Path(os.path.expandvars(
                rf'%LOCALAPPDATA%\Icarus\Saved\PlayerData\{sid}\Mounts.json'
            ))
            exists = "exists" if mounts_path.exists() else "no mounts file"
            print(f"  {sid} ({exists})")
    else:
        print("  (none)")

    print()

    # Auto-detected
    auto_id = auto_detect_steam_id()
    if auto_id:
        print(f"Auto-detected Steam ID: {auto_id}")
    else:
        print("Auto-detection: Multiple IDs found, please specify with --steam-id")

    print()

    # Paths
    print("Paths:")
    base_path = Path(os.path.expandvars(r'%LOCALAPPDATA%\Icarus\Saved\PlayerData'))
    print(f"  Save data: {base_path}")

    print()


# =============================================================================
# Main Entry Point
# =============================================================================

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog='mount_cli',
        description='Icarus Mount Editor - Edit your mount save data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mount_cli.py list                     List all mounts
  mount_cli.py info 0                   Show details for mount 0
  mount_cli.py clone 0 "Shadow II"      Clone mount 0 with new name
  mount_cli.py level 0 50               Set mount 0 to level 50
  mount_cli.py type 0 Tusker            Change mount 0 to Tusker
  mount_cli.py variant 0 A3             Change horse variant to white
"""
    )

    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')
    parser.add_argument('--steam-id', metavar='ID',
                        help='Steam ID (auto-detected if only one exists)')
    parser.add_argument('--file', metavar='PATH',
                        help='Path to Mounts.json file (overrides --steam-id)')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip automatic backup before modifications')

    subparsers = parser.add_subparsers(dest='command', metavar='command')

    # === Information Commands ===

    # list
    list_parser = subparsers.add_parser('list', help='List all mounts')

    # info
    info_parser = subparsers.add_parser('info', help='Show detailed mount information')
    info_parser.add_argument('mount', help='Mount index or name')

    # types
    types_parser = subparsers.add_parser('types', help='List available mount types')
    types_parser.add_argument('--detailed', '-d', action='store_true',
                              help='Show detailed information including skins')

    # validate
    validate_parser = subparsers.add_parser('validate', help='Validate mount data integrity')
    validate_parser.add_argument('mount', nargs='?', help='Mount index or name (optional)')

    # === Modification Commands ===

    # rename
    rename_parser = subparsers.add_parser('rename', help='Rename a mount')
    rename_parser.add_argument('mount', help='Mount index or name')
    rename_parser.add_argument('name', help='New name')

    # level
    level_parser = subparsers.add_parser('level', help='Set mount level')
    level_parser.add_argument('mount', help='Mount index or name')
    level_parser.add_argument('level', type=int, help='New level (1-50)')

    # type
    type_parser = subparsers.add_parser('type', help='Change mount type')
    type_parser.add_argument('mount', help='Mount index or name')
    type_parser.add_argument('type', help='New mount type (e.g., Tusker, WoollyMammoth)')
    type_parser.add_argument('--name', help='Optional new name')
    type_parser.add_argument('--confirm', '-y', action='store_true',
                             help='Skip confirmation prompt')

    # clone
    clone_parser = subparsers.add_parser('clone', help='Clone a mount')
    clone_parser.add_argument('mount', help='Mount index or name to clone')
    clone_parser.add_argument('name', help='Name for the new mount')
    clone_parser.add_argument('--type', help='Optional new mount type')

    # delete
    delete_parser = subparsers.add_parser('delete', help='Delete a mount')
    delete_parser.add_argument('mount', help='Mount index or name')
    delete_parser.add_argument('--confirm', '-y', action='store_true',
                               help='Skip confirmation prompt')

    # variant
    variant_parser = subparsers.add_parser('variant', help='Change horse variant (A1/A2/A3)')
    variant_parser.add_argument('mount', help='Mount index or name')
    variant_parser.add_argument('variant', help='Variant: A1 (brown), A2 (black), or A3 (white)')

    # reset-talents
    reset_talents_parser = subparsers.add_parser('reset-talents', help='Reset mount talents (refund points)')
    reset_talents_parser.add_argument('mount', help='Mount index or name')
    reset_talents_parser.add_argument('--confirm', '-y', action='store_true',
                                       help='Skip confirmation prompt')

    # skin
    skin_parser = subparsers.add_parser('skin', help='Set cosmetic skin index')
    skin_parser.add_argument('mount', help='Mount index or name')
    skin_parser.add_argument('skin', type=int, help='Skin index (0, 1, 2, etc.)')

    # === Utility Commands ===

    # backup
    backup_parser = subparsers.add_parser('backup', help='Create a manual backup')
    backup_parser.add_argument('--output', '-o', help='Output file path')

    # restore
    restore_parser = subparsers.add_parser('restore', help='Restore from a backup')
    restore_parser.add_argument('backup', nargs='?', help='Backup filename to restore')

    # config
    config_parser = subparsers.add_parser('config', help='Show configuration')

    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Route to command handler
    commands = {
        'list': cmd_list,
        'info': cmd_info,
        'types': cmd_types,
        'validate': cmd_validate,
        'rename': cmd_rename,
        'level': cmd_level,
        'type': cmd_type,
        'clone': cmd_clone,
        'delete': cmd_delete,
        'variant': cmd_variant,
        'reset-talents': cmd_reset_talents,
        'skin': cmd_skin,
        'backup': cmd_backup,
        'restore': cmd_restore,
        'config': cmd_config,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            handler(args)
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(130)
        except (FileNotFoundError, ValueError, IndexError, RuntimeError, json.JSONDecodeError) as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
