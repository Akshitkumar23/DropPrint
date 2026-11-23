; Script generated for Inno Setup 6.x
; DropPrint - 1-Click Shopkeeper Self-Service Printing Counter
#define MyAppName "DropPrint Counter"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DropPrint Systems"
#define MyAppURL "http://localhost:8000"
#define MyAppExeName "Start_DropPrint.bat"

[Setup]
AppId={{5A8E89F2-C02A-4D78-9B41-8C13F5B2F991}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName=C:\DropPrint
DefaultGroupName=DropPrint
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=DropPrint_Setup
SetupIconFile=assets\dropprint.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UsedUserAreasWarning=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
WizardImageFile=assets\wizard.bmp
WizardSmallImageFile=assets\wizard_small.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon} (🖨️ DropPrint Counter)"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Automatically start DropPrint when computer boots up"; GroupDescription: "Automatic Startup:"

[Files]
; Core Batch & Config
Source: "Start_DropPrint.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Stop_DropPrint.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Setup_Desktop_Shortcut.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Install_Windows_AutoStart.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "cloudflared.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "HANDOVER_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; Assets & Icons
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

; Frontend Web Application
Source: "frontend\*"; DestDir: "{app}\frontend"; Flags: ignoreversion recursesubdirs createallsubdirs

; Backend Server
Source: "mfp-print-scan-server\*"; DestDir: "{app}\mfp-print-scan-server"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.pyc, __pycache__, .pytest_cache, test_*, *.log, *.db, *.db-*, *.db-wal, *.db-shm, data\*"

; Virtual Printer Output Tray
Source: "Virtual_Printer_Tray\*"; DestDir: "{app}\Virtual_Printer_Tray"; Flags: ignoreversion recursesubdirs createallsubdirs

; Bundled Python Virtual Environment & Dependencies
Source: ".venv\*"; DestDir: "{app}\.venv"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.pyc, __pycache__, .pytest_cache"

[Icons]
Name: "{autodesktop}\DropPrint Counter"; Filename: "{app}\Start_DropPrint.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\dropprint.ico"; Tasks: desktopicon
Name: "{group}\DropPrint Counter"; Filename: "{app}\Start_DropPrint.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\dropprint.ico"
Name: "{group}\Stop DropPrint Services"; Filename: "{app}\Stop_DropPrint.bat"; WorkingDir: "{app}"
Name: "{group}\Handover Guide"; Filename: "{app}\HANDOVER_GUIDE.md"
Name: "{group}\Uninstall DropPrint"; Filename: "{uninstallexe}"
Name: "{autostartup}\DropPrint Counter"; Filename: "{app}\Start_DropPrint.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\dropprint.ico"; Tasks: startupicon

[Run]
Filename: "{app}\Start_DropPrint.bat"; Description: "Launch DropPrint Shopkeeper Counter immediately"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "{app}\Stop_DropPrint.bat"; RunOnceId: "StopDropPrintOnUninstall"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\mfp-print-scan-server\__pycache__"
Type: files; Name: "{app}\mfp-print-scan-server\print_system.db*"
Type: files; Name: "{app}\Virtual_Printer_Tray\*"
