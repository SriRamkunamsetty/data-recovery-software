"""Win32 constants, IOCTL definitions, and ctypes structures for raw storage access."""

import ctypes

# File access rights
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000

# Sharing mode
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004

# Creation disposition
OPEN_EXISTING = 3

# File flags and attributes
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_RANDOM_ACCESS = 0x10000000
FILE_FLAG_OVERLAPPED = 0x40000000

# Handle error sentinel
INVALID_HANDLE_VALUE: int = int(ctypes.c_void_p(-1).value or -1)

# Storage & Disk IOCTL control codes (CTL_CODE calculation)
IOCTL_DISK_GET_DRIVE_GEOMETRY = 0x00070000
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x002D1080
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000

# Storage property query types
StorageDeviceProperty = 0
PropertyStandardQuery = 0

# Storage Bus Types
STORAGE_BUS_TYPE_UNKNOWN = 0
STORAGE_BUS_TYPE_SCSI = 1
STORAGE_BUS_TYPE_ATAPI = 2
STORAGE_BUS_TYPE_ATA = 3
STORAGE_BUS_TYPE_1394 = 4
STORAGE_BUS_TYPE_SSA = 5
STORAGE_BUS_TYPE_FIBRE = 6
STORAGE_BUS_TYPE_USB = 7
STORAGE_BUS_TYPE_RAID = 8
STORAGE_BUS_TYPE_ISCSI = 9
STORAGE_BUS_TYPE_SAS = 10
STORAGE_BUS_TYPE_SATA = 11
STORAGE_BUS_TYPE_SD = 12
STORAGE_BUS_TYPE_MMC = 13
STORAGE_BUS_TYPE_VIRTUAL = 14
STORAGE_BUS_TYPE_FILE_BACKED_VIRTUAL = 15
STORAGE_BUS_TYPE_NVME = 17

BUS_TYPE_NAMES: dict[int, str] = {
    STORAGE_BUS_TYPE_UNKNOWN: "Unknown",
    STORAGE_BUS_TYPE_SCSI: "SCSI",
    STORAGE_BUS_TYPE_ATAPI: "ATAPI",
    STORAGE_BUS_TYPE_ATA: "ATA",
    STORAGE_BUS_TYPE_1394: "FireWire",
    STORAGE_BUS_TYPE_SSA: "SSA",
    STORAGE_BUS_TYPE_FIBRE: "Fibre Channel",
    STORAGE_BUS_TYPE_USB: "USB",
    STORAGE_BUS_TYPE_RAID: "RAID",
    STORAGE_BUS_TYPE_ISCSI: "iSCSI",
    STORAGE_BUS_TYPE_SAS: "SAS",
    STORAGE_BUS_TYPE_SATA: "SATA",
    STORAGE_BUS_TYPE_SD: "Secure Digital (SD)",
    STORAGE_BUS_TYPE_MMC: "MultiMediaCard (MMC)",
    STORAGE_BUS_TYPE_VIRTUAL: "Virtual",
    STORAGE_BUS_TYPE_FILE_BACKED_VIRTUAL: "File-Backed Virtual",
    STORAGE_BUS_TYPE_NVME: "NVMe",
}

# Win32 Error codes
ERROR_SUCCESS = 0
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_HANDLE = 6
ERROR_NOT_READY = 21
ERROR_CRC = 23
ERROR_SECTOR_NOT_FOUND = 27
ERROR_SHARING_VIOLATION = 32
ERROR_HANDLE_EOF = 38
ERROR_OPERATION_ABORTED = 995
ERROR_IO_INCOMPLETE = 996
ERROR_IO_PENDING = 997
ERROR_DEVICE_NOT_CONNECTED = 1167
ERROR_MORE_DATA = 234

# Named Pipe constants
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255
NMPWAIT_USE_DEFAULT_WAIT = 0


# ctypes Structures


class GET_LENGTH_INFORMATION(ctypes.Structure):
    """Structure returned by IOCTL_DISK_GET_LENGTH_INFO."""

    _fields_ = [("Length", ctypes.c_int64)]


class DISK_GEOMETRY(ctypes.Structure):
    """Legacy disk geometry structure."""

    _fields_ = [
        ("Cylinders", ctypes.c_int64),
        ("MediaType", ctypes.c_int32),
        ("TracksPerCylinder", ctypes.c_uint32),
        ("SectorsPerTrack", ctypes.c_uint32),
        ("BytesPerSector", ctypes.c_uint32),
    ]


class DISK_GEOMETRY_EX(ctypes.Structure):
    """Extended disk geometry structure containing disk size and sector size."""

    _fields_ = [
        ("Geometry", DISK_GEOMETRY),
        ("DiskSize", ctypes.c_int64),
        ("Data", ctypes.c_ubyte * 1),
    ]


class STORAGE_DEVICE_NUMBER(ctypes.Structure):
    """Structure returned by IOCTL_STORAGE_GET_DEVICE_NUMBER."""

    _fields_ = [
        ("DeviceType", ctypes.c_uint32),
        ("DeviceNumber", ctypes.c_uint32),
        ("PartitionNumber", ctypes.c_uint32),
    ]


class STORAGE_PROPERTY_QUERY(ctypes.Structure):
    """Query parameter for IOCTL_STORAGE_QUERY_PROPERTY."""

    _fields_ = [
        ("PropertyId", ctypes.c_int32),
        ("QueryType", ctypes.c_int32),
        ("AdditionalParameters", ctypes.c_ubyte * 1),
    ]


class STORAGE_DESCRIPTOR_HEADER(ctypes.Structure):
    """Header describing total size of a storage descriptor buffer."""

    _fields_ = [
        ("Version", ctypes.c_uint32),
        ("Size", ctypes.c_uint32),
    ]


class STORAGE_DEVICE_DESCRIPTOR(ctypes.Structure):
    """Device descriptor containing vendor, product ID, and serial offsets."""

    _fields_ = [
        ("Version", ctypes.c_uint32),
        ("Size", ctypes.c_uint32),
        ("DeviceType", ctypes.c_ubyte),
        ("DeviceTypeModifier", ctypes.c_ubyte),
        ("RemovableMedia", ctypes.c_bool),
        ("CommandQueueing", ctypes.c_bool),
        ("VendorIdOffset", ctypes.c_uint32),
        ("ProductIdOffset", ctypes.c_uint32),
        ("ProductRevisionOffset", ctypes.c_uint32),
        ("SerialNumberOffset", ctypes.c_uint32),
        ("BusType", ctypes.c_int32),
        ("RawPropertiesLength", ctypes.c_uint32),
        ("RawDeviceProperties", ctypes.c_ubyte * 1),
    ]


class DISK_EXTENT(ctypes.Structure):
    """Represents a physical disk extent of a volume."""

    _fields_ = [
        ("DiskNumber", ctypes.c_uint32),
        ("StartingOffset", ctypes.c_int64),
        ("ExtentLength", ctypes.c_int64),
    ]


class VOLUME_DISK_EXTENTS(ctypes.Structure):
    """Volume disk extents mapping volume paths to physical disk numbers."""

    _fields_ = [
        ("NumberOfDiskExtents", ctypes.c_uint32),
        ("Extents", DISK_EXTENT * 8),
    ]


class OVERLAPPED(ctypes.Structure):
    """Win32 asynchronous I/O OVERLAPPED structure."""

    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", ctypes.c_uint32),
        ("OffsetHigh", ctypes.c_uint32),
        ("hEvent", ctypes.c_void_p),
    ]
