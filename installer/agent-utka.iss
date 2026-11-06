#define AppName "Agent Utka"

[Setup]
AppId={{70D1CAD0-B140-41EC-8B68-E391F7731496}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Agent Utka
AppPublisherURL=https://github.com/utkazilla/agent-utka
DefaultDirName={localappdata}\Programs\Agent Utka
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=Agent-Utka-Setup-v{#AppVersion}-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\python\pythonw.exe

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Icons]
Name: "{autoprograms}\Agent Utka"; Filename: "{app}\python\pythonw.exe"; Parameters: "-E -s -B -m copilot.app --installed"; WorkingDir: "{app}"
Name: "{autodesktop}\Agent Utka"; Filename: "{app}\python\pythonw.exe"; Parameters: "-E -s -B -m copilot.app --installed"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-E -s -B -m copilot.app --installed"; WorkingDir: "{app}"; Description: "Open Agent Utka"; Flags: nowait postinstall skipifsilent
