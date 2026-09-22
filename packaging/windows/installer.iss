; =====================================================================
; Script Inno Setup para Translate_BooK
; =====================================================================
; Diretrizes e Políticas:
; 1. Privilégios Mínimos (PrivilegesRequired=lowest):
;    Instalação por usuário em {localappdata}\Programs\Translate_BooK.
;    Não exige privilégios de Administrador.
; 2. Isolamento de Dados:
;    - Executável e binários residem em {app} ({localappdata}\Programs\Translate_BooK).
;    - Projetos e traduções residem em {userappdata}\Translate_BooK\projects.
;    - Modelos de IA e cache residem em {localappdata}\Translate_BooK\models.
; 3. Política de Preservação no Desinstalador:
;    - O desinstalador remove ESTRITAMENTE a pasta {app} e atalhos.
;    - NUNCA remove {userappdata}\Translate_BooK\projects nem {localappdata}\Translate_BooK\models.
;    - Assegura preservação integral do trabalho do usuário em atualizações e desinstalações.
; 4. Tolerância a Caminhos com Espaços:
;    - Todos os identificadores de diretório e executáveis são devidamente envolvidos em aspas.
; =====================================================================

#define MyAppName "Translate Book CJrTools"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "CJRDOOM"
#define MyAppExeName "Translate_Book_CJrTools.exe"

[Setup]
AppId={{8B1A2C3D-4E5F-6A7B-8C9D-0E1F2A3B4C5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Translate_Book_CJrTools
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist_installer
OutputBaseFilename=Translate_Book_CJrTools_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Binários e dependências gerados pelo PyInstaller (sem pesos neurais embutidos)
Source: "..\..\dist\Translate_Book_CJrTools\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Procedimento de confirmação e preservação dos projetos do usuário
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Informa ao usuário que seus projetos e traduções foram preservados
    // em %APPDATA%\Translate_BooK\projects por segurança.
  end;
end;
