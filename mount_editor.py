#!/usr/bin/env python3
"""
Icarus Mount Editor

High-level API for editing Icarus mount save files (Mounts.json).
Handles loading, modifying, and saving mounts with proper UE4 serialization.

Usage:
    from mount_editor import MountEditor

    editor = MountEditor()
    editor.load()  # Loads from default Icarus path

    # Get mount info
    for mount in editor.list_mounts():
        print(f"{mount.name} - {mount.mount_type} (Level {mount.level})")

    # Modify a mount
    editor.set_mount_property(0, 'Experience', 999999)
    editor.set_mount_property(0, 'CurrentHealth', 5000)

    # Change mount type
    editor.change_mount_type(0, 'Tusker')

    # Save changes
    editor.save()
"""

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ue4_properties import (
    PropertySerializer,
    FPropertyTag,
    find_property,
    set_property_value,
    clone_properties
)
from mount_types import (
    MOUNT_TYPES,
    get_mount_type,
    get_transform_value,
    TRANSFORM_PROPERTIES
)


# =============================================================================
# XP/Level Calculations
# =============================================================================

# Official XP keypoints extracted from C_MountExperienceGrowth.uasset
# The game uses a cubic Hermite spline (FRichCurve) with these keypoints:
#   (level, xp, tangent)
_XP_KEYPOINTS = [
    (10, 13500, 2250),
    (30, 140000, 17000),
    (50, 1150000, 88000),
]


def _hermite_interpolate(t: float, p0: float, p1: float, m0: float, m1: float) -> float:
    """Cubic Hermite interpolation between two points."""
    t2 = t * t
    t3 = t2 * t
    h00 = 2*t3 - 3*t2 + 1
    h10 = t3 - 2*t2 + t
    h01 = -2*t3 + 3*t2
    h11 = t3 - t2
    return h00*p0 + h10*m0 + h01*p1 + h11*m1


def estimate_xp_for_level(level: int) -> int:
    """
    Calculate XP required for a given level using the official game curve.

    Uses the actual curve data extracted from C_MountExperienceGrowth.uasset.
    The game uses a cubic Hermite spline (FRichCurve) for smooth interpolation.

    IMPORTANT: The JSON MountLevel is authoritative for level display.
    This XP value affects XP bar progress, not the displayed level.

    Args:
        level: Target level (1-50)

    Returns:
        XP value from official game curve
    """
    if level <= 1:
        return 0

    # Below first keypoint - linear extrapolation using tangent
    if level < _XP_KEYPOINTS[0][0]:
        lvl0, xp0, tan0 = _XP_KEYPOINTS[0]
        return max(0, int(xp0 - tan0 * (lvl0 - level)))

    # Above last keypoint - linear extrapolation using tangent
    if level >= _XP_KEYPOINTS[-1][0]:
        lvl_last, xp_last, tan_last = _XP_KEYPOINTS[-1]
        return int(xp_last + tan_last * (level - lvl_last))

    # Find segment and interpolate
    for i in range(len(_XP_KEYPOINTS) - 1):
        lvl0, xp0, tan0 = _XP_KEYPOINTS[i]
        lvl1, xp1, tan1 = _XP_KEYPOINTS[i + 1]

        if lvl0 <= level < lvl1:
            t = (level - lvl0) / (lvl1 - lvl0)
            segment_length = lvl1 - lvl0
            m0 = tan0 * segment_length
            m1 = tan1 * segment_length
            return int(_hermite_interpolate(t, xp0, xp1, m0, m1))

    return 0


def estimate_level_from_xp(xp: int) -> int:
    """
    Estimate level from XP amount using binary search on the curve.

    Args:
        xp: Current XP amount

    Returns:
        Estimated level (1-50)
    """
    if xp <= 0:
        return 1

    # Binary search for the level (max level is 50)
    low, high = 1, 50
    while low < high:
        mid = (low + high + 1) // 2
        if estimate_xp_for_level(mid) <= xp:
            low = mid
        else:
            high = mid - 1

    return low


# =============================================================================
# Configuration
# =============================================================================

def get_default_mounts_path(steam_id: Optional[str] = None) -> Path:
    """Get the default Mounts.json path."""
    if steam_id is None:
        # Try to find the Steam ID from existing files
        base_path = Path(os.path.expandvars(r'%LOCALAPPDATA%\Icarus\Saved\PlayerData'))
        if base_path.exists():
            for subdir in base_path.iterdir():
                if subdir.is_dir() and subdir.name.isdigit():
                    mounts_file = subdir / 'Mounts.json'
                    if mounts_file.exists():
                        return mounts_file
        raise FileNotFoundError("No Mounts.json found. Please specify steam_id.")

    return Path(os.path.expandvars(
        rf'%LOCALAPPDATA%\Icarus\Saved\PlayerData\{steam_id}\Mounts.json'
    ))


