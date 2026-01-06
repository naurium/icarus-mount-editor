# Icarus Mounts.json Schema Reference

Complete schema for the `Mounts.json` save file format, including both JSON fields and UE4 binary properties.

## File Location

```
%LocalAppData%\Icarus\Saved\PlayerData\{SteamID}\Mounts.json
```

---

## JSON Structure (Outer Wrapper)

```json
{
  "SavedMounts": [
    {
      "DatabaseGUID": "noguid",
      "RecorderBlob": {
        "ComponentClassName": "/Script/Icarus.IcarusMountCharacterRecorderComponent",
        "BinaryData": [/* UE4 serialized bytes */]
      },
      "MountName": "Bartholomew",
      "MountLevel": 17,
      "MountType": "Horse",
      "MountIconName": "298311"
    }
  ]
}
```

### JSON Fields

| Field | Type | Description |
|-------|------|-------------|
| `SavedMounts` | Array | Array of mount objects |
| `DatabaseGUID` | String | Unique identifier. Set to `"noguid"` for new/cloned mounts |
| `RecorderBlob` | Object | Container for binary UE4 data |
| `RecorderBlob.ComponentClassName` | String | Always `/Script/Icarus.IcarusMountCharacterRecorderComponent` |
| `RecorderBlob.BinaryData` | Array[int] | UE4 serialized properties as byte array |
| `MountName` | String | Display name shown in-game |
| `MountLevel` | Integer | Current level (1-50). **IMPORTANT:** This is the authoritative level value used by the game. Binary `Experience` is tracked separately. |
| `MountType` | String | Type key (e.g., `"Horse"`, `"Tusker"`, `"WoollyMammoth"`) |
| `MountIconName` | String | Icon identifier (numeric string) |

---

## Binary Properties (RecorderBlob.BinaryData)

The `BinaryData` array contains UE4 serialized properties. These are parsed using `PropertySerializer.deserialize()`.

### Core Properties

| Property | Type | Description |
|----------|------|-------------|
| `MountName` | StrProperty | Internal mount name |
| `AISetupRowName` | NameProperty | AI setup row (e.g., `Mount_Horse`, `Mount_Tusker`) |
| `ActorClassName` | NameProperty | Blueprint class (e.g., `BP_Mount_Horse_Standard_C`) |
| `ObjectFName` | NameProperty | Unique object ID (e.g., `BP_Mount_Horse_Standard_C_2147441213`) |
| `ActorPathName` | StrProperty | Full actor path including level and ID |
| `IcarusActorGUID` | IntProperty | Unique numeric ID for this mount instance |

### Stats

| Property | Type | Description |
|----------|------|-------------|
| `Experience` | IntProperty | Current XP amount (see Level System below) |
| `FoodLevel` | IntProperty | Current food level |
| `WaterLevel` | IntProperty | Current water level |
| `OxygenLevel` | IntProperty | Current oxygen level |
| `Stamina` | IntProperty | Current stamina |
| `CharacterRecord.CurrentHealth` | IntProperty | Current health points |

### Level System

**CRITICAL:** Mount level is tracked in TWO places that must stay synchronized:

1. **JSON `MountLevel`** - The authoritative level value displayed in-game
2. **Binary `Experience`** - The XP value stored in properties

When setting mount level programmatically, you MUST update BOTH:
- Set `MountLevel` in the JSON data
- Set `Experience` in binary properties to match

**Official XP Curve (extracted from `C_MountExperienceGrowth.uasset`):**

The game uses a cubic Hermite spline (FRichCurve) with 3 keypoints:

| Level | XP | Tangent |
|-------|-----|---------|
| 10 | 13,500 | 2,250 |
| 30 | 140,000 | 17,000 |
| 50 | 1,150,000 | 88,000 |

**Full XP Table (calculated from official curve):**

| Level | XP | Level | XP | Level | XP |
|-------|-----|-------|-----|-------|-----|
| 1 | 0 | 20 | 39,875 | 40 | 467,500 |
| 5 | 2,250 | 25 | 74,531 | 45 | 760,625 |
| 10 | 13,500 | 30 | 140,000 | **50** | **1,150,000** |
| 15 | 23,656 | 35 | 263,125 | | |

**Max level is 50** (1,150,000 XP). Levels set above 50 are capped by the game.

