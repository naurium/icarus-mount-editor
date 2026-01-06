#!/usr/bin/env python3
"""
UE4 Property Serialization Library for Python

A standalone Python implementation of Unreal Engine 4 property serialization,
based on CrystalFerrai/UeSaveGame. Handles reading and writing UE4 save file
binary data with proper size field management.

Usage:
    from ue4_properties import PropertySerializer

    # Parse binary data
    serializer = PropertySerializer()
    properties = serializer.deserialize(binary_data)

    # Modify properties
    properties['MountName'].value = "NewName"

    # Serialize back with correct sizes
    new_binary = serializer.serialize(properties)
"""

import struct
from io import BytesIO
from typing import Any, List, Optional
from dataclasses import dataclass, field


# =============================================================================
# Binary Reader/Writer
# =============================================================================

class BinaryReader:
    """Binary stream reader with UE4 type support."""

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.offset

    @property
    def position(self) -> int:
        return self.offset

    def read_bytes(self, n: int) -> bytes:
        if self.offset + n > len(self.data):
            raise EOFError(f"Cannot read {n} bytes at offset {self.offset}, only {self.remaining} remaining")
        result = self.data[self.offset:self.offset + n]
        self.offset += n
        return result

    def read_byte(self) -> int:
        return self.read_bytes(1)[0]

    def read_int32(self) -> int:
        return struct.unpack('<i', self.read_bytes(4))[0]

    def read_uint32(self) -> int:
        return struct.unpack('<I', self.read_bytes(4))[0]

    def read_int64(self) -> int:
        return struct.unpack('<q', self.read_bytes(8))[0]

    def read_float(self) -> float:
        return struct.unpack('<f', self.read_bytes(4))[0]

    def read_double(self) -> float:
        return struct.unpack('<d', self.read_bytes(8))[0]

    def read_fstring(self) -> Optional[str]:
        """
        Read UE4 FString with length prefix.

        Format:
        - length > 0: ASCII string (length includes null terminator)
        - length < 0: Unicode string (-length = char count, *2 for bytes)
        - length == 0: null string
        - length == 1: empty string (just null terminator)
        """
        length = self.read_int32()
        if length == 0:
            return None
        if length == 1:
            self.read_byte()  # null terminator
            return ""
        if length < 0:
            # Unicode (UTF-16-LE)
            byte_count = -length * 2
            data = self.read_bytes(byte_count)
            return data[:-2].decode('utf-16-le')  # Exclude null terminator
        else:
            # ASCII
            data = self.read_bytes(length)
            return data[:-1].decode('ascii')  # Exclude null terminator


class BinaryWriter:
    """Binary stream writer with UE4 type support."""

    def __init__(self, stream: Optional[BytesIO] = None):
        self.stream = stream or BytesIO()

    @property
    def position(self) -> int:
        return self.stream.tell()

    def get_bytes(self) -> bytes:
        return self.stream.getvalue()

    def write_bytes(self, data: bytes) -> int:
        return self.stream.write(data)

    def write_byte(self, value: int) -> int:
        return self.write_bytes(bytes([value]))

    def write_int32(self, value: int) -> int:
        return self.write_bytes(struct.pack('<i', value))

    def write_uint32(self, value: int) -> int:
        return self.write_bytes(struct.pack('<I', value))

    def write_int64(self, value: int) -> int:
        return self.write_bytes(struct.pack('<q', value))

    def write_float(self, value: float) -> int:
        return self.write_bytes(struct.pack('<f', value))

    def write_double(self, value: float) -> int:
        return self.write_bytes(struct.pack('<d', value))

    def write_fstring(self, value: Optional[str]) -> int:
        """
        Write UE4 FString with length prefix.
        Returns total bytes written.
        """
        if value is None:
            self.write_int32(0)
            return 4

        # Try ASCII first
        try:
            encoded = value.encode('ascii') + b'\x00'
            self.write_int32(len(encoded))
            self.write_bytes(encoded)
            return 4 + len(encoded)
        except UnicodeEncodeError:
            # Fall back to Unicode
            encoded = value.encode('utf-16-le') + b'\x00\x00'
            char_count = len(value) + 1  # +1 for null terminator
            self.write_int32(-char_count)
            self.write_bytes(encoded)
            return 4 + len(encoded)


