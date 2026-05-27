# Material Processor
A tool for Ingestion, Standardization, and Conversion tool for all kinds of Material Networks
for complex multi-input/ multi-output materials in various DCCs.\
Supports USD file format.
Currently, it's in beta with support for Houdini's Arnold, MaterialX, PrincipledShader, 
and Redshift as regular nodes and usd prims.


<table>
  <tr>
    <td><img src="https://github.com/Ahmed-Hindy/AxeFx_tools/assets/23151881/0a330312-8809-44bf-b6a9-35e233c57eda" alt="PySide UI" width="250" /><br/>PySide UI</td>
    <td><img src="https://github.com/user-attachments/assets/6d0bb6ae-3bc9-4a0a-84a9-00e258134dec" alt="Right-click menu" width="250" /><br/>Right-click menu</td>
  </tr>
</table>


### Features
- [x] UI supports Drag and drop for dropping mat nodes from the Application.
- [x] Ingests and converts to Most Materials types: PrincipledShader, Arnold, MaterialX, Redshift.
- [x] pip-standard coding practices as much as possible and with proper logging.


### Installation
- On Windows: run the included batch installer `install_houdini_win.bat`.
  - Double-click `install_houdini_win.bat` in File Explorer.
  - The script copies the project folder to `%USERPROFILE%\Documents\HoudiniTools`.
  - The script also copies `Axe_Material_Processor.json` to `%USERPROFILE%\Documents\houdini21.0\packages`.
  - To install to a different Houdini version, run `install_houdini_win.bat <HOUDINI_VERSION>`, for example `install_houdini_win.bat 20.5`.
  - If you encounter permission or auditing errors, run .bat file as Administrator.
  - After installation, restart Houdini to load the tool.



### Roadmap
- [x] Add support for Solaris and USD files.
- [x] Finish implementation for Redshift.
- [ ] Add implementation for Vray and Renderman.
- [ ] Extend support to other apps like Substance Painter, Maya, and blender.



