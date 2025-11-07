@echo off
setlocal

rem Change to the folder containing this batch file
pushd "%~dp0" || (echo Failed to change directory & exit /b 1)

rem Source and folder name
set "SRC=%CD%"
for %%I in ("%SRC%") do set "FOLDER=%%~nI"

rem Destinations
set "DEST_BASE=%USERPROFILE%\Documents\HoudiniTools"
set "DEST=%DEST_BASE%\%FOLDER%"
set "PACKAGES=%USERPROFILE%\Documents\houdini20.5\packages"

rem Show diagnostics before copy
echo USERPROFILE=%USERPROFILE%
echo SRC=%SRC%
echo DEST_BASE=%DEST_BASE%
echo DEST=%DEST%

rem Ensure destinations exist (create final folder explicitly)
if not exist "%DEST_BASE%" mkdir "%DEST_BASE%"
if not exist "%DEST%" mkdir "%DEST%"
if not exist "%PACKAGES%" mkdir "%PACKAGES%"

echo Copying project folder "%SRC%" to "%DEST%"

rem Copy project files
robocopy "%SRC%" "%DEST%" /E /COPY:DAT /DCOPY:DA /R:3 /W:5 /MT:8
set "RC_MAIN=%ERRORLEVEL%"

if %RC_MAIN% GEQ 8 (
  echo Project copy finished with errors. robocopy exit code %RC_MAIN%.
) else (
  echo Project copy completed successfully. robocopy exit code %RC_MAIN%.
)

rem Show where files ended up
echo.
echo Listing contents of %DEST_BASE%:
dir "%DEST_BASE%" /b
echo.
echo Listing contents of %DEST%:
dir "%DEST%" /a

echo.
echo Checking for `Axe_Material_Processor.json` in "%SRC%"

set "RC_JSON=0"
if exist "%SRC%\Axe_Material_Processor.json" (
  echo Copying `Axe_Material_Processor.json` to "%PACKAGES%"
  robocopy "%SRC%" "%PACKAGES%" "Axe_Material_Processor.json" /COPY:DAT /R:3 /W:5
  set "RC_JSON=%ERRORLEVEL%"
  if %RC_JSON% GEQ 8 (
    echo JSON copy finished with errors. robocopy exit code %RC_JSON%.
  ) else (
    echo JSON file copied successfully. robocopy exit code %RC_JSON%.
  )
) else (
  echo `Axe_Material_Processor.json` not found in "%SRC%". Skipping JSON copy.
  set "RC_JSON=0"
)

rem Final existence check
if exist "%DEST%\" (
  echo Final folder exists: %DEST%
) else (
  echo Final folder not found: %DEST%
)

rem Exit with non-zero if any robocopy failed
if %RC_MAIN% GEQ 8 (
  popd
  endlocal
  exit /b 1
)
if %RC_JSON% GEQ 8 (
  popd
  endlocal
  exit /b 1
)

popd
endlocal
exit /b 0