**WARNING:** Setting high `Experience` values without corresponding `MountLevel` will result in level appearing as 0 or 1 in-game.

### Behaviour States (Enums)

| Property | Type | Values |
|----------|------|--------|
| `CombatBehaviourState` | EnumProperty | `EMountCombatBehaviourState::NeutralEngagement`, etc. |
| `MovementBehaviourState` | EnumProperty | `EMountMovementBehaviourState::IdleStanding`, etc. |
| `ConsumptionBehaviourState` | EnumProperty | `EMountConsumptionBehaviourState::Any`, etc. |
| `GrazingBehaviourState` | EnumProperty | `EMountGrazingBehaviourState::Invalid`, etc. |
| `HusbandryBehaviourState` | EnumProperty | `EMountHusbandryBehaviourState::Invalid`, etc. |

### Ownership

| Property | Type | Description |
|----------|------|-------------|
| `OwnerCharacterID` | StructProperty | Owner identification struct |
| `OwnerCharacterID.PlayerID` | StrProperty | Steam ID of owner |
| `OwnerCharacterID.ChrSlot` | IntProperty | Character slot index |
| `OwnerName` | StrProperty | Display name of owner |
| `ParentCharacterUID` | IntProperty | Parent character UID (-1 if none) |
| `OwnerResolvePolicy` | EnumProperty | `EStateRecorderOwnerResolvePolicy::RespawnOnly`, etc. |

### Talents

| Property | Type | Description |
|----------|------|-------------|
| `Talents` | ArrayProperty | Array of `MountTalentSaveData` structs |

Each talent struct contains the talent configuration for the mount's skill tree.

### Inventory

| Property | Type | Description |
|----------|------|-------------|
| `SavedInventories` | ArrayProperty | Array of `InventorySaveData` structs |
| `SavedInventories[n].Slots` | ArrayProperty | Array of `InventorySlotSaveData` |
| `SavedInventories[n].Slots[n].InventoryID` | IntProperty | Slot inventory ID |

### Transform/Position

| Property | Type | Description |
|----------|------|-------------|
| `ActorTransform` | StructProperty | World transform data |
| `ActorTransform.Rotation` | Quat | Rotation quaternion (x, y, z, w) |
| `ActorTransform.Translation` | Vector | Position (x, y, z) |
| `ActorTransform.Scale3D` | Vector | Scale (x, y, z) - usually (1, 1, 1) |

### Stomach Contents

| Property | Type | Description |
|----------|------|-------------|
| `StomachContents` | ArrayProperty | Array of `StomachContentSaveData` structs |

Tracks what the mount has eaten.

### FLOD (Far Level of Detail) Data

| Property | Type | Description |
|----------|------|-------------|
| `FLODComponentData` | StructProperty | Level streaming data |
| `FLODComponentData.TileName` | NameProperty | Current tile |
| `FLODComponentData.LevelIndex` | IntProperty | Level index (-1 if not set) |
| `FLODComponentData.RecordIndex` | IntProperty | Record index (-1 if not set) |
| `FLODComponentData.InstanceIndex` | IntProperty | Instance index (-1 if not set) |
| `FLODComponentData.bSpawnedFromPool` | BoolProperty | Spawned from object pool |
| `FLODComponentData.bIsReservingInstance` | BoolProperty | Reserving FLOD instance |
| `FLODComponentData.CurrentFLODState` | IntProperty | Current LOD state |

### Resource/Energy Traits

| Property | Type | Description |
|----------|------|-------------|
| `EnergyTraitRecord.bActive` | BoolProperty | Energy trait active |
| `WaterTraitRecord.bActive` | BoolProperty | Water trait active |
| `GeneratorTraitRecord.bActive` | BoolProperty | Generator trait active |
| `ResourceComponentRecord.bDeviceActive` | BoolProperty | Device active |
| `ResourceComponentRecord.bDeviceManuallyShutdown` | BoolProperty | Manually shut down |
| `ResourceComponentRecord.ConnectionPriorityMask` | UInt32Property | Connection priority |

### Modifiers

| Property | Type | Description |
|----------|------|-------------|
| `Modifiers` | ArrayProperty | Array of `ModifierStateSaveData` structs |

Active status effects and modifiers.

---

## Variable Arrays (Cosmetics & State)