# =============================================================================
# Property Types
# =============================================================================

@dataclass
class FPropertyTag:
    """UE4 Property metadata and value container."""

    name: str
    type_name: str
    value: Any = None

    # Type-specific metadata
    inner_type: Optional[str] = None  # For ArrayProperty
    struct_type: Optional[str] = None  # For StructProperty
    enum_type: Optional[str] = None  # For EnumProperty
    elem_name: Optional[str] = None  # For StructProperty arrays (element name)

    # For nested properties (structs, arrays)
    nested: List['FPropertyTag'] = field(default_factory=list)

    def __repr__(self):
        if self.type_name == 'StructProperty':
            return f"FPropertyTag({self.name}: {self.struct_type})"
        elif self.type_name == 'ArrayProperty':
            return f"FPropertyTag({self.name}: {self.inner_type}[{len(self.nested)}])"
        else:
            val = repr(self.value)
            if len(val) > 30:
                val = val[:30] + '...'
            return f"FPropertyTag({self.name}: {self.type_name} = {val})"

    def find(self, path: str) -> Optional['FPropertyTag']:
        """Find a nested property by dot-separated path."""
        parts = path.split('.', 1)
        name = parts[0]

        # Handle array indexing: "Name[0]"
        index = None
        if '[' in name:
            name, idx_str = name.rstrip(']').split('[')
            index = int(idx_str)

        for prop in self.nested:
            if prop.name == name:
                if index is not None:
                    if prop.type_name == 'ArrayProperty' and index < len(prop.nested):
                        target = prop.nested[index]
                    else:
                        return None
                else:
                    target = prop

                if len(parts) > 1:
                    return target.find(parts[1])
                return target

        return None


# Core struct types with fixed binary layouts (no property serialization)
CORE_STRUCT_TYPES = {
    'Vector': 12,        # 3 floats (X, Y, Z)
    'Vector2D': 8,       # 2 floats (X, Y)
    'Rotator': 12,       # 3 floats (Pitch, Yaw, Roll)
    'Quat': 16,          # 4 floats (X, Y, Z, W)
    'Transform': None,   # Nested properties
    'LinearColor': 16,   # 4 floats (R, G, B, A)
    'Color': 4,          # 4 bytes (B, G, R, A)
    'Guid': 16,          # 16 bytes
    'DateTime': 8,       # int64
    'Timespan': 8,       # int64
}


# =============================================================================
# Property Serializer
# =============================================================================

