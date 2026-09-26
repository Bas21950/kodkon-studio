#ifndef AppVersion
#define AppVersion "0.4.2"
#endif

[Setup]
AppId={{7124A9C1-B760-48A5-8528-AC5D5B106192}}
AppName=กดก่อนคิดทีหลัง Studio
AppVersion={#AppVersion}
AppPublisher=Bas21950
DefaultDirName={localappdata}\Programs\KodKon Studio
DefaultGroupName=กดก่อนคิดทีหลัง Studio
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
SetupIconFile=..\..\release\installer-input\App\KodKon Studio\frontend\public\kodkon-studio.ico
UninstallDisplayIcon={app}\App\KodKon Studio\frontend\public\kodkon-studio.ico
OutputDir=..\..\release
OutputBaseFilename=kodkon-studio-{#AppVersion}-windows-setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Files]
Source: "..\..\release\installer-input\*"; DestDir: "{app}"; Excludes: "package-manifest.json"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\กดก่อนคิดทีหลัง Studio"; Filename: "{app}\Start Studio.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\App\KodKon Studio\frontend\public\kodkon-studio.ico"; Comment: "สร้างและจัดการโพสต์ภาพ/วิดีโอ"
Name: "{autodesktop}\กดก่อนคิดทีหลัง Studio"; Filename: "{app}\Start Studio.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\App\KodKon Studio\frontend\public\kodkon-studio.ico"; Comment: "สร้างและจัดการโพสต์ภาพ/วิดีโอ"

[Run]
Filename: "{app}\Start Studio.vbs"; Description: "เปิด กดก่อนคิดทีหลัง Studio"; Flags: postinstall nowait skipifsilent shellexec
