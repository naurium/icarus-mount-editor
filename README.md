# Icarus Mount Editor

A Python toolkit for editing mount save data in [Icarus](https://store.steampowered.com/app/1149460/Icarus/).

![Icarus Mount Editor Architecture](assets/icarus-mount-editor.jpg)

**Features:**
- Transform mount types (Horse to Tusker, etc.)
- Clone mounts with unique IDs
- Reset talent points

**Why I Made This** My woolly mammoth refused to fight in the desert. Just stood there, overheated and passive, while enemies swarmed our base. In-game solutions failed, and I couldn't install mods on my friends' server. So I asked Claude to help me hack the save files instead. One day later: a working toolkit and a new Ubi mount that fights in the desert.

> **Note:** Renaming mounts can be done in-game, so this tool focuses on operations the game doesn't support.

## Requirements

- **Windows** (Icarus is a Windows game; Linux users with Proton can use `--file` flag)
- **Python 3.8+**
- No external dependencies

## Installation

```bash
# Clone or download this folder
cd icarus-mount-editor

# No external dependencies required - uses Python 3.8+ standard library only
```

## Quick Start (CLI)

The easiest way to use the editor is via the command-line interface:

```bash
# List all your mounts
python mount_cli.py list

# Show detailed info for a mount
python mount_cli.py info 0

# Clone a mount
python mount_cli.py clone 0 "Shadow II"

# Set mount to max level
python mount_cli.py level 0 50

# Transform mount type
python mount_cli.py type 0 Tusker

# Change horse color (A1=brown, A2=black, A3=white)
python mount_cli.py variant 0 A3

# See all available commands
python mount_cli.py --help
```

The CLI auto-detects your Steam ID if you only have one Icarus account.

## CLI Commands

### Information
| Command | Description |
|---------|-------------|
| `list` | List all mounts with type and level |
| `info <mount>` | Show detailed mount properties |
| `types` | List available mount types |
| `validate` | Check mount data integrity |

### Modification
| Command | Description |
|---------|-------------|
| `rename <mount> <name>` | Rename a mount |
| `level <mount> <level>` | Set mount level (1-50) |
| `type <mount> <type>` | Change mount type |
| `clone <mount> <name>` | Clone a mount |
| `delete <mount>` | Delete a mount |
| `variant <mount> <A1\|A2\|A3>` | Change horse color variant |
| `skin <mount> <index>` | Set cosmetic skin index |
| `reset-talents <mount>` | Reset talents (refund points) |

### Utility
| Command | Description |
|---------|-------------|
| `backup` | Create a manual backup |
| `restore` | List or restore from backup |
| `config` | Show configuration |

## Quick Start (Python API)

For scripting or advanced usage:

```python
from mount_editor import MountEditor

# Load your mounts (find your Steam ID in your profile URL)
editor = MountEditor(steam_id='YOUR_STEAM_ID')
editor.load()

# List all mounts
for mount in editor.list_mounts():
    print(f"[{mount.index}] {mount.name} ({mount.mount_type})")

# Transform to a different type (optionally with a new name)
editor.change_mount_type(0, "Tusker", new_name="Oliphaunt")

# Clone a mount as a different type
editor.clone_mount(0, "Shadowfax Jr", new_type="WoollyMammoth")

# Save changes (creates backup automatically)
editor.save(backup=True)
```

## Available Mount Types

### Rideable Mounts (10 types)

| Type | Key | Description |
|------|-----|-------------|
| Terrenus | `Terrenus` | Wild alien creature. Fast, balanced. Tamed from the wild. |
| Horse | `Horse` | Actual Earth horse from Workshop. 3 color variants (A1/A2/A3). |
| Moa | `Moa` | Fastest mount. Small inventory, two slots. |
| Arctic Moa | `ArcticMoa` | Cold-resistant arctic variant of Moa. |
| Buffalo | `Buffalo` | Strong, slow mount. Large carrying capacity. |
| Tusker | `Tusker` | Slowest but strongest. Found in arctic Styx regions. |
| Zebra | `Zebra` | Fast mount similar to Terrenus. |
| Wooly Zebra | `WoolyZebra` | Cold-resistant woolly variant of Zebra. |
| Ubi | `SwampBird` | Swamp-dwelling bird mount. |
| Woolly Mammoth | `WoollyMammoth` | Massive arctic mount with huge carrying capacity. |

### Workshop Horse Variants

Workshop horses are unlocked via talents and come in 3 color variants (all with identical stats):
- `Workshop_Creature_Horse_A1` - Brown horse
- `Workshop_Creature_Horse_A2` - Black horse
- `Workshop_Creature_Horse_A3` - White horse

The color is determined by the `AISetupRowName` property (e.g., `Mount_Horse_Standard_A3`).
Stats: HP 1440, Stamina 373, Speed 805, Sprint 1518, Carry 220kg.

### Companion-Only (Cannot be mounted)

| Type | Key | Notes |
|------|-----|-------|
| Blueback Daisy | `BluebackDaisy` | Has skill tree. Summons as follower only. |
| Mini Hippo | `MiniHippo` | No skill tree. Quest reward creature. |

### Unreleased Mounts

| Type | Status |
|------|--------|
| `BP_Mount_Raptor_C` | Blueprint doesn't exist yet |
| `BP_Mount_Slinker_C` | Blueprint doesn't exist yet |

## API Reference

### MountEditor

```python
class MountEditor:
    def __init__(self, steam_id: Optional[str] = None)
    def load(self) -> None
    def save(self, backup: bool = True) -> Path
    def list_mounts(self) -> List[MountInfo]
    def get_mount(self, index: int) -> MountData
    def change_mount_type(self, index: int, new_type: str, new_name: str = None) -> None
    def clone_mount(self, source_index: int, new_name: str, new_type: str = None) -> int
    def delete_mount(self, index: int) -> None
    def set_mount_level(self, index: int, level: int) -> None
    def reset_mount_talents(self, index: int) -> int  # Returns count reset
    def set_horse_variant(self, index: int, variant: str) -> None  # A1/A2/A3
    def set_cosmetic_skin(self, index: int, skin_index: int) -> None
    def validate_mount(self, index: int) -> List[str]
```

### Working with Properties

```python
from mount_editor import MountEditor, find_property

editor = MountEditor(steam_id='YOUR_STEAM_ID')
editor.load()

mount = editor.get_mount(0)

# Access specific properties
experience = find_property(mount.properties, 'Experience')

# Reset talents using the editor method
reset_count = editor.reset_mount_talents(0)
print(f"Reset {reset_count} talents")

# Set horse variant (Workshop horses only)
editor.set_horse_variant(0, 'A3')  # A1=Brown, A2=Black, A3=White

editor.save()
```

## File Locations

### Icarus Save Data Structure

All Icarus save data is stored in:
```
%LocalAppData%\Icarus\Saved\
```

On Windows, this expands to:
```
C:\Users\{Username}\AppData\Local\Icarus\Saved\
```

### Player Data (Per-Account)

```
PlayerData\{SteamID}\
├── Mounts.json          # Global mount storage (this tool edits this)
├── Characters\          # Character profiles
├── Prospects\           # Per-session world saves
│   ├── {ProspectName}.json
│   └── ...
└── MetaInventory\       # Workshop/outpost items
```

**Finding your Steam ID:**
- Visit [steamid.io](https://steamid.io/) and enter your profile URL
- Or check the folder names in `PlayerData\` - there's usually only one

### Mount Data Format

`Mounts.json` structure:
```json
{
  "SavedMounts": [
    {
      "DatabaseGUID": "unique-guid",
      "MountName": "Horse",
      "MountLevel": 25,
      "MountType": "Horse",
      "MountIconName": "12345",
      "RecorderBlob": {
        "BinaryData": [/* base64-decoded byte array */]
      }
    }
  ]
}
```

The `RecorderBlob.BinaryData` contains UE4 serialized properties including:
- `MountName`, `AISetupRowName`, `ActorClassName`
- `Experience`, `Talents`, `CharacterRecord`
- `ObjectFName`, `ActorPathName`, `IcarusActorGUID`
- `CosmeticSkinIndex` (appearance variant)
- `bIsWildTame` (wild vs bred flag)

**For complete property documentation, see [SCHEMA.md](SCHEMA.md).**

### Game Installation (PAK Files)

Mount blueprints are defined in the game's PAK files:
```
{Steam Library}\steamapps\common\Icarus\Icarus\Content\Paks\
├── pakchunk0-WindowsNoEditor.pak
├── pakchunk0_s1-WindowsNoEditor.pak
├── ...
└── pakchunk0_s28-WindowsNoEditor.pak
```

**Key PAK file:** `pakchunk0_s18-WindowsNoEditor.pak` contains ~80% of mount references.

## How Mount Types Were Discovered

Valid mount blueprints were identified by scanning game PAK files for `BP_Mount_*` references.

The test suite includes PAK verification that scans your game installation:

```bash
# Run tests including PAK verification
python test_cli.py

# Skip PAK scan for faster testing
python test_cli.py --quick
```

### Validation Process

1. **PAK Scan**: Extract all `BP_Mount_*` references from game files
2. **AI Setup Check**: Verify corresponding `Mount_*` AI setup entries exist
3. **In-Game Test**: Create test mount with blueprint, load game, verify it appears
4. **Functionality Test**: Confirm mount can be summoned, ridden (if applicable), has correct stats

### Discovery Results

| Blueprint | AI Setup | In-Game Name | Status |
|-----------|----------|--------------|--------|
| BP_Mount_Horse_C | Mount_Horse | Terrenus | ✅ Rideable (wild tame) |
| BP_Mount_Horse_Standard_C | Mount_Horse_Standard_A* | Horse | ✅ Rideable (workshop) |
| BP_Mount_Moa_C | Mount_Moa | Moa | ✅ Rideable |
| BP_Mount_Arctic_Moa_C | Mount_Arctic_Moa | Arctic Moa | ✅ Rideable |
| BP_Mount_Buffalo_C | Mount_Buffalo | Buffalo | ✅ Rideable |
| BP_Mount_Tusker_C | Mount_Tusker | Tusker | ✅ Rideable |
| BP_Mount_Zebra_C | Mount_Zebra | Zebra | ✅ Rideable |
| BP_Mount_Wooly_Zebra_C | Mount_Zebra_Shaggy | Wooly Zebra | ✅ Rideable |
| BP_Mount_SwampBird_C | Mount_SwampBird | Ubi | ✅ Rideable |
| BP_Mount_WoollyMammoth_C | Mount_WoollyMammoth | Woolly Mammoth | ✅ Rideable |
| BP_Mount_Blueback_Daisy_C | Mount_Blueback_Daisy | Blueback Daisy | ⚠️ Companion only |
| BP_Mount_MiniHippo_Quest_C | Mount_MiniHippo | Mini Hippo | ⚠️ Companion only |
| BP_Mount_Blueback_C | Mount_Blueback | - | ❌ 1 HP |
| BP_Mount_Raptor_C | Mount_Raptor | - | ❌ No blueprint yet |
| BP_Mount_Slinker_C | Mount_Slinker | - | ❌ No blueprint yet |

## How It Works

### Parsing Flow

1. Load `Mounts.json` and extract `RecorderBlob.BinaryData`
2. Parse UE4 binary format into property tree (`FPropertyTag` objects)
3. Each property has: name, type, size, value (and nested properties for structs)

### Modification Flow

1. Find target property using `find_property()`
2. Modify `prop.value` directly
3. For type changes, update multiple related properties

### Serialization Flow

1. Serialize each property to temporary buffer
2. Calculate actual byte size from buffer length
3. Write size header, then buffer contents
4. Encode back to JSON format

## Safety

- **Backups**: The editor creates timestamped backups before every save
- **Validation**: Use `validate_mount()` to check data integrity
- **Game must be closed**: Always close Icarus before editing saves

## Troubleshooting

### Mount doesn't appear in-game
- The mount type may be invalid. Use only types from the "Available Mount Types" table.
- Check for duplicate ObjectFName IDs (clone_mount handles this automatically).

### Mount has 0 HP or wrong stats
- Stats are inherited from the mount type, not stored in the save.
- Changing type will give you that type's base stats.

### "Failed to load" errors
- Ensure the game is fully closed before editing.
- Restore from backup if needed (`.backup_YYYYMMDD_HHMMSS.json` files).

## Acknowledgements

- **[CrystalFerrai/UeSaveGame](https://github.com/CrystalFerrai/UeSaveGame)** - The UE4 property serialization in this toolkit was based on concepts from this C# library for reading/writing Unreal Engine save files.

## License

MIT License - See [LICENSE](LICENSE)

## Disclaimer

This tool modifies game save files. Use at your own risk. Not affiliated with RocketWerkz or the Icarus development team.