# =============================================================================
# Mount Data Classes
# =============================================================================

@dataclass
class MountInfo:
    """Summary information about a mount."""
    index: int
    name: str
    mount_type: str
    level: int
    experience: int
    health: int
    stamina: int


@dataclass
class MountData:
    """Full mount data including parsed properties."""
    index: int
    json_data: Dict[str, Any]
    properties: List[FPropertyTag]

    @property
    def name(self) -> str:
        return self.json_data.get('MountName', 'Unknown')

    @property
    def mount_type(self) -> str:
        return self.json_data.get('MountType', 'Unknown')

    @property
    def level(self) -> int:
        return self.json_data.get('MountLevel', 0)

    def get_property(self, path: str) -> Optional[FPropertyTag]:
        """Get a property by path."""
        return find_property(self.properties, path)

    def get_value(self, path: str) -> Any:
        """Get a property value by path."""
        prop = self.get_property(path)
        return prop.value if prop else None

    def set_value(self, path: str, value: Any) -> bool:
        """Set a property value by path."""
        return set_property_value(self.properties, path, value)

    def to_info(self) -> MountInfo:
        """Convert to summary info."""
        return MountInfo(
            index=self.index,
            name=self.name,
            mount_type=self.mount_type,
            level=self.level,
            experience=self.get_value('Experience') or 0,
            health=self.get_value('CharacterRecord.CurrentHealth') or 0,
            stamina=self.get_value('Stamina') or 0
        )


# =============================================================================
# Mount Editor
# =============================================================================

