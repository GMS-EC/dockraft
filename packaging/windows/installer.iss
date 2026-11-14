#ifndef MyAppVersion
  #define ChangelogHandle FileOpen(AddBackslash(SourcePath) + "..\..\CHANGELOG.md")
  #define MyAppVersion ""
  #if ChangelogHandle
    #sub ParseChangelogLine
      #define LineText FileRead(ChangelogHandle)
      #if MyAppVersion == "" && Copy(LineText, 1, 4) == "## ["
        #define CloseBracketPos Pos("]", LineText)
        #if CloseBracketPos > 5
          #define MyAppVersion Copy(LineText, 5, CloseBracketPos - 5)
        #endif
      #endif
    #endsub
    #for {0; !FileEof(ChangelogHandle) && MyAppVersion == ""; 0} ParseChangelogLine
    #expr FileClose(ChangelogHandle)
  #endif
#endif

[Setup]
AppId={{7D5E8B3A-4C9E-4F12-9B2A-8C1F4A9E1500}
AppName=Dockraft
AppVersion={#MyAppVersion}
AppPublisher=Marcus Mayorga (GMS-EC)
AppPublisherURL=https://gmsec.cc
AppSupportURL=https://github.com/GMS-EC/dockraft
DefaultDirName={localappdata}\Programs\Dockraft
DefaultGroupName=Dockraft
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Dockraft-Setup-{#MyAppVersion}
SetupIconFile=dockraft.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\Dockraft\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Dockraft"; Filename: "{app}\Dockraft.exe"
Name: "{group}\{cm:UninstallProgram,Dockraft}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Dockraft"; Filename: "{app}\Dockraft.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Dockraft.exe"; Description: "{cm:LaunchProgram,Dockraft}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\.dockraft_root"