class PropertySerializer:
    """
    UE4 Property Serialization Helper.

    Handles reading and writing property lists with correct size field management.
    """

    def deserialize(self, data: bytes) -> List[FPropertyTag]:
        """Deserialize binary data into a list of FPropertyTag objects."""
        reader = BinaryReader(data)
        return self._read_properties(reader)

    def serialize(self, properties: List[FPropertyTag], add_trailing: bool = True) -> bytes:
        """Serialize a list of FPropertyTag objects to binary data."""
        writer = BinaryWriter()
        self._write_properties(writer, properties, add_trailing=add_trailing)
        return writer.get_bytes()

    # -------------------------------------------------------------------------
    # Deserialization
    # -------------------------------------------------------------------------

    def _read_properties(self, reader: BinaryReader) -> List[FPropertyTag]:
        """Read all properties until 'None' terminator."""
        properties = []
        while reader.remaining >= 4:
            prop = self._read_property(reader)
            if prop is None or prop.name == 'None':
                break
            properties.append(prop)
        return properties

    def _read_property(self, reader: BinaryReader, debug: bool = False) -> Optional[FPropertyTag]:
        """Read a single property tag and value."""
        if reader.remaining < 4:
            return None

        start_pos = reader.position

        # Read property name
        name = reader.read_fstring()
        if name is None or name == 'None':
            return FPropertyTag(name='None', type_name='terminator')

        if debug:
            print(f"  Reading property '{name}' at offset {start_pos}")

        # Read property type
        type_name = reader.read_fstring()

        # Read declared size (int32, not int64!)
        size = reader.read_int32()

        # Read array index (int32) - for older package versions
        array_index = reader.read_int32()

        prop = FPropertyTag(name=name, type_name=type_name)

        # Parse based on type - header is read before size is used
        if type_name == 'ArrayProperty':
            # Read inner type (header, outside of size)
            prop.inner_type = reader.read_fstring()
            # Read padding byte (also outside of size)
            reader.read_byte()
            # Now read value (within size)
            self._read_array_value(reader, prop, size)
        elif type_name == 'StructProperty':
            # Read struct type (header, outside of size)
            prop.struct_type = reader.read_fstring()
            # Read GUID (16 bytes) + padding (1 byte)
            reader.read_bytes(17)
            # Now read value (within size)
            self._read_struct_value(reader, prop, size)
        elif type_name == 'EnumProperty':
            prop.enum_type = reader.read_fstring()
            reader.read_byte()  # Padding
            prop.value = reader.read_fstring()
        elif type_name == 'MapProperty':
            self._read_map_property(reader, prop, size)
        elif type_name == 'BoolProperty':
            # For BoolProperty in older versions:
            # - Byte 1: the bool value
            # - Byte 2: extra padding byte (skipped in DeserializeProperty)
            bool_byte = reader.read_byte()
            prop.value = bool(bool_byte)
            reader.read_byte()  # Skip extra padding byte
        else:
            # Simple property - read padding byte then value
            reader.read_byte()
            self._read_simple_value(reader, prop, type_name, size)

        return prop

    def _read_property_tag(self, reader: BinaryReader) -> Optional[FPropertyTag]:
        """Read a property TAG only (header without value). Used for struct array prototypes."""
        if reader.remaining < 4:
            return None

        # Read property name
        name = reader.read_fstring()
        if name is None or name == 'None':
            return None

        # Read property type
        type_name = reader.read_fstring()

        # Read size (int32) - for prototype, this is the size of each element
        size = reader.read_int32()

        # Read array index (int32)
        array_index = reader.read_int32()

        prop = FPropertyTag(name=name, type_name=type_name)

        # Read type-specific header
        if type_name == 'StructProperty':
            prop.struct_type = reader.read_fstring()
            reader.read_bytes(16)  # GUID (no padding for prototype)
        elif type_name == 'ArrayProperty':
            prop.inner_type = reader.read_fstring()
        elif type_name == 'EnumProperty':
            prop.enum_type = reader.read_fstring()

        # Read padding/bool byte
        reader.read_byte()

        return prop

    def _read_array_value(self, reader: BinaryReader, prop: FPropertyTag, size: int) -> None:
        """Read ArrayProperty value (inner type and padding already read)."""
        # Element count
        count = reader.read_int32()

        if prop.inner_type == 'StructProperty':
            # For struct arrays, read the prototype property TAG (header only, no value)
            prototype = self._read_property_tag(reader)
            if prototype:
                prop.elem_name = prototype.name
                prop.struct_type = prototype.struct_type

                # Read each element's properties (data only, no headers)
                for _ in range(count):
                    elem = FPropertyTag(name=prototype.name, type_name='StructProperty',
                                       struct_type=prototype.struct_type)
                    elem.nested = self._read_properties(reader)
                    prop.nested.append(elem)
        elif prop.inner_type == 'ByteProperty':
            # Byte arrays are stored as raw bytes
            prop.value = list(reader.read_bytes(count))
        else:
            # Other simple arrays
            prop.value = []
            for _ in range(count):
                if prop.inner_type == 'IntProperty':
                    prop.value.append(reader.read_int32())
                elif prop.inner_type == 'FloatProperty':
                    prop.value.append(reader.read_float())
                elif prop.inner_type == 'StrProperty':
                    prop.value.append(reader.read_fstring())
                else:
                    # Fallback - calculate item size
                    remaining = size - 4  # Subtract count
                    item_size = remaining // count if count > 0 else 0
                    prop.value.append(reader.read_bytes(item_size))

    def _read_struct_value(self, reader: BinaryReader, prop: FPropertyTag, size: int) -> None:
        """Read StructProperty value (struct type and GUID already read)."""
        # Check for core struct types with fixed layout
        if prop.struct_type in CORE_STRUCT_TYPES:
            fixed_size = CORE_STRUCT_TYPES[prop.struct_type]
            if fixed_size is not None:
                self._read_core_struct(reader, prop, prop.struct_type)
                return

        # Regular struct - read nested properties within size boundary
        # The size field tells us exactly how many bytes the value takes
        start_pos = reader.position
        end_pos = start_pos + size

        # Debug: print struct info
        # print(f"    Reading struct {prop.struct_type} at {start_pos}, size={size}, end={end_pos}")

        prop.nested = []
        while reader.position < end_pos and reader.remaining >= 4:
            nested_prop = self._read_property(reader)
            if nested_prop is None or nested_prop.name == 'None':
                break
            prop.nested.append(nested_prop)

        # Ensure we've consumed exactly 'size' bytes
        bytes_read = reader.position - start_pos
        if bytes_read < size:
            # Skip remaining bytes if we hit None before end
            reader.read_bytes(size - bytes_read)

    def _read_simple_value(self, reader: BinaryReader, prop: FPropertyTag,
                            type_name: str, size: int) -> None:
        """Read a simple (non-container) property value (padding byte already read)."""
        if type_name == 'IntProperty':
            prop.value = reader.read_int32()
        elif type_name == 'UInt32Property':
            prop.value = reader.read_uint32()
        elif type_name == 'Int64Property':
            prop.value = reader.read_int64()
        elif type_name == 'FloatProperty':
            prop.value = reader.read_float()
        elif type_name == 'DoubleProperty':
            prop.value = reader.read_double()
        elif type_name in ('StrProperty', 'NameProperty'):
            prop.value = reader.read_fstring()
        else:
            # Unknown type - read raw bytes
            if size > 0:
                prop.value = reader.read_bytes(size)

    def _read_core_struct(self, reader: BinaryReader, prop: FPropertyTag,
                           struct_type: str) -> None:
        """Read a core struct type with fixed binary layout."""
        if struct_type == 'Vector':
            prop.value = {
                'x': reader.read_float(),
                'y': reader.read_float(),
                'z': reader.read_float()
            }
        elif struct_type == 'Vector2D':
            prop.value = {
                'x': reader.read_float(),
                'y': reader.read_float()
            }
        elif struct_type == 'Rotator':
            prop.value = {
                'pitch': reader.read_float(),
                'yaw': reader.read_float(),
                'roll': reader.read_float()
            }
        elif struct_type == 'Quat':
            prop.value = {
                'x': reader.read_float(),
                'y': reader.read_float(),
                'z': reader.read_float(),
                'w': reader.read_float()
            }
        elif struct_type == 'LinearColor':
            prop.value = {
                'r': reader.read_float(),
                'g': reader.read_float(),
                'b': reader.read_float(),
                'a': reader.read_float()
            }
        elif struct_type == 'Color':
            b, g, r, a = reader.read_bytes(4)
            prop.value = {'r': r, 'g': g, 'b': b, 'a': a}
        elif struct_type == 'Guid':
            prop.value = reader.read_bytes(16).hex()
        elif struct_type in ('DateTime', 'Timespan'):
            prop.value = reader.read_int64()

    def _read_enum_property(self, reader: BinaryReader, prop: FPropertyTag,
                             size: int) -> None:
        """Read an EnumProperty."""
        prop.enum_type = reader.read_fstring()
        reader.read_byte()  # Null byte
        prop.value = reader.read_fstring()

    def _read_map_property(self, reader: BinaryReader, prop: FPropertyTag,
                            size: int) -> None:
        """Read a MapProperty."""
        key_type = reader.read_fstring()
        value_type = reader.read_fstring()
        reader.read_byte()  # Null byte

        # Skip remaining bytes (map implementation is complex)
        remaining = size - (len(key_type) + 5) - (len(value_type) + 5) - 1
        if remaining > 0:
            prop.value = reader.read_bytes(remaining)

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def _write_properties(self, writer: BinaryWriter, properties: List[FPropertyTag],
                           add_trailing: bool = False) -> int:
        """Write all properties plus 'None' terminator. Returns bytes written."""
        total = 0
        for prop in properties:
            total += self._write_property(writer, prop)
        # Write terminator
        total += writer.write_fstring('None')
        # Some files have 4 trailing zero bytes after the terminator
        if add_trailing:
            writer.write_bytes(b'\x00\x00\x00\x00')
            total += 4
        return total

    def _write_property(self, writer: BinaryWriter, prop: FPropertyTag) -> int:
        """Write a single property tag and value. Returns bytes written."""
        start_pos = writer.position

        # Write property name
        writer.write_fstring(prop.name)

        # Write property type
        writer.write_fstring(prop.type_name)

        # Remember position for size field (we'll fill it in later)
        size_pos = writer.position
        writer.write_int32(0)  # Size placeholder (int32, not int64!)
        writer.write_int32(0)  # Array index (always 0 for our use case)

        if prop.type_name == 'ArrayProperty':
            # Write header (outside of size)
            writer.write_fstring(prop.inner_type)
            writer.write_byte(0)  # Padding

            # Write value (this is what size covers)
            value_start = writer.position
            self._write_array_value(writer, prop)
            value_size = writer.position - value_start

        elif prop.type_name == 'StructProperty':
            # Write header (outside of size)
            writer.write_fstring(prop.struct_type)
            writer.write_bytes(b'\x00' * 17)  # GUID (16 bytes) + padding (1 byte)

            # Write value (this is what size covers)
            value_start = writer.position
            self._write_struct_value(writer, prop)
            value_size = writer.position - value_start

        elif prop.type_name == 'EnumProperty':
            # Write header (outside of size)
            writer.write_fstring(prop.enum_type)
            writer.write_byte(0)  # Padding

            # Write value (this is what size covers)
            value_start = writer.position
            writer.write_fstring(prop.value)
            value_size = writer.position - value_start

        elif prop.type_name == 'BoolProperty':
            # For BoolProperty in older versions:
            # - Byte 1: the bool value
            # - Byte 2: extra padding byte
            writer.write_byte(1 if prop.value else 0)
            writer.write_byte(0)  # Extra padding byte
            value_size = 0  # No additional value data

        else:
            # Simple properties
            writer.write_byte(0)  # Padding

            # Write value (this is what size covers)
            value_start = writer.position
            self._write_simple_property_value(writer, prop)
            value_size = writer.position - value_start

        # Go back and fill in size
        end_pos = writer.position
        writer.stream.seek(size_pos)
        writer.write_int32(value_size)
        writer.stream.seek(end_pos)

        return writer.position - start_pos

    def _write_simple_property(self, writer: BinaryWriter, prop: FPropertyTag) -> None:
        """Write a simple property value with array index byte."""
        # Array index byte
        writer.write_byte(0)
        self._write_simple_property_value(writer, prop)

    def _write_simple_property_value(self, writer: BinaryWriter, prop: FPropertyTag) -> None:
        """Write just the simple property value (padding byte already written)."""
        if prop.type_name == 'IntProperty':
            writer.write_int32(prop.value)
        elif prop.type_name == 'UInt32Property':
            writer.write_uint32(prop.value)
        elif prop.type_name == 'Int64Property':
            writer.write_int64(prop.value)
        elif prop.type_name == 'FloatProperty':
            writer.write_float(prop.value)
        elif prop.type_name == 'DoubleProperty':
            writer.write_double(prop.value)
        elif prop.type_name in ('StrProperty', 'NameProperty'):
            writer.write_fstring(prop.value)
        elif isinstance(prop.value, bytes):
            writer.write_bytes(prop.value)

    def _write_array_value(self, writer: BinaryWriter, prop: FPropertyTag) -> None:
        """Write ArrayProperty value (header already written)."""
        # Element count
        count = len(prop.nested) if prop.inner_type == 'StructProperty' else \
                len(prop.value) if isinstance(prop.value, (list, bytes)) else 0
        writer.write_int32(count)

        if prop.inner_type == 'StructProperty':
            # For struct arrays, write a prototype property tag
            # This is a FULL property tag (name, type, size, array index, header, padding)
            elem_name = prop.elem_name
            struct_type = prop.struct_type

            if count > 0:
                first = prop.nested[0]
                elem_name = elem_name or first.name
                struct_type = struct_type or first.struct_type

            # Build prototype as a StructProperty tag
            prototype = FPropertyTag(
                name=elem_name or prop.name,
                type_name='StructProperty',
                struct_type=struct_type or ''
            )

            # Calculate size of all element data
            temp = BinaryWriter()
            for elem in prop.nested:
                self._write_properties(temp, elem.nested)
            elem_data = temp.get_bytes()

            # Write prototype property tag (this is a full property header)
            # The prototype's size field is the total size of all elements
            self._write_prototype_tag(writer, prototype, len(elem_data))

            # Write element data
            writer.write_bytes(elem_data)

        elif prop.inner_type == 'ByteProperty':
            data = prop.value if isinstance(prop.value, (bytes, list)) else []
            writer.write_bytes(bytes(data))
        else:
            values = prop.value if isinstance(prop.value, list) else []
            for val in values:
                if prop.inner_type == 'IntProperty':
                    writer.write_int32(val)
                elif prop.inner_type == 'FloatProperty':
                    writer.write_float(val)
                elif prop.inner_type == 'StrProperty':
                    writer.write_fstring(val)

    def _write_prototype_tag(self, writer: BinaryWriter, prop: FPropertyTag, elem_size: int) -> None:
        """Write a prototype property tag for struct arrays."""
        # Name
        writer.write_fstring(prop.name)
        # Type
        writer.write_fstring(prop.type_name)
        # Size (int32) - this is the size of all elements combined
        writer.write_int32(elem_size)
        # Array index (int32)
        writer.write_int32(0)
        # Header for StructProperty
        writer.write_fstring(prop.struct_type)
        writer.write_bytes(b'\x00' * 16)  # GUID
        # Padding byte
        writer.write_byte(0)

    def _write_struct_value(self, writer: BinaryWriter, prop: FPropertyTag) -> None:
        """Write StructProperty value (header already written)."""
        # Check for core struct types
        if prop.struct_type in CORE_STRUCT_TYPES:
            fixed_size = CORE_STRUCT_TYPES[prop.struct_type]
            if fixed_size is not None:
                self._write_core_struct(writer, prop, prop.struct_type)
                return

        # Regular struct - write nested properties
        self._write_properties(writer, prop.nested)

    def _write_core_struct(self, writer: BinaryWriter, prop: FPropertyTag,
                            struct_type: str) -> None:
        """Write a core struct type with fixed binary layout."""
        v = prop.value or {}

        if struct_type == 'Vector':
            writer.write_float(v.get('x', 0.0))
            writer.write_float(v.get('y', 0.0))
            writer.write_float(v.get('z', 0.0))
        elif struct_type == 'Vector2D':
            writer.write_float(v.get('x', 0.0))
            writer.write_float(v.get('y', 0.0))
        elif struct_type == 'Rotator':
            writer.write_float(v.get('pitch', 0.0))
            writer.write_float(v.get('yaw', 0.0))
            writer.write_float(v.get('roll', 0.0))
        elif struct_type == 'Quat':
            writer.write_float(v.get('x', 0.0))
            writer.write_float(v.get('y', 0.0))
            writer.write_float(v.get('z', 0.0))
            writer.write_float(v.get('w', 0.0))
        elif struct_type == 'LinearColor':
            writer.write_float(v.get('r', 0.0))
            writer.write_float(v.get('g', 0.0))
            writer.write_float(v.get('b', 0.0))
            writer.write_float(v.get('a', 0.0))
        elif struct_type == 'Color':
            writer.write_bytes(bytes([
                v.get('b', 0),
                v.get('g', 0),
                v.get('r', 0),
                v.get('a', 0)
            ]))
        elif struct_type == 'Guid':
            if isinstance(v, str):
                writer.write_bytes(bytes.fromhex(v))
            else:
                writer.write_bytes(b'\x00' * 16)
        elif struct_type in ('DateTime', 'Timespan'):
            writer.write_int64(v if isinstance(v, int) else 0)

    def _write_enum_property(self, writer: BinaryWriter, prop: FPropertyTag) -> None:
        """Write an EnumProperty."""
        writer.write_fstring(prop.enum_type)
        writer.write_byte(0)  # Null byte
        writer.write_fstring(prop.value)


