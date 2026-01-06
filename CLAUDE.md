# Claude Instructions: Icarus Mount Editor

## Project Overview

A Python toolkit for editing Icarus mount save files. Parses and re-serializes UE4 binary property data embedded in `Mounts.json`.

## Architecture

```
mount_cli.py         # Command-line interface
mount_editor.py      # High-level API (MountEditor class)
mount_types.py       # Mount type definitions (MOUNT_TYPES dict)
ue4_properties.py    # Low-level UE4 binary parser (FPropertyTag, PropertySerializer)
test_cli.py          # Test suite
```

### Data Flow

1. `Mounts.json` contains array of mounts with `RecorderBlob` field
2. `RecorderBlob.BinaryData` is base64-decoded to raw bytes
3. `PropertySerializer.deserialize()` parses UE4 property tree
4. Modifications made to `FPropertyTag` objects
5. `PropertySerializer.serialize()` re-encodes with correct size headers
6. Updated bytes written back to JSON

### Key Classes

- **MountEditor**: User-facing API for load/save/modify operations
- **MountData**: Single mount with `properties` (List[FPropertyTag]) and `json_data` (dict)
- **FPropertyTag**: UE4 property with name, type, size, value
- **PropertySerializer**: Binary parse/serialize logic

## Critical Implementation Details

### UE4 Property Size Headers

The `size` field in properties is **critical**. It must exactly match the serialized byte length of the value. The pattern:

```python
# Serialize to temp buffer first
temp = BytesIO()
value_size = serialize_value(temp, prop)

# THEN write the size
writer.write_int32(value_size)
writer.write(temp.getvalue())
```

Never calculate sizes upfront - always serialize first, then measure.

### Unique Mount IDs

Every mount needs unique identifiers across these properties:
- `ObjectFName`: `BP_Mount_Type_C_XXXXXXXXXX`
- `ActorPathName`: Contains the same ID
- `IcarusActorGUID`: The numeric ID

When cloning, generate new IDs in range `2147000000-2147483647` and check for collisions.

### Level System (CRITICAL)

Mount level is tracked in TWO places that must stay synchronized:

1. **JSON `MountLevel`** - The authoritative level value displayed in-game
2. **Binary `Experience`** - The XP value stored in properties

**IMPORTANT:** Setting `Experience` alone will NOT change the displayed level. You MUST set `MountLevel` in JSON as well.

Use `set_mount_level(index, level)` which handles both automatically.

**Official XP Curve** (extracted from `C_MountExperienceGrowth.uasset`):

| Level | XP | Level | XP |
|-------|-----|-------|-----|
| 10 | 13,500 | 40 | 467,500 |
| 20 | 39,875 | **50 (MAX)** | **1,150,000** |
| 30 | 140,000 | | |

### Mount Type Transformation

Changing mount type requires updating:
1. `AISetupRowName` (e.g., `Mount_Horse` → `Mount_Tusker`)
2. `ActorClassName` (e.g., `BP_Mount_Horse_C` → `BP_Mount_Tusker_C`)
3. `ObjectFName` (replace blueprint prefix, keep ID)
4. `ActorPathName` (replace blueprint in path)
5. JSON `MountType` field

## Valid Mount Types

From `mount_types.py` - only these blueprints work in-game:

### IMPORTANT: Terrenus vs Horse Naming

The game has confusing naming for horse-like mounts:

| Save File Type | In-Game Name | Origin |
|----------------|--------------|--------|
| `Horse` / `Mount_Horse` | **Terrenus** | Wild alien creature (purple boar-horse hybrid), tamed on Icarus |
| `Horse_Standard` / `Mount_Horse_Standard_A*` | **Horse** | Actual Earth horse, unlocked via Workshop (3 color variants) |

### Full Mount Table

