@echo off
echo ============================================
echo  Building SNBR TMS App
echo ============================================
echo.
pip install -r requirements.txt
echo.
echo Running PyInstaller...
pyinstaller --clean SNBR_TMS_App.spec
echo.
echo ============================================
echo  Build complete!
echo  Output: dist\SNBR_TMS_App\SNBR_TMS_App.exe
echo ============================================
pause