class MountEditor:
    """
    High-level editor for Icarus mount save files.

    Provides methods to load, modify, and save mount data with proper
    UE4 property serialization.
    """

    def __init__(self, steam_id: Optional[str] = None):
        """
        Initialize the mount editor.

        Args:
            steam_id: Steam ID for save file path. If None, auto-detects.
        """
        self.steam_id = steam_id
        self.file_path: Optional[Path] = None
        self.raw_data: Optional[Dict[str, Any]] = None
        self.mounts: List[MountData] = []
        self.serializer = PropertySerializer()
        self._modified = False

    @property
    def is_loaded(self) -> bool:
        return self.raw_data is not None

    @property
    def is_modified(self) -> bool:
        return self._modified

    def load(self, path: Optional[str] = None) -> None:
        """
        Load mounts from a JSON file.

        Args:
            path: Path to Mounts.json. If None, uses default Icarus path.
        """
        if path:
            self.file_path = Path(path)
        else:
            self.file_path = get_default_mounts_path(self.steam_id)

        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.raw_data = json.load(f)

        # Parse each mount's BinaryData
        self.mounts = []
        for i, mount_json in enumerate(self.raw_data.get('SavedMounts', [])):
            binary_data = bytes(mount_json['RecorderBlob']['BinaryData'])
            properties = self.serializer.deserialize(binary_data)
            self.mounts.append(MountData(
                index=i,
                json_data=mount_json,
                properties=properties
            ))

        self._modified = False
        print(f"Loaded {len(self.mounts)} mount(s) from {self.file_path}")

    def save(self, path: Optional[str] = None, backup: bool = True) -> Path:
        """
        Save mounts to a JSON file.

        Args:
            path: Output path. If None, overwrites the loaded file.
            backup: If True, creates a backup before saving.

        Returns:
            Path to the saved file.
        """
        if not self.is_loaded:
            raise RuntimeError("No data loaded. Call load() first.")

        output_path = Path(path) if path else self.file_path

        # Create backup
        if backup and output_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = output_path.with_suffix(f'.backup_{timestamp}.json')
            shutil.copy(output_path, backup_path)
            print(f"Backup created: {backup_path}")

        # Serialize each mount's properties back to BinaryData
        for mount in self.mounts:
            binary_data = self.serializer.serialize(mount.properties)
            mount.json_data['RecorderBlob']['BinaryData'] = list(binary_data)

        # Update the raw data
        self.raw_data['SavedMounts'] = [m.json_data for m in self.mounts]

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.raw_data, f, indent='\t')

        self._modified = False
        print(f"Saved {len(self.mounts)} mount(s) to {output_path}")
        return output_path

    def list_mounts(self) -> List[MountInfo]:
        """Get summary info for all mounts."""
        return [m.to_info() for m in self.mounts]

    def get_mount(self, index: int) -> MountData:
        """Get full mount data by index."""
        if index < 0 or index >= len(self.mounts):
            raise IndexError(f"Mount index {index} out of range (0-{len(self.mounts)-1})")
        return self.mounts[index]

    def find_mount_by_name(self, name: str) -> Optional[MountData]:
        """Find a mount by name (case-insensitive)."""
        name_lower = name.lower()
        for mount in self.mounts:
            if mount.name.lower() == name_lower:
                return mount
        return None

    def set_mount_property(self, index: int, path: str, value: Any) -> bool:
        """
        Set a mount property by path.

        Args:
            index: Mount index
            path: Property path (e.g., 'Experience', 'CharacterRecord.CurrentHealth')
            value: New value

        Returns:
            True if successful
        """
        mount = self.get_mount(index)
        if mount.set_value(path, value):
            self._modified = True
            return True
        return False

    def get_mount_property(self, index: int, path: str) -> Any:
        """
        Get a mount property by path.

        Args:
            index: Mount index
            path: Property path

        Returns:
            Property value or None if not found
        """
        mount = self.get_mount(index)
        return mount.get_value(path)

    def change_mount_type(self, index: int, target_type_name: str,
                          new_name: Optional[str] = None) -> None:
        """
        Change a mount's type (e.g., Horse -> Tusker).

        This modifies all the blueprint references and AI setup to match
        the new mount type.

        Args:
            index: Mount index
            target_type_name: Target mount type (e.g., "Tusker")
            new_name: Optional new name for the mount
        """
        mount = self.get_mount(index)

        # Get mount types
        source_type = get_mount_type(mount.mount_type)
        target_type = get_mount_type(target_type_name)

        if source_type is None:
            raise ValueError(f"Unknown source mount type: {mount.mount_type}")
        if target_type is None:
            raise ValueError(f"Unknown target mount type: {target_type_name}")

        if source_type.name == target_type.name:
            print(f"Mount is already a {target_type.name}")
            return

        print(f"Transforming {mount.name} from {source_type.name} to {target_type.name}")

        # Transform binary properties
        for prop_name in TRANSFORM_PROPERTIES:
            prop = find_property(mount.properties, prop_name)
            if prop and prop.value:
                old_value = prop.value
                new_value = get_transform_value(prop_name, source_type, target_type, old_value)
                prop.value = new_value
                print(f"  {prop_name}: {old_value} -> {new_value}")

        # Update JSON metadata
        mount.json_data['MountType'] = target_type.name

        # Optionally rename
        if new_name:
            self.set_mount_name(index, new_name)

        self._modified = True
        print(f"Mount type changed to {target_type.name}")

    def set_mount_name(self, index: int, new_name: str) -> None:
        """
        Change a mount's name.

        Args:
            index: Mount index
            new_name: New name for the mount
        """
        mount = self.get_mount(index)

        # Update binary property
        name_prop = find_property(mount.properties, 'MountName')
        if name_prop:
            old_name = name_prop.value
            name_prop.value = new_name
            print(f"  MountName: {old_name} -> {new_name}")

        # Update JSON metadata
        mount.json_data['MountName'] = new_name

        self._modified = True

    def set_mount_level(self, index: int, level: int) -> None:
        """
        Set a mount's level.

        Updates BOTH the JSON MountLevel and the binary Experience property
        to keep them synchronized.

        Args:
            index: Mount index
            level: New level (1-50)
        """
        if level < 1 or level > 50:
            raise ValueError("Mount level must be between 1 and 50")

        mount = self.get_mount(index)

        # Set JSON MountLevel (authoritative for game display)
        mount.json_data['MountLevel'] = level

        # Calculate and set Experience to match
        # XP formula estimated from natural mounts:
        # Level 30 ≈ 148,000 XP, Level 39 ≈ 420,000 XP
        # Using quadratic approximation: XP ≈ 165 * level^2
        experience = estimate_xp_for_level(level)
        exp_prop = find_property(mount.properties, 'Experience')
        if exp_prop:
            exp_prop.value = experience
            print(f"  MountLevel: {level}, Experience: {experience:,}")
        else:
            print(f"  MountLevel: {level} (WARNING: Experience property not found)")

        self._modified = True

    def clone_mount(self, source_index: int, new_name: str,
                    new_type: Optional[str] = None) -> int:
        """
        Clone an existing mount with a new name and optional type change.

        Args:
            source_index: Index of mount to clone
            new_name: Name for the new mount
            new_type: Optional new mount type

        Returns:
            Index of the new mount
        """
        import random
        import re

        source = self.get_mount(source_index)

        # Collect existing IDs to avoid duplicates
        existing_ids = set()
        for mount in self.mounts:
            obj_fname = find_property(mount.properties, 'ObjectFName')
            if obj_fname and obj_fname.value:
                match = re.search(r'_(\d+)$', obj_fname.value)
                if match:
                    existing_ids.add(int(match.group(1)))

        # Generate a new unique ID
        while True:
            new_id = random.randint(2147000000, 2147483647)
            if new_id not in existing_ids:
                break

        # Deep clone the JSON data
        new_json = json.loads(json.dumps(source.json_data))
        new_json['MountName'] = new_name
        new_json['DatabaseGUID'] = 'noguid'
        new_json['MountIconName'] = str(new_id)

        # Clone properties
        new_properties = clone_properties(source.properties)

        # Update MountName in binary
        name_prop = find_property(new_properties, 'MountName')
        if name_prop:
            name_prop.value = new_name

        # Update IcarusActorGUID with new unique ID
        guid_prop = find_property(new_properties, 'IcarusActorGUID')
        if guid_prop:
            guid_prop.value = new_id

        # Update ObjectFName with new unique ID
        obj_fname = find_property(new_properties, 'ObjectFName')
        if obj_fname and obj_fname.value:
            obj_fname.value = re.sub(r'_\d+$', f'_{new_id}', obj_fname.value)

        # Update ActorPathName with new unique ID
        actor_path = find_property(new_properties, 'ActorPathName')
        if actor_path and actor_path.value:
            actor_path.value = re.sub(r'_\d+$', f'_{new_id}', actor_path.value)

        # Create new mount
        new_mount = MountData(
            index=len(self.mounts),
            json_data=new_json,
            properties=new_properties
        )

        self.mounts.append(new_mount)
        self._modified = True

        new_index = new_mount.index
        print(f"Cloned mount '{source.name}' to '{new_name}' at index {new_index}")

        # Change type if requested
        if new_type:
            self.change_mount_type(new_index, new_type)

        return new_index

    def delete_mount(self, index: int) -> None:
        """
        Delete a mount by index.

        Args:
            index: Mount index to delete
        """
        mount = self.get_mount(index)
        name = mount.name
        del self.mounts[index]

        # Re-index remaining mounts
        for i, m in enumerate(self.mounts):
            m.index = i

        self._modified = True
        print(f"Deleted mount '{name}'")

    def reset_mount_talents(self, index: int) -> int:
        """
        Reset all talents for a mount, refunding talent points.

        Talents are stored as an ArrayProperty with nested StructProperty elements.
        The actual talent data is in .nested, not .value.

        Args:
            index: Mount index

        Returns:
            Number of talents that were reset (0 if none allocated)
        """
        mount = self.get_mount(index)

        # Find the Talents property
        talents_prop = find_property(mount.properties, 'Talents')
        if talents_prop is None:
            return 0

        # Talents are stored in .nested for ArrayProperty types
        talent_count = len(talents_prop.nested) if talents_prop.nested else 0
        if talent_count == 0:
            return 0

        # Clear talents by emptying the nested array
        talents_prop.nested = []
        self._modified = True

        return talent_count

    def set_horse_variant(self, index: int, variant: str) -> None:
        """
        Set workshop horse color variant (A1/A2/A3).

        Only works on Workshop Horse mounts (Horse_Standard type).
        - A1 = Brown horse
        - A2 = Black horse
        - A3 = White horse

        Args:
            index: Mount index
            variant: Variant code (A1, A2, or A3)

        Raises:
            ValueError: If variant is invalid or mount is not a Workshop Horse
        """
        variant = variant.upper()
        if variant not in ('A1', 'A2', 'A3'):
            raise ValueError(f"Invalid variant '{variant}'. Must be A1, A2, or A3.")

        mount = self.get_mount(index)

        # Check that this is a Workshop Horse (Horse_Standard)
        ai_setup = mount.get_value('AISetupRowName')
        if ai_setup is None:
            raise ValueError("Mount has no AISetupRowName property")

        # Workshop horses have AISetupRowName like "Mount_Horse_Standard_A1"
        if not ai_setup.startswith('Mount_Horse_Standard'):
            raise ValueError(
                f"Mount is not a Workshop Horse (AISetupRowName: {ai_setup}). "
                "Variant can only be set on Workshop horses."
            )

        # Update the variant
        new_ai_setup = f"Mount_Horse_Standard_{variant}"
        ai_prop = find_property(mount.properties, 'AISetupRowName')
        if ai_prop:
            old_value = ai_prop.value
            ai_prop.value = new_ai_setup
            self._modified = True
            print(f"  AISetupRowName: {old_value} -> {new_ai_setup}")

    def set_cosmetic_skin(self, index: int, skin_index: int) -> None:
        """
        Set the cosmetic skin index for a mount.

        Skins are stored in IntVariables array as CosmeticSkinIndex.
        This affects appearance for wild-tamed mounts like Terrenus.

        Args:
            index: Mount index
            skin_index: Skin index (0, 1, 2, etc.)

        Raises:
            ValueError: If IntVariables or CosmeticSkinIndex not found
        """
        mount = self.get_mount(index)

        # Find IntVariables array
        int_vars = find_property(mount.properties, 'IntVariables')
        if not int_vars or not int_vars.nested:
            raise ValueError("Mount has no IntVariables array")

        # Find CosmeticSkinIndex entry
        for var_struct in int_vars.nested:
            if not var_struct.nested:
                continue
            var_name = find_property(var_struct.nested, 'VariableName')
            var_value = find_property(var_struct.nested, 'iVariable')

            if var_name and var_name.value == 'CosmeticSkinIndex':
                old_value = var_value.value if var_value else '?'
                if var_value:
                    var_value.value = skin_index
                    self._modified = True
                    print(f"  CosmeticSkinIndex: {old_value} -> {skin_index}")
                    return

        raise ValueError("CosmeticSkinIndex not found in IntVariables")

    def validate_mount(self, index: int) -> List[str]:
        """
        Validate a mount's data integrity.

        Returns a list of issues found (empty if valid).
        """
        issues = []
        mount = self.get_mount(index)

        # Check required properties
        required = ['MountName', 'AISetupRowName', 'ActorClassName', 'Experience']
        for prop_name in required:
            prop = find_property(mount.properties, prop_name)
            if prop is None:
                issues.append(f"Missing required property: {prop_name}")
            elif prop.value is None:
                issues.append(f"Property has null value: {prop_name}")

        # Check mount type matches
        ai_setup = mount.get_value('AISetupRowName')
        if ai_setup:
            expected_type = None
            for mt in MOUNT_TYPES.values():
                if mt.ai_setup == ai_setup:
                    expected_type = mt.name
                    break
            if expected_type and expected_type != mount.mount_type:
                issues.append(
                    f"Mount type mismatch: JSON says '{mount.mount_type}' "
                    f"but AISetupRowName indicates '{expected_type}'"
                )

        # Check blueprint consistency
        actor_class = mount.get_value('ActorClassName')
        if actor_class and mount.mount_type in MOUNT_TYPES:
            expected_bp = MOUNT_TYPES[mount.mount_type].blueprint
            if actor_class != expected_bp:
                issues.append(
                    f"ActorClassName mismatch: '{actor_class}' "
                    f"should be '{expected_bp}'"
                )

        return issues


