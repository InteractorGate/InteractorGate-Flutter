; Instalador de InteractorGate (app de escritorio Windows).
; Empaqueta el build release de Flutter + el sidecar de mirada (gaze/),
; instala en Archivos de programa y crea icono en el escritorio y menu inicio.
;
; Compilar:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\InteractorGate.iss
; Salida:    installer\Output\InteractorGate-Setup.exe

#define MyAppName "InteractorGate"
#define MyAppPublisher "UPC - Tesis InteractorGate"
#define MyAppExeName "interactor_gate.exe"

; Rutas relativas al propio .iss (SourcePath = carpeta installer\). Asi funciona
; en cualquier maquina y en CI. Se pueden sobreescribir con ISCC /D...
#ifndef SourceDir
  #define SourceDir SourcePath + "..\build\windows\x64\runner\Release"
#endif
#ifndef MyOutputDir
  #define MyOutputDir SourcePath + "Output"
#endif
; Version del instalador (CI la pasa con /DMyAppVersion=x.y.z desde pubspec).
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{A7F3C2E1-9B4D-4E6A-8C1F-2D5B7E9A3C4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#MyOutputDir}
OutputBaseFilename=InteractorGate-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un icono en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent
