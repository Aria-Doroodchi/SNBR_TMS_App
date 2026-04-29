# SNBR TMS App — GUI Quick Start

## Prerequisites

- Python 3.14.3+
- Install CustomTkinter:

```
pip install customtkinter
```

## Running the App

From the `SNBR_TMS_App/` directory:

```
python main.py
```

## First Page: Import Settings

The app opens in **dark mode** by default. You can toggle to light mode using the **Dark Mode** switch in the top-right toolbar.

### Path Fields

| Field | Required | Description |
|---|---|---|
| MEM Files Directory | Yes | Folder containing `.MEM` files from Qtrack sessions |
| CSP MEM Files Directory | No | Folder containing CSP-specific `.MEM` files |
| Archive CSV File | No | A `.csv` archive file to build on (file picker, not folder) |

- Click **Browse** next to fields 1 or 2 to open a folder picker; field 3 opens a file picker filtered to `.csv`.
- You can also type or paste a path directly into the text box.
- If the default directories from `core/config.py` exist on disk, fields 1 and 2 are pre-populated automatically.
- Field 3 is pre-populated with the most recent `.csv` found in the archive directory (if any exist).

### Navigation

- **Back** is greyed out (this is page 1).
- **Next** validates that the MEM Files Directory is set and exists, then advances to the next step.
- If any filled-in path points to a non-existent folder or file, an error message appears in red.
