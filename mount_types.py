#!/usr/bin/env python3
"""
Icarus Mount Type Configuration

Defines all vanilla mount types and their identifiers for save file modification.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MountSkin:
    """Information about a mount skin variant."""
    index: int          # CosmeticSkinIndex value
    name: str           # Descriptive name
    description: str    # Visual description


@dataclass
class MountType:
    """Configuration for a mount type."""
    name: str           # Display name (e.g., "Tusker")
    ai_setup: str       # AISetupRowName value (e.g., "Mount_Tusker")
    blueprint: str      # Blueprint class name (e.g., "BP_Mount_Tusker_C")
    description: str    # Brief description
    rideable: bool = True  # Can this mount be ridden? (False = companion only)
    skins: Optional[List[MountSkin]] = None  # Available skin variants

    @property
    def blueprint_prefix(self) -> str:
        """Get the blueprint prefix without _C suffix."""
        return self.blueprint.rstrip('_C')


# =============================================================================
# Mount Type Definitions
# =============================================================================

MOUNT_TYPES: Dict[str, MountType] = {
    # =========================================================================
    # IMPORTANT: "Horse" vs "Terrenus" Naming Confusion
    # =========================================================================
    # In save files:
    #   - "Horse" / Mount_Horse / BP_Mount_Horse_C = TERRENUS (wild alien creature)
    #   - "Horse_Standard" / Mount_Horse_Standard_A* / BP_Mount_Horse_Standard_C = ACTUAL HORSE
    #
    # Terrenus are purple boar-horse hybrid aliens tamed from the wild.
    # Workshop Horses are actual Earth horses unlocked via Workshop_Creature_Horse_A1/A2/A3.
    # =========================================================================

    "Terrenus": MountType(
        name="Terrenus",
        ai_setup="Mount_Horse",
        blueprint="BP_Mount_Horse_C",
        description="Wild alien creature (boar-horse hybrid). Tamed from the wild on Icarus.",
        skins=[
            MountSkin(0, "Default", "Orange and white coat"),
            MountSkin(1, "Brown", "Solid brown coat"),
            MountSkin(2, "Brown & White", "Brown and white patterned coat"),
        ]
    ),
    "Horse": MountType(
        name="Horse",
        ai_setup="Mount_Horse_Standard_A3",  # A1/A2/A3 are color variants
        blueprint="BP_Mount_Horse_Standard_C",
        description="Actual Earth horse. Unlocked via Workshop (3 color variants: A1/A2/A3).",
        skins=[
            # Workshop horses use A1/A2/A3 variants via AISetupRowName (not CosmeticSkinIndex)
            # All three variants have identical stats (HP 1440, Stamina 373, Speed 805)
            # A1 = Brown horse
            # A2 = Black horse
            # A3 = White horse
        ]
    ),
    "Moa": MountType(
        name="Moa",
        ai_setup="Mount_Moa",
        blueprint="BP_Mount_Moa_C",
        description="Fastest mount. Small inventory, two slots."
    ),
    "ArcticMoa": MountType(
        name="Arctic Moa",
        ai_setup="Mount_Arctic_Moa",
        blueprint="BP_Mount_Arctic_Moa_C",
        description="Cold-resistant arctic variant of Moa."
    ),
    "Buffalo": MountType(
        name="Buffalo",
        ai_setup="Mount_Buffalo",
        blueprint="BP_Mount_Buffalo_C",
        description="Strong, slow mount. Large carrying capacity."
    ),
    "Tusker": MountType(
        name="Tusker",
        ai_setup="Mount_Tusker",
        blueprint="BP_Mount_Tusker_C",
        description="Slowest but strongest. Found in arctic Styx regions."
    ),
    "Zebra": MountType(
        name="Zebra",
        ai_setup="Mount_Zebra",
        blueprint="BP_Mount_Zebra_C",
        description="Fast mount similar to Horse."
    ),
    "WoolyZebra": MountType(
        name="Wooly Zebra",
        ai_setup="Mount_Zebra_Shaggy",
        blueprint="BP_Mount_Wooly_Zebra_C",
        description="Cold-resistant woolly variant of Zebra."
    ),
    "SwampBird": MountType(
        name="SwampBird",
        ai_setup="Mount_SwampBird",
        blueprint="BP_Mount_SwampBird_C",
        description="Swamp-dwelling bird mount."
    ),
    "WoollyMammoth": MountType(
        name="Woolly Mammoth",
        ai_setup="Mount_WoollyMammoth",
        blueprint="BP_Mount_WoollyMammoth_C",
        description="Massive arctic mount with huge carrying capacity."
    ),
    # =========================================================================
    # COMPANION-ONLY TYPES (Cannot be mounted - summon/follow only)
    # =========================================================================
    "BluebackDaisy": MountType(
        name="Blueback Daisy",
        ai_setup="Mount_Blueback_Daisy",
        blueprint="BP_Mount_Blueback_Daisy_C",
        description="Companion only. Has skill tree. Summons as follower.",
        rideable=False
    ),
    "MiniHippo": MountType(
        name="Mini Hippo",
        ai_setup="Mount_MiniHippo",
        blueprint="BP_Mount_MiniHippo_Quest_C",
        description="Companion only. No skill tree. Quest reward creature.",
        rideable=False
    ),
    # NOTE: BP_Mount_Blueback_C exists but spawns with 1 HP - broken/unusable
}


def get_mount_type(name: str) -> Optional[MountType]:
    """Get a mount type by name (case-insensitive)."""
    # Direct lookup
    if name in MOUNT_TYPES:
        return MOUNT_TYPES[name]

    # Case-insensitive search
    name_lower = name.lower()
    for key, mount_type in MOUNT_TYPES.items():
        if key.lower() == name_lower:
            return mount_type

    return None


def list_mount_types() -> None:
    """Print all available mount types."""
    print("Available Mount Types:")
    print("-" * 60)
    for key, mt in MOUNT_TYPES.items():
        print(f"  {key:15} - {mt.description}")
    print()


# =============================================================================
# Mount Type Transformation Rules
# =============================================================================

# Properties that need to be modified when changing mount type
TRANSFORM_PROPERTIES = [
    'AISetupRowName',       # NameProperty: Mount_Horse -> Mount_Tusker
    'ActorClassName',       # NameProperty: BP_Mount_Horse_C -> BP_Mount_Tusker_C
    'ObjectFName',          # NameProperty: BP_Mount_Horse_C_XXXX -> BP_Mount_Tusker_C_XXXX
    'ActorPathName',        # StrProperty: Contains full path with blueprint name
]


def get_transform_value(prop_name: str, source_type: MountType, target_type: MountType,
                        current_value: str) -> str:
    """
    Calculate the new value for a property when transforming mount types.

    Args:
        prop_name: Property name being transformed
        source_type: Original mount type
        target_type: Target mount type
        current_value: Current property value

    Returns:
        New property value with mount type replaced
    """
    if prop_name == 'AISetupRowName':
        return target_type.ai_setup

    elif prop_name == 'ActorClassName':
        return target_type.blueprint

    elif prop_name == 'ObjectFName':
        # Format: BP_Mount_Horse_C_XXXXXXXXXX
        # Replace the blueprint part, keep the ID
        parts = current_value.rsplit('_', 1)
        if len(parts) == 2 and parts[1].isdigit():
            return f"{target_type.blueprint}_{parts[1]}"
        return current_value.replace(source_type.blueprint, target_type.blueprint)

    elif prop_name == 'ActorPathName':
        # Format: /Game/Maps/.../Level.BP_Mount_Horse_C_XXXXXXXXXX
        # Replace the blueprint reference in the path
        old_pattern = source_type.blueprint
        new_pattern = target_type.blueprint
        return current_value.replace(old_pattern, new_pattern)

    return current_value


# =============================================================================
# Main (Test/Demo)
# =============================================================================

if __name__ == '__main__':
    list_mount_types()

    print("Transformation example (Terrenus -> Tusker):")
    print("-" * 60)

    source = MOUNT_TYPES['Terrenus']
    target = MOUNT_TYPES['Tusker']

    test_values = {
        'AISetupRowName': 'Mount_Horse',
        'ActorClassName': 'BP_Mount_Horse_C',
        'ObjectFName': 'BP_Mount_Horse_C_2147441213',
        'ActorPathName': '/Game/Maps/Terrain_016_OLY/Terrain_016.Terrain_016:PersistentLevel.BP_Mount_Horse_C_2147441213'
    }

    for prop_name, current_value in test_values.items():
        new_value = get_transform_value(prop_name, source, target, current_value)
        print(f"\n{prop_name}:")
        print(f"  Before: {current_value}")
        print(f"  After:  {new_value}")
