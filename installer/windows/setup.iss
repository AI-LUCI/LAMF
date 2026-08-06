; LAMF Windows Installer (Inno Setup)
;
; Builds LAMF-Setup-x64.exe.  This source is intentionally static: all
; variable data (version, timestamp) is supplied by the build orchestrator
; through the command line or discovered from the payload.  No build-machine
; paths, tokens, or mutable URLs are embedded here.

#define MyAppName "LAMF"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "LAMF Project"
#define MyAppURL "https://github.com/AI-LUCI/LAMF"
#define MyAppExeName "lamf.exe"
#define MyAppControlName "lamf-control.exe"

[Setup]
AppId={{LAMF-Windows-11-Local-Agent-Memory-Fabric}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\LAMF
DisableDirPage=no
DisableProgramGroupPage=yes
DefaultGroupName={#MyAppName}
OutputDir=..\..\dist
OutputBaseFilename=LAMF-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallFilesDir={app}\uninstall

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon for LAMF Control"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Dirs]
Name: "{app}"; Permissions: users-modify
Name: "{code:GetDataDir}"; Permissions: users-modify

[Files]
; Payload installed verbatim.  The payload already contains the embedded
; Python runtime, LAMF application code, optimization pack, licenses, and
; manifest.  Flags ignoreversion because the manifest verifies integrity.
Source: "..\..\dist\lamf-windows-payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LAMF Control"; Filename: "{app}\{#MyAppControlName}"
Name: "{group}\Uninstall LAMF"; Filename: "{uninstallexe}"
Name: "{autodesktop}\LAMF Control"; Filename: "{app}\{#MyAppControlName}"; Tasks: desktopicon

; The uninstall helper is invoked from CurUninstallStepChanged below so that
; Inno Setup can honor a non-zero exit code and abort before removing files.

[Code]
var
  DataDirPage: TInputDirWizardPage;
  ProfilePage: TInputOptionWizardPage;
  OptimizationsPage: TInputOptionWizardPage;
  ModulesPage: TInputOptionWizardPage;
  HarnessesPage: TInputOptionWizardPage;
  ReviewPage: TWizardPage;
  ReviewLabel: TNewStaticText;
  SelectedDataDir: String;
  SelectedProfile: String;
  SelectedHarnesses: String;
  SelectedModules: String;
  OptimizationsEnabled: String;
  // Track whether a value came from a silent/command-line parameter so the UI
  // defaults in NextButtonClick do not overwrite it.
  ProfileFromCmd: Boolean;
  OptimizationsEnabledFromCmd: Boolean;
  ModulesFromCmd: Boolean;
  HarnessesFromCmd: Boolean;

function GetDataDir(Param: String): String;
begin
  if SelectedDataDir = '' then
    SelectedDataDir := ExpandConstant('{param:DATADIR|{localappdata}\LAMF\data}');
  Result := SelectedDataDir;
end;

function GetProfile(Param: String): String;
begin
  if SelectedProfile = '' then
  begin
    SelectedProfile := ExpandConstant('{param:PROFILE|{param:SECURITYPROFILE|controlled}}');
    ProfileFromCmd := (SelectedProfile <> 'controlled') or
                       (ExpandConstant('{param:PROFILE|}') <> '') or
                       (ExpandConstant('{param:SECURITYPROFILE|}') <> '');
  end;
  Result := SelectedProfile;
end;

function GetHarnesses(Param: String): String;
begin
  if SelectedHarnesses = '' then
  begin
    SelectedHarnesses := ExpandConstant('{param:HARNESSES|}');
    HarnessesFromCmd := SelectedHarnesses <> '';
  end;
  Result := SelectedHarnesses;
end;

function GetModules(Param: String): String;
begin
  if SelectedModules = '' then
  begin
    // /MODULES is the canonical switch; /OPTIMIZATIONS is the documented alias.
    SelectedModules := ExpandConstant('{param:MODULES|{param:OPTIMIZATIONS|}}');
    ModulesFromCmd := SelectedModules <> '';
  end;
  Result := SelectedModules;
end;

function GetOptimizationsEnabled(Param: String): String;
var
  Raw: String;
begin
  if OptimizationsEnabled = '' then
  begin
    Raw := ExpandConstant('{param:OPTIMIZATIONS_ENABLED|}');
    if Raw = '' then
      OptimizationsEnabled := '1'
    else
      OptimizationsEnabled := Raw;
    OptimizationsEnabledFromCmd := Raw <> '';
  end;
  Result := OptimizationsEnabled;
end;

function GetSilentParam(Param: String): String;
begin
  if WizardSilent then
    Result := 'true'
  else
    Result := 'false';
end;

function ExistingAncestor(Path: String): String;
var
  Prev: String;
begin
  Result := Path;
  while (Result <> '') and not DirExists(Result) do
  begin
    Prev := Result;
    Result := ExtractFileDir(Result);
    if Result = Prev then
      Break;
  end;
  if Result = '' then
    Result := ExpandConstant('{sd}');
end;

function HasEnoughSpace(Path: String; RequiredGB: Integer): Boolean;
var
  FreeBytes: Int64;
  TotalBytes: Int64;
begin
  Result := GetSpaceOnDisk64(Path, FreeBytes, TotalBytes);
  if Result then
    Result := FreeBytes >= Int64(RequiredGB) * 1024 * 1024 * 1024;
end;

function SanitizeModuleId(const S: String): String;
var
  I: Integer;
  C: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    if (C <> ' ') and (C <> '/') and (C <> '\') then
      Result := Result + C;
  end;
  Result := Lowercase(Result);
end;

function PathsOverlap(A, B: String): Boolean;
var
  LowerA: String;
  LowerB: String;
begin
  LowerA := Lowercase(A);
  LowerB := Lowercase(B);
  if (Length(LowerA) > 0) and (LowerA[Length(LowerA)] <> '\') then
    LowerA := LowerA + '\';
  if (Length(LowerB) > 0) and (LowerB[Length(LowerB)] <> '\') then
    LowerB := LowerB + '\';
  Result := (Pos(LowerA, LowerB) = 1) or (Pos(LowerB, LowerA) = 1);
end;

procedure ReviewPageActivate(Sender: TWizardPage);
var
  ReviewText: String;
begin
  ReviewText := 'Application folder:' + #13#10 + WizardDirValue + #13#10#13#10 +
                'Private memory folder:' + #13#10 + GetDataDir('') + #13#10#13#10 +
                'Security profile: ' + GetProfile('') + #13#10#13#10 +
                'Agent optimizations: ';
  if GetOptimizationsEnabled('') = 'true' then
    ReviewText := ReviewText + 'enabled' + #13#10
  else
    ReviewText := ReviewText + 'disabled' + #13#10;
  if GetModules('') <> '' then
    ReviewText := ReviewText + 'Modules: ' + GetModules('') + #13#10#13#10
  else
    ReviewText := ReviewText + #13#10;
  if GetHarnesses('') <> '' then
    ReviewText := ReviewText + 'Configured agents: ' + GetHarnesses('') + #13#10#13#10
  else
    ReviewText := ReviewText + 'No agents selected.' + #13#10#13#10;
  ReviewText := ReviewText + 'Existing data will be preserved if present.';
  ReviewLabel.Caption := ReviewText;
end;

procedure InitializeWizard;
var
  PageIndex: Integer;
  L: TLabel;
  InstallDirParam: String;
  I: Integer;
  CmdProfile: String;
  CmdOptimizationsEnabled: String;
  CmdModules: TStringList;
  CmdHarnesses: TStringList;
begin
  // Honour /INSTALLDIR as an alias for Inno Setup's canonical /DIR switch.
  InstallDirParam := ExpandConstant('{param:INSTALLDIR|}');
  if InstallDirParam <> '' then
    WizardForm.DirEdit.Text := InstallDirParam;

  // Pre-load command-line/silent values so the wizard UI can reflect them and
  // NextButtonClick will not overwrite them with page defaults.
  CmdProfile := GetProfile('');
  CmdOptimizationsEnabled := GetOptimizationsEnabled('');
  CmdModules := TStringList.Create;
  CmdHarnesses := TStringList.Create;
  try
    CmdModules.CommaText := GetModules('');
    CmdHarnesses.CommaText := GetHarnesses('');

    PageIndex := wpSelectDir;

  // Data directory page (after app directory page)
  DataDirPage := CreateInputDirPage(PageIndex,
    'Choose where your private memory lives',
    'This folder is separate from the application and holds your memory, keys, and settings.',
    '',
    False, '');
  DataDirPage.Add('Private memory folder:');
  DataDirPage.Values[0] := GetDataDir('');
  L := TLabel.Create(WizardForm);
  L.Parent := DataDirPage.Surface;
  L.Caption := 'Existing data in this folder will be preserved and upgraded.';
  L.Top := DataDirPage.Edits[0].Top + 30;
  L.Left := DataDirPage.Edits[0].Left;
  L.Width := DataDirPage.SurfaceWidth;
  L.WordWrap := True;

  // Profile selection page
  ProfilePage := CreateInputOptionPage(DataDirPage.ID,
    'Protect your memory',
    'Choose the security profile for this LAMF instance.',
    'The default is controlled: your memory is private and agent access is explicit.',
    True, False);
  ProfilePage.Add('locked        — maximum isolation, no automatic agent context');
  ProfilePage.Add('controlled    — safe default: explicit access, local-only (recommended)');
  ProfilePage.Add('trusted-local — allow nearby local agents you have approved');
  ProfilePage.Add('open-local    — permissive local-only mode for rapid experimentation');
  if CmdProfile = 'locked' then
    ProfilePage.SelectedValueIndex := 0
  else if CmdProfile = 'controlled' then
    ProfilePage.SelectedValueIndex := 1
  else if CmdProfile = 'trusted-local' then
    ProfilePage.SelectedValueIndex := 2
  else if CmdProfile = 'open-local' then
    ProfilePage.SelectedValueIndex := 3
  else
    ProfilePage.SelectedValueIndex := 1;

  // Optimizations master switch (mutually exclusive: Enabled / Disabled)
  OptimizationsPage := CreateInputOptionPage(ProfilePage.ID,
    'Agent optimizations',
    'Optional instruction modules that help agents use your memory effectively.',
    'Optimizations are individually switchable and fail open.',
    True, True);
  OptimizationsPage.Add('Enabled');
  OptimizationsPage.Add('Disabled');
  if (CmdOptimizationsEnabled = '0') or (CmdOptimizationsEnabled = 'false') or
     (CmdOptimizationsEnabled = 'no') or (CmdOptimizationsEnabled = 'off') then
    OptimizationsPage.SelectedValueIndex := 1
  else
    OptimizationsPage.SelectedValueIndex := 0;

  // Individual optimization modules (multi-select checkboxes)
  ModulesPage := CreateInputOptionPage(OptimizationsPage.ID,
    'Optimization modules',
    'Select the optimization modules to activate now.',
    'You can change these at any time in LAMF Control.',
    False, True);
  ModulesPage.Add('minimal-solution');
  ModulesPage.Add('verified-execution');
  ModulesPage.Add('selective-workflows');
  ModulesPage.Add('stale-context-guards');
  ModulesPage.Add('surgical-changes');
  for I := 0 to ModulesPage.CheckListBox.Items.Count - 1 do
    if ModulesFromCmd then
      ModulesPage.CheckListBox.Checked[I] := CmdModules.IndexOf(SanitizeModuleId(ModulesPage.CheckListBox.Items[I])) >= 0
    else
      ModulesPage.CheckListBox.Checked[I] := True;

  // Harness selection page (multi-select checkboxes)
  HarnessesPage := CreateInputOptionPage(ModulesPage.ID,
    'Connect your agents',
    'Register LAMF as an MCP memory server for the agents you use.',
    'Nothing is selected automatically. Only checked agents are configured.',
    False, True);
  HarnessesPage.Add('OpenAI Codex');
  HarnessesPage.Add('Claude Code / Claude Desktop');
  HarnessesPage.Add('Kimi Code CLI');
  HarnessesPage.Add('Gemini CLI');
  HarnessesPage.Add('Grok Build CLI');
  HarnessesPage.Add('OpenClaw');
  HarnessesPage.Add('Hermes Agent');
  HarnessesPage.Add('Generic MCP client (emits a copyable snippet)');
  if HarnessesFromCmd then
  begin
    for I := 0 to HarnessesPage.CheckListBox.Items.Count - 1 do
      HarnessesPage.CheckListBox.Checked[I] := False;
    if CmdHarnesses.IndexOf('codex') >= 0 then HarnessesPage.CheckListBox.Checked[0] := True;
    if CmdHarnesses.IndexOf('claude') >= 0 then HarnessesPage.CheckListBox.Checked[1] := True;
    if CmdHarnesses.IndexOf('kimi') >= 0 then HarnessesPage.CheckListBox.Checked[2] := True;
    if CmdHarnesses.IndexOf('gemini') >= 0 then HarnessesPage.CheckListBox.Checked[3] := True;
    if CmdHarnesses.IndexOf('grok') >= 0 then HarnessesPage.CheckListBox.Checked[4] := True;
    if CmdHarnesses.IndexOf('openclaw') >= 0 then HarnessesPage.CheckListBox.Checked[5] := True;
    if CmdHarnesses.IndexOf('hermes') >= 0 then HarnessesPage.CheckListBox.Checked[6] := True;
    if CmdHarnesses.IndexOf('generic') >= 0 then HarnessesPage.CheckListBox.Checked[7] := True;
  end;

  // Review page
  ReviewPage := CreateCustomPage(HarnessesPage.ID, 'Review your choices', 'Confirm before installation.');
  ReviewLabel := TNewStaticText.Create(WizardForm);
  ReviewLabel.Parent := ReviewPage.Surface;
  ReviewLabel.Left := 0;
  ReviewLabel.Top := 0;
  ReviewLabel.Width := ReviewPage.SurfaceWidth;
  ReviewLabel.Height := ReviewPage.SurfaceHeight;
  ReviewLabel.WordWrap := True;
  ReviewLabel.Caption := 'Review';
  ReviewPage.OnActivate := @ReviewPageActivate;
  finally
    CmdModules.Free;
    CmdHarnesses.Free;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
  Items: TStringList;
  ProfileIndex: Integer;
begin
  Result := True;

  if CurPageID = DataDirPage.ID then
  begin
    SelectedDataDir := DataDirPage.Values[0];
    if SelectedDataDir = '' then
    begin
      MsgBox('Please choose a private memory folder.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if PathsOverlap(WizardDirValue, SelectedDataDir) then
    begin
      MsgBox('The private memory folder cannot be inside the application folder, and the application folder cannot be inside the private memory folder.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if not HasEnoughSpace(ExistingAncestor(SelectedDataDir), 1) then
    begin
      if MsgBox('The selected drive may not have enough free space for LAMF data. Continue anyway?',
                mbConfirmation, MB_YESNO) = IDNO then
      begin
        Result := False;
        Exit;
      end;
    end;
  end;

  if CurPageID = ProfilePage.ID then
  begin
    if not ProfileFromCmd then
    begin
      ProfileIndex := ProfilePage.SelectedValueIndex;
      case ProfileIndex of
        0: SelectedProfile := 'locked';
        1: SelectedProfile := 'controlled';
        2: SelectedProfile := 'trusted-local';
        3: SelectedProfile := 'open-local';
      else
        SelectedProfile := 'controlled';
      end;
    end;
  end;

  if CurPageID = OptimizationsPage.ID then
  begin
    if not OptimizationsEnabledFromCmd then
    begin
      if OptimizationsPage.SelectedValueIndex = 0 then
        OptimizationsEnabled := 'true'
      else
        OptimizationsEnabled := 'false';
    end;
  end;

  if CurPageID = ModulesPage.ID then
  begin
    if not ModulesFromCmd then
    begin
      Items := TStringList.Create;
      try
        for I := 0 to ModulesPage.CheckListBox.Items.Count - 1 do
          if ModulesPage.CheckListBox.Checked[I] then
            Items.Add(SanitizeModuleId(ModulesPage.CheckListBox.Items[I]));
        SelectedModules := Items.CommaText;
      finally
        Items.Free;
      end;
    end;
  end;

  if CurPageID = HarnessesPage.ID then
  begin
    if not HarnessesFromCmd then
    begin
      Items := TStringList.Create;
      try
        // Map UI labels to harness ids in the order they were added.
        if HarnessesPage.CheckListBox.Checked[0] then Items.Add('codex');
        if HarnessesPage.CheckListBox.Checked[1] then Items.Add('claude');
        if HarnessesPage.CheckListBox.Checked[2] then Items.Add('kimi');
        if HarnessesPage.CheckListBox.Checked[3] then Items.Add('gemini');
        if HarnessesPage.CheckListBox.Checked[4] then Items.Add('grok');
        if HarnessesPage.CheckListBox.Checked[5] then Items.Add('openclaw');
        if HarnessesPage.CheckListBox.Checked[6] then Items.Add('hermes');
        if HarnessesPage.CheckListBox.Checked[7] then Items.Add('generic');
        SelectedHarnesses := Items.CommaText;
      finally
        Items.Free;
      end;
    end;
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine +
            'Private memory folder: ' + GetDataDir('') + NewLine +
            'Profile: ' + GetProfile('') + NewLine +
            'Optimizations enabled: ' + GetOptimizationsEnabled('') + NewLine +
            'Modules: ' + GetModules('') + NewLine +
            'Harnesses: ' + GetHarnesses('') + NewLine +
            'Existing data will be preserved.' + NewLine;
end;

function RunPostInstall: Boolean;
var
  PythonExe: String;
  PostInstallScript: String;
  Params: String;
  LogFile: String;
  ResultCode: Integer;
  ShowCmd: Integer;
begin
  PythonExe := ExpandConstant('{app}\python\python.exe');
  PostInstallScript := ExpandConstant('{app}\post_install.py');
  LogFile := ExpandConstant('{app}\post_install.log');

  Params := Format('"%s" /APP_DIR="%s" /DATA_DIR="%s" /PROFILE="%s" /HARNESSES="%s" /MODULES="%s" /OPTIMIZATIONS_ENABLED="%s" /SILENT="%s" /LOG_FILE="%s"', [PostInstallScript,
     ExpandConstant('{app}'),
     GetDataDir(''),
     GetProfile(''),
     GetHarnesses(''),
     GetModules(''),
     GetOptimizationsEnabled(''),
     GetSilentParam(''),
     LogFile]);

  if WizardSilent then
    ShowCmd := SW_HIDE
  else
    ShowCmd := SW_SHOWMINIMIZED;

  if not Exec(PythonExe, Params, '', ShowCmd, ewWaitUntilTerminated, ResultCode) then
  begin
    if WizardSilent then
      Log('Failed to launch the LAMF post-installation step. Setup cannot continue.')
    else
      MsgBox('Failed to launch the LAMF post-installation step. Setup cannot continue.', mbError, MB_OK);
    Result := False;
    Exit;
  end;

  if ResultCode <> 0 then
  begin
    if WizardSilent then
      Log(Format('LAMF post-installation failed (exit code %d). See %s for details.', [ResultCode, LogFile]))
    else
      MsgBox(Format('LAMF post-installation failed (exit code %d). See %s for details.', [ResultCode, LogFile]), mbError, MB_OK);
    Result := False;
    Exit;
  end;

  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not RunPostInstall then
      Abort;
  end;
end;

function InitializeSetup: Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  HelperPath: String;
  Params: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    HelperPath := ExpandConstant('{app}\uninstall.exe');
    Params := ExpandConstant('/APP_DIR="{app}" /INNO_MODE /SILENT /LOG_FILE="{app}\uninstall-helper.log"');
    if not Exec(HelperPath, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      Log('LAMF uninstall helper could not be launched. Aborting uninstall to avoid stale harness registrations.');
      Abort;
    end;
    if ResultCode <> 0 then
    begin
      Log(Format('LAMF uninstall helper reported failure (exit code %d). Aborting uninstall to avoid stale harness registrations.', [ResultCode]));
      Abort;
    end;
  end;
end;
