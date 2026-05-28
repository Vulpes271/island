# Procedural Blender Island With Two Villages

This project generates a complete stylized low-poly island scene in Blender using only the Blender Python API. The island includes ocean, beach, raised terrain, two visually different villages, roads, trees, coastal rocks, a dock, boats, lighting, and an isometric camera.

## Requirements

- Windows
- Blender
- `winget` for automatic Blender installation when Blender is missing

No external Python packages are required.

## Automatic Blender Installation

The run scripts first check whether Blender is available on PATH or in common Windows install locations. If no usable executable is found, they install Blender with:

```powershell
winget install BlenderFoundation.Blender --silent --accept-package-agreements --accept-source-agreements
```

After installation, the scripts check again and use common install paths such as:

- `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- `C:\Program Files\Blender Foundation\Blender 4.5\blender.exe`
- `C:\Program Files\Blender Foundation\Blender 4.4\blender.exe`
- `C:\Program Files\Blender Foundation\Blender 4.3\blender.exe`
- `C:\Program Files\Blender Foundation\Blender 4.2\blender.exe`

## Run With PowerShell

```powershell
.\run_blender_project.ps1
```

## Run Manually

If Blender is already available on PATH:

```powershell
blender --background --python scripts/create_island_scene.py
```

If Blender is installed but not on PATH, use the full executable path:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python scripts/create_island_scene.py
```

## Generated Files

Running the project creates:

- `output/island_two_villages.blend`
- `output/island_two_villages.glb`

The script creates the `output/` folder automatically if it does not exist.

## Preview The GLB

You can preview `output/island_two_villages.glb` by opening it in:

- Blender
- Windows 3D Viewer
- Any web-based glTF/GLB viewer
- A game engine that supports glTF, such as Godot, Unity, or Unreal Engine

## Push To GitHub

Create a new empty repository on GitHub, then run:

```powershell
git init
git add .
git commit -m "Create procedural Blender island scene"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

## Optional Git LFS

`.blend` and `.glb` files can become large. If you want Git LFS to manage them:

```powershell
git lfs install
git lfs track "*.blend"
git lfs track "*.glb"
git add .gitattributes
git add .
git commit -m "Track Blender outputs with Git LFS"
```

The `.gitignore` includes commented lines you can enable if you prefer not to commit generated output files.
