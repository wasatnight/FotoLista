#define MyAppVersion "1.0.2"

[Setup]
#ifdef SmokeTest
AppId=FotoListaSmokeValidation
CreateUninstallRegKey=no
#else
AppId={{D05F1D67-0FBF-4E49-9518-6152320C463D}
#endif
AppName=FotoLista
AppVersion={#MyAppVersion}
AppPublisher=Ivan Solano
DefaultDirName={localappdata}\Programs\FotoLista
DefaultGroupName=FotoLista
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\..
OutputBaseFilename=FotoLista-{#MyAppVersion}-Instalador
SetupIconFile=..\assets\fotolista.ico
UninstallDisplayIcon={app}\FotoLista.exe
WizardStyle=modern
Compression=lzma2/normal
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\FotoLista\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
#ifndef SmokeTest
Name: "{userprograms}\FotoLista"; Filename: "{app}\FotoLista.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\FotoLista"; Filename: "{app}\FotoLista.exe"; WorkingDir: "{app}"; Tasks: desktopicon
#endif

[Run]
#ifndef SmokeTest
Filename: "{app}\FotoLista.exe"; Description: "Abrir FotoLista"; Flags: nowait postinstall skipifsilent runasoriginaluser
#endif
