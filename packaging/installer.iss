#ifndef AppVersion
  #error AppVersion must be supplied by build.py
#endif

[Setup]
AppId={{A5BEE571-741E-4A07-BF23-236EC693A026}
AppName=WebScraper
AppVersion={#AppVersion}
AppPublisher=FEBA-MONT
AppPublisherURL=https://github.com/aiupdater/WebScraper
DefaultDirName={localappdata}\Programs\WebScraper
DefaultGroupName=WebScraper
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=WebScraper-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\WebScraper.exe
AppMutex=Local\WebScraper.Desktop
SetupMutex=Local\WebScraper.Setup
CloseApplications=no
RestartApplications=no

[Languages]
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "desktopicon"; Description: "Vytvořit ikonu na ploše"; Flags: unchecked

[Files]
Source: "..\dist\WebScraper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\WebScraper"; Filename: "{app}\WebScraper.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\WebScraper"; Filename: "{app}\WebScraper.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\WebScraper.exe"; Description: "Spustit WebScraper"; Flags: nowait postinstall skipifsilent

[Code]
const WebViewClient = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWebView2: Boolean;
var Version: String;
begin
  Result := (RegQueryStringValue(HKCU, WebViewClient, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM32, WebViewClient, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM64, WebViewClient, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  if HasWebView2 then Exit;
  if WizardSilent then begin
    Result := 'Chybí Microsoft Edge WebView2 Runtime. Spusťte instalátor interaktivně.';
    Exit;
  end;
  if MsgBox('Pro zobrazení aplikace je potřeba Microsoft Edge WebView2 Runtime. Stáhnout a nainstalovat jej nyní?', mbConfirmation, MB_YESNO) <> IDYES then begin
    Result := 'Bez WebView2 Runtime nelze dokončit instalaci.';
    Exit;
  end;
  try
    DownloadTemporaryFile('https://go.microsoft.com/fwlink/p/?LinkId=2124703', 'MicrosoftEdgeWebview2Setup.exe', '', nil);
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/install', '', SW_SHOW, ewWaitUntilTerminated, Code) then
      Result := 'Nelze spustit instalátor WebView2 Runtime.'
    else if not HasWebView2 then
      Result := 'WebView2 Runtime není dostupný. Ověřte internet a instalaci opakujte.';
  except
    Result := 'WebView2 Runtime se nepodařilo stáhnout. Ověřte internet a instalaci opakujte.';
  end;
end;
