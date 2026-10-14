#define AppName "DeMark"
#define AppVersion "2.0.0"
#define AppPublisher "DeMark Team"
#define AppExeName "DeMark.exe"
#define GuideFileName "DeMark-新手使用说明.txt"

[Setup]
AppId={{2C09B218-44F8-4C91-B8E5-7A0F96582F84}
AppName={#AppName}
AppVerName={#AppName} {#AppVersion}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=dist\installer
OutputBaseFilename=DeMark-Setup-{#AppVersion}-CN-Friendly-Share
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}
InfoBeforeFile=installer_assets\install_guide.txt
InfoAfterFile=installer_assets\quick_start_guide.txt
ChangesAssociations=no
DisableProgramGroupPage=no
CloseApplications=no
ShowLanguageDialog=no
WizardImageFile=installer_assets\DeMarkWizardImage.bmp
WizardSmallImageFile=installer_assets\DeMarkWizardSmallImage.bmp

[Languages]
Name: "chinesesimplified"; MessagesFile: "installer_assets\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\DeMark\DeMark.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\DeMark\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "installer_assets\quick_start_guide.txt"; DestDir: "{app}"; DestName: "{#GuideFileName}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autoprograms}\{#AppName} 新手使用说明"; Filename: "{app}\{#GuideFileName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#GuideFileName}"; Description: "查看新手使用说明"; Flags: postinstall shellexec unchecked skipifsilent