# =============================================================================
# Utility Functions
# =============================================================================

def find_property(properties: List[FPropertyTag], path: str) -> Optional[FPropertyTag]:
    """
    Find a property by dot-separated path.

    Examples:
        find_property(props, "MountName")
        find_property(props, "CharacterRecord.CurrentHealth")
        find_property(props, "SavedInventories[0].Slots")
    """
    parts = path.split('.', 1)
    name = parts[0]

    # Handle array indexing
    index = None
    if '[' in name:
        name, idx_str = name.rstrip(']').split('[')
        index = int(idx_str)

    for prop in properties:
        if prop.name == name:
            if index is not None:
                if prop.type_name == 'ArrayProperty' and index < len(prop.nested):
                    target = prop.nested[index]
                else:
                    return None
            else:
                target = prop

            if len(parts) > 1:
                if target.nested:
                    return find_property(target.nested, parts[1])
                return None
            return target

    return None


def set_property_value(properties: List[FPropertyTag], path: str, value: Any) -> bool:
    """
    Set a property value by path.
    Returns True if successful, False if property not found.
    """
    prop = find_property(properties, path)
    if prop is None:
        return False
    prop.value = value
    return True


def clone_properties(properties: List[FPropertyTag]) -> List[FPropertyTag]:
    """Deep clone a list of properties."""
    serializer = PropertySerializer()
    data = serializer.serialize(properties)
    return serializer.deserialize(data)


