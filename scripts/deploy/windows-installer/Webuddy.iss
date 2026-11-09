#ifndef BundleRoot
  #error BundleRoot is required
#endif
#ifndef OutputRoot
  #error OutputRoot is required
#endif
#ifndef Commit
  #error Commit is required
#endif
[Setup]
AppId={{4B3F8918-76AA-42C1-A281-E21EC1DAF8B0}
AppName=Webuddy
AppVersion=2.0
AppVerName=Webuddy 2.0 ({#Commit})
DefaultDirName={localappdata}\Programs\Webuddy
DefaultGroupName=Webuddy
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputRoot}
OutputBaseFilename=Webuddy-Setup-{#Commit}-x64
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=no
UninstallDisplayIcon={app}\runtime\python\pythonw.exe
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
Name: "cursor"; Description: "安装 Cursor CLI（已有安装则复用，需要联网）"; Flags: checkedonce
Name: "lan"; Description: "允许局域网访问（仅本地子网，需要管理员确认）"; Flags: unchecked
[Files]
Source: "{#BundleRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autodesktop}\Webuddy"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"" start"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\Webuddy"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"" start"; WorkingDir: "{app}"
Name: "{group}\退出 Webuddy"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"" stop"; WorkingDir: "{app}"
Name: "{group}\登录 Cursor"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"" cursor-login"; WorkingDir: "{app}"
Name: "{group}\检查运行环境"; Filename: "{app}\check.cmd"; WorkingDir: "{app}"
Name: "{group}\卸载 Webuddy"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"" start"; Description: "打开 Webuddy"; Flags: postinstall nowait skipifsilent
[Code]
function StopOwnedServer(): Boolean;
var Code: Integer;
begin
  Result := True;
  if FileExists(ExpandConstant('{app}\desktop.py')) then
    Result := Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-B "' + ExpandConstant('{app}\desktop.py') + '" stop', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not StopOwnedServer() then Result := '请先在工作台停止正在执行的任务，再重试安装。';
end;
function InitializeUninstall(): Boolean;
begin
  Result := StopOwnedServer();
end;
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer; Args: String;
begin
  if CurStep = ssPostInstall then begin
    Args := '-B "' + ExpandConstant('{app}\desktop.py') + '" initialize';
    if WizardIsTaskSelected('lan') then Args := Args + ' --lan';
    if not Exec(ExpandConstant('{app}\runtime\python\python.exe'), Args, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      RaiseException('初始化失败。请保留安装目录并查看错误提示。');
    if WizardIsTaskSelected('cursor') then begin
      if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\cursor-setup.ps1') + '"', ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, Code) or (Code <> 0) then
        MsgBox('Webuddy 已安装，Cursor CLI 安装未完成。联网后重新运行安装程序并勾选 Cursor CLI。', mbInformation, MB_OK);
    end;
    if WizardIsTaskSelected('lan') then begin
      if not ShellExec('runas', ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\configure-firewall.ps1') + '"', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
        MsgBox('未能配置局域网防火墙。本机仍可使用；重新运行安装程序可重试。', mbInformation, MB_OK);
    end;
  end;
end;
