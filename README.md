# Materials Processor

A beta tool for ingestion, standardization, and conversion of material networks across DCCs.
It supports Houdini, Blender, and Maya material graph traversal, with USD MaterialX and OpenPBR export paths.

Current package version: `2.0.0-beta`.

<table>
  <tr>
    <td><img src="https://github.com/Ahmed-Hindy/AxeFx_tools/assets/23151881/0a330312-8809-44bf-b6a9-35e233c57eda" alt="PySide UI" width="250" /><br/>PySide UI</td>
    <td><img src="https://github.com/user-attachments/assets/6d0bb6ae-3bc9-4a0a-84a9-00e258134dec" alt="Right-click menu" width="250" /><br/>Right-click menu</td>
  </tr>
</table>

### Features

- [x] UI supports drag and drop for dropping material nodes from Houdini.
- [x] Houdini ingestion and conversion for Principled Shader, Arnold, MaterialX, Redshift, and OpenPBR paths.
- [x] Blender scene inspection and USD MaterialX/OpenPBR material export from the command line.
- [x] Maya scene inspection and USD MaterialX/OpenPBR material export from the command line.
- [x] Runtime validation for Blender and Maya.

### Installation

- For Python development, use `uv --native-tls sync`.
- On Windows: run the included batch installer `install_houdini_win.bat`.
  - Double-click `install_houdini_win.bat` in File Explorer.
  - The script copies the project folder to `%USERPROFILE%\Documents\HoudiniTools`.
  - The script also copies `Axe_Material_Processor.json` to `%USERPROFILE%\Documents\houdini21.0\packages`.
  - To install to a different Houdini version, run `install_houdini_win.bat <HOUDINI_VERSION>`, for example `install_houdini_win.bat 20.5`.
  - If you encounter permission or auditing errors, run the batch file as Administrator.
  - After installation, restart Houdini to load the tool.

### CLI Quickstart

Show the installed package version:

```powershell
uv --native-tls run materials-processor --version
```

Discover local DCC runtimes:

```powershell
uv --native-tls run materials-processor doctor
```

Run deeper runtime checks:

```powershell
uv --native-tls run materials-processor doctor --validate --material-smoke
```

Inspect a Blender scene without writing USD:

```powershell
uv --native-tls run materials-processor blender inspect "C:\path\to\scene.blend" --report-json "C:\temp\blender_report.json"
```

Export Blender materials to USD MaterialX and OpenPBR:

```powershell
uv --native-tls run materials-processor blender export-usd "C:\path\to\scene.blend" --out-dir "C:\temp\materials"
```

Use Blender texture remapping when a scene points at missing source paths:

```powershell
uv --native-tls run materials-processor blender inspect "C:\path\to\scene.blend" --texture-root "D:\textures" --missing-textures error
```

Inspect a Maya scene without writing USD:

```powershell
uv --native-tls run materials-processor maya inspect "C:\path\to\scene.ma" --report-json "C:\temp\maya_report.json"
```

Export Maya materials to USD MaterialX and OpenPBR:

```powershell
uv --native-tls run materials-processor maya export-usd "C:\path\to\scene.ma" --out-dir "C:\temp\maya_materials"
```

Validate a single runtime directly:

```powershell
uv --native-tls run materials-processor runtime validate --dcc blender --material-smoke
uv --native-tls run materials-processor runtime validate --dcc maya --material-smoke
```

### Current Limitations

- Blender node groups are reported as unsupported nodes; they are not expanded into USD yet.
- Blender texture remapping is available, but Maya texture remapping is not implemented yet.
- Maya CLI export currently traverses shading engines with surface shader connections in a saved `.ma` or `.mb` scene.
- Houdini remains the most mature in-DCC workflow. Blender and Maya CLI support are newer beta paths focused on graph extraction and USD material export.
- USD export currently targets MaterialX and OpenPBR material files, not full asset/shot USD assembly.

### Roadmap

- [x] Add support for Solaris and USD files.
- [x] Finish implementation for Redshift.
- [x] Add command line support for Blender.
- [x] Add command line support for Maya.
- [ ] Add a user-facing cross-DCC Qt launcher around the CLI workflows.
- [ ] Add implementation for Vray and Renderman.
- [ ] Extend support to other apps like Substance Painter.