These arrays store dynamic state variables including **cosmetic skins**.

### IntVariables

| Property | Type | Description |
|----------|------|-------------|
| `IntVariables` | ArrayProperty | Array of `ActorIntVariableRecord` |

**Known Variables:**

| VariableName | Description |
|--------------|-------------|
| `CosmeticSkinIndex` | **Main skin/appearance variant** (0 = default) |
| `CosmeticSkinIndex_0` | Alternate skin index (-1 if not set) |
| `LastLevelAchieved` | Last level reached (tracking only, appears unused) |

**Terrenus Skin Indices (Verified In-Game):**

| Index | Appearance |
|-------|------------|
| 0 | Default - Orange and white coat |
| 1 | Brown - Solid brown coat |
| 2 | Brown & White - Brown and white patterned coat |
| 3-9 | Unknown - need in-game verification |

### BoolVariables

| Property | Type | Description |
|----------|------|-------------|
| `BoolVariables` | ArrayProperty | Array of `ActorBoolVariableRecord` |

**Known Variables:**

| VariableName | Description |
|--------------|-------------|
| `bIsWildTame` | Whether mount was wild-tamed (vs bred) |

### NameVariables

| Property | Type | Description |
|----------|------|-------------|
| `NameVariables` | ArrayProperty | Array of `ActorNameVariableRecord` |

### TextVariables

| Property | Type | Description |
|----------|------|-------------|
| `TextVariables` | ArrayProperty | Array of `ActorTextVariableRecord` |

### LinearColorVariables

| Property | Type | Description |
|----------|------|-------------|
| `LinearColorVariables` | ArrayProperty | Array of `LinearColorVariableRecord` |

Stores RGBA color values for cosmetic customization.

---

## Other Properties

| Property | Type | Description |
|----------|------|-------------|
| `ActorStateRecorderVersion` | IntProperty | Save format version (currently 3) |
| `bWasMovedToSubLevel` | BoolProperty | Level streaming flag |

---

## Example: Accessing Cosmetic Skin

```python
from mount_editor import MountEditor, find_property

editor = MountEditor(steam_id='YOUR_STEAM_ID')
editor.load()
mount = editor.get_mount(0)

# Find IntVariables array
int_vars = find_property(mount.properties, 'IntVariables')
if int_vars and int_vars.nested:
    for var in int_vars.nested:
        var_name = find_property(var.nested, 'VariableName')
        var_value = find_property(var.nested, 'iVariable')
        if var_name and var_name.value == 'CosmeticSkinIndex':
            print(f"Current skin index: {var_value.value}")
```

---

## Type Change Requirements

When changing mount type, update these properties:

1. `AISetupRowName` - AI setup row name
2. `ActorClassName` - Blueprint class name
3. `ObjectFName` - Object ID (keep numeric suffix)
4. `ActorPathName` - Full path (replace blueprint name)
5. JSON `MountType` field

See `mount_types.py` for valid type configurations.

---

## Unique ID Generation

Every mount needs unique identifiers:

| Field | Format | Example |
|-------|--------|---------|
| `IcarusActorGUID` | Integer | `298311` |
| `ObjectFName` | `{Blueprint}_{ID}` | `BP_Mount_Horse_Standard_C_2147441213` |
| `ActorPathName` | Full path with ID | `/Game/Maps/.../BP_Mount_Horse_Standard_C_2147441213` |
| JSON `MountIconName` | String of ID | `"298311"` |

When cloning, generate new IDs in range `2147000000-2147483647` and check for collisions.

---

## Property Types Reference

| UE4 Type | Python Value | Size |
|----------|--------------|------|
| IntProperty | int | 4 bytes |
| UInt32Property | int | 4 bytes |
| Int64Property | int | 8 bytes |
| FloatProperty | float | 4 bytes |
| DoubleProperty | float | 8 bytes |
| BoolProperty | bool | 1 byte + padding |
| StrProperty | str | length-prefixed |
| NameProperty | str | length-prefixed |
| EnumProperty | str | enum type + value |
| StructProperty | nested props | varies |
| ArrayProperty | list | count + elements |

---

## Notes

- All strings are null-terminated in the binary format
- Size fields in UE4 format are **critical** - must match actual serialized length
- The game must be closed before editing save files
- Always create backups before modifications