# =============================================================================
# Main (Test/Demo)
# =============================================================================

if __name__ == '__main__':
    import json
    import sys
    import os

    # Load test data - pass your Mounts.json path as argument
    if len(sys.argv) < 2:
        # Try default location
        steam_id = os.environ.get('STEAM_ID', 'YOUR_STEAM_ID')
        json_path = os.path.expandvars(
            rf'%LocalAppData%\Icarus\Saved\PlayerData\{steam_id}\Mounts.json'
        )
    else:
        json_path = sys.argv[1]

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Test file not found: {json_path}")
        print("\nUsage: python ue4_properties.py [path/to/Mounts.json]")
        print("Or set STEAM_ID environment variable")
        exit(1)

    binary_data = bytes(data['SavedMounts'][0]['RecorderBlob']['BinaryData'])
    print(f"Original size: {len(binary_data)} bytes")

    # Deserialize
    serializer = PropertySerializer()
    properties = serializer.deserialize(binary_data)

    print(f"Parsed {len(properties)} top-level properties:")
    for prop in properties[:10]:
        print(f"  - {prop}")
    if len(properties) > 10:
        print(f"  ... and {len(properties) - 10} more")

    # Test finding properties
    print("\nProperty search tests:")
    for path in ['MountName', 'AISetupRowName', 'Experience', 'CharacterRecord.CurrentHealth']:
        prop = find_property(properties, path)
        if prop:
            print(f"  {path}: {prop.value}")
        else:
            print(f"  {path}: NOT FOUND")

    # Re-serialize
    new_data = serializer.serialize(properties)
    print(f"\nRe-serialized size: {len(new_data)} bytes")

    # Compare
    if new_data == binary_data:
        print("SUCCESS: Round-trip serialization matches exactly!")
    else:
        print("WARNING: Round-trip data differs")
        # Find first difference
        for i, (a, b) in enumerate(zip(binary_data, new_data)):
            if a != b:
                print(f"  First difference at offset {i}: original={a}, new={b}")
                break
        if len(binary_data) != len(new_data):
            print(f"  Size difference: {len(new_data) - len(binary_data):+d} bytes")
