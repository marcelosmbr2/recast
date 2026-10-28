; Inno Setup script for the Recast Windows installer.
; Built by packaging/build.ps1, which passes /DAppVersion=<version from recast.__version__>.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F0B2C5E-8E4A-4B7C-9D1A-3E2F5A7C9B10}
AppName=Recast
AppVersion={#AppVersion}
AppVerName=Recast {#AppVersion}
AppPublisher=Marcelosmbr
AppPublisherURL=https://github.com/marcelosmbr2/recast
AppSupportURL=https://github.com/marcelosmbr2/recast/issues
AppUpdatesURL=https://github.com/marcelosmbr2/recast/releases
VersionInfoVersion={#AppVersion}
; Per-user install without admin rights; the wizard still offers "install for all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Recast
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile=..\build\recast.ico
UninstallDisplayIcon={app}\Recast.exe
UninstallDisplayName=Recast
OutputDir=..\dist
OutputBaseFilename=Recast-{#AppVersion}-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Upgrades replace the whole bundle so files dropped by a newer build don't linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Recast\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; DestName: "THIRD-PARTY-NOTICES.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Recast"; Filename: "{app}\Recast.exe"
Name: "{autodesktop}\Recast"; Filename: "{app}\Recast.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Recast.exe"; Description: "{cm:LaunchProgram,Recast}"; Flags: nowait postinstall skipifsilent