# =============================================================================
# Main (Test/Demo)
# =============================================================================

if __name__ == '__main__':
    import sys

    print("=" * 60)
    print("Icarus Mount Editor")
    print("=" * 60)
    print()

    try:
        editor = MountEditor()
        editor.load()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print()
    print("Mounts:")
    print("-" * 60)
    for info in editor.list_mounts():
        print(f"  [{info.index}] {info.name} ({info.mount_type})")
        print(f"      Level: {info.level}, HP: {info.health}, "
              f"Stamina: {info.stamina}, XP: {info.experience}")
    print()

    # Validation
    print("Validation:")
    print("-" * 60)
    for mount in editor.mounts:
        issues = editor.validate_mount(mount.index)
        if issues:
            print(f"  [{mount.index}] {mount.name}: {len(issues)} issue(s)")
            for issue in issues:
                print(f"      - {issue}")
        else:
            print(f"  [{mount.index}] {mount.name}: OK")
    print()

    # Demo: Show what would happen for a type change
    if editor.mounts:
        print("Demo transformation (not applied):")
        print("-" * 60)
        mount = editor.mounts[0]
        source_type = get_mount_type(mount.mount_type)
        target_type = get_mount_type('Tusker')
        if source_type and target_type and source_type.name != target_type.name:
            print(f"  Converting {mount.name} from {source_type.name} to {target_type.name}")
            for prop_name in TRANSFORM_PROPERTIES:
                prop = find_property(mount.properties, prop_name)
                if prop and prop.value:
                    new_val = get_transform_value(prop_name, source_type, target_type, prop.value)
                    print(f"    {prop_name}:")
                    print(f"      {prop.value}")
                    print(f"      -> {new_val}")