| Key | Blueprint | AI Setup | Rideable |
|-----|-----------|----------|----------|
| Terrenus | BP_Mount_Horse_C | Mount_Horse | Yes |
| Horse | BP_Mount_Horse_Standard_C | Mount_Horse_Standard_A1/A2/A3 | Yes |
| Moa | BP_Mount_Moa_C | Mount_Moa | Yes |
| ArcticMoa | BP_Mount_Arctic_Moa_C | Mount_Arctic_Moa | Yes |
| Buffalo | BP_Mount_Buffalo_C | Mount_Buffalo | Yes |
| Tusker | BP_Mount_Tusker_C | Mount_Tusker | Yes |
| Zebra | BP_Mount_Zebra_C | Mount_Zebra | Yes |
| WoolyZebra | BP_Mount_Wooly_Zebra_C | Mount_Zebra_Shaggy | Yes |
| SwampBird | BP_Mount_SwampBird_C | Mount_SwampBird | Yes |
| WoollyMammoth | BP_Mount_WoollyMammoth_C | Mount_WoollyMammoth | Yes |
| BluebackDaisy | BP_Mount_Blueback_Daisy_C | Mount_Blueback_Daisy | No (companion) |
| MiniHippo | BP_Mount_MiniHippo_Quest_C | Mount_MiniHippo | No (companion) |

**Broken**: `BP_Mount_Blueback_C` (1 HP), `BP_Mount_Raptor_C` (doesn't exist), `BP_Mount_Slinker_C` (doesn't exist)

### Workshop Horse Variants

Workshop horses are unlocked via talents in Profile.json (all variants have identical stats):
- `Workshop_Creature_Horse_A1` - **Brown horse**
- `Workshop_Creature_Horse_A2` - **Black horse**
- `Workshop_Creature_Horse_A3` - **White horse**

Each creates a mount with `AISetupRowName: Mount_Horse_Standard_A*` where * is the variant number.
The color is baked into the AI setup, not stored as `CosmeticSkinIndex`.
Stats: HP 1440, Stamina 373, Speed 805, Sprint 1518, Carry 220kg.

> Note: A1/A2/A3 definitions are in server-side data tables, not game PAK files.

## Cosmetic Skins

Skins are stored in `IntVariables` array as `CosmeticSkinIndex`.

**Note:** `CosmeticSkinIndex` applies to wild-tamed mounts (like Terrenus). Workshop horses use A1/A2/A3 variants via `AISetupRowName` instead.

### Terrenus Skins (Verified In-Game)

| Index | Appearance |
|-------|------------|
| 0 | Default - Orange and white coat |
| 1 | Brown - Solid brown coat |
| 2 | Brown & White - Brown and white patterned coat |
| 3-9 | Unknown - need in-game verification |

## File Locations

```
%LocalAppData%\Icarus\Saved\PlayerData\{SteamID}\Mounts.json
```

## Complete Schema

See **[SCHEMA.md](SCHEMA.md)** for full documentation of all 40+ JSON and binary properties, including:
- Core identity fields (name, type, GUID)
- Stats (XP, health, stamina, food, water)
- Cosmetic variables (`CosmeticSkinIndex`, `bIsWildTame`)
- Behaviour states (combat, movement, grazing)
- Inventory, talents, transforms

## Testing Changes

1. Close Icarus completely
2. Make modifications with backup=True
3. Launch game and check mount list
4. If mount missing: blueprint invalid or ID collision
5. Restore from `.backup_*.json` if needed

## Code Style

- Python 3.8+ standard library only (no external deps)
- Type hints on all functions
- Dataclasses for data structures
- Keep backwards compatibility with existing save files

## Common Tasks

### Add New Mount Type

1. Find blueprint name in PAK files (search for `BP_Mount_`)
2. Test in-game by manually setting properties
3. If works, add to `MOUNT_TYPES` in `mount_types.py`

### Debug Serialization Issues

1. Compare `len(original_bytes)` vs `len(re_serialized_bytes)`
2. Use hex dump to find divergence point
3. Check size fields match actual content length
4. Verify string null terminators included in length

### Find Property in Mount

```python
from mount_editor import MountEditor, find_property

editor = MountEditor(steam_id='...')
editor.load()
mount = editor.get_mount(0)

# Find by name
prop = find_property(mount.properties, 'MountName')

# Find nested
health = find_property(mount.properties, 'CharacterRecord.CurrentHealth')
```
